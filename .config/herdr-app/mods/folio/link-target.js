const MARKDOWN = /\.(?:md|markdown|mdx)$/i;
const LOCATION = /\.(?:md|markdown|mdx):([1-9]\d*)(?::([1-9]\d*))?$/i;

export function sourcePosition(line, column) {
  const valid = value => Number.isInteger(value) && value > 0 && value <= 2147483647;
  return valid(line) ? { line, column: valid(column) ? column : 1 } : {};
}

export function previewTarget({ link, source }) {
  if (link.kind !== "file" || !link.path || source.machine || !MARKDOWN.test(link.path)) return null;
  const [, line, column] = LOCATION.exec(link.raw) || [];
  const props = { path: link.path, ...sourcePosition(Number(line), Number(column)) };
  if (source.pane) return ["pane.split", { pane: source.pane, direction: "right", mod: "folio", props }];
  if (source.space) return ["tab.new", { space: source.space, name: link.path.split("/").at(-1), mod: "folio", props }];
  return null;
}
