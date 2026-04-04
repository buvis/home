# Performance Optimization

## Fine-Grained Reactivity (Built In)

Svelte 5's rune-based reactivity is fine-grained by default. No memoization wrappers needed.

```svelte
<script lang="ts">
  let { markets }: { markets: Market[] } = $props()

  // Automatically efficient - only recalculates when markets changes
  let sortedMarkets = $derived(
    [...markets].sort((a, b) => b.volume - a.volume)
  )

  // Expensive computation - use $derived.by for complex logic
  let analytics = $derived.by(() => {
    const total = markets.reduce((sum, m) => sum + m.volume, 0)
    const avg = total / markets.length
    return { total, avg, count: markets.length }
  })
</script>
```

## Code Splitting and Lazy Loading

```svelte
<script lang="ts">
  let HeavyChart: typeof import('$lib/components/HeavyChart.svelte').default | null = $state(null)

  $effect(() => {
    import('$lib/components/HeavyChart.svelte').then(m => {
      HeavyChart = m.default
    })
  })
</script>

{#if HeavyChart}
  <svelte:component this={HeavyChart} data={chartData} />
{:else}
  <ChartSkeleton />
{/if}
```

## Virtualization for Long Lists

```svelte
<script lang="ts">
  import { createVirtualizer } from '@tanstack/svelte-virtual'

  let { markets }: { markets: Market[] } = $props()
  let parentEl: HTMLDivElement

  const virtualizer = createVirtualizer({
    get count() { return markets.length },
    getScrollElement: () => parentEl,
    estimateSize: () => 100,
    overscan: 5
  })
</script>

<div bind:this={parentEl} style="height: 600px; overflow: auto;">
  <div style="height: {$virtualizer.getTotalSize()}px; position: relative;">
    {#each $virtualizer.getVirtualItems() as row (row.index)}
      <div
        style="position: absolute; top: 0; left: 0; width: 100%;
               height: {row.size}px; transform: translateY({row.start}px);"
      >
        <MarketCard market={markets[row.index]} />
      </div>
    {/each}
  </div>
</div>
```

## Error Boundary Pattern

```svelte
<svelte:boundary onerror={(error, reset) => {
  console.error('Caught:', error)
}}>
  <App />

  {#snippet failed(error, reset)}
    <div class="error-fallback">
      <h2>Something went wrong</h2>
      <p>{error.message}</p>
      <button onclick={reset}>Try again</button>
    </div>
  {/snippet}
</svelte:boundary>
```
