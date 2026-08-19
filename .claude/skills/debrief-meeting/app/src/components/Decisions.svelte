<script>
  import { getContext } from 'svelte'
  import { adrMarkdown } from '../lib/derive.js'
  import Cue from './Cue.svelte'
  import CopyButton from './CopyButton.svelte'

  const { extract, meta, extractRan } = getContext('meeting')
  const decisions = extract.decisions ?? []

  let openId = $state(null)

  const STATUS = {
    made: 'sev-good',
    deferred: 'sev-warning',
    blocked: 'sev-critical',
    revisit: 'sev-serious',
  }
  const allAdrs = () => decisions.map((d) => adrMarkdown(d, meta)).join('\n\n---\n\n')
</script>

{#if !extractRan}
  <p class="empty">The extraction step hasn't run — no decisions to show yet.</p>
{:else if !decisions.length}
  <p class="empty">No decisions were extracted from this meeting.</p>
{:else}
  <section class="sec">
    <h2>Decisions</h2>
    <div class="chips">
      <CopyButton text={allAdrs} label="Copy all ADRs" />
    </div>

    {#each decisions as decision, i (decision.id ?? i)}
      {@const id = decision.id ?? `d${i}`}
      <div class="card">
        <div class="spread">
          <h3>{decision.title ?? decision.decision}</h3>
          <div class="row">
            <span class="lbl {STATUS[decision.status] ?? ''}">{decision.status ?? 'made'}</span>
            {#if decision.confidence === 'low'}<span class="lbl sev-warning">unsure</span>{/if}
            <Cue t={decision.t} />
          </div>
        </div>

        {#if decision.decision && decision.decision !== decision.title}
          <p>{decision.decision}</p>
        {/if}
        <div class="muted">
          {decision.decider ? `decided by ${decision.decider}` : 'no clear decider'}
        </div>

        <div class="row" style="margin-top: 0.5rem">
          <button class="chip" onclick={() => (openId = openId === id ? null : id)}>
            {openId === id ? 'Hide ADR' : 'Show ADR'}
          </button>
          <CopyButton text={() => adrMarkdown(decision, meta)} label="Copy ADR" />
        </div>

        {#if openId === id}
          <pre class="adr mono">{adrMarkdown(decision, meta)}</pre>
        {/if}
      </div>
    {/each}
  </section>
{/if}

<style>
  .adr {
    margin: 0.625rem 0 0;
    padding: 0.75rem;
    background: var(--raised);
    border: 1px solid var(--grid);
    border-radius: 0.25rem;
    white-space: pre-wrap;
    overflow-x: auto;
  }
</style>
