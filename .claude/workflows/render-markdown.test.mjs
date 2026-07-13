// Tests for renderReviewMarkdown (frontmatter, verdict, findings counts) and
// decideVerdict in review-fanout.workflow.js.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/*.test.mjs

import test from "node:test";
import assert from "node:assert/strict";
import {
  pure,
  finding,
  lines,
  reviewBase,
  frontmatter,
  decide,
  verdictState,
  CONSOLIDATION_RE,
} from "./_harness.mjs";
test("the review file verdict, reviewers and tests token follow the legacy contract", () => {
  const p = pure();
  const args = {
    prd: "00064",
    review: "1",
    date: "2026-07-13",
    head_sha: "abc1234",
  };
  const base = reviewBase(p);

  const clean = p.renderReviewMarkdown(base, args);
  const cleanLines = lines(clean);
  assert.equal(cleanLines[0], "---", "the file opens with YAML frontmatter");
  assert.ok(
    cleanLines.some((l) => l.trim() === "reviewers: alice"),
    "frontmatter carries reviewers: alice",
  );
  assert.ok(cleanLines.some((l) => l.includes("00064")), "frontmatter carries the prd");
  assert.ok(cleanLines.some((l) => l.includes("abc1234")), "frontmatter carries the head sha");
  assert.ok(cleanLines.includes("Verdict: converged"), "zero blocking findings converge");

  const aliceAt = cleanLines.findIndex((l) => l.startsWith("## Alice"));
  assert.notEqual(aliceAt, -1, "the review has an ## Alice section");
  const firstBody = cleanLines.slice(aliceAt + 1).find((l) => l.trim() !== "");
  assert.ok(
    !firstBody.startsWith("###"),
    `the section must not open with a subheading, got: ${firstBody}`,
  );
  assert.ok(firstBody.includes("✅ No issues found"), firstBody);

  const testsLine = cleanLines.find((l) => l.startsWith("Tests:"));
  assert.ok(testsLine, "the review file carries a Tests: line");
  assert.ok(
    testsLine.includes("{{TESTS_LINE}}"),
    `an absent tests_line renders the literal token, got: ${testsLine}`,
  );

  const blocking = [
    finding({
      title: "rce",
      severity: "CRITICAL",
      file: "src/a.js",
      task: "1",
      proof: "p",
      verified: "confirmed",
    }),
    finding({
      title: "traversal",
      severity: "HIGH",
      file: "src/b.js",
      task: "2",
      proof: "p",
      verified: "confirmed",
    }),
  ];
  const dirty = p.renderReviewMarkdown({ ...base, blocking, confirmed: 2 }, args);
  const dirtyLines = lines(dirty);
  assert.ok(dirtyLines.includes("Verdict: 2 findings"), "two blocking findings block convergence");

  const dirtyAliceAt = dirtyLines.findIndex((l) => l.startsWith("## Alice"));
  const dirtyFirstBody = dirtyLines.slice(dirtyAliceAt + 1).find((l) => l.trim() !== "");
  assert.ok(
    !dirtyFirstBody.startsWith("###"),
    `the section must not open with a subheading, got: ${dirtyFirstBody}`,
  );
  assert.ok(
    dirtyFirstBody.includes(" | File:"),
    `the first body line is a finding line, got: ${dirtyFirstBody}`,
  );
});

test("a supplied tests_line is rendered verbatim and replaces the placeholder token", () => {
  const p = pure();
  const args = {
    prd: "00064",
    review: "1",
    date: "2026-07-13",
    head_sha: "abc1234",
    // The caller hands over the COMPLETE line, prefix included.
    tests_line: "Tests: 12 passed, 0 failed, 0 skipped",
  };
  const base = reviewBase(p);

  const out = p.renderReviewMarkdown(base, args);
  const outLines = lines(out);

  assert.ok(
    outLines.includes("Tests: 12 passed, 0 failed, 0 skipped"),
    `the supplied tests_line must be rendered verbatim, got:\n${out}`,
  );
  assert.ok(
    !out.includes("{{TESTS_LINE}}"),
    "the placeholder token must not ship once a tests_line was supplied",
  );
  assert.equal(
    outLines.filter((l) => l.startsWith("Tests:")).length,
    1,
    "exactly one Tests: line, with no duplicated prefix",
  );
});

test("the review file names the agent that wrote it, rather than hardcoding Alice", () => {
  const p = pure();
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };

  const out = p.renderReviewMarkdown(reviewBase(p, { agentName: "BLAKE" }), args);
  const outLines = lines(out);

  assert.ok(
    frontmatter(out).some((l) => l.trim() === "reviewers: blake"),
    `frontmatter must carry reviewers: blake, got:\n${out}`,
  );
  assert.ok(
    outLines.some((l) => l.startsWith("## Blake")),
    `the section heading must be ## Blake, got:\n${out}`,
  );
  assert.ok(
    !/alice/i.test(out),
    `a review written by BLAKE must mention no Alice anywhere:\n${out}`,
  );
});

test("the review frontmatter carries the date and the review number it was given", () => {
  const p = pure();
  const args = {
    prd: "00064",
    review: "7",
    date: "2026-07-13",
    head_sha: "abcdef0", // deliberately free of the digit 7, so the review number is unambiguous
  };

  const fm = frontmatter(p.renderReviewMarkdown(reviewBase(p), args)).join("\n");
  assert.ok(fm.includes(args.date), `frontmatter must carry the date, got:\n${fm}`);
  assert.ok(fm.includes(args.review), `frontmatter must carry the review number, got:\n${fm}`);
  assert.ok(fm.includes(args.prd), `frontmatter must carry the prd, got:\n${fm}`);
  assert.ok(fm.includes(args.head_sha), `frontmatter must carry the head sha, got:\n${fm}`);
});

test("an unverified potential blocker means the review has not converged", () => {
  const p = pure();
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };

  // Control: with nothing outstanding, the same base does converge.
  assert.ok(
    lines(p.renderReviewMarkdown(reviewBase(p), args)).includes("Verdict: converged"),
    "the control case converges, so the fixtures below isolate the unverified count",
  );

  // Zero blocking findings, but a cap-overflowed finding was never verified: it
  // may well be a real blocker, so an empty blocking array is not convergence.
  const capped = lines(p.renderReviewMarkdown(reviewBase(p, { unverified: 3 }), args));
  assert.ok(
    !capped.includes("Verdict: converged"),
    `an unverified potential blocker must not be reported as converged:\n${capped.join("\n")}`,
  );
  assert.ok(
    capped.some((l) => l.startsWith("Verdict:")),
    "the review file still carries a Verdict: line",
  );
});

test("the verdict is decided by a pure function the harness can reach, not by an inline ternary", () => {
  const p = pure();
  assert.equal(
    typeof p.decideVerdict,
    "function",
    "decideVerdict({blocking, incomplete, unverified}) must live INSIDE the pure region: " +
      "a verdict computed inline at the bottom of the script is unreachable from any test, " +
      "so nothing can prove the engine fails closed",
  );
});

test("a blocking finding cannot produce APPROVE", () => {
  const p = pure();
  const confirmed = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "req.body.cmd reaches child_process.exec at line 17",
    verified: "confirmed",
  });

  assert.equal(decide(p, verdictState({ blocking: [confirmed] })), "CHANGES_REQUESTED");
});

test("an incomplete review cannot produce APPROVE", () => {
  const p = pure();
  // A dimension agent (or a verifier) never answered. The reviewer did not look
  // at part of the change, so it cannot vouch for it.
  assert.equal(decide(p, verdictState({ incomplete: true })), "CHANGES_REQUESTED");
});

test("an unverified potential blocker cannot produce APPROVE", () => {
  const p = pure();
  // Nothing blocks and nothing is incomplete, but a CRITICAL/HIGH was pushed
  // past VERIFY_CAP and never disproven. Unproven is not innocent.
  assert.equal(
    decide(p, verdictState({ unverified: 1 })),
    "CHANGES_REQUESTED",
    "a finding nobody verified may well be real, so it must not ship an APPROVE",
  );
  assert.equal(decide(p, verdictState({ unverified: 7 })), "CHANGES_REQUESTED");
});

test("a review approves only when nothing blocks, nothing is incomplete and nothing is unverified", () => {
  const p = pure();
  const blocker = finding({
    title: "auth bypass",
    severity: "CRITICAL",
    file: "src/auth.js",
    proof: "the guard is never called",
    verified: "confirmed",
  });

  assert.equal(
    decide(p, verdictState()),
    "APPROVE",
    "all three gates clear: this is the only state that approves",
  );

  // Every non-clear combination is a CHANGES_REQUESTED, so no pair of triggers
  // can cancel out and no single trigger is silently ignored.
  for (const blocking of [[], [blocker]]) {
    for (const incomplete of [false, true]) {
      for (const unverified of [0, 2]) {
        const state = { blocking, incomplete, unverified };
        const clear = blocking.length === 0 && !incomplete && unverified === 0;
        const expected = clear ? "APPROVE" : "CHANGES_REQUESTED";
        assert.equal(
          decide(p, state),
          expected,
          `blocking=${blocking.length} incomplete=${incomplete} unverified=${unverified}`,
        );
      }
    }
  }
});

test("the rendered verdict count and the returned verdict never disagree about convergence", () => {
  const p = pure();
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };
  const blocker = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "cmd reaches exec",
    verified: "confirmed",
  });

  const cases = [
    ["a clean run", { blocking: [], unverified: 0, failedDimensions: [], verifierFailures: [] }],
    ["a confirmed blocker", { blocking: [blocker], unverified: 0, failedDimensions: [], verifierFailures: [] }],
    ["a cap overflow", { blocking: [], unverified: 2, failedDimensions: [], verifierFailures: [] }],
    ["a dead dimension", { blocking: [], unverified: 0, failedDimensions: ["security"], verifierFailures: [] }],
    [
      "a dead verifier",
      {
        blocking: [],
        unverified: 0,
        failedDimensions: ["verify:rce via cmd param"],
        verifierFailures: ["rce via cmd param"],
      },
    ],
  ];

  for (const [label, state] of cases) {
    // The engine marks the review incomplete exactly when a dimension or a
    // verifier failed to answer.
    const incomplete = state.failedDimensions.length > 0;
    const verdict = decide(p, {
      blocking: state.blocking,
      incomplete,
      unverified: state.unverified,
    });
    const converged = lines(p.renderReviewMarkdown(reviewBase(p, state), args)).includes(
      "Verdict: converged",
    );

    assert.equal(
      converged,
      verdict === "APPROVE",
      `${label}: the review file says ${converged ? "converged" : "not converged"} while the ` +
        `returned verdict is ${verdict} — one run must not ship two contradictory answers`,
    );
  }
});

test("a dead verifier means the review has not converged", () => {
  const p = pure();
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };

  const dead = lines(
    p.renderReviewMarkdown(
      reviewBase(p, { verifierFailures: ["rce in job runner", "csrf token never checked"] }),
      args,
    ),
  );
  assert.ok(
    !dead.includes("Verdict: converged"),
    `a verifier that never answered must not be reported as converged:\n${dead.join("\n")}`,
  );
  assert.ok(
    dead.some((l) => l.startsWith("Verdict:")),
    "the review file still carries a Verdict: line",
  );
});

// ---- the rendered count: every outstanding item is counted, not just the blockers ----
//
// "Verdict: N findings" is what a human (and the rework step) reads first. A count
// that only sums `blocking` renders "Verdict: 0 findings" for a review held open by
// unverified findings, a dead verifier, or a dead dimension: it reads as clean while
// claiming non-convergence, and 0 is the number that gets believed.

/** The single Verdict: line of a rendered review file. */
function verdictLine(p, state) {
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };
  const found = lines(p.renderReviewMarkdown(reviewBase(p, state), args)).filter((l) =>
    l.startsWith("Verdict:"),
  );
  assert.equal(found.length, 1, `exactly one Verdict: line, got ${found.length}`);
  return found[0];
}

test("a review held open only by unverified findings renders that exact count, never a clean zero", () => {
  const p = pure();
  assert.equal(
    verdictLine(p, { unverified: 3 }),
    "Verdict: 3 findings",
    "three cap-overflowed potential blockers are three outstanding findings",
  );
  assert.equal(verdictLine(p, { unverified: 1 }), "Verdict: 1 findings");
  assert.notEqual(
    verdictLine(p, { unverified: 3 }),
    "Verdict: 0 findings",
    "a count that ignores the unverified reads as a clean review while refusing to converge",
  );
});

test("a review held open only by a dead verifier renders that exact count, never a clean zero", () => {
  const p = pure();
  assert.equal(
    verdictLine(p, { verifierFailures: ["rce in job runner", "csrf token never checked"] }),
    "Verdict: 2 findings",
    "two verifiers that never answered are two outstanding findings",
  );
  assert.equal(verdictLine(p, { verifierFailures: ["rce in job runner"] }), "Verdict: 1 findings");
});

test("a review held open only by a dead dimension renders that exact count, never a clean zero", () => {
  const p = pure();
  assert.equal(
    verdictLine(p, { failedDimensions: ["security", "tests"] }),
    "Verdict: 2 findings",
    "two dimensions that returned nothing are two outstanding findings",
  );
  assert.equal(verdictLine(p, { failedDimensions: ["rubric"] }), "Verdict: 1 findings");
});

test("the rendered count sums every source of non-convergence, so no source can be dropped", () => {
  const p = pure();
  const blocker = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "cmd reaches exec",
    verified: "confirmed",
  });

  // One of each, deliberately distinct, so a count that drops any single source
  // lands on a different number than 5 and this fails with the number it produced.
  assert.equal(
    verdictLine(p, {
      blocking: [blocker],
      unverified: 2,
      verifierFailures: ["csrf token never checked"],
      failedDimensions: ["security"],
    }),
    "Verdict: 5 findings",
    "1 blocking + 2 unverified + 1 dead verifier + 1 dead dimension = 5 outstanding findings",
  );

  // The control: with all four sources empty, and only then, the review converges.
  assert.equal(verdictLine(p, {}), "Verdict: converged");
});

test("a dead verifier already counted via blocking is not counted again by verifierFailures", () => {
  const p = pure();
  const dead = finding({
    title: "rce in job runner",
    severity: "CRITICAL",
    file: "src/jobs.js",
    task: "3",
    proof: "proof for rce in job runner",
    verified: "verifier_failed",
  });

  assert.equal(
    verdictLine(p, {
      blocking: [dead],
      unverified: 0,
      verifierFailures: ["rce in job runner"],
      failedDimensions: [],
    }),
    "Verdict: 1 findings",
    "one dead verifier is one outstanding item: it must not be counted once via blocking " +
      "and again via verifierFailures for the very same finding",
  );
});

test("verifierFailures still counts independently when it names a finding blocking does not carry", () => {
  const p = pure();
  // Control for the test above: when a verifierFailures title does NOT correspond to
  // anything in blocking, it must still add to the count -- the dedup must key off the
  // actual overlap, not silently discard verifierFailures whenever blocking is non-empty.
  const unrelatedBlocker = finding({
    title: "auth bypass",
    severity: "CRITICAL",
    file: "src/auth.js",
    task: "1",
    proof: "the guard is never called",
    verified: "confirmed",
  });

  assert.equal(
    verdictLine(p, {
      blocking: [unrelatedBlocker],
      unverified: 0,
      verifierFailures: ["some other finding entirely"],
      failedDimensions: [],
    }),
    "Verdict: 2 findings",
    "a verifierFailures entry naming a DIFFERENT finding than anything in blocking is a second, " +
      "distinct outstanding item",
  );
});

test("advisory findings never inflate the Verdict count and never render as parseable lines, no matter how many pile up", () => {
  const p = pure();
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };
  const nits = Array.from({ length: 15 }, (_, i) =>
    finding({ title: `nit ${i}`, severity: "LOW", file: `src/n${i}.js`, task: String(i) }),
  );
  const blocker = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "cmd reaches exec",
    verified: "confirmed",
  });

  const out = p.renderReviewMarkdown(reviewBase(p, { blocking: [blocker], advisory: nits }), args);
  const outLines = lines(out);
  assert.ok(
    outLines.includes("Verdict: 1 findings"),
    `fifteen advisory nits must not inflate the blocking count:\n${out}`,
  );

  // The parseable-line count and the Verdict count must agree: exactly one
  // parseable line for the one blocking finding, not one per pile-up nit.
  const parseable = outLines.filter((l) => CONSOLIDATION_RE.test(l));
  assert.equal(
    parseable.length,
    1,
    `only the blocking finding may produce a line the consolidation script can parse; the fifteen ` +
      `advisory nits must not, or the Verdict count and the parseable-line count would disagree:\n${out}`,
  );
  assert.ok(parseable[0].includes("rce via cmd param"), parseable[0]);

  // The nits are information, not garbage: they must still appear, as inert notes.
  assert.ok(
    out.includes("### Advisory (does not block)"),
    `the fifteen advisory nits must still appear, under their own section:\n${out}`,
  );
  for (const nit of nits) {
    assert.ok(
      out.includes(nit.title),
      `advisory finding "${nit.title}" must still appear somewhere in the output:\n${out}`,
    );
  }
});

test("renderReviewMarkdown accepts a precomputed agent output instead of recomputing it internally", () => {
  const p = pure();
  const args = { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" };
  const precomputed = "PRECOMPUTED_AGENT_OUTPUT_MARKER";

  const out = p.renderReviewMarkdown(reviewBase(p), args, precomputed);
  assert.ok(
    out.includes(precomputed),
    `a precomputed agent output must be used verbatim instead of being recomputed from state:\n${out}`,
  );
  assert.ok(
    !out.includes("No issues found"),
    "when a precomputed output is supplied, the function must not fall back to computing its own",
  );
});
