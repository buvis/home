<script>
  import { getContext } from 'svelte'
  import { slug, wipItems } from '../lib/derive.js'

  let { repos } = $props()
  const slots = getContext('slots')

  const rows = $derived(
    repos
      .map((r) => ({ r, p: r.prds ?? { backlog: [], wip: [], done_count: 0 } }))
      .filter((x) => x.p.backlog.length || x.p.wip.length || x.p.done_count)
      .toSorted(
        (a, b) => b.p.wip.length - a.p.wip.length || b.p.backlog.length - a.p.backlog.length
      )
  )
  const tot = $derived(
    rows.reduce(
      (s, x) => ({
        b: s.b + x.p.backlog.length,
        w: s.w + x.p.wip.length,
        d: s.d + x.p.done_count,
      }),
      { b: 0, w: 0, d: 0 }
    )
  )
</script>

<section class="sec">
  <h2>PRD pipeline · {tot.w} wip · {tot.b} backlog · {tot.d} done</h2>
  {#if rows.length === 0}
    <p class="empty">No PRDs found under dev/local/prds/ in any repo.</p>
  {:else}
    <div class="grid">
      {#each rows as { r, p } (slug(r))}
        <div class="card">
          <div class="head">
            <span class="dot" style="background: var(--cat{slots.get(r.org)})"></span>
            <b>{slug(r)}</b>
            <span class="donen">{p.done_count} done</span>
          </div>
          {#if p.wip.length}
            <h3>in progress</h3>
            <ul>
              {#each wipItems(p) as w (w.title)}
                <li class="sev-serious">
                  {w.title}{#if w.idle_days >= 7}<span class="idle">idle {w.idle_days}d</span>{/if}
                </li>
              {/each}
            </ul>
          {/if}
          {#if p.backlog.length}
            <h3>backlog</h3>
            <ul>{#each p.backlog as t (t)}<li>{t}</li>{/each}</ul>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 12px 14px;
  }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .donen { margin-left: auto; color: var(--muted); font-size: 11.5px; }
  h3 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin: 10px 0 4px;
  }
  ul { margin: 0; padding-left: 18px; color: var(--ink-2); }
  .idle { color: var(--muted); font-size: 11px; margin-left: 6px; }
  li { margin: 2px 0; }
  .empty { color: var(--muted); }
</style>
