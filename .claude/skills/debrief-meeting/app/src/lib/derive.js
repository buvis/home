// Pure derivations from the injected payload. No fetches — the file is self-contained.

export const COLORS = [
  'var(--cat1)', 'var(--cat2)', 'var(--cat3)', 'var(--cat4)',
  'var(--cat5)', 'var(--cat6)', 'var(--cat7)', 'var(--cat8)',
]

export function loadPayload() {
  try {
    const node = document.getElementById('meeting-payload')
    const parsed = JSON.parse(node.textContent)
    if (!parsed.transcript?.turns) throw new Error('missing transcript.turns')
    return parsed
  } catch {
    return null
  }
}

export function fmtTime(seconds) {
  if (seconds === null || seconds === undefined) return '--:--'
  const total = Math.max(0, Math.round(seconds))
  const mm = String(Math.floor(total / 60) % 60).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  const hh = Math.floor(total / 3600)
  return hh ? `${hh}:${mm}:${ss}` : `${Number(mm)}:${ss}`
}

export function fmtDur(seconds) {
  if (!seconds) return '—'
  if (seconds < 90) return `${Math.round(seconds)}s` // a 25s turn is not "0 min"
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)} h ${String(mins % 60).padStart(2, '0')} min`
}

export function speakerIndex(speakers = []) {
  return new Map(speakers.map((s, i) => [s.id, { ...s, color: COLORS[i % COLORS.length] }]))
}

/** Turn covering t, else the last turn that started before it. -1 when untimed. */
export function nearestTurn(turns, t) {
  if (t === null || t === undefined) return -1
  let best = -1
  for (const turn of turns) {
    if (turn.t === null) continue
    if (turn.t > t) break
    best = turn.i
    if (turn.end !== null && t <= turn.end) return turn.i
  }
  return best
}

/** 0 = everyone spoke equally, 1 = one person took everything. */
export function gini(values) {
  const xs = values.filter((v) => v >= 0).sort((a, b) => a - b)
  const total = xs.reduce((a, b) => a + b, 0)
  if (!total || xs.length < 2) return 0
  const weighted = xs.reduce((acc, x, i) => acc + (i + 1) * x, 0)
  const n = xs.length
  return Math.max(0, Math.round(((2 * weighted) / (n * total) - (n + 1) / n) * 100) / 100)
}

export function topShare(speakers, count = 2) {
  return Math.round(
    [...speakers]
      .sort((a, b) => b.share_words - a.share_words)
      .slice(0, count)
      .reduce((acc, s) => acc + s.share_words, 0),
  )
}

/** Split text into {text, hit} runs so the view can mark matches without innerHTML. */
export function highlight(text, query) {
  const needle = query.trim().toLowerCase()
  if (!needle) return [{ text, hit: false }]
  const out = []
  const haystack = text.toLowerCase()
  let at = 0
  for (;;) {
    const found = haystack.indexOf(needle, at)
    if (found < 0) break
    if (found > at) out.push({ text: text.slice(at, found), hit: false })
    out.push({ text: text.slice(found, found + needle.length), hit: true })
    at = found + needle.length
  }
  if (at < text.length) out.push({ text: text.slice(at), hit: false })
  return out.length ? out : [{ text, hit: false }]
}

export function adrMarkdown(decision, meta = {}) {
  const lines = [`# ADR: ${decision.title || decision.decision}`, '']
  lines.push(`- Status: ${decision.status || 'made'}`)
  if (meta.date) lines.push(`- Date: ${meta.date}`)
  if (decision.decider) lines.push(`- Decider: ${decision.decider}`)
  lines.push(`- Source: ${meta.title || 'meeting'} @ ${fmtTime(decision.t)}`)
  if (decision.confidence) lines.push(`- Extraction confidence: ${decision.confidence}`)
  if (decision.context) lines.push('', '## Context', '', decision.context)
  lines.push('', '## Decision', '', decision.decision || decision.title)
  if (decision.alternatives?.length) {
    lines.push('', '## Alternatives considered', '')
    for (const alt of decision.alternatives) {
      lines.push(`- **${alt.option}** — not chosen: ${alt.why_not || 'no reason recorded'}`)
    }
  }
  if (decision.consequences?.length) {
    lines.push('', '## Consequences', '')
    for (const item of decision.consequences) lines.push(`- ${item}`)
  }
  if (decision.quote) lines.push('', '## Evidence', '', `> ${decision.quote}`)
  return lines.join('\n')
}

export function actionsMarkdown(actions) {
  return actions
    .map((a) => {
      const who = a.assignee ? ` — **${a.assignee}**` : ' — _unassigned_'
      const when = a.due || a.due_raw
      return `- [ ] ${a.action}${who}${when ? ` (due ${when})` : ''} \`${fmtTime(a.t)}\``
    })
    .join('\n')
}

const csvCell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`

export function actionsCsv(actions) {
  const head = ['action', 'assignee', 'due', 'priority', 'status', 'timecode', 'confidence']
  const rows = actions.map((a) =>
    [a.action, a.assignee, a.due || a.due_raw, a.priority, a.status, fmtTime(a.t), a.confidence]
      .map(csvCell)
      .join(','),
  )
  return [head.join(','), ...rows].join('\n')
}

/** Every extracted item carrying a timecode, for the timeline markers. */
export function markers(extract = {}) {
  const out = []
  const push = (list, kind) => {
    for (const item of list || []) {
      if (typeof item.t === 'number') {
        out.push({ kind, t: item.t, label: item.title || item.action || item.q || item.risk })
      }
    }
  }
  push(extract.decisions, 'decision')
  push(extract.actions, 'action')
  push(extract.questions, 'question')
  push(extract.risks, 'risk')
  return out.sort((a, b) => a.t - b.t)
}
