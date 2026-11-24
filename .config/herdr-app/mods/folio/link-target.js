const MARKDOWN = /\.(?:md|markdown|mdx)$/i;

export function sourcePosition(line, column) {
  const valid = value => Number.isInteger(value) && value > 0 && value <= 2147483647;
  return valid(line) ? { line, column: valid(column) ? column : 1 } : {};
}

// Herdr (0.1.18) reads the position off the clicked text itself: `:16:4`, a range
// (`:5-12`) or an anchor (`#L5`) arrive as link.line and link.column.
export function previewTarget({ link, source }) {
  if (link.kind !== "file" || !link.path || source.machine || !MARKDOWN.test(link.path)) return null;
  const props = { path: link.path, ...sourcePosition(link.line, link.column) };
  if (source.pane) return ["pane.split", { pane: source.pane, direction: "right", mod: "folio", props }];
  if (source.space) return ["tab.new", { space: source.space, name: link.path.split("/").at(-1), mod: "folio", props }];
  return null;
}
