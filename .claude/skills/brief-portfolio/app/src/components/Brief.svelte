<script>
  import { getContext } from 'svelte'
  import { slug, worstSev, allTodos, quickWins, sinceLast, historySeries, ago } from '../lib/derive.js'
  import { loadDone } from '../lib/done.js'
  import Horizon from './Horizon.svelte'
  import Sparkline from './Sparkline.svelte'
  import Strip from './Strip.svelte'
  import Icon from './Icon.svelte'

  let { repos, agg, epics, sinceDays, prev, history, external, skillAdherence, onselect, gototab } = $props()
  const scored = getContext('scored')
  const slots = getContext('slots')

  const queue = $derived(
    repos
      .map((r) => ({ r, ...scored.get(slug(r)) }))
      .filter((x) => x.score > 0)
      .toSorted((a, b) => b.score - a.score)
  )
  const fires = $derived(queue.filter((x) => worstSev(x.reasons) === 'critical'))
  const paragraphs = $derived((epics.summary ?? '').split(/\n\n+/).filter(Boolean))
  const byslug = $derived(new Map(repos.map((r) => [slug(r), r])))
  const wins = $derived(quickWins(allTodos(repos, epics, external), loadDone()))
  const delta = $derived(sinceLast(repos, prev))
  const trend = $derived(historySeries(history))

  const STATS = $derived([
    ['commit', agg.commits, 'commits', 'activity'],
    ['pr', agg.prs, 'open PRs', 'work'],
    ['issue', agg.issues, 'issues', 'work'],
    ['ci', agg.failing, 'failing CI', 'work', agg.failing > 0],
    ['security', agg.alerts, 'security', 'todo', agg.alerts > 0],
    ['prd', agg.backlog, 'PRD backlog', 'prds'],
    ['release', agg.releases, 'releases', 'activity'],
    ['wip', agg.localWip, 'local WIP', 'repos', false, agg.localWip > 0],
  ])
</script>

<div class="stage">
  <section class="glass bar">
    <p class="head">
      <b>{repos.length}</b> repos ·
      <b class:hot={fires.length}>{fires.length}</b> burning
      {#if skillAdherence}
        · <b>{skillAdherence.count}</b> skill runs/30d
        ({skillAdherence.distinct} distinct{#if skillAdherence.top?.length}, top {skillAdherence.top[0].skill}{/if})
      {/if}
    </p>
    <div class="mini">
      {#each STATS as [icon, v, label, tab, bad, warn] (label)}
        <button class="stat" class:bad class:warn onclick={() => gototab(tab)}>
          <span class="row"><span class="g"><Icon name={icon} size={13} /></span><b>{v}</b></span>
          <span class="lab">{label}</span>
        </button>
      {/each}
    </div>
  </section>

  <section class="glass bar wins">
    <h2>Quick wins</h2>
    {#if wins.length}
      <Strip>
        {#each wins as t (t.id)}
          <button
            class="win"
            onclick={() => (byslug.has(t.repo) ? onselect(byslug.get(t.repo)) : t.url && window.open(t.url))}
          >
            <span class="wact">{t.action}</span>
            <span class="wrepo">{t.repo}</span>
          </button>
        {/each}
      </Strip>
    {:else}
      <p class="calm"><Icon name="good" size={14} /> Nothing quick left.</p>
    {/if}
  </section>

  <section class="glass bar burn">
    <h2>Burning now</h2>
    {#if queue.length === 0}
      <p class="calm"><Icon name="good" size={14} /> All quiet. Nothing needs you.</p>
    {:else}
      <Strip>
        {#each queue.slice(0, 3) as { r, score, reasons } (slug(r))}
          {@const sev = worstSev(reasons)}
          <button
            class="brow"
            style="border-left-color: var(--cat{slots.get(r.org)})"
            onclick={() => onselect(r)}
          >
            <span class="sevg sev-{sev}"><Icon name={sev} size={13} /></span>
            <span class="bname">{r.name}</span>
            <b class="bscore sev-{sev}">{score}</b>
            <span class="meter">
              <span class="fill" style="width: {Math.min(100, (score / 150) * 100)}%; background: var(--{sev})"></span>
            </span>
            <span class="breasons">{reasons[0]?.text}</span>
          </button>
        {/each}
      </Strip>
    {/if}
  </section>

  <div class="mid">
    <aside class="glass side">
      <h2>The story</h2>
      {#if paragraphs.length}
        {#each paragraphs as p, i (i)}<p class="story">{p}</p>{/each}
      {:else}
        <p class="empty">No narrative yet — the epic-grouping step (epics.json) hasn't run.</p>
      {/if}
      {#if delta}
        <h2>Since last brief</h2>
        <p class="delta">
          vs {ago(delta.at)}:
          <b class="sev-good">{delta.cleared} cleared</b> ·
          <b class:sev-serious={delta.added > 0}>{delta.added} new</b>
        </p>
        {#each delta.movers.slice(0, 3) as m (slug(m.r))}
          <button class="mover" onclick={() => onselect(m.r)}>
            <b class={m.d > 0 ? 'sev-critical' : 'sev-good'}>{m.d > 0 ? '▲' : '▼'} {Math.abs(m.d)}</b>
            {slug(m.r)}
          </button>
        {/each}
        {#if trend.length >= 3}
          <div class="trend">
            <Sparkline values={trend.map((h) => h.open)} w={300} h={22} />
            <span class="tlab">open items across {trend.length} briefs</span>
          </div>
        {/if}
      {/if}
    </aside>

    <div class="field">
      <Horizon {repos} {onselect} />
      <p class="legend">
        center = needs you · size = activity · ring = state · moons = stashes/worktrees ·
        lit chevrons = burning repos
      </p>
    </div>
  </div>
</div>

<style>
  .stage {
    max-width: 1560px;
    margin: 0 auto;
    padding: 14px 18px 46px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .glass {
    padding: 14px 18px 16px;
    border: 1px solid var(--border);
    border-radius: 18px;
    background: color-mix(in srgb, var(--surface) 76%, transparent);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
  }
  /* LCARS segmented strip along the console top */
  .glass::before {
    content: '';
    display: block;
    height: 10px;
    border-radius: 999px;
    margin-bottom: 12px;
    background: linear-gradient(
      90deg,
      var(--lcars-a) 0 34%, transparent 34% 37%,
      var(--lcars-c) 37% 58%, transparent 58% 61%,
      var(--lcars-d) 61% 88%, transparent 88% 91%,
      var(--lcars-b) 91% 100%
    );
  }
  .glass.bar {
    display: flex;
    align-items: center;
    gap: 8px 16px;
    flex-wrap: wrap;
    padding: 8px 16px;
    border-left: 14px solid var(--lcars-a);
  }
  .glass.bar::before { display: none; }
  .bar .head { margin: 0; }
  .bar h2 { margin: 0; flex: none; }
  .bar p { margin: 0; }
  .bar.wins { border-left-color: var(--lcars-c); }
  .bar.burn { border-left-color: var(--lcars-b); }
  .bar.wins, .bar.burn { flex-wrap: nowrap; }
  .mid {
    display: grid;
    grid-template-columns: 2fr 3fr;
    gap: 12px;
    align-items: stretch;
  }
  .field {
    position: relative;
    min-height: 48vh;
  }
  .glass.side { border-left: 14px solid var(--lcars-d); }
  @media (max-width: 1100px) {
    .mid { grid-template-columns: 1fr; }
    .glass.side { order: 2; }
    .field { order: 1; min-height: 44vh; }
  }
  .head {
    font-family: var(--display);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 17px;
    font-weight: 650;
    margin: 0 0 7px;
  }
  .head .hot { color: var(--critical); }
  .mini {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .stat {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    padding: 3px 12px 3px 10px;
    background: color-mix(in srgb, var(--surface) 60%, transparent);
    border: 1px solid var(--border);
    border-radius: 999px 8px 8px 999px;
    cursor: pointer;
    text-align: left;
  }
  .stat:hover { border-color: var(--lcars-a); }
  .stat .row { display: flex; align-items: center; gap: 7px; }
  .stat b {
    font-family: var(--display);
    font-size: 15px;
    line-height: 1.1;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
  .stat .lab {
    max-width: 100%;
    color: var(--ink-2);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .stat.bad b { color: var(--critical); }
  .stat.warn b { color: var(--serious); }
  h2 {
    display: flex;
    align-items: center;
    gap: 9px;
    font-family: var(--display);
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    margin: 18px 0 8px;
  }
  h2::before {
    content: '';
    width: 24px;
    height: 11px;
    border-radius: 999px;
    background: var(--lcars-c);
    flex: none;
  }
  .glass.side h2:first-of-type { margin-top: 0; }
  .brow {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    max-width: 480px;
    min-width: 0;
    padding: 3px 12px 3px 8px;
    background: color-mix(in srgb, var(--surface) 60%, transparent);
    border: 1px solid var(--border);
    border-left: 5px solid transparent;
    border-radius: 999px 8px 8px 999px;
    cursor: pointer;
    text-align: left;
  }
  .brow:hover { border-color: var(--axis); }
  .sevg { flex: none; width: 16px; text-align: center; font-size: 13px; }
  .g { flex: none; width: 16px; text-align: center; color: var(--lcars-d); font-size: 13px; }
  .bname { font-size: 13px; font-weight: 650; white-space: nowrap; }
  .bscore { font-size: 12px; font-variant-numeric: tabular-nums; }
  .meter {
    flex: none;
    width: 54px;
    height: 5px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--axis) 35%, transparent);
    overflow: hidden;
  }
  .fill { display: block; height: 100%; border-radius: 999px; }
  .breasons {
    color: var(--ink-2);
    font-size: 11.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .calm { color: var(--good); font-weight: 650; }
  .win {
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    max-width: 420px;
    min-width: 0;
    padding: 3px 12px 3px 10px;
    background: color-mix(in srgb, var(--surface) 60%, transparent);
    border: 1px solid var(--border);
    border-left: 5px solid var(--good);
    border-radius: 999px 8px 8px 999px;
    cursor: pointer;
    text-align: left;
  }
  .win:hover { border-color: var(--axis); }
  .wact {
    font-size: 12.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .wrepo { color: var(--muted); font-size: 11px; white-space: nowrap; }
  .delta { margin: 0 0 8px; font-size: 13px; }
  .mover {
    display: block;
    width: 100%;
    padding: 3px 0;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    font-size: 13px;
  }
  .mover:hover { color: var(--accent); }
  .trend { margin-top: 8px; }
  .tlab { display: block; color: var(--muted); font-size: 11px; }
  .story { color: var(--ink-2); font-size: 13px; margin: 0 0 8px; }
  .story:first-of-type { color: var(--ink); }
  .field .legend {
    position: absolute;
    left: 14px;
    right: 14px;
    bottom: 6px;
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    text-align: center;
    pointer-events: none;
  }
  .empty { color: var(--muted); }
</style>
