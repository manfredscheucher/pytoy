"""Shared pytest fixtures for toyasm tests."""

import sys, os

_ROOT = os.path.join(os.path.dirname(__file__), '..')

# make toyasm importable from project root
sys.path.insert(0, _ROOT)

# make toycc importable from the compiler folder
sys.path.insert(0, os.path.join(_ROOT, 'compiler'))
