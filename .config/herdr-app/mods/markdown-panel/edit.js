// One save for a text file and a Markdown note: edited, saving, saved, conflict, failed. The read guarantee is 1 MiB of bytes.
export const EDIT_LIMIT = 1048576;

export const byteLength = (text) => [...String(text ?? "")].reduce((n, ch) => {
  const cp = ch.codePointAt(0);
  return n + (cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4);
}, 0);

export const tooBig = (text) => byteLength(text) > EDIT_LIMIT;

export const overRead = (error) => /exceeds 1 MiB/i.test(String(error?.message ?? error));

export const wholeText = (size, text) => (size != null && Number(size) > EDIT_LIMIT) || (text != null && byteLength(text) > EDIT_LIMIT)
  ? { big: true } : { text };

export const tooLarge = () => ({ saved: null, text: null, phase: "clean", disk: null, note: null, big: true });

export const draftKey = (path, on) => `${on ?? ""}\0${path}`;

export class DraftBook {
  constructor() { this.rows = new Map(); }

  peek(key) { return this.rows.get(key) ?? null; }

  put(key, draft) { this.rows.set(key, draft); }

  drop(key) { this.rows.delete(key); }
}

export const drafts = new DraftBook();

export const remember = (book, key, state) => {
  if (!book || !key || !state || state.text == null || state.big) return;
  const current = book.peek(key);
  if (state.text === state.saved) {
    if (!current || current.text === state.text) book.drop(key);
    return;
  }
  book.put(key, { text: state.text, saved: state.saved });
};

export const opened = (text) => ({ saved: text, text, phase: "clean", disk: null, note: null, big: tooBig(text) });

export const restore = (draft) => ({
  saved: draft.saved, text: draft.text, phase: draft.text === draft.saved ? "clean" : "edited", disk: null, note: null, big: tooBig(draft.text),
});

export const typed = (state, text) => {
  if (!state || state.big) return state;
  if (state.phase === "conflict" || state.phase === "saving") return { ...state, text };
  return { ...state, text, phase: text === state.saved ? "clean" : "edited", note: null };
};

export const beginSave = (state) => {
  if (!state || state.big || state.phase === "conflict" || state.phase === "saving") return null;
  if (state.text == null || state.text === state.saved) return null;
  return { ...state, phase: "saving", note: null };
};

export const didSave = (state, written) => ({
  ...state, saved: written, phase: state.text === written ? "saved" : "edited", disk: null, note: state.text === written ? "Saved" : null,
});

export const didFail = (state, note) => ({ ...state, phase: "failed", note: note || "Could not save" });

export const didConflict = (state, disk) => ({ ...state, phase: "conflict", disk, note: null });

export const keepMine = (state) => {
  if (state?.phase !== "conflict") return state;
  return { ...state, saved: state.disk, phase: state.text === state.disk ? "clean" : "edited", disk: null, note: null };
};

export const takeTheirs = (state) => {
  if (state?.phase !== "conflict") return state;
  return { ...state, text: state.disk, saved: state.disk, phase: "clean", disk: null, note: null, big: tooBig(state.disk) };
};

export const seenDisk = (state, disk) => {
  if (!state) return opened(disk);
  if (state.phase === "conflict") return state.disk === disk ? state : { ...state, disk };
  if (state.text === state.saved) return state.saved === disk ? state : opened(disk);
  if (disk === state.saved) return state;
  return didConflict(state, disk);
};

export const word = (state) => {
  if (!state) return "";
  if (state.big) return "Too large to edit";
  if (state.phase === "saving") return "Saving…";
  if (state.phase === "failed") return state.note || "Could not save";
  if (state.phase === "edited") return "Edited";
  if (state.phase === "saved") return "Saved";
  return "";
};

export const needsSave = (state) => Boolean(state) && !state.big && state.phase !== "conflict" && state.phase !== "saving" && state.text != null && state.text !== state.saved;

export const commitText = async (state, io) => {
  const saving = state?.phase === "saving" ? state : beginSave(state);
  if (!saving || saving.text == null || saving.text === saving.saved) return { ran: false, written: null, result: null };
  const written = saving.text, expected = saving.saved;
  try {
    await io.put(written, expected);
    return { ran: true, written, result: { ok: true } };
  } catch (error) {
    if (io.quiet?.(error)) return { ran: true, written, result: { note: io.note?.(error) ?? "Could not save" } };
    const disk = await Promise.resolve(io.read()).catch(() => null);
    if (disk !== null && disk !== expected) return { ran: true, written, result: { conflict: true, disk } };
    return { ran: true, written, result: { note: io.note?.(error) ?? "Could not save" } };
  }
};

export const applied = (latest, written, result) => {
  if (!result || !latest) return latest;
  if (result.ok) return didSave(latest, written);
  if (result.conflict) return didConflict(latest, result.disk);
  return didFail(latest, result.note);
};
