// Tests for pure-region contract completeness, and args coercion + validation
// (coerceArgs, validateArgs) in review-fanout.workflow.js.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/*.test.mjs

import test from "node:test";
import assert from "node:assert/strict";
import { pure, arr, invalidArgs, PURE_SYMBOLS } from "./_harness.mjs";
test("the pure region is present and every contracted symbol is defined", () => {
  const p = pure();
  for (const name of PURE_SYMBOLS) {
    assert.notEqual(p[name], undefined, `pure region is missing ${name}`);
  }
  assert.equal(p.MAX_DIFF_BYTES, 400000);
  assert.equal(p.VERIFY_CAP, 12);
  assert.equal(arr(p.RUBRIC_IDS).length, 12);
});

test("invalid arguments fail closed with an INVALID_ARGS error", () => {
  const p = pure();
  const ok = {
    diff: "@@ -1 +1 @@\n+const a = 1;\n",
    rubric_text: "R1: no stubs\nR2: tests exist\n",
    diff_bytes: 32,
  };

  assert.doesNotThrow(() => p.validateArgs(ok));

  assert.throws(() => p.validateArgs({ ...ok, diff: "" }), invalidArgs, "empty diff");
  assert.throws(() => p.validateArgs({ ...ok, diff: undefined }), invalidArgs, "missing diff");
  assert.throws(
    () => p.validateArgs({ ...ok, diff: "  \n\t  " }),
    invalidArgs,
    "whitespace-only diff",
  );
  assert.throws(
    () => p.validateArgs({ ...ok, rubric_text: undefined }),
    invalidArgs,
    "missing rubric",
  );
  assert.throws(() => p.validateArgs({ ...ok, rubric_text: "   " }), invalidArgs, "blank rubric");
  assert.throws(
    () => p.validateArgs({ ...ok, diff: "x".repeat(p.MAX_DIFF_BYTES + 1) }),
    invalidArgs,
    "the caller was supposed to truncate an over-cap diff",
  );
  assert.throws(
    () => p.validateArgs({ ...ok, diff_bytes: p.MAX_DIFF_BYTES + 1 }),
    invalidArgs,
    "an over-cap diff_bytes with no diff_path is unrecoverable",
  );
  assert.doesNotThrow(() =>
    p.validateArgs({ ...ok, diff_bytes: p.MAX_DIFF_BYTES + 1, diff_path: "/tmp/diff.patch" }),
  );
});

test("args handed over as a JSON string are parsed, not rejected as an empty diff", () => {
  const p = pure();
  const ok = {
    diff: "@@ -1 +1 @@\n+const a = 1;\n",
    rubric_text: "R1: no stubs\n",
    diff_bytes: 32,
  };

  // The Workflow tool delivers `args` verbatim, and a caller that stringified it
  // sends one JSON string. Rejecting that as a missing diff stops the review.
  // (Field-by-field: JSON.parse runs in the vm realm, so its prototype is foreign
  // to deepStrictEqual.)
  const parsed = p.coerceArgs(JSON.stringify(ok));
  assert.equal(parsed.diff, ok.diff);
  assert.equal(parsed.rubric_text, ok.rubric_text);
  assert.equal(parsed.diff_bytes, ok.diff_bytes);
  assert.doesNotThrow(() => p.validateArgs(parsed));

  assert.equal(p.coerceArgs(ok), ok, "an object passes through untouched");
  assert.throws(() => p.coerceArgs("not json at all"), invalidArgs, "unparseable string");
  assert.throws(() => p.validateArgs(p.coerceArgs('"a bare string"')), invalidArgs, "not an object");
});
