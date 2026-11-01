# Discovery: Keep Warrant Secrets Out of Backups

## Classification

Depth: standard | Date: 2026-10-18 | Status: specified as PRD 00175
(backlog, 2026-10-19); live deployment remains separate
Seeded from session 523838c3 follow-ups; user instruction 2026-10-18: "all of
them must be recorded as discovery documents that I will go through".
Written from a sandboxed session. Nothing inside `~/.config/warrant` was read
or listed; every fact below comes from `~/bin/warrant`, `tmutil`, the
Backblaze install under `/Library/Backblaze.bzpkg/bzdata` and the buvis index.

## Premise check

**Possible exposure; completed upload is not established.** Backblaze is
configured to back up `/` continuously (`bzinfo.xml`: `bzdirfilter
dir="/" whichfiles="all"`, `backup_schedule_type="continuously"`), and no
rule excludes `/Users/bob/.config`. Its root file list
(`bzfilelists/v000af2cabc23184acce9cd70210_root_filelist.dat`) names all three
files: `config/warrant/passphrase.scrypt`, `config/warrant/config.json` and
`config/warrant/ledger.jsonl`. Checked 2026-10-18 by name match only. Local
enumeration is not a completed-upload receipt; confirm remote presence from
Restore or an authoritative upload record without reading the secret.
Possible exposure is sufficient reason to rotate; do not wait for that proof.

Other channels, as measured:

- **Time Machine**: `tmutil destinationinfo` answers "No destinations
  configured". Not a live channel today. `tmutil isexcluded` fails from the
  sandbox with exit 80, "requires Full Disk Access privileges", so the
  current exclusion state is unknown.
- **buvis**: `ls-files -- ':(top)bin/warrant' ':(top).config/warrant'` (cwd
  `/Users/bob`, control path proves the shape) lists `bin/warrant` and
  `.config/warrant/config.json` only. The hash and the ledger are not tracked;
  `config.json` is tracked on purpose and holds no secret.

What a copy of the hash is worth offline: `SCRYPT = {"n": 2**17, "r": 8, "p":
1}` (`warrant:79`), so each guess costs 128 MiB and about 0.3 s on one Apple
silicon core (the code's own comment). The PIN is 4 to 8 digits
(`set_pin`, `warrant:298-309`), a space of 111,110,000 guesses.

The source comment is not a benchmark of an attacker: no CPU scaling or GPU
cracking rate was measured. A short numeric secret permits offline guessing
when its hash escapes; do not infer a reliable recovery time from memory
capacity alone. The live
gates do not apply to an offline copy: Seatbelt's deny-read, the ledgered
`attempt` line and the three-misses-in-ten-minutes lockout
(`LOCKOUT_AFTER, LOCKOUT_WINDOW_SEC = 3, 600`, `warrant:81`) all run inside
`approve`.

## Problem

The warrant PIN relies on preventing offline guesses. Backblaze may hold
the hash and retained versions; remote presence and retention are not yet
verified. Anyone obtaining a copy can attempt offline guessing without the
broker's lockout. On its own, the PIN only approves requests typed at the
host, but a
short numeric PIN is often reused for a phone, a door or a card, so a cracked
one may unlock more than warrant. Restoring from a backup also has a quiet
cost: the machine comes back with an old PIN and an old ledger.

## Requirements (proposed)

### Must have

1. **Exclude the whole directory, not single files.** `atomic_write` writes a
   `.tmp` file and renames it over the target (`warrant:145-150`), so each
   `warrant init` makes a new inode for `passphrase.scrypt` and a sticky
   exclusion on the old file is lost. An exclusion on `~/.config/warrant`
   itself holds across rewrites.
2. **Time Machine exclusion (human act on the host):** `tmutil addexclusion
   ~/.config/warrant`. A sticky exclusion is an extended attribute on the
   directory, needs no sudo and follows the item. Agents cannot set it: the
   profile denies reads of the directory and grants no write there.
3. **Backblaze exclusion (human act on the host):** Backblaze is set to honor
   Time Machine exclusions (`use_time_machine_excludes="true"` in
   `bzinfo.xml`), so step 2 may cover it. Not yet proven that the sticky
   attribute counts, so also add the folder in Backblaze Settings,
   Exclusions. The editable rules file is mode 0666 (see Risks), so the GUI
   needs no admin password.
4. **Rotate the PIN after both exclusions (human act):** `~/bin/warrant init`
   with a new PIN that is not the old one. The old hash stays in Backblaze
   history until retention drops it; once rotated, cracking it yields a dead
   PIN. If the old PIN is used anywhere else, change it there too
   (AGENTS.md: "If a secret may have been exposed, rotate it").
5. **Make exclusion precede the secret write in `warrant init` (code,
   agent drafts, deployed through warrant):** create `config_dir`, then
   attempt its exclusion before writing the new hash or its temporary file.
   Print a warning rather than fail when exclusion cannot be set, preserving
   the proposed warning-only behavior; explicitly report that this degraded
   initialization does not prevent backup exposure. Time Machine exclusion
   alone does not prove Backblaze exclusion: requirement 3 remains a host
   prerequisite for the full protection claim. Read back the attribute with
   `xattr` without Full
   Disk Access, so a test and a later check do not depend on `tmutil
   isexcluded`.
6. **Tests ship with the code** in `~/bin/tests/test_warrant.py`: `init` on a
   fixture site marks `config_dir` excluded before the first hash write; an
   exclusion failure warns about possible exposure and still writes the PIN.

### Nice to have

- `warrant approve` warns once per run when `config_dir` has lost the
  exclusion attribute (cheap `getxattr`, no Full Disk Access).

### Out of scope

- Changing scrypt cost or allowing longer secrets. The 4 to 8 digit PIN is a
  settled decision (PRD 00159); this change removes the offline copy instead.
- Encrypting the Backblaze backup with a private key. Worth knowing (Open
  Questions), but it is an account setting, not a warrant change.
- The world-writable Backblaze data directory, beyond the note under Risks.
- Seatbelt profile changes.

## Constraints

- Agents cannot read, list or write `~/.config/warrant`, so every check of
  the live directory is a host act. The agent side ends at code, tests and a
  hand-off.
- `~/bin` is written only through warrant; deploy as in 00159 (draft in the
  scratchpad, `cp` request so the source is hashed, tests on the host).
- `tmutil isexcluded` needs Full Disk Access for the calling terminal, which
  the host terminal may lack too.

## Codebase Context

- **Relevant code**: `~/bin/warrant` `SCRYPT` and lockout constants 79-81,
  `atomic_write` 145-150, `set_pin` 298-309 (mkdir at 308), `verify_pin`
  312-319, the missing-hash check near 662.
- **Conventions**: tests load the script with `SourceFileLoader` and build a
  fixture `Site`; tests name the rule they enforce.
- **Integration points**: `set_pin` only; nothing on the agent side changes.
- **sysup is not the home.** Its steps are upgrades (`commands:` brew, uv,
  mise and others in `default.yaml`) and expiring credentials (`expiry:`).
  An exclusion is set once when the secret is born, so it belongs in `warrant
  init`. A recurring drift check could become a sysup `expiry`-style check
  later if the nice-to-have warning proves too quiet.

## Success Criteria

- On the host, `tmutil isexcluded ~/.config/warrant` (from a terminal with
  Full Disk Access) reports `[Excluded]`, or `xattr -l ~/.config/warrant`
  shows `com.apple.metadata:com_apple_backup_excludeItem`.
- Backblaze Settings, Exclusions lists the folder; verify that subsequent
  scans exclude new contents. Record remote presence of older versions and
  the applicable retention/removal behavior separately. A retained Restore
  entry after the next scan does not disprove the new exclusion.
- `warrant init` has run with a new PIN after the exclusion; `warrant
  approve` accepts it.
- `test_warrant.py` stays green on the host, with the two new tests.

## Risks

- **Restore loses the PIN and the ledger.** By design: after a restore,
  `approve` finds no hash and refuses until `warrant init`, which forces a
  fresh PIN on a new machine. The ledger's history is lost too; it is an
  audit trail, not a dependency, and its lockout window is ten minutes.
- **Backblaze may ignore the sticky attribute.** Requirement 3 adds the
  folder in the Backblaze GUI as well, so neither path depends on the other.
- **World-writable Backblaze data.** `/Library/Backblaze.bzpkg/bzdata` is
  mode 0777 and its rule files 0666, so any unsandboxed process of any local
  user can add or remove exclusions. Sandboxed agents cannot (no write grant
  under `/Library`). Recorded, not addressed here.
- **Old versions may remain.** Exclusion is not immediate historical deletion.
  Check the account's actual removal behavior; do not promise a next-scan
  disappearance. Rotation invalidates the old PIN for warrant; reuse elsewhere
  still matters. See [Backblaze's deletion documentation](https://www.backblaze.com/computer-backup/docs/delete-uploaded-files).

## Open Questions

1. Exclude the whole directory (recommended: survives `atomic_write`, keeps
   the ledger off-site too) or only `passphrase.scrypt` through a Backblaze
   rule plus a code change that re-applies the attribute after each write?
2. Is the Backblaze backup encrypted with a private key (PEK)? If not,
   Backblaze can read the copy, which shifts the case from "account takeover"
   to "provider side".
3. What is the Backblaze version retention (30 days, 1 year, forever)? It
   decides how long the old hash stays.
4. Was the current PIN 4 digits? `warrant init` to a PIN was still owed on
   2026-10-16; if a short PIN went into the backup, rotation is urgent, not
   tidy-up.

## Discovery Log (2026-10-18)

### Q1: Is the hash actually in a backup today?
**Answer** (measured, not asked; corrected by review): the local Backblaze
file list names all three files; that establishes enumeration, not upload.
Remote presence is unverified. Time Machine has no destination.

### Q2: Who can set the exclusion?
**Answer** (from the profile and tool behaviour): only the human on the host.
The agent cannot touch the directory, and `tmutil isexcluded` is refused
without Full Disk Access even before Seatbelt is reached.

### Q3: One-off act or recurring check?
**Answer** (inferred, open to reversal): one-off, built into `warrant init`,
because the exclusion must exist from the moment the hash does. sysup holds
upgrades and expiring credentials, not birth-time setup.

## Discovery review (2026-10-18)

All five standard-depth lenses ran. F4 (Coherence, Blocking), option 1:
exclusion precedes the hash write, and warning-only failure no longer claims
protection. F5 (Integrity, Blocking), option 1: separate current exclusion,
rotation and historical removal. F11 (Integrity, Non-blocking), option 1:
qualify upload evidence and remove unmeasured cracking rates. No live secret,
backup setting or PIN was read or changed. Host verification and rotation
remain pending; this review does not certify exposure closed.

## PRD coverage check (2026-10-18)

PRD created: yes, [00175](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00175-exclude-warrant-secrets-before-pin-writes-v1.md) (backlog), saved 2026-10-19.
The earlier no-match audit was superseded by the requested PRD creation.

### Elicitation refresh

Continue with the existing whole-directory exclusion proposal. Live set_pin still writes the hash without an exclusion step. Required order remains exclusion, verification, then host-only rotation. Backup account settings and retained-version evidence are host acceptance inputs, not facts inferred here. No secret, exclusion, account setting or PIN was accessed or changed.

These are code-derived findings and planning defaults, not new user answers
or a new discovery-review pass. Existing Discovery Log answers remain valid.

## PRD creation (2026-10-19)

Specified as [00175](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00175-exclude-warrant-secrets-before-pin-writes-v1.md). The user requested creation of the missing PRDs.
The earlier elicitation and review entries remain historical evidence.
The PRD records final authoring defaults, dependency ordering and scope.
Implementation uses an isolated checkout and headless acceptance checks;
live deployment and host-only operational steps remain separate.
Template, guess-density and grounding gates passed before saving.
