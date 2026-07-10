<script>
  import { getContext } from 'svelte'
  import { slug, weeklyBins, weekStart, monthLabels } from '../lib/derive.js'

  let { repos, sinceDays, onselect } = $props()
  const tip = getContext('tip')
  const slots = getContext('slots')

  const rows = $derived(
    repos
      .map((r) => ({ r, bins: weeklyBins(r.commits, sinceDays), total: r.commits?.length ?? 0 }))
      .filter((x) => x.total > 0)
      .toSorted((a, b) => b.total - a.total)
  )
  const max = $derived(Math.max(1, ...rows.flatMap((x) => x.bins)))
  const ncols = $derived(Math.ceil(sinceDays / 7))
  const labels = $derived(monthLabels(ncols, sinceDays))
  const level = (v) => (v === 0 ? 0 : Math.max(1, Math.round((v / max) * 5)))

  const releases = $derived(
    repos
      .flatMap((r) => (r.releases ?? []).map((x) => ({ ...x, r })))
      .filter((x) => x.date)
      .toSorted((a, b) => b.date.localeCompare(a.date))
  )
</script>

<section class="sec">
  <h2>Commit heat · {rows.length} active repos</h2>
  {#if rows.length === 0}
    <p class="empty">No commits in the last {sinceDays} days.</p>
  {:else}
    <div class="hm" style="--ncols: {ncols}">
      <span></span>
      {#each labels as m, i (i)}<span class="axis">{m}</span>{/each}
      {#each rows as { r, bins, total } (slug(r))}
        <button class="repobtn" onclick={() => onselect(r)}>
          <span class="dot" style="background: var(--cat{slots.get(r.org)})"></span>
          {r.name}<span class="tot">{total}</span>
        </button>
        {#each bins as v, i (i)}
          <div
            class="cell l{level(v)}"
            role="img"
            aria-label="{v} commits"
            onmouseenter={(e) => tip.show(e, `${slug(r)}\nweek of ${weekStart(i, sinceDays)} · ${v} commits`)}
            onmouseleave={tip.hide}
          ></div>
        {/each}
      {/each}
    </div>
    <div class="legend">
      less
      {#each [0, 1, 2, 3, 4, 5] as l (l)}<div class="cell l{l}"></div>{/each}
      more
    </div>
  {/if}
</section>

<section class="sec">
  <h2>Recent releases</h2>
  {#if releases.length === 0}
    <p class="empty">No releases collected.</p>
  {:else}
    <table>
      <thead><tr><th>date</th><th>repo</th><th>release</th></tr></thead>
      <tbody>
        {#each releases as x (slug(x.r) + x.tag)}
          <tr>
            <td class="num">{x.date}</td>
            <td>
              <button class="repobtn" onclick={() => onselect(x.r)}>
                <span class="dot" style="background: var(--cat{slots.get(x.r.org)})"></span>{slug(x.r)}
              </button>
            </td>
            <td>
              <a href="https://github.com/{slug(x.r)}/releases/tag/{x.tag}" target="_blank" rel="noreferrer">
                {x.name}
              </a>
              {#if x.prerelease}<span class="lbl">pre</span>{/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  .hm {
    display: grid;
    grid-template-columns: minmax(150px, max-content) repeat(var(--ncols), 15px);
    gap: 2px; /* the 2px surface gap between fills */
    align-items: center;
    overflow-x: auto;
    padding-bottom: 6px;
  }
  .hm .repobtn { padding-right: 12px; font-size: 12.5px; }
  .tot { color: var(--muted); margin-left: 6px; font-size: 11px; }
  .axis { font-size: 10px; color: var(--muted); }
  .cell {
    width: 13px;
    height: 13px;
    border-radius: 3px;
  }
  .cell.l0 { box-shadow: inset 0 0 0 1px var(--grid); }
  .cell.l1 { background: var(--seq-1); }
  .cell.l2 { background: var(--seq-2); }
  .cell.l3 { background: var(--seq-3); }
  .cell.l4 { background: var(--seq-4); }
  .cell.l5 { background: var(--seq-5); }
  .legend {
    display: flex;
    align-items: center;
    gap: 3px;
    margin-top: 8px;
    color: var(--muted);
    font-size: 11px;
  }
  .empty { color: var(--muted); }
</style>
