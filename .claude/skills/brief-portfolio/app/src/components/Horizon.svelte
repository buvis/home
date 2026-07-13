<script>
  import { getContext } from 'svelte'
  import { forceSimulation, forceCollide, forceRadial, forceManyBody } from 'd3-force'
  import { slug, worstSev } from '../lib/derive.js'

  let { repos, onselect } = $props()
  const scored = getContext('scored')
  const slots = getContext('slots')
  const tip = getContext('tip')

  let w = $state(0)
  let h = $state(0)
  let drawn = $state([])

  const CAP = 150 // attention score that lands a node dead-center
  const R = $derived(Math.min(w, h) / 2 - 52)
  const gateR = $derived(R + 18)
  const gateDash = $derived.by(() => {
    const seg = (2 * Math.PI * gateR) / 39
    return `${seg * 0.8} ${seg * 0.2}`
  })
  // one chevron locks per burning repo — "chevron one, encoded"
  const fires = $derived(
    repos.filter((r) => scored.get(slug(r)).reasons.some((x) => x.sev === 'critical')).length
  )

  $effect(() => {
    if (!w || !h || !repos.length) return
    const cx = w / 2
    const cy = h / 2
    const ns = repos.map((r, i) => {
      const sc = scored.get(slug(r))
      const sev = sc.reasons.length ? worstSev(sc.reasons) : 'quiet'
      const radius = Math.min(30, 7 + 3 * Math.sqrt(r.commits?.length ?? 0))
      const orbit = R * (0.06 + 0.9 * (1 - Math.min(sc.score, CAP) / CAP))
      const a = (i / repos.length) * 2 * Math.PI
      const moons = Math.min(
        5,
        (r.local?.stashes ?? 0) +
          (r.branches?.worktrees?.length ?? 0) +
          ((r.branches?.stray?.length ?? 0) > 0 ? 1 : 0)
      )
      // everyone starts on the outer rim; the fires travel the distance
      return { r, sc, sev, radius, orbit, moons, x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) }
    })
    const sim = forceSimulation(ns)
      .force('collide', forceCollide((d) => d.radius + 7))
      .force('radial', forceRadial((d) => d.orbit, cx, cy).strength(0.9))
      .force('charge', forceManyBody().strength(-12))
      .alphaDecay(0.08)
    // no fly-in: settle the physics off-screen, render the final constellation
    sim.tick(200)
    sim.stop()
    drawn = ns.map((n) => ({ ...n }))
    return () => sim.stop()
  })

  const hint = (n) =>
    `${slug(n.r)} · score ${n.sc.score}\n${n.sc.reasons.map((x) => x.text).join('\n') || 'quiet'}`
</script>

<div class="wrap" bind:clientWidth={w} bind:clientHeight={h}>
  <svg width={w} height={h} role="img" aria-label="Portfolio gravity field: distance from center is urgency">
    <defs>
      <radialGradient id="core">
        <stop offset="0%" stop-color="var(--lcars-d)" stop-opacity="0.2" />
        <stop offset="70%" stop-color="var(--lcars-d)" stop-opacity="0.07" />
        <stop offset="100%" stop-color="var(--lcars-d)" stop-opacity="0" />
      </radialGradient>
    </defs>
    {#if R > 60}
      {#each [0.36, 0.68] as f (f)}
        <circle class="ring" cx={w / 2} cy={h / 2} r={R * f} />
      {/each}
      <circle class="core" cx={w / 2} cy={h / 2} r={R * 0.3} />
      <g>
        <circle class="gate" cx={w / 2} cy={h / 2} r={gateR} stroke-dasharray={gateDash} />
        {#each Array(9) as _, i (i)}
          <g transform="rotate({-90 + i * 40}, {w / 2}, {h / 2})">
            <path
              class="chev"
              class:lit={i < fires}
              transform="translate({w / 2}, {h / 2 - gateR})"
              d="M -8 -5 L 8 -5 L 0 9 Z"
            />
          </g>
        {/each}
      </g>
    {/if}
    {#each drawn as n (slug(n.r))}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <g
        class="node sev-{n.sev}"
        role="button"
        tabindex="0"
        aria-label={slug(n.r)}
        transform="translate({n.x}, {n.y})"
        onclick={() => onselect(n.r)}
        onkeydown={(e) => e.key === 'Enter' && onselect(n.r)}
        onmouseenter={(e) => tip.show(e, hint(n))}
        onmouseleave={tip.hide}
      >
        {#if n.sev === 'critical'}<circle class="halo" r={n.radius + 9} />{/if}
        {#if n.sev !== 'quiet'}
          <circle class="sevring" r={n.radius + 3.5} style="stroke: var(--{n.sev})" />
        {/if}
        <circle
          class="body"
          r={n.radius}
          style="fill: color-mix(in srgb, var(--cat{slots.get(n.r.org)}) {n.sev === 'quiet' ? 45 : 85}%, var(--plane))"
        />
        {#each Array(n.moons) as _, mi (mi)}
          <circle
            class="moon"
            cx={(n.radius + 7) * Math.cos(mi * 2.1 - 0.8)}
            cy={(n.radius + 7) * Math.sin(mi * 2.1 - 0.8)}
            r="2.2"
          />
        {/each}
        {#if n.sc.score > 0 || n.radius >= 16}
          <text y={n.radius + 14}>{n.r.name}</text>
        {/if}
      </g>
    {/each}
  </svg>
</div>

<style>
  .wrap { position: absolute; inset: 0; overflow: hidden; }
  .ring {
    fill: none;
    stroke: color-mix(in srgb, var(--axis) 55%, transparent);
    stroke-width: 2.5;
    stroke-dasharray: 64 26; /* LCARS arc sweeps, not dotted circles */
    stroke-linecap: round;
  }
  .core { fill: url(#core); pointer-events: none; }
  .gate {
    fill: none;
    stroke: color-mix(in srgb, var(--lcars-d) 35%, var(--plane));
    stroke-width: 10;
  }
  .chev { fill: color-mix(in srgb, var(--axis) 55%, var(--plane)); }
  .chev.lit { fill: var(--lcars-a); }
  .node { cursor: pointer; outline: none; }
  .node:hover .body,
  .node:focus-visible .body { stroke: var(--ink); stroke-width: 1.5; }
  .body { stroke: var(--border); stroke-width: 1; }
  .sevring {
    fill: none;
    stroke-width: 2.5;
  }
  .node .body {
    /* --glow-alpha is 0% in light theme (glow reads muddy), 45% in dark */
    filter: drop-shadow(0 0 12px color-mix(in srgb, currentColor var(--glow-alpha, 0%), transparent));
  }
  .sev-critical { color: var(--critical); }
  .sev-serious { color: var(--serious); }
  .sev-warning { color: var(--warning); }
  .halo {
    fill: var(--critical);
    opacity: 0.28;
  }
  .moon { fill: var(--muted); }
  text {
    font-size: 10.5px;
    fill: var(--ink-2);
    text-anchor: middle;
    pointer-events: none;
  }
</style>
