export const meta = {
  name: 'review-fanout',
  description: 'Consensus review fan-out: dimensions in parallel, dedup, adversarial verify',
  whenToUse: 'Use when a multi-dimension consensus review of a diff or PRD implementation should run as one orchestrated fan-out. Triggers on "review fanout", "fan out the review", "consensus review workflow".',
  phases: [
    { title: 'Review', detail: 'dimension agents in parallel' },
    { title: 'Verify', detail: 'adversarial verification of CRITICAL/HIGH findings' },
  ],
}

// ---- pure region (start) ----

const MAX_DIFF_BYTES = 400000;
const VERIFY_CAP = 12;
const CELL_MAX = 200;

const RUBRIC_IDS = ["R1", "R2", "R3", "R4", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "R13"];

const SEVERITY_EMOJI = { CRITICAL: "🔴", HIGH: "🟠", MEDIUM: "🟡", LOW: "⚪" };
const SEVERITY_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

// Matched against camel-split, lowercased text (see securityish), so `authToken`
// hits both terms while `execute` and `hashmap` hit none. The trailing `s?`
// admits plurals (`secrets.yml`). The auth-adjacent terms (authenticat, authoriz,
// permission, login, forbidden, acl) match as open-ended stems on the right, on
// purpose: a renamed guard (isAuthenticated, hasPermission, login_required) must
// still arm even though it never contains the bare word `auth`.
const SECURITY_RE =
  /(?<![a-z0-9])(?:(?:exec|eval|auth|token|password|secret|sql|crypto|hash|credential|session|cookie|csrf|xss|jwt|sanitize|injection|privilege)s?(?![a-z0-9])|authenticat|authoriz|permission|login|forbidden|acl)/;

/** One sanitized table cell: no pipes, no newlines, trimmed, length-capped. */
function cell(value) {
  if (value === undefined || value === null) return "";
  return String(value)
    .replace(/\|/g, "/")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, CELL_MAX);
}

/** Fuzzy-match form: lowercase, every run of non-alphanumerics becomes one space. */
function norm(value) {
  if (value === undefined || value === null) return "";
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Two agents quoting the same evidence in the same file collide here, no matter the title.
 *  A blank evidence is the ABSENCE of a locator, not one every fileless finding shares, so it
 *  falls back to the title — the only locator such a finding has left. */
function dedupKey(f) {
  const evidence = norm(f.evidence);
  if (evidence === "") return [norm(f.file), "title", norm(f.title)].join("|");
  return [norm(f.file), "evidence", evidence].join("|");
}

const rank = (severity) => (severity in SEVERITY_RANK ? SEVERITY_RANK[severity] : 4);
const textLen = (s) => (typeof s === "string" ? s.trim().length : 0);

/** UTF-8 byte count in pure ECMAScript — the workflow sandbox guarantees only
 *  language built-ins (no Buffer, no TextEncoder). for..of walks code points;
 *  a lone surrogate counts 3, matching TextEncoder's U+FFFD replacement. */
function utf8ByteLength(s) {
  let bytes = 0;
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    bytes += cp <= 0x7f ? 1 : cp <= 0x7ff ? 2 : cp <= 0xffff ? 3 : 4;
  }
  return bytes;
}

/** The tool hands `args` through as a JSON string when the caller stringified it. */
function coerceArgs(a) {
  if (typeof a !== "string") return a;
  try {
    return JSON.parse(a);
  } catch {
    throw new Error("INVALID_ARGS: args arrived as a string that is not JSON");
  }
}

function validateArgs(a) {
  const bad = (why) => {
    throw new Error(`INVALID_ARGS: ${why}`);
  };
  if (a === null || typeof a !== "object") bad("args must be an object");
  if (typeof a.diff !== "string" || a.diff.trim() === "") bad("diff is required and must be a non-empty unified diff");
  if (utf8ByteLength(a.diff) > MAX_DIFF_BYTES) bad(`diff is longer than MAX_DIFF_BYTES (${MAX_DIFF_BYTES}); the caller must truncate it`);
  if (typeof a.rubric_text !== "string" || a.rubric_text.trim() === "") bad("rubric_text is required");
  if (typeof a.diff_bytes !== "number") bad("diff_bytes is required");
  if (!Number.isFinite(a.diff_bytes) || a.diff_bytes < 0) bad("diff_bytes must be a finite non-negative number");
  if (a.diff_bytes > MAX_DIFF_BYTES && !a.diff_path) bad("diff_bytes is over MAX_DIFF_BYTES but no diff_path was supplied");
  // changed_files is optional, but a STRING silently iterates characters in
  // securityTriggered's `for (const path of changedFiles)` — every char fails
  // securityish(), so the path-based security signal disappears with no error.
  // Reject a non-array up front rather than under-arm the security dimension.
  if (a.changed_files != null && !Array.isArray(a.changed_files))
    bad("changed_files must be an array of paths (a string iterates characters and silently under-arms the security dimension)");
}

/** `diff_bytes` is a real byte count (from `wc -c`); `.length` counts UTF-16 code
 *  units, so a non-ASCII diff needs the real byte count to avoid a false positive. */
function isTruncated(diffBytes, diffText) {
  return diffBytes > utf8ByteLength(diffText);
}

/** Split camelCase so `authToken` yields both words, then lowercase. */
function securityish(text) {
  return SECURITY_RE.test(
    String(text)
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .toLowerCase(),
  );
}

/** Security arms on what the diff ADDED or REMOVED, or on a security-ish changed path: a
 *  guard disappearing is at least as strong a signal as one appearing. A real file header
 *  (`--- a/path` / `+++ b/path`) only ever shows up as an adjacent pair; a removed content
 *  line that merely starts with the same `--` prefix (a dropped flag, a SQL comment) has no
 *  such partner, so it is scanned like any other removed line instead of being skipped. */
function securityTriggered(diff, changedFiles) {
  for (const path of changedFiles || []) {
    if (securityish(path)) return true;
  }
  const lines = String(diff || "").split("\n");
  const isDashHeader = (l) => typeof l === "string" && /^---(?:\s|$)/.test(l);
  const isPlusHeader = (l) => typeof l === "string" && /^\+\+\+(?:\s|$)/.test(l);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isHeader =
      (isDashHeader(line) && isPlusHeader(lines[i + 1])) ||
      (isPlusHeader(line) && isDashHeader(lines[i - 1]));
    if (isHeader) continue;
    if (line.startsWith("+") && securityish(line)) return true;
    if (line.startsWith("-") && securityish(line)) return true;
  }
  return false;
}

/** A CRITICAL/HIGH nobody can prove is a MEDIUM: it never blocks and never gets verified. */
function demote(findings) {
  let demoted = 0;
  const out = findings.map((f) => {
    const blocks = f.severity === "CRITICAL" || f.severity === "HIGH";
    if (!blocks || textLen(f.proof) > 0) return f;
    demoted += 1;
    return { ...f, severity: "MEDIUM", demoted: true };
  });
  return { findings: out, demoted };
}

/** Merge duplicates: strictest severity, longest proof, longest fix, union of dimensions. */
function dedupe(findings) {
  const byKey = new Map();
  for (const f of findings) {
    const key = dedupKey(f);
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, { ...f, dimensions: [...(f.dimensions || [])] });
      continue;
    }
    if (rank(f.severity) < rank(prev.severity)) prev.severity = f.severity;
    if (textLen(f.proof) > textLen(prev.proof)) prev.proof = f.proof;
    if (textLen(f.fix) > textLen(prev.fix)) prev.fix = f.fix;
    // The flag belongs to the surviving RECORD, not to whichever copy won the severity rank:
    // a demotion sticks only while the merged record still has no proof to show.
    prev.demoted = (prev.demoted || f.demoted) && textLen(prev.proof) === 0;
    for (const d of f.dimensions || []) {
      if (!prev.dimensions.includes(d)) prev.dimensions.push(d);
    }
  }
  return { unique: [...byKey.values()], raw: findings.length };
}

/** Spend the verify budget strictest-first, never in arrival order. */
function selectForVerify(findings) {
  const blockers = findings.filter((f) => f.severity === "CRITICAL" || f.severity === "HIGH");
  const ordered = blockers.slice().sort((a, b) => rank(a.severity) - rank(b.severity));
  return { toVerify: ordered.slice(0, VERIFY_CAP), overflow: ordered.slice(VERIFY_CAP) };
}

/** Only a literal `refuted: true` disarms a finding. Anything else is a dead verifier. */
function applyVerification({ toVerify, verdicts, overflow, passthrough }) {
  const blocking = [];
  const advisory = [];
  const verifierFailures = [];
  let confirmed = 0;
  let refuted = 0;

  toVerify.forEach((f, i) => {
    const v = verdicts[i];
    const flag = v && typeof v === "object" ? v.refuted : undefined;
    if (flag === true) {
      refuted += 1;
      advisory.push({ ...f, verified: "refuted", refutation: v.reason });
    } else if (flag === false) {
      confirmed += 1;
      blocking.push({ ...f, verified: "confirmed" });
    } else {
      verifierFailures.push(f.title);
      blocking.push({ ...f, verified: "verifier_failed" });
    }
  });

  for (const f of overflow) advisory.push({ ...f, verified: "unverified" });
  for (const f of passthrough) advisory.push({ ...f });

  return { blocking, advisory, confirmed, refuted, unverified: overflow.length, verifierFailures };
}

/** Every contracted rule gets a verdict; an unanswered rule is a fail. */
function aggregateRubric(verdicts) {
  const byId = new Map();
  for (const v of verdicts || []) {
    if (v && RUBRIC_IDS.includes(v.rule_id)) byId.set(v.rule_id, v);
  }
  return RUBRIC_IDS.map((id) => {
    const v = byId.get(id);
    return {
      rule_id: id,
      verdict: v && v.verdict === "pass" ? "pass" : "fail",
      note: v ? v.note : undefined,
    };
  });
}

/** Nothing disproved an over-cap finding, so it stays a potential blocker and says so. */
function marker(f) {
  if (f.demoted) return " (demoted: no proof)";
  if (f.verified === "unverified") return " (unverified: verify cap)";
  if (f.verified === "verifier_failed") return " (verifier: no usable verdict)";
  return "";
}

/** `[AGENT] {emoji} {title} | File: {file} | Task: {task}` — the legacy parser's shape. */
function findingLine(agentName, f) {
  const emoji = SEVERITY_EMOJI[f.severity] || SEVERITY_EMOJI.MEDIUM;
  const title = cell(f.title) + marker(f);
  return `[${agentName}] ${emoji} ${title} | File: ${cell(f.file) || "N/A"} | Task: ${cell(f.task) || "general"}`;
}

/** Unproven is not innocent: an unverified potential blocker fails closed, like an incomplete review. */
function decideVerdict({ blocking, incomplete, unverified }) {
  const outstanding = blocking.length > 0 || incomplete || unverified > 0;
  return outstanding ? "CHANGES_REQUESTED" : "APPROVE";
}

function renderAgentOutput({ agentName, blocking, advisory, failedDimensions, rubric, statsLine }) {
  const parseable = [];
  const refutedNotes = [];
  const advisoryNotes = [];

  for (const dim of failedDimensions) {
    parseable.push(
      `[${agentName}] 🔴 review incomplete: dimension ${cell(dim)} returned nothing | File: N/A | Task: general`,
    );
  }
  for (const f of blocking) parseable.push(findingLine(agentName, f));
  for (const f of advisory) {
    if (f.verified === "refuted") {
      refutedNotes.push(`- refuted: ${cell(f.title)} - ${cell(f.refutation)}`);
    } else if (f.verified === "unverified") {
      // A cap-overflowed finding is never disproven, so it stays a potential
      // blocker and keeps the parseable shape (see the "unverified" branch of marker()).
      parseable.push(findingLine(agentName, f));
    } else {
      // MEDIUM/LOW passthrough and demoted findings: advisory, so a note, never a
      // parseable line. marker() still carries the demoted text onto the note.
      advisoryNotes.push(`- ${cell(f.title)}${marker(f)}`);
    }
  }
  if (parseable.length === 0) parseable.push(`[${agentName}] ✅ No issues found`);

  const sections = [parseable.join("\n")];
  if (refutedNotes.length > 0) {
    sections.push(["### Refuted (adversarially verified, not blocking)", "", ...refutedNotes].join("\n"));
  }
  if (advisoryNotes.length > 0) {
    sections.push(["### Advisory (does not block)", "", ...advisoryNotes].join("\n"));
  }
  sections.push(["### Rubric", "", ...rubric.map((e) => `${e.rule_id}: ${e.verdict}`)].join("\n"));

  const rubricNotes = rubric.filter((e) => cell(e.note) !== "").map((e) => `- ${e.rule_id}: ${cell(e.note)}`);
  if (rubricNotes.length > 0) sections.push(["### Rubric notes", "", ...rubricNotes].join("\n"));

  sections.push(statsLine);
  return sections.join("\n\n");
}

function renderReviewMarkdown(state, args, agentOutput = renderAgentOutput(state)) {
  const agentName = state.agentName;
  const heading = agentName.charAt(0).toUpperCase() + agentName.slice(1).toLowerCase();
  // A dead verifier's finding is already counted once via `blocking`, so it must
  // not be counted again here.
  const outstanding = state.blocking.length + state.unverified + state.failedDimensions.length;
  const verdict = outstanding === 0 ? "Verdict: converged" : `Verdict: ${outstanding} findings`;
  const testsLine = args.tests_line ? args.tests_line : "Tests: {{TESTS_LINE}}";

  return [
    "---",
    `prd: ${cell(args.prd)}`,
    `review: ${cell(args.review)}`,
    `date: ${cell(args.date)}`,
    `head_sha: ${cell(args.head_sha)}`,
    `reviewers: ${agentName.toLowerCase()}`,
    "---",
    "",
    `## ${heading}`,
    "",
    agentOutput,
    "",
    verdict,
    testsLine,
    "",
  ].join("\n");
}

// ---- pure region (end) ----

const FINDINGS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["findings"],
  properties: {
    findings: {
      type: "array",
      maxItems: 25,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["title", "severity", "file", "evidence"],
        properties: {
          title: { type: "string", maxLength: 200 },
          severity: { type: "string", enum: ["CRITICAL", "HIGH", "MEDIUM", "LOW"] },
          file: { type: "string" },
          line: { type: "integer" },
          evidence: { type: "string", minLength: 1 },
          proof: { type: "string", pattern: "\\S" },
          fix: { type: "string" },
          task: { type: "string" },
        },
        if: {
          properties: { severity: { enum: ["CRITICAL", "HIGH"] } },
          required: ["severity"],
        },
        then: {
          required: ["proof"],
        },
      },
    },
  },
};

const RUBRIC_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["verdicts"],
  properties: {
    verdicts: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["rule_id", "verdict"],
        properties: {
          rule_id: { type: "string", enum: RUBRIC_IDS },
          verdict: { type: "string", enum: ["pass", "fail"] },
          note: { type: "string" },
        },
      },
    },
  },
};

const VERDICT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["refuted", "reason"],
  properties: { refuted: { type: "boolean" }, reason: { type: "string" } },
};

const DIMENSIONS = [
  {
    name: "requirements",
    checklist: [
      "Implementation matches the task description; all acceptance criteria met.",
      "No scope creep: features nobody asked for.",
      "No missing pieces from the original task.",
      'Every PRD "must have" requirement is addressed; no PRD section is left unimplemented.',
      "Dependencies are handled; the success metrics are achievable with what shipped.",
    ],
  },
  {
    name: "correctness",
    checklist: [
      "Hunt logic bugs in the diff: off-by-one, wrong boundary, inverted condition, missing await, lost error.",
      "Trace each changed function on its edge inputs (empty, one element, last element, null).",
      "Error handling is explicit and never silently swallowed (R10).",
      "The implementation matches the described behavior exactly (R9).",
      "No debug statements, TODOs, stubs or placeholder markers remain (R11).",
    ],
  },
  {
    name: "quality",
    checklist: [
      "Reduce complexity: no needless indirection, dead branches, or abstractions built for a single caller; nesting <= 4; functions under 50 lines.",
      "Eliminate redundancy: no logic duplicated within the diff or against existing code.",
      "Improve naming: names state intent; action-named functions start with a verb.",
      "Follow project standards (CLAUDE.md / AGENTS.md and the surrounding code); no dead code.",
      "Documentation: public APIs documented, complex logic commented, breaking changes noted.",
      "Flag behavior-preserving simplifications at MEDIUM. Never trade clarity for brevity, and never propose a change that alters behavior.",
    ],
  },
  {
    name: "tests",
    checklist: [
      "Unit tests for every new behavior; edge cases and error paths covered.",
      "Integration tests where the change crosses a boundary.",
      "Tests bind to intent, not just to observable behavior.",
      "No skipped or xfail test masks a failure.",
      "Tests actually run and pass.",
    ],
  },
  {
    name: "security",
    checklist: [
      "No hardcoded secrets.",
      "Input validated and sanitized at every boundary.",
      "No SQL or command injection risk.",
      "Auth/authz correctly applied.",
      "Sensitive data never logged.",
    ],
  },
];

const input = coerceArgs(args);
validateArgs(input);

const agentName = input.agent_name || "ALICE";
const cycle = input.cycle || 1;
const diffTruncated = isTruncated(input.diff_bytes, input.diff);
const prdMatch = input.prd_path ? input.prd_path.match(/(\d{5})/) : null;
const prdId = prdMatch ? prdMatch[1] : "";

const context = [
  "## Diff under review",
  "```diff",
  input.diff,
  "```",
  input.prd_text ? `## Requirements (PRD)\n\n${input.prd_text}` : "",
  input.diff_path
    ? `The diff above is TRUNCATED. Read the full diff at ${input.diff_path} before you judge anything.`
    : "",
  input.context_path ? `Further context for this change: read ${input.context_path}.` : "",
]
  .filter(Boolean)
  .join("\n\n");

const REPORTING_RULES = [
  "Report only defects you can ground in the diff above. Do not speculate.",
  "Every finding carries: title, severity (CRITICAL|HIGH|MEDIUM|LOW), file, and evidence — the exact snippet you are accusing, quoted from the diff.",
  "Every CRITICAL or HIGH also carries a proof: why the code is REALLY broken (the input, the path, the consequence), not why it looks suspicious. A CRITICAL or HIGH without a proof is demoted to MEDIUM and stops blocking.",
  "Add a fix (the concrete change) and a task id when you know them.",
  "Report nothing at all rather than padding the list.",
].join("\n");

const dimensionPrompt = (d) =>
  [
    `You are the ${d.name.toUpperCase()} reviewer of a completed change. Review ONLY through the ${d.name} lens.`,
    "",
    "Checklist:",
    ...d.checklist.map((c) => `- ${c}`),
    "",
    REPORTING_RULES,
    "",
    context,
  ].join("\n");

const rubricPrompt = [
  "You are the RUBRIC reviewer of a completed change. Answer every rule below with pass or fail.",
  "A rule you cannot confirm from the diff is a fail. Add a short note for every fail.",
  "",
  "## Rubric",
  "",
  input.rubric_text,
  "",
  context,
].join("\n");

const skepticPrompt = (f) =>
  [
    "You are an adversarial verifier. Another reviewer raised the finding below. Your job is to REFUTE it.",
    "",
    `Title: ${f.title}`,
    `Severity: ${f.severity}`,
    `File: ${f.file}${f.line ? `:${f.line}` : ""}`,
    `Evidence: ${f.evidence}`,
    `Claimed proof: ${f.proof || "(none)"}`,
    "",
    "Read the diff (and the surrounding code if you need it). Look for the guard, the caller, the constant, or the invariant that makes this finding wrong.",
    "Return refuted: true unless you can CONFIRM the defect is real from the code itself. Uncertainty refutes: if you cannot show the broken path, the finding does not survive.",
    "Return refuted: false only when you can restate the concrete failing input and its consequence.",
    "The reason field states, in one sentence, what refuted or confirmed it.",
    "",
    context,
  ].join("\n");

phase("Review");

const armed = securityTriggered(input.diff, input.changed_files);
const dims = DIMENSIONS.filter((d) => d.name !== "security" || armed);
log(`review-fanout: ${dims.length} finding dimensions + rubric${armed ? " (security armed)" : ""}`);

const dimResults = await parallel([
  ...dims.map((d) => () => agent(dimensionPrompt(d), { label: d.name, phase: "Review", schema: FINDINGS_SCHEMA })),
  () => agent(rubricPrompt, { label: "rubric", phase: "Review", schema: RUBRIC_SCHEMA }),
]);

const rubricResult = dimResults[dimResults.length - 1];
const failedDimensions = [];
let incomplete = false;

const tagged = [];
dims.forEach((d, i) => {
  const res = dimResults[i];
  if (!res || !Array.isArray(res.findings)) {
    failedDimensions.push(d.name);
    incomplete = true;
    return;
  }
  for (const f of res.findings) tagged.push({ ...f, dimensions: [d.name] });
});
if (!rubricResult || !Array.isArray(rubricResult.verdicts)) {
  failedDimensions.push("rubric");
  incomplete = true;
}

const demoted = demote(tagged);
const { unique, raw } = dedupe(demoted.findings);
const { toVerify, overflow } = selectForVerify(unique);
const passthrough = unique.filter((f) => f.severity !== "CRITICAL" && f.severity !== "HIGH");

phase("Verify");
log(`verifying ${toVerify.length} blocking findings (${overflow.length} over the cap)`);

const verdicts = await parallel(
  toVerify.map((f) => () => agent(skepticPrompt(f), { label: `verify: ${f.title}`, phase: "Verify", schema: VERDICT_SCHEMA })),
);

// A dead verifier's finding stays blocking via `verified.blocking` (see
// applyVerification) and is rendered with its own accurate marker — it is not a
// failed dimension, so it does not belong in `failedDimensions`.
const verified = applyVerification({ toVerify, verdicts, overflow, passthrough });

const rubric = aggregateRubric(rubricResult ? rubricResult.verdicts : null);

const stats = {
  dimensions: dims.length,
  raw,
  unique: unique.length,
  confirmed: verified.confirmed,
  refuted: verified.refuted,
  demoted: demoted.demoted,
  unverified: verified.unverified,
  diff_bytes: input.diff_bytes,
  diff_truncated: diffTruncated,
};
const statsLine =
  `_engine: workflow — dimensions ${stats.dimensions}, raw ${stats.raw}, unique ${stats.unique}, ` +
  `confirmed ${stats.confirmed}, refuted ${stats.refuted}, demoted ${stats.demoted}, ` +
  `unverified ${stats.unverified}, diff_bytes ${stats.diff_bytes}_`;

const state = {
  agentName,
  blocking: verified.blocking,
  advisory: verified.advisory,
  failedDimensions,
  rubric,
  statsLine,
  unverified: verified.unverified,
  verifierFailures: verified.verifierFailures,
};

const agent_output = renderAgentOutput(state);
const review_markdown = renderReviewMarkdown(
  state,
  {
    prd: prdId,
    review: cycle,
    date: input.date,
    head_sha: input.head_sha,
    tests_line: input.tests_line,
  },
  agent_output,
);

log(
  `review-fanout done: ${stats.raw} raw -> ${stats.unique} unique, ${verified.blocking.length} blocking, ` +
    `${stats.confirmed} confirmed, ${stats.refuted} refuted, ${stats.demoted} demoted, ${stats.unverified} unverified` +
    (incomplete ? ` — INCOMPLETE (${failedDimensions.join(", ")})` : ""),
);

return {
  verdict: decideVerdict({ blocking: verified.blocking, incomplete, unverified: verified.unverified }),
  blocking: verified.blocking,
  advisory: verified.advisory,
  rubric,
  incomplete,
  failedDimensions,
  stats,
  agent_output,
  review_markdown,
  stats_line: statsLine,
};
