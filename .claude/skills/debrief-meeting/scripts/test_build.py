"""Rules build.py must hold: run with `python3 -m pytest scripts/test_build.py -q`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import build
import pytest


def _make_template(tmp_path: Path) -> Path:
    template = tmp_path / "template.html"
    template.write_text("__MEETING_PAYLOAD__", encoding="utf-8")
    return template


def _load_payload(out_path: Path) -> dict:
    return json.loads(out_path.read_text(encoding="utf-8").replace("<\\/", "</"))


def _run_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workdir: Path, out_path: Path
) -> None:
    monkeypatch.setattr(build, "TEMPLATE", _make_template(tmp_path))
    monkeypatch.setattr(sys, "argv", ["build.py", str(workdir), "--out", str(out_path)])
    build.main()


def test_applies_windows_path_replacement_without_regex_error() -> None:
    turns = [{"text": "config lives at old-path"}]
    corrections = [{"from": "old-path", "to": "C:\\Temp"}]

    log = build.apply_corrections(turns, corrections)

    assert turns[0]["text"] == "config lives at C:\\Temp"
    assert log[0]["applied"] == 1


def test_returns_zero_applied_count_when_from_text_matches_nothing() -> None:
    turns = [{"text": "hello world"}]
    corrections = [{"from": "zzz_no_match_zzz", "to": "replacement"}]

    log = build.apply_corrections(turns, corrections)

    assert log == [
        {
            "kind": "text",
            "from": "zzz_no_match_zzz",
            "to": "replacement",
            "reason": None,
            "applied": 0,
        },
    ]
    assert turns[0]["text"] == "hello world"


def test_reports_extract_ran_false_and_warns_when_extract_json_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "meeting"
    workdir.mkdir()
    (workdir / "transcript.json").write_text(
        json.dumps({"turns": []}), encoding="utf-8"
    )
    out_path = tmp_path / "out" / "debrief.html"

    _run_main(tmp_path, monkeypatch, workdir, out_path)

    payload = _load_payload(out_path)
    assert payload["extract_ran"] is False
    warnings = payload["transcript"]["warnings"]
    assert isinstance(warnings, list)
    assert all(isinstance(w, str) for w in warnings)
    assert any("extract" in w.lower() and "run" in w.lower() for w in warnings)


def test_truncated_extract_json_exits_with_single_line_message_naming_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "meeting"
    workdir.mkdir()
    (workdir / "transcript.json").write_text(
        json.dumps({"turns": []}), encoding="utf-8"
    )
    extract_file = workdir / "extract.json"
    extract_file.write_text('{"decisions": [', encoding="utf-8")
    monkeypatch.setattr(build, "TEMPLATE", _make_template(tmp_path))
    monkeypatch.setattr(sys, "argv", ["build.py", str(workdir)])

    with pytest.raises(SystemExit) as excinfo:
        build.main()

    assert len(excinfo.value.args) == 1
    message = excinfo.value.args[0]
    assert isinstance(message, str)
    assert str(extract_file) in message
    assert "\n" not in message


def test_creates_missing_parent_directories_for_out_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "meeting"
    workdir.mkdir()
    (workdir / "transcript.json").write_text(
        json.dumps({"turns": []}), encoding="utf-8"
    )
    out_path = tmp_path / "nested" / "sub" / "debrief.html"

    _run_main(tmp_path, monkeypatch, workdir, out_path)

    assert out_path.is_file()


def test_warns_about_unknown_extract_json_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "meeting"
    workdir.mkdir()
    (workdir / "transcript.json").write_text(
        json.dumps({"turns": []}), encoding="utf-8"
    )
    (workdir / "extract.json").write_text(
        json.dumps({"bogus_key": []}), encoding="utf-8"
    )
    out_path = tmp_path / "out.html"

    _run_main(tmp_path, monkeypatch, workdir, out_path)

    warnings = _load_payload(out_path)["transcript"]["warnings"]
    assert any("bogus_key" in w for w in warnings)


def test_warns_about_correction_matching_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "meeting"
    workdir.mkdir()
    (workdir / "transcript.json").write_text(
        json.dumps({"turns": [{"text": "hello world"}]}),
        encoding="utf-8",
    )
    (workdir / "extract.json").write_text(
        json.dumps(
            {"corrections": [{"from": "zzz_no_match_zzz", "to": "replacement"}]}
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "out.html"

    _run_main(tmp_path, monkeypatch, workdir, out_path)

    warnings = _load_payload(out_path)["transcript"]["warnings"]
    assert any("zzz_no_match_zzz" in w for w in warnings)


def test_backslash_correction_produces_page_without_regex_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "meeting"
    workdir.mkdir()
    (workdir / "transcript.json").write_text(
        json.dumps({"turns": [{"text": "find it in old-path now"}]}),
        encoding="utf-8",
    )
    (workdir / "extract.json").write_text(
        json.dumps({"corrections": [{"from": "old-path", "to": "C:\\Temp"}]}),
        encoding="utf-8",
    )
    out_path = tmp_path / "out.html"

    _run_main(tmp_path, monkeypatch, workdir, out_path)

    assert out_path.is_file()
