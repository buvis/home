<script>
  let { text, label = 'Copy' } = $props()
  let done = $state(false)

  function fallback(value) {
    // navigator.clipboard can be missing when the file is opened straight off disk
    const box = document.createElement('textarea')
    box.value = value
    box.style.position = 'fixed'
    box.style.opacity = '0'
    document.body.append(box)
    box.select()
    document.execCommand('copy')
    box.remove()
  }

  async function copy() {
    const value = typeof text === 'function' ? text() : text
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      fallback(value)
    }
    done = true
    setTimeout(() => (done = false), 1200)
  }
</script>

<button class="chip" onclick={copy}>{done ? 'Copied' : label}</button>
