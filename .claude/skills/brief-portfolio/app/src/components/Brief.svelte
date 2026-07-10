<script>
  import { getContext } from 'svelte'
  import { slug, worstSev } from '../lib/derive.js'

  let { repos, agg, epics, onselect, gototab } = $props()
  const scored = getContext('scored')
  const slots = getContext('slots')

  const queue = $derived(
    repos
      .map((r) => ({ r, ...scored.get(slug(r)) }))
      .filter((x) => x.score > 0)
      .toSorted((a, b) => b.score - a.score)
  )
  const paragraphs = $derived((epics.summary ?? '').split(/\n\n+/).filter(Boolean))
</script>

<section class="tiles">
  <button class="tile" onclick={() => gototab('repos')}><b>{agg.repos}</b><span>repos</span></button>
  <button class="tile" onclick={() => gototab('activity')}><b>{agg.commits}</b><span>commits</span></button>
  <button class="tile" onclick={() => gototab('work')}>
    <b>{agg.prs}</b><span>open PRs{agg.depPrs ? ` (${agg.depPrs} deps)` : ''}</span>
  </button>
  <button class="tile" onclick={() => gototab('work')}><b>{agg.issues}</b><span>open issues</span></button>
  <button class="tile" class:bad={agg.failing > 0} onclick={() => gototab('work')}>
    <b>{agg.failing}</b><span>failing CI</span>
  </button>
  <button class="tile" onclick={() => gototab('prds')}>
    <b>{agg.backlog}</b><span>PRDs backlog{agg.wip ? ` · ${agg.wip} wip` : ''}</span>
  </button>
  <button class="tile" onclick={() => gototab('activity')}><b>{agg.releases}</b><span>releases</span></button>
  <button class="tile" class:warn={agg.localWip > 0} onclick={() => gototab('repos')}>
    <b>{agg.localWip}</b><span>repos with local WIP</span>
  </button>
</section>

<section class="sec narrative">
  <h2>The story</h2>
  {#if paragraphs.length}
    {#each paragraphs as p, i (i)}<p>{p}</p>{/each}
  {:else}
    <p class="empty">No narrative yet — the epic-grouping step (epics.json) hasn't run.</p>
  {/if}
</section>

<section class="sec">
  <h2>Needs your attention</h2>
  {#if queue.length === 0}
    <p class="empty">Nothing. All {repos.length} repos are quiet.</p>
  {:else}
    {#each queue.slice(0, 15) as { r, score, reasons } (slug(r))}
      <div class="qrow">
        <span class="score">
          <span class="dot" style="background: var(--{worstSev(reasons)})"></span>
          <b>{score}</b>
        </span>
        <button class="repobtn" onclick={() => onselect(r)}>
          <span class="dot" style="background: var(--cat{slots.get(r.org)})"></span>{slug(r)}
        </button>
        <span class="reasons">{reasons.map((x) => x.text).join(' · ')}</span>
      </div>
    {/each}
    {#if repos.length - queue.length > 0}
      <p class="empty">{repos.length - queue.length} more repos need nothing right now.</p>
    {/if}
  {/if}
</section>

<style>
  .narrative p { max-width: 75ch; margin: 0 0 10px; color: var(--ink-2); }
  .narrative p:first-of-type { color: var(--ink); }
  .qrow {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 8px 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 7px;
    margin-bottom: 6px;
  }
  .score {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 52px;
    font-variant-numeric: tabular-nums;
  }
  .qrow .repobtn { white-space: nowrap; }
  .reasons { color: var(--ink-2); font-size: 13px; }
  .empty { color: var(--muted); }
</style>
