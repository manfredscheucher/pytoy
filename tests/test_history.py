"""Pure-logic tests for History — the debugger's step-back (undo) stack.

Exercises snapshot/restore without Qt, including the critical case where a STORE
mutates mem: stepping back must restore the exact pre-step memory, and the
snapshot must not alias the live state (mutating after push/pop must not leak).

Run: python3 -m pytest tests/test_history.py -q
"""

from pytoy.core import execute_one, decode
from pytoy.simulator import History, step_change


def test_empty_pop_returns_none():
    h = History()
    assert len(h) == 0
    assert h.pop() is None


def test_push_pop_roundtrips_scalars_and_containers():
    h = History()
    h.push({"acc": 5, "pc": 3, "mem": [1, 2, 3], "touched": {1}})
    assert len(h) == 1
    snap = h.pop()
    assert snap == {"acc": 5, "pc": 3, "mem": [1, 2, 3], "touched": {1}}
    assert len(h) == 0


def test_snapshot_does_not_alias_live_mem():
    # Mutating the live mem AFTER a push must not change the stored snapshot.
    h = History()
    mem = [0, 0, 0]
    h.push({"mem": mem})
    mem[0] = 99                 # mutate live state after snapshotting
    snap = h.pop()
    assert snap["mem"] == [0, 0, 0]   # snapshot untouched


def test_popped_container_is_independent_of_stack():
    # Popping twice-pushed state and mutating the result must not affect a
    # second snapshot of the same object.
    h = History()
    mem = [0, 0]
    h.push({"mem": mem})
    h.push({"mem": mem})
    a = h.pop()
    a["mem"][0] = 7            # mutate the restored copy
    b = h.pop()
    assert b["mem"] == [0, 0]  # the other snapshot is unaffected


def test_step_then_back_restores_store_exactly():
    # The real scenario: a STORE writes memory; step-back must undo the write.
    # Program: STORE into addr 2 (opcode 21, operand byte = 2). mem[2] starts 0.
    mem = [21, 2, 0]           # store -> mem[2]
    acc, pc = 7, 0
    fields = ("mem", "touched", "acc", "pc")

    h = History()
    # snapshot BEFORE executing, like the GUI does
    h.push({"mem": mem, "touched": set(), "acc": acc, "pc": pc})

    instr, arg_addr, _ = decode(mem, pc)
    pc, acc, arg_addr, _ = execute_one(mem, pc, acc)  # STORE mutates mem
    assert mem[2] == 7          # the store happened

    # now undo
    snap = h.pop()
    mem = snap["mem"]; acc = snap["acc"]; pc = snap["pc"]
    assert mem[2] == 0          # store undone
    assert acc == 7 and pc == 0 # back to pre-step acc/pc


def test_len_tracks_pushes_and_pops():
    h = History()
    assert len(h) == 0
    h.push({"a": 1}); h.push({"a": 2})
    assert len(h) == 2
    h.pop()
    assert len(h) == 1
    h.clear()
    assert len(h) == 0
