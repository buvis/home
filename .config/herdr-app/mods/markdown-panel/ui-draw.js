import { div, svg } from "gpui-kit";
import { Button } from "gpui-base";
import { alpha, glyphOf } from "./ui.js";
import { viewOf, stylesFor, hovering, changed, remembered, shapeOf, collapse } from "./ui-match.js";

const ink = (c, value) => {
  if (!value || typeof value !== "object" || !("colour" in value)) return value;
  if (value.colour === null) return "#00000000";
  return value.share === undefined ? c[value.colour] : alpha(c[value.colour], value.share);
};

const plain = () => div();

export const lastOp = (ops, name) => {
  const found = ops.filter(([op]) => op === name);
  return found.length ? found[found.length - 1] : null;
};
const radiusOf = (ops) => lastOp(ops, "rounded")?.[1] ?? 0;
const ringOf = (ops, c) => {
  const outline = lastOp(ops, "ring"), shadow = lastOp(ops, "shadow")?.[1];
  const [width, colour] = outline ? [outline[1], outline[2]] : shadow?.kind === "ring" ? [shadow.width, shadow] : [0, null];
  return width ? plain().absolute().inset_0().border(width).border_color(ink(c, colour)).rounded(radiusOf(ops)) : null;
};
const LINES = { top: "border_t", bottom: "border_b" };

// `hoverClass` is the Storybook's static hover mark. It is not on the element at rest.
// `live` is false for a node that is not a control: a hover callback would paint .kanso-control--hover onto it.
const worked = (node, rules, hoverClass, live) => {
  const own = collapse(stylesFor(node, rules));
  if (!live) return { own, extra: [] };
  const marked = hoverClass ? { ...node, classes: [...node.classes, hoverClass] } : node;
  return { own, extra: changed(own, stylesFor(marked, rules, hovering(node))) };
};
export const lookOf = (node, rules, hoverClass = null, live = true) => remembered(rules, `look${live}${hoverClass ?? ""}${shapeOf(node)}`, () => worked(node, rules, hoverClass, live));
const stepsOf = (ops, c) => ops.flatMap((entry) => {
  const [op, ...args] = entry;
  if (op === "ring") return [["relative", []]];
  if (op === "shadow" && entry !== lastOp(ops, "shadow")) return [];
  if (op === "shadow") return !args[0] ? [] : args[0].kind === "ring" ? [["relative", []]] : [[LINES[args[0].kind], [args[0].width]], ["border_color", [ink(c, args[0])]]];
  return [[op, args.map((arg) => ink(c, arg))]];
});
class Plans {
  constructor() { this.byTheme = new WeakMap(); }

  of(look, c) {
    if (!this.byTheme.has(c)) this.byTheme.set(c, new PlanOf());
    return this.byTheme.get(c).of(look, c);
  }
}
class PlanOf {
  constructor() { this.byLook = new WeakMap(); }

  of(look, c) {
    if (!this.byLook.has(look)) this.byLook.set(look, { own: stepsOf(look.own, c), extra: stepsOf(look.extra, c) });
    return this.byLook.get(look);
  }
}
const plans = new Plans();
const call = (el, [op, args]) => (args.length === 0 ? el[op]() : args.length === 1 ? el[op](args[0]) : el[op](...args));
const run = (el, steps) => steps.reduce(call, el);
export const painted = (el, look, c) => {
  const { own, extra } = plans.of(look, c);
  const drawn = run(el, own);
  return extra.length ? drawn.hover((style) => run(style, extra)) : drawn;
};
export const paint = (el, node, c, rules, hoverClass = null, live = true) => painted(el, lookOf(node, rules, hoverClass, live), c);
export const boxOf = (look, c, id = null) => {
  const el = plain();
  return painted(id ? el.id(id) : el, look, c);
};
export const box = (node, c, rules, id = null, live = false) => boxOf(lookOf(node, rules, null, live), c, id);

const apply = (el, ops, c) => ops.reduce((acc, entry) => {
  const [op, ...args] = entry;
  if (op === "ring") return acc.relative();
  if (op === "shadow" && entry !== lastOp(ops, "shadow")) return acc;
  if (op === "shadow") return !args[0] ? acc : args[0].kind === "ring" ? acc.relative() : acc[LINES[args[0].kind]](args[0].width).border_color(ink(c, args[0]));
  if (typeof acc[op] !== "function") throw new Error(`kit: gpui has no ${op}`);
  return acc[op](...args.map((arg) => ink(c, arg)));
}, el);

const iconName = (node) => (node.children.find((child) => child.tag === "use")?.attrs.href ?? "").replace(/^#(lu-)?/, "");

export const draw = (tree, c, { id, rules, presses = {} }) => {
  const make = (node, path) => {
    if (node.tag === "#text") return node.text;
    const own = stylesFor(node, rules);
    if (node.tag === "svg") return apply(svg(glyphOf(iconName(node))), own, c);
    const key = `${id}-${path}`;
    const press = presses[node.attrs.title];
    const hovered = stylesFor(node, rules, hovering(node)).slice(own.length);
    const base = apply(press ? Button.new(key).on_click(press) : plain().id(key), own, c);
    const withHover = hovered.length ? base.hover((style) => apply(style, hovered, c)) : base;
    const el = node.attrs.title ? withHover.tooltip(node.attrs.title) : withHover;
    return el.children([...node.children.map((child, i) => make(child, `${path}-${i}`)), ringOf(own, c)].filter(Boolean));
  };
  return viewOf(tree).map((node, i) => make(node, String(i)));
};
