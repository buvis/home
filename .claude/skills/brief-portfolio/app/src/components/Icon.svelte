<script>
  // Static micro-icon set (14x14, stroke 1.5, currentColor). Octicon-flavored
  // geometry; {@html} only ever receives these constants.
  const P = {
    commit: '<circle cx="7" cy="7" r="2.6"/><path d="M0.8 7 H4.4 M9.6 7 H13.2"/>',
    pr: '<circle cx="3.5" cy="3" r="1.8"/><circle cx="3.5" cy="11" r="1.8"/><path d="M3.5 4.8 V9.2"/><circle cx="10.5" cy="11" r="1.8"/><path d="M10.5 9.2 V6 C10.5 4.2 9.4 3.2 7.6 3.2 H6.6 M8 1.6 L6.4 3.2 L8 4.8"/>',
    issue: '<circle cx="7" cy="7" r="5.2"/><circle cx="7" cy="7" r="1.4" fill="currentColor" stroke="none"/>',
    ci: '<circle cx="7" cy="7" r="2.2"/><path d="M7 1.2 V3 M7 11 V12.8 M1.2 7 H3 M11 7 H12.8 M2.9 2.9 L4.2 4.2 M9.8 9.8 L11.1 11.1 M11.1 2.9 L9.8 4.2 M4.2 9.8 L2.9 11.1"/>',
    security: '<path d="M7 1.2 L12 3.2 V6.8 C12 10.2 10 12.2 7 13 C4 12.2 2 10.2 2 6.8 V3.2 Z"/>',
    prd: '<path d="M2 3 H12 M2 7 H12 M2 11 H8"/>',
    release: '<path d="M7.5 1.5 H12.5 V6.5 L6.5 12.5 L1.5 7.5 Z"/><circle cx="9.9" cy="4.1" r="1" fill="currentColor" stroke="none"/>',
    wip: '<path d="M2 12 L2.6 9.4 L9.8 2.2 A1.2 1.2 0 0 1 11.8 4.2 L4.6 11.4 Z"/>',
    branch: '<circle cx="3.5" cy="3" r="1.8"/><circle cx="3.5" cy="11" r="1.8"/><circle cx="10.5" cy="4.5" r="1.8"/><path d="M3.5 4.8 V9.2 M10.5 6.3 C10.5 8.4 8.2 8.9 5.4 9.3"/>',
    stash: '<path d="M1.5 9 H4.5 L5.7 10.7 H8.3 L9.5 9 H12.5 M1.5 9 L2.4 3.6 H11.6 L12.5 9 M1.5 9 V12 H12.5 V9"/>',
    judgment: '<path d="M7 1.5 L8.4 5.6 L12.5 7 L8.4 8.4 L7 12.5 L5.6 8.4 L1.5 7 L5.6 5.6 Z" fill="currentColor" stroke="none"/>',
    critical: '<circle cx="7" cy="7" r="5.4"/><path d="M4.9 4.9 L9.1 9.1 M9.1 4.9 L4.9 9.1"/>',
    serious: '<path d="M7 1.8 L13 12.2 H1 Z" fill="currentColor" stroke="none"/><path d="M7 5.4 V8.6" stroke="var(--surface)" stroke-width="1.6"/><circle cx="7" cy="10.4" r="0.9" fill="var(--surface)" stroke="none"/>',
    warning: '<path d="M7 1.8 L13 12.2 H1 Z"/><path d="M7 5.8 V8.4"/><circle cx="7" cy="10.3" r="0.8" fill="currentColor" stroke="none"/>',
    good: '<circle cx="7" cy="7" r="5.4"/><path d="M4.4 7.2 L6.3 9.1 L9.8 5.2"/>',
    quiet: '<circle cx="7" cy="7" r="1.6" fill="currentColor" stroke="none"/>',
    up: '<path d="M7 12 V2.5 M3.5 6 L7 2.5 L10.5 6"/>',
    down: '<path d="M7 2 V11.5 M3.5 8 L7 11.5 L10.5 8"/>',
  }

  let { name, size = 14 } = $props()
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 14 14"
  fill="none"
  stroke="currentColor"
  stroke-width="1.5"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {@html P[name] ?? P.quiet}
</svg>

<style>
  svg { vertical-align: -2px; }
</style>
