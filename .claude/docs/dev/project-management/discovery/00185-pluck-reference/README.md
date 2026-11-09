# Pluck reference for PRD 00185

Behavior reference for porting Pluck to a herdr-app mod. Copied unchanged on
2026-11-09 from herdr-plugins commit 4362ef4 (`plugins/pluck/`), before that
local-only repository was retired. The full history is in the git bundle
`~/.local/share/archive/herdr-plugins.bundle` (`git clone` it to restore).

- `pluck_transcripts.py`: transcript readers and snippet extraction to port.
- `test_pluck_snippets.py`, `test_pluck_recovery.py`: the cases the port's
  `test.mjs` translates.

These files import modules that are not copied here (`pluck`, test helpers);
they document behavior and are not meant to run from this folder.
