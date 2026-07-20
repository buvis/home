<script>
  import { setContext } from 'svelte'
  import { loadPayload, aggregate, attention, orgSlots, slug, ago, allTodos, quadrant } from './lib/derive.js'
  import { pruneDone } from './lib/done.js'
  import Brief from './components/Brief.svelte'
  import Todos from './components/Todos.svelte'
  import Matrix from './components/Matrix.svelte'
  import Repos from './components/Repos.svelte'
  import Activity from './components/Activity.svelte'
  import Work from './components/Work.svelte'
  import Prds from './components/Prds.svelte'
  import RepoDetail from './components/RepoDetail.svelte'
  import Icon from './components/Icon.svelte'

  const payload = loadPayload()
  const repos = payload?.data.repos ?? []
  const epics = payload?.epics ?? { summary: '', repos: {} }
  const sinceDays = payload?.data.since_days ?? 60
  const external = payload?.data.external ?? null
  const skillAdherence = payload?.data.skill_adherence ?? null
  const prev = payload?.prev ?? null
  const history = payload?.history ?? []
  const slots = orgSlots(repos)
  const scored = new Map(repos.map((r) => [slug(r), attention(r)]))
  setContext('slots', slots)
  setContext('scored', scored)
  if (payload) pruneDone(new Set(allTodos(repos, epics, external).map((t) => t.id)))

  let tab = $state('brief')
  let org = $state('all')
  let filterOpen = $state(false)
  let selected = $state(null)
  let tip = $state({ x: 0, y: 0, text: '', show: false })
  setContext('tip', {
    show: (e, text) => (tip = { x: e.clientX, y: e.clientY, text, show: true }),
    hide: () => (tip = { ...tip, show: false }),
  })

  const TABS = [
    ['brief', 'Brief'],
    ['todo', 'Todo'],
    ['matrix', 'Matrix'],
    ['repos', 'Repos'],
    ['activity', 'Activity'],
    ['work', 'Work'],
    ['prds', 'PRDs'],
  ]
  const orgs = [...slots.keys()]
  const visible = $derived(org === 'all' ? repos : repos.filter((r) => r.org === org))
  // external PRs aren't org-scoped; only show them on the unfiltered view
  const ext = $derived(org === 'all' ? external : null)
  const agg = $derived(aggregate(visible, sinceDays))
  const worstAll = $derived.by(() => {
    for (const sev of ['critical', 'serious', 'warning'])
      if (visible.some((r) => scored.get(slug(r)).reasons.some((x) => x.sev === sev))) return sev
    return 'good'
  })
  const todosAll = $derived(allTodos(visible, epics, ext))
  const counts = $derived({
    todo: todosAll.length,
    matrix: todosAll.filter((t) => quadrant(t) === 'do').length,
    repos: visible.length,
    activity: agg.commits,
    work: agg.prs + agg.issues,
    prds: agg.backlog + agg.wip,
  })
</script>

{#if !payload}
  <div class="fatal">
    No data injected. Run <span class="mono">build.py</span> to produce this file from
    <span class="mono">data.json</span>.
  </div>
{:else}
  <div class="ambient" style="--glow: var(--{worstAll})"></div>
  <header>
    <h1>Portfolio Brief</h1>
    <span class="meta">generated {ago(payload.data.generated_at)} · window {sinceDays}d</span>
    <nav>
      {#each TABS as [id, label] (id)}
        <button class:active={tab === id} onclick={() => (tab = id)}>
          {label}{#if counts[id] != null}<span class="cnt">{counts[id]}</span>{/if}
        </button>
      {/each}
    </nav>
    <div class="filter">
      <button
        class="chip"
        class:active={org !== 'all'}
        aria-label="Filter by org"
        onclick={() => (filterOpen = !filterOpen)}
      >
        <Icon name="filter" size={13} />
        {#if org !== 'all'}
          <span class="dot" style="background: var(--cat{slots.get(org)})"></span>{org}
        {/if}
      </button>
      {#if filterOpen}
        <button class="popback" aria-label="Close filter" onclick={() => (filterOpen = false)}></button>
        <div class="pop">
          <button class="chip" class:active={org === 'all'} onclick={() => ((org = 'all'), (filterOpen = false))}>
            all orgs
          </button>
          {#each orgs as o (o)}
            <button class="chip" class:active={org === o} onclick={() => ((org = o), (filterOpen = false))}>
              <span class="dot" style="background: var(--cat{slots.get(o)})"></span>{o}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </header>
  <main class:full={tab === 'brief'}>
    {#if tab === 'brief'}
      <Brief repos={visible} {agg} {epics} {sinceDays} {prev} {history} external={ext} {skillAdherence} onselect={(r) => (selected = r)} gototab={(t) => (tab = t)} />
    {:else if tab === 'todo'}
      <Todos repos={visible} {epics} external={ext} onselect={(r) => (selected = r)} />
    {:else if tab === 'matrix'}
      <Matrix repos={visible} {epics} external={ext} onselect={(r) => (selected = r)} />
    {:else if tab === 'repos'}
      <Repos repos={visible} {sinceDays} onselect={(r) => (selected = r)} />
    {:else if tab === 'activity'}
      <Activity repos={visible} {sinceDays} onselect={(r) => (selected = r)} />
    {:else if tab === 'work'}
      <Work repos={visible} external={ext} onselect={(r) => (selected = r)} />
    {:else}
      <Prds repos={visible} />
    {/if}
  </main>
  {#if selected}
    <RepoDetail repo={selected} {epics} onclose={() => (selected = null)} />
  {/if}
  {#if tip.show}
    <div
      class="tooltip"
      style="left: {Math.min(tip.x + 12, window.innerWidth - 260)}px; top: {tip.y + 14}px"
    >
      {tip.text}
    </div>
  {/if}
{/if}

<style>
  header {
    display: flex;
    align-items: center;
    gap: 10px 14px;
    flex-wrap: wrap;
    padding: 10px 22px;
    border-bottom: 1px solid var(--grid);
  }
  h1 {
    font-size: 19px;
    margin: 0;
    padding: 3px 20px 4px;
    background: var(--lcars-a);
    color: var(--lcars-ink);
    border-radius: 999px 6px 6px 999px;
  }
  .meta {
    padding: 5px 16px 6px;
    background: var(--lcars-d);
    color: var(--surface);
    border-radius: 6px 999px 999px 6px;
  }
  .meta { font-size: 12px; }
  nav {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .filter { margin-left: auto; position: relative; }
  .popback {
    position: fixed;
    inset: 0;
    z-index: 25;
    background: transparent;
    border: none;
    cursor: default;
  }
  .pop {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    z-index: 26;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    min-width: 170px;
    padding: 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 7px solid var(--lcars-c);
    border-radius: 12px 8px 8px 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  }
  .pop .chip { justify-content: flex-start; }
  nav button {
    font-family: var(--display);
    text-transform: uppercase;
    letter-spacing: 0.07em;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 7px solid var(--lcars-d);
    border-radius: 999px 6px 6px 999px;
    padding: 5px 16px 5px 14px;
    cursor: pointer;
    color: var(--ink-2);
  }
  nav button:hover { border-color: var(--axis); border-left-color: var(--lcars-c); }
  nav button.active {
    background: var(--lcars-a);
    border-color: var(--lcars-a);
    color: var(--lcars-ink);
    font-weight: 600;
  }
  nav .cnt {
    margin-left: 7px;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--ink-2);
    background: color-mix(in srgb, var(--plane) 75%, transparent);
    border-radius: 999px;
    padding: 1px 7px;
  }
  nav button.active .cnt {
    color: var(--lcars-ink);
    background: color-mix(in srgb, var(--lcars-ink) 12%, transparent);
  }
  main { padding: 18px 22px 60px; max-width: 1280px; margin: 0 auto; }
  main.full { padding: 0; max-width: none; }
  .ambient {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 34vh;
    pointer-events: none;
    background: radial-gradient(
      60% 100% at 50% 0%,
      color-mix(in srgb, var(--glow) 9%, transparent),
      transparent 75%
    );
  }
  .tooltip {
    position: fixed;
    z-index: 30;
    max-width: 260px;
    background: var(--surface);
    color: var(--ink);
    font-size: 12px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-left: 7px solid var(--lcars-a);
    border-radius: 12px 8px 8px 12px;
    pointer-events: none;
    white-space: pre-line;
  }
  .fatal { padding: 60px; text-align: center; color: var(--critical); }
</style>
