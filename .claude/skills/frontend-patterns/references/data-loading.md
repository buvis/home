# Data Loading and Forms

## Server Load Functions

```ts
// routes/markets/+page.server.ts
import type { PageServerLoad } from './$types'

export const load: PageServerLoad = async ({ fetch }) => {
  const markets = await fetch('/api/markets').then(r => r.json())
  return { markets }
}
```

```svelte
<!-- routes/markets/+page.svelte -->
<script lang="ts">
  let { data } = $props()
</script>

{#each data.markets as market}
  <MarketCard {market} />
{/each}
```

## Streaming with Promises

```ts
// routes/dashboard/+page.server.ts
export const load: PageServerLoad = async ({ fetch }) => {
  return {
    summary: fetch('/api/summary').then(r => r.json()),
    // Streamed - doesn't block initial render
    activity: fetch('/api/activity').then(r => r.json())
  }
}
```

```svelte
{#await data.activity}
  <Skeleton />
{:then activity}
  <ActivityFeed items={activity} />
{:catch error}
  <ErrorDisplay {error} />
{/await}
```

## Native SvelteKit Form Actions

```svelte
<!-- routes/markets/create/+page.svelte -->
<script lang="ts">
  import { enhance } from '$app/forms'

  let { form } = $props()
</script>

<form method="POST" use:enhance>
  <input name="name" value={form?.name ?? ''} required />
  {#if form?.errors?.name}
    <span class="error">{form.errors.name}</span>
  {/if}

  <textarea name="description" required>{form?.description ?? ''}</textarea>

  <input type="date" name="endDate" required />

  <button type="submit">Create Market</button>
</form>
```

```ts
// routes/markets/create/+page.server.ts
import type { Actions } from './$types'
import { fail } from '@sveltejs/kit'

export const actions = {
  default: async ({ request }) => {
    const data = await request.formData()
    const name = data.get('name') as string

    if (!name?.trim()) {
      return fail(400, { name, errors: { name: 'Name is required' } })
    }

    if (name.length > 200) {
      return fail(400, { name, errors: { name: 'Name must be under 200 characters' } })
    }

    await createMarket({ name, description: data.get('description') as string })
    return { success: true }
  }
} satisfies Actions
```

## Reactive Form with Bind

```svelte
<script lang="ts">
  let name = $state('')
  let description = $state('')
  let errors: Record<string, string> = $state({})

  function validate(): boolean {
    const newErrors: Record<string, string> = {}
    if (!name.trim()) newErrors.name = 'Name is required'
    if (name.length > 200) newErrors.name = 'Must be under 200 characters'
    if (!description.trim()) newErrors.description = 'Description is required'
    errors = newErrors
    return Object.keys(newErrors).length === 0
  }

  async function handleSubmit() {
    if (!validate()) return
    await createMarket({ name, description })
  }
</script>

<form onsubmit|preventDefault={handleSubmit}>
  <input bind:value={name} placeholder="Market name" />
  {#if errors.name}<span class="error">{errors.name}</span>{/if}

  <textarea bind:value={description} />
  {#if errors.description}<span class="error">{errors.description}</span>{/if}

  <button type="submit">Create Market</button>
</form>
```
