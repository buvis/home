// Tests for renderAgentOutput in review-fanout.workflow.js: finding lines,
// markers, sanitization (cell), the File cell, and injection safety.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/

import test from "node:test";
import assert from "node:assert/strict";
import { pure, finding, render, lines, fileCell, arr, EXPECTED_RUBRIC_IDS } from "./_harness.mjs";
test("a title carrying a pipe and a newline still renders exactly one parseable line", () => {
  const p = pure();
  const f = finding({
    title: "bad | thing\nsecond line of the title",
    severity: "CRITICAL",
    file: "src/x.js",
    task: "3",
    proof: "proven",
  });

  const out = render(p, { blocking: [f], statsLine: "stats: raw=1 unique=1" });
  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));
  assert.equal(
    parseable.length,
    1,
    "an injected newline must not split the finding into two lines",
  );

  const line = parseable[0];
  assert.match(line, /^\[ALICE\] 🔴 /, "emoji must follow '] ' for the legacy parser");
  assert.ok(line.includes(" | File:"), `missing File cell: ${line}`);
  assert.ok(line.includes(" | Task:"), `missing Task cell: ${line}`);
  assert.equal(
    (line.match(/\|/g) || []).length,
    2,
    `the injected pipe must be sanitized away, leaving only the File and Task separators: ${line}`,
  );
  assert.ok(line.includes("bad / thing second line of the title"), `title not sanitized: ${line}`);
});

test("every severity renders its own emoji, so a HIGH never masquerades as a CRITICAL", () => {
  const p = pure();
  assert.equal(p.SEVERITY_EMOJI.CRITICAL, "🔴");
  assert.equal(p.SEVERITY_EMOJI.HIGH, "🟠", "HIGH is orange, not red");
  assert.equal(p.SEVERITY_EMOJI.MEDIUM, "🟡");
  assert.equal(p.SEVERITY_EMOJI.LOW, "⚪", "LOW is white, not red");

  const high = finding({
    title: "path traversal in upload",
    severity: "HIGH",
    file: "src/upload.js",
    task: "2",
    proof: "filename is joined unchecked",
    verified: "confirmed",
  });
  const low = finding({ title: "stray log", severity: "LOW", file: "src/d.js", task: "5" });

  const out = render(p, { blocking: [high], advisory: [low] });
  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));

  const highLine = parseable.find((l) => l.includes("path traversal in upload"));
  assert.ok(highLine, `missing the HIGH finding line in:\n${out}`);
  assert.match(highLine, /^\[ALICE\] 🟠 /, `a HIGH must render 🟠, got: ${highLine}`);
  assert.ok(!highLine.includes("🔴"), `a HIGH must not render red: ${highLine}`);

  const lowLine = parseable.find((l) => l.includes("stray log"));
  assert.ok(lowLine, `missing the LOW finding line in:\n${out}`);
  assert.match(lowLine, /^\[ALICE\] ⚪ /, `a LOW must render ⚪, got: ${lowLine}`);
  assert.ok(!lowLine.includes("🔴"), `a LOW must not render red: ${lowLine}`);
});

test("a severity outside the vocabulary still renders a finding, never the string undefined", () => {
  const p = pure();
  const f = finding({
    title: "mystery severity from a rogue agent",
    severity: "BLOCKER", // not one of CRITICAL / HIGH / MEDIUM / LOW
    file: "src/a.js",
    task: "9",
    proof: "p",
  });
  assert.equal(p.SEVERITY_EMOJI.BLOCKER, undefined, "the fixture severity is deliberately unknown");

  const out = render(p, { blocking: [f] });
  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));
  const line = parseable.find((l) => l.includes("mystery severity from a rogue agent"));
  assert.ok(line, `an unknown severity must not silently drop the finding:\n${out}`);
  assert.ok(
    !line.includes("undefined"),
    `an unknown severity must fall back, not render the string "undefined": ${line}`,
  );
  assert.ok(!out.includes("undefined"), `nothing may render as the string "undefined":\n${out}`);
});

test("a finding with no task renders the general task fallback, never the string undefined", () => {
  const p = pure();
  const f = finding({
    title: "taskless finding",
    severity: "CRITICAL",
    file: "src/a.js",
    proof: "proven",
  });
  assert.equal(f.task, undefined, "the fixture deliberately carries no task");

  const out = render(p, { blocking: [f] });
  const line = lines(out).find((l) => l.startsWith("[ALICE]") && l.includes("taskless finding"));
  assert.ok(line, `missing the finding line in:\n${out}`);
  assert.ok(line.includes("| Task: general"), `a task-less finding falls back to general: ${line}`);
  assert.ok(!out.includes("undefined"), `nothing may render as the string "undefined":\n${out}`);
});

test("each finding line carries its own file in the File cell, not a shared placeholder", () => {
  const p = pure();
  // The consolidation script builds a rework task from the File cell. A line that
  // renders "N/A" for a finding that HAS a file sends the fixer to nothing: the
  // finding is reported, counted, blocks convergence, and cannot be acted on.
  const charge = finding({
    title: "unauthenticated refund path",
    severity: "CRITICAL",
    file: "src/payments/charge.js",
    task: "1",
    proof: "refund() is reachable without the auth middleware",
    verified: "confirmed",
  });
  const upload = finding({
    title: "path traversal in upload",
    severity: "HIGH",
    file: "src/upload/handler.js",
    task: "2",
    proof: "filename is joined unchecked",
    verified: "confirmed",
  });

  const out = render(p, { blocking: [charge, upload] });
  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));

  const chargeLine = parseable.find((l) => l.includes("unauthenticated refund path"));
  assert.ok(chargeLine, `missing the blocking finding line in:\n${out}`);
  assert.equal(
    fileCell(chargeLine),
    "src/payments/charge.js",
    `the File cell must carry the finding's own file: a rework task built from this line ` +
      `points at whatever the cell says, so a placeholder points at nothing: ${chargeLine}`,
  );

  const uploadLine = parseable.find((l) => l.includes("path traversal in upload"));
  assert.ok(uploadLine, `missing the second blocking finding line in:\n${out}`);
  assert.equal(
    fileCell(uploadLine),
    "src/upload/handler.js",
    `each finding keeps its OWN file: one constant cell for every finding is the same ` +
      `defect as N/A for every finding: ${uploadLine}`,
  );

  assert.notEqual(
    fileCell(chargeLine),
    fileCell(uploadLine),
    "two findings in two files must not render the same File cell",
  );
  assert.ok(
    !out.includes("| File: N/A |"),
    `no finding here lacks a file, so nothing may fall back to N/A:\n${out}`,
  );
});

test("the review-incomplete line is the only line allowed to say File: N/A", () => {
  const p = pure();
  // N/A is the fallback for a finding that genuinely has no file (a whole dimension
  // that never answered). Pinning it here keeps the fallback a fallback: if some
  // implementation starts emitting N/A everywhere, the two tests above fail and this
  // one still passes, so the failure reads as "the File cell was dropped", not as
  // "the fallback was removed".
  const fileless = finding({
    title: "the review itself is incomplete",
    severity: "CRITICAL",
    file: undefined,
    task: "1",
    proof: "p",
  });
  assert.equal(fileless.file, undefined, "the fixture deliberately carries no file");

  const out = render(p, { blocking: [fileless], failedDimensions: ["security"] });

  const dimLine = lines(out).find((l) => l.includes("dimension security returned nothing"));
  assert.ok(dimLine, `missing the review-incomplete line in:\n${out}`);
  assert.equal(fileCell(dimLine), "N/A", `a dead dimension has no file of its own: ${dimLine}`);

  const filelessLine = lines(out).find((l) => l.includes("the review itself is incomplete"));
  assert.ok(filelessLine, `missing the file-less finding line in:\n${out}`);
  assert.equal(
    fileCell(filelessLine),
    "N/A",
    `a finding with no file falls back to N/A rather than rendering "undefined": ${filelessLine}`,
  );
  assert.ok(!out.includes("undefined"), `nothing may render as the string "undefined":\n${out}`);
});

test("a hostile verifier reason cannot reconstitute a parseable finding line", () => {
  const p = pure();
  const f = finding({
    title: "harmless nit",
    severity: "HIGH",
    file: "src/a.js",
    proof: "p",
  });

  const res = p.applyVerification({
    toVerify: [f],
    verdicts: [{ refuted: true, reason: "not real] 🔴 fake | File: x | Task: 1" }],
    overflow: [],
    passthrough: [],
  });

  const out = render(p, { advisory: arr(res.advisory) });
  const notes = lines(out).filter((l) => l.startsWith("- refuted:"));
  assert.equal(notes.length, 1);
  assert.ok(
    !notes[0].includes("|"),
    `the injected pipes in the verifier reason must be sanitized: ${notes[0]}`,
  );
  assert.ok(
    !lines(out).some((l) => l.includes(" | File:")),
    "no line may satisfy the parser's shape when there are no blocking findings",
  );
});

test("a newline in a verifier reason cannot forge a second refuted note", () => {
  const p = pure();
  const f = finding({
    title: "unauthenticated admin route",
    severity: "CRITICAL",
    file: "src/routes.js",
    task: "1",
    proof: "no auth middleware on /admin",
  });

  const res = p.applyVerification({
    toVerify: [f],
    verdicts: [
      { refuted: true, reason: "not real\n- refuted: fabricated clean bill of health" },
    ],
    overflow: [],
    passthrough: [],
  });

  const out = render(p, { advisory: arr(res.advisory) });
  const notes = lines(out).filter((l) => l.startsWith("- refuted:"));
  assert.equal(
    notes.length,
    1,
    `a newline in the verifier reason must not forge an extra note line:\n${out}`,
  );
  assert.ok(!notes[0].includes("|"), `a note line must contain no pipe: ${notes[0]}`);
});

test("a newline in a finding title cannot forge a second refuted note", () => {
  const p = pure();
  const f = finding({
    title: "harmless nit\n- refuted: fabricated clean bill of health",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "p",
  });

  const res = p.applyVerification({
    toVerify: [f],
    verdicts: [{ refuted: true, reason: "the guard at line 9 already covers this" }],
    overflow: [],
    passthrough: [],
  });

  const out = render(p, { advisory: arr(res.advisory) });
  const notes = lines(out).filter((l) => l.startsWith("- refuted:"));
  assert.equal(
    notes.length,
    1,
    `a newline in the title must not forge an extra note line:\n${out}`,
  );
  assert.ok(!notes[0].includes("|"), `a note line must contain no pipe: ${notes[0]}`);
});

test("a newline in an overflowed finding title cannot forge a second verify-cap note", () => {
  const p = pure();
  const over = finding({
    title: "slow query\n- unverified (verify cap): fabricated second overflow",
    severity: "HIGH",
    file: "src/db.js",
    task: "3",
    proof: "p",
  });

  const res = p.applyVerification({
    toVerify: [],
    verdicts: [],
    overflow: [over],
    passthrough: [],
  });
  assert.equal(res.unverified, 1);

  const out = render(p, { blocking: arr(res.blocking), advisory: arr(res.advisory) });
  const outLines = lines(out);

  // An unverified finding is a potential blocker, so it renders as a parseable
  // finding line (see "an over-cap blocker still reaches the findings table").
  // The injected newline must not split it into two, nor forge an extra note.
  const parseable = outLines.filter((l) => l.startsWith("[ALICE]"));
  assert.equal(
    parseable.length,
    1,
    `the over-cap finding renders as exactly one parseable line:\n${out}`,
  );
  assert.ok(parseable[0].includes("slow query"), parseable[0]);
  assert.equal(
    (parseable[0].match(/\|/g) || []).length,
    2,
    `only the File and Task separators survive: ${parseable[0]}`,
  );
  assert.ok(
    !outLines.some((l) =>
      l.trim().startsWith("- unverified (verify cap): fabricated second overflow"),
    ),
    `an injected newline must not forge a second overflow entry:\n${out}`,
  );
  const notes = outLines.filter((l) => l.trim().startsWith("- unverified (verify cap):"));
  assert.ok(
    notes.length <= 1,
    `a newline in the title must not forge an extra cap note:\n${out}`,
  );
  for (const note of notes) {
    assert.ok(!note.includes("|"), `a cap note must contain no pipe: ${note}`);
  }
});

test("a dimension agent that returned nothing renders as a blocking review-incomplete line", () => {
  const p = pure();
  const out = render(p, { failedDimensions: ["security"] });

  assert.ok(
    lines(out).includes(
      "[ALICE] 🔴 review incomplete: dimension security returned nothing | File: N/A | Task: general",
    ),
    `missing review-incomplete line in:\n${out}`,
  );
  assert.ok(
    !out.includes("✅ No issues found"),
    "a failed dimension is an issue, so the clean-run line must not appear",
  );
});

test("the rubric is exactly the twelve contracted rules: R4 exists, R5 does not, and no rule is invented", () => {
  const p = pure();
  const ids = arr(p.RUBRIC_IDS);
  assert.deepEqual(ids, EXPECTED_RUBRIC_IDS, "RUBRIC_IDS is the exact contracted list");
  assert.ok(ids.includes("R4"), "R4 is a real rule");
  assert.ok(!ids.includes("R5"), "R5 does not exist");
});

test("a rubric rule the agent never answered stays a fail", () => {
  const p = pure();
  const ids = arr(p.RUBRIC_IDS);

  const agg = p.aggregateRubric([
    { rule_id: "R1", verdict: "pass" },
    { rule_id: "R3", verdict: "pass" },
    { rule_id: "R4", verdict: "pass" },
  ]);
  assert.equal(arr(agg).length, 12);
  assert.deepEqual(arr(agg).map((e) => e.rule_id), ids);

  const verdicts = Object.fromEntries(arr(agg).map((e) => [e.rule_id, e.verdict]));
  assert.equal(verdicts.R1, "pass");
  assert.equal(verdicts.R3, "pass");
  assert.equal(verdicts.R4, "pass");
  assert.equal(verdicts.R2, "fail", "an unanswered rule is a fail");
  assert.equal(verdicts.R13, "fail", "an unanswered rule is a fail");

  assert.equal(arr(p.aggregateRubric([])).filter((e) => e.verdict === "fail").length, 12);
  assert.equal(arr(p.aggregateRubric(null)).length, 12, "a dead rubric agent fails every rule");
  assert.equal(arr(p.aggregateRubric(null)).filter((e) => e.verdict === "fail").length, 12);

  const out = render(p, { rubric: agg });
  const rendered = lines(out);
  assert.ok(rendered.includes("R1: pass"));
  assert.ok(rendered.includes("R2: fail"));
  assert.ok(rendered.includes("R3: pass"));
  assert.ok(rendered.includes("R4: pass"));
  for (const id of ids) {
    assert.ok(
      rendered.some((l) => l === `${id}: pass` || l === `${id}: fail`),
      `missing rubric line for ${id}`,
    );
  }
  assert.ok(!out.includes("R5:"), "R5 must never be rendered");
  assert.ok(!out.includes("R42:"), "R42 is not a rule");
});

test("a clean review renders the single no-issues line, then the rubric and the stats", () => {
  const p = pure();
  const out = render(p, { statsLine: "stats: raw=0 unique=0 verified=0" });

  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));
  assert.deepEqual(parseable, ["[ALICE] ✅ No issues found"]);

  const rendered = lines(out);
  for (const id of arr(p.RUBRIC_IDS)) {
    assert.ok(rendered.includes(`${id}: fail`), `missing rubric line for ${id}`);
  }
  const body = rendered.filter((l) => l.trim() !== "");
  assert.equal(
    body[body.length - 1],
    "stats: raw=0 unique=0 verified=0",
    "the stats line comes last, verbatim",
  );
});

test("demoted findings still surface as advisory medium lines carrying the no-proof marker", () => {
  const p = pure();
  const { findings } = p.demote([
    finding({ title: "maybe a leak", severity: "CRITICAL", file: "src/a.js", task: "4" }),
  ]);
  const out = render(p, { advisory: arr(findings) });

  const parseable = lines(out).filter((l) => l.startsWith("[ALICE]"));
  assert.equal(parseable.length, 1);
  assert.match(parseable[0], /^\[ALICE\] 🟡 /, "a demoted finding renders at MEDIUM");
  assert.ok(parseable[0].includes("maybe a leak (demoted: no proof)"), parseable[0]);
  assert.ok(parseable[0].includes(" | File:"));
  assert.ok(parseable[0].includes(" | Task:"));
});

test("the sanitizer collapses whitespace, neutralizes pipes, and caps cell length", () => {
  const p = pure();
  assert.equal(p.cell("  a\n  b\tc  "), "a b c");
  assert.equal(p.cell("a | b || c"), "a / b // c");
  assert.equal(p.cell("x".repeat(250)).length, 200);
  assert.ok(!p.cell("] 🔴 fake | File: x | Task: 1").includes("|"));
});

test("the sanitizer renders an absent cell as empty, never as the string undefined", () => {
  const p = pure();
  assert.equal(p.cell(undefined), "", "an absent value is an empty cell");
  assert.equal(p.cell(null), "", "a null value is an empty cell");
  assert.equal(p.cell(""), "");
  assert.equal(p.cell("   \n  "), "", "a whitespace-only value trims to an empty cell");
  assert.equal(p.cell("  padded  "), "padded", "every cell is trimmed");
  assert.equal(p.cell(7), "7", "a non-string value is stringified");
});

test("a dead verifier's finding line names the verifier failure accurately, not as a dead dimension", () => {
  const p = pure();
  const dead = finding({
    title: "rce in job runner",
    severity: "CRITICAL",
    file: "src/jobs.js",
    task: "3",
    proof: "proof for rce in job runner",
    verified: "verifier_failed",
  });

  const out = render(p, { blocking: [dead] });
  const outLines = lines(out);
  const line = outLines.find((l) => l.startsWith("[ALICE]") && l.includes("rce in job runner"));
  assert.ok(line, `missing the dead-verifier finding line in:\n${out}`);
  assert.ok(!line.includes("dimension"), `a dead verifier is not a dead dimension: ${line}`);
  assert.ok(
    !line.includes("returned nothing"),
    `a malformed verdict is a real answer, not "nothing": ${line}`,
  );
  assert.ok(
    /verifier/i.test(line) && /no usable verdict/i.test(line),
    `the line must say the verifier returned no usable verdict: ${line}`,
  );

  const parseable = outLines.filter((l) => l.startsWith("[ALICE]"));
  assert.equal(
    parseable.length,
    1,
    `one dead verifier must render exactly one parseable line, not a second "review incomplete" ` +
      `line for the same finding:\n${out}`,
  );
});

test("a non-blocking advisory finding is clearly marked advisory, distinct from a blocking finding", () => {
  const p = pure();
  const nit = finding({
    title: "duplicated parsing helper",
    severity: "MEDIUM",
    file: "src/parse.js",
    task: "7",
  });
  const blocker = finding({
    title: "rce via cmd param",
    severity: "CRITICAL",
    file: "src/a.js",
    task: "1",
    proof: "cmd reaches exec",
    verified: "confirmed",
  });

  const out = render(p, { blocking: [blocker], advisory: [nit] });
  const outLines = lines(out);
  const advisoryLine = outLines.find(
    (l) => l.startsWith("[ALICE]") && l.includes("duplicated parsing helper"),
  );
  const blockingLine = outLines.find((l) => l.startsWith("[ALICE]") && l.includes("rce via cmd param"));

  assert.ok(advisoryLine, `missing the advisory line:\n${out}`);
  assert.ok(blockingLine, `missing the blocking line:\n${out}`);
  assert.ok(
    /advisory/i.test(advisoryLine),
    `an advisory finding must self-identify as advisory, so a reader -- human or the ` +
      `consolidation script, which parses every parseable line -- cannot mistake it for a ` +
      `blocking finding: ${advisoryLine}`,
  );
  assert.ok(
    !/advisory/i.test(blockingLine),
    `a blocking finding must not carry the advisory marker: ${blockingLine}`,
  );
});
