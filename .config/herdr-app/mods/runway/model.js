// Pure parsers for the runway mod: no imports, so Node's test runner loads it directly.

const BUCKETS = ["backlog", "wip", "hold", "done"];

// `git worktree list --porcelain`: blank-line separated blocks; the first is the main checkout.
export function parseWorktrees(stdout) {
  return stdout.split(/\n\s*\n/).filter((b) => b.trim()).map((block, i) => {
    const wt = { path: null, branch: null, main: i === 0 };
    for (const line of block.split("\n")) {
      if (line.startsWith("worktree ")) wt.path = line.slice(9);
      else if (line.startsWith("branch ")) wt.branch = line.slice(7).replace(/^refs\/heads\//, "");
    }
    return wt;
  });
}

// Listing script output: `@<key>` starts a section; lines before the first one are dropped.
export function parseListing(stdout) {
  const out = { backlog: [], wip: [], hold: [], done: [], intake: [], specflow: null };
  const spec = [];
  let key = null;
  for (const line of stdout.split("\n")) {
    if (line.startsWith("@")) {
      key = line.slice(1);
      if (key === "specflow") out.specflow = "";
    } else if (key === "specflow") spec.push(line);
    else if (BUCKETS.includes(key) && line.endsWith(".md")) out[key].push(line);
    else if (key === "intake" && /^\d{5}-/.test(line)) out.intake.push(line);
  }
  if (out.specflow !== null) out.specflow = spec.join("\n");
  return out;
}

export function newestVersion(names) {
  const parse = (n) => n.split(".").map(Number);
  return names.filter((n) => /^\d+\.\d+\.\d+$/.test(n)).reduce((best, n) => {
    if (best === null) return n;
    const [a, b] = [parse(n), parse(best)];
    const d = a.findIndex((x, i) => x !== b[i]);
    return d !== -1 && a[d] > b[d] ? n : best;
  }, null);
}

export function parseFrontmatter(text) {
  const lines = text.split("\n");
  if (lines[0] !== "---") return {};
  const fm = {};
  for (const line of lines.slice(1)) {
    if (line === "---") break;
    const at = line.indexOf(":");
    if (at > 0) fm[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  return fm;
}

export function titleOf(text, fallback) {
  const line = text.split("\n").find((l) => l.startsWith("# "));
  return line ? line.slice(2) : fallback;
}

const PRDS = "docs/dev/project-management/prds";

// First rule that matches: state owner holding it in wip/hold; stale (done on main, or renamed
// there: same number, other name) -> done; first wip holder; main; first holder.
function ownPrd(checkouts, name) {
  const find = (match, buckets) => {
    for (const c of checkouts) {
      const bucket = match(c) && buckets.find((b) => c.buckets[b].includes(name));
      if (bucket) return { kind: "prd", name, bucket, checkout: c };
    }
  };
  const main = checkouts.find((c) => c.main);
  const onMain = main ? BUCKETS.flatMap((b) => main.buckets[b]) : [];
  const stale = main && (main.buckets.done.includes(name)
    || (!onMain.includes(name) && onMain.some((n) => n.slice(0, 5) === name.slice(0, 5))));
  return find((c) => c.state?.prd === name, ["wip", "hold"])
    ?? (stale ? { kind: "prd", name, bucket: "done", checkout: main } : null)
    ?? find(() => true, ["wip"]) ?? find((c) => c.main, BUCKETS) ?? find(() => true, BUCKETS);
}

// A spec's lane takes ownership through its recorded name or standard branch name.
function ownSpecs(checkouts) {
  const main = checkouts.find((c) => c.main);
  const owned = new Map((main?.specs?.specs ?? []).map((s) => [s.spec, { spec: s, checkout: main }]));
  for (const c of checkouts) {
    const n = c.spec?.split("-")[0] ?? c.branch?.match(/^feature\/specflow-(.+)$/)?.[1];
    const spec = n && c.specs?.specs?.find((s) => c.spec ? s.spec === c.spec : s.spec.startsWith(`${n}-`));
    if (!spec) continue;
    for (const key of owned.keys()) if (key.startsWith(`${n}-`)) owned.delete(key);
    owned.set(spec.spec, { spec, checkout: c });
  }
  return [...owned.values()].filter(({ spec }) => spec.phase !== "complete")
    .map(({ spec, checkout }) => ({ kind: "spec", name: spec.spec, bucket: null, checkout, spec }));
}

export function ownItems(checkouts) {
  const prds = [...new Set(checkouts.flatMap((c) => BUCKETS.flatMap((b) => c.buckets[b])))]
    .map((name) => ownPrd(checkouts, name)).filter((i) => i.bucket !== "done");
  const ideas = [...new Set(checkouts.flatMap((c) => c.intake))].map((name) => ({
    kind: "idea", name, bucket: null,
    checkout: checkouts.find((c) => c.main && c.intake.includes(name)) ?? checkouts.find((c) => c.intake.includes(name)),
  }));
  return [...prds, ...ideas, ...ownSpecs(checkouts)];
}

function prdFields({ name, bucket }, text, state) {
  const st = state?.prd === name ? state : null;
  if (bucket === "backlog") return { stage: "backlog", next: "build" };
  if (bucket === "hold") {
    const line = text.split("\n").find((l) => l.startsWith("Detail: "));
    return { group: "parked", stage: "parked", reason: line?.slice(8) || st?.pause_reason?.detail || st?.stall_reason?.stalled || "" };
  }
  if (!st) return { stage: "wip", detail: "no state", next: "build" };
  const detail = {
    build: st.tasks_total > 0 ? `${st.tasks_completed}/${st.tasks_total} tasks` : "",
    review: `cycle ${st.cycle} of ${st.rework_cap}`,
    paused: st.pause_reason?.detail ?? "",
  }[st.phase] ?? "";
  const next = !st.next_phase ? "" : st.next_phase === "review" ? `review, cycle ${st.cycle}` : st.next_phase;
  return { stage: st.phase, detail, next };
}

function specFields({ phase, state, gates, nextTask, hold }) {
  const gate = ["design", "tasks", "implementation"].find((g) => gates[g] !== "open");
  const next = nextTask ? `task ${nextTask.id ?? nextTask.title}` : gate ? `${gate} gate` : "";
  const reason = !hold ? "" : typeof hold === "string" ? hold
    : typeof hold.reason === "string" ? hold.reason : JSON.stringify(hold);
  return { group: hold ? "parked" : "spec", stage: phase, detail: state === "valid" ? "" : `state ${state}`, next, reason };
}

export function toCard(item, text, checkout) {
  const { kind, name } = item;
  const path = checkout.path;
  const bare = name.replace(/^\d{5}-/, "");
  const card = { id: `${kind}:${name}`, kind, number: name.slice(0, 5), group: kind, detail: "", next: "", reason: "", checkout: path };
  if (kind === "idea") {
    return { ...card, title: titleOf(text, bare), stage: "idea", file: `${path}/docs/dev/project-management/intake/new/${name}/idea.md` };
  }
  if (kind === "spec") {
    return { ...card, ...specFields(item.spec), title: bare.replaceAll("-", " "), file: `${path}/${checkout.specsDir}/${name}/requirements.md` };
  }
  return { ...card, ...prdFields(item, text, checkout.state), title: titleOf(text, bare.replace(/\.md$/, "")), file: `${path}/${PRDS}/${item.bucket}/${name}` };
}

const CHIP_TYPES = ["branch", "worktree", "lane", "pr", "issue", "ref"];
const URLS = /https?:\/\/\S+/g;
const MENTIONS = /\b(issue|pr|pull\s+request)\s*#?(\d+)/gi;
const REFS = /(?<![\w/&])#(\d{1,5})(?![A-Za-z0-9])/g;

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const listOf = (value) => (value ?? "").split(",").map((s) => s.trim());
const numChip = (type, n, url) => ({ type, label: `#${n}`, value: url ?? n });

function urlChip(url) {
  const m = url.match(/\/(issues|pull|pull-requests|merge_requests)\/(\d+)\b/);
  return m ? [numChip(m[1] === "issues" ? "issue" : "pr", m[2], url)] : [];
}

// Frontmatter `issue:` / `pr:` item: a URL, or `#<n>` / `<n>`.
function itemChips(type, item) {
  if (/^https?:\/\//.test(item)) return urlChip(item);
  const n = item.replace(/^#/, "");
  return /^\d+$/.test(n) ? [numChip(type, n)] : [];
}

function branchChip(name, worktrees) {
  const path = worktrees.find((w) => w.branch === name)?.path;
  return path ? { type: "branch", label: name, value: name, path } : { type: "branch", label: name, value: name };
}

// A checked-out worktree shows as its branch.
function treeChip(w, worktrees) {
  return w.branch ? branchChip(w.branch, worktrees) : { type: "worktree", label: w.path.split("/").pop(), value: w.path, path: w.path };
}

function bodyOf(text) {
  const lines = text.split("\n");
  if (lines[0] !== "---") return text;
  const end = lines.indexOf("---", 1);
  return end === -1 ? "" : lines.slice(end + 1).join("\n");
}

function proseChips(body, { branches, worktrees }) {
  const urls = [...body.matchAll(URLS)].flatMap((m) => urlChip(m[0].replace(/[)\].,;:!?'"]+$/, "")));
  const plain = body.replace(URLS, " ");
  const mentions = [...plain.matchAll(MENTIONS)].map((m) => numChip(m[1].toLowerCase() === "issue" ? "issue" : "pr", m[2]));
  const refs = [...plain.replace(MENTIONS, " ").matchAll(REFS)].map((m) => numChip("ref", m[1]));
  const named = branches.filter((b) => b !== "master" && b !== "main" && b.length >= 4
    && new RegExp(`(?<![A-Za-z0-9._/-])${esc(b)}(?![A-Za-z0-9._/-])`).test(plain));
  return [...urls, ...mentions, ...refs, ...named.map((b) => branchChip(b, worktrees))];
}

// Names carrying the card's number; `specflow` names belong to spec cards only.
function numberChips(card, { branches, worktrees }) {
  const re = new RegExp(`(?<!\\d)${esc(card.number)}(?!\\d)`);
  const hit = (name) => re.test(name) && name.includes("specflow") === (card.kind === "spec");
  return [
    ...branches.filter(hit).map((b) => branchChip(b, worktrees)),
    ...worktrees.filter((w) => !w.main && hit(w.path.split("/").pop())).map((w) => treeChip(w, worktrees)),
  ];
}

function laneChips(card, { branches, worktrees, lanes }) {
  const file = card.file.split("/").pop();
  return lanes.filter((l) => l.prds.includes(file)).flatMap((l) => {
    const tree = worktrees.find((w) => w.path === l.worktree);
    const chips = [
      ...(branches.includes(l.branch) ? [branchChip(l.branch, worktrees)] : []),
      ...(tree ? [treeChip(tree, worktrees)] : []),
    ];
    return chips.length ? chips : [{ type: "lane", label: `lane ${l.name} (${l.status})`, value: l.name }];
  });
}

// A chip click: the ship-it panel that lists the item, or the browser.
export function jumpFor(chip, scope, modifiers) {
  const value = String(chip.value);
  if (modifiers?.platform || modifiers?.control || scope === "all" || chip.type === "ref" || !/^\d+$/.test(value)) return "browser";
  if (chip.type === "pr") return { panel: "ship-it-prs", kind: "pr", number: Number(value) };
  if (chip.type === "issue") return { panel: "ship-it-issues", kind: "issue", number: Number(value) };
  return "browser";
}

export function scanRefs(card, text, ctx) {
  const fm = parseFrontmatter(text);
  const chips = [
    ...listOf(fm.branch).filter((b) => ctx.branches.includes(b)).map((b) => branchChip(b, ctx.worktrees)),
    ...listOf(fm.issue).flatMap((i) => itemChips("issue", i)),
    ...listOf(fm.pr).flatMap((i) => itemChips("pr", i)),
    ...proseChips(bodyOf(text), ctx),
    ...numberChips(card, ctx),
    ...laneChips(card, ctx),
  ];
  const seen = new Set();
  return chips.filter((c) => {
    const key = `${c.type}\n${c.value}`;
    return seen.has(key) ? false : seen.add(key);
  }).sort((a, b) => CHIP_TYPES.indexOf(a.type) - CHIP_TYPES.indexOf(b.type));
}
