"""Shared pytest fixtures for pytoy tests."""

import sys, os

# make pytoy importable from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
