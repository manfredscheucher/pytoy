"""Pure-logic tests for the GUI's "change highlight" decision.

These exercise step_change() (the tiny helper _refresh_memory uses) WITHOUT
booting Qt, so they run fast and don't need PySide6.

The highlight fires on *write*, not on value change: a `load` of the value
already in ACC still lights up, and a `store` of the same value still marks the
cell. So step_change looks only at the opcode, not before/after values.

Run: python3 -m pytest tests/test_change_highlight.py -q
"""

from pytoy.core import OPCODES, execute_one
from pytoy.simulator import step_change


def test_acc_written_matches_the_executor():
    """Pin step_change's ACC-writer classification to what execute_one actually
    does, so WRITES_ACC can't silently drift from the CPU semantics. For every
    opcode, run it on a crafted memory where the operand cell differs from ACC,
    and check whether execute_one changed ACC; step_change must agree."""
    for opcode in OPCODES.values():
        # mem[1] holds an operand distinct from the initial ACC so that any
        # opcode that reads or transforms ACC produces a visibly different value.
        mem = [opcode, 1, 0b10101010] + [0] * 253
        acc_before = 0b01010101
        _, acc_after, _, _ = execute_one(mem, 0, acc_before)
        really_wrote = acc_after != acc_before
        _, acc_written = step_change(opcode, 1)
        # If the executor changed ACC, step_change must say so. (It may also flag
        # a write that happens to leave the value unchanged — that's intended,
        # "write" not "change" — so only the executor-changed case is forced.)
        if really_wrote:
            assert acc_written, f"opcode {opcode} changed ACC but step_change didn't flag it"


def test_store_records_written_cell_and_leaves_acc():
    # STORE (opcode 21) into address 42: marks the cell, does not write ACC.
    changed_cell, acc_written = step_change(21, 42)
    assert changed_cell == 42
    assert acc_written is False


def test_load_writes_acc_no_cell():
    # LOAD (opcode 20) writes ACC; two-byte op but no memory cell written.
    changed_cell, acc_written = step_change(20, 5)
    assert changed_cell is None
    assert acc_written is True


def test_load_marks_acc_even_when_value_unchanged():
    # The whole point: a load that happens to reload the same value still
    # counts as an ACC write (step_change never sees the values).
    changed_cell, acc_written = step_change(20, 5)
    assert acc_written is True


def test_one_byte_acc_op_writes_acc_no_cell():
    # RIGHT (opcode 1) writes ACC; one-byte op, arg_addr None, no cell.
    changed_cell, acc_written = step_change(1, None)
    assert changed_cell is None
    assert acc_written is True


def test_arith_ops_write_acc():
    # ADD/SUB/AND/OR/XOR/NOT/LEFT all write ACC.
    for opcode in (22, 23, 17, 18, 19, 15, 2):
        assert step_change(opcode, 3)[1] is True, opcode


def test_control_flow_and_stop_do_not_write_acc():
    # GOTO 24, IFZERO 25, STOP 0, NOP 128, unknown opcode: no ACC write, no cell.
    for opcode in (24, 25, 0, 128, 200):
        changed_cell, acc_written = step_change(opcode, 3)
        assert acc_written is False, opcode
        assert changed_cell is None, opcode
