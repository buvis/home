# Shared agent skills: machine-local policy

The design, install steps, `braid` usage, `.braidignore` format, multi-source
overlay pattern, per-plugin treatment, and compatibility classes live in
`~/git/src/github.com/buvis/agent-skills/README.md` and are canonical. This file
carries only what is true of this machine.

## Sources composed here

One source today: `~/git/src/github.com/buvis/agent-skills`, listed under
`sources` in `~/.config/buvis/buvis-braid.yaml`. Every entry in
`~/.agents/skills` is a symlink into it. `braid` itself ships in buvis-gems
(mise tool `pipx:buvis-gems`). On a work machine, list the private employer
checkout under `sources` in `~/.local/.config/buvis/buvis-braid.yaml`.

## Policy files

There is no machine-local `.braidignore` here, and adding one is usually the
wrong move. Exclusions are repository policy and belong in the source repo's
own `.braidignore`, which every machine then gets. The machine-local file this
directory used to carry held forty names: twenty-three that no longer existed
and seventeen the source repo already listed.

Add one only for a name this machine alone must skip - a work checkout's skill
that is wrong for this box, say. Anything broader belongs upstream.
