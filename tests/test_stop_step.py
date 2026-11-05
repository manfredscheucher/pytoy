"""STOP counts as a step: a program that is just `stop` stops after 1 step,
the PC stays on the STOP, and in the GUI the STOP can be undone like any step.

Run: python3 -m pytest tests/test_stop_step.py -q
"""

import os
import sys

from pytoy.assembler import assemble
from pytoy.simulator import simulate

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gen_snapshot  # noqa: E402


def _mem(src):
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    assert not errors, errors
    return mem, listing, syms, data_addrs


def test_cli_single_stop_is_one_step(capsys):
    mem, _listing, syms, data_addrs = _mem("stop\n")
    simulate(mem, syms, data_addrs, verbose=True)
    assert "Stopped after 1 steps." in capsys.readouterr().out


def test_snapshot_runner_counts_stop():
    mem, _listing, _syms, data_addrs = _mem("load x\nadd x\nstop\nx: 1\n")
    _acc, steps, _touched, _mem2, _cap = gen_snapshot.run_program(mem, data_addrs)
    assert steps == 3


def test_gui_stop_counts_keeps_pc_and_undoes(build_debugger):
    mem, listing, syms, data_addrs = _mem("stop\n")
    win = build_debugger(mem=mem, listing=listing, syms=syms, data_addrs=data_addrs)
    win.step()
    assert win.stopped
    assert win.step_count == 1
    assert win.pc == 0
    win.step_back()
    assert not win.stopped
    assert win.step_count == 0
