---
name: awesome-neovim-scan
description: Scan awesome-neovim for new plugins since last check. Triggers on "check awesome-neovim", "scan neovim plugins", "any new neovim plugins?", "new plugins in awesome-neovim".
---

# awesome-neovim-scan

Scans `rockerBOO/awesome-neovim` for plugins added since the last scan date recorded in the
zettelkasten, and appends new entries (with `- [ ]` checkboxes) to the appropriate sections.
Skips any plugin already present in the file — in any section, any checkbox state.

---

## Step 0 — Initialise zettelkasten if missing

Check whether `/Users/bob/bim/zettelkasten/20260227122532.md` exists. If it does **not**, create
it using the template below — substituting **today's actual date** for `YYYY-MM-DD` — then
**stop and report** "Zettelkasten created with scan date YYYY-MM-DD. Run again to pick up new
plugins." Do NOT proceed with the scan on the same run; the file is empty and there is nothing
to diff against yet.

```markdown
# Awesome Neovim

Last scan: **YYYY-MM-DD**

Tracks new entries from [rockerBOO/awesome-neovim](https://github.com/rockerBOO/awesome-neovim).

---

## 1. LSP & Completion

Language servers, completion engines, diagnostics, inline hints, hover docs.

## 2. AI & Copilot

AI coding assistants, LLM integrations, copilot alternatives, chat interfaces.

## 3. File & Project Navigation

Fuzzy finders, file explorers, project management, buffer management, marks, search.

## 4. Git & Version Control

Git integration plugins, diff tools, blame, conflict resolution.

## 5. Debugging & Testing

DAP adapters, debugging UIs, test runners, code runners.

## 6. Syntax & Language Support

Treesitter, syntax highlighting, language-specific plugins, snippets.

## 7. Editing & Formatting

Editing support, text objects, surround, auto-pairs, formatting, alignment.

## 8. UI & Appearance

Colorschemes, statuslines, tablines, icons, startup screens, animations, scrolling.

## 9. Utility & Workflow

Utilities, session management, keybindings, motion, command line tools, workflow.

## 10. Note Taking & Knowledge

Note taking, wiki, markdown preview, database, live preview.

## 11. Terminal & Remote

Terminal integration, remote development, deployment, split/window management.

## 12. Neovim Development

Lua development tools, plugin development utilities, Fennel, starter templates.

## 13. Dropped

Rejected — exists only to prevent re-adding.
```

---

## Step 1 — Read the zettelkasten

Read `/Users/bob/bim/zettelkasten/20260227122532.md` and extract:

1. **Last scan date** — the date on the line `Last scan: **YYYY-MM-DD**`
2. **All tracked repos** — every GitHub owner/repo handle that appears anywhere in the file
   (e.g. `nvim-telescope/telescope.nvim`). This is your dedup list. Check all sections
   including Dropped.

---

## Step 2 — Fetch commits since last scan

Fetch the commit history page:

```text
https://github.com/rockerBOO/awesome-neovim/commits/main
```

Parse commits dated **after** the last scan date. Focus only on commits matching this pattern:

```text
Add `<owner>/<repo>` (#NNN)
```

Ignore commits like `Update ...`, `Fix ...`, `chore: ...`, `Merge ...` — these don't add new
plugins. Each matching commit corresponds to one new plugin being added to the list.

---

## Step 3 — Look up each new plugin

For each new-plugin commit, fetch the corresponding PR page:

```text
https://github.com/rockerBOO/awesome-neovim/pull/<NNN>
```

Extract:

- **GitHub URL** (owner/repo)
- **Short name** (the plugin's name as listed)
- **Description** — one sentence of what it actually does; prefer the repo's own README tagline
  over the PR description if they differ
- **Category** — which section of awesome-neovim it was added to (visible in the PR diff)

Also fetch the repo's GitHub page to get the **star count** (★N).

Skip any repo whose owner/repo already appears in the zettelkasten (any section).

---

## Step 4 — Choose the right section

Place each new plugin in the most fitting section. Use the category from the PR diff as a strong
hint, but apply your own judgement to map it to the zettelkasten sections:

| # | Section | Typical contents |
|---|---------|-----------------|
| 1 | LSP & Completion | language servers, completion (nvim-cmp, blink), diagnostics, hover |
| 2 | AI & Copilot | AI assistants, LLM chat, Copilot alternatives, code generation |
| 3 | File & Project Navigation | telescope, fzf, nvim-tree, harpoon, buffers, marks, search |
| 4 | Git & Version Control | gitsigns, fugitive, diffview, git blame, conflict tools |
| 5 | Debugging & Testing | nvim-dap, neotest, test runners, code runners, REPL |
| 6 | Syntax & Language Support | treesitter, syntax, snippets, language-specific, register |
| 7 | Editing & Formatting | text objects, surround, autopairs, formatting, alignment |
| 8 | UI & Appearance | colorschemes, lualine, barbar, icons, dashboard, animation |
| 9 | Utility & Workflow | utilities, session, keybindings, motion, mouse, scrolling, command line |
| 10 | Note Taking & Knowledge | neorg, obsidian, wiki, markdown preview, databases |
| 11 | Terminal & Remote | toggleterm, remote dev, deployment, split/window management |
| 12 | Neovim Development | Lua dev, plugin scaffolding, Fennel, starter configs, preconfigured |
| 13 | Dropped | rejected |

If a plugin is clearly niche/low-value for a SAP/ABAP/Python/Rust/Kubernetes developer —
e.g. a game plugin, a very niche language tool, commercial noise, <5 stars with no clear use
case — add it to **Section 13 Dropped** with a brief reason. This prevents it from re-appearing
in future scans.

---

## Step 5 — Write the new entries

For each new plugin being added to sections 1–12, append it **at the end** of the unchecked
(`- [ ]`) block in that section, using this format:

```markdown
- [ ] **<short-name>** — [<owner>/<repo>](https://github.com/<owner>/<repo>) — <one-sentence description>. ★<count>
```

For plugins added to Section 13 (Dropped), use:

```markdown
- [ ] [<owner>/<repo>](https://github.com/<owner>/<repo>) — <reason for dropping>
```

Do **not** duplicate entries. If owner/repo already appears anywhere in the file, skip it entirely.

---

## Step 6 — Update the scan date

Replace the line:

```text
Last scan: **<old-date>**
```

with today's date:

```text
Last scan: **YYYY-MM-DD**
```

---

## Step 7 — Report back

Summarise what was done:

- Updated scan date from `<old>` → `<new>`
- List each plugin added, which section it went into, and its star count
- Mention any plugins skipped (already present or dropped)

Keep it concise — the user can open the file for full details.

---

## Edge cases

- **PR is a 404** — note it in the summary as "could not fetch #NNN" and skip.
- **Repo is a 404 or archived** — add to Section 13 Dropped with reason "404/archived".
- **Stars not shown** — omit the ★ count rather than guessing.
- **Ambiguous section** — pick the best fit and mention it briefly in the summary so the user
  can move it if needed.
- **No new commits** — report "No new plugins since <last-scan-date>" and leave the file
  unchanged (don't even update the scan date, since nothing was actually scanned).
- **Multiple plugins in one commit** — uncommon but possible; process each separately.
