# Coding Style

## Immutability

Prefer immutable data to prevent hidden side effects, simplify debugging, and enable safe concurrency.

- In GC languages (JS, Python, Java): create new objects, don't mutate existing ones.
- In Rust: trust the borrow checker. `&mut self`, `Mutex`, `RwLock`, and interior mutability are idiomatic when ownership rules are satisfied. Don't clone or rebuild data structures just to avoid `mut`.

## File Organization

Many small files over few large files:
- High cohesion, low coupling
- 200-400 lines typical, 800 max
- Functions under 50 lines
- No deep nesting (4 levels max)
- Organize by feature/domain, not by type

## Error Handling

- Handle errors explicitly at every level
- Provide user-friendly messages in UI-facing code
- Log detailed error context server-side
- Never silently swallow errors

## Input Validation

- Validate all user input before processing
- Use schema-based validation where available
- Fail fast with clear error messages
- Never trust external data (API responses, user input, file content)

## Naming

- Name commands, skills, functions, and anything that performs an action starting with an action verb (e.g. `review-deps-prs`, not `dep-updates`).

## Production-Ready Code

All code must be complete, working, and shippable.

- No stubs, placeholders, TODOs, `NotImplementedError`, `unimplemented!()`, or fake data. When requirements are unclear, ask.
- Write or update tests covering new behavior. Ensure they pass.
- Self-review all changes for incomplete markers before responding.

## Simplicity

- Avoid over-engineering. Make only changes directly requested or clearly necessary.
- Don't add features, refactor code, or make improvements beyond what was asked.
- Don't add error handling, fallbacks, or validation for scenarios that can't happen. Validate at system boundaries only.
- Don't create helpers, utilities, or abstractions for one-time operations. Don't design for hypothetical future requirements.

## Warnings

- NEVER silence warnings with `#[allow(...)]`, `// nolint`, `@SuppressWarnings`, `# type: ignore`, or equivalent. Fix root cause.
- When you discover pre-existing warnings, lint issues, or code smells, do not silently ignore them. Surface them and push for action.

