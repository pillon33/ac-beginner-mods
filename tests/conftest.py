"""Make the in-game app folders importable from tests.

In-game apps aren't packages (AC loads them by folder), so tests put
each app folder on sys.path the same way AC effectively does.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(REPO_ROOT, "apps", "python")

sys.path.insert(0, os.path.join(APPS_DIR, "fuel_hud"))
