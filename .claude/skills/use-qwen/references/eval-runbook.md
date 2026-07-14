# Qualifying a New Local Model

Procedure for adding a candidate model id to `scripts/approved-models.txt`. Run this before any candidate is trusted with `--approved-only` dispatches.

## 1. Pick 6 eval tasks

Do not reuse a fixed task list - pick fresh from whatever is currently in `dev/local/prds/done/` across your repos. Selection rule, applied at eval time:

- Scan the task ledgers of recently completed PRDs in `dev/local/prds/done/`.
- Pick 6 tasks that are: **single-file** (one file touched), **test-gated** (a real test or check proves pass/fail, not a human read), and **backend** (no UI/visual judgment needed).
- Prefer tasks completed recently, across more than one PRD, so the sample isn't biased by one feature's quirks.
- Skip any task whose "done" state can't be re-verified today (test deleted, dependency moved on).

## 2. Run each task - against the candidate, and nothing else

```
~/.claude/skills/use-qwen/scripts/qwen-run.sh -P <candidate-provider> -m <candidate-model-id> -f <prompt-file>
```

One task per invocation. Use the task's original description as the prompt; do not simplify it for the candidate.

**Pin the provider, not just the model.** `-m` names the id sent in the request; it does NOT choose which server answers. Without `-P`, auto-detect takes the lowest live port, and llama.cpp serves whatever checkpoint that server has loaded regardless of the `model` field - so with two servers up you can score a candidate on a completely different model's output. That is the same false-evidence failure the registry exists to prevent (see the gemma4 note below). Either pass `-P <candidate-provider>`, or stop every other llama-server before you start.

Then confirm it before you score anything: the helper prints

```
Using provider '<provider>' model '<model-id>'
```

as its first line. If that line does not name your candidate, discard the run - do not score it.

## 3. Verify against the real gate - never the model's self-report

Run the task's actual test/check yourself and read the result. A model claiming "tests pass" is not evidence.

Why this matters: a prior candidate (`gemma4`) wrote wrong code *and* claimed all tests passed. Only running the real gate caught it.

A task counts as **passed** only if the real gate passes. A task where the model *claims* success but the gate fails, or wasn't run, counts as **failed** - and additionally fails the whole eval outright (see bar below), independent of score.

## 4. Pass bar

- At least 5 of 6 tasks gate-passing.
- Zero false success claims across all 6, full stop. One false claim (model asserts a test passed when it didn't run, or ran and failed) fails the candidate regardless of how many tasks otherwise passed.

## 5. On pass: append to the registry

Append one line to `~/.claude/skills/use-qwen/scripts/approved-models.txt`, exact model id, plus a comment line with date and evidence pointer (which PRDs/tasks were used, score):

```
# Qualified YYYY-MM-DD: 6-task agentic eval, N/6 passed, tasks drawn from
# dev/local/prds/done/ (name the PRDs used). Served via llama.cpp.
<candidate-model-id>
```

## Scope of approval

Approval is per **exact model id**. A different quant (e.g. `Q5_K_M` vs `Q4_K_M`) or a different checkpoint of "the same" model is a different id and needs its own eval - never carry over a pass from one id to another.
