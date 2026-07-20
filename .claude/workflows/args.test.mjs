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

  // changed_files must be an array: a string would iterate CHARACTERS in
  // securityTriggered and silently drop the path-based security signal (PRD 00085 R3).
  assert.throws(
    () => p.validateArgs({ ...ok, changed_files: "src/auth.js\nsrc/db.js" }),
    invalidArgs,
    "a string changed_files iterates characters and under-arms the security dimension",
  );
  assert.throws(
    () => p.validateArgs({ ...ok, changed_files: "src/token.js" }),
    invalidArgs,
    "even a single-path string is rejected — it is still iterated char-by-char",
  );
  assert.doesNotThrow(
    () => p.validateArgs({ ...ok, changed_files: ["src/auth.js", "src/db.js"] }),
    "an array of paths is the required shape",
  );
  assert.doesNotThrow(
    () => p.validateArgs({ ...ok, changed_files: undefined }),
    "changed_files is optional — absent is fine",
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

// The engine computes `diffTruncated` in the IMPURE region (below the pure-region
// marker), as `input.diff_bytes > input.diff.length` — `.length` counts UTF-16 code
// units, not bytes, so a non-ASCII diff falsely reports truncation. The harness can
// only reach the pure region, so this seam does not yet exist to test:
//
//   REQUIRED SEAM: a function `isTruncated(diffBytes, diffText)` INSIDE the pure
//   region of review-fanout.workflow.js, returning
//   `diffBytes > Buffer.byteLength(diffText, "utf8")`. The engine body must call it
//   instead of the raw `.length` comparison, and _harness.mjs's PURE_SYMBOLS must
//   list "isTruncated" so pure() actually exposes it.
//
// Until that seam exists, `p.isTruncated` is undefined and every assertion below
// fails with "p.isTruncated is not a function" — a legitimate red test for a
// contract that has no implementation yet, not a bug in the test.
test("truncation is measured in bytes: a non-ASCII diff that matches its declared byte count is never falsely reported as truncated", () => {
  const p = pure();
  // "café — naïve": 12 UTF-16 code units, 16 real UTF-8 bytes (é and — are each one
  // code unit but two-plus bytes). diff_bytes here is the TRUE byte count of exactly
  // this text, i.e. nothing was truncated.
  const text = "café — naïve";
  const trueBytes = Buffer.byteLength(text, "utf8");
  assert.equal(
    p.isTruncated(trueBytes, text),
    false,
    "diff_bytes equal to the real byte count is not a truncation, even though it exceeds .length",
  );
});

test("truncation is measured in bytes: a declared byte count bigger than the text actually handed over is still reported as truncated", () => {
  const p = pure();
  const truncatedText = "@@ -1 +1 @@\n+const a = 1;"; // only a prefix of the real diff
  const realDiffBytes = Buffer.byteLength(truncatedText, "utf8") + 500; // the full diff was bigger
  assert.equal(
    p.isTruncated(realDiffBytes, truncatedText),
    true,
    "a declared byte count exceeding what was handed over means real truncation happened",
  );
});

test("validateArgs rejects a nonsense diff_bytes (NaN, Infinity, negative) as INVALID_ARGS, and accepts a valid non-negative finite one", () => {
  const p = pure();
  const ok = {
    diff: "@@ -1 +1 @@\n+const a = 1;\n",
    rubric_text: "R1: no stubs\n",
  };

  assert.throws(() => p.validateArgs({ ...ok, diff_bytes: NaN }), invalidArgs, "NaN diff_bytes");
  assert.throws(
    () => p.validateArgs({ ...ok, diff_bytes: Infinity }),
    invalidArgs,
    "Infinity diff_bytes",
  );
  assert.throws(() => p.validateArgs({ ...ok, diff_bytes: -1 }), invalidArgs, "negative diff_bytes");
  assert.doesNotThrow(
    () => p.validateArgs({ ...ok, diff_bytes: 0 }),
    "0 is a valid non-negative finite diff_bytes",
  );
});

test("MAX_DIFF_BYTES in validateArgs caps real UTF-8 bytes, not UTF-16 code units", () => {
  const p = pure();
  // 'é' is one UTF-16 code unit but two UTF-8 bytes: repeated, .length stays under
  // the cap while the real byte size sails past it.
  const diff = "é".repeat(200001);
  assert.ok(diff.length <= p.MAX_DIFF_BYTES, "fixture must stay under the cap by .length");
  assert.ok(
    Buffer.byteLength(diff, "utf8") > p.MAX_DIFF_BYTES,
    "fixture must exceed the cap by real UTF-8 bytes",
  );
  assert.throws(
    () =>
      p.validateArgs({
        diff,
        rubric_text: "R1: no stubs\n",
        diff_bytes: 32, // deliberately unrelated to diff's real size: isolates the diff-length check itself
      }),
    invalidArgs,
    "a diff within the code-unit cap but over the real byte cap must still be rejected",
  );
});
