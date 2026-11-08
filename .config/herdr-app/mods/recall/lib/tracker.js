// The tracker's window: what Recall asks Herdr for, and whether an open one
// was asked for the same way.

/**
 * The tracker's width and height, in px. Herdr reads an overlay size of 1 or
 * less as a share of its own window, so at 1 the tracker lay over all of it,
 * unseen, and took the clicks and scrolls meant for what was under it.
 */
export const TRACKER_SIZE = 2;

/** The overlay Recall opens for its tracker: a frameless window Herdr keeps and reopens on its next start. */
export function trackerWindow(mod) {
  return { mod, kind: "window", key: "recall-tracker", keep: true, frame: "none", width: TRACKER_SIZE, height: TRACKER_SIZE, at: { x: 0, y: 0 }, props: { role: "tracker", size: TRACKER_SIZE } };
}

/**
 * Whether a tracker opened with these props has today's size. Herdr reopens
 * a kept window as it was last opened, so one kept by an earlier version
 * comes back at that version's size until it is opened again.
 */
export function isCurrentTracker(props) {
  return props?.size === TRACKER_SIZE;
}
