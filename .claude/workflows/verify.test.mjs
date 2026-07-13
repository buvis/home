// Tests for adversarial verification and the verify cap (selectForVerify,
// applyVerification) in review-fanout.workflow.js.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/

import test from "node:test";
import assert from "node:assert/strict";
import { pure, finding, arr, render, lines, fileCell, decide, CONSOLIDATION_RE, reviewBase } from "./_harness.mjs";
test("an unverified over-cap finding carries its own file too, so the cap cannot erase the location", () => {
  const p = pure();
  // The over-cap finding is the one most likely to become a rework task without a
  // human ever reading it: nobody verified it, so nobody re-derived where it lives.
  const unproven = finding({
    title: "unauthenticated admin route",
    severity: "CRITICAL",
    file: "src/routes/admin.js",
    task: "4",
    proof: "no auth middleware on /admin",
  });

  const res = p.applyVerification({
    toVerify: [],
    verdicts: [],
    overflow: [unproven],
    passthrough: [],
  });
  assert.equal(res.unverified, 1);

  const out = render(p, { blocking: arr(res.blocking), advisory: arr(res.advisory) });
  const line = lines(out).find(
    (l) => l.startsWith("[ALICE]") && l.includes("unauthenticated admin route"),
  );
  assert.ok(line, `the unverified potential blocker must reach the findings table:\n${out}`);
  assert.equal(
    fileCell(line),
    "src/routes/admin.js",
    `an unverified finding keeps its file: it is still a rework candidate, and a rework ` +
      `task pointed at N/A is unfixable: ${line}`,
  );
});

test("a refuted finding renders as an inert note and never as a parseable finding line", () => {
  const p = pure();
  const f = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "2",
    proof: "cmd reaches exec",
  });

  const res = p.applyVerification({
    toVerify: [f],
    verdicts: [{ refuted: true, reason: "the branch is unreachable: cmd is validated at line 9" }],
    overflow: [],
    passthrough: [],
  });

  assert.equal(arr(res.blocking).length, 0, "a refuted finding must not block");
  assert.equal(arr(res.advisory).length, 1);
  assert.equal(arr(res.advisory)[0].verified, "refuted");
  assert.equal(
    arr(res.advisory)[0].refutation,
    "the branch is unreachable: cmd is validated at line 9",
  );
  assert.equal(res.refuted, 1);
  assert.equal(res.confirmed, 0);

  const out = render(p, { advisory: arr(res.advisory) });
  assert.ok(
    out.includes("### Refuted (adversarially verified, not blocking)"),
    "refuted notes need their heading",
  );
  const notes = lines(out).filter((l) => l.startsWith("- refuted:"));
  assert.equal(notes.length, 1);
  assert.ok(!notes[0].includes("|"), `a note line must contain no pipe: ${notes[0]}`);
  assert.ok(notes[0].includes("rce via cmd param"));
  assert.ok(notes[0].includes("the branch is unreachable"));
  assert.ok(
    !lines(out).some((l) => l.startsWith("[ALICE]") && l.includes("rce via cmd param")),
    "the refuted finding must not also appear as a parseable line",
  );
});

test("only a literal refuted:true refutes; any other verdict shape is a dead verifier that keeps the finding blocking", () => {
  const p = pure();
  const mk = (title, file, task) =>
    finding({ title, severity: "CRITICAL", file, task, proof: `proof for ${title}` });

  const nullVerdict = mk("unauthenticated admin route", "src/routes.js", "1");
  const emptyVerdict = mk("path traversal in upload", "src/upload.js", "2");
  const truthyStringVerdict = mk("rce in job runner", "src/jobs.js", "3");
  const errorVerdict = mk("secret logged in plaintext", "src/log.js", "4");
  const missingVerdict = mk("csrf token never checked", "src/form.js", "5");
  const alive = finding({
    title: "sql injection in search",
    severity: "HIGH",
    file: "src/search.js",
    task: "6",
    proof: "q is interpolated",
  });

  const res = p.applyVerification({
    toVerify: [
      nullVerdict,
      emptyVerdict,
      truthyStringVerdict,
      errorVerdict,
      missingVerdict,
      alive,
    ],
    verdicts: [
      null,
      {},
      { refuted: "no" }, // a truthy string is NOT a refutation
      { error: "timeout" },
      undefined,
      { refuted: false, reason: "confirmed by reading search.js" },
    ],
    overflow: [],
    passthrough: [],
  });

  const blocking = arr(res.blocking);
  assert.equal(
    blocking.length,
    6,
    "a dead or malformed verifier verdict must never disarm a proven finding",
  );
  assert.equal(arr(res.advisory).length, 0, "nothing was actually refuted");

  const byTitle = Object.fromEntries(blocking.map((f) => [f.title, f]));
  for (const title of [
    "unauthenticated admin route",
    "path traversal in upload",
    "rce in job runner",
    "secret logged in plaintext",
    "csrf token never checked",
  ]) {
    assert.equal(
      byTitle[title].verified,
      "verifier_failed",
      `${title}: a non-boolean verdict is a verifier failure, not a refutation`,
    );
  }
  assert.equal(byTitle["sql injection in search"].verified, "confirmed");

  assert.deepEqual(
    arr(res.verifierFailures).sort(),
    [
      "csrf token never checked",
      "path traversal in upload",
      "rce in job runner",
      "secret logged in plaintext",
      "unauthenticated admin route",
    ],
    "every dead verifier is recorded by name",
  );
  assert.equal(res.refuted, 0, "no verdict refuted anything");
  assert.equal(res.confirmed, 1, "only the one real refuted:false verdict confirms");

  const out = render(p, { blocking });
  assert.ok(
    lines(out).some(
      (l) =>
        l.startsWith("[ALICE] 🔴") &&
        l.includes("rce in job runner") &&
        l.includes(" | File:"),
    ),
    `a finding whose verifier answered {refuted: "no"} still blocks:\n${out}`,
  );
});

test("the verify cap is spent strictest-first, so an arrival-ordered HIGH never displaces a CRITICAL", () => {
  const p = pure();
  const findings = [];
  // Deliberately shuffled: the HIGHs arrive FIRST. An implementation that just
  // slices the first VERIFY_CAP blockers in arrival order would overflow a
  // CRITICAL here.
  for (let i = 0; i < 8; i++) {
    findings.push(
      finding({
        title: `high ${i}`,
        severity: "HIGH",
        file: `src/h${i}.js`,
        evidence: `evidence h${i}`,
        proof: `proof h${i}`,
      }),
    );
  }
  for (let i = 0; i < 5; i++) {
    findings.push(
      finding({
        title: `critical ${i}`,
        severity: "CRITICAL",
        file: `src/c${i}.js`,
        evidence: `evidence c${i}`,
        proof: `proof c${i}`,
      }),
    );
  }
  assert.equal(findings.length, 13);

  const { toVerify, overflow } = p.selectForVerify(findings);
  assert.equal(arr(toVerify).length, 12, "at most VERIFY_CAP findings are verified");
  assert.equal(arr(overflow).length, 1);
  assert.equal(
    arr(toVerify).filter((f) => f.severity === "CRITICAL").length,
    5,
    "strictest first: every CRITICAL makes the cut even when the HIGHs arrived first",
  );
  assert.deepEqual(
    arr(toVerify)
      .filter((f) => f.severity === "CRITICAL")
      .map((f) => f.title)
      .sort(),
    ["critical 0", "critical 1", "critical 2", "critical 3", "critical 4"],
  );
  assert.equal(arr(overflow)[0].severity, "HIGH", "the overflowed finding is the least severe");

  const verdicts = arr(toVerify).map(() => ({ refuted: false, reason: "confirmed" }));
  const res = p.applyVerification({
    toVerify: arr(toVerify),
    verdicts,
    overflow: arr(overflow),
    passthrough: [],
  });
  assert.equal(res.unverified, 1);
  assert.equal(arr(res.blocking).length, 12);
  const capped = arr(res.advisory).find((f) => f.verified === "unverified");
  assert.ok(capped, "the cap overflow lands in advisory as unverified");
  assert.equal(capped.severity, "HIGH");

  const out = render(p, { blocking: arr(res.blocking), advisory: arr(res.advisory) });
  const outLines = lines(out);

  // The cap overflow was never disproven, so it is still a potential blocker: it
  // must survive into the parseable findings, not evaporate into prose.
  const cappedLine = outLines.find(
    (l) => l.startsWith("[ALICE]") && l.includes(capped.title),
  );
  assert.ok(
    cappedLine,
    `an unverified potential blocker must render as a parseable finding line:\n${out}`,
  );
  assert.ok(cappedLine.includes(" | File:"), cappedLine);
  assert.ok(cappedLine.includes(" | Task:"), cappedLine);

  const notes = outLines.filter((l) => l.trim().startsWith("- unverified (verify cap):"));
  for (const note of notes) {
    assert.ok(!note.includes("|"), `a cap note must contain no pipe: ${note}`);
  }
});

test("non-blocking findings ride through verification untouched and still render as parseable advisory lines", () => {
  const p = pure();
  const medium = finding({
    title: "duplicated parsing helper",
    severity: "MEDIUM",
    file: "src/parse.js",
    task: "7",
  });
  const low = finding({
    title: "stray debug log",
    severity: "LOW",
    file: "src/log.js",
    task: "8",
  });
  const blocker = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "cmd reaches exec",
  });

  const res = p.applyVerification({
    toVerify: [blocker],
    verdicts: [{ refuted: false, reason: "confirmed" }],
    overflow: [],
    passthrough: [medium, low],
  });

  assert.equal(arr(res.blocking).length, 1, "passthrough findings never block");
  assert.equal(res.confirmed, 1);
  assert.equal(res.refuted, 0);
  assert.equal(res.unverified, 0, "a passthrough is not a cap overflow");

  const advisory = arr(res.advisory);
  const byTitle = Object.fromEntries(advisory.map((f) => [f.title, f]));
  assert.ok(
    byTitle["duplicated parsing helper"],
    `the MEDIUM passthrough must reach advisory, got: ${advisory.map((f) => f.title).join(", ")}`,
  );
  assert.ok(byTitle["stray debug log"], "the LOW passthrough must reach advisory");
  assert.equal(byTitle["duplicated parsing helper"].severity, "MEDIUM");
  assert.equal(byTitle["stray debug log"].severity, "LOW");
  assert.ok(
    !byTitle["duplicated parsing helper"].verified,
    "a passthrough was never verified, so it carries no verification verdict",
  );
  assert.ok(!byTitle["stray debug log"].verified);

  const out = render(p, { blocking: arr(res.blocking), advisory });
  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));

  const mediumLine = parseable.find((l) => l.includes("duplicated parsing helper"));
  assert.ok(mediumLine, `the MEDIUM passthrough must render as a parseable line:\n${out}`);
  assert.match(mediumLine, /^\[ALICE\] 🟡 /, mediumLine);
  assert.ok(mediumLine.includes(" | File:"), mediumLine);
  assert.ok(mediumLine.includes(" | Task: 7"), mediumLine);

  const lowLine = parseable.find((l) => l.includes("stray debug log"));
  assert.ok(lowLine, `the LOW passthrough must render as a parseable line:\n${out}`);
  assert.match(lowLine, /^\[ALICE\] ⚪ /, lowLine);
  assert.ok(lowLine.includes(" | File:"), lowLine);
  assert.ok(lowLine.includes(" | Task: 8"), lowLine);
});

test("thirteen proven blockers whose verified twelve are all refuted still cannot produce APPROVE", () => {
  const p = pure();
  assert.equal(p.VERIFY_CAP, 12, "the fixture overflows the cap by exactly one");

  const raw = [];
  for (let i = 0; i < 13; i++) {
    raw.push(
      finding({
        title: `critical ${i}`,
        severity: "CRITICAL",
        file: `src/c${i}.js`,
        evidence: `evidence c${i}`,
        proof: `req.body.cmd reaches exec at line ${i + 10} of c${i}.js`,
        task: String(i),
      }),
    );
  }

  const { findings: kept, demoted } = p.demote(raw);
  assert.equal(demoted, 0, "every fixture carries a proof, so nothing is demoted");
  const { unique } = p.dedupe(arr(kept));
  assert.equal(arr(unique).length, 13, "thirteen distinct defects");

  const { toVerify, overflow } = p.selectForVerify(arr(unique));
  assert.equal(arr(toVerify).length, 12);
  assert.equal(arr(overflow).length, 1, "the thirteenth blocker never gets a verifier");
  const unproven = arr(overflow)[0];

  const res = p.applyVerification({
    toVerify: arr(toVerify),
    verdicts: arr(toVerify).map(() => ({ refuted: true, reason: "guarded by the caller" })),
    overflow: arr(overflow),
    passthrough: [],
  });
  assert.equal(arr(res.blocking).length, 0, "all twelve verified findings came back refuted");
  assert.equal(res.refuted, 12);
  assert.equal(res.unverified, 1, "the thirteenth survives, unproven");

  const verdict = decide(p, {
    blocking: arr(res.blocking),
    incomplete: false,
    unverified: res.unverified,
  });
  assert.notEqual(
    verdict,
    "APPROVE",
    "an empty blocking list is not a clean review while a potential blocker was never checked",
  );
  assert.equal(verdict, "CHANGES_REQUESTED");

  const out = render(p, {
    blocking: arr(res.blocking),
    advisory: arr(res.advisory),
    statsLine: "stats: raw=13 unique=13",
  });
  assert.ok(
    !out.includes("✅ No issues found"),
    `the engine must not report a clean run while ${res.unverified} finding(s) went unverified:\n${out}`,
  );

  const line = lines(out).find((l) => l.startsWith("[ALICE]") && l.includes(unproven.title));
  assert.ok(line, `the unproven blocker must survive into the output:\n${out}`);
  assert.match(
    line,
    CONSOLIDATION_RE,
    `the unproven blocker must be parseable by the consolidation script, or it never becomes a rework task: ${line}`,
  );

  const review = lines(
    p.renderReviewMarkdown(
      reviewBase(p, {
        blocking: arr(res.blocking),
        advisory: arr(res.advisory),
        refuted: res.refuted,
        unverified: res.unverified,
      }),
      { prd: "00064", review: "1", date: "2026-07-13", head_sha: "abc1234" },
    ),
  );
  assert.ok(
    !review.includes("Verdict: converged"),
    `the review file must not claim convergence while the returned verdict is ${verdict}:\n${review.join("\n")}`,
  );
});

test("an over-cap blocker reaches the findings table as a rework-able line, keeping its own severity", () => {
  const p = pure();
  const critical = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "2",
    proof: "cmd reaches exec",
  });
  const high = finding({
    title: "path traversal in upload",
    severity: "HIGH",
    file: "src/upload.js",
    task: "3",
    proof: "filename is joined unchecked",
  });

  const res = p.applyVerification({
    toVerify: [],
    verdicts: [],
    overflow: [critical, high],
    passthrough: [],
  });
  assert.equal(res.unverified, 2);
  for (const f of arr(res.advisory)) {
    assert.equal(f.verified, "unverified", "the fixture models cap overflow, not refutation");
  }

  const out = render(p, { advisory: arr(res.advisory) });
  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));

  const criticalLine = parseable.find((l) => l.includes("rce via cmd param"));
  assert.ok(
    criticalLine,
    `an unverified CRITICAL must render as a parseable finding line, not as prose:\n${out}`,
  );
  assert.match(
    criticalLine,
    CONSOLIDATION_RE,
    `only this shape reaches the findings table and becomes a rework task: ${criticalLine}`,
  );
  assert.match(
    criticalLine,
    /^\[ALICE\] 🔴 /u,
    `an unverified CRITICAL keeps its own emoji: it must not be laundered into a lesser severity: ${criticalLine}`,
  );
  assert.match(
    criticalLine,
    /unverified/i,
    `the line must tell the reader it was never verified: ${criticalLine}`,
  );
  assert.ok(criticalLine.includes(" | Task: 2"), criticalLine);
  assert.equal(
    (criticalLine.match(/\|/g) || []).length,
    2,
    `only the File and Task separators: ${criticalLine}`,
  );

  const highLine = parseable.find((l) => l.includes("path traversal in upload"));
  assert.ok(highLine, `an unverified HIGH must render as a parseable finding line:\n${out}`);
  assert.match(highLine, CONSOLIDATION_RE, highLine);
  assert.match(highLine, /^\[ALICE\] 🟠 /u, `an unverified HIGH stays orange: ${highLine}`);
  assert.match(highLine, /unverified/i, highLine);
  assert.ok(highLine.includes(" | Task: 3"), highLine);
});

test("the agent output never reports a clean run while a finding went unverified", () => {
  const p = pure();
  const unproven = finding({
    title: "unauthenticated admin route",
    severity: "CRITICAL",
    file: "src/routes.js",
    task: "1",
    proof: "no auth middleware on /admin",
  });

  const res = p.applyVerification({
    toVerify: [],
    verdicts: [],
    overflow: [unproven],
    passthrough: [],
  });

  const out = render(p, { blocking: arr(res.blocking), advisory: arr(res.advisory) });
  assert.equal(arr(res.blocking).length, 0, "nothing was confirmed, because nothing was checked");
  assert.ok(
    !out.includes("✅ No issues found"),
    `"no issues found" is a lie while an unverified potential blocker exists:\n${out}`,
  );
  assert.ok(
    lines(out).some((l) => CONSOLIDATION_RE.test(l)),
    `the run must emit at least one parseable finding line:\n${out}`,
  );
});
