<script>
  import { getContext } from 'svelte'
  import { allTodos, quadrant } from '../lib/derive.js'
  import { loadDone, saveDone } from '../lib/done.js'
  import Icon from './Icon.svelte'

  let { repos, epics, external, onselect } = $props()
  const slots = getContext('slots')

  let done = $state(loadDone())
  let hideDone = $state(true)

  const byslug = $derived(new Map(repos.map((r) => [`${r.owner}/${r.name}`, r])))
  const todos = $derived(allTodos(repos, epics, external))
  const QUADS = [
    ['do', 'Do now', 'urgent and important — start here', 'critical'],
    ['schedule', 'Schedule', 'important, waits for a real slot', 'serious'],
    ['delegate', 'Delegate to agents', 'not important — dispatch a command', 'warning'],
    ['drop', 'Drop / batch', 'batch monthly, or let it rot in peace', 'muted'],
  ]
  const byQuad = $derived.by(() => {
    const m = { do: [], schedule: [], delegate: [], drop: [] }
    for (const t of todos) m[quadrant(t)].push(t)
    return m
  })

  function toggle(id) {
    const s = new Set(done)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    done = s
    saveDone(s)
  }
</script>

<div class="bar">
  <span class="count">
    urgency from age and severity · importance from consequence (security, data loss, users waiting)
  </span>
  <button class="chip" class:active={hideDone} onclick={() => (hideDone = !hideDone)}>hide done</button>
</div>

<div class="matrix">
  {#each QUADS as [q, title, hint, tone] (q)}
    {@const items = byQuad[q]}
    {@const open = items.filter((t) => !done.has(t.id))}
    <section class="quad q-{q}">
      <h2 style="color: var(--{tone})">{title} · {open.length}</h2>
      <p class="hint">{hint}</p>
      {#each hideDone ? open : items as t (t.id)}
        <div class="item" class:isdone={done.has(t.id)}>
          <input type="checkbox" id="m-{t.id}" checked={done.has(t.id)} onchange={() => toggle(t.id)} />
          <label for="m-{t.id}">
            <span class="action">
              {#if t.url}<a href={t.url} target="_blank" rel="noreferrer">{t.action}</a>{:else}{t.action}{/if}
            </span>
            {#if t.why}<span class="why">{t.why}</span>{/if}
          </label>
          {#if t.agent}<span class="lbl agent">→ {t.agent}</span>{/if}
          {#if t.effort === 'quick'}<span class="lbl">quick</span>{/if}
          {#if byslug.has(t.repo)}
            <button class="repobtn" onclick={() => onselect(byslug.get(t.repo))}>
              <span class="dot" style="background: var(--cat{slots.get(byslug.get(t.repo).org)})"></span>
              {t.repo}
            </button>
          {:else}
            <span class="lbl"><Icon name="pr" size={11} /> {t.repo}</span>
          {/if}
        </div>
      {:else}
        <p class="empty">nothing here</p>
      {/each}
    </section>
  {/each}
</div>

<style>
  .bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
  .count { color: var(--muted); font-size: 12px; }
  .matrix {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  @media (max-width: 900px) {
    .matrix { grid-template-columns: 1fr; }
  }
  .quad {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 14px;
    min-height: 140px;
  }
  .q-do { border-top: 5px solid var(--critical); }
  .q-schedule { border-top: 5px solid var(--serious); }
  .q-delegate { border-top: 5px solid var(--lcars-c); }
  .q-drop { border-top: 5px solid var(--grid); }
  .quad h2 {
    font-family: var(--display);
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 0;
  }
  .hint { color: var(--muted); font-size: 11.5px; margin: 2px 0 10px; }
  .item {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 6px 8px;
    border: 1px solid var(--grid);
    border-radius: 7px;
    margin-bottom: 5px;
    background: color-mix(in srgb, var(--plane) 40%, var(--surface));
  }
  .item input { margin: 0; accent-color: var(--accent); }
  .item label { flex: 1; cursor: pointer; min-width: 0; }
  .isdone .action { text-decoration: line-through; color: var(--muted); }
  .why { color: var(--muted); font-size: 12px; margin-left: 8px; }
  .agent { color: var(--accent); border-color: var(--accent); }
  .item .repobtn { white-space: nowrap; font-size: 12px; }
  .empty { color: var(--muted); font-size: 12.5px; }
</style>
