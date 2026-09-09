"""Shared pytest fixtures / import path for the pytoy tests."""

import sys, os

_ROOT = os.path.join(os.path.dirname(__file__), '..')

# make the pytoy package importable from the repo root
sys.path.insert(0, _ROOT)
