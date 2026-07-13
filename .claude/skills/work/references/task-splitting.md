# Task Splitting

Read this when the Handle-result table (`SKILL.md` step 4) routes a task to
**Timeout** or **Context exceeded**, or when a task proves too complex to finish
in one dispatch.

**Note:** With 1M context, context-exceeded failures are rare. Split primarily for timeout or task complexity, not context limits.

When a tool can't complete a task (timeout/complexity), split it:

1. Analyze what was accomplished
2. Create 2-4 smaller tasks covering remaining work
3. Use `TaskCreate` for each subtask
4. Set dependencies with `TaskUpdate.addBlockedBy` if sequential
5. Mark original task as blocked or completed (if partially done)

## Split criteria

| Original scope | Split into |
|----------------|------------|
| Multiple files | One task per file |
| Multiple features | One task per feature |
| Large refactor | Extract → transform → cleanup |
| Full-stack feature | Backend task (qwen or Claude per the routing table) → Frontend task (Gemini) |

## Parallel dispatch for independent rework fixes

If `superpowers:dispatching-parallel-agents` is in the available skills list and the current batch contains 2+ tasks that:
- Touch completely different files (no overlap)
- Have no `blockedBy` dependencies on each other
- Are all tagged `[C{n}]` or `[D{n}]` (rework tasks, not original plan tasks)

Then dispatch them in parallel using the dispatching-parallel-agents pattern, **with at most 2 agents in flight at once**. Parallel agents share one working tree — one `cargo` target dir and one build lock — so their compiles serialize on that lock, but each `cargo` invocation still spawns a full `rustc` fleet. Bounding that fleet is what keeps RAM safe: rely on the global `~/.cargo/config.toml` `[build] jobs` cap and **never raise `CARGO_BUILD_JOBS`, pass `--jobs`, or run a full-workspace `cargo build` / `cargo test --workspace` / `clippy` inside a parallel agent** (per-task verify in step 5.5 is single-crate; the full suite runs once in step 7). An uncapped fan-out once locked the whole machine (`design-rationale.md` § parallel rework cap).

**Never parallelize original plan tasks** - the one-at-a-time rule remains for all non-rework tasks due to pidash sync requirements.
