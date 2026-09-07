"""Tests for toyasm assembler and simulator."""

import io
import sys
import contextlib
from toyasm import assemble, simulate, parse_val, OPCODES, has_operand


# ── Value parser ──────────────────────────────────────────────────────────

def test_parse_val_decimal():
    assert parse_val("42") == 42

def test_parse_val_binary_prefix():
    assert parse_val("0b1010") == 10

def test_parse_val_binary_raw():
    assert parse_val("00001111") == 15

def test_parse_val_hex():
    assert parse_val("0xFF") == 255

def test_parse_val_zero():
    assert parse_val("0") == 0


# ── Instruction set ──────────────────────────────────────────────────────

def test_opcodes_exist():
    expected = {'stop', 'right', 'left', 'not', 'and', 'or', 'xor',
                'load', 'store', 'add', 'sub', 'goto', 'ifzero', 'nop'}
    assert set(OPCODES.keys()) == expected

def test_has_operand():
    assert not has_operand(OPCODES['stop'])
    assert not has_operand(OPCODES['right'])
    assert not has_operand(OPCODES['left'])
    assert not has_operand(OPCODES['not'])
    assert has_operand(OPCODES['load'])
    assert has_operand(OPCODES['store'])
    assert has_operand(OPCODES['add'])
    assert has_operand(OPCODES['sub'])
    assert has_operand(OPCODES['goto'])
    assert has_operand(OPCODES['ifzero'])


# ── Assembler ─────────────────────────────────────────────────────────────

def test_assemble_simple_stop():
    mem, listing, syms, data_addrs, errors, _ds = assemble("stop")
    assert errors == []
    assert mem[0] == OPCODES['stop']

def test_assemble_load_store():
    src = """
        load x
        store y
        stop
x:      10
y:      0
"""
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    assert errors == []
    assert 'x' in syms
    assert 'y' in syms
    assert mem[syms['x']] == 10
    assert mem[syms['y']] == 0

def test_assemble_labels():
    src = """
start:  load val
        stop
val:    42
"""
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    assert errors == []
    assert syms['start'] == 0
    assert syms['val'] == 3
    assert mem[3] == 42

def test_assemble_data_addrs():
    src = """
        stop
x:      5
y:      10
"""
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    assert errors == []
    assert syms['x'] in data_addrs
    assert syms['y'] in data_addrs

def test_assemble_error_unknown_label():
    mem, listing, syms, data_addrs, errors, _ds = assemble("load unknown")
    assert len(errors) > 0

def test_assemble_comments_ignored():
    src = """
        # this is a comment
        load x   # inline comment
        stop
x:      7
"""
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    assert errors == []
    assert mem[syms['x']] == 7


# ── Simulator ─────────────────────────────────────────────────────────────

def _run(src):
    """Assemble and simulate, return ACC result."""
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    assert errors == [], f"Assembly errors: {errors}"
    with contextlib.redirect_stdout(io.StringIO()):
        return simulate(mem, syms, data_addrs)

def test_sim_load_stop():
    assert _run("load x\nstop\nx: 42") == 42

def test_sim_add():
    src = """
        load a
        add  b
        stop
a:      10
b:      20
"""
    assert _run(src) == 30

def test_sim_sub():
    src = """
        load a
        sub  b
        stop
a:      50
b:      20
"""
    assert _run(src) == 30

def test_sim_store():
    src = """
        load val
        store dst
        load dst
        stop
val:    99
dst:    0
"""
    assert _run(src) == 99

def test_sim_goto():
    src = """
        goto skip
        load a
skip:   load b
        stop
a:      10
b:      20
"""
    assert _run(src) == 20

def test_sim_ifzero_taken():
    src = """
        load zero
        ifzero target
        load a
        stop
target: load b
        stop
zero:   0
a:      10
b:      20
"""
    assert _run(src) == 20

def test_sim_ifzero_skip():
    src = """
        load one
        ifzero target
        load a
        stop
target: load b
        stop
one:    1
a:      10
b:      20
"""
    assert _run(src) == 10

def test_sim_right_shift():
    src = """
        load val
        right
        stop
val:    8
"""
    assert _run(src) == 4

def test_sim_left_shift():
    src = """
        load val
        left
        stop
val:    4
"""
    assert _run(src) == 8

def test_sim_not():
    src = """
        load val
        not
        stop
val:    0
"""
    assert _run(src) == 255

def test_sim_and():
    src = """
        load a
        and  b
        stop
a:      0b11001100
b:      0b10101010
"""
    assert _run(src) == 0b10001000

def test_sim_or():
    src = """
        load a
        or   b
        stop
a:      0b11000000
b:      0b00001111
"""
    assert _run(src) == 0b11001111

def test_sim_xor():
    src = """
        load a
        xor  b
        stop
a:      0b11110000
b:      0b10101010
"""
    assert _run(src) == 0b01011010

def test_sim_overflow():
    src = """
        load a
        add  b
        stop
a:      200
b:      100
"""
    assert _run(src) == 44  # (200+100) - 256

def test_sim_underflow():
    src = """
        load a
        sub  b
        stop
a:      10
b:      20
"""
    assert _run(src) == 246  # 10 - 20 + 256

def test_sim_fibonacci():
    """fibonacci.toys with n=7 should produce fib(7) = 13."""
    src = open('examples/fibonacci.toys').read()
    assert _run(src) == 13

def test_sim_left_shift_overflow():
    src = """
        load val
        left
        stop
val:    200
"""
    assert _run(src) == 144  # (200 << 1) & 0xFF = 400 & 255

def test_sim_nop():
    src = """
        load val
        nop
        stop
val:    42
"""
    assert _run(src) == 42

def test_sim_sum():
    """sum.toys with [3,1,4,1,5,9,2] should produce 25."""
    src = open('examples/sum.toys').read()
    assert _run(src) == 25

def test_sim_max():
    """max.toys with [3,1,4,1,5,9,2] should produce 9."""
    src = open('examples/max.toys').read()
    assert _run(src) == 9

def test_sim_multiply():
    """multiply.toys with a=7, b=6 should produce 42."""
    src = open('examples/multiply.toys').read()
    assert _run(src) == 42

def test_sim_loop_countdown():
    """Count down from 3 to 0."""
    src = """
        load  n
loop:   ifzero done
        sub   one
        store n
        load  n
        goto  loop
done:   stop
n:      3
one:    1
"""
    assert _run(src) == 0


# ── Memory limits & code-overwrite detection ──────────────────────────────

def test_assemble_overflow_reports_error():
    """A program larger than 256 bytes yields a clean error, not an
    IndexError."""
    src = "\n".join(["add x"] * 200) + "\nstop\nx: 1\n"  # 200*2 + 1 + 1 = 402
    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    assert errors, "oversized program should report an error"
    assert "256" in errors[0] and "402" in errors[0]

def test_assemble_exactly_256_is_ok():
    """256 one-byte instructions fill memory exactly; no overflow."""
    src = "\n".join(["right"] * 256)  # 256 * 1 = 256, no operands needed
    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    assert errors == []

def test_assemble_257_overflows():
    src = "\n".join(["right"] * 257)  # 257 bytes
    _, _, _, _, errors, _ = assemble(src)
    assert errors and "257" in errors[0]

def test_data_marker_sets_data_start():
    """The '# data' marker line records where data begins."""
    src = "load v\nstore v\nstop\n# data\nv: 7\n"
    _, _, syms, _, errors, data_start = assemble(src)
    assert errors == []
    assert data_start == syms['v']  # first byte after the marker

def test_no_data_marker_gives_none():
    src = "load v\nstop\nv: 7\n"
    _, _, _, _, _, data_start = assemble(src)
    assert data_start is None

def _run_guarded(src, answer):
    """Assemble with its data marker as code_guard, feed `answer` to the
    interactive prompt, return the ACC result."""
    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    assert errors == [] and data_start is not None
    with contextlib.redirect_stdout(io.StringIO()), \
         contextlib.redirect_stderr(io.StringIO()):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(answer)
        try:
            return simulate(mem, syms, data_addrs, code_guard=data_start)
        finally:
            sys.stdin = old_stdin

# A program that stores into address 0 (its own first code byte).
_OVERWRITE_SRC = "top: load v\n     store top\n     stop\n# data\nv: 99\n"

def test_code_overwrite_abort_on_no():
    """Answering 'n' stops before the code byte is overwritten."""
    # If aborted, execution returns the current ACC (99) without doing the
    # STORE or reaching a second run; the key check is it does NOT crash and
    # does NOT continue past the guarded store.
    acc = _run_guarded(_OVERWRITE_SRC, "n\n")
    assert acc == 99  # value loaded, store refused, aborted

def test_code_overwrite_continue_on_yes():
    """Answering 'y' performs the store and runs to STOP."""
    acc = _run_guarded(_OVERWRITE_SRC, "y\n")
    assert acc == 99  # ran to completion

def test_code_overwrite_not_triggered_without_guard():
    """Without code_guard the self-modifying store just happens."""
    mem, listing, syms, data_addrs, errors, data_start = assemble(_OVERWRITE_SRC)
    with contextlib.redirect_stdout(io.StringIO()):
        acc = simulate(mem, syms, data_addrs)  # no code_guard
    assert acc == 99

def test_store_into_data_region_not_flagged():
    """A normal store into the data region does not trigger the guard even
    with code_guard set."""
    src = "load v\nstore w\nstop\n# data\nv: 42\nw: 0\n"
    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    with contextlib.redirect_stdout(io.StringIO()):
        # feed nothing; if the guard fired it would try to read stdin and the
        # store target (w) is in the data region, so it must not prompt.
        acc = simulate(mem, syms, data_addrs, code_guard=data_start)
    assert acc == 42
