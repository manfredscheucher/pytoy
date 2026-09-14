"""Pure-logic tests for the GUI's "change highlight" decision.

These exercise step_change() (the tiny helper _refresh_memory uses) WITHOUT
booting Qt, so they run fast and don't need PySide6.

Run: python3 -m pytest tests/test_change_highlight.py -q
"""

from pytoy.simulator import step_change


def test_store_records_written_cell():
    # STORE (opcode 21) into address 42; ACC unchanged by a store.
    changed_cell, acc_changed = step_change(21, 42, acc_before=7, acc_after=7)
    assert changed_cell == 42
    assert acc_changed is False


def test_load_changing_acc_sets_acc_changed_no_cell():
    # LOAD (opcode 20) that brings a new value into ACC.
    changed_cell, acc_changed = step_change(20, 5, acc_before=0, acc_after=99)
    assert changed_cell is None
    assert acc_changed is True


def test_load_same_value_does_not_set_acc_changed():
    # LOAD of a value equal to the current ACC: no change.
    changed_cell, acc_changed = step_change(20, 5, acc_before=42, acc_after=42)
    assert changed_cell is None
    assert acc_changed is False


def test_one_byte_op_changing_acc_sets_acc_changed_no_cell():
    # RIGHT (opcode 1) shifts ACC; one-byte op has arg_addr None, no cell.
    changed_cell, acc_changed = step_change(1, None, acc_before=8, acc_after=4)
    assert changed_cell is None
    assert acc_changed is True
