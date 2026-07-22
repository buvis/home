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
"""

import datetime
import json
import subprocess
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
