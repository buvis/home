<script>
  import { getContext } from 'svelte'
  import { slug, ciFailing, weeklyBins, ago } from '../lib/derive.js'
  import Sparkline from './Sparkline.svelte'

  let { repos, sinceDays, onselect } = $props()
  const scored = getContext('scored')
  const slots = getContext('slots')
  let search = $state('')
  let sort = $state('attention')
  let searchEl = $state()

  const sorts = {
    attention: (a, b) => scored.get(slug(b)).score - scored.get(slug(a)).score,
    activity: (a, b) => (b.commits?.length ?? 0) - (a.commits?.length ?? 0),
    pushed: (a, b) => (b.pushed_at ?? '').localeCompare(a.pushed_at ?? ''),
    name: (a, b) => slug(a).localeCompare(slug(b)),
  }
  const shown = $derived.by(() => {
    const q = search.toLowerCase()
    return repos
      .filter((r) => `${slug(r)} ${r.description ?? ''} ${r.language ?? ''}`.toLowerCase().includes(q))
      .toSorted(sorts[sort])
  })

  function onkeydown(e) {
    if (e.key === '/' && !e.target.closest('input, textarea')) {
      e.preventDefault()
      searchEl?.focus()
    }
  }
</script>

<svelte:window {onkeydown} />

<div class="bar">
  <input bind:this={searchEl} bind:value={search} placeholder="filter repos… ( / )" />
  <select bind:value={sort}>
    <option value="attention">sort: attention</option>
    <option value="activity">sort: activity</option>
    <option value="pushed">sort: last push</option>
    <option value="name">sort: name</option>
  </select>
  <span class="count">{shown.length} shown</span>
</div>

<div class="grid">
  {#each shown as r (slug(r))}
    {@const fails = ciFailing(r)}
    {@const sc = scored.get(slug(r))}
    {@const wip = (r.local?.dirty ?? 0) + (r.local?.ahead ?? 0) > 0}
    <button class="card" onclick={() => onselect(r)}>
      <div class="head">
        <span class="dot" style="background: var(--cat{slots.get(r.org)})"></span>
        <b>{r.name}</b>
        {#if r.visibility === 'private'}<span class="lbl">private</span>{/if}
        {#if sc.score > 0}<span class="scorelbl">{sc.score}</span>{/if}
      </div>
      {#if r.description}<p class="desc">{r.description}</p>{/if}
      <div class="badges">
        {#if r.ci?.length}
          <span class={fails.length ? 'sev-critical' : 'sev-good'}>
            {fails.length ? `✗ CI ${fails.length}` : '✓ CI'}
          </span>
        {/if}
        {#if r.prs?.length}<span>⇄ {r.prs.length}</span>{/if}
        {#if r.issues?.length}<span>◎ {r.issues.length}</span>{/if}
        {#if r.unreleased_commits >= 10}<span class="sev-warning">↟ {r.unreleased_commits}</span>{/if}
        {#if wip}<span class="sev-serious">● WIP</span>{/if}
        {#if r.prds?.backlog.length}<span>▤ {r.prds.backlog.length}</span>{/if}
      </div>
      <div class="foot">
        <Sparkline values={weeklyBins(r.commits, sinceDays)} />
        <span class="meta">{r.language || '—'} · pushed {ago(r.pushed_at)}</span>
      </div>
    </button>
  {/each}
</div>

<style>
  .bar { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
  input, select {
    font: inherit;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--grid);
    border-radius: 7px;
    padding: 6px 10px;
  }
  input { width: 260px; }
  .count { color: var(--muted); font-size: 12px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
    gap: 10px;
  }
  .card {
    text-align: left;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 12px 14px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .card:hover { border-color: var(--axis); }
  .head { display: flex; align-items: center; gap: 8px; }
  .head b { font-size: 15px; }
  .scorelbl {
    margin-left: auto;
    font-size: 12px;
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }
  .desc {
    margin: 0;
    color: var(--ink-2);
    font-size: 12.5px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .badges { display: flex; gap: 12px; font-size: 12.5px; color: var(--ink-2); flex-wrap: wrap; }
  .foot { display: flex; align-items: center; justify-content: space-between; margin-top: auto; }
  .meta { color: var(--muted); font-size: 11.5px; }
</style>
