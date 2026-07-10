<script>
  import { setContext } from 'svelte'
  import { loadPayload, aggregate, attention, orgSlots, slug, ago } from './lib/derive.js'
  import Brief from './components/Brief.svelte'
  import Todos from './components/Todos.svelte'
  import Repos from './components/Repos.svelte'
  import Activity from './components/Activity.svelte'
  import Work from './components/Work.svelte'
  import Prds from './components/Prds.svelte'
  import RepoDetail from './components/RepoDetail.svelte'

  const payload = loadPayload()
  const repos = payload?.data.repos ?? []
  const epics = payload?.epics ?? { summary: '', repos: {} }
  const sinceDays = payload?.data.since_days ?? 60
  const slots = orgSlots(repos)
  const scored = new Map(repos.map((r) => [slug(r), attention(r)]))
  setContext('slots', slots)
  setContext('scored', scored)

  let tab = $state('brief')
  let org = $state('all')
  let selected = $state(null)
  let theme = $state('auto')
  let tip = $state({ x: 0, y: 0, text: '', show: false })
  setContext('tip', {
    show: (e, text) => (tip = { x: e.clientX, y: e.clientY, text, show: true }),
    hide: () => (tip = { ...tip, show: false }),
  })

  const TABS = [
    ['brief', 'Brief'],
    ['todo', 'Todo'],
    ['repos', 'Repos'],
    ['activity', 'Activity'],
    ['work', 'Work'],
    ['prds', 'PRDs'],
  ]
  const orgs = [...slots.keys()]
  const visible = $derived(org === 'all' ? repos : repos.filter((r) => r.org === org))
  const agg = $derived(aggregate(visible, sinceDays))

  $effect(() => {
    if (theme === 'auto') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
  })

  function onkeydown(e) {
    if (e.target.closest('input, textarea, select') || e.metaKey || e.ctrlKey) return
    const i = '123456'.indexOf(e.key)
    if (i >= 0) tab = TABS[i][0]
  }
</script>

<svelte:window {onkeydown} />

{#if !payload}
  <div class="fatal">
    No data injected. Run <span class="mono">build.py</span> to produce this file from
    <span class="mono">data.json</span>.
  </div>
{:else}
  <header>
    <div class="brand">
      <h1>Portfolio Brief</h1>
      <span class="meta">
        generated {ago(payload.data.generated_at)} · window {sinceDays}d · {repos.length} repos
      </span>
    </div>
    <div class="orgs">
      <button class="chip" class:active={org === 'all'} onclick={() => (org = 'all')}>all</button>
      {#each orgs as o (o)}
        <button class="chip" class:active={org === o} onclick={() => (org = o)}>
          <span class="dot" style="background: var(--cat{slots.get(o)})"></span>{o}
        </button>
      {/each}
    </div>
    <button
      class="chip"
      onclick={() => (theme = theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto')}
    >
      ◐ {theme}
    </button>
  </header>
  <nav>
    {#each TABS as [id, label], i (id)}
      <button class:active={tab === id} onclick={() => (tab = id)}>{label} <kbd>{i + 1}</kbd></button>
    {/each}
  </nav>
  <main>
    {#if tab === 'brief'}
      <Brief repos={visible} {agg} {epics} onselect={(r) => (selected = r)} gototab={(t) => (tab = t)} />
    {:else if tab === 'todo'}
      <Todos repos={visible} {epics} onselect={(r) => (selected = r)} />
    {:else if tab === 'repos'}
      <Repos repos={visible} {sinceDays} onselect={(r) => (selected = r)} />
    {:else if tab === 'activity'}
      <Activity repos={visible} {sinceDays} onselect={(r) => (selected = r)} />
    {:else if tab === 'work'}
      <Work repos={visible} onselect={(r) => (selected = r)} />
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
    gap: 16px;
    flex-wrap: wrap;
    padding: 14px 22px 0;
  }
  .brand { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  h1 { font-size: 19px; margin: 0; }
  .meta { color: var(--muted); font-size: 12px; }
  .orgs { display: flex; gap: 6px; margin-left: auto; }
  nav {
    display: flex;
    gap: 2px;
    padding: 10px 22px 0;
    border-bottom: 1px solid var(--grid);
  }
  nav button {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 12px;
    cursor: pointer;
    color: var(--ink-2);
  }
  nav button.active {
    color: var(--ink);
    border-bottom-color: var(--accent);
    font-weight: 600;
  }
  main { padding: 18px 22px 60px; max-width: 1280px; margin: 0 auto; }
  .tooltip {
    position: fixed;
    z-index: 30;
    max-width: 260px;
    background: var(--ink);
    color: var(--plane);
    font-size: 12px;
    padding: 6px 9px;
    border-radius: 6px;
    pointer-events: none;
    white-space: pre-line;
  }
  .fatal { padding: 60px; text-align: center; color: var(--critical); }
</style>
