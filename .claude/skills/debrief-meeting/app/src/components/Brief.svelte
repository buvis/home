<script>
  import { getContext } from 'svelte'
  import { fmtDur } from '../lib/derive.js'
  import Cue from './Cue.svelte'
  import CopyButton from './CopyButton.svelte'

  const { transcript, extract, extractRan } = getContext('meeting')

  const open = (extract.questions ?? []).filter((q) => !q.answered)
  const unresolvedRisks = (extract.risks ?? []).filter((r) => !r.addressed)
  const paragraphs = (extract.summary ?? '').split(/\n\s*\n/).filter(Boolean)
  const tiles = [
    [fmtDur(transcript.meta.duration), 'duration'],
    [transcript.speakers.length, 'speaking'],
    [extractRan ? (extract.decisions?.length ?? 0) : '—', 'decisions'],
    [extractRan ? (extract.actions?.length ?? 0) : '—', 'actions'],
    [extractRan ? open.length : '—', 'open questions'],
    [unresolvedRisks.length, 'live risks'],
  ]
</script>

<section class="sec">
  <h2>At a glance</h2>
  <div class="tiles">
    {#each tiles as [value, key] (key)}
      <div class="tile"><div class="n">{value}</div><div class="k">{key}</div></div>
    {/each}
  </div>
  {#if !extractRan}<div class="muted">The extraction step hasn't run — decisions, actions, and open questions above are not counted.</div>{/if}
</section>

{#if extract.tldr?.length}
  <section class="sec">
    <h2>The short version</h2>
    <ul>
      {#each extract.tldr as line, i (i)}<li>{line}</li>{/each}
    </ul>
  </section>
{/if}

{#if paragraphs.length}
  <section class="sec">
    <h2>Notes</h2>
    {#each paragraphs as para, i (i)}<p>{para}</p>{/each}
  </section>
{/if}

{#if extract.agenda?.length}
  <section class="sec">
    <h2>Agenda</h2>
    {#each extract.agenda as item, i (i)}
      <div class="card">
        <div class="spread">
          <h3>{item.title}</h3>
          <div class="row">
            <span
              class="lbl {item.coverage === 'skipped'
                ? 'sev-critical'
                : item.coverage === 'partial'
                  ? 'sev-warning'
                  : 'sev-good'}"
            >
              {item.coverage ?? 'covered'}
            </span>
            {#if item.planned === false}<span class="lbl">unplanned</span>{/if}
            <Cue t={item.t} />
          </div>
        </div>
        {#if item.note}<div class="muted">{item.note}</div>{/if}
      </div>
    {/each}
  </section>
{/if}

{#if open.length}
  <section class="sec">
    <h2>Left open</h2>
    {#each open as item, i (i)}
      <div class="card" style="border-left-color: var(--warning)">
        <div class="spread"><h3>{item.q}</h3><Cue t={item.t} /></div>
        <div class="muted">
          asked by {item.asked_by ?? 'someone'}{item.owner ? ` · owner ${item.owner}` : ''}
        </div>
      </div>
    {/each}
  </section>
{/if}

{#if extract.followups?.length}
  <section class="sec">
    <h2>Next time</h2>
    <ul>
      {#each extract.followups as item, i (i)}
        <li>{item.what}{item.when ? ` — ${item.when}` : ''}{item.who ? ` (${item.who})` : ''}</li>
      {/each}
    </ul>
  </section>
{/if}

{#if extract.email}
  <section class="sec">
    <h2>Follow-up email</h2>
    <div class="chips"><CopyButton text={extract.email} label="Copy email" /></div>
    <pre class="card mono" style="white-space: pre-wrap">{extract.email}</pre>
  </section>
{/if}
