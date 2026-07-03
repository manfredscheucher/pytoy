"""Tests for toycc (the C -> Toy CPU assembly compiler).

Pipeline under test (one stage feeds the next):

    C source ──toycc.compile_source()──▶ .toys assembly text
             ──toyasm.assemble()───────▶ memory image  (must have 0 errors)
             ──toyasm.simulate()───────▶ final accumulator (ACC)
                                         ▲ assert ACC == expected

For the example programs the expected result lives WITH the data: each
`compiler/examples/*.toyc` file carries a machine-readable `// expect: N`
annotation, so adding a new example needs no change to this test file.
"""

import io
import os
import re
import glob
import contextlib

import pytest

from toyasm import assemble, simulate
from toycc import compile_source, CompileError


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'compiler', 'examples')


# ── Pipeline helpers ────────────────────────────────────────────────────────

def compile_c(src, name="test.toyc"):
    """Stage 1: C source -> .toys assembly text."""
    return compile_source(src, name)


def run_asm(asm):
    """Stages 2+3: assemble the .toys text, simulate it, return ACC."""
    mem, listing, syms, data_addrs, errors = assemble(asm)
    assert errors == [], f"assembler errors: {errors}\n--- asm ---\n{asm}"
    with contextlib.redirect_stdout(io.StringIO()):
        return simulate(mem, syms, data_addrs)


def run_c(src, name="test.toyc"):
    """Full pipeline: C source -> ACC result."""
    return run_asm(compile_c(src, name))


def wrap(body):
    """Wrap statements in a minimal int main(void) { ... }."""
    return "int main(void) {\n" + body + "\n}\n"


# ── Example programs (data-driven) ──────────────────────────────────────────

_EXPECT_RE = re.compile(r'//\s*expect:\s*(\d+)', re.IGNORECASE)


def _collect_examples():
    cases = []
    for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, '*.toyc'))):
        with open(path) as f:
            src = f.read()
        m = _EXPECT_RE.search(src)
        assert m, f"{os.path.basename(path)} is missing an '// expect: N' annotation"
        cases.append((os.path.basename(path), src, int(m.group(1))))
    return cases


EXAMPLE_CASES = _collect_examples()


def test_examples_present():
    """Guard against the examples folder silently going missing/empty."""
    names = {name for name, _, _ in EXAMPLE_CASES}
    assert names, "no .toyc examples found"
    # the ports of the assembler examples must exist
    for expected in {'fibonacci.toyc', 'multiply.toyc', 'sevenfold.toyc', 'sum.toyc', 'max.toyc'}:
        assert expected in names, f"missing example {expected}"


@pytest.mark.parametrize(
    "name,src,expected",
    EXAMPLE_CASES,
    ids=[name for name, _, _ in EXAMPLE_CASES],
)
def test_example_compiles_and_runs(name, src, expected):
    """Each example compiles, assembles cleanly, and yields its // expect value."""
    assert run_c(src, name) == expected


# ── Focused unit tests (localise failures to a single feature) ──────────────

def test_return_constant():
    assert run_c(wrap("return 42;")) == 42

def test_return_variable():
    assert run_c(wrap("int x = 7; return x;")) == 7

def test_declaration_without_init_defaults_zero():
    assert run_c(wrap("int x; return x;")) == 0

def test_addition():
    assert run_c(wrap("int a = 20; int b = 22; return a + b;")) == 42

def test_subtraction():
    assert run_c(wrap("int a = 50; int b = 8; return a - b;")) == 42

def test_multiplication_repeated_addition():
    assert run_c(wrap("int a = 6; int b = 7; return a * b;")) == 42

def test_assignment_updates_variable():
    assert run_c(wrap("int x = 1; x = 42; return x;")) == 42

def test_compound_add_assign():
    assert run_c(wrap("int x = 40; x += 2; return x;")) == 42

def test_wraparound_mod_256():
    assert run_c(wrap("int a = 200; int b = 100; return a + b;")) == 44

def test_bitwise_and():
    assert run_c(wrap("int a = 0xCC; int b = 0xAA; return a & b;")) == 0x88

def test_bitwise_or():
    assert run_c(wrap("int a = 0xC0; int b = 0x0F; return a | b;")) == 0xCF

def test_bitwise_xor():
    assert run_c(wrap("int a = 0xF0; int b = 0xAA; return a ^ b;")) == 0x5A

def test_bitwise_not():
    assert run_c(wrap("int a = 0; return ~a;")) == 255

def test_shift_left():
    assert run_c(wrap("int a = 3; return a << 2;")) == 12

def test_shift_right():
    assert run_c(wrap("int a = 40; return a >> 2;")) == 10

def test_if_taken():
    assert run_c(wrap("int x = 0; if (x == 0) { x = 5; } return x;")) == 5

def test_if_not_taken():
    assert run_c(wrap("int x = 1; if (x == 0) { x = 5; } return x;")) == 1

def test_if_else_true_branch():
    assert run_c(wrap("int a = 3; int b = 9; int r; if (a < b) { r = 1; } else { r = 2; } return r;")) == 1

def test_if_else_false_branch():
    assert run_c(wrap("int a = 9; int b = 3; int r; if (a < b) { r = 1; } else { r = 2; } return r;")) == 2

def test_equality_true():
    assert run_c(wrap("int a = 7; int b = 7; return a == b;")) == 1

def test_equality_false():
    assert run_c(wrap("int a = 7; int b = 8; return a == b;")) == 0

def test_inequality():
    assert run_c(wrap("int a = 7; int b = 8; return a != b;")) == 1

def test_while_loop_sum():
    body = "int i = 5; int s = 0; while (i != 0) { s += i; i -= 1; } return s;"
    assert run_c(wrap(body)) == 15

def test_for_loop_sum():
    body = "int s = 0; int i; for (i = 1; i <= 5; i += 1) { s += i; } return s;"
    assert run_c(wrap(body)) == 15

def test_nested_blocks():
    body = "int x = 0; if (x == 0) { if (x != 1) { x = 9; } } return x;"
    assert run_c(wrap(body)) == 9


# ── Compiler diagnostics ────────────────────────────────────────────────────

def test_line_comment_before_main_is_ignored():
    """The // expect: annotation sits before main and must not break lexing."""
    src = "// expect: 3\nint main(void) { return 3; }\n"
    assert run_c(src) == 3

def test_syntax_error_raises_compile_error():
    with pytest.raises(CompileError):
        compile_c("int main(void) { return }")
