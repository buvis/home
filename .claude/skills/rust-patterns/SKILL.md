---
name: rust-patterns
description: Use when writing, reviewing, or refactoring Rust code. Covers ownership, error handling, traits, concurrency, and project structure. Triggers on Rust file edits, "idiomatic rust", "rust best practices".
---

# Rust Patterns

Idiomatic Rust patterns and best practices. Read relevant references based on the task.

## References

- `references/ownership.md` - Borrowing, references, Cow for flexible ownership
- `references/error-handling.md` - Result/?, thiserror (libs) vs anyhow (apps), Option combinators
- `references/enums-matching.md` - State modeling with enums, exhaustive matching
- `references/traits-generics.md` - Generics, trait objects, newtype, builder pattern
- `references/iterators-concurrency.md` - Iterator chains, Arc<Mutex>, channels, async Tokio
- `references/unsafe-modules.md` - Unsafe rules, module layout, visibility, tooling

## Quick Reference

| Idiom | Description |
|-------|-------------|
| Borrow, don't clone | Pass `&T` instead of cloning unless ownership needed |
| Make illegal states unrepresentable | Use enums to model valid states only |
| `?` over `unwrap()` | Propagate errors, never panic in production |
| Parse, don't validate | Convert unstructured data to typed structs at boundary |
| Newtype for type safety | Wrap primitives to prevent argument swaps |
| Prefer iterators over loops | Declarative chains are clearer and often faster |
| `#[must_use]` on Results | Ensure callers handle return values |
| `Cow` for flexible ownership | Avoid allocations when borrowing suffices |
| Exhaustive matching | No wildcard `_` for business-critical enums |
| Minimal `pub` surface | Use `pub(crate)` for internal APIs |
