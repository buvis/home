---
default_model: opus
model_tier_rationale: invented predicates (session ownership, path and URL recognition, ranking), invented mod contracts, and writes outside ~/.claude
---

# Build Pluck as a herdr-app mod

Source: herdr-plugins PRD 00001 (parked in `~/git/src/github.com/buvis/herdr-plugins/docs/dev/project-management/prds/hold/00001-pluck-v1.md`), the desktop part of herdr-plugins intake 00002 (`~/git/src/github.com/buvis/herdr-plugins/docs/dev/project-management/intake/new/00002-pluck-smart-copy-across-clients/idea.md`), and the user's decisions of 2026-11-08: JavaScript mod in herdr-app, the Python core retired, mods versioned in buvis, commands plus more kinds, a pi session reporter.

Before launching: `export _AUTOPILOT_WRITE_SCOPE_EXTRA="$HOME/.config/herdr-app:$HOME/.pi/agent/extensions"` (the write-scope fence denies these roots otherwise).

## Overview

### Problem Statement

The user runs coding agents (Claude Code, pi) in the herdr-app desktop window on herdr-core (`hc`). Copying a command, code block, URL, path or whole answer from agent output means dragging over rendered terminal text, which loses boundaries and keeps renderer line breaks. Pluck solved this for the Herdr TUI by reading the agent's own transcript, but herdr-app does not load TUI plugins. The transcript logic is Python (`plugins/pluck/pluck_transcripts.py` in herdr-plugins); herdr-app mods are JavaScript.

### Target Users

The solo developer on macOS who works in herdr-app with Claude Code and pi terminals.

### Success Metrics

- `node ~/.config/herdr-app/mods/pluck/test.mjs` exits 0.
- `herdr-app check ~/.config/herdr-app/mods/pluck` prints `check passed`.
- `jq -r '.global["cmd-shift-y"]' ~/.config/herdr-app/keys.json` prints `mod.open:pluck`.
- `git --git-dir=$HOME/.buvis --work-tree=$HOME ls-files ':(top).config/herdr-app/mods/pluck' ':(top).pi/agent/extensions/pluck-session.ts'` lists every source file named in the Repository Structure.

## Functional Decomposition

### Capability: Identify the source transcript

Map the terminal the person was in to exactly one transcript, or ask them to choose.

#### Feature: Capture the source terminal
- **Description**: Record which terminal Pluck was opened from, once, when the mod opens.
- **Inputs**: `focused()` from the `herdr` module; `spaces()` for the focused space's `machine`.
- **Outputs**: `{ address, cwd }` of the source terminal.
- **Behavior**: In `init`, read `focused().terminal`. Null (a mod pane has focus) is the error `Pluck needs a terminal: focus an agent terminal first`. A focused space whose `machine` is non-null is the error `Pluck reads local transcripts only; this terminal runs on <machine>`. Never re-read focus later in the session.

#### Feature: Resolve native identity
- **Description**: Turn the terminal's foreground process into a transcript path without guessing.
- **Inputs**: `hc(["get", address, "--json"])` → `foreground` (`pid`, `cwd`, `argv`) and `status.app`; Claude's `~/.claude/sessions/<pid>.json`; the pi reporter's `~/.local/state/pluck/pi/<pid>.json`; roots `~/.claude/projects` and `~/.pi/agent/sessions`.
- **Outputs**: `{ kind: "native", agent, pid, sessionId, transcript }`, or `null` when no native record exists.
- **Behavior**: `status.app == "claude-code"` reads `~/.claude/sessions/<pid>.json`; its `sessionId` must be a non-empty string and its `pid` must equal the foreground pid. The transcript is the single file named `<sessionId>.jsonl` directly inside a folder of `~/.claude/projects`. Its first record carrying `sessionId` must hold that same id. Zero matches is the error `no Claude transcript for session <id>`; two or more is `<n> Claude transcripts claim session <id>; refusing to guess`. `status.app == "pi"` reads `~/.local/state/pluck/pi/<pid>.json` (`pid`, `sessionFile`, `sessionId`). `sessionFile` must be absolute, end in `.jsonl`, exist, and start with a pi `session` header whose `id` equals `sessionId`. Any other `app`, or a missing record file, returns `null`. An unreadable or malformed record file is an error naming the file, never a silent `null`.

#### Feature: Fall back to an explicit choice
- **Description**: When no native record exists, offer same-folder transcripts and require a choice.
- **Inputs**: The agent (`claude` or `pi`, from `status.app`; otherwise the error `Pluck supports Claude Code and pi; this terminal runs <app>`), the foreground `cwd`, the agent's root.
- **Outputs**: A candidate list, newest first, each labeled `heuristic - not verified ownership` with its mtime as `YYYY-MM-DD HH:MM`.
- **Behavior**: List `*.jsonl` files under the root, skipping any `subagents` folder. Keep the files whose header `cwd` equals the foreground `cwd` (Claude: the first record with a string `cwd`, within the first 128 lines; pi: the session header). Always ask, even for one candidate. Zero candidates shows `No transcript for this folder. Pluck needs Claude Code or the pluck-session pi extension to identify the session.` and copies nothing.

#### Feature: Re-check before copying
- **Description**: Abort when the terminal changed session after resolution.
- **Inputs**: The source address and the resolved identity.
- **Outputs**: Nothing, or an error.
- **Behavior**: Immediately before writing the clipboard, repeat native resolution. A different foreground pid, `sessionId` or transcript path, or native identity appearing or disappearing, is the error `the terminal changed session since Pluck opened; nothing copied`.

#### Feature: Report pi sessions
- **Description**: A pi extension records which session file each pi process uses.
- **Inputs**: pi's `session_start` and `agent_start` events and their `ctx`.
- **Outputs**: `~/.local/state/pluck/pi/<process.pid>.json` holding `{ "pid", "sessionFile", "sessionId", "cwd", "updatedAt" }`.
- New symbols: `sessionFile`
- **Behavior**: Only when `ctx.mode === "tui"`. Read `ctx.sessionManager.getSessionFile()` and `getSessionId()` as `herdr-agent-state.ts` does; write only when the file path is absolute. Write atomically: a temp file in the same folder, then rename. Create the folder with mode `0700`. Never throw into pi: any write error is swallowed after one `console.error` line. That pi's `process.pid` equals hc's foreground pid for a pi terminal is assumed (guess); when it does not hold, the mod finds no record and uses the explicit choice.

### Capability: Read and extract

Port the Python reader and extractor, then add more kinds.

#### Feature: Read transcripts
- **Description**: Read the newest assistant text from a Claude or pi transcript.
- **Inputs**: Transcript path, agent, lookback 20.
- **Outputs**: Entries `{ text, messageIndex, sourceOrder }`, messageIndex 0 for the newest message.
- **Behavior**: Exactly the behavior of `read_claude_entries`, `read_pi_entries`, `_read_jsonl` and `_walk_pi_chain` in `plugins/pluck/pluck_transcripts.py`: blank lines skipped; an unparseable last line without a trailing newline ignored (a writer mid-append); any other unparseable line is `<path>: malformed record on line <n>`; Claude keeps `type == "assistant"` records whose `isSidechain` is not true and whose content blocks include text, thinking or tool_use; pi follows `parentId` links back from the last record and rejects unknown parents and cycles. Read with `fs/promises` `readFile`, not `readTextFile` (its 1 MiB cap is smaller than real transcripts).

#### Feature: Extract commands
- **Description**: The command kind, ported as is.
- **Inputs**: Entries.
- **Outputs**: Items `{ kind: "command", raw, display, tier, messageIndex, sourceOrder }`.
- **Behavior**: Exactly the behavior of `extract_snippets` and `_extract_fence_bodies` in `plugins/pluck/pluck_transcripts.py` at herdr-plugins commit d8ec3d2: the fence tag is the first word of the info string, lowercased; bash/sh/zsh/fish fences are one command, prompts stripped only when the first non-blank line is a `$ ` prompt; console and untagged fences yield only their `$ ` lines; standalone `$ ` lines outside fences; an odd number of trailing backslashes continues a command and a `> ` continuation prefix is stripped; tier 0 for bash/sh/zsh/fish fences, 1 when the prose since the previous block matches `\b(run|in another terminal|in a second pane)\b` (case-insensitive), else 2.

#### Feature: Extract more kinds
- **Description**: Code blocks, URLs, paths and whole answers.
- **Inputs**: Entries.
- **Outputs**: Items of kind code, url, path and answer.
- **Behavior**: Code: every fenced block whose tag is neither a shell tag nor console, plus untagged fences with no `$ ` line; the body with the fence's indentation removed and the final newline dropped. URL: matches of the regex https?://[^\s<>"'\x60)\]]+ in text outside fences, with trailing . , ; : ! ? characters removed. Path: single-backtick inline code outside fences whose content has no whitespace and either starts with "/", "~/", "./" or "../", or contains "/" and ends with "." plus 1-8 letters or digits, optionally followed by ":" and digits. Answer: each entry's full text. Within each kind, drop later duplicates of the same raw text (keep the newest). Order: tier, then messageIndex, then sourceOrder.

#### Feature: Render safely
- **Description**: Show untrusted transcript text without letting it control the screen.
- **Inputs**: An item's `raw`.
- **Outputs**: `display` (one line) and the preview (many lines).
- **Behavior**: Drop Unicode category C characters and U+2028/U+2029 (keep `\t` in `display`, mapped to one space; keep `\n` and map `\t` to four spaces in the preview). `display` is the first line, truncated to 120 characters with `…`. `raw` is never altered.

### Capability: Pick and copy

#### Feature: Open the picker
- **Description**: A key opens Pluck over the window.
- **Inputs**: `keys.json` binding `"cmd-shift-y": "mod.open:pluck"` in `global`; `mod.json`.
- **Outputs**: A popup overlay.
- **Behavior**: `mod.json` is `{ "place": "none", "title": "Pluck", "overlay": { "kind": "popup", "at": "top", "offset": 40, "width": 720, "height": 0.8 } }`, the shape of the shipped `picker` mod.

#### Feature: Choose and copy
- **Description**: Filter, preview and copy one item.
- **Inputs**: Items, keyboard.
- **Outputs**: The clipboard holds the item's exact `raw`.
- **Behavior**: The header names the source terminal and `native` or `heuristic`. A filter input matches `display` case-insensitively. Tab and Shift-Tab cycle the kind tab in the order command, code, url, path, answer; the first tab with items opens first. Up/Down move the selection; the preview shows the selected item. Enter runs the re-check, then `cx.write_to_clipboard(raw)`, then `notify({ title: "Copied <kind>", body: display, level: "success" })`, then closes. Esc closes without copying. Errors show inside the popup until Esc and never touch the clipboard. Empty extraction shows `Nothing to copy in the last 20 answers.`

### Capability: Version the mod

#### Feature: Track sources in buvis
- **Description**: Pluck's source files get history in the dotfiles repo.
- **Inputs**: The files in the Repository Structure.
- **Outputs**: A buvis commit.
- **Behavior**: Stage only the listed source files by explicit `:(top)` pathspecs, never the generated `gpui-kit.d.ts` or `jsconfig.json` and never other mods. When the buvis index is not writable in the sandbox, file `git --git-dir=$HOME/.buvis --work-tree=$HOME add ...` and `commit` through `~/bin/warrant request --no-wait` and report the request ids.

## Structural Decomposition

### Repository Structure

```text
~/.config/herdr-app/mods/pluck/
├── mod.json          # Maps to: Open the picker
├── main.js           # Maps to: Capture the source terminal, Choose and copy
├── identity.js       # Maps to: Resolve native identity, Fall back to an explicit choice, Re-check before copying
├── transcripts.js    # Maps to: Read transcripts
├── extract.js        # Maps to: Extract commands, Extract more kinds, Render safely
└── test.mjs          # node self-check for identity.js, transcripts.js, extract.js
~/.config/herdr-app/keys.json                 # one added binding
~/.pi/agent/extensions/pluck-session.ts      # Maps to: Report pi sessions
# Read-only reference (behavior to port, not edited):
~/git/src/github.com/buvis/herdr-plugins/plugins/pluck/pluck_transcripts.py
~/git/src/github.com/buvis/herdr-plugins/plugins/pluck/test_pluck_snippets.py
~/git/src/github.com/buvis/herdr-plugins/plugins/pluck/test_pluck_recovery.py
```

### Module: transcripts
- **Maps to capability**: Read and extract
- **Responsibility**: Parse Claude and pi JSONL into ordered entries.
- **Location**: `~/.config/herdr-app/mods/pluck/transcripts.js`
- **Exports**:
  - `readEntries(path, agent, lookback)` - entries, newest message first by messageIndex
- New symbols: `readEntries`, `messageIndex`, `sourceOrder`, `test.mjs`

### Module: extract
- **Maps to capability**: Read and extract
- **Responsibility**: Turn entries into ranked, deduplicated items per kind, and render them safely.
- **Location**: `~/.config/herdr-app/mods/pluck/extract.js`
- **Exports**:
  - `extractItems(entries)` - every kind's items
  - `stripControls(text, keep)` - the shared sanitizer
  - `renderLine(text)` - the one-line `display`
- New symbols: `extractItems`, `stripControls`, `renderLine`

### Module: identity
- **Maps to capability**: Identify the source transcript
- **Responsibility**: Map a terminal to a transcript, list heuristic candidates, and re-check. IO is injected (`hcGet`, `readText`, `listDir`, `stat`) so node can test it without the app.
- **Location**: `~/.config/herdr-app/mods/pluck/identity.js`
- **Exports**:
  - `resolveNative(terminal, io)` - native identity or `null`
  - `listCandidates(agent, cwd, io)` - heuristic candidates
  - `sameIdentity(a, b)` - the re-check comparison
- New symbols: `resolveNative`, `listCandidates`, `sameIdentity`, `hcGet`, `readText`, `listDir`

### Module: ui
- **Maps to capability**: Pick and copy
- **Responsibility**: The overlay: capture, picker states (candidates, items, error), copy.
- **Location**: `~/.config/herdr-app/mods/pluck/main.js`, `~/.config/herdr-app/mods/pluck/mod.json`, `~/.config/herdr-app/keys.json`
- **Exports**: default `View` class

### Module: pi reporter
- **Maps to capability**: Report pi sessions
- **Responsibility**: Write the pid-to-session record.
- **Location**: `~/.pi/agent/extensions/pluck-session.ts`
- **Exports**: default extension function

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **transcripts**: entries from both transcript formats.
- **extract**: items from entries (pure; depends only on the entry shape).
- **pi reporter**: independent of the mod.

### Core Layer (Phase 1)
- **identity**: Depends on [transcripts] (header and metadata reads).

### Integration Layer (Phase 2)
- **ui**: Depends on [identity, extract, transcripts].

## Implementation Phases

### Phase 0: Foundation
**Goal**: The ported reader and extractor, and the pi reporter.

**Tasks**:
- [ ] Port the readers into `~/.config/herdr-app/mods/pluck/transcripts.js` with node tests in `~/.config/herdr-app/mods/pluck/test.mjs` translated from the reader cases of `test_pluck_snippets.py` and `test_pluck_recovery.py` (no deps) - Acceptance: `node ~/.config/herdr-app/mods/pluck/test.mjs` exits 0 and prints "ok <name>" for each of the checks "claude text only", "claude lookback", "pi active branch", "trailing append", "malformed record", "unsupported format", "complete final record".
- [ ] Port command extraction and add the other kinds in `~/.config/herdr-app/mods/pluck/extract.js`, tests in `~/.config/herdr-app/mods/pluck/test.mjs` (no deps) - Acceptance: `node ~/.config/herdr-app/mods/pluck/test.mjs` exits 0 and prints "ok <name>" for "shell fences", "console output excluded", "standalone prompt", "continuations", "heredoc kept", "untagged fence prompts", "fence tag attributes", "stable ranking", "code blocks", "urls", "paths", "answers", "dedupe newest", "render strips controls".
- [ ] Write `~/.pi/agent/extensions/pluck-session.ts` (no deps) - Acceptance: `rg -n 'session_start|agent_start|getSessionFile|rename' ~/.pi/agent/extensions/pluck-session.ts` finds all four; `rg -n '\.local/state/pluck/pi' ~/.pi/agent/extensions/pluck-session.ts` finds the path.

**Exit Criteria**: The extractor and readers match the Python behavior on the translated cases.

### Phase 1: Core
**Goal**: Terminal-to-transcript resolution.

**Tasks**:
- [ ] Implement `~/.config/herdr-app/mods/pluck/identity.js` with injected IO; tests in `~/.config/herdr-app/mods/pluck/test.mjs` (depends on: Phase 0) - Acceptance: `node ~/.config/herdr-app/mods/pluck/test.mjs` exits 0 and prints "ok <name>" for "claude native", "claude pid mismatch", "claude duplicate session refused", "pi native", "pi record header mismatch", "missing record is heuristic", "malformed record is error", "heuristic same cwd only", "heuristic skips subagents", "re-check detects change". Every check ends with a nonzero exit when it fails.

**Exit Criteria**: Every identity rule above has a passing named check.

### Phase 2: Integration
**Goal**: The working mod, bound and versioned.

**Tasks**:
- [ ] Build `~/.config/herdr-app/mods/pluck/main.js` and `~/.config/herdr-app/mods/pluck/mod.json` (depends on: Phase 1) - Acceptance: `herdr-app check ~/.config/herdr-app/mods/pluck` prints `check passed`; `rg -n 'write_to_clipboard' ~/.config/herdr-app/mods/pluck/main.js` finds exactly one call, and `rg -n 'sameIdentity' ~/.config/herdr-app/mods/pluck/main.js` finds the re-check.
- [ ] Add `"cmd-shift-y": "mod.open:pluck"` to `global` in `~/.config/herdr-app/keys.json` (depends on: previous task). Premise: `cmd-shift-y` is unbound in every section of that file. Re-check at execution with `jq '[.. | objects | keys[]] | index("cmd-shift-y")' ~/.config/herdr-app/keys.json`; on a hit, skip this task and report the existing binding - Acceptance: `jq -r '.global["cmd-shift-y"]' ~/.config/herdr-app/keys.json` prints `mod.open:pluck` and `jq . ~/.config/herdr-app/keys.json` exits 0.
- [ ] Commit the sources to buvis (depends on: previous tasks) - Acceptance: the Success Metrics `ls-files` command lists `mod.json`, `main.js`, `identity.js`, `transcripts.js`, `extract.js`, `test.mjs` and `pluck-session.ts`, and does not list `gpui-kit.d.ts` or `jsconfig.json`.

**Exit Criteria**: Every Success Metric holds.

## Test Strategy

### Critical Scenarios
- **Happy path**: A Claude terminal with a `~/.claude/sessions/<pid>.json` record → the picker opens on its transcript marked `native` → Enter copies the exact `raw` bytes.
- **Edge case**: A pi terminal without a reporter record → the candidate list for its folder, labeled heuristic; no automatic choice even for one candidate.
- **Error case**: The terminal's Claude session changes between opening and Enter → `the terminal changed session since Pluck opened; nothing copied`, clipboard untouched.
- **Error case**: A transcript line that is malformed and complete → `<path>: malformed record on line <n>` inside the popup.

## Risks

- **Claude's session file is internal**: `~/.claude/sessions/<pid>.json` is not a documented interface (seen in Claude Code 2.1.318 and 2.1.319). If it disappears or changes shape, resolution returns `null` and Pluck falls back to the explicit choice; it never guesses silently.
- **pi pid match**: If pi's `process.pid` is not hc's foreground pid, pi terminals always use the explicit choice. The reporter record still carries `cwd` for a later fix.
- **Untrusted text**: Transcript text reaches the screen only through `stripControls`, and the clipboard only through `write_to_clipboard(raw)`; Pluck never runs selected text.
- **Mod runtime differences**: Modules shared with `node` may import only `fs/promises` and `path`, never `herdr` or `gpui-kit`; `main.js` alone touches the app API.
