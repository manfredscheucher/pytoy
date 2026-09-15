"""Pure-logic tests for line_changed_bytes() — the source panel's "this line's
byte(s) now differ from the assembled original" check, used to red-flag edited
data cells and overwritten code. No Qt needed.

Run: python3 -m pytest tests/test_line_changed.py -q
"""

from pytoy.simulator import line_changed_bytes


def test_comment_or_blank_line_never_flagged():
    mem = [1, 2, 3]
    assert line_changed_bytes(mem, mem, None, []) is False
    assert line_changed_bytes(mem, mem, 0, []) is False  # empty blist


def test_unchanged_single_byte_line():
    orig = [5, 0, 0]
    mem = [5, 0, 0]
    assert line_changed_bytes(mem, orig, 0, [5]) is False


def test_changed_data_byte_flagged():
    orig = [0, 0, 7]        # data cell at addr 2 = 7
    mem = [0, 0, 9]         # runtime STORE changed it to 9
    assert line_changed_bytes(mem, orig, 2, [7]) is True


def test_two_byte_instruction_change_in_either_byte():
    orig = [20, 5, 0]       # load 5 : opcode at 0, operand at 1
    # operand byte overwritten
    mem_op = [20, 8, 0]
    assert line_changed_bytes(mem_op, orig, 0, [20, 5]) is True
    # opcode byte overwritten
    mem_code = [22, 5, 0]
    assert line_changed_bytes(mem_code, orig, 0, [20, 5]) is True
    # neither changed
    assert line_changed_bytes(list(orig), orig, 0, [20, 5]) is False


def test_change_outside_the_line_does_not_flag_it():
    orig = [20, 5, 3]
    mem = [20, 5, 99]       # addr 2 changed, but the line owns only [0,1]
    assert line_changed_bytes(mem, orig, 0, [20, 5]) is False
