// Renders the built single-file page in jsdom. Catches the runtime breakage a
// successful `vite build` cannot: a missing field, a bad lookup, a dead tab.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JSDOM, VirtualConsole } from 'jsdom'

const TEMPLATE = new URL('../assets/template.html', import.meta.url)

const PAYLOAD = {
  transcript: {
    meta: { duration: 135, cues: 4, turns: 3, words: 30, has_timecodes: true },
    speakers: [
      { id: 's0', name: 'Anna Novak', words: 20, turns: 2, seconds: 40, share_words: 66.7,
        share_time: 66.7, wpm: 30, questions: 1, interruptions: 0, longest_turn: 25,
        first_t: 2, last_t: 120 },
      { id: 's1', name: 'Tomas Bouska', words: 10, turns: 1, seconds: 20, share_words: 33.3,
        share_time: 33.3, wpm: 30, questions: 0, interruptions: 1, longest_turn: 20,
        first_t: 12, last_t: 32 },
    ],
    turns: [
      { t: 2, end: 11, text: 'Agenda today is the store migration.', i: 0, s: 's0' },
      { t: 12, end: 32, text: 'Works for me, I have a hard stop.', i: 1, s: 's1' },
      { t: 52.5, end: 120, text: 'Then we go with Postgres.', i: 2, s: 's0',
        raw: 'Then we go with postgres.' },
    ],
    matrix: { s0: { s1: 1 }, s1: { s0: 1 } },
    buckets: { size: 67.5, series: [{ t: 0, by: { s0: 8, s1: 9 } }, { t: 67.5, by: { s0: 13 } }] },
    corrections: [{ kind: 'speaker-merge', from: 'Novak, Anna', to: 'Anna Novak' }],
    warnings: [],
  },
  extract: {
    meta: { title: 'Store migration sync', date: '2026-08-06', platform: 'Teams' },
    tldr: ['Postgres wins on licence cost.'],
    summary: 'One paragraph.\n\nAnother paragraph.',
    agenda: [{ title: 'Store migration', planned: true, t: 2, end: 120, coverage: 'full' }],
    topics: [{ id: 't1', title: 'Store migration', t: 2, end: 120, summary: 'Picked Postgres.',
               notes: ['42k licence'] }],
    decisions: [{ id: 'd1', title: 'Use Postgres', t: 52.5, status: 'made',
                  decision: 'Migrate to Postgres.', decider: 'Anna Novak', context: 'Licensing.',
                  alternatives: [{ option: 'SQL Server', why_not: 'cost' }],
                  consequences: ['ops tuning'], confidence: 'high' }],
    actions: [{ id: 'a1', action: 'Talk to reporting', assignee: 'Tomas Bouska',
                due: '2026-08-13', t: 12 }],
    questions: [{ q: 'Can reporting move?', asked_by: 'Anna Novak', t: 12, answered: false }],
    risks: [{ risk: 'Reporting reads the old store', raised_by: 'Tomas Bouska', t: 12,
              severity: 'high', addressed: false }],
    entities: { systems: ['PostgreSQL'], metrics: [{ label: 'licence', value: '42k', t: 12 }] },
    glossary: [{ term: 'autovacuum', definition: 'reclaims dead rows', t: 52.5 }],
    quotes: [{ text: 'Then we go with Postgres.', who: 'Anna Novak', t: 52.5 }],
    quality: { on_topic_ratio: 0.95, notes: ['closed every item'] },
    dynamics: ['Anna chaired.'],
    email: 'Subject: outcomes',
  },
  extract_ran: true,
}

function render(payload = PAYLOAD, { storage } = {}) {
  const page = readFileSync(TEMPLATE, 'utf8').replace(
    '__MEETING_PAYLOAD__',
    JSON.stringify(payload).replace(/<\//g, '<\\/'),
  )
  // jsdom does not run type="module", and running the bundle inline would fire
  // before #app exists. Lift it out and eval it once the document is built —
  // same code, same order a deferred module script would give it.
  const [tag, bundle] = page.match(/<script type="module"[^>]*>([\s\S]*?)<\/script>/)
  const errors = []
  const dom = new JSDOM(page.replace(tag, ''), {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    // jsdom treats the default about:blank as an opaque origin, where
    // localStorage throws instead of working — give it a real origin so the
    // app's own localStorage use behaves as it would in a browser.
    url: 'https://example.org/',
    virtualConsole: new VirtualConsole().on('jsdomError', (e) => errors.push(e)),
  })
  for (const [key, value] of Object.entries(storage ?? {})) {
    dom.window.localStorage.setItem(key, value)
  }
  dom.window.eval(bundle)
  assert.deepEqual(errors.map((e) => e.message), [], 'the page threw while mounting')
  const doc = dom.window.document
  // Svelte 5 applies updates in a microtask, so every click needs a flush
  const flush = () => new Promise((resolve) => dom.window.setTimeout(resolve, 0))
  const openTab = async (label) => {
    const button = [...doc.querySelectorAll('nav.tabs button')].find((b) =>
      b.textContent.trim().startsWith(label),
    )
    assert.ok(button, `missing tab ${label}`)
    button.click()
    await flush()
    return button
  }
  const clickText = async (selector, text) => {
    const node = [...doc.querySelectorAll(selector)].find((n) => n.textContent.trim() === text)
    assert.ok(node, `no ${selector} reading "${text}"`)
    node.click()
    await flush()
  }
  return { doc, flush, openTab, clickText }
}

test('mounts the page and shows the meeting title', () => {
  const { doc } = render()
  assert.equal(doc.querySelector('h1').textContent.trim(), 'Store migration sync')
  assert.match(doc.querySelector('.subtitle').textContent, /2026-08-06/)
})

test('opens on the brief with the headline counts', () => {
  const { doc } = render()
  const tiles = [...doc.querySelectorAll('.tile')].map((t) => t.textContent.replace(/\s+/g, ''))
  assert.ok(tiles.includes('1decisions'), `tiles were: ${tiles.join(' | ')}`)
  assert.ok(tiles.includes('1liverisks'), `tiles were: ${tiles.join(' | ')}`)
  assert.match(doc.body.textContent, /Postgres wins on licence cost/)
})

test('every tab shows its own content', async () => {
  const { doc, openTab } = render()
  const expected = {
    Brief: /At a glance/,
    Timeline: /What was discussed/,
    Actions: /Talk to reporting/,
    Decisions: /Use Postgres/,
    People: /Airtime/,
    Transcript: /Agenda today is the store migration/,
    Insights: /Risks raised/,
  }
  for (const [label, pattern] of Object.entries(expected)) {
    await openTab(label)
    assert.match(doc.querySelector('main').textContent, pattern, `${label} tab is wrong`)
  }
})

test('a timecode chip moves the reader to that turn in the transcript', async () => {
  const { doc, openTab, clickText } = render()
  await openTab('Decisions')
  await clickText('main .cue', '0:53') // decision sits at t=52.5
  const transcriptTab = [...doc.querySelectorAll('nav.tabs button')].find((b) =>
    b.textContent.trim().startsWith('Transcript'),
  )
  assert.equal(transcriptTab.getAttribute('aria-current'), 'page')
  assert.match(doc.querySelector('.turn.focused').textContent, /Then we go with Postgres/)
})

test('marks a corrected turn and can show the original wording', async () => {
  const { doc, openTab, clickText } = render()
  await openTab('Transcript')
  assert.match(doc.querySelector('main').textContent, /edited/)
  await clickText('.chip', 'original wording')
  assert.match(doc.querySelector('main').textContent, /Then we go with postgres\./)
})

test('the transcript search input has an accessible name and the turn count is announced', async () => {
  const { doc, openTab } = render()
  await openTab('Transcript')
  const searchInput = doc.querySelector('main input[type="search"]')
  assert.ok(searchInput, 'missing the transcript search input')
  assert.equal(searchInput.getAttribute('aria-label'), 'Search the transcript')
  const count = doc.querySelector('main .muted')
  assert.ok(count, 'missing the turn count element')
  assert.equal(count.getAttribute('aria-live'), 'polite')
  assert.equal(count.textContent.trim(), '3 of 3 turns')
})

test('builds an ADR from a decision on demand', async () => {
  const { doc, openTab, clickText } = render()
  await openTab('Decisions')
  await clickText('.chip', 'Show ADR')
  const adr = doc.querySelector('main pre').textContent
  assert.match(adr, /# ADR: Use Postgres/)
  assert.match(adr, /\*\*SQL Server\*\* — not chosen: cost/)
})

test('an action with no id stays ticked by its own text, not its position in the list', async () => {
  const payload = structuredClone(PAYLOAD)
  const text = 'Draft the migration runbook'
  payload.extract.actions = [{ action: text, assignee: 'Anna Novak', due: '2026-08-20', t: 30 }]
  const { doc, openTab } = render(payload, {
    storage: { 'debrief-done:Store migration sync': JSON.stringify([text]) },
  })
  await openTab('Actions')
  const row = [...doc.querySelectorAll('main tbody tr')].find((tr) => tr.textContent.includes(text))
  assert.ok(row, 'missing the row for the seeded action')
  const checkbox = row.querySelector('input[type=checkbox]')
  assert.ok(checkbox, 'missing the row checkbox')
  assert.equal(checkbox.checked, true, 'a ticked action with no id should stay checked after rebuild')
})

test('brief tiles show numeric counts and no not-run note when extract_ran is absent from the payload', async () => {
  const payload = structuredClone(PAYLOAD)
  delete payload.extract_ran
  const { doc, openTab } = render(payload)
  await openTab('Brief')
  const tiles = [...doc.querySelectorAll('.tile')].map((t) => t.textContent.replace(/\s+/g, ''))
  assert.ok(tiles.includes('1decisions'), `tiles were: ${tiles.join(' | ')}`)
  assert.ok(tiles.includes('1actions'), `tiles were: ${tiles.join(' | ')}`)
  assert.ok(tiles.includes('1openquestions'), `tiles were: ${tiles.join(' | ')}`)
  assert.ok(!tiles.some((t) => t.includes('—')), `a tile showed the em-dash placeholder: ${tiles.join(' | ')}`)
  assert.doesNotMatch(doc.querySelector('main').textContent, /extraction step hasn't run/)
})

// The test above covers the absent-field fallback (absence reads as "ran").
// These cover the other side: when extraction never ran, the tiles and empty
// states must say so instead of showing a false zero.
test('brief tiles show em dashes and a not-run note when extraction did not run', () => {
  const payload = structuredClone(PAYLOAD)
  payload.extract_ran = false
  payload.extract = {}
  const { doc } = render(payload)
  const tiles = [...doc.querySelectorAll('.tile')].map((t) => t.textContent.replace(/\s+/g, ''))
  assert.ok(tiles.includes('—decisions'), `tiles were: ${tiles.join(' | ')}`)
  assert.ok(tiles.includes('—actions'), `tiles were: ${tiles.join(' | ')}`)
  assert.ok(tiles.includes('—openquestions'), `tiles were: ${tiles.join(' | ')}`)
  assert.equal(
    doc.querySelector('main .muted').textContent.trim(),
    "The extraction step hasn't run — decisions, actions, and open questions above are not counted.",
  )
})

test('decisions tab shows the not-run message when extraction did not run', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.extract_ran = false
  payload.extract = {}
  const { doc, openTab } = render(payload)
  await openTab('Decisions')
  assert.equal(
    doc.querySelector('main .empty').textContent.trim(),
    "The extraction step hasn't run — no decisions to show yet.",
  )
})

test('actions tab shows the not-run message when extraction did not run', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.extract_ran = false
  payload.extract = {}
  const { doc, openTab } = render(payload)
  await openTab('Actions')
  assert.equal(
    doc.querySelector('main .empty').textContent.trim(),
    "The extraction step hasn't run — no actions to show yet.",
  )
})

test('decisions tab still reports none extracted when extraction ran but found nothing', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.extract_ran = true
  payload.extract.decisions = []
  const { doc, openTab } = render(payload)
  await openTab('Decisions')
  assert.equal(
    doc.querySelector('main .empty').textContent.trim(),
    'No decisions were extracted from this meeting.',
  )
})

// Regression: {#each} blocks keyed by a list item's own value (instead of a
// stable id or index) throw `each_key_duplicate` when two items share that
// value — on the default tab this blanks the whole page at mount (zero body
// characters); on other tabs it silently breaks the tab switch. Either way,
// duplicate-valued items should render twice, not crash.

// Each row clones PAYLOAD, mutates one field to hold a duplicate, opens the
// tab that renders it, and counts how many times the duplicated string
// appears in `main`. Counts vary: most fields render once per entry (2 dupes
// -> 2), but a timeline topic's title renders in both the lane strip and the
// "What was discussed" card, so two duplicate topics -> 4.
const DUPLICATE_CASES = [
  {
    name: 'renders duplicate tldr bullets on the brief instead of crashing',
    mutate: (payload) => {
      payload.extract.tldr = ['Duplicate insight bullet.', 'Duplicate insight bullet.']
    },
    tab: 'Brief',
    text: 'Duplicate insight bullet.',
    count: 2,
  },
  {
    name: 'renders duplicate agenda titles on the brief instead of crashing',
    mutate: (payload) => {
      payload.extract.agenda = [
        { title: 'Duplicate Agenda Item', planned: true, t: 2, end: 60, coverage: 'full' },
        { title: 'Duplicate Agenda Item', planned: false, t: 61, end: 120, coverage: 'partial' },
      ]
    },
    tab: 'Brief',
    text: 'Duplicate Agenda Item',
    count: 2,
  },
  {
    name: 'renders duplicate followups on the brief instead of crashing',
    mutate: (payload) => {
      payload.extract.followups = [
        { what: 'Duplicate followup text.', when: 'next sync', who: 'Anna Novak' },
        { what: 'Duplicate followup text.', when: 'next sync', who: 'Anna Novak' },
      ]
    },
    tab: 'Brief',
    text: 'Duplicate followup text.',
    count: 2,
  },
  {
    name: 'renders duplicate transcript warnings on the brief instead of crashing',
    mutate: (payload) => {
      payload.transcript.warnings = ['Duplicate transcript warning.', 'Duplicate transcript warning.']
    },
    tab: 'Brief',
    text: 'Duplicate transcript warning.',
    count: 2,
  },
  {
    name: 'renders duplicate risks on the insights tab instead of crashing',
    mutate: (payload) => {
      payload.extract.risks = [
        { risk: 'Duplicate risk text.', raised_by: 'Tomas Bouska', t: 12, severity: 'high',
          addressed: false },
        { risk: 'Duplicate risk text.', raised_by: 'Anna Novak', t: 40, severity: 'medium',
          addressed: true },
      ]
    },
    tab: 'Insights',
    text: 'Duplicate risk text.',
    count: 2,
  },
  {
    name: 'renders duplicate quality notes on the insights tab instead of crashing',
    mutate: (payload) => {
      payload.extract.quality = {
        on_topic_ratio: 0.95,
        notes: ['Duplicate quality note.', 'Duplicate quality note.'],
      }
    },
    tab: 'Insights',
    text: 'Duplicate quality note.',
    count: 2,
  },
  {
    name: 'renders duplicate blockers on the insights tab instead of crashing',
    mutate: (payload) => {
      payload.extract.blockers = [
        { what: 'Duplicate blocker text.', depends_on: 'Vendor SLA', t: 20 },
        { what: 'Duplicate blocker text.', depends_on: 'Vendor SLA', t: 40 },
      ]
    },
    tab: 'Insights',
    text: 'Duplicate blocker text.',
    count: 2,
  },
  {
    name: 'renders duplicate assumptions on the insights tab instead of crashing',
    mutate: (payload) => {
      payload.extract.assumptions = [
        { assumption: 'Duplicate assumption text.', validated: false, t: 10 },
        { assumption: 'Duplicate assumption text.', validated: true, t: 20 },
      ]
    },
    tab: 'Insights',
    text: 'Duplicate assumption text.',
    count: 2,
  },
  {
    name: 'renders duplicate quotes on the insights tab instead of crashing',
    mutate: (payload) => {
      payload.extract.quotes = [
        { text: 'Duplicate quoted text.', who: 'Anna Novak', t: 10 },
        { text: 'Duplicate quoted text.', who: 'Tomas Bouska', t: 20 },
      ]
    },
    tab: 'Insights',
    text: 'Duplicate quoted text.',
    count: 2,
  },
  {
    name: 'renders duplicate glossary terms on the insights tab instead of crashing',
    mutate: (payload) => {
      payload.extract.glossary = [
        { term: 'DuplicateTerm', definition: 'First definition.', t: 10 },
        { term: 'DuplicateTerm', definition: 'Second definition.', t: 20 },
      ]
    },
    tab: 'Insights',
    text: 'DuplicateTerm',
    count: 2,
  },
  {
    name: 'renders duplicate dynamics notes on the people tab instead of crashing',
    mutate: (payload) => {
      payload.extract.dynamics = ['Duplicate dynamics note.', 'Duplicate dynamics note.']
    },
    tab: 'People',
    text: 'Duplicate dynamics note.',
    count: 2,
  },
  {
    name: 'renders a decision sharing a title with no id instead of crashing',
    mutate: (payload) => {
      payload.extract.decisions = [
        {
          title: 'Use Postgres',
          t: 52.5,
          status: 'made',
          decision: 'Migrate to Postgres.',
          decider: 'Anna Novak',
          context: 'Licensing.',
          alternatives: [{ option: 'SQL Server', why_not: 'cost' }],
          consequences: ['ops tuning'],
          confidence: 'high',
        },
        {
          title: 'Use Postgres',
          t: 90,
          status: 'made',
          decision: 'Second duplicate decision entry.',
          decider: 'Tomas Bouska',
          context: 'Duplicate context.',
          alternatives: [],
          consequences: [],
          confidence: 'medium',
        },
      ]
    },
    tab: 'Decisions',
    text: 'Use Postgres',
    count: 2,
  },
  {
    name: 'renders two topics sharing a title with no id instead of crashing',
    mutate: (payload) => {
      payload.extract.topics = [
        { title: 'Duplicate Topic Title', t: 10, end: 20, summary: 'First summary.',
          notes: ['note one'] },
        { title: 'Duplicate Topic Title', t: 30, end: 40, summary: 'Second summary.',
          notes: ['note two'] },
      ]
    },
    tab: 'Timeline',
    text: 'Duplicate Topic Title',
    // the title renders once in the lane strip and once in the "What was
    // discussed" card, per topic: 2 topics x 2 places = 4.
    count: 4,
  },
  {
    name: 'renders duplicate notes within a timeline topic instead of crashing',
    mutate: (payload) => {
      payload.extract.topics[0].notes = ['Duplicate topic note.', 'Duplicate topic note.']
    },
    tab: 'Timeline',
    text: 'Duplicate topic note.',
    count: 2,
  },
]

for (const { name, mutate, tab, text, count } of DUPLICATE_CASES) {
  test(name, async () => {
    const payload = structuredClone(PAYLOAD)
    mutate(payload)
    const { doc, openTab } = render(payload)
    await openTab(tab)
    const main = doc.querySelector('main').textContent
    assert.ok(main.length > 0, 'main was empty')
    const found = main.split(text).length - 1
    assert.equal(found, count, `expected "${text}" to render ${count} times, main was: ${main}`)
  })
}

test('a zero-hit correction shows the not-found badge, distinct from an applied one', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.transcript.corrections = [
    { from: 'Teh', to: 'The', applied: 0 },
    { from: 'Novak, Anna', to: 'Anna Novak', applied: 2 },
  ]
  const { doc, openTab } = render(payload)
  await openTab('Insights')

  const section = [...doc.querySelectorAll('main section.sec')].find(
    (s) => s.querySelector('h2')?.textContent.trim() === 'Cleanup applied',
  )
  assert.ok(section, 'missing the Cleanup applied section')
  const items = [...section.querySelectorAll('ul > li')]
  assert.equal(
    items.length,
    2,
    `expected 2 correction rows, got: ${items.map((li) => li.textContent.trim())}`,
  )

  const notFound = items.find((li) => li.textContent.includes('not found'))
  const applied = items.find((li) => li.textContent.includes('(2×)'))
  assert.ok(notFound, `no correction row read "not found": ${items.map((li) => li.textContent.trim())}`)
  assert.ok(applied, `no correction row read "(2×)": ${items.map((li) => li.textContent.trim())}`)
  assert.notEqual(notFound.textContent.trim(), applied.textContent.trim())

  const badge = notFound.querySelector('.lbl.sev-warning')
  assert.ok(badge, 'the not-found row is missing the .lbl.sev-warning badge')
  assert.equal(badge.textContent.trim(), 'not found')
  assert.ok(
    !/\(\d+×\)/.test(notFound.textContent),
    `the not-found row should not show an applied count: ${notFound.textContent.trim()}`,
  )
})

test('insights tab shows the not-run message when extraction never ran and there is nothing to show', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.extract_ran = false
  payload.extract = {}
  payload.transcript.corrections = []
  const { doc, openTab } = render(payload)
  await openTab('Insights')
  assert.equal(
    doc.querySelector('main .empty').textContent.trim(),
    "The extraction step hasn't run — nothing to show yet.",
  )
})

test('insights tab reports nothing to show when extraction ran but found nothing', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.extract_ran = true
  payload.extract = {}
  payload.transcript.corrections = []
  const { doc, openTab } = render(payload)
  await openTab('Insights')
  assert.equal(
    doc.querySelector('main .empty').textContent.trim(),
    'Nothing to show for this meeting.',
  )
})
