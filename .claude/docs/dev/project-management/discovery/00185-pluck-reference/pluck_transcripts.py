"""Read assistant transcript text and extract pasteable shell snippets."""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


class PluckError(Exception):
    """An actionable failure safe to show in the popup."""


DISPLAY_WIDTH = 120
CLAUDE_BLOCK_TYPES = {"text", "thinking", "tool_use"}
_FENCE_RE = re.compile(r"([ \t]*)(`{3,}|~{3,})([^`~]*)")
SHELL_TAGS = {"bash", "sh", "zsh", "fish", "console"}
# Fences read like a terminal session: only `$ ` prompt lines are commands.
PROMPT_ONLY_TAGS = {"console", ""}
_PROMPT_LINE_RE = re.compile(r"\$ ")
_RUN_CUE_RE = re.compile(
    r"\b(run|in another terminal|in a second pane)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class TranscriptEntry:
    text: str
    source_order: int
    message_index: int


@dataclass(frozen=True)
class Snippet:
    id: str
    display: str
    raw: str
    rank_tier: int
    message_index: int
    source_order: int


def _read_jsonl(path: Path) -> list[object]:
    """Parse complete JSONL lines; drop an incomplete trailing line (a writer mid-append)."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise PluckError(f"cannot read {path}: {error.strerror or error}") from error
    records = []
    lines = data.split(b"\n")
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError as error:
            if number == len(lines) and not data.endswith(b"\n"):
                break
            raise PluckError(f"{path}: malformed record on line {number}") from error
    return records


def _to_entries(groups: list[list[str]], lookback: int) -> list[TranscriptEntry]:
    """Keep the newest `lookback` text-bearing records, given oldest first."""
    kept = groups[max(0, len(groups) - lookback) :]
    entries = []
    for position, texts in enumerate(kept):
        for text in texts:
            age = len(kept) - 1 - position
            entries.append(
                TranscriptEntry(text=text, source_order=len(entries), message_index=age)
            )
    return entries


def read_claude_entries(path: Path, lookback: int) -> list[TranscriptEntry]:
    groups = []
    for record in _read_jsonl(path):
        if (
            not isinstance(record, dict)
            or record.get("type") != "assistant"
            or record.get("isSidechain") is True
        ):
            continue
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if content is None:
            continue
        if not isinstance(content, list):
            raise PluckError(
                f"{path}: unsupported Claude format: assistant content is not a list"
            )
        types = [
            block.get("type") if isinstance(block, dict) else None for block in content
        ]
        if content and not CLAUDE_BLOCK_TYPES.intersection(types):
            raise PluckError(
                f"{path}: unsupported Claude format: unknown content blocks {types!r}"
            )
        texts = [
            block.get("text")
            for block, kind in zip(content, types, strict=True)
            if kind == "text"
        ]
        texts = [text for text in texts if isinstance(text, str)]
        if texts:
            groups.append(texts)
    return _to_entries(groups, lookback)


def _walk_pi_chain(records: list, path: Path) -> list[dict]:
    by_id = {}
    for record in records[1:]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise PluckError(
                f"{path}: unsupported pi format: record without a string id"
            )
        by_id[record["id"]] = record
    for record in records[1:]:
        parent = record.get("parentId")
        if parent is not None and (not isinstance(parent, str) or parent not in by_id):
            raise PluckError(
                f"{path}: malformed record {record['id']!r}: unknown parentId {parent!r}"
            )
    chain, seen = [], set()
    current = records[-1] if len(records) > 1 else None
    while current is not None:
        if current["id"] in seen:
            raise PluckError(
                f"{path}: malformed record {current['id']!r}: parentId cycle"
            )
        seen.add(current["id"])
        chain.append(current)
        parent = current.get("parentId")
        current = None if parent is None else by_id[parent]
    return chain


def read_pi_entries(path: Path, lookback: int) -> list[TranscriptEntry]:
    records = _read_jsonl(path)
    header = records[0] if records else None
    if not (
        isinstance(header, dict)
        and header.get("type") == "session"
        and isinstance(header.get("id"), str)
        and isinstance(header.get("cwd"), str)
    ):
        raise PluckError(
            f"{path}: unsupported pi format: first record is not a session header"
        )
    chain = _walk_pi_chain(records, path)
    groups = []
    for record in reversed(chain):
        message = record.get("message")
        if (
            record.get("type") != "message"
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
        ):
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        texts = [
            b.get("text")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        texts = [text for text in texts if isinstance(text, str)]
        if texts:
            groups.append(texts)
    return _to_entries(groups, lookback)


def strip_controls(text: str, keep: str = "") -> str:
    """Drop control and Unicode line/paragraph separator characters, except `keep`."""
    return "".join(
        ch
        for ch in text
        if ch in keep
        or (unicodedata.category(ch)[0] != "C" and ch not in "\u2028\u2029")
    )


def render_single_line(text: str) -> str:
    """Render text's first line, control-char-stripped and truncated to DISPLAY_WIDTH."""
    first = text.split("\n", 1)[0]
    shown = strip_controls(first, keep="\t").replace("\t", " ")
    return shown if len(shown) <= DISPLAY_WIDTH else shown[: DISPLAY_WIDTH - 1] + "…"


def _continues(line: str) -> bool:
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def _prompt_command(lines: list[str], start: int, end: int) -> tuple[str, int]:
    """Strip recognized prompts and retain explicit backslash continuations."""
    command = [lines[start][2:]]
    next_line = start + 1
    while next_line < end and _continues(command[-1]):
        line = lines[next_line]
        command.append(line[2:] if line.startswith("> ") else line)
        next_line += 1
    return "\n".join(command), next_line


def _extract_fence_bodies(
    lines: list[str], start: int, fence: re.Match
) -> tuple[list[tuple[int, str]], int, str]:
    """Return a fence's (line, command) bodies, the index after it, and its tag."""
    indent, delimiter, info = fence.groups()
    words = info.split()
    tag = words[0].lower() if words else ""
    closing = re.compile(
        r"[ \t]*" + re.escape(delimiter[0]) + "{" + str(len(delimiter)) + r",}[ \t]*"
    )
    end = next(
        (j for j in range(start + 1, len(lines)) if closing.fullmatch(lines[j])),
        len(lines),
    )
    if tag not in SHELL_TAGS | PROMPT_ONLY_TAGS:
        return [], end + 1, tag
    lines = [line[len(indent) :] if line.startswith(indent) else line for line in lines]
    body = lines[start + 1 : end]
    first = next((line for line in body if line.strip()), "")
    if tag not in PROMPT_ONLY_TAGS and not _PROMPT_LINE_RE.match(first):
        # A script, not a transcript: `$ ` lines may be heredoc or string content.
        return [(start, "\n".join(body).rstrip("\n"))], end + 1, tag
    bodies, shell_lines, index = [], [], start + 1
    while index < end:
        if _PROMPT_LINE_RE.match(lines[index]):
            line_index = index
            raw, index = _prompt_command(lines, index, end)
            bodies.append((line_index, raw))
            shell_lines.append(raw)
        else:
            shell_lines.append(lines[index])
            index += 1
    if tag not in PROMPT_ONLY_TAGS:
        bodies = [(start, "\n".join(shell_lines).rstrip("\n"))]
    return bodies, end + 1, tag


def extract_snippets(entries: list[TranscriptEntry]) -> list[Snippet]:
    found = []
    for item in sorted(entries, key=lambda entry: entry.source_order):
        lines = item.text.split("\n")
        gap, i = [], 0
        while i < len(lines):
            fence = _FENCE_RE.fullmatch(lines[i])
            if not fence and not _PROMPT_LINE_RE.match(lines[i]):
                gap.append(lines[i])
                i += 1
                continue
            cued = bool(_RUN_CUE_RE.search("\n".join(gap)))
            gap, tier = [], 1 if cued else 2
            if not fence:
                start = i
                raw, i = _prompt_command(lines, i, len(lines))
                bodies = [(start, raw)]
            else:
                bodies, i, tag = _extract_fence_bodies(lines, i, fence)
                if tag not in PROMPT_ONLY_TAGS:
                    tier = 0
            for line_index, raw in bodies:
                if not raw.strip():
                    continue
                display = render_single_line(raw)
                snippet_id = f"{item.message_index}:{item.source_order}:{line_index}"
                found.append(
                    Snippet(
                        snippet_id, display, raw, tier, item.message_index, len(found)
                    )
                )
    return sorted(
        found,
        key=lambda snippet: (
            snippet.rank_tier,
            snippet.message_index,
            snippet.source_order,
        ),
    )
