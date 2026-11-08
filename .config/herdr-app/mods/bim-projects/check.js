// Parser and consistency checks for bim project notes. Pure: no Herdr imports, so
// `node test.mjs` can run it against the vault.

// Quiet-day limits from the vault's review rules (20250122222850): now/next/wait items are reviewed
// after 2 months, someday items after 4. A project is "parked" when all its open actions are later/someday.
export const STALE_DAYS = { active: 60, parked: 120 };
// Names a #gtd/wait task may use without a contact link are private: they live in the
// vault's .bim-projects-ignored.json (kept identical to "List missing contacts") and
// reach check() as ignoredNames.
// From notes/system/templates/page.create-project.tpl.
const SECTIONS = ["Description", "Log", "Plan", "Solution"];
const PLACEHOLDER = { Description: "One paragraph summarizing the problem statement.", Solution: "Describe what was done to get project closure acceptance." };
// From "Review GTD projects actions" (notes/20250119193658): a task the review can see.
const GTD_LINE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) - (.*?) => (.*?) \| (#gtd\/\S+.*)$/;
export const KINDS = {
  "no-action": "No next action", untagged: "Untagged task", format: "Task format", "multi-gtd": "Several GTD tags",
  undated: "Undated", contact: "Unlinked contact", overdue: "Overdue", stale: "Quiet",
  "done-open": "Done, open tasks", template: "Template text", sections: "Missing section", frontmatter: "Frontmatter",
};
export const SOFT = new Set(["overdue", "stale"]);
export const localDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function parseFrontmatter(text) {
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(text), fm = {};
  if (!m) return { fm, body: text };
  let key = null;
  for (const line of m[1].split("\n")) {
    const kv = /^([\w-]+):\s*(.*)$/.exec(line), item = /^\s+-\s+(.*)$/.exec(line);
    if (kv) {
      key = kv[1];
      const v = kv[2].trim();
      fm[key] = v === "" ? [] : v.startsWith("[") ? v.slice(1, -1).split(",").map((s) => s.trim()).filter(Boolean) : v.replace(/^"(.*)"$/, "$1");
    } else if (item && Array.isArray(fm[key])) fm[key].push(item[1].trim());
  }
  return { fm, body: text.slice(m[0].length) };
}

function parseTask(status, text, section, line) {
  const m = GTD_LINE.exec(text), dates = {};
  for (const d of text.matchAll(/(📅|⏳|🛫|✅|❌)\s*(\d{4}-\d{2}-\d{2})/g)) dates[d[1]] = d[2];
  return { open: status === " ", text, section, line, gtd: text.match(/#gtd\/[\w/-]+/g) || [], dates, action: m ? m[3] : null, wellFormed: Boolean(m) };
}

export function parseNote(path, text) {
  const { fm, body } = parseFrontmatter(text), lines = body.split("\n"), sections = {}, tasks = [];
  // Task line numbers are file lines, so count the frontmatter lines the body skips.
  const skipped = text.slice(0, text.length - body.length).split("\n").length - 1;
  let section = "";
  const stack = []; // enclosing tasks by indentation: { indent, tagged }
  lines.forEach((l, i) => {
    const h = /^## (.+)$/.exec(l);
    if (h) { section = h[1].trim(); sections[section] = []; stack.length = 0; return; }
    if (section) sections[section].push(l);
    const t = /^(\s*)- \[(.)\] (.*)$/.exec(l);
    if (!t) return;
    const indent = t[1].length;
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    const task = parseTask(t[2], t[3], section, i + 1 + skipped);
    // Like the vault's "List open tasks without tags" (20250122104052): a sub-step is covered by a tagged parent.
    task.inherited = stack.some((s) => s.tagged);
    stack.push({ indent, tagged: task.gtd.length > 0 });
    tasks.push(task);
  });
  const title = fm.title || (lines.find((l) => l.startsWith("# ")) || "").slice(2) || path.split("/").pop().replace(/\.md$/, "");
  const tags = Array.isArray(fm.tags) ? fm.tags : fm.tags ? [fm.tags] : [];
  return { path, id: fm.id || "", title, tags, completed: fm.completed === "true", fm, sections, tasks, lower: `${title} ${text}`.toLowerCase() };
}

// Triage rewrites behind main.js's c and s keys. Pure, so test.mjs can check them.
export function completeNote(text, today) {
  const fm = /^completed:.*$/m.test(text) ? text.replace(/^completed:.*$/m, "completed: true") : text.replace(/\n---\n/, "\ncompleted: true\n---\n");
  return fm.replace(/^(\s*- )\[ \] (.*?)[ \t]*$/gm, `$1[-] $2 ❌ ${today}`);
}

export function parkNote(text, stamp) {
  const retagged = text.replace(/^\s*- \[ \] .*$/gm, (l) => l.replace(/#gtd\/(act\/\w+|wait)\b/g, "#gtd/act/someday").replace(/[ \t]*(📅|⏳|🛫)[ \t]*\d{4}-\d{2}-\d{2}/g, ""));
  return retagged.replace(/^## Log\n\n?/m, (h) => `${h}- [i] ${stamp} - parked during review\n`);
}

export function rescheduleNote(text, today) {
  const week = new Date(Date.parse(today) + 7 * 864e5).toISOString().slice(0, 10);
  return text.replace(/^\s*- \[ \] .*$/gm, (l) => l.replace(/(📅|⏳)(\s*)(\d{4}-\d{2}-\d{2})/g, (m, mark, sp, d) => (d < today ? `${mark}${sp}${week}` : m)));
}

export function check(p, today, ignoredNames = []) {
  const issues = [], add = (kind, msg, task) => issues.push({ kind, msg, task });
  const open = p.tasks.filter((t) => t.open), log = open.filter((t) => t.section === "Log");
  if (p.fm.completed === undefined) add("frontmatter", "no `completed` property");
  if (!p.fm.title) add("frontmatter", "no `title` property");
  for (const s of SECTIONS) if (!(s in p.sections)) add("sections", `no "## ${s}" section`);
  if (!p.completed && p.sections.Description?.some((l) => l.trim() === PLACEHOLDER.Description)) add("template", "Description still holds the template text");
  if (p.completed && p.sections.Solution?.some((l) => l.trim() === PLACEHOLDER.Solution)) add("template", "Solution still holds the template text");
  if (p.completed && open.length) add("done-open", `completed, but ${open.length} task(s) still open`);
  if (!p.completed && !open.some((t) => t.gtd.length)) add("no-action", "open project without an open #gtd action");
  for (const t of log) {
    if (!t.gtd.length) { if (!t.inherited) add("untagged", "Log task without a #gtd tag", t); }
    else if (!t.wellFormed) add("format", "not `YYYY-MM-DD HH:mm - context => action | #gtd/...`, the review query skips it", t);
    if (["#gtd/act/now", "#gtd/wait"].includes(t.gtd[0]) && !t.dates["📅"] && !t.dates["⏳"] && !t.dates["🛫"]) add("undated", `${t.gtd[0]} without 📅, ⏳ or 🛫, so the daily note never shows it`, t);
  }
  for (const t of open) {
    if (t.gtd.length > 1) add("multi-gtd", `${t.gtd.join(" ")}`, t);
    const who = t.gtd.includes("#gtd/wait") && t.action ? /^(.*?)\s+will\b/.exec(t.action)?.[1] : null;
    if (who && !who.startsWith("[[") && !ignoredNames.includes(who)) add("contact", `"${who}" is not a [[notes/contact/...]] link`, t);
    const due = t.dates["📅"], when = t.dates["⏳"];
    if ((due && due < today) || (when && when < today)) add("overdue", due && due < today ? `📅 ${due}` : `⏳ ${when}`, t);
  }
  const stamps = (p.sections.Log || []).flatMap((l) => l.match(/\d{4}-\d{2}-\d{2}/g) || []);
  const last = stamps.length ? stamps.reduce((a, b) => (a > b ? a : b)) : String(p.fm.date || "").slice(0, 10);
  p.lastLog = last; // main.js sorts the stale list by it
  const tagged = open.filter((t) => t.gtd.length), parked = tagged.length > 0 && tagged.every((t) => /\/(later|someday)$/.test(t.gtd[0]));
  const limit = parked ? STALE_DAYS.parked : STALE_DAYS.active;
  const cutoff = new Date(Date.parse(today) - limit * 864e5).toISOString().slice(0, 10);
  if (!p.completed && last && last < cutoff) add("stale", `last Log entry ${last}, ${parked ? "parked" : "active"} limit ${limit} days`);
  return issues;
}
