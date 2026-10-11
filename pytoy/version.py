#!/usr/bin/env python3
"""Build identity for pytoy — shown in Help -> About.

The release number lives in the top-level VERSION file (bump it by hand). The
rest (commit sha, dirty flag, commit date) is read from git *at runtime*, since
pytoy runs straight from the checkout — no build step to bake it in. Everything
degrades gracefully when git or the VERSION file is missing (e.g. installed as a
plain package), so About always shows *something*.

Mirrors hex610's version-info convention (version / commit / dirty / commitDate)
so the two projects report their build identity the same way.
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


def version_info():
    """A dict describing this build. Keys always present; values may be
    'unknown' / None when git or the VERSION file is unavailable.

      version    : release number from ./VERSION
      commit     : short git SHA (or None)
      dirty      : True if tracked files have uncommitted changes (None if unknown)
      commitDate : author date of HEAD, ISO-8601 (or None)
    """
    commit = _git("rev-parse", "--short", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    dirty = None if status is None else bool(status)
    commit_date = _git("show", "-s", "--format=%cI", "HEAD")
    return {
        "version": _read_version_file(),
        "commit": commit,
        "dirty": dirty,
        "commitDate": commit_date,
    }


def version_lines():
    """version_info() formatted as display lines for the About dialog."""
    info = version_info()
    lines = [f"pytoy {info['version']}"]
    if info["commit"]:
        commit = info["commit"]
        if info["dirty"]:
            commit += " (modified)"
        lines.append(f"commit {commit}")
    if info["commitDate"]:
        lines.append(f"committed {info['commitDate']}")
    return lines
