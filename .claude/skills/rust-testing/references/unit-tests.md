# Unit Tests

## Module-Level Test Organization

```rust
// src/user.rs
pub struct User {
    pub name: String,
    pub email: String,
}

impl User {
    pub fn new(name: impl Into<String>, email: impl Into<String>) -> Result<Self, String> {
        let email = email.into();
        if !email.contains('@') {
            return Err(format!("invalid email: {email}"));
        }
        Ok(Self { name: name.into(), email })
    }

    pub fn display_name(&self) -> &str {
        &self.name
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creates_user_with_valid_email() {
        let user = User::new("Alice", "alice@example.com").unwrap();
        assert_eq!(user.display_name(), "Alice");
        assert_eq!(user.email, "alice@example.com");
    }

    #[test]
    fn rejects_invalid_email() {
        let result = User::new("Bob", "not-an-email");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("invalid email"));
    }
}
```

## Assertion Macros

```rust
assert_eq!(2 + 2, 4);                                    // Equality
assert_ne!(2 + 2, 5);                                    // Inequality
assert!(vec![1, 2, 3].contains(&2));                     // Boolean
assert_eq!(value, 42, "expected 42 but got {value}");    // Custom message
assert!((0.1_f64 + 0.2 - 0.3).abs() < f64::EPSILON);   // Float comparison
```

## Testing `Result` Returns

```rust
#[test]
fn parse_returns_error_for_invalid_input() {
    let result = parse_config("}{invalid");
    assert!(result.is_err());

    // Assert specific error variant
    let err = result.unwrap_err();
    assert!(matches!(err, ConfigError::ParseError(_)));
}

#[test]
fn parse_succeeds_for_valid_input() -> Result<(), Box<dyn std::error::Error>> {
    let config = parse_config(r#"{"port": 8080}"#)?;
    assert_eq!(config.port, 8080);
    Ok(()) // Test fails if any ? returns Err
}
```

## Testing Panics

```rust
#[test]
#[should_panic]
fn panics_on_empty_input() {
    process(&[]);
}

#[test]
#[should_panic(expected = "index out of bounds")]
fn panics_with_specific_message() {
    let v: Vec<i32> = vec![];
    let _ = v[0];
}
```
