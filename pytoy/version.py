#!/usr/bin/env python3
"""Build identity for pytoy — shown in Help -> About.

The release number lives in the top-level VERSION file (bump it by hand). The
rest (commit sha, dirty flag, commit date) is read from git *at runtime*, since
pytoy runs straight from the checkout — no build step to bake it in. Everything
degrades gracefully when git or the VERSION file is missing (e.g. installed as a
plain package), so About always shows *something*.
"""
import os
import subprocess

# repo root = the parent of this package directory (…/pytoy/pytoy/version.py)
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PKG_DIR)


def _read_version_file():
    """The release number from the top-level VERSION file, or 'unknown'."""
    try:
        with open(os.path.join(_ROOT, "VERSION")) as f:
            return f.read().strip() or "unknown"
    except OSError:
        return "unknown"


def _git(*args):
    """Run a git command in the repo root, return stdout stripped or None."""
    try:
        out = subprocess.run(
            ["git", "-C", _ROOT, *args],
            capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def version_lines():
    """The build identity as display lines for the About dialog."""
    lines = [f"pytoy {_read_version_file()}"]
    commit = _git("rev-parse", "--short", "HEAD")
    if commit:
        dirty = _git("status", "--porcelain", "--untracked-files=no")
        lines.append(f"commit {commit}" + (" (modified)" if dirty else ""))
    commit_date = _git("show", "-s", "--format=%cI", "HEAD")
    if commit_date:
        lines.append(f"committed {commit_date}")
    return lines
