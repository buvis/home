# Working Documents

## dev/local/

- All self-created working documents go in `dev/local/` in repo root. Ensure `dev/local/` is in `.gitignore`.
- Always use the Write tool for `dev/local/` files, including when CWD is `~/.claude`. Never use Bash shell redirects (`cat >`, `echo >`) to write files.

## PRDs

- New PRDs start in `backlog/`. Only move to `wip/` when actively starting implementation.
- Never move PRDs from backlog to done without the user's explicit confirmation (skipping wip).
- Keep the `00XXX-` prefix on PRD filenames when moving between backlog/wip/done.
- Use `mv` (not `cp`) when moving PRDs between folders - no duplicates across backlog/wip/done.
