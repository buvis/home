# Unsafe Code and Module System

## When Unsafe Is Acceptable

```rust
// Acceptable: FFI boundary with documented invariants (Rust 2024+)
/// # Safety
/// `ptr` must be a valid, aligned pointer to an initialized `Widget`.
unsafe fn widget_from_raw<'a>(ptr: *const Widget) -> &'a Widget {
    // SAFETY: caller guarantees ptr is valid and aligned
    unsafe { &*ptr }
}

// Acceptable: Performance-critical path with proof of correctness
// SAFETY: index is always < len due to the loop bound
unsafe { slice.get_unchecked(index) }
```

## When Unsafe Is NOT Acceptable

```rust
// Bad: Using unsafe to bypass borrow checker
// Bad: Using unsafe for convenience
// Bad: Using unsafe without a Safety comment
// Bad: Transmuting between unrelated types
```

## Organize by Domain, Not by Type

```text
my_app/
├── src/
│   ├── main.rs
│   ├── lib.rs
│   ├── auth/          # Domain module
│   │   ├── mod.rs
│   │   ├── token.rs
│   │   └── middleware.rs
│   ├── orders/        # Domain module
│   │   ├── mod.rs
│   │   ├── model.rs
│   │   └── service.rs
│   └── db/            # Infrastructure
│       ├── mod.rs
│       └── pool.rs
├── tests/             # Integration tests
├── benches/           # Benchmarks
└── Cargo.toml
```

## Visibility — Expose Minimally

```rust
// Good: pub(crate) for internal sharing
pub(crate) fn validate_input(input: &str) -> bool {
    !input.is_empty()
}

// Good: Re-export public API from lib.rs
pub mod auth;
pub use auth::AuthMiddleware;

// Bad: Making everything pub
pub fn internal_helper() {} // Should be pub(crate) or private
```

## Essential Commands

```bash
# Build and check
cargo build
cargo check              # Fast type checking without codegen
cargo clippy             # Lints and suggestions
cargo fmt                # Format code

# Testing
cargo test
cargo test -- --nocapture    # Show println output
cargo test --lib             # Unit tests only
cargo test --test integration # Integration tests only

# Dependencies
cargo audit              # Security audit
cargo tree               # Dependency tree
cargo update             # Update dependencies

# Performance
cargo bench              # Run benchmarks
```
