# Onboarding Walkthrough (worked example)

Concrete walkthrough of `SKILL.md`'s "Onboarding a New Model" pipeline, using
the real case it was built from: `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL`,
served on `llamacpp8001`.

## 1. Register

```
~/.claude/skills/use-qwen/scripts/qwen-run.sh --register-model -P llamacpp8001 --name "Qwen3.6 27B MTP (Llama, :8001)"
```

**Never derive the id or port from the GGUF filename or a naming
convention** - that's exactly why this flag exists instead of hand-editing
`~/.pi/agent/models.json`. Guessing both got it wrong once already:
`Qwen3.6-27B-UD-Q6_K_XL.gguf` looked like it should be
`unsloth/Qwen3.6-27B-GGUF:UD-Q6_K_XL` on port 8080 by analogy with sibling
entries; the live server actually reported `unsloth/Qwen3.6-27B-MTP` on port
8001. The `-hf`-shorthand pattern some entries share is coincidence, not a
rule - only the live probe (`/v1/models`) is ground truth.

**But ground truth can be poisoned at the server launch (2026-07-19
incident).** That `unsloth/Qwen3.6-27B-MTP` id above existed only because the
server was started with `--alias unsloth/Qwen3.6-27B-MTP`, which replaces the
served id. The model was later qualified under its real `-hf` id
(`...-GGUF:UD-Q6_K_XL`, via a different server), so the aliased server never
matched the quant-exact approved registry: `--approved-only` skipped it and
every autopilot dispatch silently fell through to the next port for days. The
rule: **never launch llama-server with `--alias`.** If `--register-model`
warns that the probed id has no `:<quant>` tag, fix the server launch and
re-register - do not register the alias and do not approve it.

## 2. Qualify

Manifest (`<prompt-file><TAB><verify-shell-command>` per line, 6 tasks):

```
/tmp/task1-prompt.txt	cd ~/git/src/github.com/acme/api && pytest tests/test_rate_limit.py -q
/tmp/task2-prompt.txt	cd ~/git/src/github.com/acme/api && cargo test --lib parse_config
...(4 more lines, one per task)
```

```
~/.claude/skills/use-qwen/scripts/run-eval.sh \
  -P llamacpp8001 -m unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL \
  --tasks /tmp/qwen-eval-tasks.tsv --commit
```

Illustrative output shape (the real 2026-07-14 eval of this id scored 6/6;
evidence file as named):

```
Evidence: /Users/bob/.claude/dev/local/audit-results/qwen-eval-unsloth-Qwen3.6-27B-MTP-GGUF-UD-Q6_K_XL-2026-07-14.md
Score: 6/6, verdict: PASS
Appended 'unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL' to /Users/bob/.claude/skills/use-qwen/scripts/approved-models.txt.
```

## 3. Promote

```
~/.claude/skills/use-qwen/scripts/promote-default.sh unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL
```

Illustrative output on success:

```
Promoted 'unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q6_K_XL' to default (was 'unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M'). Regression suite: PASS.
Changed: SKILL.md, ../work/references/qwen-integration.md, scripts/test_qwen_run.sh, scripts/default-model.txt
```
