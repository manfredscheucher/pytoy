"""Tests for pytoy assembler and simulator."""

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
    mem, listing, syms, data_addrs, errors = assemble("stop")
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
    mem, listing, syms, data_addrs, errors = assemble(src)
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
    mem, listing, syms, data_addrs, errors = assemble(src)
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
    mem, listing, syms, data_addrs, errors = assemble(src)
    assert errors == []
    assert syms['x'] in data_addrs
    assert syms['y'] in data_addrs

def test_assemble_error_unknown_label():
    mem, listing, syms, data_addrs, errors = assemble("load unknown")
    assert len(errors) > 0

def test_assemble_comments_ignored():
    src = """
        # this is a comment
        load x   # inline comment
        stop
x:      7
"""
    mem, listing, syms, data_addrs, errors = assemble(src)
    assert errors == []
    assert mem[syms['x']] == 7


# ── Simulator ─────────────────────────────────────────────────────────────

def _run(src):
    """Assemble and simulate, return ACC result."""
    mem, listing, syms, data_addrs, errors = assemble(src)
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
