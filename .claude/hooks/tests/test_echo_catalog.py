"""Tests for hooks/_echo_catalog.py — the rationalizations catalog behind the
Echo deny envelope (parsing, path pinning, trigger precedence).

`hooks/` is on sys.path via the tests package (`tests/__init__.py`), so the
module imports by bare name. Every catalog override goes through monkeypatch:
`_echo_catalog` is imported once per session, so a bare assignment would leak
into every later test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import _echo_catalog as catalog

ENTRY = Path(__file__).resolve().parents[1] / "cartographer-echo.py"


def _write_catalog(path: Path, body: str) -> None:
    path.write_text(
        "# Rationalizations Catalog\n\n## Excuses\n\n" + body,
        encoding="utf-8",
    )


def _use_catalog(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(catalog, "_RATIONALIZATIONS_PATH", path)
    monkeypatch.setattr(catalog, "_RATIONALIZATIONS_CACHE", None)


# --- Real catalog: path pinned to rules-library/, entries parse ---


def test_rationalizations_parsed_from_rules_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rationalizations parser must successfully load real rule file content."""
    monkeypatch.setattr(catalog, "_RATIONALIZATIONS_CACHE", None)
    rats = catalog._load_rationalizations()
    assert "Quick fix, skip the map" in rats
    assert "Couldn't find existing helper" in rats


def test_rationalizations_path_points_to_existing_file() -> None:
    """The module-level catalog path constant must resolve to a real file on disk."""
    assert catalog._RATIONALIZATIONS_PATH.is_file(), (
        f"_RATIONALIZATIONS_PATH does not exist: {catalog._RATIONALIZATIONS_PATH}"
    )


def test_rationalizations_path_yields_parsed_entries_not_pointer_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog path must resolve to the real catalog (parseable entries), not
    the <=200 byte pointer stub left behind at the old rules/ location."""
    monkeypatch.setattr(catalog, "_RATIONALIZATIONS_CACHE", None)
    rats = catalog._load_rationalizations()
    assert rats, (
        f"expected non-empty parsed entries from {catalog._RATIONALIZATIONS_PATH}, got {rats}"
    )
    for key in (
        "Quick fix, skip the map",
        "Couldn't find existing helper",
        "I'll add tests later",
    ):
        assert key in rats, (
            f"missing known catalog entry {key!r}; got keys {sorted(rats.keys())}"
        )
        why, counter, triggers = rats[key]
        assert why.strip(), f"empty 'why' text for {key!r}"
        assert counter.strip(), f"empty 'counter' text for {key!r}"
        assert triggers, f"live catalog entry {key!r} carries no triggers"


def test_every_hardcoded_lookup_key_exists_in_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A catalog heading rename must not silently kill a selector branch.

    Regression for the `"Quick fix, skip atlas"` key: the heading was renamed
    to "Quick fix, skip the map" (PRD 00138) and the lookup key never updated,
    so that branch was dead and every non-helper-verb deny fell through to the
    first entry. Scans both the catalog module and the entry hook: a hardcoded
    key could reappear in either."""
    source = (
        Path(catalog.__file__).read_text(encoding="utf-8")
        + ENTRY.read_text(encoding="utf-8")
    )
    keys = re.findall(r"rats(?:\.get\(\s*|\[)\s*['\"]([^'\"]+)['\"]", source)
    monkeypatch.setattr(catalog, "_RATIONALIZATIONS_CACHE", None)
    rats = catalog._load_rationalizations()
    missing = [k for k in keys if k not in rats]
    assert not missing, (
        f"lookup keys with no matching catalog heading: {missing}; "
        f"catalog has {sorted(rats)}"
    )


# --- Synthetic catalogs: trigger precedence and parsing edges (PRD 00157) ---


def test_shared_trigger_cites_the_earlier_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When two entries claim the same trigger term, the earlier entry (file
    order) wins — the documented precedence rule. Also pins comma-separated
    multi-term parsing: the later entry stays reachable via its unshared term."""
    path = tmp_path / "rationalizations.md"
    _write_catalog(
        path,
        '### "Earlier entry"\n\n'
        "- **Why it's wrong**: earlier why.\n"
        "- **Counter-action**: earlier counter.\n"
        "- **Triggers**: frobnicate\n\n"
        '### "Later entry"\n\n'
        "- **Why it's wrong**: later why.\n"
        "- **Counter-action**: later counter.\n"
        "- **Triggers**: glorp, frobnicate\n",
    )
    _use_catalog(monkeypatch, path)
    picked = catalog._pick_rationalization(["frobnicate_widget"])
    assert picked is not None and picked[0] == "Earlier entry"
    picked = catalog._pick_rationalization(["glorp_widget"])
    assert picked is not None and picked[0] == "Later entry"


def test_empty_triggers_bullet_yields_no_triggers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty Triggers bullet must parse to (), never swallow the following
    bullet's text as garbage trigger terms (author puts Triggers mid-entry)."""
    path = tmp_path / "rationalizations.md"
    _write_catalog(
        path,
        '### "Empty triggers entry"\n\n'
        "- **Why it's wrong**: some why.\n"
        "- **Triggers**:\n"
        "- **Counter-action**: some counter.\n",
    )
    _use_catalog(monkeypatch, path)
    rats = catalog._load_rationalizations()
    assert "Empty triggers entry" in rats
    why, counter, triggers = rats["Empty triggers entry"]
    assert triggers == (), triggers
    assert counter == "some counter."


def test_entry_without_triggers_parses_but_is_never_cited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entry with no Triggers bullet still parses (humans and /architect
    read it) but is never auto-cited by a deny."""
    path = tmp_path / "rationalizations.md"
    _write_catalog(
        path,
        '### "Untriggered entry"\n\n'
        "- **Why it's wrong**: some why.\n"
        "- **Counter-action**: some counter.\n",
    )
    _use_catalog(monkeypatch, path)
    rats = catalog._load_rationalizations()
    assert "Untriggered entry" in rats
    assert rats["Untriggered entry"][2] == ()
    assert catalog._pick_rationalization(["untriggered_entry_helper"]) is None


def test_missing_catalog_file_yields_empty_and_no_pick(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable catalog degrades to no rationalization, never an exception:
    the deny envelope must still render on a host without rules-library/."""
    _use_catalog(monkeypatch, tmp_path / "absent.md")
    assert catalog._load_rationalizations() == {}
    assert catalog._pick_rationalization(["formatPrice"]) is None
