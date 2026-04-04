# Reactive State Patterns

## Basic Reactivity with Runes

```svelte
<script lang="ts">
  // Reactive state
  let count = $state(0)

  // Derived values (replaces computed/memo)
  let doubled = $derived(count * 2)
  let isEven = $derived(count % 2 === 0)

  // Side effects
  $effect(() => {
    console.log(`Count changed to ${count}`)
  })
</script>

<button onclick={() => count++}>
  {count} (doubled: {doubled})
</button>
```

## Shared State with Stores

```ts
// lib/stores/markets.ts
import { writable, derived } from 'svelte/store'
import type { Market } from '$lib/types'

export const markets = writable<Market[]>([])
export const selectedMarketId = writable<string | null>(null)

export const selectedMarket = derived(
  [markets, selectedMarketId],
  ([$markets, $id]) => $markets.find(m => m.id === $id) ?? null
)

export async function loadMarkets() {
  const res = await fetch('/api/markets')
  markets.set(await res.json())
}
```

## Class-Based Reactive State (Svelte 5)

```ts
// lib/stores/marketStore.svelte.ts
export class MarketStore {
  markets = $state<Market[]>([])
  selectedId = $state<string | null>(null)
  loading = $state(false)

  selected = $derived(
    this.markets.find(m => m.id === this.selectedId) ?? null
  )

  async load() {
    this.loading = true
    try {
      const res = await fetch('/api/markets')
      this.markets = await res.json()
    } finally {
      this.loading = false
    }
  }
}

// Provide via context in layout
import { setContext } from 'svelte'
const store = new MarketStore()
setContext('markets', store)
```

## Debounced Reactivity

```svelte
<script lang="ts">
  let searchQuery = $state('')
  let debouncedQuery = $state('')

  $effect(() => {
    const timeout = setTimeout(() => {
      debouncedQuery = searchQuery
    }, 500)
    return () => clearTimeout(timeout)
  })

  $effect(() => {
    if (debouncedQuery) {
      performSearch(debouncedQuery)
    }
  })
</script>

<input bind:value={searchQuery} placeholder="Search..." />
```
