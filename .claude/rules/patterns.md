# Common Patterns

## Repository Pattern

Encapsulate data access behind a consistent interface:
- Define standard operations: findAll, findById, create, update, delete
- Concrete implementations handle storage details
- Business logic depends on the abstract interface, not storage
- Enables easy swapping of data sources and simplifies testing

## API Response Envelope

Use a consistent envelope for all API responses:
- Success/status indicator
- Data payload (nullable on error)
- Error message field (nullable on success)
- Metadata for paginated responses (total, page, limit)
