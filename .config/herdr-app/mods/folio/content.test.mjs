import assert from "node:assert/strict";
import { test } from "node:test";
import { contentParts as parse } from "./content.js";

test("extract fences without interpreting code as Markdown", () => {
  const parts = parse("Before\n\n```JS title\n| A | B |\n|---|---|\n```\nAfter");
  assert.equal(parts[0].markdown, "Before\n");
  assert.equal(parts[1].language, "js");
  assert.equal(parts[1].code, "| A | B |\n|---|---|");
  assert.equal(parts[2].markdown, "After");
});

test("respect fence delimiters, CRLF, empty and unclosed blocks", () => {
  assert.equal(parse("~~~PY\r\nprint(1)\r\n~~~")[0].language, "py");
  assert.equal(parse("````js\n```\n~~~~\n````")[0].code, "```\n~~~~");
  assert.equal(parse("```js\nunclosed")[0].code, "unclosed");
  assert.equal(parse("```\n```")[0].code, "");
  assert.equal(parse("```invalid`info\ntext")[0].code, undefined);
});

test("keep nested and indented fences in native Markdown", () => {
  for (const text of ["- Item\n\n  ```js\n  code\n  ```", "    ```js\n    code\n    ```", "> ```js\n> code\n> ```"])
    assert.deepEqual(parse(text), [{ markdown: text }]);
});

test("retain tables, alignment, escaped pipes and references across fragments", () => {
  const table = parse("| A | B |\n|:---|---:|\n| a\\|b | 2 |")[0];
  assert.deepEqual(table.align, ["left", "right"]);
  assert.equal(table.rows[1][0], "a\\|b");
  const refs = parse("[link][x]\n\n```js\n[x]: fake\n```\n\n[x]: https://example.com");
  assert.ok(refs[0].markdown.includes("[x]: https://example.com"));
  assert.equal(refs[1].code, "[x]: fake");
});
