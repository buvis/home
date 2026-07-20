---
name: brief-portfolio
description: Use when the user wants a portfolio-wide status brief of all gita-registered repos as a single-file HTML dashboard with actionable follow-ups. Triggers on "brief portfolio", "state of my repos", "repo dashboard", "cross-repo todos".
---

# Brief Portfolio

Produce `~/.claude/portfolio-brief/portfolio-brief.html`: a self-contained Svelte
SPA showing recent releases/commits (grouped into epics), open issues/PRs,
failing CI, security alerts, PRD pipeline, local WIP, branch/worktree litter,
and a pickable cross-repo todo list for every repo in the gita registry
(`~/.config/gita/repos.csv`).

## Dependencies

- Path: `~/.config/gita/repos.csv` - the repo registry. Without it `collect.py`
  exits with "no repos found in gita registry" and there is nothing to brief.
- CLIs: `gh` (authenticated), `git`, `python3`.
- Reads per repo: `dev/local/audit-results/brush-report.md` — its `generated:`
  line stamps the last `brush` run and powers the 30-day brush-cadence nag
  (todo + attention reason). Missing report = never brushed = the nag fires.
- Writes: `~/.claude/portfolio-brief/`.
- Optional: `npm` plus node, only for the maintenance-only SPA rebuild below.
  Absent = the pre-built template still renders; you just cannot change `app/`.

## Workflow

### 1. Collect (deterministic)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/collect.py
```

Options: `--days N` (window, default 60), `--no-fetch` (skip `git fetch`, much
faster), `--out DIR` (default `~/.claude/portfolio-brief`). Writes `data.json` and
`commits-digest.md` into the out dir; it also rotates the previous `data.json`
to `data-prev.json` (powers the "Since last brief" diff) and appends one
summary line per run to `history.jsonl` (powers the trend sparkline) — never
delete those two. Report any `WARN` lines from stderr to the user verbatim —
transient GitHub API failures land there and in each repo's `errors` field.

### 2. Epics + judgment todos (model step)

Read `~/.claude/portfolio-brief/commits-digest.md` (and skim `data.json` signals
if needed) and write `~/.claude/portfolio-brief/epics.json`:

```json
{
  "summary": "2-4 short paragraphs. Manager voice. What actually moved across the portfolio, which themes dominate, what looks stuck or risky. Plain text, paragraphs separated by blank lines.",
  "repos": {
    "owner/name": {
      "epics": [
        {"title": "Short epic name", "summary": "one line", "shas": ["abc1234", "def5678"]}
      ]
    }
  },
  "todos": [
    {
      "id": "owner/name:judgment:short-slug",
      "repo": "owner/name",
      "kind": "judgment",
      "urgency": "now",
      "action": "Imperative follow-up the user can execute",
      "why": "one line of grounding in the data"
    }
  ]
}
```

Epic rules:
- Group by feature/theme (what shipped), never by commit type (feat/fix/test).
- 2-6 epics per repo; only repos with >=5 meaningful commits need epics.
- Skip pure-automation repos (all `chore(deps)`/`chore: sync`) — mention them in
  `summary`; their commits fall into the UI's "Other changes" bucket.
- Every sha must be copied exactly from the digest. Unknown shas are silently
  dropped by the UI, so don't invent any.

Todo rules:
- The app already auto-generates mechanical todos (failing CI, security alerts,
  unmerged PRs with checks state, unpushed/dirty local state with
  dirty-for-N-days, overdue releases with changelog readiness, milestone-due
  and engaged issues, stale-issue triage, PRD pipeline with wip idle-days,
  stray branches and worktrees, review requests outside the portfolio, overdue
  brush hygiene on a 30-day cadence). Do NOT duplicate those.
- Add only judgment items: composed follow-ups ("this repo has been dirty for
  11 days — resume or park the PRD work"), cross-repo observations, process
  suggestions grounded in the data. A handful, not dozens.
- `urgency`: `now` | `soon` | `later`. Ids must be stable across runs (checked
  state persists in the browser by id).
- Optional per-todo fields for the Matrix (Eisenhower) tab: `importance`
  (`high` | `low`, default `high`) and `effort` (`quick` | `medium` | `deep`,
  default `medium`). Set them only when the defaults are wrong.

### 3. Build and open

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build.py
open ~/.claude/portfolio-brief/portfolio-brief.html   # attended only
```

`open` needs a desktop session — run it **only in an attended run**. In an unattended/headless run (`CLAUDE_UNATTENDED=1`) skip it and just report the written path (`~/.claude/portfolio-brief/portfolio-brief.html`).

`build.py` injects `{data, epics}` into `assets/template.html` (pre-built
Svelte 5 single-file app) and writes `~/.claude/portfolio-brief/portfolio-brief.html`.
It works without epics.json but say so if you skipped step 2.

## Tests

```bash
python3 -m pytest ${CLAUDE_SKILL_DIR}/scripts/test_collect.py -q
npm --prefix ${CLAUDE_SKILL_DIR}/app test
```

## Rebuilding the SPA template (maintenance only)

Only needed after changing `app/` sources:

```bash
npm --prefix ${CLAUDE_SKILL_DIR}/app install
npm --prefix ${CLAUDE_SKILL_DIR}/app test
npm --prefix ${CLAUDE_SKILL_DIR}/app run build
cp ${CLAUDE_SKILL_DIR}/app/dist/index.html ${CLAUDE_SKILL_DIR}/assets/template.html
```
