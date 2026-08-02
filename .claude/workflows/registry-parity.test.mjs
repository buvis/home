// PRD 00109 parity: a prompt rebuilt from the agent registry must be
// byte-identical to the prompt the workflow assembled inline before the
// personas moved out.
//
// The goldens in fixtures/prompt-goldens.json were captured from the workflow
// itself (capture-prompt-goldens.mjs) BEFORE any persona text was removed, so
// this compares registry output against the real historical bytes, not against
// a reimplementation.
//
// Assembly contract under test, for every workflow lane:
//     <agent body, placeholders substituted, trailing newline trimmed>
//     + "\n\n" + <run context block>

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const AGENTS = join(process.env.HOME, ".claude", "agents");
const GOLDENS = JSON.parse(
  readFileSync(join(HERE, "fixtures", "prompt-goldens.json"), "utf8"),
);

const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;

/** The persona body: the agent file with its frontmatter block stripped.
 *  The blank line agent files put between the closing `---` and the first
 *  line of prose is file formatting, not prompt content, so it is trimmed. */
function body(name) {
  const text = readFileSync(join(AGENTS, `${name}.md`), "utf8");
  assert.match(text, FRONTMATTER, `${name}.md must open with frontmatter`);
  return text.replace(FRONTMATTER, "").trimStart();
}

/** The run-input block the workflow appends to every dispatch prompt. */
function contextBlock(a) {
  return [
    "## Diff under review",
    "```diff",
    a.diff,
    "```",
    a.prd_text ? `## Requirements (PRD)\n\n${a.prd_text}` : "",
    a.diff_path
      ? `The diff above is TRUNCATED. Read the full diff at ${a.diff_path} before you judge anything.`
      : "",
    a.context_path ? `Further context for this change: read ${a.context_path}.` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

function assemble(name, substitutions = {}) {
  let text = body(name);
  for (const [key, value] of Object.entries(substitutions)) {
    text = text.replaceAll(`{${key}}`, value);
  }
  const leftover = text.match(/\{[A-Z_]+\}/);
  assert.equal(leftover, null, `${name}: unsubstituted placeholder ${leftover?.[0]}`);
  return `${text.trimEnd()}\n\n${contextBlock(GOLDENS.fixture.args)}`;
}

const DIMENSION_PERSONAS = ["rita", "cora", "grace", "toby", "mallory"];

for (const name of DIMENSION_PERSONAS) {
  test(`${name} assembles byte-identically to the pre-registry prompt`, () => {
    assert.equal(assemble(name), GOLDENS.prompts[name]);
  });
}

test("trent assembles byte-identically once the rubric is inlined", () => {
  assert.equal(
    assemble("trent", { RUBRIC: GOLDENS.fixture.args.rubric_text }),
    GOLDENS.prompts.trent,
  );
});

test("victor assembles byte-identically once the finding is inlined", () => {
  const f = GOLDENS.fixture.finding;
  assert.equal(
    assemble("victor", {
      FINDING_TITLE: f.title,
      FINDING_SEVERITY: f.severity,
      FINDING_FILE: f.line ? `${f.file}:${f.line}` : f.file,
      FINDING_EVIDENCE: f.evidence,
      FINDING_PROOF: f.proof || "(none)",
    }),
    GOLDENS.prompts.victor,
  );
});

test("every workflow lane has a golden and an agent file", () => {
  const expected = [...DIMENSION_PERSONAS, "trent", "victor"].sort();
  assert.deepEqual(Object.keys(GOLDENS.prompts).sort(), expected);
});
