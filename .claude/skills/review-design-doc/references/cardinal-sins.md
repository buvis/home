# Cardinal sins (immediate blockers)


Flag any of these as blockers regardless of justification. They are non-negotiable because getting them wrong has asymmetric, usually irreversible cost:

- No rollback plan for stateful changes
- Secrets in config files, plaintext environment variables, or source code
- Single point of failure on a write path, without explicit acceptance and justification
- No identified human owner for production operation
- No observability for user-visible operations (no way to know if it is broken)
- "We will figure it out later" attached to a load-bearing concern (security, data integrity, observability, compliance)
- Unbounded resource consumption with no limits, quotas, or backpressure
- Schema changes without a migration plan
- Vendor lock-in for critical infrastructure without an exit strategy
- Authentication or authorization deferred to a later phase
- Data deletion, correction, or export with no defined path (compliance trap)
- Persistent data without a backup and tested restore procedure
- Public API contracts without a versioning strategy
- Hardcoded credentials, keys, or tokens anywhere in the doc or referenced code
- Critical decisions made by acclamation without recorded alternatives or rationale

