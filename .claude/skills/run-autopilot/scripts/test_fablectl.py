"""Tests for fablectl.py.

Stdlib-only unittest, subprocess pattern (matches test_statectl.py).
Runs under both `python3 test_fablectl.py` and `python3 -m pytest test_fablectl.py`.

fablectl.py is the sole writer of the Fable rescue ledger, invoked as:

    python3 fablectl.py <ledger> request <prd> <task_id> <task_name> <batch_id> <json>
    python3 fablectl.py <ledger> decide  <prd> approved|rejected
    python3 fablectl.py <ledger> consume <prd>
    python3 fablectl.py <ledger> show    <prd>

These tests bind the public contract only - the one-request-per-PRD latch, the
transition table, and the exit codes callers branch on (0 ok, 1 usage, 2 corrupt
ledger, 3 refused) - by running the CLI as a subprocess and asserting on exit
codes and file bytes, never on internals.

The file also carries the Fable documentation contract (`FableTierEnumerationTest`,
`WorkSkillFableContractTest` and `WorkSkillExploitRejectionTest` at the bottom): an
approved rescue is worthless if the tier tables `/work` routes from forget the
rescue rung exists.
"""

import datetime
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

FABLECTL = Path(__file__).parent / "fablectl.py"

PRD = "00076-route-builds-sonnet-first-with-fable-rescue-v1.md"
PRD_B = "00077-consume-the-fable-approval-v1.md"
PRD_C = "00078-park-on-fable-rejection-v1.md"

TASK_ID = "task-uuid-8"
TASK_NAME = "Wire approval consumption"
BATCH_ID = "202607202320"
JUSTIFICATION = {
    "problem": "the task could not wire approval consumption",
    "attempts": "haiku(2) -> sonnet(2) -> opus(2), last outcome rework_failed",
    "impact": "fable rescue never fires and the PRD stays parked",
}
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
ENTRY_FIELDS = {
    "status",
    "task_id",
    "task_name",
    "requested_at",
    "batch_id",
    "justification",
    "decided_at",
    "consumed_at",
}


class FablectlTest(unittest.TestCase):
    def setUp(self) -> None:
        # python3 itself exits 2 on a missing script, so without this guard the
        # exit-2 assertions below would pass with no fablectl.py at all.
        self.assertTrue(FABLECTL.exists(), f"missing unit under test: {FABLECTL}")
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.json"
        self.bak = Path(str(self.ledger) + ".bak")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(
        self, *args: str, ledger: Path | None = None
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(FABLECTL), str(ledger or self.ledger), *args],
            capture_output=True,
            text=True,
        )

    def request(
        self,
        prd: str = PRD,
        ledger: Path | None = None,
        justification: str | None = None,
    ) -> subprocess.CompletedProcess:
        return self.run_cli(
            "request",
            prd,
            TASK_ID,
            TASK_NAME,
            BATCH_ID,
            json.dumps(JUSTIFICATION) if justification is None else justification,
            ledger=ledger,
        )

    def make_entry(
        self, status: str, prd: str = PRD, ledger: Path | None = None
    ) -> None:
        """Drive the CLI until PRD's entry sits at `status`."""
        steps = {
            "requested": [],
            "approved": [("decide", "approved")],
            "rejected": [("decide", "rejected")],
            "consumed": [("decide", "approved"), ("consume",)],
        }[status]
        first = self.request(prd, ledger=ledger)
        self.assertEqual(first.returncode, 0, f"seeding {status}: request failed")
        for step in steps:
            result = self.run_cli(step[0], prd, *step[1:], ledger=ledger)
            self.assertEqual(result.returncode, 0, f"seeding {status}: {step} failed")

    def load_entry(self, prd: str = PRD, ledger: Path | None = None) -> dict:
        return json.loads((ledger or self.ledger).read_text())[prd]

    def read_or_none(self, path: Path) -> bytes | None:
        return path.read_bytes() if path.exists() else None

    def age_stamp(self, field: str, value: str) -> None:
        """Backdate a stamp on disk, so a value copied forward is detectable."""
        ledger = json.loads(self.ledger.read_text())
        ledger[PRD][field] = value
        self.ledger.write_text(json.dumps(ledger))

    def assert_stamp(self, value: object, label: str) -> datetime.datetime:
        self.assertIsInstance(value, str, f"{label} must be a string")
        try:
            stamp = datetime.datetime.strptime(value, TS_FORMAT)
        except ValueError:
            self.fail(f"{label}={value!r} is not {TS_FORMAT}")
        # A frozen literal of the right shape is not a timestamp. The value has
        # to come off the clock, so pin it near now - 120s is generous enough
        # that a slow machine cannot flake it, tight enough that a constant dies.
        now = datetime.datetime.now(datetime.timezone.utc)
        drift = abs(stamp.replace(tzinfo=datetime.timezone.utc) - now)
        self.assertLessEqual(
            drift.total_seconds(),
            120,
            f"{label}={value!r} is not derived from the clock (now={now:{TS_FORMAT}})",
        )
        return stamp

    # 1. request: absent-file tolerance and the entry shape --------------------

    def test_request_creates_ledger_and_entry_with_requested_status(self) -> None:
        result = self.request()
        self.assertEqual(result.returncode, 0, result.stderr)
        ledger = json.loads(self.ledger.read_text())
        self.assertEqual(list(ledger), [PRD])
        entry = ledger[PRD]
        self.assertEqual(set(entry), ENTRY_FIELDS)
        self.assertEqual(entry["status"], "requested")
        self.assertEqual(entry["task_id"], TASK_ID)
        self.assertEqual(entry["task_name"], TASK_NAME)
        self.assertEqual(entry["batch_id"], BATCH_ID)
        self.assertEqual(entry["justification"], JUSTIFICATION)
        self.assertIsNone(entry["decided_at"])
        self.assertIsNone(entry["consumed_at"])
        self.assert_stamp(entry["requested_at"], "requested_at")

    def test_request_creates_missing_parent_directory(self) -> None:
        nested = Path(self.tmp.name) / "state" / "fable" / "ledger.json"
        result = self.request(ledger=nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.load_entry(ledger=nested)["status"], "requested")

    # 2. the latch: one request per PRD, ever ----------------------------------

    def test_second_request_for_same_prd_exits_3_whatever_the_status(self) -> None:
        # The safety property. A second request must be refused from EVERY state,
        # including the terminal ones, and must not touch the ledger or its backup.
        for status in ("requested", "approved", "rejected", "consumed"):
            with self.subTest(status=status):
                ledger = Path(self.tmp.name) / f"latch_{status}.json"
                bak = Path(str(ledger) + ".bak")
                self.make_entry(status, ledger=ledger)
                before, before_bak = ledger.read_bytes(), self.read_or_none(bak)
                result = self.request(ledger=ledger)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(ledger.read_bytes(), before)
                self.assertEqual(self.read_or_none(bak), before_bak)
                self.assertEqual(self.load_entry(ledger=ledger)["status"], status)

    def test_request_for_a_second_prd_lands_alongside_the_first(self) -> None:
        # The latch is per-PRD, not a global one-request-ever kill switch. The
        # second request carries values that share nothing with the module
        # constants, so each entry must be built from ITS OWN argv - canned
        # literals cannot satisfy both.
        other_task_id = "task-uuid-19"
        other_task_name = "Park the PRD when the verdict is rejected"
        other_batch_id = "202607221030"
        other_justification = {
            "problem": "the parking hand-off never fired",
            "attempts": "sonnet(1) -> opus(3), last outcome review_failed",
            "impact": "one blocked PRD stalls the rest of the batch",
        }
        self.assertEqual(self.request(PRD).returncode, 0)
        second = self.run_cli(
            "request",
            PRD_B,
            other_task_id,
            other_task_name,
            other_batch_id,
            json.dumps(other_justification),
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        ledger = json.loads(self.ledger.read_text())
        self.assertEqual(sorted(ledger), sorted([PRD, PRD_B]))
        self.assertEqual(ledger[PRD]["status"], "requested")
        self.assertEqual(ledger[PRD_B]["status"], "requested")
        self.assertEqual(ledger[PRD]["task_id"], TASK_ID)
        self.assertEqual(ledger[PRD]["task_name"], TASK_NAME)
        self.assertEqual(ledger[PRD]["batch_id"], BATCH_ID)
        self.assertEqual(ledger[PRD]["justification"], JUSTIFICATION)
        self.assertEqual(ledger[PRD_B]["task_id"], other_task_id)
        self.assertEqual(ledger[PRD_B]["task_name"], other_task_name)
        self.assertEqual(ledger[PRD_B]["batch_id"], other_batch_id)
        self.assertEqual(ledger[PRD_B]["justification"], other_justification)
        self.assertNotEqual(
            ledger[PRD]["justification"], ledger[PRD_B]["justification"]
        )

    # 3. decide: only out of "requested" ---------------------------------------

    def test_decide_records_the_verdict_and_stamps_decided_at(self) -> None:
        for status in ("approved", "rejected"):
            with self.subTest(status=status):
                ledger = Path(self.tmp.name) / f"decide_{status}.json"
                self.make_entry("requested", ledger=ledger)
                requested_at = self.load_entry(ledger=ledger)["requested_at"]
                result = self.run_cli("decide", PRD, status, ledger=ledger)
                self.assertEqual(result.returncode, 0, result.stderr)
                entry = self.load_entry(ledger=ledger)
                self.assertEqual(entry["status"], status)
                self.assert_stamp(entry["decided_at"], "decided_at")
                self.assertIsNone(entry["consumed_at"])
                # The rest of the entry survives the mutation untouched.
                self.assertEqual(entry["requested_at"], requested_at)
                self.assertEqual(entry["task_id"], TASK_ID)
                self.assertEqual(entry["justification"], JUSTIFICATION)

    def test_decide_on_a_non_requested_entry_exits_3(self) -> None:
        # approved -> approved, and anything out of the terminal rejected and
        # consumed states, is outside the transition table; the ledger must come
        # out unchanged.
        for status in ("approved", "rejected", "consumed"):
            with self.subTest(status=status):
                ledger = Path(self.tmp.name) / f"redecide_{status}.json"
                self.make_entry(status, ledger=ledger)
                before = ledger.read_bytes()
                result = self.run_cli("decide", PRD, "approved", ledger=ledger)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(ledger.read_bytes(), before)

    def test_decide_on_a_missing_entry_exits_3(self) -> None:
        absent = self.run_cli("decide", PRD, "approved")
        self.assertEqual(absent.returncode, 3)
        self.assertFalse(self.ledger.exists())
        self.assertEqual(self.request(PRD_B).returncode, 0)
        before = self.ledger.read_bytes()
        missing_key = self.run_cli("decide", PRD, "approved")
        self.assertEqual(missing_key.returncode, 3)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_decide_with_an_unknown_status_exits_1(self) -> None:
        self.make_entry("requested")
        before = self.ledger.read_bytes()
        # "approved" and "rejected" are an allowlist, not a blacklist of the
        # strings this test happens to try: arbitrary words, the empty string
        # and a near-miss with trailing whitespace must all be refused.
        bad_statuses = (
            "consumed",
            "requested",
            "APPROVED",
            "yes",
            "banana",
            "",
            "approved ",
            " rejected",
        )
        for bad in bad_statuses:
            with self.subTest(status=bad):
                result = self.run_cli("decide", PRD, bad)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(self.ledger.read_bytes(), before)
                self.assertEqual(self.load_entry()["status"], "requested")

    def test_decide_and_consume_stamp_from_the_clock_not_a_copied_stamp(self) -> None:
        # Every step of a normal run lands milliseconds apart, so copying the
        # previous stamp forward is invisible - and both values pass a freshness
        # window. Backdate the earlier stamp on disk first: a copy then lands in
        # 2020 and dies, while a real clock read stays fresh.
        aged = "2020-01-01T00:00:00Z"
        self.make_entry("requested")
        self.age_stamp("requested_at", aged)
        self.assertEqual(self.run_cli("decide", PRD, "approved").returncode, 0)
        entry = self.load_entry()
        self.assertNotEqual(entry["decided_at"], aged, "decided_at copied forward")
        self.assert_stamp(entry["decided_at"], "decided_at")
        # ... and the older stamp is carried through verbatim, not restamped.
        self.assertEqual(entry["requested_at"], aged)
        self.age_stamp("decided_at", aged)
        self.assertEqual(self.run_cli("consume", PRD).returncode, 0)
        entry = self.load_entry()
        self.assertNotEqual(entry["consumed_at"], aged, "consumed_at copied forward")
        self.assert_stamp(entry["consumed_at"], "consumed_at")
        self.assertEqual(entry["decided_at"], aged)

    # 4. consume: one approval, one spend --------------------------------------

    def test_consume_after_approval_stamps_consumed_at(self) -> None:
        self.make_entry("approved")
        decided_at = self.load_entry()["decided_at"]
        result = self.run_cli("consume", PRD)
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = self.load_entry()
        self.assertEqual(entry["status"], "consumed")
        self.assertEqual(entry["decided_at"], decided_at)
        self.assertEqual(entry["justification"], JUSTIFICATION)
        # The three stamps are a lifecycle, not three copies of one literal.
        requested = self.assert_stamp(entry["requested_at"], "requested_at")
        decided = self.assert_stamp(entry["decided_at"], "decided_at")
        consumed = self.assert_stamp(entry["consumed_at"], "consumed_at")
        self.assertLessEqual(requested, decided, "requested_at is after decided_at")
        self.assertLessEqual(decided, consumed, "decided_at is after consumed_at")

    def test_second_consume_exits_3_and_leaves_file_unchanged(self) -> None:
        # Exactly one spend per approval, ever.
        self.make_entry("consumed")
        before = self.ledger.read_bytes()
        result = self.run_cli("consume", PRD)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(self.load_entry()["status"], "consumed")

    def test_consume_on_a_non_approved_entry_exits_3(self) -> None:
        for status in ("requested", "rejected"):
            with self.subTest(status=status):
                ledger = Path(self.tmp.name) / f"consume_{status}.json"
                self.make_entry(status, ledger=ledger)
                before = ledger.read_bytes()
                result = self.run_cli("consume", PRD, ledger=ledger)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(ledger.read_bytes(), before)
                self.assertEqual(self.load_entry(ledger=ledger)["status"], status)
        absent = self.run_cli("consume", PRD_C)
        self.assertEqual(absent.returncode, 3)
        self.assertFalse(self.ledger.exists())

    # 5. show: read-only, absence is not an error ------------------------------

    def test_show_returns_empty_object_for_absent_file_and_absent_key(self) -> None:
        absent_file = self.run_cli("show", PRD)
        self.assertEqual(absent_file.returncode, 0, absent_file.stderr)
        self.assertEqual(json.loads(absent_file.stdout), {})
        self.assertFalse(self.ledger.exists())
        self.assertEqual(self.request(PRD_B).returncode, 0)
        absent_key = self.run_cli("show", PRD)
        self.assertEqual(absent_key.returncode, 0, absent_key.stderr)
        self.assertEqual(json.loads(absent_key.stdout), {})

    def test_show_prints_the_entry_and_writes_nothing(self) -> None:
        self.make_entry("approved")
        before, before_bak = self.ledger.read_bytes(), self.read_or_none(self.bak)
        result = self.run_cli("show", PRD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.load_entry())
        self.assertEqual(json.loads(result.stdout)["status"], "approved")
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(self.read_or_none(self.bak), before_bak)

    def test_a_bare_prd_number_is_not_a_ledger_key(self) -> None:
        # Keys match exactly; a "00076" prefix must never resolve to the entry,
        # or an approval could be spent against the wrong PRD.
        self.make_entry("approved")
        shown = self.run_cli("show", "00076")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout), {})
        consumed = self.run_cli("consume", "00076")
        self.assertEqual(consumed.returncode, 3)
        self.assertEqual(self.load_entry()["status"], "approved")

    # 6. corrupt ledger: exit 2, never rewritten -------------------------------

    def test_corrupt_ledger_exits_2_and_leaves_file_byte_identical(self) -> None:
        # Damage has many shapes; sniffing for one marker is not detection.
        # An EMPTY file is not an ABSENT file, and valid JSON that is not an
        # object is not a ledger - both are damage, so both are 2. Never 1:
        # callers read 1 as "I called it wrong" and would retry differently.
        corruptions = {
            "trailing commas": b'{"' + PRD.encode() + b'": {"status": "x",,,}',
            "truncated": b'{"' + PRD.encode() + b'": {"status": "approved"',
            "empty file": b"",
            "top-level array": b'[{"status": "approved"}]',
            "top-level scalar": b"42",
            "non-utf8 bytes": b"\xff\xfe{\x00s\x00t\x00}",
            # Damage inside an entry is damage too. Letting these traceback out
            # as 1 tells the caller it called wrong, when the truth is that the
            # ledger is broken and no retry will help.
            "entry is a string": json.dumps({PRD: "approved"}).encode(),
            "entry has no status": json.dumps({PRD: {"task_id": TASK_ID}}).encode(),
            "status is not a string": json.dumps({PRD: {"status": 7}}).encode(),
        }
        verbs = {
            "request": None,
            "decide": ("decide", PRD, "approved"),
            "consume": ("consume", PRD),
            # show is read-only, not exempt: answering {} on an unreadable
            # ledger would report "no request exists" for one that may hold one.
            "show": ("show", PRD),
        }
        for shape, corrupt in corruptions.items():
            for name, args in verbs.items():
                with self.subTest(corruption=shape, verb=name):
                    self.ledger.write_bytes(corrupt)
                    result = self.request() if args is None else self.run_cli(*args)
                    self.assertEqual(result.returncode, 2)
                    self.assertTrue(result.stderr.strip())
                    self.assertEqual(self.ledger.read_bytes(), corrupt)

    def test_out_of_enum_status_exits_2_and_names_ledger_prd_and_status(self) -> None:
        # A string status outside the four legal values is corrupt state, not a
        # valid latch: `apply_verb` must never see it, or a garbage status could
        # silently refuse or allow a mutation. Distinct from the "not a string"
        # corruption above; must be caught for every verb that reads the ledger,
        # `show` included, with a message naming the ledger, the PRD key, AND
        # the offending status value.
        bad_status = "foo"
        corrupt = json.dumps(
            {PRD: {"status": bad_status, "task_id": TASK_ID}}
        ).encode()
        verbs = {
            "request": None,
            "decide": ("decide", PRD, "approved"),
            "consume": ("consume", PRD),
            "show": ("show", PRD),
        }
        for name, args in verbs.items():
            with self.subTest(verb=name):
                self.ledger.write_bytes(corrupt)
                result = self.request() if args is None else self.run_cli(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(str(self.ledger), result.stderr)
                self.assertIn(PRD, result.stderr)
                self.assertIn(bad_status, result.stderr)
                self.assertEqual(self.ledger.read_bytes(), corrupt)

    def test_os_error_exits_4_with_one_line_diagnostic_and_no_traceback(self) -> None:
        # A NotADirectoryError (or any other OS error beyond a plain missing
        # file) must not read as "bad argument" (1), and must not traceback out
        # unhandled: a disk/permission failure needs its own exit code and a
        # caller-readable one-line diagnostic, not a Python stack dump.
        blocker = Path(self.tmp.name) / "afile"
        blocker.write_text("not a directory")
        bad_ledger = blocker / "sub" / "ledger.json"
        result = self.run_cli("decide", PRD, "approved", ledger=bad_ledger)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertNotIn("Traceback (most recent call last)", result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_refused_decide_and_consume_create_no_droppings(self) -> None:
        # decide/consume against an absent ledger correctly refuse (exit 3),
        # but must not leave a stray parent directory or `.lock` file behind
        # when there is nothing to mutate. `request` against an absent ledger
        # is the legitimate case and must still create both, so an
        # implementation that never creates anything for any verb cannot pass
        # this test by doing nothing.
        nested = Path(self.tmp.name) / "state" / "fable" / "ledger.json"
        lock = Path(f"{nested}.lock")
        for args in (("decide", PRD, "approved"), ("consume", PRD)):
            with self.subTest(verb=args[0]):
                result = self.run_cli(*args, ledger=nested)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertFalse(
                    nested.parent.exists(), "refusal must not create the parent dir"
                )
                self.assertFalse(
                    lock.exists(), "refusal must not create the lock file"
                )
        legit = self.request(ledger=nested)
        self.assertEqual(legit.returncode, 0, legit.stderr)
        self.assertTrue(nested.parent.exists())
        self.assertTrue(nested.exists())
        self.assertTrue(lock.exists())

    # 7. usage errors ----------------------------------------------------------

    def test_invalid_justification_exits_1(self) -> None:
        bad = [
            json.dumps({k: v for k, v in JUSTIFICATION.items() if k != drop})
            for drop in JUSTIFICATION
        ]
        bad += [
            # Right size, wrong names: the three keys are checked by NAME, so
            # counting them is not enough.
            json.dumps({"a": 1, "b": 2, "c": 3}),
            # The three fields are one-line prose, so a non-string is a bad
            # argument at the boundary, present key or not.
            json.dumps(dict(JUSTIFICATION, problem=None)),
            json.dumps(dict(JUSTIFICATION, attempts=[])),
            json.dumps(dict(JUSTIFICATION, impact={})),
            json.dumps([JUSTIFICATION]),
            json.dumps("problem"),
            "{not json",
        ]
        for justification in bad:
            with self.subTest(justification=justification):
                result = self.request(justification=justification)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(self.ledger.exists())

    def test_justification_with_an_extra_key_is_accepted(self) -> None:
        # Three REQUIRED keys, not three permitted ones: an unknown extra key
        # is legal and must not be rejected.
        extended = dict(JUSTIFICATION, reviewer="blake")
        result = self.request(justification=json.dumps(extended))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.load_entry()["justification"], extended)

    def test_unknown_verb_and_missing_arguments_exit_1(self) -> None:
        invocations = [
            (),
            ("approve", PRD),
            ("request",),
            ("request", PRD, TASK_ID, TASK_NAME, BATCH_ID),
            ("decide", PRD),
            ("consume",),
            ("show",),
        ]
        for args in invocations:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(self.ledger.exists())

    def test_a_blank_prd_argument_exits_1(self) -> None:
        # A blank is a bad argument, not a ledger key. An entry filed under ""
        # or under spaces is one the per-PRD latch can never match again.
        for blank in ("", "   ", "\t"):
            invocations = [
                (
                    "request",
                    blank,
                    TASK_ID,
                    TASK_NAME,
                    BATCH_ID,
                    json.dumps(JUSTIFICATION),
                ),
                ("decide", blank, "approved"),
                ("consume", blank),
                ("show", blank),
            ]
            for args in invocations:
                with self.subTest(prd=repr(blank), verb=args[0]):
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse(self.ledger.exists())

    # 8. rotating backup and restore -------------------------------------------

    def test_backup_holds_pre_mutation_bytes_and_restore_recovers_status(self) -> None:
        # request is a mutation too. Writing a PRD into a POPULATED ledger must
        # back up the previous bytes first, or the entries already in the file
        # are unrecoverable the moment a new request lands.
        self.assertEqual(self.request(PRD_B).returncode, 0)
        seeded = self.ledger.read_bytes()
        self.assertEqual(self.request(PRD).returncode, 0)
        self.assertTrue(self.bak.exists())
        self.assertEqual(self.bak.read_bytes(), seeded)
        after_request = self.ledger.read_bytes()
        self.assertEqual(self.run_cli("decide", PRD, "approved").returncode, 0)
        self.assertTrue(self.bak.exists())
        self.assertEqual(self.bak.read_bytes(), after_request)
        self.assertEqual(self.load_entry()["status"], "approved")
        # One rotating backup: the 2nd mutation's .bak holds the 1st's result.
        after_decide = self.ledger.read_bytes()
        self.assertEqual(self.run_cli("consume", PRD).returncode, 0)
        self.assertEqual(self.bak.read_bytes(), after_decide)
        # Restoring is a plain move, and it brings back the prior status.
        self.bak.replace(self.ledger)
        restored = self.run_cli("show", PRD)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(json.loads(restored.stdout)["status"], "approved")
        self.assertIsNone(json.loads(restored.stdout)["consumed_at"])

    # 9. concurrent requests for different PRDs both land ----------------------

    def test_two_concurrent_requests_for_different_prds_both_land(self) -> None:
        # A single race is a FLAKY guard: a lock-free impl false-passes most of
        # the time because spawn overhead usually serializes the two writers by
        # luck. Repeat on a FRESH ledger each round so a missing lock loses a
        # write within a few iterations; a locked impl survives all of them.
        for i in range(25):
            ledger = Path(self.tmp.name) / f"race_{i}.json"
            seed = self.request(PRD_C, ledger=ledger)
            self.assertEqual(seed.returncode, 0, f"iteration {i}: seed failed")
            # Start BOTH processes before waiting on either, so they truly race.
            procs = [
                subprocess.Popen(
                    [
                        "python3",
                        str(FABLECTL),
                        str(ledger),
                        "request",
                        prd,
                        TASK_ID,
                        TASK_NAME,
                        BATCH_ID,
                        json.dumps(JUSTIFICATION),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for prd in (PRD, PRD_B)
            ]
            for proc in procs:
                proc.wait()
            for proc in procs:
                self.assertEqual(proc.returncode, 0, f"iteration {i}: nonzero exit")
            # Must still parse: json.loads raises (failing the test) if not.
            entries = json.loads(ledger.read_text())
            self.assertEqual(
                sorted(entries),
                sorted([PRD, PRD_B, PRD_C]),
                f"iteration {i}: lost a write",
            )


# ---------------------------------------------------------------------------
# Fable documentation contract
#
# `fable` is a real model tier - the human-gated rescue rung above `opus`. The
# three files below are the tier tables `/work` routes, stamps, and gates from.
# Every tier enumeration in them that names haiku, sonnet and opus together must
# also name fable, or a future edit silently drops the rescue rung out of a
# routing / pipeline / gate table and a rescued task is mis-handled.
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
WORK_SKILL = SKILLS_DIR / "work" / "SKILL.md"
STATE_SCHEMA = SKILLS_DIR / "run-autopilot" / "references" / "state-schema.md"
MODEL_LADDER = SKILLS_DIR / "run-autopilot" / "references" / "model-ladder.md"
TIER_TABLE_FILES = (WORK_SKILL, STATE_SCHEMA, MODEL_LADDER)

# One line at a time: "names all three tiers", and the same with "and does not
# name fable" - the offending shape.
TIER_ENUM = re.compile(r"(?=.*haiku)(?=.*sonnet)(?=.*opus)", re.I)
MISSING_FABLE = re.compile(r"(?=.*haiku)(?=.*sonnet)(?=.*opus)(?!.*fable)", re.I)

# An escalation chain (`haiku -> sonnet -> opus`) is a LADDER WALK, not a tier
# enumeration: `fable` is never auto-escalatable, so its absence there IS the
# contract. Blanking chains before the enumeration test states that as a rule
# instead of as a per-file exemption a re-wording could launder.
CHAIN = re.compile(r"(?:`?[\w-]+`?\s*(?:->|→)\s*)+`?[\w-]+`?")

COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Lines that name all three tiers and must STAY fable-free: adding `fable` to
# one of these would be a real defect, not a fix. Each row is (file, short
# distinctive substring, why). Keep this table small - a growing exemption list
# means the rule is wrong, not that the docs are special.
EXEMPTIONS = (
    (
        MODEL_LADDER,
        "Claude rungs (haiku / sonnet / opus)",
        "§ Per-rung budgets: `fable` has its OWN budget row (1 dispatch per PRD, "
        "ever), so it is not a Claude rung in this sense",
    ),
    (
        MODEL_LADDER,
        "`haiku -> sonnet -> opus`",
        "§ Capability ladders edge list: `fable` is never auto-escalatable, so "
        "its absence from the ladder IS the contract (the human gate)",
    ),
    (
        MODEL_LADDER,
        "A non-qwen `haiku` task:",
        "§ Per-rung budgets worst-case example: a ladder-walk narrative, not an "
        "enumeration (wrapped over two lines today, so this row only bites if "
        "the bullet is ever re-wrapped onto one)",
    ),
    (
        STATE_SCHEMA,
        "haiku(2) -> sonnet(2) -> opus(2)",
        "the rung-history example (JSON block and the `justification` row): it "
        "records what exhausted BEFORE a rescue is requested, so it must never "
        "gain `fable`",
    ),
)


def _section(lines: list[str], heading: str) -> list[tuple[int, str]]:
    """1-based (lineno, text) for the body of the `heading` section."""
    body: list[tuple[int, str]] = []
    inside = False
    for number, text in enumerate(lines, 1):
        if text.startswith(heading):
            inside = True
            continue
        if inside:
            if text.startswith("## ") or text.startswith("### "):
                break
            body.append((number, text))
    return body


def _cite(path: Path, number: int, text: str) -> str:
    return f"  {path}:{number}: {' '.join(text.split())[:140]}"


def _strip_comments(text: str) -> str:
    """Blank out `<!-- ... -->`, keeping every newline so line numbers survive.

    An HTML comment is invisible in the rendered doc, so it can never satisfy a
    contract - and stripping it must not shift the `file:line` a failure cites.
    """
    return COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


Hit = namedtuple("Hit", "line text start end")


class Flow:
    """A run of lines JOINED into one string, with a line number per offset.

    Pinned contracts are matched against this, not against single lines: a
    hard wrap in the middle of a mapping must not hide it from the scan.
    """

    def __init__(self, path: Path, rows: list[tuple[int, str]]) -> None:
        self.path = path
        self.rows = rows
        pieces: list[str] = []
        index: list[int] = []
        for number, text in rows:
            piece = " ".join(text.split())
            pieces.append(piece)
            index.extend([number] * (len(piece) + 1))
        self.text = " ".join(pieces)
        self.index = index or [0]

    @property
    def head(self) -> int:
        return self.rows[0][0] if self.rows else 0

    def find(self, pattern: re.Pattern) -> list[Hit]:
        return [
            Hit(self.index[match.start()], match.group(0), match.start(), match.end())
            for match in pattern.finditer(self.text)
        ]

    def window(self, hit: Hit, radius: int) -> str:
        return self.text[max(0, hit.start - radius) : hit.end + radius]


class Doc:
    """A tier-table file, comment-stripped, addressable by line or by section."""

    def __init__(self, path: Path, text: str | None = None) -> None:
        self.path = path
        source = path.read_text() if text is None else text
        self.lines = _strip_comments(source).splitlines()

    def section(self, heading: str) -> list[tuple[int, str]]:
        return _section(self.lines, heading)

    def flow(self, *headings: str) -> Flow:
        rows: list[tuple[int, str]] = []
        for heading in headings:
            rows.extend(self.section(heading))
        return Flow(self.path, rows)

    def whole(self) -> Flow:
        return Flow(self.path, list(enumerate(self.lines, 1)))


# --- the pinned sites -------------------------------------------------------
#
# Every check below returns a list of problem strings (empty = the contract
# holds) and takes the Doc as a parameter, so the same code runs against the
# real file and against the exploit fixtures at the bottom.

PINNED_SECTIONS = (
    "## Per-task model dispatch",
    "## Attempt logging",
    "### 2.85.",
    "### 3.",
    "### 5.5.",
    "### 5.7.",
    "### 6.",
)
PIPELINE_SECTIONS = ("## Attempt logging", "### 6.")
ROUTING_SECTIONS = ("## Per-task model dispatch", "### 3.")
ESCALATION_SECTION = "### 5.5."

# A mapping is a PAIR. `fable` on the same line as `"full"` proves nothing when
# `opus -> "full"` sits later in the same sentence, so the arrow has to be
# between the two halves - and no OTHER arrow may sit in the gap.
GAP = r"(?:(?!->|→)[^|\n]){0,30}"
FABLE_FULL = re.compile(rf"`?fable`?{GAP}(?:->|→)\s*`?\"full\"`?", re.I)
FABLE_SHALLOW = re.compile(rf"`?fable`?{GAP}(?:->|→)\s*`?\"(?:minimal|lean)\"`?", re.I)
ANY_PIPELINE_MAP = re.compile(r"(?:->|→)\s*`?\"(?:minimal|lean|full)\"", re.I)

# A negator between the two halves flips the sentence, so the gap may not hold
# one: `fable` DOES NOT override the table is not a statement that it does.
CLEAN_GAP = r"(?:(?!\b(?:not|never|neither|nor)\b)[^.]){0,120}?"
OVERRIDES = (
    re.compile(rf"`?fable`?{CLEAN_GAP}\boverrid(?:e|es|ing)\b", re.I),
    re.compile(rf"\boverrid(?:e|es|ing)\b{CLEAN_GAP}`?fable`?", re.I),
)
SESSION_MODEL = (
    re.compile(r"`?fable`?[^.]{0,120}?\bnever\b[^.]{0,80}?session model", re.I),
    re.compile(r"\bnever\b[^.]{0,80}?session model[^.]{0,120}?`?fable`?", re.I),
)

NEGATED_ACTION = re.compile(
    r"\b(?:skip|skips|skipped|no|not|never|without|omit|omits|bypass|bypasses)\b", re.I
)
DEVON_ACTION = re.compile(
    r"(?:dispatch\w*\s+devon|devon\s+(?:is\s+)?dispatch\w*)", re.I
)
REVIEW_ACTION = re.compile(r"\breview\b", re.I)

FOLDED_BUDGET = re.compile(r"claude rungs?\b.{0,80}?\b(?:2|two) dispatches", re.I)
FABLE_TWO_DISPATCHES = re.compile(
    r"`?fable`?[^.]{0,60}?\bgets?\s+(?:2|two) dispatches", re.I
)
FABLE_OWN_BUDGET = re.compile(
    r"`?fable`?[^.]{0,80}?\b(?:1|one)\s+(?:capability\s+)?dispatch per PRD", re.I
)
LADDER_FILE = "model-ladder.md"

# The exclusion words that make a `fable` mention on an escalation edge legal.
# NOT "gate" - § 5.5 says "gate failure" and "gate-output" everywhere.
EXCLUSION = re.compile(
    r"\b(?:never|not|human|approval|approved|exclude\w*|no rung above)\b", re.I
)
NO_RUNG_ABOVE = (
    re.compile(r"`?fable`?[^.]{0,80}?no rung above", re.I),
    re.compile(r"no rung above[^.]{0,80}?`?fable`?", re.I),
)

# Phrasings that DENY a contract. A `fable` mention that denies must fail, not
# pass: every one of these was appended to a real line to satisfy a scan that
# only asked whether the word appeared.
DENIALS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"not an accepted value",
        r"never write it",
        r"treat any task carrying it as",
        r"(?:does|do) not override",
        r"no (?:reviewer|devon) dispatch",
        r"nothing (?:in this step|here) changes",
        r"is not supported",
        r"not a (?:valid|real|supported) (?:tier|rung|value|model)",
        r"never a (?:valid|real|supported) (?:tier|rung|value|model)",
    )
)
DENIAL_RADIUS = 200

# The feedback-retry and REPAIR carve-outs at § 5.5 say "Claude rung(s)"
# without naming which tiers that means. `fable` is elsewhere mapped to
# "Claude Fable" as a model (the routing table), so the bare phrase reads as
# including it - handing a `fable` gate failure a second dispatch (retry) and
# a third (repair), which breaks the one-Fable-dispatch-per-PRD invariant.
# Each anchor pins the STABLE boilerplate around one carve-out and captures
# the qualifier phrase between it - the phrase a fix is expected to re-word.
FEEDBACK_RETRY_ANCHOR = re.compile(
    r"feedback retry:\s*dispatch ivan with the failure output,\s*same tier\s*"
    r"\((.*?)per the 1-dispatch budget\)",
    re.I,
)
REPAIR_VERDICT_ANCHOR = re.compile(
    r'verdict\s*"spec_gap"\s*\(exit 0\)\s*(?:->|→)\s*repair path below, if '
    r"repair unused this task and current rung is\s+(.*?)\s*\(qwen never repairs",
    re.I,
)
REPAIR_CONDITION_ANCHOR = re.compile(
    r"repair\s*\(spec_gap, repair not yet used this task,\s*(.*?)\):\s*"
    r"fill the identified",
    re.I,
)
RETRY_REPAIR_SITES = (
    ("feedback-retry gate", FEEDBACK_RETRY_ANCHOR),
    ("repair-diagnosis condition", REPAIR_VERDICT_ANCHOR),
    ("REPAIR gate condition", REPAIR_CONDITION_ANCHOR),
)

# `fable` must be NEGATED close to where it is named in the qualifier - not
# merely present somewhere in it. Without the tight window, a stray `never`/
# `no` belonging to the qwen carve-out several words away (same qualifier
# text on the feedback-retry site) would launder an unguarded `fable` grant.
FABLE_EXCLUDED = (
    re.compile(r"fable\b.{0,20}?\b(?:never|not|neither|nor|exclud\w*|except)\b", re.I),
    re.compile(r"\b(?:never|not|neither|nor|exclud\w*|except)\b.{0,20}?fable\b", re.I),
)


def check_line_enumerations(doc: Doc) -> list[str]:
    """Backstop: any ONE line naming all three Claude tiers also names fable."""
    exempt = [needle for source, needle, _ in EXEMPTIONS if source == doc.path]
    problems = []
    for number, text in enumerate(doc.lines, 1):
        if not MISSING_FABLE.match(text) or any(needle in text for needle in exempt):
            continue
        if not TIER_ENUM.match(CHAIN.sub(" ", text)):
            continue  # a ladder walk, not an enumeration
        problems.append(_cite(doc.path, number, text))
    return problems


def check_pinned_enumerations(doc: Doc) -> list[str]:
    """Wrap-proof: each pinned section, read as ONE joined string, names fable."""
    problems = []
    for heading in PINNED_SECTIONS:
        flow = doc.flow(heading)
        if not flow.rows:
            problems.append(f"  {doc.path}: no `{heading}` section - renamed?")
            continue
        enumerates = TIER_ENUM.match(CHAIN.sub(" ", flow.text))
        if enumerates and "fable" not in flow.text.lower():
            problems.append(
                _cite(
                    doc.path,
                    flow.head,
                    f"§ {heading} enumerates haiku/sonnet/opus and never names fable",
                )
            )
    return problems


def check_denials(doc: Doc) -> list[str]:
    """A `fable` mention that DENIES the contract must never satisfy it."""
    flow = doc.whole()
    problems = []
    for pattern in DENIALS:
        for hit in flow.find(pattern):
            if "fable" in flow.window(hit, DENIAL_RADIUS).lower():
                problems.append(
                    _cite(doc.path, hit.line, f"denies the rescue rung: {hit.text}")
                )
    return problems


def check_pipeline_mapping(doc: Doc) -> list[str]:
    """`fable` is PAIRED with `"full"` in every tier -> pipeline-depth mapping."""
    problems = []
    mapped = False
    for heading in PIPELINE_SECTIONS:
        flow = doc.flow(heading)
        if not ANY_PIPELINE_MAP.search(flow.text):
            continue
        mapped = True
        for hit in flow.find(FABLE_SHALLOW):
            problems.append(
                _cite(
                    doc.path,
                    hit.line,
                    f"§ {heading} maps the rescue rung SHALLOW: {hit.text}",
                )
            )
        if not flow.find(FABLE_FULL):
            problems.append(
                _cite(
                    doc.path,
                    flow.head,
                    f"§ {heading} maps tiers to pipeline depths but never pairs "
                    '`fable` -> `"full"`',
                )
            )
    if not mapped:
        problems.append(
            f"  {doc.path}: no tier -> pipeline-depth mapping left in "
            f"{list(PIPELINE_SECTIONS)} - deleted or renamed?"
        )
    return problems


def check_routing_override(doc: Doc) -> list[str]:
    flow = doc.flow(*ROUTING_SECTIONS)
    problems = []
    if not any(flow.find(pattern) for pattern in OVERRIDES):
        problems.append(
            f"  {doc.path}:{flow.head}: no sentence in "
            f"{list(ROUTING_SECTIONS)} says `fable` OVERRIDES the routing table"
        )
    if not any(flow.find(pattern) for pattern in SESSION_MODEL):
        problems.append(
            f"  {doc.path}:{flow.head}: no sentence in "
            f"{list(ROUTING_SECTIONS)} says `fable` is NEVER a session model"
        )
    return problems


def _fable_rows(rows: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """(lineno, subject, action) for table rows whose FIRST cell names fable."""
    found = []
    for number, text in rows:
        line = text.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        if "fable" in cells[0].lower():
            found.append((number, cells[0], cells[1]))
    return found


def check_gate_row(
    doc: Doc, heading: str, action: re.Pattern, otherwise: str
) -> list[str]:
    """The row that NAMES fable carries the positive action, in that same row."""
    rows = doc.section(heading)
    if not rows:
        return [f"  {doc.path}: no `{heading}` section - renamed?"]
    named = _fable_rows(rows)
    if not named:
        return [
            _cite(
                doc.path,
                rows[0][0],
                f"§ {heading} has NO table row naming `fable`, so it falls into "
                f"the catch-all row, which {otherwise}",
            )
        ]
    return [
        _cite(doc.path, number, f"the `{subject}` row's action is `{cell}`")
        for number, subject, cell in named
        if NEGATED_ACTION.search(cell) or not action.search(cell)
    ]


def check_devon_row(doc: Doc) -> list[str]:
    return check_gate_row(
        doc,
        "### 2.85.",
        DEVON_ACTION,
        "skips Devon - the rescue rung belongs with `opus` on the dispatch side",
    )


def check_review_row(doc: Doc) -> list[str]:
    return check_gate_row(
        doc,
        "### 5.7.",
        REVIEW_ACTION,
        "is not the reviewed side - only `haiku` skips the per-task review",
    )


def check_budget(doc: Doc) -> list[str]:
    """`fable` keeps its own budget: 1 dispatch per PRD, ever - never folded."""
    whole = doc.whole()
    problems = [
        _cite(
            doc.path,
            hit.line,
            f"`fable` folded into the Claude-rungs 2-dispatch group: {hit.text}",
        )
        for hit in whole.find(FOLDED_BUDGET)
        if "fable" in hit.text.lower()
    ]
    problems += [
        _cite(doc.path, hit.line, f"`fable` given a 2-dispatch budget: {hit.text}")
        for hit in whole.find(FABLE_TWO_DISPATCHES)
    ]
    flow = doc.flow(ESCALATION_SECTION)
    own = flow.find(FABLE_OWN_BUDGET)
    if not own:
        problems.append(
            f"  {doc.path}:{flow.head}: § {ESCALATION_SECTION} never gives `fable` "
            "its own budget (1 dispatch per PRD, ever)"
        )
    elif LADDER_FILE not in flow.window(own[0], 300):
        problems.append(
            _cite(
                doc.path,
                own[0].line,
                f"fable's budget is restated without citing {LADDER_FILE}: "
                f"{own[0].text}",
            )
        )
    return problems


def check_no_auto_escalation(doc: Doc) -> list[str]:
    """The rung-up computation never puts `fable` on an automatic edge."""
    flow = doc.flow(ESCALATION_SECTION)
    return [
        _cite(
            doc.path,
            hit.line,
            f"escalation chain puts `fable` on an automatic edge: {hit.text}",
        )
        for hit in flow.find(CHAIN)
        if "fable" in hit.text.lower()
        and not EXCLUSION.search(flow.window(hit, 120))
    ]


def check_no_rung_above(doc: Doc) -> list[str]:
    """The `no rung above` claim is pinned to `fable`, not to some other rung."""
    flow = doc.flow(ESCALATION_SECTION)
    if any(flow.find(pattern) for pattern in NO_RUNG_ABOVE):
        return []
    return [
        f"  {doc.path}:{flow.head}: § {ESCALATION_SECTION} never says, of `fable` "
        "itself, that it has no rung above it"
    ]


def check_retry_repair_excludes_fable(doc: Doc) -> list[str]:
    """The feedback-retry gate and both REPAIR gates name their tiers and
    explicitly exclude `fable` - a bare "Claude rung(s)" reads as including it
    (`fable` is elsewhere mapped to "Claude Fable" as a model), which would
    hand a `fable` gate failure a second dispatch (retry) and a third
    (repair).
    """
    flow = doc.flow(ESCALATION_SECTION)
    problems = []
    for label, anchor in RETRY_REPAIR_SITES:
        matches = list(anchor.finditer(flow.text))
        if not matches:
            problems.append(
                f"  {doc.path}: the {label} text was not found in § "
                f"{ESCALATION_SECTION} - re-worded, so this scan is blind there"
            )
            continue
        for match in matches:
            qualifier = match.group(1)
            line = flow.index[match.start(1)]
            if not TIER_ENUM.match(qualifier):
                problems.append(
                    _cite(
                        doc.path,
                        line,
                        f"{label} still says an unqualified `Claude rung(s)` "
                        f"instead of naming haiku/sonnet/opus: {qualifier.strip()}",
                    )
                )
                continue
            if "fable" not in qualifier.lower():
                problems.append(
                    _cite(
                        doc.path,
                        line,
                        f"{label} names haiku/sonnet/opus but never names "
                        f"`fable` to exclude it: {qualifier.strip()}",
                    )
                )
            elif not any(pattern.search(qualifier) for pattern in FABLE_EXCLUDED):
                problems.append(
                    _cite(
                        doc.path,
                        line,
                        f"{label} names `fable` without excluding it, granting "
                        f"it a retry/repair: {qualifier.strip()}",
                    )
                )
    return problems


WORK_SKILL_CHECKS = (
    ("line enumerations", check_line_enumerations),
    ("pinned enumerations", check_pinned_enumerations),
    ("denials", check_denials),
    ("routing override", check_routing_override),
    ("pipeline mapping", check_pipeline_mapping),
    ("Devon gate row", check_devon_row),
    ("review gate row", check_review_row),
    ("per-rung budget", check_budget),
    ("auto-escalation", check_no_auto_escalation),
    ("no rung above", check_no_rung_above),
    ("retry/repair fable exclusion", check_retry_repair_excludes_fable),
)


class FableTierEnumerationTest(unittest.TestCase):
    """Every tier enumeration in the tier tables names the rescue rung."""

    def setUp(self) -> None:
        self.docs = []
        for path in TIER_TABLE_FILES:
            self.assertTrue(path.exists(), f"missing tier-table file: {path}")
            doc = Doc(path)
            # Per-FILE positive control. An empty result is evidence of absence
            # only once the pattern is known to match something IN THAT FILE
            # (rules/tools.md: empty output is unverified, not confirmed-absent).
            # Controlling one file said nothing about the other two.
            self.assertTrue(
                any(TIER_ENUM.match(line) for line in doc.lines),
                f"the tier-enumeration pattern matches nothing in {path} - the "
                "scan is broken there, so its verdict on that file means nothing",
            )
            self.docs.append(doc)

    def test_fable_row_present_in_every_tier_enumeration(self) -> None:
        offenders = [
            problem for doc in self.docs for problem in check_line_enumerations(doc)
        ]
        if offenders:
            self.fail(
                "these lines enumerate haiku/sonnet/opus without naming `fable`, "
                "the human-gated rescue rung above `opus`:\n"
                + "\n".join(offenders)
                + "\nAdd `fable` to the enumeration. If naming it there would be "
                "WRONG (a Claude-rungs-only budget, a pre-rescue history), add a "
                "row to EXEMPTIONS with the reason instead. A ladder walk "
                "(`haiku -> sonnet -> opus`) needs no exemption - chains are "
                "blanked before this scan."
            )

    def test_pinned_sections_name_fable_even_when_rewrapped(self) -> None:
        # The per-line scan above dies to a hard wrap: split a mapping across two
        # lines and neither half names all three tiers. Each pinned section is
        # therefore also read as ONE joined string.
        offenders = check_pinned_enumerations(Doc(WORK_SKILL))
        if offenders:
            self.fail(
                "these sections enumerate the Claude tiers with no `fable` "
                "anywhere in them, read with their lines joined:\n"
                + "\n".join(offenders)
            )

    def test_no_tier_table_denies_the_fable_contract(self) -> None:
        offenders = [problem for doc in self.docs for problem in check_denials(doc)]
        if offenders:
            self.fail(
                "these lines mention `fable` in order to DENY it - naming the "
                "rescue rung to forbid it is not naming it:\n" + "\n".join(offenders)
            )


class WorkSkillFableContractTest(unittest.TestCase):
    """`fable` is wired into /work's routing, pipeline and gates, not just spelled.

    The enumeration scan above is satisfied by pasting the bare word `fable`
    onto a line. These pin the contracts a rescued task actually depends on:
    the mapping's two halves must be PAIRED, a gate row must carry the positive
    action, and a sentence that denies the contract fails it.
    """

    def setUp(self) -> None:
        self.assertTrue(WORK_SKILL.exists(), f"missing tier-table file: {WORK_SKILL}")
        self.doc = Doc(WORK_SKILL)
        # Positive control: every section these contracts pin still exists, so a
        # clean verdict cannot come from scanning an empty section.
        for heading in PINNED_SECTIONS:
            self.assertTrue(
                self.doc.section(heading),
                f"{WORK_SKILL}: no `{heading}` section - renamed?",
            )

    def reject(self, problems: list[str], message: str) -> None:
        if problems:
            self.fail(message + "\n" + "\n".join(problems))

    def test_fable_overrides_the_deterministic_routing_table(self) -> None:
        self.reject(
            check_routing_override(self.doc),
            f"{WORK_SKILL} never says a task carrying `metadata.model: \"fable\"` "
            "OVERRIDES the step-3 deterministic routing table outright - never "
            'qwen, never Gemini, always a Claude Agent dispatch at `model: '
            '"fable"` - and that `fable` is never a session model, never selected '
            "autonomously. Without both, the table routes a rescued backend task "
            "to qwen and burns the one approved rescue.",
        )

    def test_fable_maps_to_full_pipeline(self) -> None:
        self.reject(
            check_pipeline_mapping(self.doc),
            f"{WORK_SKILL} never PAIRS `fable` with the `\"full\"` pipeline depth "
            "(the same depth as `opus`) in a tier -> depth mapping. A rescue "
            "attempt would then be stamped with, and run, the wrong pipeline.",
        )

    def test_devon_is_dispatched_for_a_fable_task(self) -> None:
        self.reject(
            check_devon_row(self.doc),
            f"{WORK_SKILL} step 2.85: the Devon tier gate has no `fable` row "
            "carrying the DISPATCH action. The rescue rung runs the deepest "
            "pipeline, like `opus`, so its own row must dispatch Devon.",
        )

    def test_a_fable_task_is_reviewed_by_the_per_task_review_gate(self) -> None:
        self.reject(
            check_review_row(self.doc),
            f"{WORK_SKILL} step 5.7: the per-task review tier gate has no `fable` "
            "row carrying the REVIEW action. Only `haiku` skips that review - the "
            "rescue rung's own row must be on the reviewed side.",
        )

    def test_a_fable_gate_failure_has_no_rung_above_it(self) -> None:
        self.reject(
            check_no_rung_above(self.doc),
            f"{WORK_SKILL} step 5.5: state of `fable` ITSELF that it has **no rung "
            "above it**, in that same sentence, so its gate failure goes to the "
            "exhaustion path, never to an escalation.",
        )
        self.reject(
            check_no_auto_escalation(self.doc),
            f"{WORK_SKILL} step 5.5: the rung-up computation puts `fable` on an "
            "automatic escalation edge, which destroys the human gate. Name it "
            "there only to EXCLUDE it.",
        )

    def test_fable_carries_its_own_dispatch_budget(self) -> None:
        self.reject(
            check_budget(self.doc),
            f"{WORK_SKILL} step 5.5: `fable` has its own budget - 1 dispatch per "
            f"PRD, ever - and must be cited from {LADDER_FILE} § Per-rung budgets, "
            "never folded into the Claude-rungs 2-dispatch group. Folding it "
            "licenses a second rescue off one human approval.",
        )

    def test_feedback_retry_and_repair_gates_exclude_fable_by_name(self) -> None:
        self.reject(
            check_retry_repair_excludes_fable(self.doc),
            f"{WORK_SKILL} step 5.5: the feedback-retry gate or a REPAIR gate "
            "still says an unqualified `Claude rung(s)` (or names `fable` "
            'without excluding it). `fable` is elsewhere mapped to "Claude '
            'Fable" as a model, so that wording reads as including it - '
            "handing a `fable` gate failure a second dispatch (feedback "
            "retry) and a third (repair), which breaks the one-Fable-"
            "dispatch-per-PRD invariant.",
        )


# --- exploit regression fixtures -------------------------------------------
#
# The checks above are only as good as their ability to REJECT. The real
# work/SKILL.md IS the compliant baseline - it carries the `fable` wiring for
# real - so each fixture copies it into a temp dir and REPLACES (or deletes)
# the file's OWN wiring with the exact edit that beat an earlier version of
# these tests, then asserts the check now rejects it. Every fixture therefore
# takes something load-bearing AWAY; none can pass by adding inert prose.
#
# `patch` asserts every anchor is still in the file, so a re-worded SKILL.md
# makes the fixture FAIL LOUDLY ("re-anchor it") instead of quietly mutating
# nothing and passing.


class WorkSkillExploitRejectionTest(unittest.TestCase):
    """Ten edits that beat the `fable` contract and passed anyway. Never again."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.copy = Path(self.tmp.name) / "SKILL.md"
        shutil.copyfile(WORK_SKILL, self.copy)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def patch(self, text: str, patches: tuple) -> str:
        for old, new in patches:
            self.assertIn(
                old,
                text,
                f"fixture drift: {WORK_SKILL} no longer contains {old[:70]!r}, so "
                "this fixture is testing something else - re-anchor it",
            )
            text = text.replace(old, new, 1)
        return text

    def write(self, text: str) -> Doc:
        self.copy.write_text(text)
        return Doc(self.copy)

    def exploited(self, *patches: tuple) -> Doc:
        return self.write(self.patch(self.copy.read_text(), patches))

    def test_the_unmodified_real_file_passes_every_check(self) -> None:
        # Without this, "the check rejects the exploit" is worthless: a check
        # that rejects everything would pass all nine fixtures below. Pinning
        # the baseline to the SHIPPED file also makes every fixture non-vacuous
        # by construction - an exploit can only bite by removing real wiring.
        doc = Doc(self.copy)
        for name, check in WORK_SKILL_CHECKS:
            with self.subTest(check=name):
                self.assertEqual(
                    check(doc),
                    [],
                    f"the {name} check rejects the real {WORK_SKILL}, so it can "
                    "never be satisfied",
                )

    def test_rejects_negated_accepted_values_line(self) -> None:
        # 1. The word `fable` on the accepted-values line, appended to a
        #    parenthetical that FORBIDS the tier.
        doc = self.exploited(
            (
                'A fourth value, `"fable"`, is the human-gated rescue rung above '
                "`opus`",
                'A fourth value, `"fable"`, is the human-gated rescue rung above '
                '`opus` (`"fable"` is **not** an accepted value - never write it '
                "into `metadata.model`; treat any task carrying it as `sonnet`)",
            )
        )
        self.assertEqual(
            check_line_enumerations(doc),
            [],
            "precondition: the line still spells `fable`, which is exactly why a "
            "presence scan cannot catch this",
        )
        self.assertTrue(
            check_denials(doc), "a line that forbids `fable` must not satisfy it"
        )

    def test_rejects_fable_mapped_to_the_shallowest_pipeline(self) -> None:
        # 2. `haiku` and `fable` -> "minimal", with `opus` -> "full" later in the
        #    same sentence satisfying a co-occurrence scan.
        doc = self.exploited(
            (
                '`fable` → `"full"` as well — the rescue rung runs the deepest '
                "pipeline, like `opus`. ",
                "",
            ),
            (
                '`haiku` → `"minimal"` (Tess + Ivan)',
                '`haiku` and `fable` → `"minimal"` (Tess + Ivan)',
            ),
        )
        self.assertEqual(
            check_line_enumerations(doc),
            [],
            "precondition: the line still names all four tiers",
        )
        self.assertTrue(
            check_pipeline_mapping(doc),
            "`fable` and `\"full\"` on one line is not a mapping - the pair has to "
            "be `fable` -> `\"full\"`",
        )

    def test_rejects_fable_folded_into_the_claude_rungs_budget(self) -> None:
        # 3. `Claude rungs (haiku/sonnet/opus/fable) get 2 dispatches` - which
        #    licenses a second rescue off one human approval.
        doc = self.exploited(
            (
                "Claude rungs (haiku/sonnet/opus) get 2 dispatches (initial + one "
                "feedback retry) before diagnosis; the `fable` rescue rung gets 1 "
                "capability dispatch per PRD, ever (no feedback retry, no repair);",
                "Claude rungs (haiku/sonnet/opus/fable) get 2 dispatches (initial "
                "+ one feedback retry) before diagnosis;",
            )
        )
        self.assertTrue(
            check_budget(doc),
            "`fable` gets 1 dispatch per PRD, ever - it is not a Claude rung in "
            "the 2-dispatch sense",
        )

    def test_rejects_fable_on_an_automatic_escalation_edge(self) -> None:
        # 4. `haiku -> sonnet -> opus -> fable` in the rung-up computation.
        doc = self.exploited(
            (
                "haiku, haiku -> sonnet -> opus) with a FAILURE SUMMARY",
                "haiku, haiku -> sonnet -> opus -> fable) with a FAILURE SUMMARY",
            )
        )
        self.assertTrue(
            check_no_auto_escalation(doc),
            "an automatic `opus -> fable` edge destroys the human rescue gate",
        )

    def test_rejects_a_rewrapped_enumeration_that_drops_fable(self) -> None:
        # 5. The step-6 mapping hard-wrapped after `haiku` -> "minimal", so no
        #    single line names all three tiers any more.
        doc = self.exploited(
            (
                '(`haiku` → `"minimal"`, `sonnet`/absent/legacy → `"lean"`, '
                '`opus` → `"full"`) plus `fable` → `"full"` (the rescue rung runs '
                "the deepest pipeline, like `opus`)",
                '(`haiku` → `"minimal"`,\n`sonnet`/absent/legacy → `"lean"`, '
                '`opus` → `"full"`)',
            )
        )
        self.assertEqual(
            check_line_enumerations(doc),
            [],
            "precondition: the wrap is exactly what blinds the per-line scan",
        )
        self.assertTrue(
            check_pinned_enumerations(doc),
            "the joined-section scan exists for this: a hard wrap must not hide "
            "an enumeration",
        )
        self.assertTrue(check_pipeline_mapping(doc))

    def test_rejects_a_contract_stated_only_in_an_html_comment(self) -> None:
        # 6. Both statements of the routing-override contract (§ Per-task model
        #    dispatch and § 3) demoted into invisible HTML comments - the second
        #    one negating the contract outright.
        doc = self.exploited(
            (
                '**A task carrying `metadata.model: "fable"` overrides the step-3 '
                "Deterministic routing table outright**",
                '<!-- **A task carrying `metadata.model: "fable"` overrides the '
                "step-3 Deterministic routing table outright**",
            ),
            (
                'the step-5.7 per-task review, and `pipeline: "full"`.',
                'the step-5.7 per-task review, and `pipeline: "full"`. -->',
            ),
            (
                "**`fable` overrides this table outright.**",
                "<!-- **`fable` overrides this table outright.**",
            ),
            (
                "so the human rescue gate is the only way in "
                "(`run-autopilot/references/model-ladder.md` § Fable rescue).",
                "so the human rescue gate is the only way in "
                "(`run-autopilot/references/model-ladder.md` § Fable rescue). "
                "Correction: `fable` does not override the routing table and IS "
                "an ordinary session model. -->",
            ),
        )
        self.assertTrue(
            check_routing_override(doc),
            "an HTML comment renders to nothing, so it can never carry a contract",
        )
        self.assertEqual(
            check_denials(doc),
            [],
            "the comment must be invisible to BOTH scans - not merely re-caught "
            "by the denial rule",
        )

    def test_rejects_a_see_also_line_in_place_of_a_devon_row(self) -> None:
        # 7. A "nothing in this step changes" pointer in § 2.85 that changes no
        #    row, leaving `fable` in the catch-all skip row.
        doc = self.exploited(
            (
                "\n| `fable` | dispatch Devon (below) — the rescue rung runs the "
                "deepest pipeline, like `opus` |",
                "",
            ),
            (
                "The step-2.8 test quality gate is **unchanged**",
                "See also: the Fable rescue gate is documented in "
                "`run-autopilot/references/model-ladder.md` - nothing in this "
                "step changes for it.\n\nThe step-2.8 test quality gate is "
                "**unchanged**",
            ),
        )
        self.assertTrue(
            check_devon_row(doc),
            "a mention in the section is not a row: the gate reads the TABLE",
        )

    def test_rejects_a_skip_row_worded_as_no_reviewer_dispatch(self) -> None:
        # 8. The `fable` row moved to the not-reviewed side by synonym, evading a
        #    scan for the literal word "skip".
        doc = self.exploited(
            (
                "| `fable` | review (below) — the rescue rung is reviewed like "
                "`opus` |",
                "| `fable` | no reviewer dispatch — proceed straight to step 6 |",
            )
        )
        self.assertTrue(
            check_review_row(doc),
            "the row that names `fable` must carry the REVIEW action, whatever "
            "words the skip side is dressed in",
        )

    def test_rejects_no_rung_above_attached_to_the_wrong_rung(self) -> None:
        # 9. "no rung above" said of `opus`, with `fable` six lines earlier (in
        #    exploit 4, where it says the opposite).
        doc = self.exploited(
            (
                "haiku, haiku -> sonnet -> opus) with a FAILURE SUMMARY",
                "haiku, haiku -> sonnet -> opus -> fable) with a FAILURE SUMMARY",
            ),
            (
                "  A `fable` attempt has **no rung above it**: its gate failure "
                "goes straight to that same\n"
                "  exhaustion path, never to an escalation (`model-ladder.md` "
                "§ Capability ladders).",
                "  The opus rung has **no rung above it**, so opus-rung exhaustion "
                "goes straight\n  to that same exhaustion path, never to an "
                "escalation.",
            ),
        )
        self.assertTrue(
            check_no_rung_above(doc),
            "`fable` and `no rung above` in one section is not a statement about "
            "`fable` - the subject has to be the rescue rung itself",
        )

    def test_rejects_fable_granted_a_feedback_retry(self) -> None:
        # 10. The feedback-retry carve-out "fixed" by listing `fable` among the
        #     eligible tiers instead of excluding it - a second Fable dispatch.
        doc = self.exploited(
            (
                "haiku/sonnet/opus rungs only, never fable",
                "haiku/sonnet/opus/fable rungs only",
            )
        )
        self.assertEqual(
            check_line_enumerations(doc),
            [],
            "precondition: the line now names all four tiers, which is exactly "
            "why a bare presence scan cannot catch this",
        )
        self.assertTrue(
            check_retry_repair_excludes_fable(doc),
            "listing `fable` alongside haiku/sonnet/opus as eligible for the "
            "feedback retry is not excluding it - it grants a second `fable` "
            "dispatch off one human approval",
        )


if __name__ == "__main__":
    unittest.main()
