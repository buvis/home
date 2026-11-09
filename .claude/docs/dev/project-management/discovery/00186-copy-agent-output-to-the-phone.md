# Discovery: Copy Agent Output to the Phone

## Classification

Depth: seed | Date: 2026-11-09 | Status: open, not specified
Moved from herdr-plugins intake 00002 ("smart copying across Herdr desktop and
Moshi", recorded 2026-11-07 at the user's request). The desktop half of that
item is `~/.claude` PRD 00185 (Pluck as a herdr-app mod). This document keeps
the half PRD 00185 cannot cover: delivering a picked snippet to the phone.
herdr-plugins is a local-only archive since 2026-11-08 (the user left the
Herdr TUI), so this record lives here instead.

## Problem

When the user works from the phone through Moshi, copying a command or answer
from an agent terminal means selecting rendered terminal text on a small
screen. A desktop Pluck mod cannot help: herdr-app mods run only in the
desktop window, and a phone attached through `hc attach` never runs them. The
desktop clipboard (`write_to_clipboard`, `pbcopy`) never reaches the phone.

## Direction (from the intake, unchanged)

- A command that runs inside the terminal (not a mod) offers the same picker
  as PRD 00185 (commands, code blocks, URLs, paths, whole answers) from the
  agent's transcript, and writes the choice with OSC 52.
- Deliver only to the requesting client; never broadcast to every client
  attached to the same terminal.
- Distinguish a confirmed local copy from an OSC 52 request sent without
  acknowledgement. Cancellation and empty extraction leave the clipboard alone.
- Reuse PRD 00185's pure modules (`transcripts.js`, `extract.js`,
  `identity.js`) rather than a second implementation.

## Open verification

- Moshi documents OSC 52 over SSH and mosh (https://getmoshi.app/docs/clipboard).
  Whether OSC 52 survives the `hc attach` route, how payload limits apply
  (herdr-app accepts up to 1 MiB), and what lands in the phone's clipboard are
  unverified.
- Client isolation: which attached client receives an OSC 52 write from a
  terminal that two clients share.

## Depends on

`~/.claude` PRD 00185 (its pure modules and identity rules).
