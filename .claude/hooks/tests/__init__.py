"""Test package for ~/.claude/hooks/.

Adds the parent hooks/ directory to sys.path so test modules can import the
hook scripts directly (`import notify`, `import track_cost`, etc.) without
each test file needing its own sys.path manipulation.
"""

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parents[1])
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
