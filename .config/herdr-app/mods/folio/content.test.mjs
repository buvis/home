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
    assert.deepEqual(parse(text), [{ markdown: text, line: 1 }]);
});

test("retain tables, alignment, escaped pipes and references across fragments", () => {
  const table = parse("| A | B |\n|:---|---:|\n| a\\|b | 2 |")[0];
  assert.deepEqual(table.align, ["left", "right"]);
  assert.equal(table.rows[1][0], "a\\|b");
  const refs = parse("[link][x]\n\n```js\n[x]: fake\n```\n\n[x]: https://example.com");
  assert.ok(refs[0].markdown.includes("[x]: https://example.com"));
  assert.equal(refs[1].code, "[x]: fake");
});

test("heading targets use source lines across frontmatter, fences, tables and duplicate slugs", () => {
  const parts = parse([
    "---", "# Hidden YAML", "tag: example", "---",
    "# Hello *world*!", "", "[Jump](#hello-world-1)", "",
    "| A |", "|--:|", "| 1 |", "",
    "~~~js", "# Hidden code", "~~~",
    "Hello world", "---", "", "## 中文 标题", "## Hello world-1",
  ].join("\r\n"));
  assert.equal(parts[0].code, "# Hidden YAML\ntag: example");
  const headings = parts.filter(part => part.heading);
  assert.deepEqual(headings.map(part => [part.heading.slug, part.heading.line]),
    [["hello-world", 5], ["hello-world-1", 16], ["中文-标题", 19], ["hello-world-1-1", 20]]);
  assert.equal(headings[0].markdown, "# Hello *world*!");
  assert.equal(headings[1].markdown, "Hello world\n---");
});

test("keep nested Markdown whole while extracting standalone Mermaid and multiline setext", () => {
  const nested = "- Item\nlazy continuation\n  ## Nested\n  ```mermaid\n  graph LR\n  ```\n\n> # Quoted";
  const parts = parse(nested + "\n\nContinued\nheading\n=====\n\n  ~~~Mermaid title\n  graph LR\n  A-->B\n  ~~~\n~~~mermaid\nflowchart LR");
  assert.equal(parts[0].markdown.trimEnd(), nested);
  assert.equal(parts[1].heading.title, "Continued heading");
  assert.equal(parts[2].language, "mermaid");
  assert.equal(parts[2].code, "graph LR\nA-->B");
  assert.equal(parts[2].closed, true);
  assert.equal(parts[3].closed, false);
});

test("preserve multiline link references and ignore headings and diagrams inside HTML comments", () => {
  const comment = "<!--\n## Not a heading\n```mermaid\ngraph LR\nA --- B\n```\n-->";
  const parts = parse("# First\n\n[Jump][where]\n\n" + comment +
    "\n\n## Last\n\n[where]:\n  #last\n  \"Chapter two\"");
  assert.deepEqual(parts.flatMap(part => part.heading?.slug ?? []), ["first", "last"]);
  assert.ok(parts.every(part => part.code === undefined));
  const body = parts.find(part => part.markdown?.includes("[Jump][where]")).markdown;
  assert.ok(body.includes(comment));
  assert.match(body, /\[where\]:\n  #last\n  "Chapter two"/);
});
