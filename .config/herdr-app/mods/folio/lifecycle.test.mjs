import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";

const runtime = new URL("./main.js", import.meta.url).href;
const mocks = {
  "gpui-kit": "export class View {}; export const div = null, image = null, svg = null;",
  "gpui-base": `export const h_flex = null, v_flex = null, TextView = null, Editor = null;
    export const EditorState = { new: () => ({ release() {} }) };
    export const ScrollHandle = { new: () => globalThis.folioTest.scroll };`,
  "herdr": `export const props = () => ({ path: "/docs/notes.md" }), checking = () => false;
    export const readTextFile = path => globalThis.folioTest.read(path);
    export const watchFolder = dir => globalThis.folioTest.watch(dir);
    export const appHome = () => "/unused", writeTextFile = null, exec = null, focused = null, panes = null;
    export const notify = () => {};`,
  "./mermaid.js": `export const DIAGRAM_LIMIT = 12;
    export const diagram = source => globalThis.folioTest.diagram(source);`,
};

test("apply only the latest read and discard diagrams and watches when their preview is gone", async t => {
  const reads = [], tasks = [], diagrams = [], jumps = [];
  let cancelled = 0, released = 0;
  globalThis.folioTest = {
    read: () => new Promise(resolve => reads.push(resolve)),
    watch: dir => {
      assert.equal(dir, "/docs");
      const result = Promise.withResolvers();
      return Object.assign(result.promise, { cancel() { cancelled++; result.resolve([]); } });
    },
    diagram: source => new Promise(resolve => diagrams.push({ source, resolve })),
    scroll: { release() { released++; }, scroll_to_item(index) { jumps.push(index); } },
  };
  const hooks = registerHooks({
    resolve(specifier, context, next) {
      if (context.parentURL === runtime && Object.hasOwn(mocks, specifier))
        return { url: `data:text/javascript,${encodeURIComponent(mocks[specifier])}`, shortCircuit: true };
      return next(specifier, context);
    },
  });
  t.after(() => { hooks.deregister(); delete globalThis.folioTest; });
  const { default: Folio } = await import(runtime);
  const preview = new Folio();
  const cx = { spawn(fn) { tasks.push(fn(cx)); }, notify() {} };
  preview.init(undefined, cx);
  preview.load(cx);
  reads[1]("# New\n\n```mermaid\nflowchart LR\nA-->B\n```");
  await tasks[2];
  reads[0]("# Old");
  await tasks[0];
  assert.deepEqual([...preview.headings.keys()], ["new"]);
  assert.equal(diagrams.length, 1);

  preview.follow("#new", cx);
  assert.deepEqual(jumps, [0]);
  assert.deepEqual(preview.position, { line: 1, column: 1 });
  preview.load(cx);
  reads[2]("Moved heading.\n\n# New");
  await tasks[4];
  assert.deepEqual(preview.position, { line: 3, column: 1 });
  diagrams[0].resolve({ path: "stale.svg", width: 8, height: 8 });
  await tasks[3];
  assert.equal(preview.diagramResults.size, 0);

  preview.load(cx);
  preview.close();
  reads[3]("# After close");
  await Promise.all(tasks);
  assert.deepEqual([...preview.headings.keys()], ["new"]);
  assert.equal(cancelled, 1);
  assert.equal(released, 1);
});
