"""Tests for render_prompt.py — persona frontmatter stripping and {PLACEHOLDER} substitution CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("render_prompt.py")
_SPEC = importlib.util.spec_from_file_location("render_prompt", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
render_prompt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(render_prompt)


def _persona(tmp_path: Path, content: str, name: str = "persona.md") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Frontmatter stripping
# ---------------------------------------------------------------------------


def test_uses_persona_as_is_when_no_frontmatter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hello {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 0
    rendered = out_path.read_text(encoding="utf-8")
    assert rendered == "Hello World!"
    captured = capsys.readouterr()
    assert captured.out.rstrip("\n") == str(len(rendered.encode("utf-8")))


def test_strips_frontmatter_before_scanning_placeholders(tmp_path: Path) -> None:
    persona = _persona(
        tmp_path,
        "---\ntitle: Test Persona\nmode: strict\n---\nHello {NAME}, welcome.\n",
    )
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 0
    rendered = out_path.read_text(encoding="utf-8")
    assert "Hello World, welcome." in rendered
    assert "---" not in rendered
    assert "title" not in rendered
    assert "mode" not in rendered


def test_returns_exit_3_when_frontmatter_never_closes(tmp_path: Path) -> None:
    persona = _persona(
        tmp_path,
        "---\ntitle: Test Persona\nBody without a closing marker {NAME}\n",
    )
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 3
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Persona file errors
# ---------------------------------------------------------------------------


def test_returns_exit_2_when_persona_file_missing(tmp_path: Path) -> None:
    missing_persona = tmp_path / "does-not-exist.md"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(missing_persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 2
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# --set / --set-file / --set-cmd, each individually
# ---------------------------------------------------------------------------


def test_set_literal_value_is_substituted(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "GREETING=hello"],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Say hello!"


def test_set_file_uses_full_contents_including_trailing_newline(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "X:{VAL}:Y")
    value_path = tmp_path / "value.txt"
    value_path.write_text("file-value\n", encoding="utf-8")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-file", f"VAL={value_path}"],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "X:file-value\n:Y"


def test_rejects_missing_set_file_path_with_exit_4(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "X:{VAL}:Y")
    missing_value_path = tmp_path / "does-not-exist.txt"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set-file",
            f"VAL={missing_value_path}",
        ],
    )

    assert exit_code == 4
    captured = capsys.readouterr()
    assert (
        captured.err.rstrip("\n")
        == f"render_prompt: --set-file path not found for {{VAL}}: {missing_value_path}"
    )
    assert not out_path.exists()


def test_set_cmd_uses_trailing_newline_stripped_stdout(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-cmd", "GREETING=echo hello"],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Say hello!"


def test_rejects_nonzero_set_cmd_with_exit_4_ignoring_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"
    cmd = "echo partial; echo boom >&2; exit 7"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-cmd", f"GREETING={cmd}"],
    )

    assert exit_code == 4
    captured = capsys.readouterr()
    assert (
        captured.err.rstrip("\n")
        == f"render_prompt: --set-cmd failed for {{GREETING}}: {cmd} (exit 7): boom"
    )
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Placeholder validation
# ---------------------------------------------------------------------------


def test_returns_exit_1_naming_the_missing_placeholder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.rstrip("\n") == "render_prompt: missing placeholder: {NAME}"


def test_missing_placeholder_message_names_first_name_sorted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "{ZEBRA} and {APPLE}")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.rstrip("\n") == "render_prompt: missing placeholder: {APPLE}"


def test_no_output_file_written_when_placeholder_unfilled(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


def test_unused_set_key_is_not_an_error(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Only {USED} here")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "USED=foo",
            "--set",
            "UNUSED=bar",
        ],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Only foo here"


def test_lowercase_braces_are_not_treated_as_placeholders(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{notaplaceholder} then {REAL}")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "REAL=World"],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "{notaplaceholder} then World"


def test_duplicate_placeholder_occurrences_all_substituted(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{X} and {X} again")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "X=Yo"],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Yo and Yo again"


# ---------------------------------------------------------------------------
# Substitution semantics
# ---------------------------------------------------------------------------


def test_substituted_value_containing_brace_sequence_is_not_rescanned(
    tmp_path: Path,
) -> None:
    persona = _persona(tmp_path, "Start {A} End")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "A=value with {B} inside"],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Start value with {B} inside End"


# ---------------------------------------------------------------------------
# Precedence: last-write-wins across flag kinds
# ---------------------------------------------------------------------------


def test_last_write_wins_set_file_after_set(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{KEY}")
    value_path = tmp_path / "value.txt"
    value_path.write_text("FILEVAL", encoding="utf-8")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "KEY=SETVAL",
            "--set-file",
            f"KEY={value_path}",
        ],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "FILEVAL"


def test_last_write_wins_set_after_set_file(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{KEY}")
    value_path = tmp_path / "value.txt"
    value_path.write_text("FILEVAL", encoding="utf-8")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set-file",
            f"KEY={value_path}",
            "--set",
            "KEY=SETVAL",
        ],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "SETVAL"


def test_all_three_source_kinds_combine_in_one_render(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{A}-{B}-{C}")
    value_path = tmp_path / "value.txt"
    value_path.write_text("2", encoding="utf-8")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "A=1",
            "--set-file",
            f"B={value_path}",
            "--set-cmd",
            "C=echo 3",
        ],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "1-2-3"


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


def test_returns_exit_5_when_out_parent_dir_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "missing_dir" / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 5
    captured = capsys.readouterr()
    assert (
        captured.err.rstrip("\n")
        == f"render_prompt: output directory does not exist: {out_path.parent}"
    )
    assert not out_path.exists()


def test_stdout_prints_byte_count_not_character_count_for_multibyte_value(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Value: {V}")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "V=café"],
    )

    assert exit_code == 0
    rendered = out_path.read_text(encoding="utf-8")
    assert rendered == "Value: café"
    byte_count = len(rendered.encode("utf-8"))
    assert byte_count != len(rendered)  # sanity: fixture actually has a multibyte char
    captured = capsys.readouterr()
    assert captured.out.rstrip("\n") == str(byte_count)
    assert len(out_path.read_bytes()) == byte_count


# ---------------------------------------------------------------------------
# Regression: silent exit codes must name their cause on stderr
# ---------------------------------------------------------------------------


def test_exit_2_prints_stderr_line_naming_the_missing_persona_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_persona = tmp_path / "does-not-exist.md"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(missing_persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert str(missing_persona) in stderr_line
    assert not out_path.exists()


def test_exit_3_prints_stderr_line_naming_the_persona_path_when_frontmatter_unterminated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(
        tmp_path,
        "---\ntitle: Test Persona\nBody without a closing marker {NAME}\n",
    )
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME=World"],
    )

    assert exit_code == 3
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert str(persona) in stderr_line
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Regression: a --set*/--set-file/--set-cmd argument with no "=" is a usage error
# ---------------------------------------------------------------------------


def test_set_without_equals_sign_exits_6_and_names_the_offending_argument(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME"],
    )

    assert exit_code == 6
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert "NAME" in stderr_line
    assert not out_path.exists()


def test_set_file_without_equals_sign_exits_6_and_names_the_offending_argument(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "X:{VAL}:Y")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-file", "VAL"],
    )

    assert exit_code == 6
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert "VAL" in stderr_line
    assert not out_path.exists()


def test_set_cmd_without_equals_sign_exits_6_and_names_the_offending_argument(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-cmd", "GREETING"],
    )

    assert exit_code == 6
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert "GREETING" in stderr_line
    assert not out_path.exists()


def test_set_with_explicit_empty_value_after_equals_sign_still_renders_successfully(
    tmp_path: Path,
) -> None:
    persona = _persona(tmp_path, "Value:[{NAME}]")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "NAME="],
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Value:[]"


# ---------------------------------------------------------------------------
# Regression: a --set-cmd that succeeds with empty stdout is never silently substituted
# ---------------------------------------------------------------------------


def test_set_cmd_succeeding_with_empty_stdout_exits_4_and_names_the_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-cmd", "GREETING=true"],
    )

    assert exit_code == 4
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert "GREETING" in stderr_line
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Coverage gap: --set-cmd timeout branch (passes against current code)
# ---------------------------------------------------------------------------


def test_set_cmd_timeout_exits_4_and_names_the_key_without_the_real_wait(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(render_prompt, "SET_CMD_TIMEOUT_SECONDS", 0.05)
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-cmd", "GREETING=sleep 1"],
    )

    assert exit_code == 4
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert stderr_line != ""
    assert "\n" not in stderr_line
    assert "GREETING" in stderr_line
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Dispatch-target preflight: --require-file / --require-parent
# (a relative or dangling target path must block the render — Tess edited a
# suffix-matching vault copy after such a path failed to resolve, 2026-08-18)
# ---------------------------------------------------------------------------


def test_require_file_accepts_absolute_existing_file(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    target = tmp_path / "target.js"
    target.write_text("x", encoding="utf-8")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "NAME=World",
            "--require-file",
            str(target),
        ],
    )

    assert exit_code == 0
    assert out_path.exists()


def test_rejects_relative_require_file_path_with_exit_7(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "NAME=World",
            "--require-file",
            "debrief-meeting/app/smoke.test.js",
        ],
    )

    assert exit_code == 7
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert "not absolute" in stderr_line
    assert "debrief-meeting/app/smoke.test.js" in stderr_line
    assert not out_path.exists()


def test_rejects_missing_require_file_path_with_exit_7(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    missing_target = tmp_path / "does-not-exist.js"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "NAME=World",
            "--require-file",
            str(missing_target),
        ],
    )

    assert exit_code == 7
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert "does not exist" in stderr_line
    assert str(missing_target) in stderr_line
    assert not out_path.exists()


def test_require_parent_accepts_new_file_in_existing_directory(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    new_target = tmp_path / "new-file.js"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "NAME=World",
            "--require-parent",
            str(new_target),
        ],
    )

    assert exit_code == 0
    assert out_path.exists()


def test_rejects_require_parent_path_whose_directory_is_missing_with_exit_7(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    dangling_target = tmp_path / "no-such-dir" / "new-file.js"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "NAME=World",
            "--require-parent",
            str(dangling_target),
        ],
    )

    assert exit_code == 7
    captured = capsys.readouterr()
    stderr_line = captured.err.rstrip("\n")
    assert "parent directory" in stderr_line
    assert str(dangling_target) in stderr_line
    assert not out_path.exists()


def test_rejects_relative_require_parent_path_with_exit_7(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [
            str(persona),
            "--out",
            str(out_path),
            "--set",
            "NAME=World",
            "--require-parent",
            "app/smoke.test.js",
        ],
    )

    assert exit_code == 7
    captured = capsys.readouterr()
    assert "not absolute" in captured.err
    assert not out_path.exists()
