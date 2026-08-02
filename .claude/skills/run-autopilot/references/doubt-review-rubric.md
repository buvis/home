# Doubt-Review Rubric

This rubric applies binary pass/fail rules to the output of Phase 8 doubt-review. For each residual finding, the reviewer must categorize it as FIX, VERIFY, or KNOWN. The rubric ensures consistent categorization and that no finding is silently dropped.

Rule ids use the `D` prefix (PRD 00108). The three review rubrics once shared a
single id namespace, which made a bare rule id ambiguous across consensus, blind
and doubt — a latent misroute now that rubric ids live inside agent files. The
consensus set keeps the `R` prefix, blind took `B`, doubt took `D`. Ids are
stable within a set: the prefix changed, no rule was renumbered.

## Rules

### Full Categorization

D1: Every residual finding is placed in exactly one of FIX/VERIFY/KNOWN.

### FIX Validity

D2: All items in FIX bucket are genuinely fixable now (bounded scope, in-scope, actionable).

### VERIFY Validity

D3: All items in VERIFY bucket name the exact check needed to resolve them (not vague "look into X").

### KNOWN Validity

D4: All items in KNOWN bucket carry a written justification explaining why they are out-of-scope.

### Count Conservation

D5: Input finding count equals the sum of FIX + VERIFY + KNOWN counts.
