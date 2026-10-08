"""Tests for run.py's `sim` CLI argument handling (no GUI, no Qt).

Covers the guard that stops `sim` from feeding a C source (.toyc) to the
assembler: it must exit with a clear hint pointing at the `cc` subcommand,
instead of the confusing "Assembly failed" you'd get by assembling C text.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import run  # noqa: E402


def _sim_args(file):
    """A minimal args namespace for cmd_sim with everything else defaulted off."""
    return types.SimpleNamespace(
        file=file, cli=True, run=False, quiet=True, export=False,
        detect_code_overwrite=False)


def test_sim_rejects_toyc_with_cc_hint():
    with pytest.raises(SystemExit) as exc:
        run.cmd_sim(_sim_args("foo.toyc"))
    msg = str(exc.value)
    assert "C source" in msg
    assert "run.py cc" in msg          # points at the compile subcommand


def test_sim_toyc_check_is_case_insensitive():
    # .TOYC should be caught too (the extension check is lower-cased).
    with pytest.raises(SystemExit) as exc:
        run.cmd_sim(_sim_args("FOO.TOYC"))
    assert "run.py cc" in str(exc.value)
