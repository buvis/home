# Lifecycle Migration Map

Maps every behavior ID in `migration_manifest.txt` to where it lives in the
`references/*.md` prose today, what happens to it as the logic moves into the
`cli/` CLI, and the test that proves the disposition.

Two waves are recorded here: PRD 00051's park/stall recovery procedures, and
PRD 00089's lifecycle half — selection, frontmatter parse, phase transitions
and resume mapping — plus statectl's absorption into the validated writer.

Disposition legend:

- `ported` — the CLI now performs this behavior; `test_id` names the test
  that proves it (a real, landed test — `test_migration_map.py`'s parity
  suite resolves every `test_id` in this table against the actual test
  files).
- `retired` — deliberately dropped; `test_id` is the free-text reason.
- `stays_prose` — judgment/IO that remains English, guarded by an existing
  doc-contract test.
- `behavior_change` — the CLI deliberately behaves differently from today's
  prose; `test_id` names the test proving the new behavior.

| behavior_id | source | disposition | test_id |
|---|---|---|---|
| park-consume-marker | references/phase-build.md § Handle park request | ported | test_records_park.py::test_normal_park_moves_prd_records_stall_and_resets_state |
| park-classify-decision | references/phase-build.md § Handle park request | ported | test_autopilot_resume.py::ParkDecisionTests |
| park-skip-malformed | references/phase-build.md § Handle park request | ported | test_records_park.py::test_unparseable_json_marker_is_deleted_and_ignored |
| park-skip-stale | references/phase-build.md § Handle park request | ported | test_records_park.py::test_marker_prd_not_in_wip_and_no_stall_op_is_deleted_as_stale |
| park-execute-stall | references/phase-build.md § Handle park request | ported | test_records_park.py::test_normal_park_moves_prd_records_stall_and_resets_state |
| park-increment-parks-consecutive | references/phase-build.md § Handle park request | ported | test_records_park.py::test_normal_park_lands_the_increment_and_the_reset_in_the_same_commit |
| park-delete-marker-last | references/phase-build.md § Handle park request | ported | test_records_park.py::test_after_commit_before_marker_delete_leaves_marker_and_recovers_as_stale_on_retry |
| park-systemic-halt | references/phase-build.md § Handle park request | ported | test_records_park.py::test_second_consecutive_park_triggers_systemic_halt |
| stall-verified-move-to-hold | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_stall_creates_hold_dir_moves_prd_and_appends_one_deferred_record |
| stall-deferred-json-record | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_stall_creates_hold_dir_moves_prd_and_appends_one_deferred_record |
| stall-per-prd-reset | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_stall_creates_hold_dir_moves_prd_and_appends_one_deferred_record |
| stall-print-banner | references/recovery.md § Loop-mode stall procedure | stays_prose | test_autopilot_lifecycle.py::test_stall_banner_and_continue_stay_caller_prose |
| stall-continue-batch | references/recovery.md § Loop-mode stall procedure | stays_prose | test_autopilot_lifecycle.py::test_stall_banner_and_continue_stay_caller_prose |
| systemic-park-reset-on-non-wrapper-died | references/recovery.md § Systemic-park breaker interaction | ported | test_records_stall.py::test_resets_parks_consecutive_to_zero_for_non_wrapper_died_site |
| reset-prd-fields-standard | references/phase-done.md § Phase 9 step 10 | ported | test_records.py::test_removes_every_per_prd_reset_field |
| crash-recovery-no-double-move | references/recovery.md § Crash recovery: escalation_exhausted seen at Phase 0 | ported | test_records_stall.py::test_after_move_before_append_leaves_prd_in_hold_and_recovers_on_retry |
| stall-oversized-task-via-cli | references/recovery.md § plan-tasks stall: oversized task | ported | test_records_stall.py::test_exit_4_when_prd_absent_from_both_wip_and_hold, test_cli_default_paths.py::test_bare_stall_resolves_state_and_prds_by_walking_up_from_cwd |
| stall-escalation-exhausted-via-cli | references/recovery.md § Rework escalation exhausted → Stall move | ported | test_records_stall.py::test_exit_9_when_deferred_dir_path_is_occupied_by_a_file, test_cli_default_paths.py::test_bare_stall_from_nested_subdir_still_resolves_the_project_root_dirs |
| reset-repo-root-always | references/phase-done.md § Phase 9 step 10 | behavior_change | test_records.py::test_removes_every_per_prd_reset_field |
| reset-unlisted-fields-now-cleared | references/phase-build.md § Frontmatter parse (step 4) | behavior_change | test_records.py::test_clears_the_four_fields_that_leak_today |
| statectl-transaction-ordering | scripts/statectl.py § mutate | behavior_change | test_state.py::test_raising_fn_leaves_state_and_bak_byte_unchanged |
| park-marker-wrapper-call-site | references/phase-build.md § Handle park request | retired | Interim call site only — PRD 00052 moves the call to `autopilot park` directly; do_park is written caller-agnostic so the call site can move without touching the logic |
| lifecycle-mkdir-p-block | references/phase-build.md § Ensure lifecycle directories exist | stays_prose | test_autopilot_lifecycle.py::test_phase0_ensures_lifecycle_dirs_with_mkdir_p |
| backlog-to-wip-verified-move | references/phase-build.md § Normal PRD selection | stays_prose | test_autopilot_lifecycle.py::test_backlog_to_wip_move_is_verified |
| wip-to-done-verified-move | references/phase-done.md § Phase 9 step 3 | stays_prose | test_autopilot_lifecycle.py::test_wip_to_done_move_is_verified |
| work-start-sha-recapture-guard | references/phase-build.md § Phase 3: Work | stays_prose | test_autopilot_lifecycle.py::test_phase3_guards_work_start_sha_against_recapture_on_resume |
| prd-selection-lowest-sequence | references/phase-build.md § Normal PRD selection | ported | test_selection.py::SelectTests, test_lifecycle_cli.py::SelectTests::test_picks_lowest_sequence_in_wip |
| prd-selection-never-scans-hold | references/phase-build.md § Normal PRD selection | ported | test_selection.py::SelectTests::test_selection_cannot_reach_hold, test_lifecycle_cli.py::SelectTests::test_never_picks_from_hold |
| frontmatter-parse-defaults | references/phase-build.md § Frontmatter parse (step 4) | ported | test_frontmatter.py::RecognizedValueTests, test_frontmatter.py::InvalidValueTests |
| frontmatter-malformed-single-warning | references/phase-build.md § Frontmatter parse (step 4) | ported | test_frontmatter.py::MalformedBlockTests |
| phase-transition-effects-one-commit | SKILL.md § Session handoff procedure | ported | test_transitions.py::ReworkTests, test_lifecycle_cli.py::PhaseDoneTests::test_rework_increments_cycle_and_clears_ids_in_one_commit |
| phase-transition-convergence-marker | references/phase-review.md § Hand off to the finalize session | ported | test_transitions.py::ConvergedTests, test_lifecycle_cli.py::PhaseDoneTests::test_converged_lands_phase_and_marker_in_one_commit |
| phase-transition-drained-empty-next-phase | references/phase-done.md § Continuation | ported | test_transitions.py::DrainedTests, test_lifecycle_cli.py::PhaseDoneTests::test_drained_writes_the_empty_next_phase |
| resume-target-mapping | SKILL.md § State Management | ported | test_resume.py::GoldenFixtureTests, test_lifecycle_cli.py::ResumeTargetTests |
| statectl-absorbed-into-boundary | scripts/statectl.py | ported | test_shims.py::StatectlShimSymbolTests |
| statectl-rejects-malformed-own-field | scripts/statectl.py | behavior_change | test_shims.py::ShimValidationTests::test_malformed_value_for_the_targeted_field_is_rejected_loudly |
| statectl-tolerates-unrelated-odd-field | scripts/statectl.py | behavior_change | test_shims.py::ShimValidationTests::test_unrelated_pre_existing_odd_field_blocks_nothing |

## Notes

- `reset-prd-fields-standard` covers the field set common to all four
  per-PRD reset occurrences (the three in `references/recovery.md` —
  "plan-tasks stall: oversized task" step 5, "Crash recovery:
  escalation_exhausted seen at Phase 0", and "Rework escalation exhausted" →
  "Stall move" step 3 — plus `references/phase-done.md` step 10). The two
  `behavior_change` rows above record where the new single `reset_prd_fields`
  function now clears MORE than all four of those occurrences agree on today.
- `park-marker-wrapper-call-site` is retired as a call site, not as logic:
  `do_park` itself is ported (see the `park-*` rows above) and stays
  caller-agnostic so PRD 00052 can point a different caller at it later.
- Task-10 cutover (2026-07-31): every `ported`/`behavior_change` `test_id` was
  re-pointed from task 1's forward references to the REAL tests that landed
  (tasks 4-6); `stall-print-banner` and `stall-continue-batch` were
  re-classified `ported` → `stays_prose` — the CLI performs the stall's
  durable effects, but the STALLED banner and the continue-the-batch judgment
  deliberately remain caller prose in `recovery.md`'s exit-0 row, guarded by
  the new lifecycle doc-contract test the rows now name. No doc-contract test
  pinned the retired multi-step prose (proven: the lifecycle and phase2-stall
  suites stayed green through the rewrite), so zero test retirements were
  needed.
- PRD 00089 (2026-08-07) retired four prose derivations and zero tests. The
  doc-contract tests in `scripts/test_autopilot_lifecycle.py` all survive
  untouched, because what they guard is what deliberately STAYED prose: the
  `mkdir -p` block, the three verified moves, and the `work_start_sha`
  recapture guard. `autopilot select` decides which PRD is next; the verified
  backlog→wip move it implies remains the caller's, which is why
  `backlog-to-wip-verified-move` keeps its `stays_prose` row above.
- `scripts/test_golden_contracts.py` documents a limitation in its own header:
  the Phase-0 frontmatter fixture was a PRODUCER-side pin only, "no Python
  consumer parser exists (the Phase 0 parse is model-driven)". `cli/frontmatter.py`
  is that consumer now, and `test_frontmatter.py::GoldenFixtureTests` parses
  the same fixture with it. The golden suite itself is left byte-unchanged on
  purpose — it is the regression gate on the shims — so its header comment
  understates what the fixture is bound to. Read this note, not that comment.
- The `statectl-*` rows sit beside `statectl-transaction-ordering`, which PRD
  00051 recorded as a `behavior_change` in advance. 00089 is what made it
  true: the `.bak` is now written after validation rather than before.
- **`resume-target-mapping` is the weakest row here and the wording is
  deliberate.** The pure function predates 00089 (PRD 00047 C11 extracted it
  to `scripts/resume_target.py`); 00089 only moved it into the package and
  gave it a subcommand. What the subcommand does NOT do is replace the resume
  procedure: the abort handlers in `phase-build.md` and the phase→gate router
  in `SKILL.md` still carry the operational steps, because `resume_target()`
  returns a DESCRIPTION, not an action. It is wired in as a cross-check
  against those handlers, not as their replacement, and it answers only for
  the `build` and `review` gates (`phase: "done"` returns
  `unknown phase: done`, unchanged since 00047).
- **Two validation limits the boundary does NOT close, found in 00089's
  review pass and left deliberately.** (1) Validation is only as deep as
  `cli/schema.py`: `tasks` must be a list, but nothing checks the shape of its
  ELEMENTS, so `task-done` can append a non-object to `tasks[].attempts` even
  though `state-schema.md` documents it as `object[]`. Fields with no rule at
  all (`pause_reason`, `stall_reason`, `contract_card`) are unvalidated by the
  same design that tolerates unknown fields. Deepening the schema is its own
  change; it is not what "one validated writer" claims. (2) `validate_changed`
  keys on a CHANGED value, so re-writing a malformed field with the identical
  malformed value passes and the transaction still stamps `schema_version`.
  The write cannot make the field worse, and scoping to "fields the mutation
  targeted" would mean threading the json-path through `mutate()` for a case
  nobody has hit — so it stays as documented in `test_schema.py`'s
  `test_no_change_validates_nothing`.
