# Common Patterns

Scope: these patterns apply only when their precondition holds. Simple scripts,
CLIs, and single-backend apps are exempt; the Simplicity rules in
`rules/coding-style.md` govern them.

## Repository Pattern

Applies when a data layer has more than one real backend, or tests genuinely
need to swap storage. Then:

- Define standard operations: findAll, findById, create, update, delete
- Concrete implementations handle storage details
- Business logic depends on the abstract interface, not storage

One storage backend and no swap need: call it directly, no repository layer.

## API Response Envelope

Applies to public-facing HTTP APIs. Then use a consistent envelope:

- Success/status indicator
- Data payload (nullable on error)
- Error message field (nullable on success)
- Metadata for paginated responses (total, page, limit)

Internal tools and one-consumer endpoints may return the payload bare.
