# Task Examples

Good vs bad task descriptions.

## Example 1: Database Model

### Bad
```
Add user model
```
Why: No location, no fields, no constraints.

### Good
```
Create User model

Location: src/models/user.ts

Fields:
- id: UUID, primary key, auto-generated
- email: string, unique, not null
- passwordHash: string, not null
- createdAt: timestamp, default now()
- updatedAt: timestamp, auto-update

Verify: Model file exists, can import and instantiate User
```

## Example 2: API Endpoint

### Bad
```
Add login endpoint
```
Why: No path, no request/response format, no error cases.

### Good
```
Add POST /api/auth/login endpoint

Location: src/routes/auth.ts

Request body:
- email: string (required)
- password: string (required)

Response:
- 200: { token: string, user: { id, email } }
- 400: { error: "Invalid credentials" }
- 429: { error: "Too many attempts" } (after 5 failures)

Verify: Can login with valid credentials, get 400 on invalid
```

## Example 3: Refactoring

### Bad
```
Refactor auth module
```
Why: No specific changes, no boundaries, no success criteria.

### Good
```
Extract token generation from login handler

Location: src/routes/auth.ts → src/services/token.ts

Changes:
- Create TokenService class in new file
- Move generateToken() and verifyToken() functions
- Update imports in auth.ts
- Keep same function signatures

Verify: All auth tests still pass, no changes to API behavior
```

## Example 4: Bug Fix

### Bad
```
Fix login bug
```
Why: Which bug? What's the expected behavior?

### Good
```
Fix: Login returns 500 when email contains uppercase

Location: src/services/auth.ts:45

Problem: Email comparison is case-sensitive, user "John@example.com"
can register but can't login as "john@example.com"

Fix: Lowercase email before lookup in findUserByEmail()

Verify: Can login with any case variation of registered email
```

## Example 5: Separable vs Coupled Splits (Step 4.6 Eligibility Trigger)

Step 4.6's eligibility trigger splits a backend task touching `>=3` files toward `<=2`-file pieces — **only when cleanly separable**. The judgment is read off the PRD's Functional Decomposition and Dependency Graph, with a hard floor that each resulting piece must independently compile and carry its own passing tests. The two examples below show one task that splits and one that must stay whole.

### Separable — splits into `<=2`-file pieces

Task as originally planned:

```
Add cache metrics + LRU eviction + invalidation hooks to the cache layer

Location: src/cache/metrics.rs (new), src/cache/lru.rs, src/cache/invalidation.rs, src/cache/mod.rs

Files touched: 4 (backend, sonnet tier)
```

Functional Decomposition signals (from the PRD):
- **Capability A: Cache observability** — owns `metrics.rs`. Distinct feature; no other capability lists `metrics.rs`.
- **Capability B: Cache eviction policy** — owns `lru.rs`. Distinct feature.
- **Capability C: Cache invalidation hooks** — owns `invalidation.rs` and an additive entry in `mod.rs`.

Dependency Graph signals: A, B, C all listed as **independent leaves** (no `depends on:` arrows between them). Each capability's tests live alongside its own file.

Verdict — **separable**. Step 4.6 splits into:

- Subtask 1 (`<=2` files): `metrics.rs` + the `mod.rs` re-export it needs — Capability A.
- Subtask 2 (1 file): `lru.rs` — Capability B.
- Subtask 3 (1 file): `invalidation.rs` — Capability C.

Each subtask compiles standalone, ships its own tests, and routes to qwen. The original task is replaced by the three subtasks.

### Coupled — stays whole, routes to Claude

Task as originally planned:

```
Add Storage trait + FileStorage + S3Storage implementations

Location: src/storage/mod.rs (Storage trait, new), src/storage/file.rs, src/storage/s3.rs

Files touched: 3 (backend, sonnet tier)
```

Task text contains no step-4.7 Rule 1 opus signals (see Rule 1 for the canonical list), so step 4.6's opus-signal exemption does **not** fire and the eligibility trigger actually evaluates clean separability — the path this example illustrates.

Functional Decomposition signal (from the PRD): a **single capability** ("Storage abstraction") owns all three files. There is no second capability to split along.

Dependency Graph signal: `file.rs` and `s3.rs` both list `mod.rs` as a `depends on:` source — they implement the `Storage` trait the new `mod.rs` defines. The trait cannot be split from its implementations: shipping `file.rs`'s `impl Storage` without `mod.rs`'s `trait Storage` leaves the build red between commits (no such trait to implement).

Verdict — **not cleanly separable**. Step 4.6 keeps the task whole and step 6 reports it under irreducible-coupling. The task routes to Claude at its tier (sonnet), not qwen.

## Task Size Guidelines

| Scope | Task count |
|-------|------------|
| Single function change | 1 task |
| New file with 2-3 functions | 1 task |
| New feature touching 3+ files | 2-4 tasks |
| Cross-cutting concern | 1 task per layer |
