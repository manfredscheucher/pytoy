"""Shared pytest fixtures for pytoy tests."""

import sys, os

_ROOT = os.path.join(os.path.dirname(__file__), '..')

# make pytoy importable from project root
sys.path.insert(0, _ROOT)

# make toycc importable from the toy-c-compiler folder
sys.path.insert(0, os.path.join(_ROOT, 'toy-c-compiler'))
