---
name: frontend-patterns
description: Use when building Svelte 5 / SvelteKit components. Covers runes, reactivity, data loading, forms, animations, and accessibility. Triggers on .svelte file edits, "svelte", "sveltekit", "runes".
---

# Frontend Patterns

Svelte 5 and SvelteKit patterns. Read relevant references based on the task.

## References

- `references/components.md` - Slots, snippets, compound components, headless/renderless
- `references/reactivity.md` - $state, $derived, $effect, stores, class-based state
- `references/data-loading.md` - Server load functions, streaming, SvelteKit form actions
- `references/performance.md` - Fine-grained reactivity, code splitting, virtualization, error boundaries
- `references/animations.md` - Transitions, spring/tweened motion, custom transitions
- `references/actions-a11y.md` - Svelte actions (clickOutside, trapFocus), keyboard nav, focus management

## Key Svelte 5 Patterns

```svelte
<!-- Reactive state -->
let count = $state(0)
let doubled = $derived(count * 2)

<!-- Side effects with cleanup -->
$effect(() => {
  const id = setInterval(tick, 1000)
  return () => clearInterval(id)
})

<!-- Props -->
let { items, variant = 'default' }: Props = $props()

<!-- Snippets (replaces slots) -->
{#snippet header()}...{/snippet}
{@render header()}
```

Svelte's compiler-driven reactivity eliminates most manual optimization. Use stores/context when state crosses component boundaries; keep local state with runes.
