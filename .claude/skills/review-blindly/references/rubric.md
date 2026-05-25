# Review-Blindly Rubric

This rubric provides binary pass/fail criteria for the spec-only hostile audit performed by the review-blindly skill. The reviewer has access only to the PRD and the implementation diff, with no additional context about how the implementation works internally. Each rule must be answered using only these two sources.

## Rules

### Spec Compliance

R1: The implementation satisfies all specified behaviors and outputs described in the PRD.

R2: All stated data formats and structures in the PRD are preserved in the implementation.

R3: Every API endpoint or interface specified in the PRD is implemented with the correct signature and behavior.

R4: All stated performance requirements and constraints from the PRD are met.

R5: The implementation matches all specified error handling behaviors and status codes.

### Scope Creep

R6: No new functionality or features beyond those explicitly specified in the PRD are present.

R7: No additional parameters, options, or flags are added beyond those in the PRD.

R8: No new external dependencies or libraries are introduced beyond those specified.

### Security

R9: All specified authentication mechanisms from the PRD are implemented and enforced.

R10: Required input validation and sanitization are present as specified in the PRD.

R11: Any specified rate-limiting or throttling controls are implemented as described.

### Data Safety

R12: No destructive operations (delete, update, etc.) are performed without proper safeguards.

R13: All data migrations include rollback or reversal mechanisms as specified.

R14: No unguarded database queries or file operations are present in the implementation.

### Acceptance Criteria

R15: All acceptance criteria for Phase 1 tasks are satisfied in the implementation.

R16: All acceptance criteria for Phase 2 tasks are satisfied in the implementation.

R17: All acceptance criteria for Phase 3 tasks are satisfied in the implementation.

### Out-of-Scope

R18: All items explicitly marked as out-of-scope in the PRD are absent from the implementation.

R19: No features or functionality mentioned in the PRD as out-of-scope are present in the diff.