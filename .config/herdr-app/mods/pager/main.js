import { View, div } from "gpui-kit";
import { agents, terminals, exec, theme, appHome } from "herdr";
const STORAGE = "episodes-v1";
const RETRY_MS = 30000;
const MAX_ATTEMPTS = 3;

export default class Pager extends View {
  init() {
    try { this.episodes = JSON.parse(localStorage.getItem(STORAGE) || "{}"); }
    catch { this.episodes = {}; }
    if (!this.episodes || typeof this.episodes !== "object" || Array.isArray(this.episodes)) this.episodes = {};
    this.pending = new Set();
    this.started = false;
  }

  save() {
    localStorage.setItem(STORAGE, JSON.stringify(this.episodes));
  }

  observe(cx) {
    const now = Date.now();
    const listed = new Map(agents().map(a => [a.address, a]));
    const all = terminals().filter(t => t.state === "live");
    const included = new Set(all.filter(t => listed.has(t.address) || t.labels?.["herdr.space"]).map(t => t.address));
    // Include children of Herdr terminals, but not unrelated core terminals.
    let previous;
    do {
      previous = included.size;
      for (const t of all) if (included.has(t.parent)) included.add(t.address);
    } while (previous !== included.size);

    let dirty = false;
    this.current = new Set();
    for (const terminal of all) {
      if (!included.has(terminal.address)) continue;
      const agent = listed.get(terminal.address);
      const status = agent?.status ?? terminal.status;
      const blocked = status === "blocked" || status === "error";
      const done = !terminal.parent && status === "done";
      const key = `${terminal.address}:${terminal.created_ms ?? ""}`;
      this.current.add(key);
      let episode = this.episodes[key];
      const turn = terminal.turn ?? 0;
      if (!episode || episode.blocked !== blocked || Boolean(episode.done) !== done || episode.turn !== turn) {
        episode = { blocked, done, turn, updated: now };
        this.episodes[key] = episode;
        dirty = true;
      }
      const name = agent?.program?.name || terminal.program?.name || agent?.app || terminal.address;
      const place = agent?.space_name || terminal.labels?.where || terminal.address;
      const message = `${name} ${blocked ? "needs you" : "finished"} in ${place} (${terminal.address}). Open Herdr to respond.`;
      if (blocked || done) {
        // Preserve successful alerts from the former two-channel implementation.
        episode.delivery ??= { attempts: 0, sent: Boolean(episode.sent || episode.desktop?.sent), next: 0 };
        this.deliver(key, episode.delivery, message, cx, blocked);
      }
    }
    // Keep absent terminals briefly: an empty snapshot on reconnect must not resend alerts.
    for (const [key, episode] of Object.entries(this.episodes)) {
      if (!this.current.has(key) && now - episode.updated > 7 * 86400000) {
        delete this.episodes[key];
        dirty = true;
      }
    }
    if (dirty) this.save();
  }

  deliver(key, episode, message, cx, blocked) {
    if (episode.sent || episode.attempts >= MAX_ATTEMPTS || Date.now() < episode.next || this.pending.has(key)) return;
    this.pending.add(key);
    episode.attempts += 1;
    episode.next = Date.now() + RETRY_MS;
    this.save();
    cx.spawn(async cx => {
      let ok = false;
      try {
        const title = blocked ? "Herdr: agent needs you" : "Herdr: agent finished";
        const result = await exec("python3", ["-B", `${appHome()}/mods/pager/sender.py`, title, message]);
        ok = result.code === 0;
        try { episode.lastDelivery = JSON.parse(result.stdout); } catch { /* No diagnostic on a failed launch. */ }
      } catch { /* Show a failure without logging credentials or process output. */ }
      this.pending.delete(key);
      episode.sent = ok;
      this.save();
      cx.notify();
    });
  }

  render(cx) {
    if (!this.started) {
      this.started = true;
      // This timer only retries failed deliveries; live data triggers observation.
      cx.timer.every(RETRY_MS, cx => {
        this.observe(cx);
        cx.notify();
      });
    }
    this.observe(cx);
    const failures = Object.entries(this.episodes).flatMap(([key, e]) => {
      if (!this.current.has(key)) return [];
      return [[key, e.blocked || e.done ? e.delivery : null]]
        .filter(([id, state]) => state && !state.sent && state.attempts > 0 && !this.pending.has(id));
    });
    const label = this.pending.size ? "Alerts · sending…" : failures.length ? "Alerts · delivery failed · click to retry" : "Alerts · phone when away";
    const t = theme();
    return div().id("pager").size_full().px(12).flex().items_center().text_size(11)
      .bg(t.chrome).text_color(failures.length ? t.blocked : t.muted)
      .tooltip("Needs you or finished: desktop when present; phone after 5 minutes idle, with screensaver active, or lid below 70°. Active while this layout is open.")
      .on_click((_event, cx) => {
        for (const [, e] of failures) { e.attempts = 0; e.next = 0; }
        this.save();
        this.observe(cx);
        cx.notify();
      }).child(label);
  }
}
