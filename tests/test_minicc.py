"""Tests for minicc, the minimal didactic C -> Toy CPU compiler.

minicc is the stripped-down teaching compiler (pytoy/minicc.py): main() only,
no functions/recursion/stack, no optimizations. It must still compile the
single-function examples correctly. The full compiler is covered by
test_toycc.py.
"""

import io
import os
import re
import contextlib

import pytest

from pytoy.assembler import assemble
from pytoy.simulator import simulate
from pytoy.minicc import compile_source, MiniError

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), '..', 'examples', 'c')


def run(src, name="t.toyc"):
    """Full pipeline: C source -> ACC."""
    asm = compile_source(src, name)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"assembler errors: {errors}\n{asm}"
    with contextlib.redirect_stdout(io.StringIO()):
        return simulate(mem, syms, data_addrs)


def wrap(body):
    return "int main(void) {\n" + body + "\n}\n"


# ── core language ────────────────────────────────────────────────────────────

def test_arithmetic():
    assert run(wrap("return 2 + 3;")) == 5
    assert run(wrap("int a=10; int b=3; return a - b;")) == 7
    assert run(wrap("return 200 + 100;")) == 44          # wraps mod 256
    assert run(wrap("int x=6; int y=7; return x * y;")) == 42

def test_bitwise_and_shift():
    assert run(wrap("return 12 & 10;")) == 8
    assert run(wrap("return 5 | 2;")) == 7
    assert run(wrap("return 6 ^ 3;")) == 5
    assert run(wrap("int x=15; return ~x;")) == 240
    assert run(wrap("int x=3; return x << 2;")) == 12
    assert run(wrap("int x=200; return x >> 3;")) == 25

def test_hex_literals():
    assert run(wrap("return 0xF0 & 0x3C;")) == 0x30

def test_unary_minus():
    assert run(wrap("int x=5; return -x;")) == 251        # -5 mod 256

def test_if_else():
    src = wrap("int a=7; int b=12; int r;"
               " if (a < b) { r = b - a; } else { r = a - b; } return r;")
    assert run(src) == 5

def test_while_loop():
    src = wrap("int i=0; int s=0; while (i < 5) { s = s + i; i = i + 1; }"
               " return s;")
    assert run(src) == 10                                  # 0+1+2+3+4

def test_comparisons():
    for expr, want in [("3 < 5", 1), ("5 < 3", 0), ("4 == 4", 1),
                       ("4 != 4", 0), ("7 > 2", 1), ("2 >= 2", 1),
                       ("1 <= 0", 0)]:
        assert run(wrap(f"return {expr};")) == want, expr

def test_arrays():
    src = wrap("int a[4] = {10, 20, 30, 40}; int i=2; return a[i];")
    assert run(src) == 30

def test_array_write_and_read():
    src = wrap("int a[3]; a[0]=5; a[1]=9; a[2]=1;"
               " int i=1; a[i] = a[i] + 100; return a[1];")
    assert run(src) == 109


# ── examples it is expected to handle ────────────────────────────────────────

MINICC_OK = [
    "ifelse", "sum_array", "max_array", "multiply", "sevenfold",
    "bitops", "fibonacci_array", "msb_shift_vs_mask",
]

@pytest.mark.parametrize("name", MINICC_OK)
def test_example_matches_expect(name):
    path = os.path.join(EXAMPLES_DIR, name + ".toyc")
    src = open(path).read()
    want = int(re.search(r"//\s*expect:\s*(\d+)", src, re.IGNORECASE).group(1))
    assert run(src, name + ".toyc") == want


# ── deliberate limits (documented, not bugs) ─────────────────────────────────

def test_rejects_functions():
    """Only main() is allowed; a second function is a parse error."""
    with pytest.raises(MiniError):
        compile_source("int f(void){return 1;} int main(void){return f();}", "t")

def test_rejects_variable_shift():
    with pytest.raises(MiniError):
        compile_source(wrap("int x=4; int n=2; return x >> n;"), "t")

def test_rejects_unknown_variable():
    with pytest.raises(MiniError):
        compile_source(wrap("return y;"), "t")

def test_rejects_second_function_clearly():
    """A second function gives a clear 'main only' message, not a raw parse error."""
    with pytest.raises(MiniError, match="only.*main"):
        compile_source("int f(void){return 1;} int main(void){return 0;}", "t")

def test_rejects_compound_assignment_clearly():
    """`x += 3` explains that compound assignment is unsupported."""
    with pytest.raises(MiniError, match="compound assignment"):
        compile_source(wrap("int x=5; x += 3; return x;"), "t")
