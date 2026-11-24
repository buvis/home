import assert from "node:assert/strict";
import { test } from "node:test";
import { previewTarget, sourcePosition } from "./link-target.js";

test("route only the native clicked Markdown path and its diagnostic position", () => {
  const path = "/project/Bob's draft.MD";
  const source = { pane: "clicked", space: "workspace", machine: null };
  const target = previewTarget({ source, link: { kind: "file", path, raw: path + ":16:4", line: 16, column: 4 } });
  assert.deepEqual(target, ["pane.split", { pane: "clicked", direction: "right", mod: "folio",
    props: { path, line: 16, column: 4 } }]);
  // A range or an anchor has no column: Herdr reports its first line.
  assert.deepEqual(previewTarget({ source, link: { kind: "file", path, raw: path + "#L5-L12", line: 5 } })[1].props,
    { path, line: 5, column: 1 });
  assert.deepEqual(previewTarget({ source: { ...source, pane: null },
    link: { kind: "file", path, raw: "file:///project/Bob%27s%20draft.MD" } }),
    ["tab.new", { space: "workspace", name: "Bob's draft.MD", mod: "folio", props: { path } }]);
});

test("leave ordinary URLs, non-Markdown files and unresolved or remote links to Herdr", () => {
  const source = { pane: "clicked", machine: null };
  const link = { kind: "file", path: "/project/a.md", raw: "./a.md" };
  for (const skip of [{ kind: "url" }, { ...link, path: "/project/a.txt" }, { ...link, path: null }])
    assert.equal(previewTarget({ source, link: skip }), null);
  assert.equal(previewTarget({ source: { ...source, machine: "remote" }, link }), null);
  assert.deepEqual(sourcePosition(2147483648, 1), {});
  assert.deepEqual(sourcePosition("1", 1), {});
  assert.deepEqual(sourcePosition(2, undefined), { line: 2, column: 1 });
});
