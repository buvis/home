import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  actionsCsv, actionsMarkdown, adrMarkdown, fmtDur, fmtTime, gini, highlight, markers,
  nearestTurn, speakerIndex, topShare,
} from './derive.js'

const TURNS = [
  { i: 0, t: 0, end: 10, s: 's0', text: 'we start' },
  { i: 1, t: 10, end: 40, s: 's1', text: 'I disagree' },
  { i: 2, t: 60, end: 90, s: 's0', text: 'fine' },
]

test('formats minutes without a leading zero hour', () => {
  assert.equal(fmtTime(0), '0:00')
  assert.equal(fmtTime(754), '12:34')
  assert.equal(fmtTime(3754), '1:02:34')
})

test('shows a placeholder when a timecode is missing', () => {
  assert.equal(fmtTime(null), '--:--')
  assert.equal(fmtDur(0), '—')
})

test('renders long durations in hours and minutes', () => {
  assert.equal(fmtDur(2520), '42 min')
  assert.equal(fmtDur(4320), '1 h 12 min')
})

test('keeps short spans in seconds rather than rounding them away', () => {
  assert.equal(fmtDur(25), '25s')
  assert.equal(fmtDur(89), '89s')
  assert.equal(fmtDur(95), '2 min')
})

test('resolves a timecode to the turn that covers it', () => {
  assert.equal(nearestTurn(TURNS, 20), 1)
  assert.equal(nearestTurn(TURNS, 0), 0)
})

test('falls back to the last turn before an uncovered timecode', () => {
  assert.equal(nearestTurn(TURNS, 50), 1) // inside the gap between turns
  assert.equal(nearestTurn(TURNS, 999), 2)
})

test('reports no turn for a missing timecode', () => {
  assert.equal(nearestTurn(TURNS, null), -1)
})

test('scores an even split as no dominance', () => {
  assert.equal(gini([25, 25, 25, 25]), 0)
})

test('scores a monologue as near-total dominance', () => {
  assert.ok(gini([97, 1, 1, 1]) > 0.7)
})

test('sums the loudest voices for the dominance headline', () => {
  const speakers = [{ share_words: 50 }, { share_words: 30 }, { share_words: 20 }]
  assert.equal(topShare(speakers, 2), 80)
})

test('assigns neighbouring speakers distinct colour slots', () => {
  const index = speakerIndex([{ id: 's0' }, { id: 's1' }])
  assert.notEqual(index.get('s0').color, index.get('s1').color)
})

test('marks every occurrence of the search term', () => {
  const parts = highlight('Kafka then Kafka', 'kafka')
  assert.deepEqual(parts.filter((p) => p.hit).map((p) => p.text), ['Kafka', 'Kafka'])
  assert.equal(parts.map((p) => p.text).join(''), 'Kafka then Kafka')
})

test('leaves text untouched when the search box is empty', () => {
  assert.deepEqual(highlight('hello', '  '), [{ text: 'hello', hit: false }])
})

test('writes an ADR carrying its source timecode and alternatives', () => {
  const adr = adrMarkdown(
    {
      title: 'Use Postgres',
      status: 'made',
      decision: 'Postgres for the new store',
      decider: 'A. Example',
      context: 'Two candidates were on the table.',
      alternatives: [{ option: 'MySQL', why_not: 'no partial indexes' }],
      consequences: ['ops must learn tuning'],
      t: 754,
    },
    { title: 'Design sync', date: '2026-08-06' },
  )
  assert.match(adr, /# ADR: Use Postgres/)
  assert.match(adr, /- Date: 2026-08-06/)
  assert.match(adr, /Design sync @ 12:34/)
  assert.match(adr, /\*\*MySQL\*\* — not chosen: no partial indexes/)
  assert.match(adr, /- ops must learn tuning/)
})

test('flags an unassigned action in the markdown export', () => {
  const md = actionsMarkdown([{ action: 'Ship it', t: 60, due: '2026-08-13' }])
  assert.equal(md, '- [ ] Ship it — _unassigned_ (due 2026-08-13) `1:00`')
})

test('quotes embedded quotation marks in the csv export', () => {
  const csv = actionsCsv([{ action: 'Say "hi"', assignee: 'A. Example', t: 0 }])
  assert.match(csv, /"Say ""hi"""/)
  assert.equal(csv.split('\n').length, 2)
})

test('collects timecoded findings of every kind as timeline markers', () => {
  const found = markers({
    decisions: [{ title: 'D', t: 100 }],
    actions: [{ action: 'A', t: 50 }],
    questions: [{ q: 'Q', t: 10 }],
    risks: [{ risk: 'R' }], // no timecode — must not appear
  })
  assert.deepEqual(found.map((m) => m.kind), ['question', 'action', 'decision'])
  assert.deepEqual(found.map((m) => m.t), [10, 50, 100])
})
