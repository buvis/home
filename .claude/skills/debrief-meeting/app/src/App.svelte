<script>
  import { setContext } from 'svelte'
  import { fmtDur, loadPayload, nearestTurn, speakerIndex } from './lib/derive.js'
  import Brief from './components/Brief.svelte'
  import Timeline from './components/Timeline.svelte'
  import Actions from './components/Actions.svelte'
  import Decisions from './components/Decisions.svelte'
  import People from './components/People.svelte'
  import Transcript from './components/Transcript.svelte'
  import Insights from './components/Insights.svelte'

  const payload = loadPayload()
  const transcript = payload?.transcript
  const extract = payload?.extract ?? {}
  const extractRan = payload?.extract_ran ?? true
  const meta = extract.meta ?? {}
  const speakers = speakerIndex(transcript?.speakers ?? [])

  // one shared view state: the timecode chips everywhere drive it
  const view = $state({ tab: 'brief', focus: -1, query: '', speaker: 'all' })

  setContext('meeting', {
    transcript,
    extract,
    extractRan,
    meta,
    speakers,
    view,
    jump(t) {
      // "take me there" beats "keep my filters" — a hidden turn cannot be scrolled to
      view.speaker = 'all'
      view.query = ''
      view.focus = nearestTurn(transcript.turns, t)
      view.tab = 'transcript'
    },
  })

  const TABS = [
    ['brief', 'Brief', null, Brief],
    ['timeline', 'Timeline', extract.topics?.length, Timeline],
    ['actions', 'Actions', extract.actions?.length, Actions],
    ['decisions', 'Decisions', extract.decisions?.length, Decisions],
    ['people', 'People', transcript?.speakers?.length, People],
    ['transcript', 'Transcript', null, Transcript],
    ['insights', 'Insights', null, Insights],
  ]
  const Current = $derived(TABS.find(([id]) => id === view.tab)?.[3] ?? Brief)

  const facts = $derived(
    [
      meta.date,
      meta.platform,
      meta.type,
      fmtDur(transcript?.meta?.duration),
      `${transcript?.speakers?.length ?? 0} speaking`,
      `${transcript?.meta?.words ?? 0} words`,
    ].filter(Boolean),
  )
</script>

{#if !payload}
  <div class="wrap">
    <h1>Meeting Debrief</h1>
    <p class="empty">No payload was injected into this file. Re-run scripts/build.py.</p>
  </div>
{:else}
  <header class="top">
    <div class="wrap">
      <h1>{meta.title ?? 'Meeting Debrief'}</h1>
      <div class="subtitle">{facts.join(' · ')}</div>
      {#if meta.purpose}<div class="subtitle">{meta.purpose}</div>{/if}
      <nav class="tabs" aria-label="Sections">
        {#each TABS as [id, label, count] (id)}
          <button
            aria-current={view.tab === id ? 'page' : undefined}
            onclick={() => (view.tab = id)}
          >
            {label}{#if count}<span class="count">{count}</span>{/if}
          </button>
        {/each}
      </nav>
    </div>
  </header>

  <main class="wrap">
    {#if transcript.warnings?.length && view.tab === 'brief'}
      <div class="card" style="border-left-color: var(--warning)">
        <strong>Transcript quality</strong>
        <ul>
          {#each transcript.warnings as warning, i (i)}<li>{warning}</li>{/each}
        </ul>
      </div>
    {/if}
    <Current />
  </main>
{/if}
