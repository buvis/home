# Component Patterns

## Composition with Slots

```svelte
<!-- Card.svelte -->
<script lang="ts">
  import type { Snippet } from 'svelte'

  let { header, children, variant = 'default' }: {
    header?: Snippet
    children: Snippet
    variant?: 'default' | 'outlined'
  } = $props()
</script>

<div class="card card-{variant}">
  {#if header}
    <div class="card-header">
      {@render header()}
    </div>
  {/if}
  <div class="card-body">
    {@render children()}
  </div>
</div>

<!-- Usage -->
<Card variant="outlined">
  {#snippet header()}
    <h3>Title</h3>
  {/snippet}
  <p>Content goes here</p>
</Card>
```

## Compound Components with Context

```svelte
<!-- Tabs.svelte -->
<script lang="ts">
  import { setContext } from 'svelte'
  import type { Snippet } from 'svelte'

  let { children, defaultTab }: {
    children: Snippet
    defaultTab: string
  } = $props()

  let activeTab = $state(defaultTab)

  setContext('tabs', {
    get activeTab() { return activeTab },
    setActiveTab(tab: string) { activeTab = tab }
  })
</script>

<div class="tabs">
  {@render children()}
</div>

<!-- Tab.svelte -->
<script lang="ts">
  import { getContext } from 'svelte'
  import type { Snippet } from 'svelte'

  let { id, children }: { id: string, children: Snippet } = $props()
  const tabs = getContext<{ activeTab: string, setActiveTab: (t: string) => void }>('tabs')
</script>

<button
  class:active={tabs.activeTab === id}
  onclick={() => tabs.setActiveTab(id)}
>
  {@render children()}
</button>
```

## Renderless / Headless Pattern with Snippets

```svelte
<!-- DataLoader.svelte -->
<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'

  let { url, children }: {
    url: string
    children: Snippet<[{ data: T | null, loading: boolean, error: Error | null }]>
  } = $props()

  let data: T | null = $state(null)
  let loading = $state(true)
  let error: Error | null = $state(null)

  $effect(() => {
    loading = true
    error = null
    fetch(url)
      .then(r => r.json())
      .then(d => { data = d })
      .catch(e => { error = e })
      .finally(() => { loading = false })
  })
</script>

{@render children({ data, loading, error })}

<!-- Usage -->
<DataLoader url="/api/markets">
  {#snippet children({ data, loading, error })}
    {#if loading}<Spinner />{/if}
    {#if error}<ErrorDisplay {error} />{/if}
    {#if data}<MarketList markets={data} />{/if}
  {/snippet}
</DataLoader>
```
