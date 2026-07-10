<script>
  import { getContext } from 'svelte'
  import { slug, epicsFor, isDepBot, daysAgo, ago, ciFailing } from '../lib/derive.js'

  let { repo, epics, onclose } = $props()
  const scored = getContext('scored')
  const slots = getContext('slots')

  const url = $derived(`https://github.com/${slug(repo)}`)
  const grouped = $derived(epicsFor(repo, epics))
  const sc = $derived(scored.get(slug(repo)))
  const l = $derived(repo.local ?? {})
  let closeBtn = $state()

  $effect(() => {
    const prev = document.activeElement
    closeBtn?.focus()
    return () => prev?.focus?.()
  })
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<button class="backdrop" aria-label="Close" onclick={onclose}></button>
<div class="panel" role="dialog" aria-modal="true" aria-label={slug(repo)}>
  <header>
    <span class="dot" style="background: var(--cat{slots.get(repo.org)})"></span>
    <h2><a href={url} target="_blank" rel="noreferrer">{slug(repo)}</a></h2>
    {#if repo.visibility === 'private'}<span class="lbl">private</span>{/if}
    <button class="close" bind:this={closeBtn} onclick={onclose}>✕</button>
  </header>
  {#if repo.description}<p class="desc">{repo.description}</p>{/if}
  <p class="meta">
    {repo.language || 'no language'} · {repo.default_branch} · pushed {ago(repo.pushed_at)}
    {#if repo.last_tag}
      · last tag {repo.last_tag}{repo.unreleased_commits ? ` (+${repo.unreleased_commits} unreleased)` : ''}
    {:else}
      · never released
    {/if}
    {#if repo.stars}· ★ {repo.stars}{/if}
  </p>

  {#if l.dirty || l.ahead || l.behind || l.stashes || (l.branch && l.branch !== repo.default_branch)}
    <div class="localrow">
      {#if l.branch && l.branch !== repo.default_branch}<span class="lbl">on {l.branch}</span>{/if}
      {#if l.dirty}<span class="lbl sev-serious">{l.dirty} dirty</span>{/if}
      {#if l.ahead}<span class="lbl sev-serious">{l.ahead} unpushed</span>{/if}
      {#if l.behind}<span class="lbl sev-warning">{l.behind} behind</span>{/if}
      {#if l.stashes}<span class="lbl">{l.stashes} stashed</span>{/if}
    </div>
  {/if}

  {#if sc.reasons.length}
    <section>
      <h3>Attention · score {sc.score}</h3>
      <ul>
        {#each sc.reasons as x, i (i)}
          <li><span class="dot" style="background: var(--{x.sev})"></span> {x.text}</li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if repo.errors?.length}
    <section>
      <h3 class="sev-warning">Collection warnings</h3>
      <ul>{#each repo.errors as e, i (i)}<li class="mono">{e}</li>{/each}</ul>
    </section>
  {/if}

  <section>
    <h3>What happened · {(repo.commits ?? []).length} commits</h3>
    {#each grouped.epics as e (e.title)}
      <details open={grouped.epics.length <= 3}>
        <summary>
          <b>{e.title}</b> · {e.commits.length} commits
          {#if e.summary}<span class="esum">{e.summary}</span>{/if}
        </summary>
        <ul class="commits">
          {#each e.commits as c (c.sha)}
            <li>
              <a class="mono" href="{url}/commit/{c.sha}" target="_blank" rel="noreferrer">{c.sha}</a>
              <span class="cdate">{c.date}</span>
              {c.subject}
            </li>
          {/each}
        </ul>
      </details>
    {/each}
    {#if grouped.rest.length}
      <details open={grouped.epics.length === 0}>
        <summary><b>{grouped.epics.length ? 'Other changes' : 'Commits'}</b> · {grouped.rest.length}</summary>
        <ul class="commits">
          {#each grouped.rest as c (c.sha)}
            <li>
              <a class="mono" href="{url}/commit/{c.sha}" target="_blank" rel="noreferrer">{c.sha}</a>
              <span class="cdate">{c.date}</span>
              {c.subject}
            </li>
          {/each}
        </ul>
      </details>
    {:else if !grouped.epics.length}
      <p class="meta">No commits in window.</p>
    {/if}
  </section>

  {#if repo.ci?.length}
    <section>
      <h3>CI</h3>
      <ul>
        {#each repo.ci as w (w.workflow)}
          <li>
            <span class={ciFailing({ ci: [w] }).length ? 'sev-critical' : w.conclusion === 'success' ? 'sev-good' : ''}>
              {w.status !== 'completed' ? '◌' : w.conclusion === 'success' ? '✓' : '✗'}
            </span>
            <a href={w.url} target="_blank" rel="noreferrer">{w.workflow}</a>
            <span class="cdate">{w.conclusion ?? w.status} · {w.date}</span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if repo.prs?.length}
    <section>
      <h3>Open PRs · {repo.prs.length}</h3>
      <ul>
        {#each repo.prs as p (p.number)}
          <li>
            <a href="{url}/pull/{p.number}" target="_blank" rel="noreferrer">#{p.number} {p.title}</a>
            <span class="cdate">{p.author} · {daysAgo(p.created)}d</span>
            {#if p.draft}<span class="lbl">draft</span>{/if}
            {#if isDepBot(p)}<span class="lbl">deps</span>{/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if repo.issues?.length}
    <section>
      <h3>Open issues · {repo.issues.length}</h3>
      <ul>
        {#each repo.issues as i (i.number)}
          <li>
            <a href="{url}/issues/{i.number}" target="_blank" rel="noreferrer">#{i.number} {i.title}</a>
            <span class="cdate">{daysAgo(i.created)}d</span>
            {#each i.labels as lb (lb)}<span class="lbl">{lb}</span>{/each}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if repo.releases?.length}
    <section>
      <h3>Releases</h3>
      <ul>
        {#each repo.releases as x (x.tag)}
          <li>
            <a href="{url}/releases/tag/{x.tag}" target="_blank" rel="noreferrer">{x.name}</a>
            <span class="cdate">{x.date}</span>
            {#if x.prerelease}<span class="lbl">pre</span>{/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if repo.prds && (repo.prds.backlog.length || repo.prds.wip.length || repo.prds.done_count)}
    <section>
      <h3>PRDs</h3>
      {#if repo.prds.wip.length}
        <p class="meta">wip:</p>
        <ul>{#each repo.prds.wip as t (t)}<li class="sev-serious">{t}</li>{/each}</ul>
      {/if}
      {#if repo.prds.backlog.length}
        <p class="meta">backlog:</p>
        <ul>{#each repo.prds.backlog as t (t)}<li>{t}</li>{/each}</ul>
      {/if}
      <p class="meta">{repo.prds.done_count} done</p>
    </section>
  {/if}
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    border: none;
    cursor: default;
    z-index: 40;
  }
  .panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(680px, 94vw);
    background: var(--plane);
    border-left: 1px solid var(--grid);
    z-index: 50;
    overflow-y: auto;
    padding: 18px 22px 40px;
  }
  header { display: flex; align-items: center; gap: 10px; }
  h2 { margin: 0; font-size: 17px; }
  .close {
    margin-left: auto;
    background: none;
    border: 1px solid var(--grid);
    border-radius: 6px;
    padding: 4px 9px;
    cursor: pointer;
  }
  .desc { color: var(--ink-2); margin: 8px 0 0; }
  .meta { color: var(--muted); font-size: 12.5px; margin: 6px 0; }
  .localrow { display: flex; gap: 6px; margin: 8px 0; flex-wrap: wrap; }
  section { margin-top: 18px; }
  h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin: 0 0 6px;
  }
  ul { list-style: none; margin: 0; padding: 0; }
  li { padding: 3px 0; }
  .commits li { padding: 2px 0; font-size: 13px; }
  .cdate { color: var(--muted); font-size: 11.5px; margin: 0 6px; }
  .esum { color: var(--ink-2); font-weight: 400; margin-left: 8px; }
  details { margin-bottom: 8px; }
  summary { cursor: pointer; }
</style>
