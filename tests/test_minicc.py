"""Tests for minicc, the minimal didactic C -> Toy CPU compiler.

minicc is the stripped-down teaching compiler (pytoy/minicc.py): non-recursive
functions via global slots (no stack), no optimizations. Recursion is rejected.
The full compiler is covered by test_toycc.py.
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

def test_rejects_variable_shift():
    with pytest.raises(MiniError):
        compile_source(wrap("int x=4; int n=2; return x >> n;"), "t")

def test_rejects_unknown_variable():
    with pytest.raises(MiniError):
        compile_source(wrap("return y;"), "t")

def test_rejects_compound_assignment_clearly():
    """`x += 3` explains that compound assignment is unsupported."""
    with pytest.raises(MiniError, match="compound assignment"):
        compile_source(wrap("int x=5; x += 3; return x;"), "t")

def test_array_named_like_temp_no_collision():
    """An array named t1 / c_5 must not collide with generated temp/const labels
    (array data uses an adata_ prefix, not the bare name)."""
    # t1 would clash with the multiply temp; c_5 with the constant 5.
    assert run(wrap("int t1[2]; t1[0]=99; int r = 2*3; return t1[0];")) == 99
    assert run(wrap("int c_5[2]; c_5[0]=7; int x = 5; return c_5[0] + x;")) == 12


# ── non-recursive functions (global slots + marker dispatch) ─────────────────

def test_two_functions():
    """main calls a helper; the value comes back via the helper's return slot."""
    src = ("int add(int a, int b) { return a + b; }\n"
           "int main(void) { return add(20, 22); }\n")
    assert run(src) == 42

def test_call_in_expression():
    """A call used as an operand inside a larger expression."""
    src = ("int dbl(int x) { return x + x; }\n"
           "int main(void) { return dbl(5) + 1; }\n")
    assert run(src) == 11

def test_same_function_twice_in_expression():
    """square(a) + square(b): one body, two call sites, both via f__ret."""
    src = ("int square(int x) { return x * x; }\n"
           "int main(void) { return square(3) + square(4); }\n")
    assert run(src) == 25

def test_multiple_call_sites():
    """Three separate call sites of one helper all dispatch back correctly."""
    src = ("int inc(int x) { return x + 1; }\n"
           "int main(void) {\n"
           "    int a = inc(10);\n"
           "    int b = inc(20);\n"
           "    int c = inc(30);\n"
           "    return a + b + c;\n"    # 11 + 21 + 31 = 63
           "}\n")
    assert run(src) == 63

def test_helper_calls_helper():
    """A non-recursive chain main -> f -> g."""
    src = ("int g(int x) { return x + 1; }\n"
           "int f(int x) { return g(x) + g(x); }\n"   # 2*(x+1)
           "int main(void) { return f(10); }\n")      # 2*11 = 22
    assert run(src) == 22

def test_nested_call_as_argument():
    """square(square(x)): inner result feeds the outer call's parameter slot."""
    src = ("int square(int x) { return x * x; }\n"
           "int main(void) { return square(square(2)); }\n")   # 2^4 = 16
    assert run(src) == 16

def test_same_function_call_in_later_argument():
    """sub(y, sub(a, b)): the 2nd argument re-enters sub, which must not clobber
    the first argument's parameter slot before the outer jump."""
    src = ("int sub(int a, int b) { return a - b; }\n"
           "int main(void) { return sub(20, sub(10, 3)); }\n")  # 20 - (10-3) = 13
    assert run(src) == 13

def test_call_statement_discards_value():
    """A bare call statement runs for effect; its return value is discarded."""
    src = ("int touch(int x) { return x; }\n"
           "int main(void) { int r = 7; touch(99); return r; }\n")
    assert run(src) == 7


# ── recursion is rejected (minicc is stackfree) ──────────────────────────────

def test_rejects_direct_recursion():
    src = ("int f(int n) { if (n == 0) { return 0; } return f(n - 1); }\n"
           "int main(void) { return f(3); }\n")
    with pytest.raises(MiniError, match="recursion|stackfree"):
        compile_source(src, "t")

def test_rejects_mutual_recursion():
    """f -> g -> f is an indirect cycle and must be caught too."""
    src = ("int f(int n) { return g(n); }\n"
           "int g(int n) { return f(n); }\n"
           "int main(void) { return f(1); }\n")
    with pytest.raises(MiniError, match="recursion|stackfree"):
        compile_source(src, "t")

def test_diamond_call_graph_is_not_recursion():
    """main->f, main->g, f->h, g->h is a DAG (shared callee), not a cycle."""
    src = ("int h(int x) { return x + 1; }\n"
           "int f(int x) { return h(x); }\n"
           "int g(int x) { return h(x); }\n"
           "int main(void) { return f(10) + g(20); }\n")   # 11 + 21 = 32
    assert run(src) == 32


# ── call errors ──────────────────────────────────────────────────────────────

def test_rejects_undefined_call():
    with pytest.raises(MiniError, match="undefined"):
        compile_source("int main(void) { return nope(1); }", "t")

def test_rejects_wrong_arg_count():
    src = ("int f(int a, int b) { return a + b; }\n"
           "int main(void) { return f(1); }\n")
    with pytest.raises(MiniError, match="argument"):
        compile_source(src, "t")

def test_rejects_missing_main():
    with pytest.raises(MiniError, match="main"):
        compile_source("int f(void) { return 1; }", "t")

def test_rejects_main_with_parameters():
    """main is never called, so it gets no parameter slots; demand main(void)."""
    with pytest.raises(MiniError, match="main"):
        compile_source("int main(int x) { return x; }", "t")
