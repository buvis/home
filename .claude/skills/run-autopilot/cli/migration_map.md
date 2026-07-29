# Park/Stall Migration Map

Maps every behavior ID in `migration_manifest.txt` to where it lives in the
`references/*.md` prose today, what happens to it as the park/stall logic
moves into the `cli/` CLI, and the test that proves the disposition.

Disposition legend:

- `ported` — the CLI now performs this behavior; `test_id` names the test
  that proves it (forward reference — the CLI and its tests are not written
  yet).
- `retired` — deliberately dropped; `test_id` is the free-text reason.
- `stays_prose` — judgment/IO that remains English, guarded by an existing
  doc-contract test.
- `behavior_change` — the CLI deliberately behaves differently from today's
  prose; `test_id` names the test proving the new behavior.

| behavior_id | source | disposition | test_id |
|---|---|---|---|
| park-consume-marker | references/phase-build.md § Handle park request | ported | test_records_park.py::test_consumes_park_requested_marker |
| park-classify-decision | references/phase-build.md § Handle park request | ported | test_records_park.py::test_classifies_marker_via_park_decision |
| park-skip-malformed | references/phase-build.md § Handle park request | ported | test_records_park.py::test_skips_malformed_marker_and_falls_through |
| park-skip-stale | references/phase-build.md § Handle park request | ported | test_records_park.py::test_skips_stale_marker_without_incrementing_counter |
| park-execute-stall | references/phase-build.md § Handle park request | ported | test_records_park.py::test_parks_prd_via_stall_procedure |
| park-increment-parks-consecutive | references/phase-build.md § Handle park request | ported | test_records_park.py::test_increments_parks_consecutive_in_same_write |
| park-delete-marker-last | references/phase-build.md § Handle park request | ported | test_records_park.py::test_deletes_marker_only_after_park_succeeds |
| park-systemic-halt | references/phase-build.md § Handle park request | ported | test_records_park.py::test_halts_batch_at_two_consecutive_parks |
| stall-verified-move-to-hold | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_verified_move_wip_to_hold |
| stall-deferred-json-record | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_appends_stall_record_to_deferred_json |
| stall-per-prd-reset | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_stall_procedure_resets_per_prd_state |
| stall-print-banner | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_prints_stalled_banner |
| stall-continue-batch | references/recovery.md § Loop-mode stall procedure | ported | test_records_stall.py::test_continue_ends_turn_or_resumes_phase0 |
| systemic-park-reset-on-non-wrapper-died | references/recovery.md § Systemic-park breaker interaction | ported | test_records_stall.py::test_resets_parks_consecutive_for_non_wrapper_died_stall |
| reset-prd-fields-standard | references/phase-done.md § Phase 9 step 10 | ported | test_records.py::test_reset_clears_standard_fields |
| crash-recovery-no-double-move | references/recovery.md § Crash recovery: escalation_exhausted seen at Phase 0 | ported | test_records_stall.py::test_already_in_hold_counts_as_move_success |
| reset-repo-root-always | references/phase-done.md § Phase 9 step 10 | behavior_change | test_records.py::test_reset_clears_every_listed_field |
| reset-unlisted-fields-now-cleared | references/phase-build.md § Frontmatter parse table | behavior_change | test_records.py::test_reset_clears_every_listed_field |
| statectl-transaction-ordering | scripts/statectl.py § mutate | behavior_change | test_state.py::test_raising_fn_leaves_bak_unchanged |
| park-marker-wrapper-call-site | references/phase-build.md § Handle park request | retired | Interim call site only — PRD 00052 moves the call to `autopilot park` directly; do_park is written caller-agnostic so the call site can move without touching the logic |
| lifecycle-mkdir-p-block | references/phase-build.md § Ensure lifecycle directories exist | stays_prose | test_autopilot_lifecycle.py::test_phase0_ensures_lifecycle_dirs_with_mkdir_p |
| backlog-to-wip-verified-move | references/phase-build.md § Normal PRD selection | stays_prose | test_autopilot_lifecycle.py::test_backlog_to_wip_move_is_verified |
| wip-to-done-verified-move | references/phase-done.md § Phase 9 step 3 | stays_prose | test_autopilot_lifecycle.py::test_wip_to_done_move_is_verified |
| work-start-sha-recapture-guard | references/phase-build.md § Phase 3: Work | stays_prose | test_autopilot_lifecycle.py::test_phase3_guards_work_start_sha_against_recapture_on_resume |

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
