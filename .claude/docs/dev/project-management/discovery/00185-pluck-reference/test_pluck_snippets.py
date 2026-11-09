# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Exercise transcript readers and byte-preserving snippet extraction."""

import json
import tempfile
import unittest
from pathlib import Path

from pluck_transcripts import (
    PluckError,
    Snippet,
    TranscriptEntry,
    extract_snippets,
    read_claude_entries,
    read_pi_entries,
)


def write_jsonl(path: Path, rows: list[object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("".join(line + "\n" for line in lines))
    return path


THINK = {"type": "thinking", "thinking": "$ echo hidden thought"}
CLAUDE_TOOL = {
    "type": "tool_use",
    "id": "toolu_1",
    "name": "Bash",
    "input": {"command": "echo tool"},
}
PI_TOOL = {
    "type": "toolCall",
    "id": "call_1",
    "name": "bash",
    "arguments": {"command": "echo tool"},
}
PI_HEADER = {"type": "session", "id": "sess-1", "cwd": "/work/app"}
PI_ROOT = {
    "type": "model_change",
    "id": "r0",
    "parentId": None,
    "provider": "anthropic",
}


def block(value: str) -> dict[str, str]:
    return {"type": "text", "text": value}


def claude_msg(
    *blocks: object, sidechain: bool | None = None, kind: str = "assistant"
) -> dict[str, object]:
    record: dict[str, object] = {
        "type": kind,
        "message": {"role": kind, "content": list(blocks)},
    }
    if sidechain is not None:
        record["isSidechain"] = sidechain
    return record


def pi_msg(
    record_id: object, parent: object, role: str, *blocks: object
) -> dict[str, object]:
    return {
        "type": "message",
        "id": record_id,
        "parentId": parent,
        "message": {"role": role, "content": list(blocks)},
    }


def jsonl_text(rows: list[object]) -> str:
    return "".join(
        (row if isinstance(row, str) else json.dumps(row)) + "\n" for row in rows
    )


def entries_of(found: list[TranscriptEntry]) -> list[tuple[int, str]]:
    return sorted((entry.message_index, entry.text) for entry in found)


def entry(text: str, message_index: int, source_order: int) -> TranscriptEntry:
    return TranscriptEntry(
        text=text, source_order=source_order, message_index=message_index
    )


def ranked(snippets: list[Snippet]) -> list[tuple[int, int, str]]:
    return [
        (snippet.rank_tier, snippet.message_index, snippet.raw) for snippet in snippets
    ]


class SnippetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def assert_pluck_error(self, call: object, *args: object) -> str:
        with self.assertRaises(PluckError) as caught:
            call(*args)
        message = str(caught.exception)
        self.assertTrue(message.strip())
        self.assertNotIn("\n", message)
        return message

    def test_claude_text_only(self) -> None:
        rows = [
            {"type": "summary", "summary": "$ echo summary"},
            claude_msg(block("$ echo user"), kind="user"),
            {
                "type": "user",
                "message": {"role": "user", "content": "$ echo plain user"},
            },
            claude_msg(block("old reply")),
            claude_msg(block("side reply"), sidechain=True),
            claude_msg(
                THINK,
                block("  first\tblock \n"),
                CLAUDE_TOOL,
                block("second block"),
                sidechain=False,
            ),
            claude_msg(CLAUDE_TOOL),
        ]
        found = read_claude_entries(write_jsonl(self.root / "main.jsonl", rows), 20)
        self.assertEqual(
            entries_of(found),
            [(0, "  first\tblock \n"), (0, "second block"), (1, "old reply")],
        )
        self.assertTrue(all(isinstance(item, TranscriptEntry) for item in found))
        orders = {item.text: item.source_order for item in found}
        self.assertEqual(len(set(orders.values())), 3)
        self.assertLess(orders["  first\tblock \n"], orders["second block"])
        other = write_jsonl(
            self.root / "other.jsonl", [claude_msg(block("other file"))]
        )
        self.assertEqual(
            entries_of(read_claude_entries(other, 20)), [(0, "other file")]
        )
        self.assertEqual(
            read_claude_entries(write_jsonl(self.root / "empty.jsonl", []), 20), []
        )

    def test_claude_lookback_counts_text_entries(self) -> None:
        rows = [
            claude_msg(block("one")),
            claude_msg(CLAUDE_TOOL),
            claude_msg(block("two")),
            claude_msg(THINK, CLAUDE_TOOL),
            claude_msg(block("three-a"), CLAUDE_TOOL, block("three-b")),
            claude_msg(CLAUDE_TOOL),
            claude_msg(block("side"), sidechain=True),
        ]
        path = write_jsonl(self.root / "lookback.jsonl", rows)
        newest = [(0, "three-a"), (0, "three-b")]
        cases = (
            (1, newest),
            (2, [*newest, (1, "two")]),
            (3, [*newest, (1, "two"), (2, "one")]),
        )
        for lookback, expected in (*cases, (50, cases[-1][1])):
            with self.subTest(lookback=lookback):
                self.assertEqual(
                    entries_of(read_claude_entries(path, lookback)), expected
                )
        many = [
            row
            for i in range(6)
            for row in (claude_msg(block(f"m{i}")), claude_msg(CLAUDE_TOOL))
        ]
        long = write_jsonl(self.root / "many.jsonl", many)
        everything = [(i, f"m{5 - i}") for i in range(6)]
        for lookback, expected in (
            (5, everything[:5]),
            (6, everything),
            (20, everything),
        ):
            with self.subTest(many=lookback):
                self.assertEqual(
                    entries_of(read_claude_entries(long, lookback)), expected
                )

    def test_pi_active_branch(self) -> None:
        rows = [
            PI_HEADER,
            PI_ROOT,
            pi_msg("x1", None, "assistant", block("other root")),
            pi_msg("u1", "r0", "user", block("user text")),
            pi_msg("a1", "u1", "assistant", block("first"), THINK, block("second")),
            pi_msg("s1", "u1", "assistant", block("sibling")),
            pi_msg("t1", "a1", "assistant", PI_TOOL),
            pi_msg("tr", "t1", "toolResult", block("tool output")),
            pi_msg("a3", "tr", "assistant", THINK, PI_TOOL, block("newest")),
            pi_msg("s2", "s1", "assistant", block("sibling child")),
            {
                "type": "model_change",
                "id": "m9",
                "parentId": "a3",
                "provider": "openai",
            },
        ]
        path = write_jsonl(self.root / "pi.jsonl", rows)
        main = [(0, "newest"), (1, "first"), (1, "second")]
        for lookback, expected in ((1, main[:1]), (2, main), (20, main)):
            with self.subTest(lookback=lookback):
                self.assertEqual(entries_of(read_pi_entries(path, lookback)), expected)
        orders = {item.text: item.source_order for item in read_pi_entries(path, 20)}
        self.assertEqual(len(set(orders.values())), 3)
        self.assertLess(orders["first"], orders["second"])
        flipped = write_jsonl(
            self.root / "flip.jsonl", [*rows, pi_msg("u9", "s2", "user", block("next"))]
        )
        self.assertEqual(
            entries_of(read_pi_entries(flipped, 20)),
            [(0, "sibling child"), (1, "sibling")],
        )
        self.assertEqual(
            read_pi_entries(write_jsonl(self.root / "header.jsonl", [PI_HEADER]), 20),
            [],
        )

    def test_pi_lookback_counts_branch_messages(self) -> None:
        chain = [
            pi_msg(f"l{i}", f"l{i - 1}" if i else None, "assistant", block(f"m{i}"))
            for i in range(6)
        ]
        long = write_jsonl(self.root / "long.jsonl", [PI_HEADER, *chain])
        everything = [(i, f"m{5 - i}") for i in range(6)]
        for lookback, expected in (
            (5, everything[:5]),
            (6, everything),
            (20, everything),
        ):
            with self.subTest(long=lookback):
                self.assertEqual(entries_of(read_pi_entries(long, lookback)), expected)

    def test_trailing_append(self) -> None:
        claude = self.root / "claude.jsonl"
        done = jsonl_text([claude_msg(block("complete"))])
        pending = json.dumps(claude_msg(block("pending")))
        tails = (
            ("", [(0, "complete")]),
            (pending[:25], [(0, "complete")]),
            (pending, [(0, "pending"), (1, "complete")]),
        )
        for tail, expected in (
            *tails,
            (pending + "\n", [(0, "pending"), (1, "complete")]),
        ):
            with self.subTest(claude_tail=tail):
                claude.write_text(done + tail)
                self.assertEqual(entries_of(read_claude_entries(claude, 20)), expected)
        claude.write_text(pending[:25])
        self.assertEqual(read_claude_entries(claude, 20), [])
        pi = self.root / "pi.jsonl"
        rows = [
            PI_HEADER,
            pi_msg("a1", None, "assistant", block("main")),
            pi_msg("b1", None, "assistant", block("branch")),
        ]
        partial = json.dumps(pi_msg("a2", "a1", "assistant", block("partial")))
        for tail, expected in (
            (partial[:30], [(0, "branch")]),
            (partial, [(0, "partial"), (1, "main")]),
        ):
            with self.subTest(pi_tail=tail):
                pi.write_text(jsonl_text(rows) + tail)
                self.assertEqual(entries_of(read_pi_entries(pi, 20)), expected)
        pi.write_text(jsonl_text(rows) + partial + "\n")
        self.assertEqual(
            entries_of(read_pi_entries(pi, 20)), [(0, "partial"), (1, "main")]
        )
        pi.write_text(jsonl_text([PI_HEADER]) + partial[:30])
        self.assertEqual(read_pi_entries(pi, 20), [])

    def test_malformed_record(self) -> None:
        good = claude_msg(block("fine"))
        for name, rows, line in (
            ("broken.jsonl", [good, good, '{"type": "assistant", "mess', good], 3),
            ("later.jsonl", [good, "not json", good, good], 2),
            ("last.jsonl", [good, good, good, "not json"], 4),
        ):
            with self.subTest(claude=name):
                path = write_jsonl(self.root / name, rows)
                message = self.assert_pluck_error(read_claude_entries, path, 20)
                self.assertIn(name, message)
                rest = message.replace(str(path), "").replace(name, "")
                self.assertRegex(rest, rf"\b{line}\b")
                for other in range(2, len(rows) + 1):
                    if other != line:
                        self.assertNotRegex(rest, rf"\b{other}\b")

    def test_malformed_pi_record(self) -> None:
        tip = pi_msg("a1", "r0", "assistant", block("tip"))
        valid = write_jsonl(self.root / "valid.jsonl", [PI_HEADER, PI_ROOT, tip])
        self.assertEqual(entries_of(read_pi_entries(valid, 20)), [(0, "tip")])
        cases = {
            "bad-json": [PI_HEADER, PI_ROOT, "{not json", tip],
            "unknown-parent": [
                PI_HEADER,
                PI_ROOT,
                pi_msg("a1", "r00", "assistant", block("tip")),
            ],
            "int-parent": [
                PI_HEADER,
                PI_ROOT,
                pi_msg("a1", 7, "assistant", block("tip")),
            ],
            "header-parent": [
                PI_HEADER,
                PI_ROOT,
                pi_msg("a1", "sess-1", "assistant", block("tip")),
            ],
            "off-branch": [
                PI_HEADER,
                {"type": "model_change", "id": "r1", "parentId": "gone"},
                PI_ROOT,
                tip,
            ],
            "cycle": [
                PI_HEADER,
                pi_msg("a1", "a2", "assistant", block("x")),
                pi_msg("a2", "a1", "assistant", block("y")),
            ],
            "self-cycle": [PI_HEADER, pi_msg("a1", "a1", "assistant", block("x"))],
        }
        for name, rows in cases.items():
            with self.subTest(pi=name):
                self.assert_pluck_error(
                    read_pi_entries, write_jsonl(self.root / f"{name}.jsonl", rows), 20
                )

    def test_unsupported_format(self) -> None:
        accepted = [
            claude_msg(CLAUDE_TOOL),
            claude_msg(THINK),
            {"type": "user", "message": {"content": "plain"}},
        ]
        self.assertEqual(
            read_claude_entries(write_jsonl(self.root / "ok.jsonl", accepted), 20), []
        )
        claude_cases = {
            "string-content": [
                {
                    "type": "assistant",
                    "message": {"role": "assistant", "content": "$ echo hi"},
                }
            ],
            "dict-content": [
                {"type": "assistant", "message": {"content": block("$ echo hi")}}
            ],
            "unknown-blocks": [
                claude_msg({"type": "tool_result", "content": "x"}, {"type": "image"})
            ],
        }
        for name, rows in claude_cases.items():
            with self.subTest(claude=name):
                self.assert_pluck_error(
                    read_claude_entries,
                    write_jsonl(self.root / f"c-{name}.jsonl", rows),
                    20,
                )

    def test_unsupported_pi_format(self) -> None:
        pi_ok = write_jsonl(
            self.root / "pi-ok.jsonl",
            [PI_HEADER, pi_msg("a1", None, "assistant", block("ok"))],
        )
        self.assertEqual(entries_of(read_pi_entries(pi_ok, 20)), [(0, "ok")])
        tip = pi_msg("a1", None, "assistant", block("x"))
        pi_cases = {
            "claude-file": [claude_msg(block("x"))],
            "header-late": [tip, PI_HEADER],
            "wrong-type": [
                {"type": "sessions", "id": "sess-1", "cwd": "/work/app"},
                tip,
            ],
            "no-cwd": [{"type": "session", "id": "sess-1"}, tip],
            "int-header-id": [{"type": "session", "id": 5, "cwd": "/work/app"}, tip],
            "list-record": [PI_HEADER, tip, ["type", "message"]],
            "missing-id": [PI_HEADER, {"type": "model_change", "parentId": None}, tip],
            "int-id": [PI_HEADER, pi_msg(9, None, "assistant", block("x"))],
        }
        for name, rows in pi_cases.items():
            with self.subTest(pi=name):
                self.assert_pluck_error(
                    read_pi_entries,
                    write_jsonl(self.root / f"p-{name}.jsonl", rows),
                    20,
                )

    def test_shell_fences(self) -> None:
        text = "\n".join(
            [
                "Setup steps:",
                "```bash",
                "echo bash",
                "```",
                "```sh",
                "echo sh",
                "```",
                "Run this in another terminal:",
                "```zsh",
                "echo zsh",
                "```",
                "```fish",
                "echo fish",
                "```",
                "```python",
                "print('no')",
                "```",
                "```bashrc",
                "export NOPE=1",
                "```",
            ]
        )
        found = extract_snippets(
            [entry(text, 3, 0), entry("```sh\necho newer\n```\n", 2, 1)]
        )
        expected = [
            (0, 2, "echo newer"),
            *((0, 3, f"echo {tag}") for tag in ("bash", "sh", "zsh", "fish")),
        ]
        self.assertEqual(ranked(found), expected)
        self.assertEqual(
            [snippet.display for snippet in found], [raw for _, _, raw in expected]
        )
        self.assertEqual(len({snippet.id for snippet in found}), 5)
        self.assertEqual(extract_snippets([]), [])
        self.assertEqual(
            extract_snippets([entry("No commands, just $5 and `ls`.", 0, 0)]), []
        )

    def test_console_output_excluded(self) -> None:
        console = "```console\n$ ls -la\ntotal 8\n$no-space\n-rw-r--r-- file\n$ echo 'hi there'\nhi there\n```"
        cases = (
            ("Expected listing:\n", 0, 2),
            ("Run this in another terminal:\n", 1, 1),
            ("In a second pane:\n", 4, 1),
            ("Output:\n", 2, 2),
            ("Setup steps:\n", 3, 2),
        )
        for lead, message_index, tier in cases:
            with self.subTest(lead=lead):
                found = extract_snippets([entry(lead + console, message_index, 0)])
                expected = [
                    (tier, message_index, "ls -la"),
                    (tier, message_index, "echo 'hi there'"),
                ]
                self.assertEqual(ranked(found), expected)
        self.assertEqual(
            extract_snippets([entry("```console\ntotal 8\nhi there\n```", 0, 0)]), []
        )

    def test_standalone_prompt(self) -> None:
        text = (
            "Expected:\n$ git status\n$ git diff --stat\nThen $ not this\n$PATH stays\n"
        )
        plain = extract_snippets([entry(text, 0, 0)])
        self.assertEqual(
            ranked(plain), [(2, 0, "git status"), (2, 0, "git diff --stat")]
        )
        self.assertEqual(
            [snippet.display for snippet in plain], ["git status", "git diff --stat"]
        )
        self.assertEqual(
            ranked(extract_snippets([entry("Run this:\n$ make test\n", 1, 4)])),
            [(1, 1, "make test")],
        )
        self.assertEqual(
            ranked(extract_snippets([entry("Output:\n$ ls\n", 2, 0)])), [(2, 2, "ls")]
        )
        fenced = extract_snippets(
            [entry("```bash\n$ echo inside\necho next\n```", 0, 0)]
        )
        self.assertEqual(ranked(fenced), [(0, 0, "echo inside\necho next")])

    def test_untagged_fence_prompt_lines_extracted(self) -> None:
        text = "```\n$ npm install\nadded 3 packages\n$ npm test\n```"
        found = extract_snippets([entry(text, 0, 0)])
        self.assertEqual(ranked(found), [(2, 0, "npm install"), (2, 0, "npm test")])
        self.assertEqual(extract_snippets([entry("```\nplain output\n```", 0, 0)]), [])

    def test_script_fence_keeps_heredoc_prompt_text(self) -> None:
        for tag in ("bash", "sh", "zsh", "fish"):
            with self.subTest(tag=tag):
                script = "cat <<'EOF'\n$ HOME stays literal\nEOF"
                found = extract_snippets([entry(f"```{tag}\n{script}\n```", 0, 0)])
                self.assertEqual([snippet.raw for snippet in found], [script])

    def test_fence_tag_ignores_attributes_and_case(self) -> None:
        for opener in ('```bash title="setup"', "```Bash", "```SH {.numberLines}"):
            with self.subTest(opener=opener):
                found = extract_snippets([entry(f"{opener}\nmake test\n```", 0, 0)])
                self.assertEqual(ranked(found), [(0, 0, "make test")])

    def test_console_continuation_preserved(self) -> None:
        text = "```console\n$ docker run \\\n>   --name 'my app' \\\n>   image\ncontainer-output\n$ echo done\ndone\n```"
        found = extract_snippets([entry(text, 0, 0)])
        self.assertEqual(
            [snippet.raw for snippet in found],
            ["docker run \\\n  --name 'my app' \\\n  image", "echo done"],
        )

    def test_standalone_continuation_preserved(self) -> None:
        text = "$ docker run \\\n  --name 'my app' \\\n\timage\nOutput: started\n$ echo done"
        found = extract_snippets([entry(text, 0, 0)])
        self.assertEqual(
            [snippet.raw for snippet in found],
            ["docker run \\\n  --name 'my app' \\\n\timage", "echo done"],
        )

    def test_escaped_backslash_does_not_consume_output(self) -> None:
        text = "$ echo \\\\\noutput\n$ echo next"
        found = extract_snippets([entry(text, 0, 0)])
        self.assertEqual([snippet.raw for snippet in found], ["echo \\\\", "echo next"])

    def test_shell_prompt_continuation_preserved(self) -> None:
        text = "```sh\n$ echo first \\\n>   second\nprintf '%s' '$ unchanged'\n```"
        [snippet] = extract_snippets([entry(text, 0, 0)])
        self.assertEqual(
            snippet.raw, "echo first \\\n  second\nprintf '%s' '$ unchanged'"
        )

    def test_multiline_preserved(self) -> None:
        body = "docker run \\\n  --name 'my app' \\\n\t-e KEY=\"a b\" image\n\nprintf '%s\\n' \"$HOME\""
        for after in ("", "\nDone.", "\n"):
            with self.subTest(after=after):
                [snippet] = extract_snippets(
                    [entry(f"Build it:\n```bash\n{body}\n```{after}", 0, 0)]
                )
                self.assertEqual(snippet.raw, body)
                self.assertEqual(snippet.display, "docker run \\")
        long = "echo " + "x" * 400
        [wide] = extract_snippets([entry(f"```sh\n{long}\n```", 0, 0)])
        self.assertEqual(wide.raw, long)
        self.assertLess(len(wide.display), len(long))
        self.assertTrue(wide.display.startswith("echo x"))
        self.assertTrue(wide.display.endswith(("…", "...")))
        [wider] = extract_snippets([entry(f"```sh\necho {'x' * 4000}\n```", 0, 0)])
        self.assertEqual(wider.display, wide.display)
        control = "printf 'a\tb' \x1b[31mred"
        [colored] = extract_snippets([entry(f"```zsh\n{control}\n```", 0, 0)])
        self.assertEqual(colored.raw, control)
        self.assertNotIn("\x1b", colored.display)
        self.assertNotIn("\t", colored.display)
        self.assertTrue(colored.display.startswith("printf 'a b'"))

    def test_stable_ranking(self) -> None:
        older = "Expected:\n$ old plain\nRun this:\n```console\n$ old cue\n```\n```bash\nold shell\n```"
        newer_a = "Expected:\n$ new plain\n```sh\nnew shell a\n```\n```fish\nnew shell a2\n```"
        newer_b = "```zsh\nnew shell b\n```\nRun this:\n$ new cue"
        entries = [entry(older, 1, 0), entry(newer_b, 0, 2), entry(newer_a, 0, 1)]
        expected = [
            (0, 0, "new shell a"),
            (0, 0, "new shell a2"),
            (0, 0, "new shell b"),
            (0, 1, "old shell"),
            (1, 0, "new cue"),
            (1, 1, "old cue"),
            (2, 0, "new plain"),
            (2, 1, "old plain"),
        ]
        newest_in_text = [
            "new plain",
            "new shell a",
            "new shell a2",
            "new shell b",
            "new cue",
        ]
        oldest_in_text = ["old plain", "old cue", "old shell"]
        for order in (entries, entries[::-1]):
            with self.subTest(first=order[0].message_index):
                found = extract_snippets(order)
                self.assertEqual(ranked(found), expected)
                keys = [
                    (snippet.rank_tier, snippet.message_index, snippet.source_order)
                    for snippet in found
                ]
                self.assertEqual(keys, sorted(keys))
                self.assertEqual(len({snippet.id for snippet in found}), len(expected))
                orders = {snippet.raw: snippet.source_order for snippet in found}
                for text_order in (newest_in_text, oldest_in_text):
                    values = [orders[raw] for raw in text_order]
                    self.assertEqual(values, sorted(set(values)))


if __name__ == "__main__":
    unittest.main()
