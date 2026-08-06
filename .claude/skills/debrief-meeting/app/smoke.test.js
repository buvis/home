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
}

function render() {
  const page = readFileSync(TEMPLATE, 'utf8').replace(
    '__MEETING_PAYLOAD__',
    JSON.stringify(PAYLOAD).replace(/<\//g, '<\\/'),
  )
  // jsdom does not run type="module", and running the bundle inline would fire
  // before #app exists. Lift it out and eval it once the document is built —
  // same code, same order a deferred module script would give it.
  const [tag, bundle] = page.match(/<script type="module"[^>]*>([\s\S]*?)<\/script>/)
  const errors = []
  const dom = new JSDOM(page.replace(tag, ''), {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: new VirtualConsole().on('jsdomError', (e) => errors.push(e)),
  })
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

test('builds an ADR from a decision on demand', async () => {
  const { doc, openTab, clickText } = render()
  await openTab('Decisions')
  await clickText('.chip', 'Show ADR')
  const adr = doc.querySelector('main pre').textContent
  assert.match(adr, /# ADR: Use Postgres/)
  assert.match(adr, /\*\*SQL Server\*\* — not chosen: cost/)
})
