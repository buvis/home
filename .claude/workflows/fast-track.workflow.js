export const meta = {
  name: 'fast-track',
  description: 'Implement one spec card: fresh implementor, sequential gate, zero-context multi-model review roster, adversarial verify, one rework, exit rule',
  whenToUse: 'Use when a small, test-specified item should be implemented and reviewed by every lens without the autopilot loop phases. Triggers on "fast-track item", "run the fast-track harness".',
  phases: [
    { title: 'Prep', detail: 'read the card, personas, rubric; record base sha; refuse a dirty tree' },
    { title: 'Implement', detail: 'fresh implementor, tests are the spec, fixed allowlist' },
    { title: 'Gate', detail: 'card gate commands, one at a time, foreground' },
    { title: 'Review', detail: 'review-fanout child workflow + Eve + Blake + Bob(codex) + Carl(gemini), zero session context' },
    { title: 'Verify', detail: 'adversarial refutation of every CRITICAL/HIGH from the non-fanout lanes' },
    { title: 'Rework', detail: 'one rework by a fresh implementor, gate again, closure check per finding' },
    { title: 'Report', detail: 'consolidated review file; the driver commits or branches' },
  ],
}

// ---- args ----------------------------------------------------------------
// {
//   repo:             absolute repo root
//   item:             short id, e.g. "FT-4"
//   card_path:        absolute path to the spec card (markdown, see the plan)
//   plugin_root:      absolute path of the installed autopilot plugin (agents/, skills/)
//   fanout_script:    absolute path of review-fanout.workflow.js
//   implementor_model: 'sonnet' | 'opus' (default sonnet; the card's "## Model" wins when present)
//   rework_cap:       number of review-driven rework cycles (default 1)
//   date:             'YYYY-MM-DD' (Date.now is unavailable inside a workflow)
// }
const a = typeof args === 'string' ? JSON.parse(args) : args
const need = (k) => { if (!a || typeof a[k] !== 'string' || a[k].trim() === '') throw new Error(`INVALID_ARGS: ${k} is required`) }
;['repo', 'item', 'card_path', 'plugin_root', 'fanout_script', 'date'].forEach(need)
const REWORK_CAP = Number.isFinite(a.rework_cap) ? a.rework_cap : 1
const ITEM = a.item
const REPO = a.repo
const TMP = `${REPO}/dev/local/tmp`
const DIFF_PATH = `${TMP}/${ITEM}-fast-track.diff`
const MAX_INLINE_DIFF = 300000

const TOOL_RULES = `
Tool rules (mandatory): use the Read tool for files and rg for search; cat/head/tail/grep/find are blocked by a hook; the Grep and Glob tools do not exist. Run every cargo/test/lint command in the FOREGROUND, one command per Bash call, never in the background, never chained with && or pipes, always with an explicit timeout (60000 ms inspection, 300000 ms narrow test/lint, 600000 ms build or suite). Never run cargo commands in parallel with another agent: you are the only cargo user while you run. Never run ddb commands inside the repo checkout. Never modify files outside what your prompt allows.`

function fill(body, map) {
  let text = body
  for (const k of Object.keys(map)) text = text.split(`{${k}}`).join(map[k])
  const left = text.match(/\{[A-Z_]+\}/)
  if (left) throw new Error(`unfilled placeholder ${left[0]}`)
  return text
}
const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
const isBlocker = (f) => f.severity === 'CRITICAL' || f.severity === 'HIGH'

// ---- schemas ---------------------------------------------------------------
const PREP_SCHEMA = {
  type: 'object',
  properties: {
    base_sha: { type: 'string' },
    dirty_tree: { type: 'boolean' },
    dirty_detail: { type: 'string' },
    card: {
      type: 'object',
      properties: {
        title: { type: 'string' }, goal: { type: 'string' },
        tests: { type: 'array', items: { type: 'string' } },
        allowlist: { type: 'array', items: { type: 'string' } },
        readonly_context: { type: 'array', items: { type: 'string' } },
        constraints: { type: 'string' },
        gate: { type: 'array', items: { type: 'string' } },
        docs: { type: 'string' }, transport: { type: 'string' }, model: { type: 'string' },
      },
      required: ['title', 'goal', 'tests', 'allowlist', 'readonly_context', 'constraints', 'gate', 'docs', 'transport', 'model'],
    },
    card_text: { type: 'string' },
    tests_content: { type: 'string', description: 'the content of every test file named in the card, each prefixed by "### <path>"' },
    context_content: { type: 'string', description: 'the content of every read-only context file, capped at 40000 chars total' },
    personas: {
      type: 'object',
      properties: {
        ivan: { type: 'string' }, eve: { type: 'string' }, blake: { type: 'string' }, bob: { type: 'string' }, carl: { type: 'string' },
        rita: { type: 'string' }, cora: { type: 'string' }, grace: { type: 'string' }, toby: { type: 'string' }, mallory: { type: 'string' },
        trent: { type: 'string' }, victor: { type: 'string' },
      },
      required: ['ivan', 'eve', 'blake', 'bob', 'carl', 'rita', 'cora', 'grace', 'toby', 'mallory', 'trent', 'victor'],
    },
    rubric_text: { type: 'string' },
    checklist_text: { type: 'string' },
    output_format_text: { type: 'string' },
    devlocal_realpath: { type: 'string' },
  },
  required: ['base_sha', 'dirty_tree', 'dirty_detail', 'card', 'card_text', 'tests_content', 'context_content', 'personas', 'rubric_text', 'checklist_text', 'output_format_text', 'devlocal_realpath'],
}

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    summary: { type: 'string' },
    files_touched: { type: 'array', items: { type: 'string' } },
    assumptions: { type: 'array', items: { type: 'string' } },
    blocker: { type: 'string' },
    narrow_test_result: { type: 'string' },
  },
  required: ['status', 'summary', 'files_touched', 'assumptions', 'blocker', 'narrow_test_result'],
}

const GATE_SCHEMA = {
  type: 'object',
  properties: {
    passed: { type: 'boolean' },
    results: { type: 'array', items: { type: 'object', properties: { cmd: { type: 'string' }, exit_code: { type: 'integer' }, seconds: { type: 'number' }, tail: { type: 'string' } }, required: ['cmd', 'exit_code', 'tail'] } },
  },
  required: ['passed', 'results'],
}

const DIFF_SCHEMA = {
  type: 'object',
  properties: {
    head_sha: { type: 'string' },
    diff: { type: 'string', description: 'the unified diff text, or an empty string when it is larger than the inline cap' },
    diff_bytes: { type: 'integer' },
    diff_path: { type: 'string' },
    changed_files: { type: 'array', items: { type: 'string' } },
  },
  required: ['head_sha', 'diff', 'diff_bytes', 'diff_path', 'changed_files'],
}

const FINDING = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
    file: { type: 'string' },
    line: { type: 'integer' },
    evidence: { type: 'string' },
    proof: { type: 'string', description: 'for CRITICAL/HIGH: the concrete failing input and its consequence; required' },
    fix: { type: 'string' },
  },
  required: ['title', 'severity', 'file', 'evidence'],
}
const LANE_SCHEMA = {
  type: 'object',
  properties: {
    lane_status: { type: 'string', enum: ['ok', 'unavailable', 'failed'] },
    status_detail: { type: 'string' },
    findings: { type: 'array', items: FINDING },
    verdict_lines: { type: 'array', items: { type: 'string' }, description: 'rubric verdict lines the persona emits (R1: pass ... / D1: pass ... / B1: pass ...), verbatim' },
    raw_excerpt: { type: 'string', description: 'up to 4000 chars of the lane\'s raw output' },
  },
  required: ['lane_status', 'status_detail', 'findings', 'verdict_lines', 'raw_excerpt'],
}
const VERDICT_SCHEMA = { type: 'object', properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } }, required: ['refuted', 'reason'] }
const CLOSURE_SCHEMA = { type: 'object', properties: { closed: { type: 'boolean' }, reason: { type: 'string' } }, required: ['closed', 'reason'] }
const REPORT_SCHEMA = { type: 'object', properties: { review_path: { type: 'string' } }, required: ['review_path'] }

// ---- Prep ------------------------------------------------------------------
phase('Prep')
const prep = await agent(`You prepare a fast-track run for item ${ITEM} in the repo ${REPO}. READ-ONLY: do not edit anything, do not run cargo.
${TOOL_RULES}
1. Run \`git -C ${REPO} status --porcelain\` (timeout 60000). If it prints anything, set dirty_tree=true and put the output in dirty_detail (the run refuses to start on a dirty tree). Run \`git -C ${REPO} rev-parse HEAD\` for base_sha.
2. Read the spec card at ${a.card_path} and return it verbatim as card_text, and parsed into card: title (the H1), goal (## Goal), tests (## Tests: one entry per line, "path::test_name" or "path"), allowlist (## Allowlist: paths the implementor may edit; a line may carry a parenthesised restriction, keep it), readonly_context (## Read-only context: paths to read, never edit), constraints (## Constraints verbatim), gate (## Gate: one shell command per line, in order), docs (## Docs and CHANGELOG verbatim), transport (## Transport impact verbatim), model (## Model: sonnet or opus; empty if absent).
3. tests_content: Read every file path in tests (strip "::name") and concatenate them, each prefixed by "### <path>".
4. context_content: Read every readonly_context file; concatenate with "### <path>" prefixes; cap the total at 40000 characters (truncate the largest files first and say so at the cut).
5. personas: for each of ivan, eve, blake, bob, carl, rita, cora, grace, toby, mallory, trent, victor read ${a.plugin_root}/agents/<name>.md and return the body with the YAML frontmatter (the leading --- block) stripped.
6. rubric_text = ${a.plugin_root}/skills/review-work-completion/references/rubric.md (whole file); checklist_text = .../references/review-dimensions.md (whole file); output_format_text = the "## Agent Output Format (Single Source of Truth)" section of .../references/output-formats.md (from that heading up to the next "## " heading).
7. devlocal_realpath: the output of \`readlink -f ${REPO}/dev/local\` (or the path itself when it is not a symlink).
Return exactly the schema.`, { label: 'prep', phase: 'Prep', schema: PREP_SCHEMA, effort: 'low' })

if (!prep) throw new Error('prep agent returned nothing')
if (prep.dirty_tree) return { item: ITEM, outcome: 'aborted', reason: `dirty tree: ${prep.dirty_detail}` }
const card = prep.card
const IMPL_MODEL = (card.model === 'opus' || card.model === 'sonnet') ? card.model : (a.implementor_model === 'opus' ? 'opus' : 'sonnet')
log(`fast-track ${ITEM}: base ${prep.base_sha.slice(0, 7)}, implementor ${IMPL_MODEL}, ${card.tests.length} spec tests, ${card.allowlist.length} allowlisted files, ${card.gate.length} gate commands`)

const allowlistBlock = [
  '## Files you may modify',
  ...card.allowlist.map((p) => `- ${p}`),
  '',
  '## Files you may only read',
  `- ${REPO}/AGENTS.md`,
  ...card.readonly_context.map((p) => `- ${p}`),
].join('\n')

const ivanPrompt = (retryInstruction) => fill(prep.personas.ivan, {
  FAILING_TESTS: `${prep.tests_content}\n\nThese tests are the spec. Some carry #[ignore = "fast-track ..."]: removing that attribute (and nothing else in the test file) is part of the job, and only when the card's allowlist names the test file. Run the narrow tests yourself: for a ddb-core/tests file \`cargo test -p ddb-core --test <file stem>\`; for tests/e2e first \`cargo build -p ddb-cli\` then \`cargo test -p ddb-e2e --test e2e <module name>\`.`,
  ARCHITECTURE_CONTEXT: `## Card\n${prep.card_text}\n\n## Read-only context files\n${prep.context_content}`,
  FILE_PATHS: allowlistBlock,
  RETRY_INSTRUCTION: retryInstruction,
}) + `\n\nRepository root: ${REPO}\n${TOOL_RULES}\nReturn exactly the schema: status done or blocked, summary, files_touched (repo-relative), assumptions, blocker (empty when done), narrow_test_result (the last narrow test command and its summary line).`

// ---- Implement -------------------------------------------------------------
phase('Implement')
let impl = await agent(ivanPrompt(''), { label: 'implement', phase: 'Implement', model: IMPL_MODEL, schema: IMPL_SCHEMA })
if (!impl || impl.status !== 'done') {
  return { item: ITEM, outcome: 'implementor_blocked', base_sha: prep.base_sha, blocker: impl ? impl.blocker : 'implementor returned nothing', assumptions: impl ? impl.assumptions : [] }
}
const assumptions = [...impl.assumptions]

// ---- Gate ------------------------------------------------------------------
const gatePrompt = () => `You are the gate runner for fast-track item ${ITEM} in ${REPO}. Run these commands from the repo root, in this order, one Bash call each, FOREGROUND, timeout 600000 each, and stop at the first non-zero exit:
${card.gate.map((c, i) => `${i + 1}. ${c}`).join('\n')}
Do not edit any file. Do not run anything else. ${TOOL_RULES}
Return passed=true only if every command exited 0. For each command return its exit code, wall seconds and the last 40 lines of output (tail).`

phase('Gate')
let gate = await agent(gatePrompt(), { label: 'gate', phase: 'Gate', schema: GATE_SCHEMA, effort: 'low' })
if (!gate || !gate.passed) {
  const failing = gate ? gate.results.filter((r) => r.exit_code !== 0).map((r) => `$ ${r.cmd}\n${r.tail}`).join('\n\n') : 'gate runner returned nothing'
  log(`gate failed once; one implementor retry`)
  impl = await agent(ivanPrompt(`RETRY: the gate failed after your change. Fix it within your allowlist without weakening any test. Failing output:\n${failing}`), { label: 'implement-gate-retry', phase: 'Gate', model: IMPL_MODEL, schema: IMPL_SCHEMA })
  if (impl && impl.status === 'done') assumptions.push(...impl.assumptions)
  gate = await agent(gatePrompt(), { label: 'gate-retry', phase: 'Gate', schema: GATE_SCHEMA, effort: 'low' })
  if (!gate || !gate.passed) return { item: ITEM, outcome: 'gate_failed', base_sha: prep.base_sha, gate, assumptions }
}

// ---- Diff ------------------------------------------------------------------
const takeDiff = async (label) => agent(`In ${REPO}: run \`git -C ${REPO} add -A\` (timeout 60000; dev/local is gitignored, nothing under it is staged), then \`git -C ${REPO} diff --cached ${prep.base_sha}\` and write that exact output with the Write tool to ${DIFF_PATH} (create dev/local/tmp if missing). Run \`git -C ${REPO} diff --cached --name-only ${prep.base_sha}\` for changed_files and \`git -C ${REPO} rev-parse HEAD\` for head_sha. Measure the diff byte size with \`wc -c ${DIFF_PATH}\`. Return diff = the full diff text when it is at most ${MAX_INLINE_DIFF} bytes, otherwise an empty string. Do not edit any repo file. ${TOOL_RULES}`, { label, phase: 'Review', schema: DIFF_SCHEMA, effort: 'low' })

// ---- Review ----------------------------------------------------------------
phase('Review')
let diff = await takeDiff('diff')
if (!diff) throw new Error('diff agent returned nothing')

const fanoutArgs = (d) => ({
  diff: d.diff || `(diff of ${d.diff_bytes} bytes is over the inline cap; read ${d.diff_path})`,
  diff_bytes: d.diff_bytes,
  diff_path: d.diff ? undefined : d.diff_path,
  changed_files: d.changed_files,
  rubric_text: prep.rubric_text,
  personas: { rita: prep.personas.rita, cora: prep.personas.cora, grace: prep.personas.grace, toby: prep.personas.toby, mallory: prep.personas.mallory, trent: prep.personas.trent, victor: prep.personas.victor },
  prd_text: prep.card_text,
  prd_path: a.card_path,
  agent_name: 'FANOUT',
  cycle: 1,
  date: a.date,
  head_sha: d.head_sha,
})

const laneContext = (d) => `\n\n## Item card (the spec)\n${prep.card_text}\n\n## Diff range\n${prep.base_sha}..HEAD (staged, uncommitted working tree; full diff at ${d.diff_path})\n\n## Changed files\n${d.changed_files.join('\n')}\n\n## Diff\n\`\`\`diff\n${d.diff || `(over the inline cap: read ${d.diff_path})`}\n\`\`\`\n\nRepository root: ${REPO}. ${TOOL_RULES}\nReturn exactly the lane schema: lane_status ok, your findings (severity CRITICAL/HIGH/MEDIUM/LOW; every CRITICAL/HIGH must carry a proof: the concrete failing input and its consequence), your rubric verdict lines verbatim, and a raw excerpt of your own written review.`

const evePrompt = fill(prep.personas.eve, { PACK_FINDINGS: '(no pack available this cycle)' }) + laneContext(diff) + `\nMap your buckets onto findings: FIX items keep their real severity, VERIFY items are MEDIUM with the exact check named in fix, KNOWN items are LOW with the justification in evidence. Emit the five D1-D5 verdict lines in verdict_lines.`

// output_format_text carries the lane tag placeholder [{AGENT_NAME}]; fill it after the section is substituted in
const blakePrompt = fill(prep.personas.blake, { PRD: prep.card_text, RUBRIC: prep.rubric_text, OUTPUT_FORMAT: prep.output_format_text, AGENT_NAME: 'BLAKE' }) + `\n\n## Filesystem notes\nProject root: ${REPO}\n\`dev/local\` realpath: ${prep.devlocal_realpath}\n\`rg --files\` does not descend into dot-directories or follow this symlink; list or Read the realpath directly.\n\nYou see NO diff and NO changed-file list on purpose: find the code yourself. The spec is the card above; its "Tests" section names the regression tests that must now pass and must not be ignored. ${TOOL_RULES}\nReturn exactly the lane schema (findings + your B-rule verdict lines + raw excerpt).`

const cliLane = (name, script, personaBody) => {
  const promptFile = `${TMP}/${ITEM}-${name}-prompt.md`
  const outFile = `${TMP}/${ITEM}-${name}-output.txt`
  const body = fill(personaBody, {
    CONTEXT_FILE: a.card_path,
    DIFF_FILE: diff.diff_path,
    PACK_FILE: `${TMP}/${ITEM}-no-pack.md`,
    REVIEW_CHECKLIST: prep.checklist_text,
    RUBRIC: prep.rubric_text,
    OUTPUT_FORMAT: prep.output_format_text,
    AGENT_NAME: name.toUpperCase(),
  })
  return `You dispatch the external-model review lane "${name}" for fast-track item ${ITEM}. Steps, each a separate Bash call in the FOREGROUND with timeout 600000:
1. Write the file ${TMP}/${ITEM}-no-pack.md with the single line "(no pack available this cycle)" and write the file ${promptFile} with EXACTLY the prompt text between the markers below (Write tool).
2. Run: bash ${a.plugin_root}/skills/use-codex/scripts/${script} -f "${promptFile}" -o "${outFile}" (for gemini use ${a.plugin_root}/skills/use-gemini/scripts/${script} with the same flags). Note the exit code and stderr.
3. If the helper is missing, exits non-zero without output, or exit code 4 (permanently unavailable), return lane_status unavailable/failed with the reason in status_detail and no findings. Otherwise Read ${outFile} and translate every issue line of the form "[NAME] <emoji> <title> | File: <file> | Task: <task>" into a finding (🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM, ⚪ LOW; evidence = the line's own text plus any explanation that follows it; proof = the reviewer's stated failing input/consequence when given, else empty), and copy the R-rule verdict lines verbatim into verdict_lines. raw_excerpt = the first 4000 chars of the output.
Never summarise or soften the findings; never add findings of your own. ${TOOL_RULES}
===== PROMPT START =====
${body}
===== PROMPT END =====`
}

const [fanout, eve, blake, bob, carl] = await parallel([
  () => workflow({ scriptPath: a.fanout_script }, fanoutArgs(diff)),
  () => agent(evePrompt, { label: 'eve', phase: 'Review', model: 'fable', schema: LANE_SCHEMA }),
  () => agent(blakePrompt, { label: 'blake', phase: 'Review', model: 'sonnet', schema: LANE_SCHEMA }),
  () => agent(cliLane('bob', 'codex-run.sh', prep.personas.bob), { label: 'bob-codex', phase: 'Review', schema: LANE_SCHEMA, effort: 'low' }),
  () => agent(cliLane('carl', 'gemini-run.sh', prep.personas.carl), { label: 'carl-gemini', phase: 'Review', schema: LANE_SCHEMA, effort: 'low' }),
])

const lanes = { fanout, eve, blake, bob, carl }
const laneStatus = {
  fanout: fanout ? (fanout.incomplete ? `incomplete (${fanout.failedDimensions.join(', ')})` : fanout.verdict) : 'failed',
  eve: eve ? eve.lane_status : 'failed',
  blake: blake ? blake.lane_status : 'failed',
  bob: bob ? `${bob.lane_status}${bob.status_detail ? ': ' + bob.status_detail.slice(0, 120) : ''}` : 'failed',
  carl: carl ? `${carl.lane_status}${carl.status_detail ? ': ' + carl.status_detail.slice(0, 120) : ''}` : 'failed',
}
log(`lanes: ${Object.entries(laneStatus).map(([k, v]) => `${k}=${v}`).join(' | ')}`)

// ---- Verify ----------------------------------------------------------------
phase('Verify')
const fanoutBlocking = fanout ? fanout.blocking.map((f) => ({ ...f, lane: 'fanout', verified: f.verified })) : []
const seen = new Set(fanoutBlocking.map((f) => `${norm(f.file)}|${norm(f.evidence || f.title)}`))
const candidates = []
for (const name of ['eve', 'blake', 'bob', 'carl']) {
  const lane = lanes[name]
  if (!lane || !Array.isArray(lane.findings)) continue
  for (const f of lane.findings) {
    if (!isBlocker(f)) continue
    const key = `${norm(f.file)}|${norm(f.evidence || f.title)}`
    if (seen.has(key)) continue
    seen.add(key)
    candidates.push({ ...f, lane: name })
  }
}
log(`verifying ${candidates.length} CRITICAL/HIGH from eve/blake/bob/carl (fanout already verified ${fanoutBlocking.length})`)
const verdicts = await parallel(candidates.map((f) => () => agent(
  fill(prep.personas.victor, {
    FINDING_TITLE: f.title, FINDING_SEVERITY: f.severity, FINDING_FILE: `${f.file}${f.line ? ':' + f.line : ''}`,
    FINDING_EVIDENCE: f.evidence, FINDING_PROOF: f.proof || '(none)',
  }) + laneContext(diff),
  { label: `verify: ${f.title.slice(0, 60)}`, phase: 'Verify', model: 'sonnet', schema: VERDICT_SCHEMA },
)))
let blocking = [...fanoutBlocking]
const refuted = []
candidates.forEach((f, i) => {
  const v = verdicts[i]
  if (v && v.refuted === true) refuted.push({ ...f, refutation: v.reason })
  else blocking.push({ ...f, verified: v ? 'confirmed' : 'verifier_failed', reason: v ? v.reason : '' })
})
const advisory = []
for (const name of ['eve', 'blake', 'bob', 'carl']) {
  const lane = lanes[name]
  if (lane && Array.isArray(lane.findings)) for (const f of lane.findings) if (!isBlocker(f)) advisory.push({ ...f, lane: name })
}
if (fanout) for (const f of fanout.advisory) advisory.push({ ...f, lane: 'fanout' })

// ---- Rework ----------------------------------------------------------------
phase('Rework')
let reworks = 0
let remaining = blocking
if (blocking.length > 0 && REWORK_CAP > 0) {
  reworks = 1
  const list = blocking.map((f, i) => `${i + 1}. [${f.severity}] ${f.title} (${f.file}${f.line ? ':' + f.line : ''})\n   evidence: ${f.evidence}\n   proof: ${f.proof || '(none)'}\n   suggested fix: ${f.fix || '(none)'}`).join('\n')
  const rework = await agent(ivanPrompt(`REWORK: independent reviewers confirmed these findings against your predecessor's change (the diff is already in the working tree). Fix exactly these, surgically, within your allowlist, keeping every spec test green:\n${list}`), { label: 'rework', phase: 'Rework', model: IMPL_MODEL, schema: IMPL_SCHEMA })
  if (rework && rework.status === 'done') assumptions.push(...rework.assumptions)
  gate = await agent(gatePrompt(), { label: 'gate-after-rework', phase: 'Rework', schema: GATE_SCHEMA, effort: 'low' })
  if (!gate || !gate.passed) return { item: ITEM, outcome: 'gate_failed_after_rework', base_sha: prep.base_sha, gate, blocking, assumptions, lane_status: laneStatus }
  diff = await takeDiff('diff-after-rework')
  const closures = await parallel(blocking.map((f) => () => agent(`You check whether ONE review finding is closed by the current change in ${REPO}. Finding: [${f.severity}] ${f.title} at ${f.file}${f.line ? ':' + f.line : ''}. Evidence: ${f.evidence}. Proof: ${f.proof || '(none)'}. Read the diff at ${diff.diff_path} (range ${prep.base_sha}..working tree) and the surrounding code. closed=true only when the code now prevents the stated failing input from producing the stated consequence; a comment, a rename or a partial guard is not closure. ${TOOL_RULES}`, { label: `closure: ${f.title.slice(0, 60)}`, phase: 'Rework', model: 'sonnet', schema: CLOSURE_SCHEMA })))
  remaining = blocking.filter((f, i) => !(closures[i] && closures[i].closed === true)).map((f, i) => ({ ...f, closure_reason: closures[i] ? closures[i].reason : 'closure check failed' }))
}

// ---- Report ----------------------------------------------------------------
phase('Report')
const outcome = remaining.length === 0 ? 'ready' : 'blocked'
const summary = {
  item: ITEM, outcome, base_sha: prep.base_sha, head_sha: diff.head_sha, implementor_model: IMPL_MODEL, reworks,
  lane_status: laneStatus,
  blocking_before_rework: blocking.map((f) => ({ lane: f.lane, severity: f.severity, title: f.title, file: f.file })),
  remaining: remaining.map((f) => ({ lane: f.lane, severity: f.severity, title: f.title, file: f.file, closure_reason: f.closure_reason })),
  refuted: refuted.map((f) => ({ lane: f.lane, title: f.title, refutation: f.refutation })),
  advisory_count: advisory.length,
  assumptions,
  files_touched: impl.files_touched,
  gate: gate.results.map((r) => ({ cmd: r.cmd, exit_code: r.exit_code, seconds: r.seconds })),
}
const report = await agent(`Write the consolidated fast-track review for item ${ITEM} to ${REPO}/dev/local/reviews/${ITEM}-fast-track-review.md (Write tool; create the directory if missing). Content, in this order: a YAML frontmatter (item, date ${a.date}, base_sha, head_sha, outcome, implementor_model, reworks, lanes as a map); "## Summary" with the outcome and the blocking/remaining/refuted counts; "## Fan-out (Alice-engine)" containing the fan-out review markdown verbatim; one "## <Lane>" section each for Eve, Blake, Bob (codex) and Carl (gemini) with lane_status, the findings as a table (severity | title | file | proof), and the verdict lines; "## Adversarial verification" listing every candidate with confirmed/refuted and the reason; "## Rework" listing closures; "## Advisory" (all non-blocking findings); "## Assumptions" (from the implementors); "## Gate" (commands, exit codes, seconds). Do not run cargo; do not edit any other file. ${TOOL_RULES}
DATA (JSON):
${JSON.stringify({ summary, fanout_markdown: fanout ? fanout.review_markdown : '(fan-out failed)', lanes: { eve, blake, bob, carl }, refuted, remaining, advisory }, null, 2)}`, { label: 'report', phase: 'Report', schema: REPORT_SCHEMA, effort: 'low' })

log(`fast-track ${ITEM}: ${outcome} (blocking ${blocking.length}, remaining ${remaining.length}, refuted ${refuted.length}, advisory ${advisory.length}, reworks ${reworks})`)
return { ...summary, review_path: report ? report.review_path : `${REPO}/dev/local/reviews/${ITEM}-fast-track-review.md`, diff_path: diff.diff_path }
