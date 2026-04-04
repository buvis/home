# Svelte Actions and Accessibility

## clickOutside Action

```ts
// lib/actions/clickOutside.ts
export function clickOutside(node: HTMLElement, callback: () => void) {
  function handleClick(event: MouseEvent) {
    if (!node.contains(event.target as Node)) {
      callback()
    }
  }

  document.addEventListener('click', handleClick, true)
  return {
    destroy() {
      document.removeEventListener('click', handleClick, true)
    }
  }
}
```

## trapFocus Action

```ts
// lib/actions/trapFocus.ts
export function trapFocus(node: HTMLElement) {
  const focusable = node.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  const first = focusable[0]
  const last = focusable[focusable.length - 1]

  function handleKeydown(e: KeyboardEvent) {
    if (e.key !== 'Tab') return
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  node.addEventListener('keydown', handleKeydown)
  first?.focus()

  return {
    destroy() {
      node.removeEventListener('keydown', handleKeydown)
    }
  }
}
```

## Usage

```svelte
<script lang="ts">
  import { clickOutside } from '$lib/actions/clickOutside'
  import { trapFocus } from '$lib/actions/trapFocus'

  let open = $state(false)
</script>

{#if open}
  <div use:clickOutside={() => open = false} use:trapFocus>
    <p>Dropdown content</p>
  </div>
{/if}
```

## Keyboard Navigation

```svelte
<script lang="ts">
  let { options, onselect }: {
    options: string[]
    onselect: (opt: string) => void
  } = $props()

  let isOpen = $state(false)
  let activeIndex = $state(0)

  function handleKeydown(e: KeyboardEvent) {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        activeIndex = Math.min(activeIndex + 1, options.length - 1)
        break
      case 'ArrowUp':
        e.preventDefault()
        activeIndex = Math.max(activeIndex - 1, 0)
        break
      case 'Enter':
        e.preventDefault()
        onselect(options[activeIndex])
        isOpen = false
        break
      case 'Escape':
        isOpen = false
        break
    }
  }
</script>

<div
  role="combobox"
  aria-expanded={isOpen}
  aria-haspopup="listbox"
  onkeydown={handleKeydown}
>
  <!-- Dropdown implementation -->
</div>
```

## Focus Management

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte'

  let { open, onclose, children }: {
    open: boolean
    onclose: () => void
    children: Snippet
  } = $props()

  let modalEl: HTMLDivElement
  let previousFocus: HTMLElement | null = null

  $effect(() => {
    if (open) {
      previousFocus = document.activeElement as HTMLElement
      modalEl?.focus()
    } else {
      previousFocus?.focus()
    }
  })
</script>

{#if open}
  <div
    bind:this={modalEl}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    onkeydown={e => e.key === 'Escape' && onclose()}
  >
    {@render children()}
  </div>
{/if}
```
