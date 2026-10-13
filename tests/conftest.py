"""Make the repo-root packages, telemetry/ and scripts/ importable from
tests, the way the app, the external tools and the scripts see them."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for folder in (REPO_ROOT, os.path.join(REPO_ROOT, "telemetry"), os.path.join(REPO_ROOT, "scripts")):
    sys.path.insert(0, folder)
