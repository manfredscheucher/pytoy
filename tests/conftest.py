"""Shared pytest fixtures / import path for the pytoy tests."""

import sys, os

_ROOT = os.path.join(os.path.dirname(__file__), '..')

# make the pytoy package importable from the repo root
sys.path.insert(0, _ROOT)

# Run Qt headless unless the caller already chose a platform, so the GUI tests
# don't need a display (equivalent to QT_QPA_PLATFORM=offscreen on the CLI).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
