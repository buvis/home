# Review-Blindly Rubric

This rubric provides binary pass/fail criteria for the spec-only hostile audit performed by the review-blindly skill. The reviewer's prompt contains ONLY the PRD — no diff, no file list, no implementation summary, no implementer self-review. The reviewer must independently locate and read the relevant code to evaluate each rule against the spec.

Rule ids use the `B` prefix (PRD 00108). The three review rubrics once shared a
single id namespace, which made a bare rule id ambiguous across consensus, blind
and doubt — a latent misroute now that rubric ids live inside agent files. The
consensus set keeps the `R` prefix, doubt took `D`, blind took `B`. Ids are
stable within a set: the prefix changed, no rule was renumbered.

## Rules

### Spec Compliance

B1: The implementation satisfies all specified behaviors and outputs described in the PRD.

B2: All stated data formats and structures in the PRD are preserved in the implementation.

B3: Every API endpoint or interface specified in the PRD is implemented with the correct signature and behavior.

B4: All stated performance requirements and constraints from the PRD are met.

B5: The implementation matches all specified error handling behaviors and status codes.

### Scope Creep

B6: No new functionality or features beyond those explicitly specified in the PRD are present.

B7: No additional parameters, options, or flags are added beyond those in the PRD.

B8: No new external dependencies or libraries are introduced beyond those specified.

### Security

B9: All specified authentication mechanisms from the PRD are implemented and enforced.

B10: Required input validation and sanitization are present as specified in the PRD.

B11: Any specified rate-limiting or throttling controls are implemented as described.

### Data Safety

B12: No destructive operations (delete, update, etc.) are performed without proper safeguards.

B13: All data migrations include rollback or reversal mechanisms as specified.

B14: No unguarded database queries or file operations are present in the implementation.

### Acceptance Criteria

B15: All acceptance criteria for Phase 1 tasks are satisfied in the implementation.

B16: All acceptance criteria for Phase 2 tasks are satisfied in the implementation.

B17: All acceptance criteria for Phase 3 tasks are satisfied in the implementation.

### Out-of-Scope

B18: All items explicitly marked as out-of-scope in the PRD are absent from the implementation.

B19: No features or functionality mentioned in the PRD as out-of-scope are present in the codebase the reviewer inspected.
