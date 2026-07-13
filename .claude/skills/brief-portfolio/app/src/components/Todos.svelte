<script>
  import { getContext } from 'svelte'
  import { slug, allTodos } from '../lib/derive.js'
  import { loadDone, saveDone } from '../lib/done.js'
  import Icon from './Icon.svelte'

  const KIND_ICON = { local: 'wip', external: 'pr' } // other kinds share the icon name

  let { repos, epics, external, onselect } = $props()
  const slots = getContext('slots')

  let done = $state(loadDone())
  let hideDone = $state(false)
  let copied = $state('')

  const byslug = $derived(new Map(repos.map((r) => [slug(r), r])))
  const todos = $derived(allTodos(repos, epics, external))
  const groups = $derived(
    ['now', 'soon', 'later'].map((u) => ({
      u,
      all: todos.filter((t) => t.urgency === u),
      shown: todos.filter((t) => t.urgency === u && !(hideDone && done.has(t.id))),
    }))
  )
  const openCount = $derived(todos.filter((t) => !done.has(t.id)).length)

  function toggle(id) {
    const s = new Set(done)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    done = s
    saveDone(s)
  }
  async function copy(items, label) {
    const open = items.filter((t) => !done.has(t.id))
    const md = open.map((t) => `- [ ] ${t.repo}: ${t.action}`).join('\n')
    await navigator.clipboard.writeText(md)
    copied = label
    setTimeout(() => (copied = ''), 1500)
  }
</script>

<div class="bar">
  <span class="count"><b>{openCount}</b> open follow-ups · checked state survives regeneration</span>
  <button class="chip" class:active={hideDone} onclick={() => (hideDone = !hideDone)}>hide done</button>
  <button class="chip" onclick={() => copy(todos, 'all')}>
    {copied === 'all' ? '✓ copied' : 'copy open as markdown'}
  </button>
</div>

{#each groups as { u, all, shown } (u)}
  {#if all.length}
    <section class="sec">
      <h2 class="u-{u}">
        {u} · {all.filter((t) => !done.has(t.id)).length} open
        <button class="chip mini" onclick={() => copy(all, u)}>{copied === u ? '✓' : 'copy'}</button>
      </h2>
      {#each shown as t (t.id)}
        <div class="todo" class:isdone={done.has(t.id)}>
          <input type="checkbox" id={t.id} checked={done.has(t.id)} onchange={() => toggle(t.id)} />
          <label for={t.id}>
            <span class="action">
              {#if t.url}<a href={t.url} target="_blank" rel="noreferrer">{t.action}</a>{:else}{t.action}{/if}
            </span>
            {#if t.why}<span class="why">{t.why}</span>{/if}
          </label>
          {#if t.agent}<span class="lbl agent">→ {t.agent}</span>{/if}
          <span class="lbl"><Icon name={KIND_ICON[t.kind] ?? t.kind} size={11} /> {t.kind}{t.manual ? ' ✦' : ''}</span>
          {#if byslug.has(t.repo)}
            <button class="repobtn" onclick={() => onselect(byslug.get(t.repo))}>
              <span class="dot" style="background: var(--cat{slots.get(byslug.get(t.repo).org)})"></span>
              {t.repo}
            </button>
          {:else}
            <span class="lbl">{t.repo}</span>
          {/if}
        </div>
      {/each}
    </section>
  {/if}
{/each}
{#if todos.length === 0}
  <p class="empty">Nothing to do. Enjoy it.</p>
{/if}

<style>
  .bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .count { color: var(--ink-2); }
  .u-now { color: var(--critical); }
  .u-soon { color: var(--serious); }
  .u-later { color: var(--muted); }
  .sec > h2 { display: flex; align-items: center; gap: 10px; }
  .mini { padding: 1px 8px; font-size: 11px; }
  .todo {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 7px 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 7px;
    margin-bottom: 5px;
  }
  .todo:nth-of-type(even) { background: color-mix(in srgb, var(--plane) 45%, var(--surface)); }
  .todo input { margin: 0; accent-color: var(--accent); }
  .todo label { flex: 1; cursor: pointer; }
  .isdone .action { text-decoration: line-through; color: var(--muted); }
  .isdone .action a { text-decoration: line-through; color: var(--muted); }
  .why { color: var(--muted); font-size: 12px; margin-left: 8px; }
  .agent { color: var(--accent); border-color: var(--accent); }
  .todo .repobtn { white-space: nowrap; font-size: 12.5px; }
  .empty { color: var(--muted); margin-top: 20px; }
</style>
