<script>
  import { getContext } from 'svelte'
  import { fmtTime, highlight } from '../lib/derive.js'

  const { transcript, speakers, view } = getContext('meeting')
  const turns = transcript.turns
  let showRaw = $state(false)

  const shown = $derived(
    turns.filter(
      (turn) =>
        (view.speaker === 'all' || turn.s === view.speaker) &&
        (!view.query.trim() || turn.text.toLowerCase().includes(view.query.trim().toLowerCase())),
    ),
  )

  // scroll the jumped-to turn into view once the filtered list has rendered
  $effect(() => {
    if (view.focus < 0) return
    document.getElementById(`turn-${view.focus}`)?.scrollIntoView({ block: 'center' })
  })
</script>

<section class="sec">
  <h2>Transcript</h2>

  <div class="chips">
    <input
      type="search"
      placeholder="Search the transcript"
      aria-label="Search the transcript"
      bind:value={view.query}
    />
    <button
      class="chip"
      aria-pressed={view.speaker === 'all'}
      onclick={() => (view.speaker = 'all')}
    >
      everyone
    </button>
    {#each transcript.speakers as person (person.id)}
      <button
        class="chip"
        aria-pressed={view.speaker === person.id}
        onclick={() => (view.speaker = person.id)}
      >
        <span class="dot" style="background: {speakers.get(person.id).color}"></span>
        {person.name}
      </button>
    {/each}
    <button class="chip" aria-pressed={showRaw} onclick={() => (showRaw = !showRaw)}>
      original wording
    </button>
    <span class="muted" aria-live="polite">{shown.length} of {turns.length} turns</span>
  </div>

  {#each shown as turn (turn.i)}
    <article id="turn-{turn.i}" class="turn" class:focused={turn.i === view.focus}>
      <div class="meta">
        <button class="cue" onclick={() => (view.focus = turn.i)}>{fmtTime(turn.t)}</button>
        <span class="who" style="color: {speakers.get(turn.s)?.color ?? 'var(--ink-2)'}">
          {speakers.get(turn.s)?.name ?? 'Unknown'}
        </span>
        {#if turn.raw}<span class="lbl" title={turn.raw}>edited</span>{/if}
      </div>
      <p>
        {#each highlight(showRaw && turn.raw ? turn.raw : turn.text, view.query) as part, i (i)}
          {#if part.hit}<mark>{part.text}</mark>{:else}{part.text}{/if}
        {/each}
      </p>
    </article>
  {:else}
    <p class="empty">Nothing matches that filter.</p>
  {/each}
</section>

<style>
  .turn {
    /* ponytail: native render-skipping instead of a virtual-list dependency;
       swap in @tanstack/svelte-virtual only if very long meetings actually stutter */
    content-visibility: auto;
    contain-intrinsic-size: auto 3.5rem;
    padding: 0.375rem 0.5rem;
    border-left: 0.1875rem solid transparent;
  }
  .turn.focused {
    background: color-mix(in srgb, var(--lcars-a) 22%, var(--surface));
    border-left-color: var(--lcars-a);
  }
  .meta { display: flex; align-items: center; gap: 0.5rem; }
  .who { font-weight: 600; font-size: 0.8125rem; }
  .turn p { margin: 0.125rem 0 0; }
</style>
