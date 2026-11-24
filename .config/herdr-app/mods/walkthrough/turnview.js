// The Last turn tab: the turns hooks/turn.sh recorded (or the recorder, for
// agents with no hooks), which one is shown, and the walkthroughs written for
// them without a click. Kept beside view.js; each function takes the
// walkthrough view it works for.

import { div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { agents, notify, settings, watchFolder } from "herdr";
import { turnSource, pickTurn, keepTurn, lastFinished, isOpen, autoWritable, firstLine, ago, hookSettings, HOOK_WAIT } from "./lib/turns.js";
import { recorderState, recorderStep, lookSince, RECORD_EVERY } from "./lib/recorder.js";
import { AUTO_MODEL } from "./lib/job.js";
import { turnsFolder, listTurns, closeTurn, readDiff, readPreferences, keyFor, hasEntry, jobOf, preparePrompt, fits, startJob, finished, finishJob, copyText, hookScript, startTurn, endTurn, agentSessions, claimRecorder } from "./engine.js";
import { button, formatElapsed } from "./ui.js";

// Written without a click only by the cheapest model, and only for a change small enough to be cheap.
export const AUTO_MAX_HUNKS = 300;
export const AUTO = [
  { key: "on-open", name: "While open", about: "When an agent's turn ends, and on opening, write its walkthrough with the cheapest model (300 hunks at most)" },
  { key: "off", name: "Off", about: "Only when you press Generate" },
];
export const DEFAULT_AUTO = "on-open";
export const autoOf = (key) => AUTO.find((a) => a.key === key) ?? AUTO[0];

/** The repository's turns folder is found and watched; the newest turn is picked. */
export async function startTurns(v, cx) {
  v.turnsDir = await turnsFolder(v.repo.top);
  await loadTurns(v);
  if (!v.turnsDir) return;
  cx.spawn(async () => {
    for (;;) {
      await watchFolder(v.turnsDir);
      v.turnsDirty = true;
    }
  });
}

/**
 * Records the turns of agents with no hooks (pi, codex, opencode) while this
 * walkthrough is open and recording is on (lib/recorder.js). Claude Code's
 * sessions are left to its hooks, so a prompt is never recorded twice; of two
 * walkthroughs open on one repository, one records (engine.js claimRecorder).
 */
export function startRecorder(v, cx) {
  v.rec = { ...recorderState(), owner: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`, busy: false, mine: false };
  cx.timer.every(RECORD_EVERY, (cx) => cx.spawn(async (cx) => {
    // A look can outlast the interval on a large repository: the next one waits its turn instead of racing it.
    if (v.rec.busy || !v.record || !v.repo || !v.turnsDir) return;
    v.rec.busy = true;
    try { await recordTick(v, cx); } catch { /* the next look tries again */ } finally { v.rec.busy = false; }
  }));
}

async function recordTick(v, cx) {
  const r = v.rec, top = v.repo.top, now = Date.now();
  if (!await claimRecorder(v.turnsDir, r.owner)) { r.mine = false; r.turn = null; return; }
  if (!r.mine) {
    // Recording starts here: a turn a closed walkthrough left open never saw its end.
    r.mine = true;
    Object.assign(r, recorderState(now));
    for (const t of v.turns.filter((t) => t.recorded && isOpen(t))) await endTurn(top, t, { interrupted: true }).catch(() => undefined);
    return;
  }
  const { prompts, active } = await agentSessions(top, lookSince(r, now));
  const step = recorderStep(r, { prompts, active, treeAt: v.treeChangedAt ?? 0, now });
  r.seenAt = step.seenAt;
  r.lastActivity = step.lastActivity;
  let ended = null;
  if (step.end && r.turn) {
    await endTurn(top, r.turn, step.end).catch(() => undefined);
    if (!step.end.interrupted) ended = r.turn.id;
    r.turn = null;
  }
  if (step.start) r.turn = await startTurn(v.turnsDir, top, step.start).catch(() => null);
  if (!step.end && !step.start) return;
  if (await loadTurns(v) && v.scope === "turn") await v.reload(cx);
  // A turn that ended on its own is written up as a Stop hook's would be.
  const turn = ended && v.turns.find((t) => t.id === ended);
  if (turn) await autoGenerate(v, cx, turn);
  cx.notify();
}

/** Turns recording off ends the turn it has open, as interrupted: its end wasn't seen. */
export async function stopRecorder(v) {
  const r = v.rec;
  if (!r) return;
  r.mine = false; // turned on again, it starts afresh: prompts sent while it was off aren't recorded
  if (!r.turn || !v.repo) return;
  const turn = r.turn;
  r.turn = null;
  await endTurn(v.repo.top, turn, { interrupted: true }).catch(() => undefined);
  v.turnsDirty = true;
}

/**
 * Lists the turns again. The one picked by hand stays picked; otherwise the
 * newest (of the terminal the walkthrough opened over) is. Returns whether the
 * shown turn is another one now, or the same one in another state.
 */
export async function loadTurns(v) {
  v.turnsDirty = false;
  v.turnsRead = Date.now();
  const ends = { idleSince: (terminal) => idleSince(v, terminal) };
  let turns = await listTurns(v.turnsDir, ends);
  // A turn no Stop hook ended, whose agent has gone quiet, stops following the working tree here.
  const stale = turns.filter((t) => t.state === "stale");
  if (stale.length && v.repo) {
    for (const t of stale) await closeTurn(v.repo.top, t).catch(() => undefined);
    turns = await listTurns(v.turnsDir, ends);
  }
  const before = v.turn;
  v.turns = turns;
  ({ turn: v.turn, pinned: v.turnPinned } = keepTurn(turns, before, v.turnPinned, v.from));
  return before?.id !== v.turn?.id || before?.state !== v.turn?.state || before?.endTree !== v.turn?.endTree;
}

/**
 * Since when the agent in a terminal has not been working: null while it
 * works or waits on the person, the time it was first seen otherwise (gone
 * from agents() counts: it was quit).
 */
function idleSince(v, terminal) {
  v.idle ??= new Map();
  const a = agents().find((x) => x.address === terminal);
  if (a && (a.status === "working" || a.status === "blocked")) { v.idle.delete(terminal); return null; }
  if (!v.idle.has(terminal)) v.idle.set(terminal, Date.now());
  return v.idle.get(terminal);
}

/** The toolbar's turn dropdown face. */
export const turnLabel = (v) => (v.turn ? firstLine(v.turn.prompt, 48) || "(empty prompt)" : "Pick a turn");

function stateOf(t) {
  if (t.state === "running") return "still running";
  if (t.state === "stale") return "no end recorded";
  if (t.frozen) return "no Stop recorded, ended when seen idle";
  if (t.state === "interrupted") return "interrupted";
  return t.ended ? `took ${formatElapsed(t.ended - t.started)}` : "finished";
}

export const turnItems = (v) => v.turns.map((t) => ({
  label: firstLine(t.prompt, 72) || "(empty prompt)",
  hint: [ago(t.started), stateOf(t), t.terminal].filter(Boolean).join(" · "),
  right: isOpen(t) ? "running" : "",
  value: t, selected: t.id === v.turn?.id,
}));

/** A turn picked from the dropdown stays picked, unless it is the one that would be picked anyway. */
export function chooseTurn(v, turn) {
  v.turn = turn;
  v.turnPinned = turn.id !== pickTurn(v.turns, v.from)?.id;
}

/**
 * The once-a-second part: a turns folder that changed is listed again, an
 * agent of this tab that stopped working has its turn written up, and
 * walkthroughs written in the background are stored and announced.
 */
export async function turnTick(v, cx) {
  // An open turn can go stale with no file changing: its agent was quit. Looked at every 15 seconds.
  const due = v.turns.some(isOpen) && Date.now() - (v.turnsRead ?? 0) > 15_000;
  if ((v.turnsDirty || due) && await loadTurns(v) && v.scope === "turn") await v.reload(cx);
  if (v.auto !== "off") {
    if (agentStopped(v)) v.autoWanted = Date.now();
    if (v.autoWanted) {
      // The Stop hook writes the turn's end a moment after the agent reports it is done.
      const turn = lastFinished(v.turns, agents().filter((a) => a.tab === v.tab).map((a) => a.address));
      if (turn && turn.ended >= v.autoWanted - 60_000) { v.autoWanted = null; await autoGenerate(v, cx, turn); }
      else if (Date.now() - v.autoWanted > HOOK_WAIT) v.autoWanted = null;
    }
  }
  for (const b of [...v.background]) {
    const done = await finished(b.job);
    // Still running, unless the view took the answer itself (the turn was shown) and the folder is gone.
    if (!done && Date.now() < b.job.meta.deadline + 10_000 && await jobOf(v.repo, b.job.meta.sk)) continue;
    v.background = v.background.filter((x) => x !== b);
    if (!done) continue; // run.sh stopped it; the folder is cleared the next time that turn is opened
    try {
      // null: the view itself (or another window) took the answer, and says so.
      if (await finishJob(done)) announce(b.job.meta.source);
    } catch (e) {
      notify({ title: "Walkthrough", body: `Couldn't write the walkthrough of "${firstLine(b.job.meta.source?.prompt, 60)}": ${String(e?.message ?? e)}`, level: "warning" });
    }
    if (v.diff?.sk === done.meta.sk) await v.reload(cx);
  }
}

/** In a pane only: whether an agent in this tab has just stopped working. */
function agentStopped(v) {
  if (v.inDialog || !v.tab) return false;
  let stopped = false;
  for (const a of agents().filter((x) => x.tab === v.tab)) {
    if (v.statuses.get(a.address) === "working" && (a.status === "done" || a.status === "idle")) stopped = true;
    v.statuses.set(a.address, a.status);
  }
  return stopped;
}

/** `source`: the turn's source, as its job keeps it. */
export function announce(source) {
  notify({ title: "Walkthrough ready", body: `Last turn: "${firstLine(source?.prompt, 60) || "(empty prompt)"}"`, level: "success" });
}

/**
 * Writes the walkthrough of a finished turn that has none yet, with the
 * backend's cheapest model, in the background. Once per turn per open walkthrough; never past
 * AUTO_MAX_HUNKS, where Generate is waited for.
 */
export async function autoGenerate(v, cx, turn) {
  if (v.auto === "off" || !v.cli || !v.repo || !autoWritable(turn) || v.autoTried.has(turn.id)) return;
  v.autoTried.add(turn.id);
  try {
    const source = turnSource(turn);
    const diff = await readDiff(v.repo, source);
    if (!diff.hunkCount || diff.hunkCount > AUTO_MAX_HUNKS) return;
    // Matched against the turn's prompt, as a click on Generate would be: the same task, the same key.
    const [preferences, task] = await Promise.all([readPreferences(), v.taskFor(source)]);
    // One by the model picked here counts too: it is the one that would be shown.
    const autoModel = AUTO_MODEL[v.backend] ?? AUTO_MODEL.claude;
    const key = keyFor(v.repo, diff, autoModel, v.language, preferences, task);
    if (await hasEntry(key) || await hasEntry(keyFor(v.repo, diff, v.model, v.language, preferences, task))) return;
    // One written before tasks were matched (or with the task off) is shown with a Regenerate banner; it isn't paid for twice unasked.
    if (task && (await hasEntry(keyFor(v.repo, diff, autoModel, v.language, preferences)) || await hasEntry(keyFor(v.repo, diff, v.model, v.language, preferences)))) return;
    if (await jobOf(v.repo, diff.sk)) return;
    const prompt = preparePrompt(diff, { language: v.language, previous: null, preferences, task });
    if (!fits(prompt)) return;
    const job = await startJob(v.repo, diff, { key, model: autoModel, language: v.language, prompt, source, auto: true, task });
    // Followed here as well as by the view while the turn is shown, so switching away doesn't orphan it.
    v.background.push({ job });
    if (v.diff?.sk === diff.sk) v.setJob(job);
  } catch {
    // A turn that can't be read now is read when it is opened, with its error.
  }
  cx.notify();
}

/**
 * The Last turn tab before any turn was recorded: Claude Code's hooks, set up
 * in three steps, or, for agents with no hooks, recording while it is open.
 */
export function hookHelp(v, t) {
  // One line per hook, as the README shows them; Copy settings copies exactly what is shown.
  const snippet = hookSettings(hookScript(), { compact: true });
  const font = settings().font_family ?? "JetBrains Mono";
  const step = (n, title, ...body) => h_flex().w_full().px(14).py(12).gap(12).items_start().when(n > 1, (e) => e.border_t(1).border_color(t.border))
    .child(div().flex_none().size(22).rounded(11).bg(t.accent + "26").flex().items_center().justify_center().text_size(11.5).font_semibold().text_color(t.accent).child(String(n)))
    .child(v_flex().flex_1().min_w(0).gap(6).child(div().text_size(13).font_semibold().child(title)).children(body));
  const small = (text) => div().text_size(12).line_height(1.5).text_color(t.muted).child(text);
  return v_flex().id("turn-help").size_full().overflow_y_scrollbar().items_center().p(28)
    .child(v_flex().w_full().max_w(620).gap(12)
      .child(div().text_size(18).font_semibold().child("Record the agent's turns"))
      .child(div().text_size(13).line_height(1.5).text_color(t.muted).child("Last turn shows exactly what an agent changed while answering one prompt. Two Claude Code hooks take a snapshot of your working tree, outside the repository's .git, when you send a prompt and when the agent stops."))
      .child(v_flex().w_full().rounded(10).border_1().border_color(t.border)
        .child(step(1, "Copy the two hooks",
          // A line longer than the box wraps under its own indent instead of spilling out of it.
          v_flex().w_full().min_w(0).p(10).rounded(8).border_1().border_color(t.border).bg(t.raised).font_family(font).text_size(11)
            .children(snippet.split("\n").map((line) => {
              const indent = /^ */.exec(line)[0].length;
              return div().w_full().min_w(0).pl(indent * 7).child(line.trimStart() || " ");
            })),
          h_flex().gap(10).items_center()
            .child(button(t, "copy-hooks", "Copy settings", (_e, cx) => cx.spawn(async (cx) => {
              try { await copyText(snippet); v.flash("✓ Copied"); } catch (e) { v.flash(`Couldn't copy: ${String(e?.message ?? e)}`); }
              cx.notify();
            }), { kind: "solid", small: true }))
            .when(Boolean(v.sent), (e) => e.child(div().text_size(11.5).text_color(v.sent.startsWith("✓") ? t.ansi2 : t.dim).child(v.sent)))))
        .child(step(2, "Add them to ~/.claude/settings.json", small("Next to any hooks you already have. The walkthrough never edits your settings itself.")))
        .child(step(3, "Send your agent a prompt", small("Turns are recorded from then on. Snapshots go to ~/.herdr/walkthrough/turns/; the newest 20 per repository are kept."))))
      .child(div().mt(10).text_size(14).font_semibold().child("Using pi, codex or opencode?"))
      .child(div().text_size(13).line_height(1.5).text_color(t.muted).child("They have no hooks to install. Instead, while this walkthrough is open, it can read their sessions in this repository and take the same snapshots itself: when a prompt appears, and once the agent and the working tree have been still for a minute. Claude Code's sessions are left to the hooks above."))
      .child(h_flex().gap(10).items_center()
        .child(button(t, "toggle-record", v.record ? "● Recording" : "Record while open", (_e, cx) => v.choose("record", !v.record, cx), { kind: v.record ? "soft" : "outline", small: true }))
        .child(small(v.record ? "Send your agent a prompt. A prompt sent with the walkthrough closed isn't recorded." : "Off until you turn it on."))));
}
