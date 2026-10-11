# Working Documents

Durable work-management artifacts are tracked under
`docs/dev/project-management/`: PRDs, plans, reviews, decisions, discovery,
audits, and automation state. Never gitignore this tree.

Temporary assets belong under `docs/dev/tmp/`. This is the only development
artifact tree that should be globally gitignored. Do not put decisions,
requirements, reviews, or other remotely useful records there.

PRDs live only in
`docs/dev/project-management/prds/{backlog,wip,hold,done}/`. Named project
keepers live in `docs/dev/project-management/meta/`; executed plans are
removed from `docs/dev/project-management/plans/` after completion.

The aegis redirect hook and `enforce_prd_location.py` enforce these paths.
