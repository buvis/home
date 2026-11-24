// Ctrl/Cmd-click on file:line in a terminal opens that file in Neovim at that line,
// in a split right of the clicked pane. A link without a line stays with Herdr
// (the default app), and so do remote terminals and paths Herdr could not resolve.
// The layout lists this mod after folio, so Markdown goes to the preview first.
import { run } from "herdr";

// Safe integers print as plain digits; 1e21 and above would print as "1e+21".
const whole = (n) => Number.isSafeInteger(n) && n > 0;

// ["command", args] for a click this mod takes, else null.
export function editTarget({ link, source }) {
  if (link.kind !== "file" || !link.path || source.machine || !whole(link.line)) return null;
  const argv = ["nvim", `+call cursor(${link.line},${whole(link.column) ? link.column : 1})`, "--", link.path];
  if (source.pane) return ["pane.split", { pane: source.pane, direction: "right", argv }];
  if (source.space) return ["tab.new", { space: source.space, name: link.path.split("/").at(-1), argv }];
  return null;
}

export function handleLink(click) {
  const target = editTarget(click);
  if (!target) return "pass";
  run(...target);
  return "handled";
}
