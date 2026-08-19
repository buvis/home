<script>
  import { getContext } from 'svelte'
  import { COLORS, fmtTime, markers } from '../lib/derive.js'
  import Cue from './Cue.svelte'

  const { transcript, extract, speakers, jump } = getContext('meeting')

  const duration = transcript.meta.duration
  const topics = extract.topics ?? []
  const pins = markers(extract)
  const series = transcript.buckets?.series ?? []
  const totals = series.map((b) => Object.values(b.by).reduce((a, n) => a + n, 0))
  const peak = Math.max(1, ...totals)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({ at: f * 100, label: fmtTime(f * duration) }))

  const KIND = {
    decision: { glyph: '◆', color: 'var(--cat5)' },
    action: { glyph: '●', color: 'var(--cat1)' },
    question: { glyph: '?', color: 'var(--warning)' },
    risk: { glyph: '▲', color: 'var(--critical)' },
  }

  const pct = (seconds) => `${Math.min(100, Math.max(0, (seconds / duration) * 100))}%`
  const span = (topic) => `${Math.max(0.6, (((topic.end ?? topic.t) - topic.t) / duration) * 100)}%`
</script>

{#if !duration}
  <p class="empty">This transcript carries no timecodes, so there is no timeline to draw.</p>
{:else}
  <section class="sec">
    <h2>Timeline</h2>

    <div class="pins">
      {#each pins as pin, i (i)}
        <button
          class="pin"
          style="left: {pct(pin.t)}; color: {KIND[pin.kind].color}"
          title="{pin.kind}: {pin.label} ({fmtTime(pin.t)})"
          onclick={() => jump(pin.t)}
        >{KIND[pin.kind].glyph}</button>
      {/each}
    </div>

    {#each topics as topic, i (topic.id ?? i)}
      <div class="lane">
        <div class="lane-name" title={topic.title}>{topic.title}</div>
        <div class="track">
          <button
            class="band"
            style="left: {pct(topic.t)}; width: {span(topic)}; background: {COLORS[i % COLORS.length]}"
            title="{topic.title} — {fmtTime(topic.t)}"
            onclick={() => jump(topic.t)}
            aria-label="Jump to {topic.title}"
          ></button>
        </div>
      </div>
    {/each}

    <div class="lane">
      <div class="lane-name muted">who is talking</div>
      <div class="strip">
        {#each series as bucket, i (i)}
          <div class="col" style="height: {(totals[i] / peak) * 100}%" title={fmtTime(bucket.t)}>
            {#each Object.entries(bucket.by) as [sid, words] (sid)}
              <div style="flex: {words}; background: {speakers.get(sid)?.color ?? 'var(--grid)'}"></div>
            {/each}
          </div>
        {/each}
      </div>
    </div>

    <div class="lane">
      <div class="lane-name"></div>
      <div class="axis">
        {#each ticks as tick (tick.at)}
          <span style="left: {tick.at}%">{tick.label}</span>
        {/each}
      </div>
    </div>

    <div class="chips" style="margin-top: 0.75rem">
      {#each Object.entries(KIND) as [kind, k] (kind)}
        <span class="lbl"><span style="color: {k.color}">{k.glyph}</span> {kind}</span>
      {/each}
      {#each transcript.speakers as speaker (speaker.id)}
        <span class="lbl">
          <span class="dot" style="background: {speakers.get(speaker.id).color}"></span>
          {speaker.name}
        </span>
      {/each}
    </div>
  </section>

  {#if topics.length}
    <section class="sec">
      <h2>What was discussed</h2>
      {#each topics as topic, i (topic.id ?? i)}
        <div class="card" style="border-left-color: {COLORS[i % COLORS.length]}">
          <div class="spread">
            <h3>{topic.title}</h3>
            <Cue t={topic.t} label="{fmtTime(topic.t)} – {fmtTime(topic.end)}" />
          </div>
          {#if topic.summary}<p>{topic.summary}</p>{/if}
          {#if topic.notes?.length}
            <ul>
              {#each topic.notes as note, ni (ni)}<li>{note}</li>{/each}
            </ul>
          {/if}
        </div>
      {/each}
    </section>
  {/if}
{/if}

<style>
  .pins {
    position: relative;
    height: 1.25rem;
    margin-left: 9rem;
  }
  .pin {
    position: absolute;
    transform: translateX(-50%);
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    font-size: 0.75rem;
    line-height: 1;
  }
  .lane { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.1875rem; }
  .lane-name {
    width: 8.5rem;
    flex: none;
    font-size: 0.75rem;
    text-align: right;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .track {
    position: relative;
    flex: 1;
    height: 0.875rem;
    background: var(--surface);
    border: 1px solid var(--grid);
    border-radius: 0.125rem;
  }
  .band {
    position: absolute;
    top: 0;
    bottom: 0;
    border: none;
    border-radius: 0.125rem;
    cursor: pointer;
    padding: 0;
  }
  .strip {
    flex: 1;
    display: flex;
    align-items: flex-end;
    gap: 1px;
    height: 3rem;
    border-bottom: 1px solid var(--axis);
  }
  .col { flex: 1; display: flex; flex-direction: column-reverse; min-height: 1px; }
  .axis { position: relative; flex: 1; height: 1.125rem; font-size: 0.6875rem; color: var(--muted); }
  .axis span { position: absolute; transform: translateX(-50%); }
</style>
