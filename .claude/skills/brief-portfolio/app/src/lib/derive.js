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
  if (l.dirty) add(15, 'serious', n(l.dirty, 'uncommitted file'))
  if (l.ahead) add(12, 'serious', n(l.ahead, 'unpushed commit'))
  if (l.behind) add(6, 'warning', `local ${l.behind} behind origin`)
  if (l.stashes) add(3, 'warning', n(l.stashes, 'stash', 'es'))

  const prds = repo.prds ?? { backlog: [], wip: [] }
  if (prds.wip.length) add(8, 'serious', `${prds.wip.length} PRD in progress`)
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

// Deterministic follow-up extraction. Mechanical items only — the model step
// adds judgment items (composition, cross-repo cleanups) via epics.json todos.
export function todosFor(repos) {
  const out = []
  for (const r of repos) {
    const s = slug(r)
    const add = (kind, ref, urgency, action, why) =>
      out.push({ id: `${s}:${kind}:${ref}`, repo: s, kind, urgency, action, why })
    for (const w of ciFailing(r))
      add('ci', w.workflow, 'now', `Fix failing CI: ${w.workflow}`,
        `${w.conclusion} on ${r.default_branch} (${w.date})`)
    const l = r.local ?? {}
    if (l.dirty) add('local', 'dirty', 'now', `Commit or stash ${l.dirty} dirty file${l.dirty > 1 ? 's' : ''}`, 'uncommitted work can be lost')
    if (l.ahead) add('local', 'push', 'now', `Push ${l.ahead} local commit${l.ahead > 1 ? 's' : ''}`, 'unpushed work has no backup')
    if (l.behind) add('local', 'pull', 'soon', `Pull ${l.behind} commit${l.behind > 1 ? 's' : ''} from origin`, 'local is behind')
    if (l.stashes) add('local', 'stash', 'later', `Review ${l.stashes} stash${l.stashes > 1 ? 'es' : ''}`, 'forgotten stashes rot')
    const prs = r.prs ?? []
    for (const p of prs.filter((x) => !x.draft && !isDepBot(x))) {
      const old = daysAgo(p.created) > 14
      add('pr', `#${p.number}`, p.review === 'APPROVED' || old ? 'now' : 'soon',
        `${p.review === 'APPROVED' ? 'Merge approved' : 'Review'} PR #${p.number}: ${p.title}`,
        `by ${p.author}, open ${daysAgo(p.created)}d${p.review === 'CHANGES_REQUESTED' ? ', changes requested' : ''}`)
    }
    const deps = prs.filter(isDepBot)
    if (deps.length >= 3) add('pr', 'deps', 'soon', `Batch-review ${deps.length} dependency PRs`, 'deps-bot train piling up')
    else for (const p of deps) add('pr', `#${p.number}`, 'later', `Review deps PR #${p.number}: ${p.title}`, `by ${p.author}`)
    if (r.unreleased_commits >= 10)
      add('release', r.last_tag, 'soon', `Cut a release (+${r.unreleased_commits} commits since ${r.last_tag})`, 'users only see releases')
    const issues = r.issues ?? []
    if (issues.length)
      add('issue', 'triage', 'later', `Triage ${issues.length} open issue${issues.length > 1 ? 's' : ''}`,
        `oldest is ${Math.max(...issues.map((i) => daysAgo(i.created) ?? 0))}d old`)
    const prds = r.prds ?? { backlog: [], wip: [] }
    for (const t of prds.wip) add('prd', t, 'soon', `Finish WIP PRD: ${t}`, 'sitting in dev/local/prds/wip')
    if (prds.backlog.length)
      add('prd', 'backlog', 'later', `Pick next PRD from backlog (${prds.backlog.length} waiting)`, `next: ${prds.backlog[0]}`)
  }
  const rank = { now: 0, soon: 1, later: 2 }
  return out.toSorted((a, b) => rank[a.urgency] - rank[b.urgency] || a.repo.localeCompare(b.repo))
}

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
