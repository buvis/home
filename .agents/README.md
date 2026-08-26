# Shared agent skills: machine-local policy

The design, install steps, `braid` usage, `.braidignore` format, multi-source
overlay pattern, per-plugin treatment, and compatibility classes live in
`~/git/src/github.com/buvis/agent-skills/README.md` and are canonical. This file
carries only what is true of this machine.

## Sources composed here

One source today: `~/git/src/github.com/buvis/agent-skills`, recorded in
`~/.config/agent-skills/sources.d/personal`. Every entry in `~/.agents/skills`
is a symlink into it, and `~/.agents/bin/braid` is a symlink into its `bin/`.
Add a work-machine-only `sources.d/work` file when a private employer checkout
exists.

## Policy files

There is no machine-local `.braidignore` here, and adding one is usually the
wrong move. Exclusions are repository policy and belong in the source repo's
own `.braidignore`, which every machine then gets. The machine-local file this
directory used to carry held forty names: twenty-three that no longer existed
and seventeen the source repo already listed.

Add one only for a name this machine alone must skip - a work checkout's skill
that is wrong for this box, say. Anything broader belongs upstream.
