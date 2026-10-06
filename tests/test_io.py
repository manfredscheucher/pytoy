"""Tests for the memory-mapped I/O model: reserved assembler labels (io0..io14,
ready) and the headless CLI simulate(), which treats 240..255 as ordinary
memory (no prompting, no output echo). Pure (no Qt)."""

import io
import contextlib

from pytoy.assembler import assemble
from pytoy.simulator import simulate, polling_input
from pytoy import format as F


def _run(src, max_steps=100_000):
    """Assemble + run in the CLI simulator; return (final_acc, stdout)."""
    mem0, listing, syms, data, errs, ds = assemble(src)
    assert errs == [], errs
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        acc = simulate(mem0, syms, data, max_steps=max_steps)
    return acc, buf.getvalue()


# ── reserved labels ──────────────────────────────────────────────────────────

def test_reserved_io_labels_resolve():
    mem, listing, syms, data, errs, ds = assemble(
        "        load  ready\n        store io0\n        store io14\n        stop\n")
    assert errs == []
    assert syms["ready"] == 255 and syms["io0"] == 240 and syms["io14"] == 254


def test_reserved_labels_match_format_module():
    # The assembler seeds the same io0..io14/ready symbols the format module
    # defines, so the two never drift apart.
    _, _, syms, _, errs, _ = assemble(
        "        load ready\n        store io0\n        stop\n")
    assert errs == []
    for name, addr in F.IO_SYMBOLS.items():
        assert syms[name] == addr


def test_user_label_overrides_io_seed():
    mem, listing, syms, data, errs, ds = assemble(
        "io0:    9\n        load io0\n        stop\n")
    assert syms["io0"] == 0          # user label wins over the seed


# ── I/O cells are ordinary memory in the headless runner ─────────────────────

def test_io_cells_are_plain_memory():
    # Store a constant into io0 and read it back into ACC; no prompting/echo.
    src = ("        load  v\n        store io0\n"
           "        load  io0\n        stop\n"
           "v:      42\n")
    acc, out = _run(src)
    assert acc == 42                   # io0 round-tripped through plain memory
    assert "[io0]" not in out          # no output echo in the new model


def test_ready_register_is_plain_memory():
    # Pre-seed ready (255); the program reads it like any other cell into ACC.
    src = ("        load  ready\n        stop\n")
    mem0, listing, syms, data, errs, ds = assemble(src)
    assert errs == []
    mem0[F.IO_READY] = 7               # pretend some input arrived
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        acc = simulate(mem0, syms, data, max_steps=1000)
    assert acc == 7                    # ready read back as ordinary memory


# ── polling_input helper ─────────────────────────────────────────────────────

def test_polling_input_detects_load_of_ready():
    mem, listing, syms, data, errs, ds = assemble(
        "        load  ready\n        stop\n")
    assert polling_input(mem, 0) is True        # LOAD ready at pc 0
    assert polling_input(mem, 2) is False       # the STOP is not a poll


# ── step cap ─────────────────────────────────────────────────────────────────

def test_step_cap_stops_busy_poll():
    # A busy-poll on ready with no change spins forever; the cap must stop it.
    src = "loop:   load  ready\n        ifzero loop\n        stop\n"
    mem0, listing, syms, data, errs, ds = assemble(src)
    buf = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(buf):
        simulate(mem0, syms, data, max_steps=5000)
    assert "Step cap" in buf.getvalue()
