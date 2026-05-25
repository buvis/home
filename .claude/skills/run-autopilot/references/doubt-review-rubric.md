# Doubt-Review Rubric

This rubric applies binary pass/fail rules to the output of Phase 8 doubt-review. For each residual finding, the reviewer must categorize it as FIX, VERIFY, or KNOWN. The rubric ensures consistent categorization and that no finding is silently dropped.

## Rules

### Full Categorization

R1: Every residual finding is placed in exactly one of FIX/VERIFY/KNOWN.

### FIX Validity

R2: All items in FIX bucket are genuinely fixable now (bounded scope, in-scope, actionable).

### VERIFY Validity

R3: All items in VERIFY bucket name the exact check needed to resolve them (not vague "look into X").

### KNOWN Validity

R4: All items in KNOWN bucket carry a written justification explaining why they are out-of-scope.

### Count Conservation

R5: Input finding count equals the sum of FIX + VERIFY + KNOWN counts.