<script>
  // Horizontal scroll strip with hidden scrollbar; edge fades + chevrons hint
  // at overflow and vanish when that direction is exhausted.
  let { children } = $props()
  let el = $state()
  let w = $state(0)
  let canL = $state(false)
  let canR = $state(false)

  function check() {
    if (!el) return
    canL = el.scrollLeft > 2
    canR = el.scrollLeft + el.clientWidth < el.scrollWidth - 2
  }
  $effect(() => {
    w // re-check whenever the wrapper resizes
    check()
  })
</script>

<div class="wrap" bind:clientWidth={w}>
  <div class="strip" bind:this={el} onscroll={check}>
    {@render children()}
  </div>
  {#if canL}<div class="fade l">‹</div>{/if}
  {#if canR}<div class="fade r">›</div>{/if}
</div>

<style>
  .wrap {
    position: relative;
    flex: 1;
    min-width: 0;
  }
  .strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .strip::-webkit-scrollbar { display: none; }
  .strip > :global(*) { flex: none; }
  .fade {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 36px;
    display: flex;
    align-items: center;
    pointer-events: none;
    color: var(--accent);
    font-size: 15px;
    font-weight: 650;
  }
  .fade.r {
    right: 0;
    justify-content: flex-end;
    background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--surface) 94%, transparent));
  }
  .fade.l {
    left: 0;
    justify-content: flex-start;
    background: linear-gradient(270deg, transparent, color-mix(in srgb, var(--surface) 94%, transparent));
  }
</style>
