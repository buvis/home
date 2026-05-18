"""Verify /survey completes within the 30-second performance budget."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
from run import main

_BUDGET_SECONDS = 30


def test_survey_completes_within_30s(tmp_path, monkeypatch):
    # Populate a realistic-sized repo: 5 layer dirs, 20 .py files each
    for layer in ("api", "cli", "hooks", "lib", "scripts"):
        layer_dir = tmp_path / layer
        layer_dir.mkdir()
        for i in range(20):
            (layer_dir / f"mod_{i}.py").write_text(
                f"import os\n\ndef func_{i}(x):\n    return x\n"
            )

    monkeypatch.chdir(tmp_path)
    start = time.monotonic()
    main(argparse.Namespace(refresh=False, if_missing=False), _home=tmp_path)
    elapsed = time.monotonic() - start
    assert elapsed < _BUDGET_SECONDS, f"survey took {elapsed:.1f}s, exceeds {_BUDGET_SECONDS}s budget"
