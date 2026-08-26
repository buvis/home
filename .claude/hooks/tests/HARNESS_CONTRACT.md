# Hooks test harness contract

What a test author may rely on when testing anything under `~/.claude/hooks/`.
Every entry below is the observable behavior of the live module, not a design
note. `test_harness_contract.py` binds the load-bearing ones to the code and
fails if a public name in `_common.py` has no entry here.

Format: one `###` heading per public name in `hooks/_common.py`.

## `_common.py`

### `read_input() -> dict[str, Any]`

Reads all of `sys.stdin` and parses it as JSON. Returns `{}` on empty or
whitespace-only input, on a JSON parse failure, and on valid JSON that is not
an object. Any other exception raised by `sys.stdin.read()` itself propagates -
it does not swallow read errors.

### `block(reason: str) -> NoReturn`

Prints `reason` to stderr, then raises `SystemExit(2)`. Never returns.

### `allow() -> NoReturn`

Raises `SystemExit(0)`. Never returns. Writes nothing.

### `log_path(name: str) -> Path`

Returns `~/.claude/hooks/<name>`. Pure path math - creates nothing, checks
nothing.

### `secret_path(name: str) -> Path`

Returns `~/.claude/secrets/<name>`. Pure path math - creates nothing, checks
nothing.

### `resolve_toplevel(path: str) -> str | None`

Returns the git toplevel containing `path`, or `None` when `path` is not in a
repo or `git` fails. `path` need not exist: the walk starts at the nearest
existing ancestor directory. Memoized per process, keyed by that ancestor
directory, so two hooks in one dispatcher process spawn `git` at most once
between them. **A test that changes what a path resolves to must clear
`_common._TOPLEVEL_CACHE`** - the cache outlives the test.

### `append_jsonl_row(path: Path, row: str) -> None`

Appends `row + "\n"` to `path`, creating the file if absent. If the file
already has content whose last byte is not a newline, a leading newline is
written first so the new row still lands on its own line. Opens in mode `"a"`
(O_APPEND) and writes once.

### `parse_transcript_entries(path: Path) -> list[dict[str, Any]]`

Parses a JSONL transcript into dict entries. Blank lines, malformed JSON lines
and non-dict JSON values are skipped, not raised. A missing or unreadable file
returns `[]` - but only `OSError` is caught, so a file that exists and is not
valid UTF-8 raises `UnicodeDecodeError`. Cached per `Path` for the life of the
process. **A test that
rewrites a transcript between assertions must clear
`_common._TRANSCRIPT_CACHE`** or use a fresh path.

### `HandlerTimeout` (class)

Raised by the dispatcher's SIGALRM handler. Subclasses **`BaseException`, not
`Exception`**, so neither a handler's own `except Exception` nor
`capture_main`'s isolation can swallow the wall-clock cap. No handler may catch
it; only the dispatcher's `_invoke` does.

### `capture_main(fn: Callable[[], Any], payload: dict) -> tuple[int, str, str]`

Runs `fn()` with `payload` fed in as stdin JSON and returns
`(exit_code, captured_stdout, captured_stderr)`.

- Installs `io.StringIO(json.dumps(payload))` as `sys.stdin`, fresh `StringIO`s
  as `sys.stdout` and `sys.stderr`, and truncates `sys.argv` to `[argv[0]]`.
- Restores all four in a `finally`, including on timeout.
- Exit code: `fn()` returning an `int` gives that int, anything else gives 0; a
  `SystemExit` gives its int code, 0 for `None`, 1 otherwise; any other
  `Exception` gives 0 with the traceback appended to the captured stderr
  (handler isolation). `HandlerTimeout` is **not** caught and propagates.
- A `bool` is not an int here: both branches guard on `not isinstance(..., bool)`,
  so `return True` gives 0 and `SystemExit(False)` gives 1.

**Trap for test authors**: `capture_main` installs its own `sys.stdin`, so a
test that patches `sys.stdin` and drives the handler through `run(payload)` /
`capture_main` is testing the harness's stdin, not its own - such a test cannot
fail against broken code. To control stdin, call the handler's `main()`
directly.

## `dispatch.py`

- Each handler is imported **fresh per invocation** via
  `importlib.util.spec_from_file_location`, and the dispatcher calls its
  `run(payload)` - not `main()` - under a per-handler SIGALRM wall-clock cap.
  `run(payload)` must return an `(int, str, str)` triple.
- A route that produces **no decision** - fails to import, has no `run()`,
  raises out of `run()`, or times out - exits 2 when `kind="enforcement"` and 0
  for an observer. So a timed-out or crashed enforcement hook **denies**; it
  does not silently allow.
- A malformed return is deliberately not a no-decision case: it exits 0.
- On a platform without `SIGALRM` (Windows), the cap is skipped; the handler
  still runs and its result still surfaces.
