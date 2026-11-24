// The kit with the Storybook's signatures: a piece takes its props and returns a drawing, `(id, c, more) => element`.
import { row as drawRow } from "./ui-row.js";
import { button as drawButton } from "./ui-button.js";
import { menu as drawMenu } from "./ui-menu.js";
import { stateEmpty, stateLine, stateBlock } from "./ui-state.js";
import { toast as drawToast } from "./ui-toast.js";
import { skeletonOf as drawSkeleton, tabSkeleton as drawTabSkeleton } from "./ui-skeleton.js";
import { figure } from "./ui-metric.js";
import { diffText, facts, plus } from "./ui-facts.js";
import { card as drawCard } from "./ui-card.js";
import { code as drawCode } from "./ui-code.js";
import { dawnSky } from "./ui-dawn.js";
import { thumbnail as drawThumbnail } from "./ui-thumbnail.js";
import { markdown as drawMarkdown, markdownBlock as drawMarkdownBlock, markdownWords as drawMarkdownWords } from "./ui-markdown.js";
import { tipText } from "./ui-tooltip.js";
import { avatar as drawAvatar } from "./ui-avatar.js";
import { chip as drawChip } from "./ui-chip.js";
import { mark as drawMark } from "./ui-mark.js";
import { tab as drawTabs } from "./ui-tab.js";
import { stackOf } from "./ui-stack.js";
import { statusItem as drawStatusItem, needsItem as drawNeedsItem, stepper as drawStepper } from "./ui-status.js";
import { div, svg, image } from "gpui-kit";
import { Button } from "gpui-base";
import { DAWN_H, ICON_ROW, glyphOf, toneColor } from "./ui.js";

// Facts as words, as the Storybook writes them.
export { diffText, facts, plus };

// A composition's children: the Storybook joins their markup, the app keeps the pieces, each drawn where the list places it.
export const list = (...children) => children.flat(Infinity).filter((child) => child !== null && child !== undefined && child !== false);
// A label made of words and values, such as a name inside an action's title.
export const phrase = (...parts) => parts.join(" ");
// A tool: its icon and the label its tooltip reads.
export const icon = (name, label) => ({ icon: name, label });
// The room between the pieces before it and after it.
export const grow = () => (id, c, more = {}) => {
  given(more);
  return div().flex_1();
};

const EVENTS = {
  onSize: (el, fn) => el.on_size_change(fn),
  onOver: (el, fn) => el.on_hover(fn),
  onPress: (el, fn) => el.on_mouse_down("left", fn),
  onRelease: (el, fn) => el.on_mouse_up("left", fn),
  onMenu: (el, fn) => el.on_mouse_down("right", fn),
  onMove: (el, fn) => el.on_mouse_move(fn),
  onWheel: (el, fn) => el.on_scroll_wheel(fn),
};
// `onChange(key, cx)`: a choice among tabs or menu items; `onOpen(open, cx)`: a menu under a button opens or shuts; `onLink(url, cx)`: a link's press in markdown.
// `presses`: a composition's press targets by name, its icon or else its label; a stack passes them down and each press takes its own.
// `focuses`: by the same names, the focus handles the caller owns, so a target keeps the keyboard while it is drawn in another form.
const HANDLERS = ["on", "presses", "focuses", "wires", "onClick", "onChange", "onClose", "onOpen", "onHover", "onKey", "onLink", "focusHandle", ...Object.keys(EVENTS)];
const withEvents = (el, events) => Object.entries(events).filter(([, fn]) => fn).reduce((drawnEl, [name, fn]) => EVENTS[name](drawnEl, fn), el);
const appIcon = (icon) => (typeof icon === "string" ? icon.replace(/^lu-/, "") : icon);
const iconOf = (icon) => (icon === "none" ? null : appIcon(icon));
const withIcon = (part) => (part?.icon ? { ...part, icon: appIcon(part.icon) } : part);
const keyOf = ({ icon, label }) => (icon ? appIcon(icon) : label);
const parts = (slot) => [slot].flat(Infinity).filter((part) => part !== null && part !== undefined && part !== false);
const drawn = (id, c, name, slot) => parts(slot).map((part, i) => (typeof part === "function" ? part(`${id}-${name}-${i}`, c) : part));

const given = (more) => {
  const unknown = Object.keys(more).filter((key) => !HANDLERS.includes(key));
  if (unknown.length) throw new Error(`kit: the app gives only handlers, not ${unknown.join(", ")}`);
  return Object.fromEntries(Object.entries(more).filter(([, value]) => value !== undefined));
};

// The first piece given `presses` or `focuses` checks, once drawn, that each name found a drawn target, as `on` checks its tools:
// a renamed label or icon throws instead of leaving its press or handle unbound. Pieces under it take theirs with `takeOf`.
// `Symbol.for`: one mark across every copy of the kit, as a composition and its slots may each import their own.
const noTool = (id, missing) => {
  if (missing.length) throw new Error(`kit: ${id} has no tool ${missing.join(", ")}`);
};
const TAKEN = Symbol.for("kanso.presses.taken");
const NAMED = ["presses", "focuses"];
const pressing = (draw) => (id, c, more = {}, context = {}) => {
  const fresh = NAMED.filter((name) => more[name] && !more[name][TAKEN]);
  if (!fresh.length) return draw(id, c, more, context);
  const marked = Object.fromEntries(fresh.map((name) => [name, { ...more[name], [TAKEN]: new Set() }]));
  const el = draw(id, c, { ...more, ...marked }, context);
  noTool(id, Object.values(marked).flatMap((named) => Object.keys(named).filter((key) => named[key] && !named[TAKEN].has(key))));
  return el;
};
// A name several targets share, such as rows with one icon, takes a list: one press each, in drawing order (null for one that does not act);
// each turn taken is marked beside the name.
const atKey = (named, key) => (key in named || !(`lu-${key}` in named) ? key : `lu-${key}`);
const takeOf = (named, wanted) => {
  const key = atKey(named, wanted);
  const given = named[key] ?? null;
  if (given) named[TAKEN]?.add(key);
  if (!Array.isArray(given)) return given;
  const turn = [...(named[TAKEN] ?? [])].filter((mark) => mark.startsWith(`${key}\u0000`)).length;
  named[TAKEN]?.add(`${key}\u0000${turn}`);
  return given[turn] ?? null;
};

const wired = (on) => (tool) => (tool && on[keyOf(tool)] ? { ...tool, onClick: on[keyOf(tool)] } : tool);

// A detail fact with a `label` is a press, wired by that label as a tool is.
const pressFact = (part) => typeof part === "object" && Boolean(part.label);
// A tool not given in `on` takes its press from the `presses` a stack passes down, by the same name.
const withHandlers = (id, raw, actions, action, detail, presses) => {
  const own = parts(actions).map(withIcon);
  const lone = withIcon(action);
  const handed = Object.fromEntries([...own, lone].filter(Boolean).map(keyOf).filter((key) => !raw[key] && presses[atKey(presses, key)]).map((key) => [key, takeOf(presses, key)]));
  const on = Object.fromEntries(Object.entries({ ...raw, ...handed }).map(([key, fn]) => [appIcon(key), fn]));
  const facts = parts(detail).map(withIcon);
  const targets = [...own, lone, ...facts.filter(pressFact)];
  noTool(id, Object.keys(on).filter((key) => !targets.some((tool) => tool && keyOf(tool) === key)));
  return { actions: own.map(wired(on)), action: wired(on)(lone), detail: facts.map((part) => (pressFact(part) ? wired(on)(part) : part)) };
};

// The Storybook's mark symbols as a row's icon are the app's marks, drawn in the icon's place.
const MARK_ICONS = { "e-work": "working", "e-blk": "blocked", "e-done": "done", "e-idle": "idle" };

export const row = ({ icon, flag, detail, action, actions, start, tools, ...props }) => pressing((id, c, more) => {
  const key = keyOf({ icon, label: props.name });
  const { on = {}, presses = {}, focuses = {}, onClick = takeOf(presses, key), focusHandle = takeOf(focuses, key), onPress, onRelease, onMenu, onMove, ...handlers } = given(more);
  const status = MARK_ICONS[icon];
  const drawnRow = drawRow(id, c, {
    ...props, ...handlers, onClick, focusHandle, ...withHandlers(id, on, actions, action, detail, presses), icon: status ? null : iconOf(icon), flag: appIcon(flag),
    start: [...drawn(id, c, "start", start), ...(status ? [drawMark(c, { status })] : [])], tools: drawn(id, c, "tools", tools),
  });
  return withEvents(drawnRow, { onPress, onRelease, onMenu, onMove });
});

// `icon: "none"` is the Storybook's no icon; app-only props, such as `color`, pass through as the row's do.
// `content`: kit pieces or elements drawn in place of the icon and label, such as a picture and its name. No `tip` reads the label.
// `ink`: the stack around it quiets it, as Sort at its default order is dim; in a `card` it stands at the card's start.
export const button = ({ label, icon = "none", content = [], tip = "", name = "", ...props }) => pressing((id, c, more, { ink = null, card = false }) => {
  const key = name || keyOf({ icon: iconOf(icon), label });
  const { presses = {}, focuses = {}, wires = {}, onClick = takeOf(presses, key), focusHandle = takeOf(focuses, key) } = given(more);
  const drawnButton = drawButton(id, label, onClick, c, { ...(ink ? { color: c[ink] } : {}), ...props, name, tip: tip || null, icon: iconOf(icon), content: drawn(id, c, "content", content) });
  const placedButton = card ? drawnButton.self_start() : drawnButton;
  const focused = focusHandle ? placedButton.track_focus(focusHandle) : placedButton;
  return wires[key] ? wires[key](focused) : focused;
});

// Explain to <agent>: the bot icon and the agent named in words; its press starts that agent on the question.
export const explainButton = ({ agent, size = "md" }) => button({ label: `Explain to ${agent}`, kind: "tonal", size, icon: "lu-bot" });

// Each item carries its own `onClick`, or, with a `key`, calls `onChange` with it: a menu's items are data, not tools.
export const menu = ({ title = null, items = [] }) => (id, c, more = {}) => {
  const { onChange = null } = given(more);
  const chosen = (item) => (onChange && item.key && !item.onClick ? { ...item, onClick: (cx) => onChange(item.key, cx) } : item);
  return drawMenu(id, { title, items: items.map(withIcon).map(chosen) }, c);
};

// A drawing that takes no handler: the app's piece with these props.
const still = (draw) => (props) => (id, c, more = {}) => {
  given(more);
  return draw(c, props);
};
export const avatar = ({ initial, image = null, size = "md", tone = null }) => still(drawAvatar)({ initial, image, size, tone: tone || null });
export const chip = ({ label, quiet = false, pill = false, tone = null }) => pressing((id, c, more = {}) => {
  const { presses = {}, onClick = takeOf(presses, label) } = given(more);
  const drawn = drawChip(c, { label, quiet, pill, tone: tone || null });
  return onClick ? Button.new(`${id}-${label}`).on_click((_e, cx) => onClick(cx)).tooltip("Replay the sunrise").child(drawn) : drawn;
});
export const mark = ({ status, size = "md" }) => still(drawMark)({ status, size });
// An icon on its own, at a row's size, in the muted ink or its `tone`.
export const glyph = (icon, tone = "") => still((c) => svg(glyphOf(appIcon(icon))).size(ICON_ROW).flex_none().text_color(tone ? toneColor(c, tone) : c.muted))();

export const tabs = ({ items = [], value = null, size = "md", track = false, disabled = false, icon = false, label = false }) => (id, c, more = {}, { bar = false } = {}) => {
  const { onChange = null, onClose = null, wires = {} } = given(more);
  const shown = items.map((item) => ({ ...item, icon: icon ? appIcon(item.icon) : null }));
  const own = Object.fromEntries(items.map(({ key }) => [key, { onClose: onClose && ((cx) => onClose(key, cx)), wire: wires[`tab:${key}`] }]));
  return drawTabs(id, shown, value, onChange, c, { size, track, disabled, collapsed: icon && !label, bar, on: own });
};

export const tabSkeleton = () => (id, c, more = {}, { index = 0 } = {}) => {
  given(more);
  return drawTabSkeleton(id, c, index);
};

// A wrapper that only places other pieces, as the Storybook's: `label` is a focusable one's tooltip and spoken name.
// A pressable one takes `onClick` itself; any other gives its handlers, `presses` with them, to its children.
// `context`: what the stack around it says of its place, such as a column.
export const stack = ({ variant, on = false, label = "", ...flags }, ...children) => pressing((id, c, more, context) => {
  const { onPress, onRelease, onMenu, onMove, onWheel, onSize, onOver, ...handlers } = given(more);
  return stackOf(id, c, { variant, on, label, ...flags }, list(...children), handlers, (el) => withEvents(el, { onPress, onRelease, onMenu, onMove, onWheel, onSize, onOver }), context);
});

// Dawn Mode's sky behind the lights: the Storybook's art in this theme's colours, layer by layer (built by build:ui-tokens),
// rising as the Storybook's keyframes say. `c.dawn.sky` carries the view's width, its run and whether it has started rising.
export const dawn = ({ id = "dawn" } = {}) => still((c) => dawnSky(id, c, c.dawn.sky ?? { rising: true }))({ id });

// The state patterns and the toast: the one action or fix takes `onClick`.
const pattern = (draw) => (props) => pressing((id, c, more) => {
  const { presses = {}, onClick = takeOf(presses, props.fix || props.action) } = given(more);
  return draw(id, c, { ...props, onClick });
});
export const emptyState = ({ icon = "", text, action = "" }) => pattern(stateEmpty)({ icon: appIcon(icon), text, action });
export const failureLine = ({ text, fix = "", detail = "" }) => pattern(stateLine)({ text, fix, detail });
export const failureBlock = ({ text, source = "", fix = "", agent = "" }) => pressing((id, c, more) => {
  const { presses = {}, onClick = takeOf(presses, fix) } = given(more);
  return stateBlock(id, c, { text, source, fix, onClick, agent, onExplain: agent ? takeOf(presses, `Explain to ${agent}`) : null });
});
// A press on the toast or its fix goes home.
export const toast = ({ icon = "none", ...props }) => pattern(drawToast)({ ...props, icon: iconOf(icon) });
export const skeletonOf = ({ shape, count }) => (id, c, more = {}) => {
  given(more);
  return drawSkeleton(id, c, { shape, count });
};

// The one number: its unit beside it, its facts (separated by |) on a quiet line under it. App only: `tone` and `tip` for the value.
export const metric = ({ value, unit = "", facts = "", loading = false, tone = "", tip = "" }) => (id, c, more = {}) => {
  given(more);
  return figure(id, c, { value, unit, facts, loading, tone, tip });
};

// `content`: kit pieces drawn in place of the prose body.
export const card = ({ content = [], ...props }) => (id, c, more = {}) => {
  given(more);
  return drawCard(id, c, { ...props, content: drawn(id, c, "content", content) });
};

export const code = (props) => (id, c, more = {}) => {
  given(more);
  return drawCode(id, c, props);
};

// A picture to pick: its press picks it. Proposed: `color`, its ground until the picture is drawn.
export const thumbnail = ({ image = "", label, selected = false, loading = false, color = "" }) => (id, c, more = {}) => {
  const { onClick = null } = given(more);
  return drawThumbnail(id, c, { image, label, selected, loading, color }, onClick);
};

// Prose in blocks, the `block`th (from 1) hovered or edited; `onLink` takes a link's press.
export const markdown = ({ source, block = 0, state = "rest" }) => (id, c, more = {}) => {
  const { onLink = null } = given(more);
  return drawMarkdown(id, c, { source, block, state }, { onLink });
};

// A block's words: `source` drawn as markdown, with no padding of their own; `onLink` takes a link's press.
export const markdownWords = ({ source = "" }) => (id, c, more = {}) => {
  const { onLink = null } = given(more);
  return drawMarkdownWords(id, c, { source }, { onLink });
};

// One block of a document. Proposed: `content`, drawn pieces in place of its formatted source (`markdownWords` for words). `onPress` takes a press on it (a double press edits it).
export const markdownBlock = ({ source = "", state = "rest", content = [] }) => (id, c, more = {}) => {
  const { onLink = null, onPress = null, onOpen = null } = given(more);
  return drawMarkdownBlock(id, c, { source, state, content: drawn(id, c, "content", content) }, { onLink, onPress, onOpen });
};

// The status bar's items: a press is named by the item's icon, else its mark, else its words; Needs you's by its mark. App only: `tip`.
const statusPress = (key, draw) => pressing((id, c, more) => {
  const { presses = {}, onClick = takeOf(presses, key) } = given(more);
  return draw(id, c, onClick);
});
export const statusItem = ({ icon = "", mark = "", text = "", tone = "", pending = false, open = false, tip = "" }) => statusPress(icon ? appIcon(icon) : mark || text,
  (id, c, onClick) => drawStatusItem(id, c, { icon: icon ? appIcon(icon) : null, mark: mark || null, text, tone: tone || null, pending, open, tip: tip || null, onClick }));
export const needsItem = ({ name, question = "", more = 0, tip = "" }) => statusPress("blocked",
  (id, c, onClick) => drawNeedsItem(id, c, { name, question: question || null, more, tip: tip || null, onClick }));

// Panes per view: `presses` and `focuses` by minus and plus, and the number's handle as value; `onClick` evens out, `onChange(i, cx)` goes to column i.
// App only: `chords`, the key table's chords for fewer, more and fit. Proposed: `columns`, the minimap.
export const stepper = ({ value = 2, open = false, hover = false, columns = [], chords = {} }) => pressing((id, c, more) => {
  const { presses = {}, focuses = {}, onClick = null, onChange = null, onHover = null } = given(more);
  const handles = Object.fromEntries(["minus", "plus", "value"].map((key) => [key, takeOf(focuses, key)]));
  return drawStepper(id, c, { value, open, hover, columns, chords },
    { minus: takeOf(presses, "minus"), plus: takeOf(presses, "plus"), value: onClick, column: onChange, hover: onHover, focuses: handles });
});

// Herdr's `.tooltip()` takes only a string, so the tooltip is its words: `.tooltip(tooltip({ label, detail, chord }))`.
// `chord` is the key table's chord ("cmd-shift-p", from ui-tooltip.js `boundChord`), written as this computer writes it. Anything else throws.
export const tooltip = ({ label, detail = "", chord = "", ...rest }) => {
  if (Object.keys(rest).length) throw new Error(`kit: a tooltip takes label, detail and chord, not ${Object.keys(rest).join(", ")}`);
  return tipText({ label, detail, chord });
};
