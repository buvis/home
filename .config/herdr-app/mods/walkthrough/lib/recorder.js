// Recording an agent's turns without hooks, for agents that have none (pi,
// codex, opencode): while a walkthrough is open, their sessions in the
// repository are looked at every few seconds. A new prompt starts a turn (a
// snapshot of the working tree); the turn ends once the agent's sessions and
// the working tree have both been still for a while. Plain decisions over what
// was seen; the snapshots and the looking are turnview.js's and engine.js's.

// How often the sessions are looked at: the start snapshot of a turn is taken
// up to this long after its prompt was sent.
export const RECORD_EVERY = 3000;
// A turn ends once nothing was written (by the agent to its session, or to the
// working tree) for this long. Agent turns often run for minutes; a long
// thought or a slow test keeps writing to the session.
export const RECORD_QUIET = 60_000;
// A new prompt sent this soon after the last activity ends the turn before it
// as interrupted: the agent was still at it.
export const RECORD_SETTLE = 10_000;
// Session files written in this window are looked at; anything older can't hold a new prompt.
export const RECORD_LOOKBACK = 120_000;

/**
 * A new recorder's state. Prompts sent before `now` are not recorded: they
 * were sent with no walkthrough open, and the tree they started from is gone.
 */
export const recorderState = (now = Date.now()) => ({ seenAt: now, lastActivity: now, turn: null });

/**
 * What one look decides, from the prompts seen (`at` ms, `text`, `session`),
 * when the agents' sessions last wrote (`active`) and when the working tree
 * last changed (`treeAt`):
 *   end:   { interrupted } when the open turn ends now, else null
 *   start: { prompt, session, started } when a turn starts now, else null
 * and the state to keep (seenAt, lastActivity). Several prompts seen at once
 * make one turn: they share one snapshot, so a turn each would be empty.
 */
export function recorderStep(state, { prompts = [], active = 0, treeAt = 0, now = Date.now() }) {
  const fresh = prompts.filter((p) => p.at > state.seenAt).sort((a, b) => a.at - b.at);
  if (fresh.length) {
    // The activity seen before this prompt: the agent was still working if it is close to it.
    const end = state.turn ? { interrupted: fresh[0].at - state.lastActivity < RECORD_SETTLE } : null;
    return {
      end,
      start: { prompt: fresh.map((p) => p.text).join("\n\n"), session: fresh[fresh.length - 1].session ?? null, started: fresh[0].at },
      seenAt: fresh[fresh.length - 1].at,
      lastActivity: Math.max(now, active, treeAt),
    };
  }
  const lastActivity = Math.max(state.lastActivity, active, treeAt);
  const quiet = state.turn && now - Math.max(lastActivity, state.turn.started) > RECORD_QUIET;
  return { end: quiet ? { interrupted: false } : null, start: null, seenAt: state.seenAt, lastActivity };
}

/** Since when to read prompts on a look: just after the last one seen, but no further back than the window. */
export const lookSince = (state, now = Date.now()) => Math.max(state.seenAt + 1, now - RECORD_LOOKBACK);
