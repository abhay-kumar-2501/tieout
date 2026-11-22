"""App tests import ``components`` as the running app does (``app/`` on the path)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# A new session starts on a random sample merger; tests pin the held-out demo seed so
# their figures are fixed. Tests of the rotation itself override this per test.
os.environ["TIEOUT_SAMPLE"] = "demo"
