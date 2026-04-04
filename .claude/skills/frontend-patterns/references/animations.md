# Animation Patterns

## Built-In Transitions

```svelte
<script lang="ts">
  import { fade, fly, slide, scale } from 'svelte/transition'
  import { flip } from 'svelte/animate'

  let { markets }: { markets: Market[] } = $props()
</script>

{#each markets as market (market.id)}
  <div
    in:fly={{ y: 20, duration: 300 }}
    out:fade={{ duration: 200 }}
    animate:flip={{ duration: 300 }}
  >
    <MarketCard {market} />
  </div>
{/each}
```

## Custom Transitions

```ts
// lib/transitions.ts
import type { TransitionConfig } from 'svelte/transition'

export function scaleIn(node: Element, {
  delay = 0,
  duration = 300,
  easing = t => t
} = {}): TransitionConfig {
  const style = getComputedStyle(node)
  const opacity = +style.opacity

  return {
    delay,
    duration,
    easing,
    css: (t) => `
      opacity: ${t * opacity};
      transform: scale(${0.9 + 0.1 * t}) translateY(${(1 - t) * 20}px);
    `
  }
}
```

## Spring and Tweened Motion

```svelte
<script lang="ts">
  import { spring, tweened } from 'svelte/motion'
  import { cubicOut } from 'svelte/easing'

  let coords = spring({ x: 0, y: 0 }, { stiffness: 0.1, damping: 0.25 })
  let progress = tweened(0, { duration: 400, easing: cubicOut })

  function handlePointerMove(e: PointerEvent) {
    coords.set({ x: e.clientX, y: e.clientY })
  }
</script>

<svelte:window onpointermove={handlePointerMove} />

<div
  class="cursor-follower"
  style="transform: translate({$coords.x}px, {$coords.y}px)"
/>

<progress value={$progress} />
<button onclick={() => progress.set(1)}>Complete</button>
```

## Modal with Transitions

```svelte
<!-- Modal.svelte -->
<script lang="ts">
  import { fade, scale } from 'svelte/transition'
  import type { Snippet } from 'svelte'

  let { open, onclose, children }: {
    open: boolean
    onclose: () => void
    children: Snippet
  } = $props()
</script>

{#if open}
  <div
    class="modal-overlay"
    transition:fade={{ duration: 200 }}
    onclick={onclose}
    onkeydown={e => e.key === 'Escape' && onclose()}
  />
  <div
    class="modal-content"
    role="dialog"
    aria-modal="true"
    transition:scale={{ start: 0.9, duration: 300 }}
  >
    {@render children()}
  </div>
{/if}
```
