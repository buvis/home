"""Rules parse.py must hold: run with `python3 -m pytest scripts/test_parse.py -q`."""

from __future__ import annotations

import parse

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
<v Bouska, Tomas>Right, let us start with the migration.</v>

00:00:04.500 --> 00:00:09.000
<v Anna Novak>I think we should pick Postgres.</v>

00:00:08.000 --> 00:00:12.000
<v Bouska, Tomas>Agreed, Postgres it is.</v>
"""


def test_reads_voice_tag_speaker_and_timecodes() -> None:
    parsed = parse.parse_cues(VTT, "vtt")
    assert len(parsed) == 3
    assert parsed[0]["speaker"] == "Bouska, Tomas"
    assert parsed[0]["t"] == 1.0
    assert parsed[0]["end"] == 4.0
    assert parsed[0]["text"] == "Right, let us start with the migration."


def test_reads_colon_speaker_when_no_voice_tag() -> None:
    parsed = parse.parse_cues(
        "WEBVTT\n\n00:01:00.000 --> 00:01:02.000\nAnna Novak: Sounds good.\n",
        "vtt",
    )
    assert parsed[0]["speaker"] == "Anna Novak"
    assert parsed[0]["text"] == "Sounds good."


def test_keeps_sentence_with_colon_as_speech_not_speaker() -> None:
    parsed = parse.parse_cues(
        "WEBVTT\n\n00:01:00.000 --> 00:01:02.000\nSo my point is this: we ship.\n",
        "vtt",
    )
    assert parsed[0]["speaker"] is None
    assert parsed[0]["text"] == "So my point is this: we ship."


def test_parses_hour_and_millisecond_stamps() -> None:
    assert parse.to_seconds("01:02:03.500") == 3723.5
    assert parse.to_seconds("2:05") == 125.0
    assert parse.to_seconds("00:00:04,250") == 4.25


def test_merges_comma_swapped_and_abbreviated_names() -> None:
    mapping, merges = parse.canonicalize(
        ["Bouska, Tomas", "Tomas Bouska", "Tomas Bouska", "T. Bouska", "Anna Novak"],
    )
    assert mapping["Bouska, Tomas"] == mapping["Tomas Bouska"] == mapping["T. Bouska"]
    assert mapping["Anna Novak"] == "Anna Novak"
    assert len(merges) == 1  # only the initial form needs a fuzzy merge


def test_keeps_distinct_people_apart() -> None:
    mapping, _ = parse.canonicalize(["Anna Novak", "Adam Novak"])
    assert mapping["Anna Novak"] != mapping["Adam Novak"]


def test_strips_role_suffix_from_speaker_name() -> None:
    mapping, _ = parse.canonicalize(["Anna Novak (Guest)", "Anna Novak"])
    assert len(set(mapping.values())) == 1


def test_collapses_growing_live_caption_lines() -> None:
    raw = [
        {"t": 0.0, "end": 1.0, "speaker": "A", "text": "we should"},
        {"t": 0.0, "end": 2.0, "speaker": "A", "text": "we should ship it"},
        {"t": 0.0, "end": 3.0, "speaker": "A", "text": "we should ship it today"},
        {"t": 3.0, "end": 4.0, "speaker": "B", "text": "agreed"},
    ]
    out, dropped = parse.dedup_growth(raw)
    assert dropped == 2
    assert [c["text"] for c in out] == ["we should ship it today", "agreed"]
    assert out[0]["end"] == 3.0


def test_keeps_repeated_but_different_lines() -> None:
    raw = [
        {"t": 0.0, "end": 1.0, "speaker": "A", "text": "yes"},
        {"t": 1.0, "end": 2.0, "speaker": "A", "text": "no"},
    ]
    out, dropped = parse.dedup_growth(raw)
    assert dropped == 0
    assert len(out) == 2


def test_speaking_share_sums_to_one_hundred() -> None:
    data = parse.normalize_text(VTT, "vtt")
    assert sum(s["share_words"] for s in data["speakers"]) == 100.0
    assert data["meta"]["has_timecodes"] is True


def test_counts_overlapping_start_as_interruption() -> None:
    data = parse.normalize_text(VTT, "vtt")
    tomas = next(s for s in data["speakers"] if s["name"].startswith("Tomas"))
    assert tomas["interruptions"] == 1  # starts at 8.0 while Anna runs to 9.0


def test_reads_teams_copied_header_layout() -> None:
    text = "Anna Novak   0:12\nWe need a decision today.\nTomas Bouska   1:40\nLet us vote.\n"
    parsed = parse.parse_cues(text, "text")
    assert [c["speaker"] for c in parsed] == ["Anna Novak", "Tomas Bouska"]
    assert parsed[0]["t"] == 12.0
    assert parsed[1]["t"] == 100.0


def test_reads_bracketed_timestamp_layout() -> None:
    parsed = parse.parse_cues("[00:03:10] Anna Novak: Ship it.\n", "text")
    assert parsed[0]["t"] == 190.0
    assert parsed[0]["speaker"] == "Anna Novak"


def test_warns_when_transcript_has_no_timecodes() -> None:
    data = parse.normalize_text("Anna Novak: hello there\nTomas Bouska: hi\n", "text")
    assert data["meta"]["has_timecodes"] is False
    assert any("no timecodes" in w for w in data["warnings"])


def test_returns_none_for_empty_input() -> None:
    assert parse.normalize_text("", "text") is None
