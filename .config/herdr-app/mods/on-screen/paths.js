// Finds file and folder paths in a terminal's visible text that exist on this computer, and
// web links (http/https), which need no check, and commands: a `$ ` or `! ` line, a line inside a
// ``` fence, or an indented line whose first word is a program on PATH (how agents print the
// commands they hand you). Up to three commands, after the paths; nine rows in all.
// The menu cannot see the clicked word, so it offers the paths on screen, newest (lowest) first.
import { exec, hc } from "herdr";

const START = /^(~\/|\.{1,2}\/|\/[\w.~-]|[\w.-]+\/|[\w-][\w.-]*\.[A-Za-z0-9]{1,8}$)/;
const URL = /^https?:\/\/[^\s<>"'`]+/i;
const MAX_WORDS = 6, MAX_CANDIDATES = 400;

// Trailing punctuation from prose, and editor suffixes like file.ts:12:3 or file.md#L4.
const TAIL = /[`'")\]>,;!?.:]+$/;
const clean = s => s.replace(TAIL, "").replace(/(:\d+){1,2}$|#L\d+(-L?\d+)?$/, "").replace(TAIL, "");

function candidates(text) {
  const lines = text.split("\n"), out = [];
  for (let row = lines.length - 1; row >= 0 && out.length < MAX_CANDIDATES; row--) {
    const line = lines[row], words = [...line.matchAll(/\S+/g)];
    // A long path can wrap onto the next row; its first word may finish it.
    const wrap = (lines[row + 1] ?? "").trimStart().split(/\s/)[0] ?? "";
    for (let i = words.length - 1; i >= 0; i--) {
      const word = words[i][0].replace(/^[`'"(\[<]+/, "");
      // A web link: one candidate, no file check. A group that is an object is a link.
      const link = word.match(URL);
      if (link) { out.push({ url: link[0].replace(TAIL, "") }); continue; }
      if (!START.test(clean(word)) && !START.test(word)) continue;
      const begin = words[i].index + words[i][0].length - word.length, group = [];
      for (let j = i; j < Math.min(words.length, i + MAX_WORDS); j++) {
        const raw = line.slice(begin, words[j].index + words[j][0].length);
        group.push(clean(raw));
        if (j === words.length - 1 && wrap) group.push(clean(raw + wrap));
      }
      out.push([...new Set(group.filter(c => c.length > 1))]);
    }
  }
  return out;
}

// Which candidates exist: "kind\0candidate\0absolute\0" for each, relative ones against cwd.
const CHECK = 'for p in "$@"; do case "$p" in "~/"*) a="$HOME/${p#"~/"}";; /*) a="$p";; *) a="$PWD/$p";; esac; ' +
  'if [ -d "$a" ]; then printf "d\\0%s\\0%s\\0" "$p" "$a"; elif [ -f "$a" ]; then printf "f\\0%s\\0%s\\0" "$p" "$a"; fi; done';

// Where bare file names live below cwd: the repo's files (tracked and untracked, not ignored),
// else a bounded find. Prints "relative/path" per line; awk keeps those whose last part is a name.
const LOOKUP = 'pick() { awk -F/ \'BEGIN { for (i = 1; i < ARGC; i++) want[ARGV[i]] = 1; ARGC = 1 } want[$NF] && n[$NF]++ < 2\' "$@"; }; ' +
  'if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git ls-files --cached --others --exclude-standard | pick "$@"; ' +
  'else find . -maxdepth 6 -type f -not -path "*/.git/*" -not -path "*/node_modules/*" 2>/dev/null | head -100000 | sed "s#^\\./##" | pick "$@"; fi';
const MAX_NAMES = 12, PER_NAME = 2;
const MAX_COMMANDS = 3;
// An indented line counts as a command only with evidence beyond "its first word is a
// program": many English words are (`what`, `time`, `look`, `file`). It must not end like a
// sentence, and must start with a tool people are told to run or contain a command marker
// (a flag, a path, &&, |, =, @, <, >, $).
const TOOLS = new Set(["git", "gh", "npm", "npx", "pnpm", "yarn", "bun", "node", "deno", "pip", "pip3", "uv", "uvx", "python", "python3", "poetry", "cargo", "rustup", "go", "brew", "apt", "apt-get", "dnf", "pacman", "docker", "kubectl", "helm", "make", "cmake", "ssh", "scp", "rsync", "curl", "wget", "sudo", "cd", "open", "code", "nvim", "vim", "ruby", "gem", "bundle", "mix", "swift", "xcodebuild", "launchctl", "defaults", "killall", "herdr-app", "hc", "gcloud", "aws", "az", "flyctl", "vercel", "wrangler", "supabase", "tofu", "terraform", "ansible", "colima", "tmux", "ollama", "claude", "codex"]);
const MARKER = /(^|\s)--?[A-Za-z]|\/|&&|\|\||\||=|@|<|>|\$/;
const SENTENCE_END = /[.,;:!?]$/;

// Candidate command lines, lowest row first: [text, firstWord | null]. Null: no PATH check needed.
function commandCandidates(text) {
  const lines = text.split("\n"), out = [];
  // Per row: "fence" for a ``` line, true inside a fence, false outside.
  let fence = false; const inFence = [];
  for (const line of lines) {
    if (/^\s*```/.test(line)) { fence = !fence; inFence.push("fence"); continue; }
    inFence.push(fence);
  }
  const joined = [];
  // A line ending in `\` continues on the next one.
  for (let i = 0; i < lines.length; i++) {
    let s = lines[i]; const start = i;
    while (/\\\s*$/.test(s) && i + 1 < lines.length) { s = s.replace(/\\\s*$/, " ") + lines[++i].trim(); }
    joined.push([start, s]);
  }
  for (let j = joined.length - 1; j >= 0; j--) {
    const [row, line] = joined[j];
    if (inFence[row] === "fence") continue;
    const prompt = line.match(/^\s*[$!] (\S.*)$/);
    if (prompt) { out.push([prompt[1].trim(), null]); continue; }
    const body = line.trim();
    if (!body) continue;
    const first = body.split(/\s+/)[0];
    if (inFence[row] === true) { out.push([body, null]); continue; }
    const indented = /^\s{2,}\S/.test(line);
    if (indented && first === "sudo") { out.push([body, null]); continue; }
    // A program by path (`./build`, `~/bin/x`, `/usr/bin/y`) or by name: checked below.
    if (!indented || SENTENCE_END.test(body)) continue;
    if (/^(\.\/|~\/|\/)/.test(first) || /^[a-z][\w.+-]*$/.test(first) && body.includes(" ") && (TOOLS.has(first) || MARKER.test(body))) out.push([body, first]);
  }
  return out;
}

// The commands on screen whose first word checks out, newest first, at most three.
async function commandsOnScreen(text, cwd) {
  const cands = commandCandidates(text);
  const words = [...new Set(cands.map(([, w]) => w).filter(Boolean))];
  let onPath = new Set();
  if (words.length) {
    // Anything the person's own interactive login shell can run (a program on PATH, a
    // function or alias from their rc files, a builtin), except shell keywords, or an
    // executable file by path (relative to the pane's folder). Their shell, so programs the
    // rc files add (fnm's node and npm, pyenv, ...) and wrappers like a `gh` function count;
    // only lines that are one of the words are read, since such a shell may print on start.
    const WHICH = 'for w in "$@"; do case "$w" in if|then|else|elif|fi|case|esac|for|while|until|do|done|in|function|select|time|coproc|foreach|repeat|end|always|nocorrect|noglob|builtin|command) continue;; "~/"*) [ -x "$HOME/${w#"~/"}" ] && printf "%s\\n" "$w"; continue;; /*|./*) [ -x "$w" ] && printf "%s\\n" "$w"; continue;; esac; command -v "$w" >/dev/null 2>&1 && printf "%s\\n" "$w"; done; exit 0';
    // The inner shell takes its first argument as $0, hence the "which" placeholder.
    const r = await exec("sh", ["-c", 'exec "${SHELL:-/bin/sh}" -lic "$0" "$@"', WHICH, "which", ...words], { cwd: cwd || undefined }).catch(() => null);
    const want = new Set(words);
    onPath = new Set((r?.stdout ?? "").split("\n").map((l) => l.trim()).filter((l) => want.has(l)));
  }
  const out = [], seen = new Set();
  for (const [cmd, w] of cands) {
    if (w && !onPath.has(w)) continue;
    if (seen.has(cmd)) continue;
    seen.add(cmd); out.push({ cmd: true, path: cmd });
    if (out.length >= MAX_COMMANDS) break;
  }
  return out;
}

async function findByName(names, cwd) {
  if (!names.length || !cwd) return new Map();
  const r = await exec("sh", ["-c", LOOKUP, "lookup", ...names], { cwd }).catch(() => null);
  const byName = new Map();
  for (const rel of (r?.stdout ?? "").split("\n").filter(Boolean)) {
    const name = rel.split("/").pop(), list = byName.get(name) ?? [];
    if (list.length < PER_NAME) byName.set(name, [...list, { dir: false, path: `${cwd}/${rel}` }]);
  }
  return byName;
}

// Up to `limit` rows: the paths and links, newest first, then up to three commands.
// `allow(path)` keeps a found path out of the list when it says no.
export async function pathsOnScreen(terminal, cwd, { limit = 9, allow = null } = {}) {
  const read = await hc(["read", terminal]);
  if (read.code !== 0) return [];
  const commands = await commandsOnScreen(read.stdout, cwd).catch(() => []);
  return [...await pathsOnly(read.stdout, cwd, limit - commands.length, allow), ...commands];
}

async function pathsOnly(text, cwd, limit, allow) {
  const groups = candidates(text);
  const all = [...new Set(groups.filter(Array.isArray).flat())].slice(0, MAX_CANDIDATES);
  if (!all.length) return groups.filter(g => !Array.isArray(g)).slice(0, limit).map(g => ({ url: true, path: g.url }));
  const r = await exec("sh", ["-c", CHECK, "paths", ...all], { cwd: cwd || undefined });
  if (r.code !== 0) return [];
  const found = new Map(), f = r.stdout.split("\0");
  for (let i = 0; i + 2 < f.length; i += 3) found.set(f[i + 1], { dir: f[i] === "d", path: f[i + 2].replace(/\/\.\/|\/+$/g, m => (m === "/./" ? "/" : "")) });
  // A bare "name.ext" that is not in cwd is looked up in the project below it.
  const bare = group => Array.isArray(group) && !group.some(c => found.has(c)) && /^[\w-][\w.-]*\.[A-Za-z0-9]{1,8}$/.test(group[0]) ? group[0] : null;
  const names = [...new Set(groups.map(bare).filter(Boolean))].slice(0, MAX_NAMES);
  const byName = await findByName(names, cwd);
  const out = [], seen = new Set();
  for (const group of groups) {
    // The longest candidate that exists: "Screenshot at 16.36.png" over "Screenshot".
    const hit = Array.isArray(group) ? group.filter(c => found.has(c)).sort((a, b) => b.length - a.length)[0] : null;
    const items = !Array.isArray(group) ? [{ url: true, path: group.url }] : hit ? [found.get(hit)] : byName.get(bare(group)) ?? [];
    for (const item of items) {
      if (item.path === "/" || item.path === cwd || seen.has(item.path)) continue;
      if (!item.url && allow && !allow(item.path)) continue;
      seen.add(item.path);
      out.push(item);
      if (out.length >= limit) return out;
    }
  }
  return out;
}
