<script>
  import { getContext } from 'svelte'
  import { fmtDur, gini, topShare } from '../lib/derive.js'
  import Cue from './Cue.svelte'

  const { transcript, extract, meta, speakers } = getContext('meeting')
  const roster = transcript.speakers
  const matrix = transcript.matrix ?? {}
  const busiest = Math.max(1, ...Object.values(matrix).flatMap((row) => Object.values(row)))
  const dominance = gini(roster.map((s) => s.share_words))
  const silent = meta.attendees_not_speaking ?? []
  const shade = (count) =>
    count ? `color-mix(in srgb, var(--cat1) ${(count / busiest) * 70}%, transparent)` : 'transparent'
</script>

<section class="sec">
  <h2>Airtime</h2>
  <p>
    The two loudest voices took <strong>{topShare(roster, 2)}%</strong> of the words. Spread score
    {dominance}
    <span class="muted">(0 = even, 1 = one person)</span>.
  </p>

  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th>Who</th>
          <th>Share of words</th>
          <th class="num">Words</th>
          <th class="num">Turns</th>
          <th class="num">Talk time</th>
          <th class="num">Pace</th>
          <th class="num">Questions</th>
          <th class="num">Cut in</th>
          <th class="num">Longest</th>
          <th>First</th>
          <th>Last</th>
        </tr>
      </thead>
      <tbody>
        {#each roster as person (person.id)}
          <tr>
            <td>
              <span class="row">
                <span class="dot" style="background: {speakers.get(person.id).color}"></span>
                {person.name}
              </span>
            </td>
            <td>
              <div class="bar" title="{person.share_words}% of words">
                <span
                  style="width: {person.share_words}%; background: {speakers.get(person.id).color}"
                ></span>
              </div>
              <span class="muted mono">{person.share_words}%</span>
            </td>
            <td class="num">{person.words}</td>
            <td class="num">{person.turns}</td>
            <td class="num">{fmtDur(person.seconds)}</td>
            <td class="num">{person.wpm ?? '—'}<span class="muted"> wpm</span></td>
            <td class="num">{person.questions}</td>
            <td class="num">{person.interruptions}</td>
            <td class="num">{fmtDur(person.longest_turn)}</td>
            <td><Cue t={person.first_t} /></td>
            <td><Cue t={person.last_t} /></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if silent.length}
    <p class="muted">Present but never spoke: {silent.join(', ')}.</p>
  {/if}
</section>

{#if roster.length > 1}
  <section class="sec">
    <h2>Who answers whom</h2>
    <p class="muted">How often the row's speaker was followed straight away by the column's.</p>
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th></th>
            {#each roster as person (person.id)}<th>{person.name}</th>{/each}
          </tr>
        </thead>
        <tbody>
          {#each roster as from (from.id)}
            <tr>
              <td>{from.name}</td>
              {#each roster as to (to.id)}
                {@const count = matrix[from.id]?.[to.id] ?? 0}
                <td class="num" style="background: {shade(count)}">{count || ''}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}

{#if extract.dynamics?.length}
  <section class="sec">
    <h2>Room dynamics</h2>
    <ul>
      {#each extract.dynamics as note (note)}<li>{note}</li>{/each}
    </ul>
  </section>
{/if}

<style>
  .bar {
    display: inline-block;
    width: 8rem;
    height: 0.5rem;
    background: var(--raised);
    border: 1px solid var(--grid);
    border-radius: 999px;
    overflow: hidden;
    vertical-align: middle;
    margin-right: 0.375rem;
  }
  .bar span { display: block; height: 100%; }
</style>
