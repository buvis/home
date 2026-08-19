<script>
  import { getContext } from 'svelte'
  import Cue from './Cue.svelte'

  const { transcript, extract } = getContext('meeting')
  const entities = extract.entities ?? {}
  const groups = Object.entries(entities).filter(
    ([key, list]) => key !== 'metrics' && Array.isArray(list) && list.length,
  )
  const label = (item) =>
    typeof item === 'string' ? item : [item.name, item.role].filter(Boolean).join(' — ')
</script>

{#if extract.risks?.length}
  <section class="sec">
    <h2>Risks raised</h2>
    {#each extract.risks as risk, i (i)}
      <div class="card" style="border-left-color: var({risk.addressed ? '--good' : '--critical'})">
        <div class="spread">
          <h3>{risk.risk}</h3>
          <div class="row">
            {#if risk.severity}<span class="lbl sev-{risk.severity}">{risk.severity}</span>{/if}
            <span class="lbl">{risk.addressed ? 'addressed' : 'open'}</span>
            <Cue t={risk.t} />
          </div>
        </div>
        <div class="muted">raised by {risk.raised_by ?? 'someone'}</div>
        {#if risk.mitigation}<div>Mitigation: {risk.mitigation}</div>{/if}
      </div>
    {/each}
  </section>
{/if}

{#if extract.blockers?.length}
  <section class="sec">
    <h2>Blockers</h2>
    <ul>
      {#each extract.blockers as blocker, i (i)}
        <li>
          {blocker.what}
          {#if blocker.depends_on}<span class="muted"> — waiting on {blocker.depends_on}</span>{/if}
          {#if blocker.owner}<span class="muted"> ({blocker.owner})</span>{/if}
          <Cue t={blocker.t} />
        </li>
      {/each}
    </ul>
  </section>
{/if}

{#if extract.assumptions?.length}
  <section class="sec">
    <h2>Assumptions</h2>
    <p class="muted">Stated as fact in the room. Unvalidated ones are worth checking.</p>
    <ul>
      {#each extract.assumptions as item, i (i)}
        <li>
          {item.assumption}
          <span class="lbl {item.validated ? 'sev-good' : 'sev-warning'}">
            {item.validated ? 'validated' : 'unchecked'}
          </span>
          {#if item.by}<span class="muted">{item.by}</span>{/if}
          <Cue t={item.t} />
        </li>
      {/each}
    </ul>
  </section>
{/if}

{#if extract.disagreements?.length}
  <section class="sec">
    <h2>Where the room split</h2>
    {#each extract.disagreements as item, i (i)}
      <div class="card">
        <div class="spread">
          <h3>{item.topic}</h3>
          <div class="row">
            <span class="lbl {item.resolved ? 'sev-good' : 'sev-warning'}">
              {item.resolved ? 'resolved' : 'unresolved'}
            </span>
            <Cue t={item.t} />
          </div>
        </div>
        <ul>
          {#each item.positions ?? [] as position, i (i)}
            <li><strong>{position.who}</strong>: {position.stance}</li>
          {/each}
        </ul>
        {#if item.resolution}<div>Landed on: {item.resolution}</div>{/if}
      </div>
    {/each}
  </section>
{/if}

{#if extract.quotes?.length}
  <section class="sec">
    <h2>Worth quoting</h2>
    {#each extract.quotes as quote, i (i)}
      <div class="card">
        <p>“{quote.text}”</p>
        <div class="row muted">
          <span>{quote.who}</span>
          {#if quote.why}<span>· {quote.why}</span>{/if}
          <Cue t={quote.t} />
        </div>
      </div>
    {/each}
  </section>
{/if}

{#if entities.metrics?.length}
  <section class="sec">
    <h2>Numbers mentioned</h2>
    <div class="scroll">
      <table>
        <thead><tr><th>What</th><th>Value</th><th>Said at</th></tr></thead>
        <tbody>
          {#each entities.metrics as metric, i (i)}
            <tr>
              <td>{metric.label}</td>
              <td class="num">{metric.value}</td>
              <td><Cue t={metric.t} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}

{#if groups.length}
  <section class="sec">
    <h2>Named in the room</h2>
    {#each groups as [key, list] (key)}
      <div class="card">
        <h3>{key}</h3>
        <div class="chips" style="margin: 0.375rem 0 0">
          {#each list as item, i (i)}<span class="lbl">{label(item)}</span>{/each}
        </div>
      </div>
    {/each}
  </section>
{/if}

{#if extract.glossary?.length}
  <section class="sec">
    <h2>Jargon</h2>
    <div class="scroll">
      <table>
        <thead><tr><th>Term</th><th>Stands for</th><th>Means</th><th>First used</th></tr></thead>
        <tbody>
          {#each extract.glossary as entry, i (i)}
            <tr>
              <td class="mono">{entry.term}</td>
              <td>{entry.expansion ?? '—'}</td>
              <td>{entry.definition ?? '—'}</td>
              <td><Cue t={entry.t} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}

{#if extract.quality}
  <section class="sec">
    <h2>How the meeting ran</h2>
    {#if extract.quality.on_topic_ratio !== undefined}
      <p>Roughly {Math.round(extract.quality.on_topic_ratio * 100)}% of the time stayed on topic.</p>
    {/if}
    {#if extract.quality.tangents?.length}
      <ul>
        {#each extract.quality.tangents as tangent, i (i)}
          <li>{tangent.what} <Cue t={tangent.t} /></li>
        {/each}
      </ul>
    {/if}
    {#if extract.quality.notes?.length}
      <ul>
        {#each extract.quality.notes as note, i (i)}<li>{note}</li>{/each}
      </ul>
    {/if}
  </section>
{/if}

{#if transcript.corrections?.length}
  <section class="sec">
    <h2>Cleanup applied</h2>
    <p class="muted">What was changed before anything was read out of this transcript.</p>
    <ul>
      {#each transcript.corrections as fix, i (i)}
        <li>
          {#if fix.kind === 'speaker-merge'}
            Merged speaker <span class="mono">{fix.from}</span> into
            <span class="mono">{fix.to}</span>
          {:else if fix.kind === 'caption-dedup'}
            Dropped {fix.count} repeated live-caption lines
          {:else}
            Replaced <span class="mono">{fix.from}</span> with <span class="mono">{fix.to}</span>
            {#if fix.applied}<span class="muted"> ({fix.applied}×)</span>{/if}
            {#if fix.reason}<span class="muted"> — {fix.reason}</span>{/if}
          {/if}
        </li>
      {/each}
    </ul>
  </section>
{/if}
