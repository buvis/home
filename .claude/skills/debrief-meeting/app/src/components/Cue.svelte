<script>
  import { getContext } from 'svelte'
  import { fmtTime } from '../lib/derive.js'

  let { t, label } = $props()
  const { jump } = getContext('meeting')
</script>

{#if t !== null && t !== undefined}
  <button class="cue" onclick={() => jump(t)} title="Show this moment in the transcript">
    {label ?? fmtTime(t)}
  </button>
{/if}
