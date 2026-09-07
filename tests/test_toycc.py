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
from toycc import (compile_source, CompileError, lex, Parser,
                   build_call_graph, find_recursive)


def _parse(src):
    return Parser(lex(src)).parse_program()


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'compiler', 'examples')


# ── Pipeline helpers ────────────────────────────────────────────────────────

def compile_c(src, name="test.toyc"):
    """Stage 1: C source -> .toys assembly text."""
    return compile_source(src, name)


def run_asm(asm):
    """Stages 2+3: assemble the .toys text, simulate it, return ACC."""
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
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

def test_oversized_program_overflows_assembler():
    """A C program that generates more than 256 bytes must be caught (the
    toycc CLI reports the assembler's 'too big' error instead of writing a
    .toys that only fails later)."""
    body = "int a = 0;\n" + "\n".join(f"a = a + {i % 7};" for i in range(150))
    body += "\nreturn a;"
    asm = compile_c(wrap(body))
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors and "too big" in errors[0]


# ── Functions: parsing + call-graph analysis (codegen lands next step) ──────

def test_parse_multiple_functions():
    prog = _parse("int add(int a, int b){ return a+b; } int main(void){ return add(2,3); }")
    assert prog[0] == 'program'
    funcs = {f[1]: f for f in prog[1]}
    assert set(funcs) == {'add', 'main'}
    assert funcs['add'][2] == ['a', 'b']      # params

def test_inline_keyword_is_gone():
    """'inline' is no longer a keyword; the compiler chooses global-slot vs
    stack automatically. Using it as a function name is even fine, but here it
    parses as an unexpected identifier where a type is expected."""
    with pytest.raises(CompileError):
        _parse("inline int f(int x){ return x; } int main(void){ return f(1); }")

def test_call_graph_detects_self_recursion():
    funcs = _parse("int f(int n){ return f(n); } int main(void){ return f(3); }")[1]
    assert find_recursive(build_call_graph(funcs)) == {'f'}

def test_call_graph_detects_mutual_recursion():
    funcs = _parse("int a(int n){return b(n);} int b(int n){return a(n);} "
                   "int main(void){return a(1);}")[1]
    assert find_recursive(build_call_graph(funcs)) == {'a', 'b'}

def test_call_graph_non_recursive_is_empty():
    funcs = _parse("int add(int a,int b){return a+b;} "
                   "int main(void){return add(1,2);}")[1]
    assert find_recursive(build_call_graph(funcs)) == set()

def test_recursive_rejected_for_now():
    with pytest.raises(CompileError, match="recursive"):
        compile_source("int f(int n){return f(n);} int main(void){return f(1);}", "t")

def test_call_to_undefined_function_rejected():
    with pytest.raises(CompileError, match="undefined function"):
        compile_source("int main(void){ return nope(1); }", "t")

def test_no_main_rejected():
    with pytest.raises(CompileError, match="no 'main'"):
        compile_source("int f(void){ return 1; }", "t")

def test_duplicate_function_rejected():
    with pytest.raises(CompileError, match="more than once"):
        _parse("int f(void){return 1;} int f(void){return 2;} int main(void){return 0;}")


# ── Function inlining (non-recursive calls) ─────────────────────────────────

def test_inline_simple_call():
    src = "int add(int a,int b){return a+b;} int main(void){return add(2,3);}"
    assert run_c(src) == 5

def test_inline_call_with_loop_body():
    src = ("int mul(int a,int b){int r=0; int i=0; while(i<b){r=r+a; i=i+1;} return r;}"
           " int main(void){return mul(6,7);}")
    assert run_c(src) == 42

def test_inline_return_inside_if():
    src = "int max2(int a,int b){ if(a>b) return a; return b;} int main(void){return max2(3,9);}"
    assert run_c(src) == 9

def test_inline_nested_calls():
    src = ("int inc(int x){return x+1;} int add(int a,int b){return a+b;}"
           " int main(void){return add(inc(2),inc(3));}")
    assert run_c(src) == 7

def test_inline_call_in_expression_position():
    src = "int sq(int x){return x*x;} int main(void){int y = sq(4)+1; return y;}"
    assert run_c(src) == 17

def test_inline_same_function_twice_no_collision():
    src = ("int dbl(int x){return x+x;}"
           " int main(void){int a = dbl(3); int b = dbl(10); return a+b;}")
    assert run_c(src) == 26

def test_inline_call_in_if_condition():
    src = ("int nonzero(int x){return x;}"
           " int main(void){ if (nonzero(0)) { return 1; } return 2; }")
    assert run_c(src) == 2

def test_inline_call_in_while_condition():
    src = ("int below(int x){return x < 5;}"
           " int main(void){ int i=0; while (below(i)) { i = i + 1; } return i; }")
    assert run_c(src) == 5

def test_recursive_call_gives_clean_compile_error():
    """A recursive function is not supported yet, but must fail with a clean
    CompileError (not a raw traceback) so the CLI prints 'compile error: ...'."""
    with pytest.raises(CompileError, match="recursive function"):
        compile_source("int f(int n){ if(n==0) return 0; return f(n-1); } "
                       "int main(void){ return f(3); }", "t")
