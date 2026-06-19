# Stress tests (10 scenarios)


Before finalizing the review, mentally run the design through these scenarios. Any that the doc cannot answer becomes a finding:

1. **Traffic 10x overnight**: what breaks first, and what is the recovery cost?
2. **Critical dependency down for 4 hours**: what is the user-visible behavior, and what is the on-call playbook?
3. **Revert this in 3 months**: what is irreversible by then, and what data shape changes lock us in?
4. **The team that built it leaves**: can a new team operate it from this doc and the code alone?
5. **Security incident requires changing behavior today**: can we ship a fix in hours, not weeks?
6. **New engineer asks "where is the source of truth for X"**: is there one clear answer?
7. **Cost doubles unexpectedly**: what knob do we turn, and is the relationship between knob and cost legible?
8. **A regulator or auditor asks for evidence of a control**: is audit logging sufficient, tamper-evident, and queryable?
9. **A new feature requires a breaking schema change**: how does the system absorb it without downtime?
10. **A noisy neighbor consumes all resources**: is there isolation, throttling, or quota?

