// Capture the review-fanout dispatch prompts as goldens (PRD 00109 Phase 0).
//
// The persona prompt builders live OUTSIDE the harness's pure region, so this
// slices the workflow from the pure-region start marker down to the end of
// `skepticPrompt` and evaluates that in a vm with `args` stubbed. Everything in
// the slice is deterministic; nothing below it (phase/log/agent/pipeline) is
// touched, so no orchestration runs.
//
// Run BEFORE the persona text moves into the agent registry, so the goldens
// record today's bytes:
//   node ~/.claude/workflows/capture-prompt-goldens.mjs
//
// Writes fixtures/prompt-goldens.json, which the Phase 2 parity tests compare
// the registry-assembled prompts against.

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(HERE, "review-fanout.workflow.js");
const START = "// ---- pure region (start) ----";
const TAIL = 'phase("Review");';

// One fixture run, pinned so the goldens are reproducible.
const FIXTURE_DIFF = readFileSync(join(HERE, "fixtures", "code-diff.patch"), "utf8");

const FIXTURE_ARGS = {
  diff: FIXTURE_DIFF,
  // Untruncated: diff_bytes matches the diff actually inlined, so no
  // "read the full diff at ..." line enters the golden.
  diff_bytes: Buffer.byteLength(FIXTURE_DIFF, "utf8"),
  prd_text: readFileSync(join(HERE, "fixtures", "fixture-prd.md"), "utf8"),
  prd_path: "dev/local/prds/wip/00109-register-reviewer-agents-v1.md",
  rubric_text: "R1. Every requirement is implemented.\nR2. No debug code remains.",
  changed_files: ["src/auth.ts", "src/auth.test.ts"],
  agent_name: "ALICE",
  cycle: 1,
};

const FIXTURE_FINDING = {
  title: "Missing null guard on session lookup",
  severity: "HIGH",
  file: "src/auth.ts",
  line: 42,
  evidence: "const user = sessions[id].user;",
  proof: "An expired id yields undefined and throws on .user.",
};

function sliceAssembly() {
  const src = readFileSync(SCRIPT, "utf8");
  const start = src.indexOf(START);
  const end = src.indexOf(TAIL);
  if (start < 0 || end < 0) {
    throw new Error(
      `assembly slice markers not found in ${SCRIPT} — expected ${START} ... ${TAIL}`,
    );
  }
  return src.slice(start + START.length, end);
}

const sandbox = { args: FIXTURE_ARGS, console };
vm.createContext(sandbox);
vm.runInContext(
  sliceAssembly() +
    "\n;globalThis.__out__ = { DIMENSIONS, dimensionPrompt, rubricPrompt, skepticPrompt };\n",
  sandbox,
  { filename: SCRIPT },
);

const { DIMENSIONS, dimensionPrompt, rubricPrompt, skepticPrompt } = sandbox.__out__;

// Dimension name -> persona, per PRD 00109.
const PERSONA = {
  requirements: "rita",
  correctness: "cora",
  quality: "grace",
  tests: "toby",
  security: "mallory",
};

const goldens = { fixture: { args: FIXTURE_ARGS, finding: FIXTURE_FINDING }, prompts: {} };
for (const d of DIMENSIONS) goldens.prompts[PERSONA[d.name]] = dimensionPrompt(d);
goldens.prompts.trent = rubricPrompt;
goldens.prompts.victor = skepticPrompt(FIXTURE_FINDING);

const out = join(HERE, "fixtures", "prompt-goldens.json");
writeFileSync(out, JSON.stringify(goldens, null, 2) + "\n");
console.log(`captured ${Object.keys(goldens.prompts).length} prompt goldens -> ${out}`);
