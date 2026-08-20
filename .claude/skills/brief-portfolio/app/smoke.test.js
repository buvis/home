// Renders the built single-file page in jsdom. Catches the runtime breakage a
// successful `vite build` cannot: a missing field, a bad lookup, a dead tab.
//
// Regression: {#each} blocks keyed by a list item's own value (instead of a
// stable id or index) throw `each_key_duplicate` when two items share that
// value. On the default tab this blanks the whole page at mount; on other
// tabs, or nested panels, it silently breaks the tab/panel switch. Either
// way, duplicate-valued items should render twice, not crash.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JSDOM, VirtualConsole } from 'jsdom'

const TEMPLATE = new URL('../assets/template.html', import.meta.url)

const PAYLOAD = {
  data: {
    repos: [{
      owner: 'buvis', name: 'demo', org: 'buvis',
      prds: {
        backlog: ['Ship pagination this week.', 'Ship pagination this week.'],
        wip: [{ title: 'Same title', idle_days: 3 }, { title: 'Same title', idle_days: 9 }],
        done_count: 0,
      },
    }],
    generated_at: new Date(0).toISOString(), since_days: 60, external: null, skill_adherence: null,
  },
  epics: { summary: '', repos: {} }, prev: null, history: [],
}

function render(payload = PAYLOAD) {
  const page = readFileSync(TEMPLATE, 'utf8').replace(
    '__PORTFOLIO_PAYLOAD__',
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
  // jsdom has no ResizeObserver; stub it so components that size themselves
  // off it (e.g. the sparkline) don't throw a ReferenceError at mount.
  dom.window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  dom.window.eval(bundle)
  assert.deepEqual(errors.map((e) => e.message), [], 'the page threw while mounting')
  const doc = dom.window.document
  // Svelte 5 applies updates in a microtask, so every click needs a flush
  const flush = () => new Promise((resolve) => dom.window.setTimeout(resolve, 0))
  const openTab = async (label) => {
    const button = [...doc.querySelectorAll('header nav button')].find((b) =>
      b.textContent.trim().startsWith(label),
    )
    assert.ok(button, `missing tab ${label}`)
    button.click()
    await flush()
    return button
  }
  return { doc, flush, openTab }
}

// Finds the heading/label element matching `text` among `selector` candidates
// inside `container`, then reads its next sibling `<ul>` and returns the
// `<li>` elements inside it. Doesn't assume DOM order beyond "list follows
// its heading", since that's the only layout fact given.
function backlogListItems(container, selector, text) {
  const heading = [...container.querySelectorAll(selector)].find(
    (n) => n.textContent.trim() === text,
  )
  assert.ok(heading, `no ${selector} reading "${text}"`)
  const ul = heading.nextElementSibling
  assert.ok(ul && ul.tagName === 'UL', `expected a <ul> right after ${selector} "${text}"`)
  return [...ul.querySelectorAll('li')]
}

test('mounts with zero errors on the default Brief tab', () => {
  const { doc } = render()
  assert.equal(doc.querySelector('h1').textContent.trim(), 'Portfolio Brief')
})

test('PRDs tab renders both duplicate backlog entries instead of crashing', async () => {
  const { doc, openTab } = render()
  await openTab('PRDs')
  const card = doc.querySelector('main .card')
  assert.ok(card, 'missing repo card')
  const items = backlogListItems(card, 'h3', 'backlog')
  assert.equal(items.length, 2, `expected 2 backlog items, got ${items.length}`)
  for (const li of items) {
    assert.equal(li.textContent.trim(), 'Ship pagination this week.')
  }
})

test('RepoDetail panel renders both duplicate backlog entries instead of crashing', async () => {
  const { doc, openTab, flush } = render()
  await openTab('Repos')
  const repoButton = doc.querySelector('button.card')
  assert.ok(repoButton, 'missing repo card button')
  repoButton.click()
  await flush()
  const panel = doc.querySelector('div.panel[role="dialog"]')
  assert.ok(panel, 'missing repo detail panel')
  const items = backlogListItems(panel, 'p.meta', 'backlog:')
  assert.equal(items.length, 2, `expected 2 backlog items, got ${items.length}`)
  for (const li of items) {
    assert.equal(li.textContent.trim(), 'Ship pagination this week.')
  }
})

test('Work tab and RepoDetail panel render both instances of a duplicated issue label, not once', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].issues = [
    { number: 7, title: 'Some issue', created: '2026-08-01', comments: 0, labels: ['bug', 'bug'] },
  ]

  const { doc, openTab, flush } = render(payload)

  await openTab('Work')
  assert.ok(doc.querySelector('main').textContent.trim().length > 0, 'Work tab is blank')
  const workChips = [...doc.querySelectorAll('main span.lbl')].filter(
    (n) => n.textContent.trim() === 'bug',
  )
  assert.equal(workChips.length, 2, `expected 2 "bug" chips on Work tab, got ${workChips.length}`)

  await openTab('Repos')
  const repoButton = doc.querySelector('button.card')
  assert.ok(repoButton, 'missing repo card button')
  repoButton.click()
  await flush()
  const panel = doc.querySelector('div.panel[role="dialog"]')
  assert.ok(panel, 'missing repo detail panel')
  const panelChips = [...panel.querySelectorAll('span.lbl')].filter(
    (n) => n.textContent.trim() === 'bug',
  )
  assert.equal(panelChips.length, 2, `expected 2 "bug" chips in RepoDetail panel, got ${panelChips.length}`)
})

test('RepoDetail panel renders both grouped epics that share a title, not once', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].commits = [
    { sha: 'aaaaaaa', date: '2026-08-01', subject: 'first' },
    { sha: 'bbbbbbb', date: '2026-08-02', subject: 'second' },
  ]
  payload.epics.repos['buvis/demo'] = {
    epics: [
      { title: 'Same epic', shas: ['aaaaaaa'] },
      { title: 'Same epic', shas: ['bbbbbbb'] },
    ],
  }

  const { doc, openTab, flush } = render(payload)
  await openTab('Repos')
  const repoButton = doc.querySelector('button.card')
  assert.ok(repoButton, 'missing repo card button')
  repoButton.click()
  await flush()
  const panel = doc.querySelector('div.panel[role="dialog"]')
  assert.ok(panel, 'missing repo detail panel')
  const epicTitles = [...panel.querySelectorAll('details summary b')].filter(
    (n) => n.textContent.trim() === 'Same epic',
  )
  assert.equal(epicTitles.length, 2, `expected 2 epics titled "Same epic", got ${epicTitles.length}`)
})

test('Work tab shows the external PR lookup error instead of an empty section', async () => {
  const payload = structuredClone(PAYLOAD)
  payload.data.external = { error: 'gh auth login', review_requested: [], authored: [] }

  const { doc, openTab } = render(payload)
  await openTab('Work')
  const mainText = doc.querySelector('main').textContent
  assert.match(mainText, /Waiting on you elsewhere/, 'external-PR section heading missing')
  assert.match(mainText, /gh auth login/, 'external lookup error message not shown')
})

test('Work tab has no "Waiting on you elsewhere" section when there is no external data', async () => {
  const { doc, openTab } = render()
  await openTab('Work')
  const mainText = doc.querySelector('main').textContent
  assert.doesNotMatch(mainText, /Waiting on you elsewhere/)
})

test('Brief tab names repos it could not collect this run', () => {
  const payload = structuredClone(PAYLOAD)
  payload.data.skipped = [
    { owner: 'doogat', name: 'jink', org: 'doogat', path: '/tmp/doogat/jink', skipped: 'clone failed' },
  ]

  // Brief is the default tab — no openTab call needed.
  const { doc } = render(payload)
  const mainText = doc.querySelector('main').textContent
  assert.match(mainText, /not collected/)
  assert.match(mainText, /doogat\/jink/)
})

test('Todos tab shows a failed-copy state when neither clipboard.writeText nor execCommand works', async () => {
  // jsdom provides neither navigator.clipboard nor a working execCommand('copy')
  // by default — the same failure mode as clicking "copy open as markdown"
  // from a file:// page.
  // Duplicate backlog/wip entries (as in the shared PAYLOAD) trip the
  // unrelated each_key_duplicate crash on this tab, so use unique data here.
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].prds = { backlog: [], wip: [], done_count: 0 }

  const { doc, openTab, flush } = render(payload)
  await openTab('Todo')
  const button = [...doc.querySelectorAll('main button.chip')].find(
    (b) => b.textContent.trim() === 'copy open as markdown',
  )
  assert.ok(button, 'missing "copy open as markdown" button')
  button.click()
  await flush()
  assert.equal(button.textContent.trim(), '✗ copy failed')
})

test('Failed copy leaves no leftover <textarea> in the document', async () => {
  // Same failure path as the "✗ copy failed" test above: jsdom provides
  // neither navigator.clipboard nor a working execCommand('copy'), so the
  // fallback textarea's select()/execCommand() throw before box.remove()
  // runs, leaking a hidden textarea into the document on every failed copy.
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].prds = { backlog: [], wip: [], done_count: 0 }

  const { doc, openTab, flush } = render(payload)
  await openTab('Todo')
  const button = [...doc.querySelectorAll('main button.chip')].find(
    (b) => b.textContent.trim() === 'copy open as markdown',
  )
  assert.ok(button, 'missing "copy open as markdown" button')
  button.click()
  await flush()
  assert.equal(doc.querySelector('textarea'), null, 'a failed copy left a <textarea> in the document')
})

test('Failed copy is announced in an aria-live region, not just the button label', async () => {
  // Same failure path as the two tests above: jsdom provides neither
  // navigator.clipboard nor a working execCommand('copy'). A label that only
  // mutates in place tells a screen-reader user nothing — the outcome must
  // also reach an aria-live="polite" region.
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].prds = { backlog: [], wip: [], done_count: 0 }

  const { doc, openTab, flush } = render(payload)
  await openTab('Todo')
  const button = [...doc.querySelectorAll('main button.chip')].find(
    (b) => b.textContent.trim() === 'copy open as markdown',
  )
  assert.ok(button, 'missing "copy open as markdown" button')
  button.click()
  await flush()
  const liveRegions = [...doc.querySelectorAll('[aria-live="polite"]')]
  const announced = liveRegions.find((el) => /copy failed/i.test(el.textContent.trim()))
  assert.ok(
    announced,
    'no aria-live="polite" element announces the copy failure (the button label alone changed)',
  )
})

test('Todos tab reports success and copies the open todos when the execCommand fallback works', async () => {
  // navigator.clipboard.writeText rejects (as it would on a file:// page with
  // no secure-context clipboard access), so copy() falls through to
  // fallbackCopy(). Stubbing execCommand to return true simulates a browser
  // where the fallback actually works, unlike the failed-copy tests above
  // where jsdom's own execCommand never succeeds.
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].prds = { backlog: [], wip: [], done_count: 0 }
  payload.data.repos[0].local = { dirty: 2, dirty_since_days: 1, ahead: 3 }

  const { doc, openTab, flush } = render(payload)
  await openTab('Todo')

  const button = [...doc.querySelectorAll('main button.chip')].find(
    (b) => b.textContent.trim() === 'copy open as markdown',
  )
  assert.ok(button, 'missing "copy open as markdown" button')

  // Derive the expected clipboard payload from what the page itself rendered
  // for the open todos, rather than hardcoding a markdown string.
  const expected = [...doc.querySelectorAll('main .todo')]
    .map((el) => {
      const action = el.querySelector('.action').textContent.trim()
      const repo = el.querySelector('.repobtn').textContent.trim()
      return `- [ ] ${repo}: ${action}`
    })
    .join('\n')
  assert.ok(expected.length > 0, 'test setup produced no open todos to copy')

  doc.defaultView.navigator.clipboard = { writeText: () => Promise.reject(new Error('denied')) }
  let recorded = null
  doc.execCommand = () => {
    // The fallback textarea is still in the document at this point — the
    // stub can't read a real selection, so it captures the value directly.
    const box = doc.querySelector('textarea')
    recorded = box ? box.value : null
    return true
  }

  button.click()
  await flush()

  assert.equal(button.textContent.trim(), '✓ copied')
  assert.equal(doc.querySelector('textarea'), null, 'a successful fallback copy left a <textarea> in the document')
  assert.equal(recorded, expected)
})

test('Todos tab reports failure when the execCommand fallback returns false', async () => {
  // navigator.clipboard.writeText rejects (as in the fallback-succeeds test
  // above), but execCommand runs without throwing and returns false — a
  // silently no-op copy rather than a working one. fallbackCopy must treat
  // that as a failure, not report success.
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].prds = { backlog: [], wip: [], done_count: 0 }
  payload.data.repos[0].local = { dirty: 2, dirty_since_days: 1, ahead: 3 }

  const { doc, openTab, flush } = render(payload)
  await openTab('Todo')

  const button = [...doc.querySelectorAll('main button.chip')].find(
    (b) => b.textContent.trim() === 'copy open as markdown',
  )
  assert.ok(button, 'missing "copy open as markdown" button')

  doc.defaultView.navigator.clipboard = { writeText: () => Promise.reject(new Error('denied')) }
  doc.execCommand = () => false

  button.click()
  await flush()

  assert.equal(button.textContent.trim(), '✗ copy failed')
  assert.equal(doc.querySelector('textarea'), null, 'a failed fallback copy left a <textarea> in the document')
})

test('Brief tab trend sparkline plots only complete history runs, not incomplete ones', () => {
  const payload = structuredClone(PAYLOAD)
  payload.prev = { repos: [], generated_at: new Date(0).toISOString() }
  payload.history = [
    { at: new Date(0).toISOString(), repos: {} },
    { at: new Date(0).toISOString(), repos: {}, skipped: 0 },
    { at: new Date(0).toISOString(), repos: {} },
    { at: new Date(0).toISOString(), repos: {}, skipped: 1 },
  ]

  // Brief is the default tab — no openTab call needed.
  const { doc } = render(payload)
  const mainText = doc.querySelector('main').textContent
  assert.match(
    mainText,
    /open items across 3 briefs/,
    'trend label should report 3 complete runs, not all 4 history entries',
  )
})

test('aria-live region clears once the failed-copy button label has reverted', async () => {
  // Same failure path as the tests above. The button's own copied/failed
  // state resets to '' after 1.5s via setTimeout, but the aria-live status
  // never resets. Svelte's $state skips the DOM write when a value repeats,
  // so once the label looks normal again, the live region must not still be
  // holding the stale "✗ copy failed" text from the click that just cleared.
  const payload = structuredClone(PAYLOAD)
  payload.data.repos[0].prds = { backlog: [], wip: [], done_count: 0 }

  const { doc, openTab, flush } = render(payload)
  await openTab('Todo')
  const button = [...doc.querySelectorAll('main button.chip')].find(
    (b) => b.textContent.trim() === 'copy open as markdown',
  )
  assert.ok(button, 'missing "copy open as markdown" button')
  button.click()
  await flush()
  assert.equal(button.textContent.trim(), '✗ copy failed')

  // Wait past the component's 1.5s reset (real time, not a stubbed clock),
  // then flush so the resulting DOM update lands.
  await new Promise((resolve) => setTimeout(resolve, 1600))
  await flush()
  assert.equal(button.textContent.trim(), 'copy open as markdown', 'label did not revert after 1.5s')

  const liveRegion = doc.querySelector('[aria-live="polite"]')
  assert.ok(liveRegion, 'missing aria-live="polite" element')
  assert.equal(
    liveRegion.textContent.trim(),
    '',
    'aria-live region still holds stale "✗ copy failed" text after the button label reverted',
  )
})
