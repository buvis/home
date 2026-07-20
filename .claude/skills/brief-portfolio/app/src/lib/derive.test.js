// Regression check for the signal→score→todo pipeline. Run: npm test (node src/lib/derive.test.js)
import assert from 'node:assert/strict'
import {
  attention, todosFor, wipItems, quadrant, externalTodos, allTodos,
  quickWins, sinceLast, historySeries,
} from './derive.js'

const repo = {
  owner: 'o',
  name: 'r',
  default_branch: 'master',
  security: [
    { kind: 'dependabot', severity: 'critical', title: 'pkg: bad', url: '' },
    { kind: 'dependabot', severity: 'low', title: 'pkg2: meh', url: '' },
  ],
  local: { dirty: 3, dirty_since_days: 11, ahead: 0, behind: 0, stashes: 0 },
  branches: {
    stray: [{ name: 'origin/old', date: '2026-01-01', merged: true }],
    worktrees: ['/tmp/wt'],
  },
  prds: { backlog: [], wip: [{ title: 'Ship X', idle_days: 20 }], done_count: 0 },
}

const texts = attention(repo).reasons.map((r) => r.text).join(' | ')
assert.match(texts, /1 critical\/high security alert/)
assert.match(texts, /1 low\/medium security alert/)
assert.match(texts, /dirty for 11d/)
assert.match(texts, /1 stray branch \(1 merged\)/)
assert.match(texts, /idle 20d/)
assert.match(texts, /1 extra worktree/)

const todos = todosFor([repo])
const ids = todos.map((t) => t.id)
assert(ids.includes('o/r:security:crit'))
assert(ids.includes('o/r:security:mild'))
assert(ids.includes('o/r:branch:prune'))
assert(ids.includes('o/r:branch:worktrees'))
assert.equal(todos.find((t) => t.id === 'o/r:prd:Ship X').urgency, 'now')
assert.match(todos.find((t) => t.id === 'o/r:local:dirty').why, /dirty for 11d/)

// pre-2026-07 data.json (wip as strings, no security/branches) still works
assert.deepEqual(wipItems({ wip: ['Old'] }), [{ title: 'Old', idle_days: null }])
const legacy = { ...repo, security: undefined, branches: undefined, prds: { backlog: [], wip: ['Old'], done_count: 0 } }
assert.equal(todosFor([legacy]).find((t) => t.id === 'o/r:prd:Old').urgency, 'soon')
assert(attention(legacy).score > 0)

// --- Eisenhower axes: importance/effort/agent → quadrant ---
const byId = (id) => todos.find((t) => t.id === id)
assert.equal(quadrant(byId('o/r:security:crit')), 'do') // now + high
assert.equal(quadrant(byId('o/r:prd:Ship X')), 'do') // wip idle 20d → now + high
assert.equal(quadrant(byId('o/r:branch:prune')), 'delegate') // low + agent
assert.equal(byId('o/r:branch:prune').effort, 'quick')
assert.equal(quadrant(byId('o/r:security:mild')), 'drop') // low, no agent
assert.equal(byId('o/r:local:dirty').effort, 'quick')
assert.equal(byId('o/r:local:dirty').importance, 'high')

const day = (d) => new Date(Date.now() - d * 86400000).toISOString().slice(0, 10)
const prRepo = {
  owner: 'o', name: 'r', default_branch: 'master',
  prs: [
    { number: 1, title: 'ok', author: 'x', draft: false, created: day(3), review: 'APPROVED', checks: 'passing', labels: [] },
    { number: 2, title: 'red', author: 'x', draft: false, created: day(3), review: 'APPROVED', checks: 'failing', labels: [] },
    { number: 3, title: 'dep', author: 'renovate', draft: false, created: day(3), review: '', checks: '', labels: [] },
  ],
  issues: [
    { number: 5, title: 'due', created: day(30), labels: [], comments: 0, reactions: 0, milestone: { title: 'v2', due: day(2) } },
    { number: 6, title: 'hot', created: day(30), labels: [], comments: 4, reactions: 0, milestone: null },
    { number: 7, title: 'quiet', created: day(30), labels: [], comments: 0, reactions: 0, milestone: null },
  ],
  unreleased_commits: 12, last_tag: 'v1', changelog_unreleased: false,
}
const prTodos = todosFor([prRepo])
assert.match(prTodos.find((t) => t.id === 'o/r:pr:#1').action, /^Merge approved/)
assert.equal(prTodos.find((t) => t.id === 'o/r:pr:#1').effort, 'quick')
assert.match(prTodos.find((t) => t.id === 'o/r:pr:#2').action, /^Fix checks on approved/)
assert.equal(prTodos.find((t) => t.id === 'o/r:pr:#3').agent, '/review-deps-prs')
assert.equal(prTodos.find((t) => t.id === 'o/r:issue:#5').urgency, 'now') // milestone overdue
assert.match(prTodos.find((t) => t.id === 'o/r:issue:#6').action, /engaged issue/)
assert.match(prTodos.find((t) => t.id === 'o/r:issue:triage').action, /Triage 1 open issue/) // #7 only
assert.match(prTodos.find((t) => t.kind === 'release').action, /CHANGELOG entries/)

// --- brush cadence: nag at >=30d or never; id rolls with the last-run date ---
const brushTodo = todos.find((t) => t.kind === 'brush') // base repo has no brush_last_run
assert.equal(brushTodo.id, 'o/r:brush:never')
assert.equal(brushTodo.agent, '/brush')
assert.equal(quadrant(brushTodo), 'delegate')
assert.match(attention(repo).reasons.map((x) => x.text).join(' | '), /never brushed/)
const brushed45 = { ...repo, brush_last_run: day(45) }
assert.match(todosFor([brushed45]).find((t) => t.kind === 'brush').why, /45d ago/)
assert.equal(todosFor([brushed45]).find((t) => t.kind === 'brush').id, `o/r:brush:${day(45)}`)
assert.match(attention(brushed45).reasons.map((x) => x.text).join(' | '), /brush overdue \(45d ago\)/)
assert(todosFor([{ ...repo, brush_last_run: day(30) }]).some((t) => t.kind === 'brush')) // boundary: due at 30
const freshBrush = { ...repo, brush_last_run: day(10) }
assert.equal(todosFor([freshBrush]).find((t) => t.kind === 'brush'), undefined)
assert(!attention(freshBrush).reasons.some((x) => /brush/.test(x.text)))

// --- external PRs (outside the portfolio) ---
const ext = externalTodos({
  review_requested: [{ repo: 'a/b', number: 9, title: 'T', created: '2026-07-01', url: 'u' }],
  authored: [{ repo: 'c/d', number: 2, title: 'M', created: '2026-07-01', url: 'u2' }],
})
assert.equal(ext[0].urgency, 'now')
assert.equal(quadrant(ext[0]), 'do')
assert.equal(ext[1].effort, 'quick')

// --- ~/.claude maintenance nag (PRD 00081): fires at >=30d or never, silent when fresh ---
// (`day(n)` is defined below in the brush-cadence block; both blocks share it.)
const maintNever = externalTodos({ review_requested: [], authored: [] }).find((t) => t.kind === 'maintenance')
assert.equal(maintNever.id, 'claude:maintenance:never')
assert.match(maintNever.action, /audit-filesystem/)
const maint45 = externalTodos({ claude_maintenance_last: day(45) }).find((t) => t.kind === 'maintenance')
assert.match(maint45.why, /45d old/)
assert.equal(maint45.id, `claude:maintenance:${day(45)}`)
assert(externalTodos({ claude_maintenance_last: day(30) }).some((t) => t.kind === 'maintenance')) // due at 30
assert.equal(externalTodos({ claude_maintenance_last: day(10) }).find((t) => t.kind === 'maintenance'), undefined)
assert.equal(externalTodos(null).length, 0) // no external payload -> no nag, no crash

// --- merged list + quick wins ---
const all = allTodos([repo], { todos: [{ id: 'o/r:judgment:x', repo: 'o/r', kind: 'judgment', urgency: 'now', action: 'A', why: 'w' }] }, null)
assert.equal(all.find((t) => t.id === 'o/r:judgment:x').importance, 'high') // judgment defaults
const wins = quickWins(all, new Set())
assert(wins.every((t) => t.effort === 'quick'))
assert(wins.some((t) => t.id === 'o/r:local:dirty'))
assert.equal(quickWins(all, new Set(['o/r:local:dirty'])).find((t) => t.id === 'o/r:local:dirty'), undefined)

// --- since-last-brief diff ---
const prevRepo = { ...repo, local: { ...repo.local, dirty: 0 } }
const diff = sinceLast([repo], { generated_at: '2026-07-10T00:00:00+00:00', repos: [prevRepo] })
assert.equal(diff.at, '2026-07-10T00:00:00+00:00')
assert(diff.added >= 1) // dirty todo is new
assert(diff.movers[0].d > 0) // score went up
assert.equal(sinceLast([repo], null), null)

// --- history trend ---
const series = historySeries([
  { at: 'd1', repos: { 'o/r': { i: 2, p: 1, a: 0, f: 1 } } },
  { at: 'd2', repos: { 'o/r': { i: 1, p: 0, a: 0, f: 0 } } },
])
assert.deepEqual(series.map((h) => h.open), [4, 1])

console.log('derive.test.js: all assertions passed')
