// Pure derivations from the injected payload. No fetches — the file is self-contained.

export function loadPayload() {
  try {
    const p = JSON.parse(document.getElementById('portfolio-payload').textContent)
    if (!p.data?.repos) throw new Error('missing data.repos')
    return p
  } catch {
    return null
  }
}

const FAILING = new Set(['failure', 'timed_out', 'startup_failure'])
const DAY = 86400000

export const slug = (r) => `${r.owner}/${r.name}`

export const daysAgo = (iso) => (iso ? Math.floor((Date.now() - new Date(iso)) / DAY) : null)

export function ago(iso) {
  const d = daysAgo(iso)
  if (d === null) return '?'
  if (d < 1) return 'today'
  if (d < 14) return `${d}d ago`
  if (d < 60) return `${Math.round(d / 7)}w ago`
  return `${Math.round(d / 30)}mo ago`
}

export const isDepBot = (pr) =>
  /renovate|dependabot/i.test(pr.author) || pr.labels.some((l) => /dependenc/i.test(l))

export const ciFailing = (repo) => (repo.ci ?? []).filter((w) => FAILING.has(w.conclusion))

// data.json before 2026-07 had prds.wip as plain title strings.
export const wipItems = (prds) =>
  (prds?.wip ?? []).map((w) => (typeof w === 'string' ? { title: w, idle_days: null } : w))

export const secCritical = (repo) =>
  (repo.security ?? []).filter((a) => a.severity === 'critical' || a.severity === 'high')

const SEV_RANK = { critical: 0, serious: 1, warning: 2 }
export const worstSev = (reasons) =>
  reasons.toSorted((a, b) => SEV_RANK[a.sev] - SEV_RANK[b.sev])[0]?.sev ?? 'good'
// Transparent scoring: every point comes with a human-readable reason.
export function attention(repo) {
  const reasons = []
  const add = (points, sev, text) => reasons.push({ points, sev, text })
  const n = (c, word, pl = 's') => `${c} ${word}${c === 1 ? '' : pl}`

  const fails = ciFailing(repo)
  if (fails.length) add(50 * fails.length, 'critical', n(fails.length, 'failing workflow'))

  const sec = repo.security ?? []
  const crit = secCritical(repo).length
  if (crit) add(60 * crit, 'critical', n(crit, 'critical/high security alert'))
  if (sec.length - crit)
    add(Math.min((sec.length - crit) * 8, 24), 'warning', n(sec.length - crit, 'low/medium security alert'))

  const prs = repo.prs ?? []
  const real = prs.filter((p) => !p.draft && !isDepBot(p))
  const deps = prs.filter(isDepBot)
  const stale = real.filter((p) => daysAgo(p.created) > 14).length
  if (real.length)
    add(Math.min(real.length * 8, 32), 'serious',
      n(real.length, 'open PR') + (stale ? ` (${stale} older than 2w)` : ''))
  if (deps.length >= 3) add(6, 'warning', `${deps.length} dependency PRs piling up`)

  const issues = repo.issues ?? []
  if (issues.length) add(Math.min(issues.length * 2, 20), 'warning', n(issues.length, 'open issue'))

  if (repo.unreleased_commits >= 10)
    add(repo.unreleased_commits >= 30 ? 20 : 12, 'warning',
      `${repo.unreleased_commits} commits unreleased since ${repo.last_tag}`)

  const l = repo.local ?? {}
  if (l.dirty)
    add(l.dirty_since_days >= 7 ? 25 : 15, 'serious',
      n(l.dirty, 'uncommitted file') + (l.dirty_since_days >= 2 ? `, dirty for ${l.dirty_since_days}d` : ''))
  if (l.ahead) add(12, 'serious', n(l.ahead, 'unpushed commit'))
  if (l.behind) add(6, 'warning', `local ${l.behind} behind origin`)
  if (l.stashes) add(3, 'warning', n(l.stashes, 'stash', 'es'))

  const stray = repo.branches?.stray ?? []
  if (stray.length) {
    const merged = stray.filter((b) => b.merged).length
    add(Math.min(stray.length * 2, 12), 'warning',
      n(stray.length, 'stray branch', 'es') + (merged ? ` (${merged} merged)` : ''))
  }
  const wts = repo.branches?.worktrees ?? []
  if (wts.length) add(6, 'warning', n(wts.length, 'extra worktree'))

  const prds = repo.prds ?? { backlog: [], wip: [] }
  const wipIdle = Math.max(0, ...wipItems(prds).map((w) => w.idle_days ?? 0))
  if (prds.wip.length)
    add(wipIdle >= 14 ? 16 : 8, 'serious',
      `${prds.wip.length} PRD in progress` + (wipIdle >= 7 ? `, idle ${wipIdle}d` : ''))
  if (prds.backlog.length)
    add(Math.min(prds.backlog.length * 3, 12), 'warning', `${prds.backlog.length} PRDs in backlog`)

  if (!(repo.commits ?? []).length && issues.length) add(8, 'warning', 'idle repo with open issues')
  if (repo.errors?.length) add(5, 'warning', n(repo.errors.length, 'collection warning'))

  reasons.sort((a, b) => b.points - a.points)
  return { score: reasons.reduce((s, r) => s + r.points, 0), reasons }
}

export function aggregate(repos, sinceDays) {
  const sum = (f) => repos.reduce((s, r) => s + f(r), 0)
  return {
    repos: repos.length,
    commits: sum((r) => r.commits?.length ?? 0),
    prs: sum((r) => r.prs?.length ?? 0),
    depPrs: sum((r) => (r.prs ?? []).filter(isDepBot).length),
    issues: sum((r) => r.issues?.length ?? 0),
    failing: sum((r) => ciFailing(r).length),
    alerts: sum((r) => r.security?.length ?? 0),
    backlog: sum((r) => r.prds?.backlog.length ?? 0),
    wip: sum((r) => r.prds?.wip.length ?? 0),
    releases: sum((r) => (r.releases ?? []).filter((x) => x.date && daysAgo(x.date) <= sinceDays).length),
    localWip: repos.filter((r) => (r.local?.dirty ?? 0) + (r.local?.ahead ?? 0) > 0).length,
  }
}

export function weeklyBins(commits, sinceDays) {
  const ncols = Math.ceil(sinceDays / 7)
  const bins = Array(ncols).fill(0)
  const start = Date.now() - sinceDays * DAY
  for (const c of commits ?? []) {
    const i = Math.floor((new Date(c.date) - start) / (7 * DAY))
    if (i >= 0) bins[Math.min(i, ncols - 1)]++
  }
  return bins
}

export const weekStart = (i, sinceDays) =>
  new Date(Date.now() - sinceDays * DAY + i * 7 * DAY)
    .toLocaleDateString('en', { month: 'short', day: 'numeric' })

export function monthLabels(ncols, sinceDays) {
  let prev = ''
  return Array.from({ length: ncols }, (_, i) => {
    const m = new Date(Date.now() - sinceDays * DAY + i * 7 * DAY)
      .toLocaleDateString('en', { month: 'short' })
    const label = m === prev ? '' : m
    prev = m
    return label
  })
}

// Fixed slot per org (alphabetical), never reassigned by filtering.
export function orgSlots(repos) {
  const orgs = [...new Set(repos.map((r) => r.org))].sort()
  return new Map(orgs.map((o, i) => [o, (i % 8) + 1]))
}

const RANK = { now: 0, soon: 1, later: 2 }

// Deterministic follow-up extraction. Mechanical items only — the model step
// adds judgment items (composition, cross-repo cleanups) via epics.json todos.
// Each todo carries three mechanical axes beyond urgency:
//   importance: consequence if ignored (security, data loss, users waiting) — high|low
//   effort: quick (<10 min), medium (one sitting), deep (real work)
//   agent: a dispatchable command when the item is delegation-shaped
export function todosFor(repos) {
  const out = []
  for (const r of repos) {
    const s = slug(r)
    const gh = `https://github.com/${s}`
    const add = (kind, ref, urgency, action, why, extra = {}) =>
      out.push({ id: `${s}:${kind}:${ref}`, repo: s, kind, urgency, action, why,
        importance: 'low', effort: 'medium', agent: null, url: null, ...extra })
    for (const w of ciFailing(r))
      add('ci', w.workflow, 'now', `Fix failing CI: ${w.workflow}`,
        `${w.conclusion} on ${r.default_branch} (${w.date})`,
        { importance: 'high', effort: 'deep', url: w.url })
    const crit = secCritical(r)
    if (crit.length)
      add('security', 'crit', 'now',
        `Fix ${crit.length} critical/high security alert${crit.length > 1 ? 's' : ''}`, crit[0].title,
        { importance: 'high', url: crit[0].url || null })
    const mild = (r.security ?? []).length - crit.length
    if (mild)
      add('security', 'mild', 'soon', `Review ${mild} low/medium security alert${mild > 1 ? 's' : ''}`,
        r.security.find((a) => !crit.includes(a)).title)
    const l = r.local ?? {}
    if (l.dirty) add('local', 'dirty', 'now', `Commit or stash ${l.dirty} dirty file${l.dirty > 1 ? 's' : ''}`,
      l.dirty_since_days >= 2 ? `dirty for ${l.dirty_since_days}d — resume or park this work` : 'uncommitted work can be lost',
      { importance: 'high', effort: 'quick' })
    if (l.ahead) add('local', 'push', 'now', `Push ${l.ahead} local commit${l.ahead > 1 ? 's' : ''}`, 'unpushed work has no backup',
      { importance: 'high', effort: 'quick' })
    if (l.behind) add('local', 'pull', 'soon', `Pull ${l.behind} commit${l.behind > 1 ? 's' : ''} from origin`, 'local is behind',
      { effort: 'quick' })
    if (l.stashes) add('local', 'stash', 'later', `Review ${l.stashes} stash${l.stashes > 1 ? 'es' : ''}`, 'forgotten stashes rot',
      { effort: 'quick' })
    const prs = r.prs ?? []
    for (const p of prs.filter((x) => !x.draft && !isDepBot(x))) {
      const old = daysAgo(p.created) > 14
      const purl = `${gh}/pull/${p.number}`
      if (p.review === 'APPROVED' && p.checks === 'failing')
        add('pr', `#${p.number}`, 'now', `Fix checks on approved PR #${p.number}: ${p.title}`,
          `approved but checks failing, open ${daysAgo(p.created)}d`,
          { importance: 'high', url: purl })
      else if (p.review === 'APPROVED')
        add('pr', `#${p.number}`, 'now', `Merge approved PR #${p.number}: ${p.title}`,
          `by ${p.author}, open ${daysAgo(p.created)}d${p.checks === 'passing' ? ', checks green' : ''}`,
          { importance: 'high', effort: 'quick', url: purl })
      else
        add('pr', `#${p.number}`, old ? 'now' : 'soon', `Review PR #${p.number}: ${p.title}`,
          `by ${p.author}, open ${daysAgo(p.created)}d${p.review === 'CHANGES_REQUESTED' ? ', changes requested' : ''}`,
          { importance: 'high', url: purl })
    }
    const deps = prs.filter(isDepBot)
    if (deps.length >= 3) add('pr', 'deps', 'soon', `Batch-review ${deps.length} dependency PRs`, 'deps-bot train piling up',
      { agent: '/review-deps-prs' })
    else for (const p of deps) add('pr', `#${p.number}`, 'later', `Review deps PR #${p.number}: ${p.title}`, `by ${p.author}`,
      { effort: 'quick', agent: '/review-deps-prs', url: `${gh}/pull/${p.number}` })
    if (r.unreleased_commits >= 10) {
      const noLog = r.changelog_unreleased === false
      add('release', r.last_tag, 'soon',
        noLog ? `Add CHANGELOG entries, then release (+${r.unreleased_commits} since ${r.last_tag})`
          : `Cut a release (+${r.unreleased_commits} commits since ${r.last_tag})`,
        noLog ? '[Unreleased] section is empty'
          : r.changelog_unreleased ? 'CHANGELOG ready — users only see releases' : 'users only see releases',
        { importance: 'high' })
    }
    const issues = r.issues ?? []
    const flagged = new Set()
    for (const i of issues) {
      const iurl = `${gh}/issues/${i.number}`
      const due = i.milestone?.due
      if (due && daysAgo(due) >= -7) {
        flagged.add(i.number)
        add('issue', `#${i.number}`, daysAgo(due) >= 0 ? 'now' : 'soon',
          `Close #${i.number} for milestone ${i.milestone.title}: ${i.title}`,
          daysAgo(due) >= 0 ? `milestone overdue ${daysAgo(due)}d` : `milestone due ${due}`,
          { importance: 'high', url: iurl })
      } else if ((i.comments ?? 0) >= 3 || (i.reactions ?? 0) >= 2) {
        flagged.add(i.number)
        add('issue', `#${i.number}`, 'soon', `Respond to engaged issue #${i.number}: ${i.title}`,
          `${i.comments ?? 0} comments, ${i.reactions ?? 0} reactions`,
          { importance: 'high', url: iurl })
      }
    }
    const rest = issues.filter((i) => !flagged.has(i.number))
    if (rest.length)
      add('issue', 'triage', 'later', `Triage ${rest.length} open issue${rest.length > 1 ? 's' : ''}`,
        `oldest is ${Math.max(...rest.map((i) => daysAgo(i.created) ?? 0))}d old`,
        { agent: 'digest-github-repo' })
    const prds = r.prds ?? { backlog: [], wip: [] }
    for (const w of wipItems(prds))
      add('prd', w.title, w.idle_days >= 14 ? 'now' : 'soon', `Finish WIP PRD: ${w.title}`,
        w.idle_days >= 7 ? `idle ${w.idle_days}d in dev/local/prds/wip` : 'sitting in dev/local/prds/wip',
        { importance: 'high', effort: 'deep' })
    if (prds.backlog.length)
      add('prd', 'backlog', 'later', `Pick next PRD from backlog (${prds.backlog.length} waiting)`, `next: ${prds.backlog[0]}`,
        { effort: 'deep', agent: '/run-autopilot' })
    const stray = r.branches?.stray ?? []
    if (stray.length) {
      const merged = stray.filter((b) => b.merged).length
      add('branch', 'prune', 'later', `Prune ${stray.length} stray branch${stray.length > 1 ? 'es' : ''}`,
        merged ? `${merged} already merged into ${r.default_branch}` : `oldest: ${stray[0].name} (${stray[0].date})`,
        { effort: 'quick', agent: 'ask Claude: prune branches' })
    }
    const wts = r.branches?.worktrees ?? []
    if (wts.length)
      add('branch', 'worktrees', 'later', `Remove ${wts.length} extra worktree${wts.length > 1 ? 's' : ''}`, wts[0],
        { effort: 'quick', agent: 'ask Claude: remove worktrees' })
  }
  return out.toSorted((a, b) => RANK[a.urgency] - RANK[b.urgency] || a.repo.localeCompare(b.repo))
}

// Solo-dev Eisenhower: Delegate means "a command can do this", not "another human".
export function quadrant(t) {
  if (t.importance === 'high') return t.urgency === 'now' ? 'do' : 'schedule'
  return t.agent ? 'delegate' : 'drop'
}

// PRs outside the gita portfolio that involve the user (collect.py `external`).
export function externalTodos(external) {
  const out = []
  for (const p of external?.review_requested ?? [])
    out.push({ id: `ext:rr:${p.repo}#${p.number}`, repo: p.repo, kind: 'external', urgency: 'now',
      importance: 'high', effort: 'medium', agent: null, url: p.url, external: true,
      action: `Review requested: ${p.repo}#${p.number} ${p.title}`, why: `waiting on you since ${p.created}` })
  for (const p of external?.authored ?? [])
    out.push({ id: `ext:mine:${p.repo}#${p.number}`, repo: p.repo, kind: 'external', urgency: 'soon',
      importance: 'high', effort: 'quick', agent: null, url: p.url, external: true,
      action: `Nudge your PR ${p.repo}#${p.number}: ${p.title}`, why: `your PR outside the portfolio, open since ${p.created}` })
  return out
}

// One merged, sorted list: judgment todos (epics.json) + external + mechanical.
export function allTodos(repos, epics, external) {
  const known = new Set(repos.map(slug))
  const manual = (epics?.todos ?? [])
    .filter((t) => known.has(t.repo))
    .map((t) => ({ urgency: 'soon', kind: 'judgment', why: '', importance: 'high',
      effort: 'medium', agent: null, url: null, ...t, manual: true }))
  const seen = new Set(manual.map((t) => t.id))
  return [...manual, ...externalTodos(external), ...todosFor(repos).filter((t) => !seen.has(t.id))]
    .toSorted((a, b) => RANK[a.urgency] - RANK[b.urgency] || a.repo.localeCompare(b.repo))
}

// allTodos is already urgency-sorted; keep the first few sub-10-minute items.
export const quickWins = (todos, done, n = 6) =>
  todos.filter((t) => t.effort === 'quick' && !done.has(t.id)).slice(0, n)

// What changed vs the previous data.json snapshot (data-prev.json, if any).
// Prev scores use today's clock, so age-driven points inflate slightly — fine for arrows.
export function sinceLast(repos, prev) {
  if (!prev?.repos) return null
  const prevBy = new Map(prev.repos.map((r) => [slug(r), r]))
  const movers = repos
    .filter((r) => prevBy.has(slug(r)))
    .map((r) => ({ r, d: attention(r).score - attention(prevBy.get(slug(r))).score }))
    .filter((m) => m.d !== 0)
    .toSorted((a, b) => Math.abs(b.d) - Math.abs(a.d))
  const nowIds = new Set(todosFor(repos).map((t) => t.id))
  const prevIds = new Set(todosFor(prev.repos).map((t) => t.id))
  return {
    at: prev.generated_at,
    movers,
    added: [...nowIds].filter((id) => !prevIds.has(id)).length,
    cleared: [...prevIds].filter((id) => !nowIds.has(id)).length,
  }
}

// Portfolio trend from history.jsonl lines: open items (issues+prs+alerts+failing CI) per run.
export const historySeries = (history) =>
  (history ?? []).map((h) => ({
    at: h.at,
    open: Object.values(h.repos ?? {}).reduce((s, c) => s + (c.i ?? 0) + (c.p ?? 0) + (c.a ?? 0) + (c.f ?? 0), 0),
  }))

export function epicsFor(repo, epics) {
  const commits = repo.commits ?? []
  const bySha = new Map(commits.map((c) => [c.sha, c]))
  const grouped = new Set()
  const out = (epics?.repos?.[slug(repo)]?.epics ?? []).map((e) => {
    const cs = (e.shas ?? []).map((s) => bySha.get(s)).filter(Boolean)
    cs.forEach((c) => grouped.add(c.sha))
    return { ...e, commits: cs }
  })
  return { epics: out, rest: commits.filter((c) => !grouped.has(c.sha)) }
}
