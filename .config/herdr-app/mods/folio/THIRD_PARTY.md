# Folio Mermaid and Markdown notices

Folio takes the QuickJS-compatible SVG bundle from [Preview Plus at
`9d8e0172`](https://github.com/linziyanleo/herdr-mods/tree/9d8e0172da18902b18650951fe3f187e19964334/preview-plus).
`svg-colors.js` uses its SVG color and font conversion, adapted upstream from
[Herdr Files Plus](https://github.com/jjongkwann/herdr-files-plus/tree/b43c4e3e1dc2305c952ef923abda78abea095f70).
`headings.js` adapts Preview Plus's heading and list parsing for Folio's
single pass over source lines.

| Component | License | Use |
| --- | --- | --- |
| Preview Plus | [MIT](licenses/Preview-Plus-MIT.txt) | Upstream bundle, SVG conversion, heading and list parsing |
| Herdr Files Plus | [MIT](licenses/Herdr-Files-Plus-MIT.txt) | SVG conversion and QuickJS build adaptation |
| beautiful-mermaid 1.1.3 | [MIT](licenses/beautiful-mermaid-MIT.txt) | SVG rendering |
| elkjs 0.11.1 | [EPL-2.0](licenses/elkjs-EPL-2.0.txt), [notices](licenses/elkjs-NOTICE.txt) | Graph layout with QuickJS patches |
| entities 7.0.1 | [BSD-2-Clause](licenses/entities-BSD-2-Clause.txt) | Entity decoding |

To reproduce the exact bundle from JavaScript inputs, check out the pinned
Preview Plus revision, enter `preview-plus/`, then run `npm ci --ignore-scripts`
and `npm run build -- --check`. Its lock file pins the inputs and esbuild
0.28.2. Its build script contains the elkjs prototype, global and timer patches
under EPL-2.0. The build consumes elkjs's published JavaScript. The
[upstream ELK source build instructions](https://github.com/kieler/elkjs/blob/0.11.1/README.md#building)
also require a sibling Eclipse ELK checkout. See the [pinned upstream
notices](https://github.com/linziyanleo/herdr-mods/blob/9d8e0172da18902b18650951fe3f187e19964334/preview-plus/mods/preview-plus/THIRD_PARTY.md)
for the source provenance and its limits. Herdr runs the bundled JavaScript
directly. Node and npm are build and test dependencies only.
