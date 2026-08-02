// PRD 00109 parity: the workflow, fed the real agent files, must produce
// prompts byte-identical to the ones it produced when the persona text was
// inline.
//
// The goldens in fixtures/prompt-goldens.json are a frozen historical artifact:
// they were captured from this workflow BEFORE any persona text moved into
// ~/.claude/agents/, so they record the real pre-migration bytes. They are not
// regenerable — the code that produced them no longer exists — which is exactly
// what makes them worth comparing against.
//
// This drives the workflow's OWN assembly (sliced out and evaluated, the same
// technique the harness uses for the pure region) rather than reimplementing
// it. A reimplementation would only prove this file agrees with itself.

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(HERE, "review-fanout.workflow.js");
const AGENTS = join(process.env.HOME, ".claude", "agents");
const GOLDENS = JSON.parse(
  readFileSync(join(HERE, "fixtures", "prompt-goldens.json"), "utf8"),
);

const START = "// ---- pure region (start) ----";
const TAIL = 'phase("Review");';
const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;

const DIMENSION_PERSONAS = ["rita", "cora", "grace", "toby", "mallory"];
const ALL_PERSONAS = [...DIMENSION_PERSONAS, "trent", "victor"];

/** The persona body the consuming skill passes through: the agent file with
 *  its frontmatter stripped. */
function body(name) {
  const text = readFileSync(join(AGENTS, `${name}.md`), "utf8");
  assert.match(text, FRONTMATTER, `${name}.md must open with frontmatter`);
  return text.replace(FRONTMATTER, "").trimStart();
}

/** Evaluate the workflow's assembly section against one set of args. Stops at
 *  `phase("Review")`, so no orchestration runs. */
function assembleWith(args) {
  const src = readFileSync(SCRIPT, "utf8");
  const start = src.indexOf(START);
  const end = src.indexOf(TAIL);
  assert.ok(start >= 0 && end >= 0, "assembly slice markers not found in the workflow");
  const sandbox = { args, console };
  vm.createContext(sandbox);
  vm.runInContext(
    src.slice(start + START.length, end) +
      "\n;globalThis.__out__ = { dims: DIMENSION_PERSONAS, dimensionPrompt, rubricPrompt, skepticPrompt };\n",
    sandbox,
    { filename: SCRIPT },
  );
  return sandbox.__out__;
}

const personas = Object.fromEntries(ALL_PERSONAS.map((n) => [n, body(n)]));
const ARGS = { ...GOLDENS.fixture.args, personas };

test("every dimension persona assembles byte-identically to its pre-registry prompt", () => {
  const { dims, dimensionPrompt } = assembleWith(ARGS);
  for (const d of dims) {
    assert.equal(dimensionPrompt(d), GOLDENS.prompts[d.persona], d.persona);
  }
});

test("trent assembles byte-identically once the rubric is inlined", () => {
  const { rubricPrompt } = assembleWith(ARGS);
  assert.equal(rubricPrompt, GOLDENS.prompts.trent);
});

test("victor assembles byte-identically once the finding is inlined", () => {
  const { skepticPrompt } = assembleWith(ARGS);
  assert.equal(skepticPrompt(GOLDENS.fixture.finding), GOLDENS.prompts.victor);
});

test("the workflow dispatches exactly the personas the goldens cover", () => {
  const { dims } = assembleWith(ARGS);
  assert.deepEqual(
    [...dims.map((d) => d.persona), "trent", "victor"].sort(),
    Object.keys(GOLDENS.prompts).sort(),
  );
});

test("a missing persona body is INVALID_ARGS, never a weaker prompt", () => {
  const { personas: _drop, ...withoutPersonas } = ARGS;
  assert.throws(
    () => assembleWith(withoutPersonas),
    /INVALID_ARGS: personas is required/,
    "omitting personas entirely",
  );
  for (const name of ALL_PERSONAS) {
    assert.throws(
      () => assembleWith({ ...ARGS, personas: { ...personas, [name]: "" } }),
      new RegExp(`INVALID_ARGS: personas\\.${name} is required`),
      `blank ${name} body`,
    );
  }
});

test("an unsubstituted placeholder fails loudly instead of reaching a reviewer", () => {
  // A literal {RUBRIC} in a dispatched prompt is a silent quality failure:
  // the reviewer reads the brace text as if it were the rubric.
  assert.throws(
    () => assembleWith({ ...ARGS, personas: { ...personas, rita: "Body with {RUBRIC}.\n" } }).dimensionPrompt({ name: "requirements", persona: "rita" }),
    /unsubstituted placeholder \{RUBRIC\}/,
  );
});
