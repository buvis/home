import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { diagram } from "./mermaid.js";

const flowchart = "flowchart LR\nA[Read] --> B[Preview]";
const read = path => readFile(path, "utf8").catch(error => {
  if (error.code === "ENOENT") return null;
  throw error;
});

test("render supported diagrams to native-compatible Solarized SVGs and share cache results", async t => {
  const home = await mkdtemp(join(tmpdir(), "folio-mermaid-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  let writes = 0;
  const write = (path, text) => {
    writes++;
    return writeFile(path, text, { flag: "wx" });
  };
  const render = source => diagram(source, home, read, write);
  const [first, concurrent] = await Promise.all([render(flowchart), render(flowchart)]);
  assert.equal(first, concurrent);
  assert.equal(first, await render(flowchart));
  assert.equal(writes, 1);

  const sources = [
    "sequenceDiagram\nAlice->>Bob: Hello",
    "stateDiagram-v2\n[*] --> Ready\nReady --> Done",
    "classDiagram\nclass Document {\n+save()\n}\nDocument --> Draft",
    "erDiagram\nUSER ||--o{ FILE : owns",
  ];
  const diagrams = [first, ...await Promise.all(sources.map(render))];
  assert.equal(new Set(diagrams.map(item => item.path)).size, diagrams.length);
  for (const { path, width, height } of diagrams) {
    assert.ok(width > 0 && height > 0);
    const svg = await read(join(home, path));
    assert.match(svg, /^<svg\b/);
    assert.match(svg, /#fdf6e3/i);
    assert.doesNotMatch(svg, /var\(|color-mix\(|@import/);
  }
});

test("reject unsupported, malformed and oversized diagrams without writing cache entries", async () => {
  const write = () => assert.fail("Invalid input must not write an SVG");
  const render = source => diagram(source, tmpdir(), async () => null, write);
  await assert.rejects(render('pie\n"A": 2'), /Supported diagrams/);
  await assert.rejects(render("sequenceDiagram\ninvalid syntax"), /Invalid or empty/);
  await assert.rejects(render(flowchart + "A".repeat(8000)), /8,000 characters/);
  await assert.rejects(render(flowchart + "\n".repeat(160)), /160 lines/);
});
