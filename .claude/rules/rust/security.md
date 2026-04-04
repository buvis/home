---
paths:
  - "**/*.rs"
---
# Rust Security

## Secrets Management

```rust
// BAD
const API_KEY: &str = "sk-abc123...";

// GOOD
fn load_api_key() -> anyhow::Result<String> {
    std::env::var("PAYMENT_API_KEY")
        .context("PAYMENT_API_KEY must be set")
}
```

## SQL Injection Prevention

Always use parameterized queries:

```rust
// BAD
let query = format!("SELECT * FROM users WHERE name = '{name}'");

// GOOD
sqlx::query("SELECT * FROM users WHERE name = $1")
    .bind(&name)
    .fetch_one(&pool)
    .await?;
```

## Input Validation

Parse, don't validate - convert unstructured data to typed structs at the boundary:

```rust
pub struct Email(String);

impl Email {
    pub fn parse(input: &str) -> Result<Self, ValidationError> {
        let trimmed = input.trim();
        let at_pos = trimmed.find('@')
            .filter(|&p| p > 0 && p < trimmed.len() - 1)
            .ok_or_else(|| ValidationError::InvalidEmail(input.to_string()))?;
        let domain = &trimmed[at_pos + 1..];
        if trimmed.len() > 254 || !domain.contains('.') {
            return Err(ValidationError::InvalidEmail(input.to_string()));
        }
        Ok(Self(trimmed.to_string()))
    }
}
```

## Unsafe Code

- Minimize `unsafe` blocks - prefer safe abstractions
- Every `unsafe` block must have a `// SAFETY:` comment
- Never use `unsafe` to bypass the borrow checker for convenience
- Audit all `unsafe` code during review

## Dependency Security

```bash
cargo audit                # Scan for known CVEs
cargo deny check           # License and advisory compliance
cargo tree -d              # Show duplicate dependencies
```

## Error Messages

Never expose internal paths, stack traces, or database errors in API responses. Log detailed errors server-side; return generic messages to clients.
