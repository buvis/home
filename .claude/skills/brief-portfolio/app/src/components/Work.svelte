<script>
  import { getContext } from 'svelte'
  import { slug, isDepBot, ciFailing, daysAgo } from '../lib/derive.js'

  let { repos, onselect } = $props()
  const slots = getContext('slots')
  let showDeps = $state(false)
  let showDrafts = $state(true)

  const allPrs = $derived(repos.flatMap((r) => (r.prs ?? []).map((p) => ({ ...p, r }))))
  const depCount = $derived(allPrs.filter(isDepBot).length)
  const prs = $derived(
    allPrs
      .filter((p) => (showDeps || !isDepBot(p)) && (showDrafts || !p.draft))
      .toSorted((a, b) => (a.created ?? '').localeCompare(b.created ?? ''))
  )
  const issues = $derived(
    repos
      .flatMap((r) => (r.issues ?? []).map((i) => ({ ...i, r })))
      .toSorted((a, b) => (a.created ?? '').localeCompare(b.created ?? ''))
  )
  const ciRows = $derived(
    repos
      .filter((r) => r.ci?.length)
      .toSorted((a, b) => ciFailing(b).length - ciFailing(a).length)
  )
  const runClass = (w) =>
    w.status !== 'completed'
      ? 'sev-warning'
      : { success: 'sev-good', failure: 'sev-critical', timed_out: 'sev-critical', startup_failure: 'sev-critical' }[w.conclusion] ?? 'mut'
  const runMark = (w) =>
    w.status !== 'completed' ? '◌' : w.conclusion === 'success' ? '✓' : ciFailing({ ci: [w] }).length ? '✗' : '–'
  const age = (c) => `${daysAgo(c) ?? '?'}d`
</script>

<section class="sec">
  <h2>Open PRs · {prs.length}</h2>
  <div class="filters">
    <button class="chip" class:active={showDeps} onclick={() => (showDeps = !showDeps)}>
      deps-bot PRs ({depCount})
    </button>
    <button class="chip" class:active={showDrafts} onclick={() => (showDrafts = !showDrafts)}>
      drafts
    </button>
  </div>
  {#if prs.length === 0}
    <p class="empty">No open PRs{depCount && !showDeps ? ` (besides ${depCount} deps-bot)` : ''}.</p>
  {:else}
    <table>
      <thead><tr><th>age</th><th>repo</th><th>PR</th><th>author</th><th>review</th></tr></thead>
      <tbody>
        {#each prs as p (slug(p.r) + p.number)}
          <tr>
            <td class="num" class:sev-serious={daysAgo(p.created) > 14}>{age(p.created)}</td>
            <td>
              <button class="repobtn" onclick={() => onselect(p.r)}>
                <span class="dot" style="background: var(--cat{slots.get(p.r.org)})"></span>{p.r.name}
              </button>
            </td>
            <td>
              <a href="https://github.com/{slug(p.r)}/pull/{p.number}" target="_blank" rel="noreferrer">
                #{p.number} {p.title}
              </a>
              {#if p.draft}<span class="lbl">draft</span>{/if}
              {#if isDepBot(p)}<span class="lbl">deps</span>{/if}
            </td>
            <td>{p.author}</td>
            <td class:sev-good={p.review === 'APPROVED'} class:sev-serious={p.review === 'CHANGES_REQUESTED'}>
              {p.review.toLowerCase().replaceAll('_', ' ')}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<section class="sec">
  <h2>Open issues · {issues.length}</h2>
  {#if issues.length === 0}
    <p class="empty">No open issues.</p>
  {:else}
    <table>
      <thead><tr><th>age</th><th>repo</th><th>issue</th><th>labels</th><th>💬</th></tr></thead>
      <tbody>
        {#each issues as i (slug(i.r) + i.number)}
          <tr>
            <td class="num" class:sev-serious={daysAgo(i.created) > 90}>{age(i.created)}</td>
            <td>
              <button class="repobtn" onclick={() => onselect(i.r)}>
                <span class="dot" style="background: var(--cat{slots.get(i.r.org)})"></span>{i.r.name}
              </button>
            </td>
            <td>
              <a href="https://github.com/{slug(i.r)}/issues/{i.number}" target="_blank" rel="noreferrer">
                #{i.number} {i.title}
              </a>
            </td>
            <td>{#each i.labels as l (l)}<span class="lbl">{l}</span>{/each}</td>
            <td class="num">{i.comments || ''}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<section class="sec">
  <h2>CI wall · latest run per workflow on default branch</h2>
  {#each ciRows as r (slug(r))}
    <div class="cirow">
      <button class="repobtn" onclick={() => onselect(r)}>
        <span class="dot" style="background: var(--cat{slots.get(r.org)})"></span>{r.name}
      </button>
      <div class="runs">
        {#each r.ci as w (w.workflow)}
          <a class="run {runClass(w)}" href={w.url} target="_blank" rel="noreferrer">
            {runMark(w)} {w.workflow}
          </a>
        {/each}
      </div>
    </div>
  {/each}
</section>

<style>
  .filters { display: flex; gap: 8px; margin-bottom: 10px; }
  .cirow {
    display: flex;
    gap: 14px;
    align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid var(--grid);
  }
  .cirow .repobtn { min-width: 170px; }
  .runs { display: flex; gap: 8px; flex-wrap: wrap; }
  .run {
    font-size: 12px;
    border: 1px solid var(--grid);
    border-radius: 999px;
    padding: 2px 9px;
  }
  .run:hover { border-color: var(--axis); text-decoration: none; }
  .mut { color: var(--muted); }
  .empty { color: var(--muted); }
</style>
