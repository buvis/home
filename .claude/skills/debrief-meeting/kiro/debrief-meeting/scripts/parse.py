#!/usr/bin/env python3
"""Normalize a meeting transcript into transcript.json.

Deterministic pass, no model: parse cues (VTT/SRT/DOCX/TXT), canonicalize
speaker names, drop live-caption duplicates, merge cues into turns, and
compute speaking stats. Everything here must be reproducible; judgment calls
belong in the model's extract.json.

Usage: parse.py TRANSCRIPT [--out DIR]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

TS = r"\d{1,3}:\d{1,2}(?::\d{1,2})?(?:[.,]\d{1,3})?"
CUE_RE = re.compile(rf"({TS})\s*-->\s*({TS})")
VOICE_RE = re.compile(r"<v\s+([^>]+?)\s*>(.*?)(?:</v>)?$", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
# "[00:12:34] Name: text" / "00:12:34 Name: text"
LINE_TS_RE = re.compile(rf"^\[?({TS})\]?\s+(.{{1,60}}?):\s*(.*)$")
# Teams "copy transcript": a "Name    12:34" header line, text on the next line
HEADER_RE = re.compile(rf"^(.{{1,60}}?)\s{{2,}}({TS})\s*$")
SPEAKER_RE = re.compile(r"^(.{1,60}?):\s+(.*)$")
NAME_PARTICLES = {"van", "von", "de", "der", "den", "da", "di", "la", "le", "of"}
# ponytail: English filler list only; add per-language sets if transcripts stop being English
FILLERS = re.compile(
    r"\b(um+|uh+|erm|uhm|mhm|hmm+|you know|i mean|sort of|kind of)\b",
    re.IGNORECASE,
)


def to_seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    secs = float(parts[-1])
    if len(parts) > 1:
        secs += int(parts[-2]) * 60
    if len(parts) > 2:
        secs += int(parts[-3]) * 3600
    return round(secs, 3)


def read_source(path: Path) -> tuple[str, str]:
    """Return (text, format). DOCX is unzipped with the stdlib, no dependency."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", "  ", xml)
        return TAG_RE.sub("", xml), "docx"
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".vtt" or text.lstrip().startswith("WEBVTT"):
        return text, "vtt"
    if suffix == ".srt":
        return text, "srt"
    return text, "text"


def parse_cues(text: str, fmt: str) -> list[dict]:
    """Return raw cues: [{'t','end','speaker','text'}]. t/end are None if untimed."""
    if fmt in ("vtt", "srt") or CUE_RE.search(text):
        return _parse_timed(text)
    return _parse_plain(text)


def _plausible_name(name: str) -> bool:
    """Guard the `Name: text` pattern against ordinary prose ("my point is this: ...")."""
    name = name.strip()
    if not name or len(name) > 60 or name[-1] in ".?!":
        return False
    tokens = [t for t in re.split(r"[\s,]+", name) if t]
    if not tokens or len(tokens) > 5:
        return False
    return all(
        t[0].isupper() or t[0].isdigit() or "@" in t or t.lower() in NAME_PARTICLES
        for t in tokens
    )


def _parse_timed(text: str) -> list[dict]:
    cues: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stamps = CUE_RE.search(lines[i])
        if not stamps:
            i += 1
            continue
        start, end = to_seconds(stamps.group(1)), to_seconds(stamps.group(2))
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip() and not CUE_RE.search(lines[i]):
            body.append(lines[i])
            i += 1
        raw = " ".join(body).strip()
        if not raw:
            continue
        speaker, said = None, raw
        voice = VOICE_RE.match(raw)
        if voice:
            speaker, said = voice.group(1).strip(), voice.group(2)
        else:
            named = SPEAKER_RE.match(TAG_RE.sub("", raw))
            if named and _plausible_name(named.group(1)):
                speaker, said = named.group(1).strip(), named.group(2)
        said = TAG_RE.sub("", said).strip()
        if said:
            cues.append({"t": start, "end": end, "speaker": speaker, "text": said})
    return cues


def _parse_plain(text: str) -> list[dict]:
    cues: list[dict] = []
    pending: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        header = HEADER_RE.match(line)
        if header and _plausible_name(header.group(1)):
            pending = {
                "t": to_seconds(header.group(2)),
                "end": None,
                "speaker": header.group(1).strip(),
                "text": "",
            }
            continue
        stamped = LINE_TS_RE.match(line)
        if stamped and _plausible_name(stamped.group(2)):
            cues.append(
                {
                    "t": to_seconds(stamped.group(1)),
                    "end": None,
                    "speaker": stamped.group(2).strip(),
                    "text": stamped.group(3).strip(),
                },
            )
            pending = None
            continue
        if pending is not None:
            pending["text"] = line
            cues.append(pending)
            pending = None
            continue
        named = SPEAKER_RE.match(line)
        if named and _plausible_name(named.group(1)):
            cues.append(
                {
                    "t": None,
                    "end": None,
                    "speaker": named.group(1).strip(),
                    "text": named.group(2).strip(),
                },
            )
        elif cues:
            cues[-1]["text"] = f"{cues[-1]['text']} {line}".strip()
        else:
            cues.append({"t": None, "end": None, "speaker": None, "text": line})
    return [c for c in cues if c["text"]]


def display_form(name: str) -> str:
    """Drop role suffixes and un-swap 'Bouska, Tomas' into 'Tomas Bouska'."""
    n = re.sub(r"\s*\([^)]*\)", " ", name)
    n = re.sub(r"\s+", " ", n).strip().strip(",")
    if "," in n:
        last, _, first = n.partition(",")
        if last.strip() and first.strip():
            n = f"{first.strip()} {last.strip()}"
    return n


def name_key(name: str) -> tuple[str, ...]:
    """Order-insensitive identity key: 'Bouska, Tomas' == 'Tomas Bouska'."""
    return tuple(sorted(w for w in re.findall(r"\w+", display_form(name).casefold())))


def _prefix_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """'T. Bouska' vs 'Tomas Bouska': same token count, every token a prefix pair."""
    if len(a) != len(b) or not a:
        return False
    return all(x.startswith(y) or y.startswith(x) for x, y in zip(a, b))


def canonicalize(names: list[str]) -> tuple[dict[str, str], list[dict]]:
    """Map every raw speaker string to one display name. Returns (mapping, merges)."""
    counts: dict[str, int] = defaultdict(int)
    for name in names:
        counts[name] += 1
    groups: dict[tuple[str, ...], list[str]] = {}
    merges: list[dict] = []
    for raw in sorted(counts, key=lambda n: (-counts[n], n)):
        key = name_key(raw)
        hit = key if key in groups else None
        if hit is None:
            hit = next(
                (
                    k
                    for k in groups
                    if _prefix_match(k, key)
                    or difflib.SequenceMatcher(None, " ".join(k), " ".join(key)).ratio()
                    >= 0.9
                ),
                None,
            )
            if hit is not None:
                merges.append(
                    {"kind": "speaker-merge", "from": raw, "to": groups[hit][0]},
                )
        if hit is None:
            groups[key] = [raw]
        else:
            groups[hit].append(raw)
    mapping: dict[str, str] = {}
    for variants in groups.values():
        # richest spelling wins: most words, then most frequent
        display = display_form(max(variants, key=lambda v: (len(v.split()), counts[v])))
        for variant in variants:
            mapping[variant] = display
    for merge in merges:
        merge["to"] = mapping[merge["to"]]
    return mapping, merges


def dedup_growth(cues: list[dict]) -> tuple[list[dict], int]:
    """Live captions re-emit a growing line. Keep the longest, count what went."""
    out: list[dict] = []
    dropped = 0
    for cue in cues:
        prev = out[-1] if out else None
        if prev and prev["speaker"] == cue["speaker"]:
            old, new = prev["text"], cue["text"]
            if new.startswith(old) or old in new:
                prev["text"] = new
                prev["end"] = cue["end"] or prev["end"]
                dropped += 1
                continue
            if old.startswith(new) or new in old:
                prev["end"] = cue["end"] or prev["end"]
                dropped += 1
                continue
        out.append(dict(cue))
    return out, dropped


def merge_turns(cues: list[dict]) -> list[dict]:
    turns: list[dict] = []
    for cue in cues:
        prev = turns[-1] if turns else None
        if prev and prev["speaker"] == cue["speaker"]:
            prev["text"] = f"{prev['text']} {cue['text']}".strip()
            prev["end"] = cue["end"] or cue["t"] or prev["end"]
            continue
        turns.append(
            {
                "t": cue["t"],
                "end": cue["end"] or cue["t"],
                "speaker": cue["speaker"],
                "text": cue["text"],
            },
        )
    for i, turn in enumerate(turns):
        turn["i"] = i
    return turns


def count_interruptions(cues: list[dict], mapping: dict[str, str]) -> dict[str, int]:
    """A speaker starting before the previous one finished. Needs cue-level times."""
    counts: dict[str, int] = defaultdict(int)
    for prev, cur in zip(cues, cues[1:]):
        if prev.get("end") is None or cur.get("t") is None:
            continue
        if prev["speaker"] == cur["speaker"]:
            continue
        if cur["t"] < prev["end"] - 0.5:
            counts[mapping.get(cur["speaker"], cur["speaker"])] += 1
    return counts


def build_speakers(
    turns: list[dict],
    cues: list[dict],
    mapping: dict[str, str],
) -> list[dict]:
    stats: dict[str, dict] = {}
    for turn in turns:
        name = turn["speaker"] or "Unknown"
        entry = stats.setdefault(
            name,
            {
                "name": name,
                "words": 0,
                "turns": 0,
                "seconds": 0.0,
                "first_t": turn["t"],
                "last_t": turn["t"],
                "longest_turn": 0.0,
                "questions": 0,
                "fillers": 0,
            },
        )
        span = (
            max(0.0, (turn["end"] or 0) - turn["t"]) if turn["t"] is not None else 0.0
        )
        entry["words"] += len(turn["text"].split())
        entry["turns"] += 1
        entry["seconds"] += span
        entry["longest_turn"] = max(entry["longest_turn"], span)
        entry["questions"] += turn["text"].count("?")
        entry["fillers"] += len(FILLERS.findall(turn["text"]))
        if turn["t"] is not None:
            first = entry["first_t"]
            entry["first_t"] = turn["t"] if first is None else min(first, turn["t"])
            entry["last_t"] = max(entry["last_t"] or 0, turn["end"] or turn["t"])
    interrupts = count_interruptions(cues, mapping)
    total_words = sum(s["words"] for s in stats.values()) or 1
    total_secs = sum(s["seconds"] for s in stats.values()) or 1
    out: list[dict] = []
    for idx, entry in enumerate(sorted(stats.values(), key=lambda x: -x["words"])):
        entry["id"] = f"s{idx}"
        entry["share_words"] = round(100 * entry["words"] / total_words, 1)
        entry["share_time"] = round(100 * entry["seconds"] / total_secs, 1)
        entry["seconds"] = round(entry["seconds"], 1)
        entry["longest_turn"] = round(entry["longest_turn"], 1)
        entry["wpm"] = (
            round(60 * entry["words"] / entry["seconds"], 1)
            if entry["seconds"]
            else None
        )
        entry["interruptions"] = interrupts.get(entry["name"], 0)
        out.append(entry)
    return out


def build_buckets(turns: list[dict], duration: float, slots: int = 48) -> dict | None:
    """Words per speaker per time slot — the participation strip under the timeline."""
    if not duration:
        return None
    size = duration / slots
    series = [{"t": round(i * size, 1), "by": {}} for i in range(slots)]
    for turn in turns:
        if turn["t"] is None or not turn["s"]:
            continue
        by = series[min(slots - 1, int(turn["t"] / size))]["by"]
        by[turn["s"]] = by.get(turn["s"], 0) + len(turn["text"].split())
    return {"size": round(size, 1), "series": series}


def build_matrix(turns: list[dict]) -> dict[str, dict[str, int]]:
    """matrix[a][b] = times b spoke straight after a. The interaction graph."""
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for prev, cur in zip(turns, turns[1:]):
        if prev["s"] and cur["s"] and prev["s"] != cur["s"]:
            matrix[prev["s"]][cur["s"]] += 1
    return {a: dict(b) for a, b in matrix.items()}


def normalize(path: Path) -> dict:
    text, fmt = read_source(path)
    data = normalize_text(text, fmt)
    if data is None:
        sys.exit(f"no speech found in {path} (format guessed: {fmt})")
    data["source"] = str(path)
    return data


def normalize_text(text: str, fmt: str) -> dict | None:
    cues = parse_cues(text, fmt)
    if not cues:
        return None

    mapping, merges = canonicalize([c["speaker"] for c in cues if c["speaker"]])
    for cue in cues:
        if cue["speaker"]:
            cue["speaker"] = mapping.get(cue["speaker"], cue["speaker"])

    deduped, dropped = dedup_growth(cues)
    turns = merge_turns(deduped)
    speakers = build_speakers(turns, deduped, mapping)
    ids = {s["name"]: s["id"] for s in speakers}
    for turn in turns:
        turn["s"] = ids.get(turn["speaker"] or "Unknown")
        del turn["speaker"]

    timed = [t for t in turns if t["t"] is not None]
    duration = max((t["end"] or t["t"] for t in timed), default=0.0)

    warnings: list[str] = []
    if not timed:
        warnings.append("no timecodes found - timeline and time-share are unavailable")
    if len(speakers) == 1:
        warnings.append("only one speaker detected - check the speaker-line format")
    if any(s["name"] == "Unknown" for s in speakers):
        warnings.append("some speech is unattributed (speaker 'Unknown')")

    corrections = merges + (
        [{"kind": "caption-dedup", "count": dropped}] if dropped else []
    )
    return {
        "source": None,
        "format": fmt,
        "meta": {
            "duration": round(duration, 1),
            "cues": len(cues),
            "turns": len(turns),
            "words": sum(s["words"] for s in speakers),
            "has_timecodes": bool(timed),
        },
        "speakers": speakers,
        "turns": turns,
        "matrix": build_matrix(turns),
        "buckets": build_buckets(turns, duration),
        "corrections": corrections,
        "warnings": warnings,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript")
    ap.add_argument(
        "--out",
        help="output dir (default: <transcript>-debrief/ next to the input)",
    )
    args = ap.parse_args()

    path = Path(args.transcript).expanduser().resolve()
    if not path.is_file():
        sys.exit(f"no such transcript: {path}")
    outdir = (
        Path(args.out).expanduser()
        if args.out
        else path.parent / f"{path.stem}-debrief"
    )
    outdir.mkdir(parents=True, exist_ok=True)

    data = normalize(path)
    (outdir / "transcript.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1),
    )
    for warning in data["warnings"]:
        print(f"WARN: {warning}", file=sys.stderr)
    print(
        f"wrote {outdir / 'transcript.json'}: {len(data['speakers'])} speakers, "
        f"{data['meta']['turns']} turns, {data['meta']['words']} words, "
        f"{data['meta']['duration'] / 60:.0f} min",
    )


if __name__ == "__main__":
    main()
