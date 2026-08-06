# debrief-meeting, Kiro port

Same tool as the Claude Code skill one directory up. The scripts and the built
SPA template are byte-identical copies; only the instruction file changes, from
a `SKILL.md` to a Kiro steering file.

## Install (work machine)

Copy two things out of this folder:

```
steering/debrief-meeting.md   ->  ~/.kiro/steering/debrief-meeting.md
debrief-meeting/              ->  ~/.kiro/debrief-meeting/
```

Global (`~/.kiro/`) is the right home: meetings are not tied to a repo, so this
works in every workspace. For a single project instead, put the steering file in
`<repo>/.kiro/steering/` and the payload in `<repo>/.kiro/debrief-meeting/`, then
change the two `~/.kiro/...` paths inside the steering file to `.kiro/...`.

Keep `scripts/` and `assets/` siblings — `build.py` finds the template at
`../assets/template.html` relative to itself.

## Use

In Kiro chat, type `#debrief-meeting` (or pick it from the `/` menu) and give it
the transcript path:

```
#debrief-meeting /Users/me/Downloads/weekly-sync.vtt
```

Kiro runs `parse.py`, writes `extract.json` itself, runs `build.py`, and reports
the path to `debrief.html`. Open that file in a browser — it is fully
self-contained, no server needed.

`inclusion: manual` means it costs no context until you ask for it. To have Kiro
reach for it on its own instead, swap the front matter for:

```yaml
---
inclusion: auto
name: debrief-meeting
description: Use when turning a meeting transcript into an interactive HTML debrief.
---
```

## Changing the page itself

The `app/` Svelte sources are not part of this port. Edit them on the personal
machine, rebuild, and copy the new `assets/template.html` over. See the
"Rebuilding the SPA template" section of `../SKILL.md`.
