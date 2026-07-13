// Tests for finding demotion (demote) and duplicate collapsing (dedupe,
// dedupKey, norm) in review-fanout.workflow.js.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/*.test.mjs

import test from "node:test";
import assert from "node:assert/strict";
import { pure, finding, arr, render } from "./_harness.mjs";
test("distinct titles sharing a file and evidence collapse to one defect", () => {
  const p = pure();
  // Two reviewers hit the same hunk and wrote it up under completely different
  // titles. The PRD keys dedup on the normalized EVIDENCE snippet, not on the
  // free-text title, so this is one defect, not two.
  const evidence = "for (let i = 0; i <= items.length; i++) { send(items[i]); }";
  const a = finding({
    title: "off-by-one walks past the end of items",
    file: "src/send.js",
    evidence,
    severity: "HIGH",
    proof: "the loop uses <= against items.length, so the final iteration reads items[items.length], which is undefined",
    dimensions: ["correctness"],
  });
  const b = finding({
    title: "unvalidated input reaches send()",
    file: "src/send.js",
    evidence,
    severity: "CRITICAL",
    proof: "send() receives an out-of-bounds element with no guard against it",
    dimensions: ["security"],
  });

  assert.equal(
    p.dedupKey(a),
    p.dedupKey(b),
    "the title is free text two agents word differently; it must not be part of the dedup key",
  );

  const { unique, raw } = p.dedupe([a, b]);
  assert.equal(raw, 2);
  assert.equal(
    arr(unique).length,
    1,
    "one quoted hunk of evidence in one file is one defect, no matter how many different titles reviewers give it",
  );
  const survivor = arr(unique)[0];
  assert.equal(survivor.severity, "CRITICAL", "the strictest severity survives the merge");
  assert.deepEqual(
    arr(survivor.dimensions).sort(),
    ["correctness", "security"],
    "both reporting dimensions survive the merge",
  );
});

test("the same title and evidence in two different files are two defects, not one", () => {
  const p = pure();
  const evidence = "const row = rows[idx + 1];";
  const a = finding({
    title: "index runs one past the end",
    file: "src/reader.js",
    evidence,
    severity: "HIGH",
    proof: "idx is already the last index when the loop exits",
    dimensions: ["correctness"],
  });
  const b = finding({
    title: "index runs one past the end",
    file: "src/writer.js",
    evidence,
    severity: "HIGH",
    proof: "idx is already the last index when the loop exits",
    dimensions: ["correctness"],
  });

  assert.notEqual(p.dedupKey(a), p.dedupKey(b), "the file must be part of the dedup key");

  const { unique, raw } = p.dedupe([a, b]);
  assert.equal(raw, 2);
  assert.equal(
    arr(unique).length,
    2,
    "the same defect text in two files is two fixes, so neither may be erased",
  );
  assert.deepEqual(
    arr(unique).map((f) => f.file).sort(),
    ["src/reader.js", "src/writer.js"],
  );
});

test("the same title in one file but on different evidence stays two findings", () => {
  const p = pure();
  const a = finding({
    title: "unvalidated user input",
    file: "src/api.js",
    evidence: "handler(req.body.name)",
    severity: "HIGH",
    dimensions: ["security"],
  });
  const b = finding({
    title: "unvalidated user input",
    file: "src/api.js",
    evidence: "handler(req.query.redirect)",
    severity: "HIGH",
    dimensions: ["security"],
  });

  assert.notEqual(p.dedupKey(a), p.dedupKey(b), "the evidence must be part of the dedup key");

  const { unique, raw } = p.dedupe([a, b]);
  assert.equal(raw, 2);
  assert.equal(
    arr(unique).length,
    2,
    "two separate hunks in one file are two defects",
  );
  assert.deepEqual(
    arr(unique).map((f) => f.evidence).sort(),
    ["handler(req.body.name)", "handler(req.query.redirect)"],
  );
});

test("two reviewers wording the same defect differently report one finding, not two", () => {
  const p = pure();
  // Same defect, same file, same hunk — but two agents wrote it up in their own
  // words, punctuation and case. The titles below are genuinely different
  // prose (not case/punctuation variants of each other), so this only passes
  // if the dedup key does not include the title at all — normalizing title
  // punctuation would not be enough to collide these two.
  const alice = finding({
    title: "SQL Injection in user_lookup()",
    severity: "HIGH",
    file: "src/db.js",
    evidence: "db.query( q )",
    proof: "q is interpolated from req.params",
    dimensions: ["security"],
  });
  const bob = finding({
    title: "the id parameter is concatenated straight into the query string",
    severity: "CRITICAL",
    file: "src/db.js",
    evidence: "db.query(q)",
    proof: "q flows unescaped from req.params into the query built at line 42",
    dimensions: ["correctness"],
  });

  assert.notEqual(
    p.norm(alice.title),
    p.norm(bob.title),
    "the fixture titles must be genuinely different prose, not the same words after normalization",
  );
  assert.equal(
    p.dedupKey(alice),
    p.dedupKey(bob),
    "the same evidence in the same file is one defect no matter how differently it is titled",
  );

  const { unique, raw } = p.dedupe([alice, bob]);
  assert.equal(raw, 2);
  assert.equal(
    arr(unique).length,
    1,
    "the same defect reported by two agents in different words is one finding, not two",
  );
  const survivor = arr(unique)[0];
  assert.equal(survivor.severity, "CRITICAL", "the strictest severity survives the fuzzy merge");
  assert.equal(survivor.proof, bob.proof, "the longest proof survives the fuzzy merge");
  assert.deepEqual(
    arr(survivor.dimensions).sort(),
    ["correctness", "security"],
    "both reporting dimensions survive the fuzzy merge",
  );
});

test("the evidence-keyed merge still keeps the strictest severity, longest proof and longest fix regardless of arrival order, even when the titles differ", () => {
  const p = pure();
  const evidence = "db.query(`SELECT * FROM u WHERE id = ${id}`)";
  // The two titles are unrelated prose on purpose: the merge collapses on file +
  // evidence alone, so this proves title has no bearing on the collapse or on
  // which fields survive it.
  const strictButThin = finding({
    title: "SQL injection in user lookup",
    severity: "CRITICAL",
    file: "src/db.js",
    evidence,
    proof: "id is unescaped",
    fix: "escape it",
    dimensions: ["security"],
  });
  const laxButDetailed = finding({
    title: "raw id interpolated into the query string",
    severity: "HIGH",
    file: "src/db.js",
    evidence,
    proof: "id flows unescaped from req.params into the template literal at line 42",
    fix: "use a parameterized query: db.query('SELECT * FROM u WHERE id = ?', [id])",
    dimensions: ["correctness"],
  });

  assert.equal(
    p.dedupKey(strictButThin),
    p.dedupKey(laxButDetailed),
    "the same defect in the same file on the same evidence is one key, even with unrelated titles",
  );

  for (const [order, input] of [
    ["strict first", [strictButThin, laxButDetailed]],
    ["strict last", [laxButDetailed, strictButThin]],
  ]) {
    const { unique, raw } = p.dedupe(input);
    assert.equal(raw, 2, order);
    assert.equal(arr(unique).length, 1, `${order}: the duplicate collapses`);

    const survivor = arr(unique)[0];
    assert.equal(survivor.severity, "CRITICAL", `${order}: the strictest severity survives`);
    assert.equal(
      survivor.proof,
      laxButDetailed.proof,
      `${order}: the longest proof survives, even when it arrives on the laxer report`,
    );
    assert.equal(
      survivor.fix,
      laxButDetailed.fix,
      `${order}: the longest fix survives, even when it arrives on the laxer report`,
    );
    assert.deepEqual(
      arr(survivor.dimensions).sort(),
      ["correctness", "security"],
      `${order}: both reporting dimensions survive`,
    );
  }
});

test("the dedup key delimits its parts, so shifting the file/evidence boundary is a different key", () => {
  const p = pure();
  // Raw concatenation ("b" + "cd" === "bc" + "d") collides here.
  assert.notEqual(
    p.dedupKey({ title: "a", file: "b", evidence: "cd" }),
    p.dedupKey({ title: "a", file: "bc", evidence: "d" }),
    "the file/evidence boundary must be delimited in the key",
  );
});

test("the severity rank is total, so MEDIUM outranks LOW no matter which arrived first", () => {
  const p = pure();
  const same = {
    title: "duplicated parsing helper",
    file: "src/parse.js",
    evidence: "const parsed = parse(x);",
    dimensions: ["maintainability"],
  };
  const low = finding({ ...same, severity: "LOW" });
  const medium = finding({ ...same, severity: "MEDIUM" });
  const high = finding({ ...same, severity: "HIGH", proof: "the helper diverges on empty input" });

  assert.equal(p.dedupKey(low), p.dedupKey(medium), "the fixtures are the same defect");

  const lowFirst = p.dedupe([low, medium]);
  assert.equal(arr(lowFirst.unique).length, 1, "the duplicate collapses");
  assert.equal(
    arr(lowFirst.unique)[0].severity,
    "MEDIUM",
    "MEDIUM outranks LOW: arrival order must not decide the survivor's severity",
  );

  const mediumFirst = p.dedupe([medium, low]);
  assert.equal(arr(mediumFirst.unique).length, 1);
  assert.equal(arr(mediumFirst.unique)[0].severity, "MEDIUM", "and the reverse order agrees");

  assert.equal(
    arr(p.dedupe([medium, high]).unique)[0].severity,
    "HIGH",
    "HIGH outranks MEDIUM",
  );
  assert.equal(
    arr(p.dedupe([high, medium]).unique)[0].severity,
    "HIGH",
    "HIGH outranks MEDIUM in either arrival order",
  );
});

test("a proof-less CRITICAL is demoted to MEDIUM and is never verified", () => {
  const p = pure();
  const noProof = finding({ title: "rce in handler", severity: "CRITICAL", file: "src/a.js" });
  const blankProof = finding({
    title: "auth bypass",
    severity: "HIGH",
    file: "src/b.js",
    proof: "   \n  ",
  });

  const { findings, demoted } = p.demote([noProof, blankProof]);
  assert.equal(demoted, 2);
  for (const f of arr(findings)) {
    assert.equal(f.severity, "MEDIUM");
    assert.equal(f.demoted, true);
  }

  const { toVerify, overflow } = p.selectForVerify(arr(findings));
  assert.equal(
    arr(toVerify).length,
    0,
    "a demoted finding is no longer a blocker, so it is not verified",
  );
  assert.equal(arr(overflow).length, 0);
});

test("a CRITICAL backed by a real proof keeps its severity, and MEDIUM/LOW are never demoted", () => {
  const p = pure();
  const proven = finding({
    title: "rce in handler",
    severity: "CRITICAL",
    file: "src/a.js",
    proof: "req.body.cmd reaches child_process.exec at line 17 with no validation",
  });
  const medium = finding({ title: "naming nit", severity: "MEDIUM", file: "src/c.js" });
  const low = finding({ title: "stray log", severity: "LOW", file: "src/d.js" });

  const { findings, demoted } = p.demote([proven, medium, low]);
  assert.equal(demoted, 0);
  const out = arr(findings);
  assert.equal(out[0].severity, "CRITICAL");
  assert.ok(!out[0].demoted);
  assert.equal(out[1].severity, "MEDIUM");
  assert.ok(!out[1].demoted);
  assert.equal(out[2].severity, "LOW");
  assert.ok(!out[2].demoted);
});

test("norm lowercases, collapses every run of non-alphanumerics to one space, and trims", () => {
  const p = pure();
  assert.equal(p.norm("  Hello,   World!! 42__x  "), "hello world 42 x");
  assert.equal(p.norm("SQL Injection in user_lookup()"), "sql injection in user lookup");
  assert.equal(p.norm("a|b"), "a b", "a pipe is just another separator");
  assert.equal(p.norm("a\nb\tc"), "a b c", "newlines and tabs collapse like any separator");
  assert.equal(p.norm("---"), "", "a value with no alphanumerics normalizes to nothing");
  assert.equal(p.norm(""), "");
  assert.equal(
    p.norm(p.norm("  Hello,   World!! 42__x  ")),
    "hello world 42 x",
    "normalizing twice changes nothing",
  );
});

test("a finding proven by one dimension is not marked demoted merely because a duplicate report lacked proof", () => {
  const p = pure();
  const evidence = "child_process.exec(cmd)";
  const noProofReport = finding({
    title: "rce in handler",
    severity: "CRITICAL",
    file: "src/a.js",
    evidence,
    dimensions: ["security"],
  });
  const provenReport = finding({
    title: "unvalidated cmd reaches exec",
    severity: "MEDIUM",
    file: "src/a.js",
    evidence,
    proof: "cmd flows from req.body straight into exec with no validation",
    dimensions: ["correctness"],
  });

  const { findings: demotedFindings, demoted } = p.demote([noProofReport]);
  assert.equal(demoted, 1);
  const demotedFinding = arr(demotedFindings)[0];
  assert.equal(demotedFinding.severity, "MEDIUM");
  assert.equal(demotedFinding.demoted, true);

  for (const [order, input] of [
    ["demoted first", [demotedFinding, provenReport]],
    ["demoted last", [provenReport, demotedFinding]],
  ]) {
    const { unique } = p.dedupe(input);
    assert.equal(arr(unique).length, 1, `${order}: same file+evidence collapses to one finding`);
    const survivor = arr(unique)[0];
    assert.ok(
      !survivor.demoted,
      `${order}: a dimension proved this defect with real proof, so the merged finding must not ` +
        `render as demoted: no proof, got demoted=${survivor.demoted}`,
    );
  }
});

test("two distinct fileless findings with no evidence stay two findings", () => {
  const p = pure();
  // The engine supports the architectural / fileless finding shape: no file to
  // point at (file: "N/A") and no hunk to quote (evidence: ""). Nothing about
  // those two placeholder values says "same defect" — they are the ABSENCE of a
  // locator, not a locator two reviewers happened to share. Two such findings
  // are two separate blockers, and collapsing them silently deletes one HIGH
  // (its title and its proof) from the results and from the verdict.
  const rollback = finding({
    title: "no rollback on partial write",
    severity: "HIGH",
    file: "N/A",
    evidence: "",
    proof: "a crash between the two writes leaves the index pointing at a half-written record, and nothing unwinds it",
    dimensions: ["correctness"],
  });
  const coverage = finding({
    title: "missing integration test",
    severity: "HIGH",
    file: "N/A",
    evidence: "",
    proof: "no test drives the writer and the index together, so this pairing regresses unnoticed",
    dimensions: ["testing"],
  });

  assert.notEqual(
    p.dedupKey(rollback),
    p.dedupKey(coverage),
    "a blank evidence and a placeholder file are not a shared locator: two different defects " +
      "must not share one key just because neither could name a file or quote a hunk",
  );

  const { unique, raw } = p.dedupe([rollback, coverage]);
  assert.equal(raw, 2);
  assert.equal(
    arr(unique).length,
    2,
    "both fileless findings survive: a dropped finding is a dropped blocker",
  );
  assert.deepEqual(
    arr(unique).map((f) => f.title).sort(),
    ["missing integration test", "no rollback on partial write"],
    "neither title is erased by the other",
  );
  assert.deepEqual(
    arr(unique).map((f) => f.proof).sort(),
    [rollback.proof, coverage.proof].sort(),
    "each finding keeps its own proof; the merge must not hand one finding's proof to the other",
  );
});

test("a merged finding holding a real proof is never stamped demoted, even when a proof-less report outranks it", () => {
  const p = pure();
  // Rank-crossing merge: the proof-carrying report is the LAXER one (LOW), and
  // the report that outranks it (a HIGH that demote() already knocked down to a
  // proof-less MEDIUM) carries demoted: true. The survivor takes the stricter
  // severity from the demoted copy but the proof from the laxer one — so it ends
  // up holding a real proof, and must not render "(demoted: no proof)" while
  // holding it. The demoted flag belongs to the RECORD that survives, not to
  // whichever copy won the severity rank.
  const evidence = "child_process.exec(cmd)";
  const unprovable = finding({
    title: "rce in handler",
    severity: "HIGH",
    file: "src/a.js",
    evidence,
    dimensions: ["security"],
  });
  const provenLow = finding({
    title: "unvalidated cmd reaches exec",
    severity: "LOW",
    file: "src/a.js",
    evidence,
    proof: "cmd flows from req.body straight into exec with no validation",
    dimensions: ["correctness"],
  });

  const { findings: demotedFindings, demoted } = p.demote([unprovable]);
  assert.equal(demoted, 1);
  const demotedFinding = arr(demotedFindings)[0];
  assert.equal(demotedFinding.severity, "MEDIUM", "the proof-less HIGH lands at MEDIUM");
  assert.equal(demotedFinding.demoted, true);

  for (const [order, input] of [
    ["proven first", [provenLow, demotedFinding]],
    ["proven last", [demotedFinding, provenLow]],
  ]) {
    const { unique } = p.dedupe(input);
    assert.equal(arr(unique).length, 1, `${order}: same file+evidence collapses to one finding`);
    const survivor = arr(unique)[0];

    assert.equal(
      survivor.severity,
      "MEDIUM",
      `${order}: MEDIUM outranks LOW, so the demoted copy decides the severity`,
    );
    assert.equal(
      survivor.proof,
      provenLow.proof,
      `${order}: the only real proof on either copy survives the merge`,
    );
    assert.ok(
      !survivor.demoted,
      `${order}: this record carries a proof, so it must not be flagged as having none — ` +
        `winning the severity rank must not re-stamp demoted onto a proven record, ` +
        `got demoted=${survivor.demoted}`,
    );
  }
});

test("dedupKey is a pure function of the finding: equal findings always yield equal keys", () => {
  const p = pure();
  // Dedup is a Map lookup, so the key must depend on the finding's CONTENT and
  // nothing else. A key that carries hidden state (a counter, a random suffix, an
  // identity map) makes the collapse nondeterministic: the same two reports merge
  // or not depending on how many findings happened to arrive before them.
  const located = finding({
    title: "off-by-one walks past the end of items",
    severity: "HIGH",
    file: "src/send.js",
    evidence: "for (let i = 0; i <= items.length; i++) { send(items[i]); }",
    proof: "the final iteration reads items[items.length], which is undefined",
    dimensions: ["correctness"],
  });
  // The fileless shape is where a stateful key hides best: blank evidence is the
  // one input for which "just make it unique" looks like a defensible answer.
  const fileless = finding({
    title: "no rollback on partial write",
    severity: "HIGH",
    file: "N/A",
    evidence: "",
    proof: "a crash between the two writes leaves a half-written record and nothing unwinds it",
    dimensions: ["correctness"],
  });

  for (const [what, f] of [
    ["a located finding", located],
    ["a fileless finding with blank evidence", fileless],
  ]) {
    assert.equal(
      p.dedupKey(f),
      p.dedupKey(f),
      `${what}: keying the very same object twice must give the same key — a key that changes ` +
        `between calls makes dedup depend on call order, not on the findings`,
    );
    // A second object with the same fields is what two reviewers actually produce:
    // separate JSON, separate objects, one defect. Object identity is not content,
    // so an identity-keyed cache is just as broken as a counter.
    assert.equal(
      p.dedupKey({ ...f }),
      p.dedupKey(f),
      `${what}: two separate objects carrying the same fields are the same defect, so they ` +
        `must key the same — the key may read the finding's fields and nothing else`,
    );
  }
});

test("two reviewers filing the same fileless defect report one finding and union their dimensions", () => {
  const p = pure();
  // The other half of the fileless contract. Distinct fileless findings stay
  // distinct (see the test above), but that must NOT be bought by handing every
  // blank-evidence finding a key of its own: two dimensions naming the SAME
  // architectural defect still have to collapse, or the consensus barrier is off
  // for every finding that cannot point at a line of code. With no file and no
  // hunk to key on, the title is the only locator left.
  const title = "no rollback on partial write";
  const security = finding({
    title,
    severity: "HIGH",
    file: "N/A",
    evidence: "",
    proof: "a crash between the two writes leaves a half-written record",
    dimensions: ["security"],
  });
  const correctness = finding({
    title,
    severity: "CRITICAL",
    file: "N/A",
    evidence: "",
    proof: "a crash between the two writes leaves the index pointing at a half-written record, and nothing unwinds it",
    dimensions: ["correctness"],
  });

  assert.equal(
    p.dedupKey(security),
    p.dedupKey(correctness),
    "one defect named the same way by two reviewers is one key, even with no file and no evidence " +
      "to key on: blank evidence must fall back to a locator, not disable dedup",
  );

  const { unique, raw } = p.dedupe([security, correctness]);
  assert.equal(raw, 2);
  assert.equal(
    arr(unique).length,
    1,
    "the same fileless defect found by two dimensions is one finding, not two",
  );
  const survivor = arr(unique)[0];
  assert.deepEqual(
    arr(survivor.dimensions).sort(),
    ["correctness", "security"],
    "both dimensions found it, so both must show on the merged finding — this union is what the " +
      "consensus barrier counts",
  );
  assert.equal(survivor.severity, "CRITICAL", "the strictest severity survives the fileless merge");
  assert.equal(survivor.proof, correctness.proof, "the longest proof survives the fileless merge");
});

test("a merged finding with no proof on either copy stays demoted, and still says so on its rendered line", () => {
  const p = pure();
  // The mirror of the rank-crossing test above. There the survivor ENDED UP with a
  // real proof, so demoted had to come off. Here neither reviewer could prove the
  // CRITICAL, demote() knocked both down to MEDIUM, and the merged record still
  // carries no proof — so the flag must stay ON. Erasing it on merge turns a
  // dropped CRITICAL into a bare advisory line: the reader is never told that a
  // CRITICAL was filed and thrown out for lack of evidence.
  const evidence = "child_process.exec(cmd)";
  const alice = finding({
    title: "rce in handler",
    severity: "CRITICAL",
    file: "src/a.js",
    evidence,
    dimensions: ["security"],
  });
  const bob = finding({
    title: "unvalidated cmd reaches exec",
    severity: "CRITICAL",
    file: "src/a.js",
    evidence,
    proof: "   \n  ",
    dimensions: ["correctness"],
  });

  const { findings: demotedFindings, demoted } = p.demote([alice, bob]);
  assert.equal(demoted, 2, "neither CRITICAL carries a proof, so both are demoted");
  const [a, b] = arr(demotedFindings);
  assert.equal(a.demoted, true);
  assert.equal(b.demoted, true);

  for (const [order, input] of [
    ["alice first", [a, b]],
    ["bob first", [b, a]],
  ]) {
    const { unique } = p.dedupe(input);
    assert.equal(arr(unique).length, 1, `${order}: same file+evidence collapses to one finding`);
    const survivor = arr(unique)[0];

    assert.equal(survivor.severity, "MEDIUM", `${order}: the demoted severity survives the merge`);
    assert.equal(
      p.norm(survivor.proof),
      "",
      `${order}: the fixture is only meaningful while the merged record really has no proof`,
    );
    assert.equal(
      survivor.demoted,
      true,
      `${order}: merging two unprovable copies does not conjure a proof, so the record still has ` +
        `none and must still be flagged as demoted, got demoted=${survivor.demoted}`,
    );

    const out = render(p, { advisory: [survivor] });
    assert.ok(
      out.includes("(demoted: no proof)"),
      `${order}: the rendered line must tell the reader a CRITICAL was dropped for lack of proof, ` +
        `otherwise it reads as an ordinary advisory:\n${out}`,
    );
  }
});
