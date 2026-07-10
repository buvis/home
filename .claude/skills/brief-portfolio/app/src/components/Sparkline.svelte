<script>
  let { values = [], w = 130, h = 26 } = $props()
  const max = $derived(Math.max(...values, 1))
  const pts = $derived(
    values
      .map((v, i) => {
        const x = (i / Math.max(values.length - 1, 1)) * (w - 4) + 2
        const y = h - 3 - (v / max) * (h - 8)
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  )
</script>

<svg width={w} height={h} viewBox="0 0 {w} {h}" aria-hidden="true">
  <polyline
    points={pts}
    fill="none"
    stroke="var(--seq-4)"
    stroke-width="2"
    stroke-linejoin="round"
    stroke-linecap="round"
  />
</svg>
