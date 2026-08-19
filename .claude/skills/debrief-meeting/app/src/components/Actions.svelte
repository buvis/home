<script>
  import { getContext } from 'svelte'
  import { actionsCsv, actionsMarkdown } from '../lib/derive.js'
  import Cue from './Cue.svelte'
  import CopyButton from './CopyButton.svelte'

  const { extract, meta } = getContext('meeting')
  const actions = extract.actions ?? []
  const owners = ['all', ...new Set(actions.map((a) => a.assignee ?? 'unassigned'))]

  const KEY = `debrief-done:${meta.title ?? 'meeting'}`
  const stored = () => {
    try {
      return new Set(JSON.parse(localStorage.getItem(KEY) ?? '[]'))
    } catch {
      return new Set()
    }
  }

  let done = $state(stored())
  let owner = $state('all')
  let openRow = $state(null)

  function toggle(id) {
    const next = new Set(done)
    if (!next.delete(id)) next.add(id)
    done = next
    localStorage.setItem(KEY, JSON.stringify([...next]))
  }

  const shown = $derived(
    owner === 'all' ? actions : actions.filter((a) => (a.assignee ?? 'unassigned') === owner),
  )
</script>

{#if !actions.length}
  <p class="empty">No action items were extracted from this meeting.</p>
{:else}
  <section class="sec">
    <h2>Actions <span class="muted">({done.size}/{actions.length} done)</span></h2>

    <div class="chips">
      {#each owners as name, i (i)}
        <button class="chip" aria-pressed={owner === name} onclick={() => (owner = name)}>
          {name}
        </button>
      {/each}
      <CopyButton text={() => actionsMarkdown(shown)} label="Copy markdown" />
      <CopyButton text={() => actionsCsv(shown)} label="Copy CSV" />
    </div>

    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th></th>
            <th>Action</th>
            <th>Owner</th>
            <th>Due</th>
            <th>Said at</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as action, i (action.id ?? i)}
            {@const id = action.id ?? action.action}
            <tr>
              <td>
                <input
                  type="checkbox"
                  checked={done.has(id)}
                  onchange={() => toggle(id)}
                  aria-label="Mark done"
                />
              </td>
              <td>
                <button
                  class="linkish {done.has(id) ? 'done' : ''}"
                  onclick={() => (openRow = openRow === id ? null : id)}
                >
                  {action.action}
                </button>
                <span class="row">
                  {#if action.priority && action.priority !== 'normal'}
                    <span class="lbl sev-{action.priority}">{action.priority}</span>
                  {/if}
                  {#if action.status && action.status !== 'new'}
                    <span class="lbl">{action.status}</span>
                  {/if}
                  {#if action.confidence === 'low'}
                    <span class="lbl sev-warning">unsure</span>
                  {/if}
                </span>
                {#if openRow === id}
                  <div class="detail">
                    {#if action.quote}<div class="muted">“{action.quote}”</div>{/if}
                    {#if action.blocked_by}<div>Blocked by: {action.blocked_by}</div>{/if}
                    {#if action.assignee_confidence}
                      <div class="muted">owner confidence: {action.assignee_confidence}</div>
                    {/if}
                  </div>
                {/if}
              </td>
              <td>{action.assignee ?? '—'}</td>
              <td>{action.due ?? action.due_raw ?? '—'}</td>
              <td><Cue t={action.t} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}

<style>
  .linkish {
    background: none;
    border: none;
    padding: 0;
    text-align: left;
    cursor: pointer;
    font-weight: 550;
  }
  .linkish:hover { color: var(--accent); }
  .detail {
    margin-top: 0.25rem;
    padding-left: 0.625rem;
    border-left: 2px solid var(--grid);
    font-size: 0.8125rem;
  }
</style>
