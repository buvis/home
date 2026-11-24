export const shapeNode = (classes, parent = null, tag = "span") => ({ tag, attrs: {}, classes: classes.filter(Boolean), parent, children: [] });
const BAR = shapeNode(["kanso-tab-bar"], null, "div");
export const listNode = ({ size, track, disabled, bar }) => shapeNode(["kanso-tabs", size !== "md" && `kanso-tabs--${size}`, track && "kanso-tabs--track", disabled && "kanso-control--off"],
  bar ? BAR : null, "div");
export const tabNode = (list, { on, square, armed, pending, held }) => shapeNode(["kanso-tabs__tab", on && "kanso-tabs__tab--on", square && "kanso-tabs__tab--icon",
  armed && "kanso-action--armed", pending && "kanso-state-line--pending", held && "kanso-control--held"], list);

export const TAB_PARTS = ["tab", "list", "label", "glyph", "dot", "close", "insertion"];
export const tabParts = (group, states) => {
  const list = listNode(group);
  const tab = tabNode(list, states);
  return {
    tab: [tab, states.live], list: [list, false], label: [shapeNode(["kanso-tabs__label"], tab), false], glyph: [shapeNode(["kanso-icon"], tab, "svg"), false],
    dot: [shapeNode(["kanso-tabs__dot"], tab, "i"), false], close: [shapeNode(["kanso-icon", "kanso-tabs__close"], tab, "svg"), !group.disabled],
    insertion: [shapeNode(["kanso-tabs__insertion"], list, "i"), false],
  };
};

const FLAGS = ["on", "square", "armed", "pending", "held"];
const flagged = ({ disabled }, flags) => {
  const states = Object.fromEntries(FLAGS.map((flag) => [flag, flags.includes(flag)]));
  return Object.freeze({ ...states, live: !disabled && !states.on && !states.armed && !states.held });
};
const AT_REST = [flagged({ disabled: false }, []), flagged({ disabled: true }, [])];
export const tabStates = (group, flags) => (flags.length ? flagged(group, flags) : AT_REST[group.disabled ? 1 : 0]);
const bit = (v) => (v ? 1 : 0);
export const tabKey = (group, states) => `${group.size}${bit(group.track)}${bit(group.disabled)}${bit(group.bar)}${bit(states.on)}${bit(states.square)}${bit(states.armed)}${bit(states.pending)}${bit(states.held)}`;

const subsets = (flags) => flags.reduce((all, flag) => [...all, ...all.map((set) => [...set, flag])], [[]]);
export const drawnTabs = () => [
  ...[false, true].flatMap((disabled) => subsets(["on", "armed", "pending", "held"]).map((flags) => [{ size: "md", track: false, disabled, bar: true }, flags])),
  ...["sm", "md", "lg"].flatMap((size) => [true, false].flatMap((track) => [false, true].flatMap((disabled) => subsets(["on", "square"])
    .map((flags) => [{ size, track, disabled, bar: false }, flags])))),
].map(([group, flags]) => [group, tabStates(group, flags)]);
