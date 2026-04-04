# Rust Platform Notes

## macOS Code Signing

- After maturin builds a `.so`, macOS `syspolicyd` may block it silently - Python hangs on import, killed by SIGKILL with no error message.
- Fix: `codesign -f -s - path/to/_core.*.so` after build.
- When debugging "Python hangs on native extension import", check code signing first.
