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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = _persona(tmp_path, "Hello {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "NAME=World"])

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

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "NAME=World"])

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

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "NAME=World"])

    assert exit_code == 3
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Persona file errors
# ---------------------------------------------------------------------------


def test_returns_exit_2_when_persona_file_missing(tmp_path: Path) -> None:
    missing_persona = tmp_path / "does-not-exist.md"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(missing_persona), "--out", str(out_path), "--set", "NAME=World"]
    )

    assert exit_code == 2
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# --set / --set-file / --set-cmd, each individually
# ---------------------------------------------------------------------------


def test_set_literal_value_is_substituted(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "GREETING=hello"])

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Say hello!"


def test_set_file_uses_full_contents_including_trailing_newline(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "X:{VAL}:Y")
    value_path = tmp_path / "value.txt"
    value_path.write_text("file-value\n", encoding="utf-8")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-file", f"VAL={value_path}"]
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "X:file-value\n:Y"


def test_rejects_missing_set_file_path_with_exit_4(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = _persona(tmp_path, "X:{VAL}:Y")
    missing_value_path = tmp_path / "does-not-exist.txt"
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-file", f"VAL={missing_value_path}"]
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
        [str(persona), "--out", str(out_path), "--set-cmd", "GREETING=echo hello"]
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Say hello!"


def test_rejects_nonzero_set_cmd_with_exit_4_ignoring_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = _persona(tmp_path, "Say {GREETING}!")
    out_path = tmp_path / "out.txt"
    cmd = "echo partial; echo boom >&2; exit 7"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set-cmd", f"GREETING={cmd}"]
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.rstrip("\n") == "render_prompt: missing placeholder: {NAME}"


def test_missing_placeholder_message_names_first_name_sorted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
        [str(persona), "--out", str(out_path), "--set", "USED=foo", "--set", "UNUSED=bar"]
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Only foo here"


def test_lowercase_braces_are_not_treated_as_placeholders(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{notaplaceholder} then {REAL}")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "REAL=World"])

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "{notaplaceholder} then World"


def test_duplicate_placeholder_occurrences_all_substituted(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "{X} and {X} again")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "X=Yo"])

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "Yo and Yo again"


# ---------------------------------------------------------------------------
# Substitution semantics
# ---------------------------------------------------------------------------


def test_substituted_value_containing_brace_sequence_is_not_rescanned(tmp_path: Path) -> None:
    persona = _persona(tmp_path, "Start {A} End")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main(
        [str(persona), "--out", str(out_path), "--set", "A=value with {B} inside"]
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
        ]
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
        ]
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
        ]
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == "1-2-3"


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


def test_returns_exit_5_when_out_parent_dir_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = _persona(tmp_path, "Hi {NAME}!")
    out_path = tmp_path / "missing_dir" / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "NAME=World"])

    assert exit_code == 5
    captured = capsys.readouterr()
    assert (
        captured.err.rstrip("\n")
        == f"render_prompt: output directory does not exist: {out_path.parent}"
    )
    assert not out_path.exists()


def test_stdout_prints_byte_count_not_character_count_for_multibyte_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persona = _persona(tmp_path, "Value: {V}")
    out_path = tmp_path / "out.txt"

    exit_code = render_prompt.main([str(persona), "--out", str(out_path), "--set", "V=café"])

    assert exit_code == 0
    rendered = out_path.read_text(encoding="utf-8")
    assert rendered == "Value: café"
    byte_count = len(rendered.encode("utf-8"))
    assert byte_count != len(rendered)  # sanity: fixture actually has a multibyte char
    captured = capsys.readouterr()
    assert captured.out.rstrip("\n") == str(byte_count)
    assert len(out_path.read_bytes()) == byte_count
