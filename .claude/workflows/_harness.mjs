// Shared harness for the review-fanout.workflow.js pure-region test suite.
//
// The workflow script cannot be imported (it mixes `export const meta` with a
// top-level `return`, so neither the ESM nor the CJS loader accepts it).
// Instead it delimits its side-effect-free helpers with two marker comments;
// we slice that text out and evaluate it in a node:vm context.
//
// This module has no test() calls, so `node --test` does not pick it up on
// its own -- it is imported by the *.test.mjs files in this directory.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/*.test.mjs

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(HERE, "review-fanout.workflow.js");
const START = "// ---- pure region (start) ----";
const END = "// ---- pure region (end) ----";

export const PURE_SYMBOLS = [
  "MAX_DIFF_BYTES",
  "VERIFY_CAP",
  "RUBRIC_IDS",
  "SEVERITY_EMOJI",
  "SECURITY_RE",
  "coerceArgs",
  "validateArgs",
  "isTruncated",
  "securityTriggered",
  "cell",
  "norm",
  "dedupKey",
  "demote",
  "dedupe",
  "selectForVerify",
  "applyVerification",
  "aggregateRubric",
  "renderAgentOutput",
  "renderReviewMarkdown",
];

// Symbols the pure region MUST expose but does not yet. They resolve leniently
// (a missing one lands as `undefined` rather than blowing up the whole suite),
// so a not-yet-implemented contract fails its own tests loudly and leaves every
// other test's signal intact.
const CONTRACT_SYMBOLS = ["decideVerdict"];

// The shape the downstream consolidation script parses. A finding that does not
// match this is invisible to it: it never reaches the findings table and never
// becomes a rework task.
export const CONSOLIDATION_RE =
  /^\[([A-Z][A-Z0-9_]*)\] (🔴|🟠|🟡|⚪) (.+?) \| File: (.+?) \| Task: (.+)$/u;

export const EXPECTED_RUBRIC_IDS = [
  "R1",
  "R2",
  "R3",
  "R4",
  "R6",
  "R7",
  "R8",
  "R9",
  "R10",
  "R11",
  "R12",
  "R13",
];

let cached = null;

/**
 * Slice the pure region out of the workflow script and evaluate it.
 * Fails loudly (clear message, never a silent skip) when the script or the
 * markers are missing.
 */
export function pure() {
  if (cached) return cached;

  if (!existsSync(SCRIPT)) {
    throw new Error(
      `workflow script not found: ${SCRIPT} — the implementation must create it`,
    );
  }
  const src = readFileSync(SCRIPT, "utf8");
  const start = src.indexOf(START);
  const end = src.indexOf(END);
  if (start === -1 || end === -1 || end < start) {
    throw new Error(
      `pure region markers not found in ${SCRIPT} — expected "${START}" ... "${END}"`,
    );
  }

  const region = src.slice(start + START.length, end);
  // console only — the real Workflow sandbox guarantees ECMAScript built-ins,
  // not Node globals; injecting Buffer here once masked a sandbox-fatal
  // Buffer.byteLength call in the workflow (found 2026-07-19).
  const sandbox = { console };
  vm.createContext(sandbox);
  // The exporter runs in the same script, so it sees the region's top-level
  // `const`/`function` lexical bindings (which never land on globalThis).
  // CONTRACT_SYMBOLS are read through a try/catch: an undeclared identifier
  // throws a catchable ReferenceError, so a missing contract symbol arrives as
  // `undefined` and only its own tests fail.
  const exporter =
    `\n;globalThis.__pure__ = { ${PURE_SYMBOLS.join(", ")} };\n` +
    `;globalThis.__contract__ = {};\n` +
    CONTRACT_SYMBOLS.map(
      (name) =>
        `;try { globalThis.__contract__.${name} = ${name}; } ` +
        `catch (e) { globalThis.__contract__.${name} = undefined; }\n`,
    ).join("");
  try {
    vm.runInContext(region + exporter, sandbox, { filename: SCRIPT });
  } catch (err) {
    // Errors cross a realm boundary here, so `instanceof` is unreliable.
    const name = err && err.name;
    const msg = err && err.message;
    if (name === "ReferenceError") {
      throw new Error(
        `pure region does not define every required symbol [${PURE_SYMBOLS.join(", ")}]: ${msg}`,
      );
    }
    throw new Error(`pure region failed to evaluate: ${name}: ${msg}`);
  }

  cached = { ...sandbox.__pure__, ...sandbox.__contract__ };
  return cached;
}

/**
 * Call the contracted verdict function, failing with the interface it must have
 * rather than with a bare "is not a function".
 */
export function decide(p, state) {
  assert.equal(
    typeof p.decideVerdict,
    "function",
    "the verdict must be decided by decideVerdict({blocking, incomplete, unverified}) " +
      "INSIDE the pure region — an inline ternary in the impure region is unreachable, " +
      "so no test can prove the engine fails closed",
  );
  return p.decideVerdict(state);
}

/** The verdict inputs of a review with nothing outstanding. */
export function verdictState(over = {}) {
  return { blocking: [], incomplete: false, unverified: 0, ...over };
}

// Values that cross back out of the vm realm carry the vm's intrinsics, so
// `deepEqual` (which compares prototypes) needs a host-realm copy first.
export const arr = (x) => Array.from(x);
const isError = (e) => Object.prototype.toString.call(e) === "[object Error]";
export const lines = (s) => s.split("\n");
export const invalidArgs = (e) =>
  isError(e) && typeof e.message === "string" && e.message.startsWith("INVALID_ARGS: ");

export function finding(overrides = {}) {
  return {
    title: "a title",
    severity: "MEDIUM",
    file: "src/x.js",
    evidence: "some evidence",
    dimensions: ["correctness"],
    ...overrides,
  };
}

export function render(p, over = {}) {
  return p.renderAgentOutput({
    agentName: "ALICE",
    blocking: [],
    advisory: [],
    failedDimensions: [],
    rubric: p.aggregateRubric([]),
    statsLine: "stats: raw=0 unique=0",
    ...over,
  });
}

/** The File cell of a finding line, as the consolidation script would read it. */
export function fileCell(line) {
  const m = line.match(CONSOLIDATION_RE);
  assert.ok(m, `the line does not match the consolidation shape at all: ${line}`);
  return m[4];
}

export function reviewBase(p, over = {}) {
  return {
    agentName: "ALICE",
    blocking: [],
    advisory: [],
    failedDimensions: [],
    rubric: p.aggregateRubric([]),
    statsLine: "stats: raw=0 unique=0",
    confirmed: 0,
    refuted: 0,
    unverified: 0,
    verifierFailures: [],
    ...over,
  };
}

/** The lines between the opening and closing `---` of the rendered review file. */
export function frontmatter(out) {
  const ls = lines(out);
  assert.equal(ls[0], "---", `the file opens with YAML frontmatter:\n${out}`);
  const close = ls.indexOf("---", 1);
  assert.notEqual(close, -1, `the frontmatter block is closed:\n${out}`);
  return ls.slice(1, close);
}
