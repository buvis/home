// Kanso's panel kit: facts as words, the Storybook's diffText, facts and plus. Apache-2.0.
// Kept byte for byte by `npm run sync:share`: edit kanso-panel/ui-facts.js. It imports nothing, so a model may use it.

/** Lines added and removed, as git says them. */
export const diffText = ({ add = 0, del = 0 }) => `+${Number(add)} −${Number(del)}`;
/** Facts on one line, the way a tooltip lists what was folded away. */
export const facts = (...parts) => parts.filter(Boolean).join(" · ");
/** A count of what is folded away, such as +3. */
export const plus = (count) => `+${count}`;
/** A metric's `facts` from a list of `{ value, unit }`: each its value and its unit, separated by |. */
export const factList = (list) => list.filter(Boolean).map(({ value, unit }) => [value, unit].filter(Boolean).join(" ")).join(" | ");
