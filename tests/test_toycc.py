"""Tests for toycc (the C -> Toy CPU assembly compiler).

Pipeline under test (one stage feeds the next):

    C source ──toycc.compile_source()──▶ .toys assembly text
             ──toyasm.assemble()───────▶ memory image  (must have 0 errors)
             ──toyasm.simulate()───────▶ final accumulator (ACC)
                                         ▲ assert ACC == expected

For the example programs the expected result lives WITH the data: each
`examples/c/*.toyc` file carries a machine-readable `// expect: N`
annotation, so adding a new example needs no change to this test file.
"""

import io
import os
import re
import glob
import contextlib

import pytest

from pytoy.assembler import assemble
from pytoy.simulator import simulate
from pytoy.core import execute_one
from pytoy.compiler import (compile_source, CompileError, lex, Parser,
                            build_call_graph, find_recursive)


def _parse(src):
    return Parser(lex(src)).parse_program()


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'examples', 'c')


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


def run_c_read_mem(src, name="test.toyc"):
    """Full pipeline that also returns the final memory image + symbol table,
    so a test can read arrays (or any data byte) out of memory after the run.
    Runs the real fetch/execute loop to STOP (simulate() hides its memory)."""
    asm = compile_c(src, name)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"assembler errors: {errors}\n--- asm ---\n{asm}"
    mem = list(mem)
    acc, pc, steps = 0, 0, 0
    while steps < 1_000_000:
        if mem[pc] == 0:   # STOP
            break
        pc, acc, _arg, _stopped = execute_one(mem, pc, acc)
        steps += 1
    else:
        raise AssertionError("program did not halt")
    return acc, mem, syms


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
    for expected in {'fibonacci_iter.toyc', 'multiply.toyc', 'sevenfold.toyc', 'sum_array.toyc', 'max_array.toyc'}:
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


# ── Fixed-size local arrays (self-modifying indexed access) ─────────────────

def test_array_init_and_constant_index_sum():
    assert run_c(wrap("int a[3]={5,1,4}; return a[0]+a[1]+a[2];")) == 10

def test_array_write_constant_index():
    assert run_c(wrap("int a[3]={1,2,3}; a[1]=9; return a[1];")) == 9

def test_array_read_variable_index():
    assert run_c(wrap("int a[4]={10,20,30,40}; int i=2; return a[i];")) == 30

def test_array_write_variable_index():
    assert run_c(wrap("int a[3]={0,0,0}; int i=1; a[i]=7; return a[i];")) == 7

def test_array_partial_init_zero_fills():
    assert run_c(wrap("int a[4]={1,2}; return a[2]+a[3];")) == 0

def test_array_no_init_defaults_zero():
    assert run_c(wrap("int a[3]; return a[0]+a[1]+a[2];")) == 0

def test_array_index_by_expression():
    assert run_c(wrap("int a[5]={0,0,0,0,9}; int i=2; return a[i+2];")) == 9

def test_array_compound_index_assign():
    assert run_c(wrap("int a[3]={1,2,3}; a[2]+=10; return a[2];")) == 13

def test_array_size_must_be_constant():
    with pytest.raises(CompileError):
        compile_c(wrap("int n=3; int a[n]; return a[0];"))

def test_array_too_many_initializers_rejected():
    with pytest.raises(CompileError):
        compile_c(wrap("int a[2]={1,2,3}; return a[0];"))

def test_array_in_recursive_function_rejected():
    """Arrays aren't saved across recursive calls, so a recursive function
    with a local array would silently miscompile — reject it instead."""
    with pytest.raises(CompileError, match="recursive.*array"):
        compile_source("int r(int n){int b[2]; b[0]=n; if(n==0)return 0;"
                       " return b[0]+r(n-1);} int main(void){return r(3);}", "t")

def test_array_and_scalar_same_name_rejected():
    with pytest.raises(CompileError, match="declared twice"):
        compile_c(wrap("int a[3]; int a; return 0;"))


BUBBLE_SORT_C = """int main(void){
  int a[10] = {3,1,4,1,5,9,2,6,5,3};
  int i = 0;
  while (i < 10) {
    int j = 0;
    while (j < 9) {
      if (a[j] > a[j+1]) {
        int t = a[j];
        a[j] = a[j+1];
        a[j+1] = t;
      }
      j = j + 1;
    }
    i = i + 1;
  }
  return a[0];
}
"""

def test_bubblesort_returns_smallest():
    """The iterative bubble sort of the 10 pi digits returns a[0] = 1."""
    assert run_c(BUBBLE_SORT_C) == 1

def test_bubblesort_full_array():
    """The whole array must be sorted in memory, not just a[0] in ACC."""
    acc, mem, syms = run_c_read_mem(BUBBLE_SORT_C)
    base = syms['arr_a']
    arr = [mem[base + k] for k in range(10)]
    assert arr == [1, 1, 2, 3, 3, 4, 5, 5, 6, 9]
    assert acc == 1

def test_bubblesort_fits_256_bytes():
    asm = compile_c(BUBBLE_SORT_C)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"bubble sort does not fit: {errors}"
    size = max(a for a, *_ in listing if a is not None) + 1
    assert size <= 256


# ── Pointers (&x, *p, int*) and array-decays-to-pointer parameters ──────────

def test_pointer_write_changes_target():
    """*p = v through a pointer to x changes x itself."""
    assert run_c("int main(void){ int x=5; int *p; p=&x; *p=9; return x; }") == 9

def test_pointer_read_through_deref():
    assert run_c("int main(void){ int x=7; int *p=&x; return *p; }") == 7

def test_pointer_decl_with_init_addressof():
    """int *p = &x; then *p reads x."""
    assert run_c("int main(void){ int x=42; int *p=&x; return *p; }") == 42

def test_pointer_swap():
    """Swap two locals via pointers to them."""
    src = ("int main(void){ int a=3; int b=8; int *pa=&a; int *pb=&b;"
           " int t=*pa; *pa=*pb; *pb=t; return a; }")
    assert run_c(src) == 8

def test_pointer_deref_compound_assign():
    """*p += v accumulates through the pointer."""
    assert run_c("int main(void){ int x=4; int *p=&x; *p += 6; return x; }") == 10

def test_addressof_array_element():
    """&a[i] yields an element address; *(&a[i]) reads that element."""
    assert run_c(wrap("int a[3]={7,8,9}; int *p=&a[1]; return *p;")) == 8

def test_array_decays_to_pointer_param_read():
    """int f(int a[], int n) reads main's array through the passed base addr."""
    src = ("int suma(int a[], int n){ int s=0; int i=0;"
           " while(i<n){ s=s+a[i]; i=i+1; } return s; }"
           " int main(void){ int v[3]={4,5,6}; return suma(v, 3); }")
    assert run_c(src) == 15

def test_pointer_param_mutates_caller_local():
    """Passing &x to a function that writes *p must change main's x — the value
    must survive the call's save/restore (address-taken locals aren't saved)."""
    src = ("int inc(int *p){ *p = *p + 1; return 0; }"
           " int main(void){ int x=5; inc(&x); inc(&x); return x; }")
    assert run_c(src) == 7

def test_addressof_local_in_recursive_function_rejected():
    """A pointer to a local is a pointer to that local's single global slot,
    which the recursion save/restore stack can't follow — reject it instead of
    silently miscompiling (mirrors the recursive-local-array rejection)."""
    src = ("int nop(int *p){ return 0; }"
           " int f(int n){ int x; x=n; nop(&x);"
           " if(n==0) return x; return x + f(n-1); }"
           " int main(void){ return f(3); }")
    with pytest.raises(CompileError, match="recursive.*address"):
        compile_c(src)

def test_array_decays_to_pointer_param_write():
    """A function writing a[i] on an array parameter mutates main's array."""
    src = ("int fill(int a[], int n){ int i=0;"
           " while(i<n){ a[i]=i+1; i=i+1; } return 0; }"
           " int main(void){ int v[3]={0,0,0}; fill(v,3); return v[0]+v[1]+v[2]; }")
    assert run_c(src) == 6


# ── Bubble sort as a function taking the array by pointer ────────────────────

BUBBLE_SORT_FN_C = """
int bubblesort(int a[], int n){
  int i; int j; int t;
  i=0;
  while(i<n){
    j=0;
    while(j<n-1-i){
      if(a[j]>a[j+1]){ t=a[j]; a[j]=a[j+1]; a[j+1]=t; }
      j=j+1;
    }
    i=i+1;
  }
  return 0;
}
int main(void){ int a[10]={3,1,4,1,5,9,2,6,5,3}; bubblesort(a, 10); return a[0]; }
"""

def test_bubblesort_fn_returns_smallest():
    assert run_c(BUBBLE_SORT_FN_C) == 1

def test_bubblesort_fn_sorts_mains_array_in_place():
    """The function sorts main's array through the decayed pointer; read the
    sorted result straight out of memory."""
    acc, mem, syms = run_c_read_mem(BUBBLE_SORT_FN_C)
    base = syms['arr_a']
    arr = [mem[base + k] for k in range(10)]
    assert arr == [1, 1, 2, 3, 3, 4, 5, 5, 6, 9]
    assert acc == 1

def test_bubblesort_fn_fits_256_bytes():
    asm = compile_c(BUBBLE_SORT_FN_C)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"bubble sort fn does not fit: {errors}"
    size = max(a for a, *_ in listing if a is not None) + 1
    assert size <= 256


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

def test_call_to_undefined_function_rejected():
    with pytest.raises(CompileError, match="undefined function"):
        compile_source("int main(void){ return nope(1); }", "t")

def test_no_main_rejected():
    with pytest.raises(CompileError, match="no 'main'"):
        compile_source("int f(void){ return 1; }", "t")

def test_duplicate_function_rejected():
    with pytest.raises(CompileError, match="more than once"):
        _parse("int f(void){return 1;} int f(void){return 2;} int main(void){return 0;}")


# ── Functions (non-recursive: global-slots + marker-dispatch codegen) ───────

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

def test_three_call_sites_each_result_preserved():
    """Regression: f__ret is a shared slot; several calls in one expression
    must each keep their own value (this once returned 3*last instead of the
    sum). sq(2)+sq(3)+sq(4) = 4+9+16 = 29."""
    src = "int sq(int x){return x*x;} int main(void){return sq(2)+sq(3)+sq(4);}"
    assert run_c(src) == 29

def test_function_calling_another_function():
    """Regression: a callee reached only via another function (not main) must
    still get its slots + body emitted. quad calls dbl; main calls quad."""
    src = ("int dbl(int x){return x+x;} int quad(int x){return dbl(dbl(x));}"
           " int main(void){return quad(5);}")
    assert run_c(src) == 20

def test_call_in_loop_repeated():
    src = ("int inc(int x){return x+1;}"
           " int main(void){int i=0;int c=0;while(i<5){c=inc(c);i=i+1;}return c;}")
    assert run_c(src) == 5

def test_deeply_chained_calls():
    src = ("int a(int x){return x+1;} int b(int x){return x+2;}"
           " int main(void){return a(b(a(0)));}")
    assert run_c(src) == 4

def test_nested_call_to_same_function():
    """Regression: f(1, f(2,3)) — the inner call to the SAME function must not
    clobber the outer call's param slots before it jumps. Args are all
    materialised into temps before any param slot is written. 1*10+23 = 33."""
    src = "int f(int a,int b){return a*10+b;} int main(void){return f(1, f(2,3));}"
    assert run_c(src) == 33

def test_nested_same_function_both_args():
    src = "int f(int a,int b){return a*10+b;} int main(void){return f(f(1,2),f(3,4));}"
    assert run_c(src) == 154   # (1*10+2)=12, (3*10+4)=34, 12*10+34

# ── Recursion (uniform save/restore + real stack) ───────────────────────────

def test_fib4_liveness():
    """The critical liveness case from the design note: fib(4) must be 3, NOT 2.
    A naive "save all slots" scheme drops the temp holding fib(n-1) while
    fib(n-2) runs and miscompiles this to 2 (see doc/design/
    recursion-codegen.md)."""
    src = ("int fib(int n){ if(n<2) return n; return fib(n-1)+fib(n-2); }"
           " int main(void){ return fib(4); }")
    assert run_c(src) == 3

def test_fib_more():
    fib = ("int fib(int n){ if(n<2) return n; return fib(n-1)+fib(n-2); }"
           " int main(void){ return fib(%d); }")
    assert run_c(fib % 6) == 8
    assert run_c(fib % 10) == 55

def test_recursive_factorial():
    src = ("int fact(int n){ if(n==0) return 1; return n*fact(n-1); }"
           " int main(void){ return fact(5); }")
    assert run_c(src) == 120

def test_mutual_recursion():
    src = ("int is_even(int n){if(n==0)return 1;return is_odd(n-1);}"
           " int is_odd(int n){if(n==0)return 0;return is_even(n-1);}"
           " int main(void){return is_even(%d);}")
    assert run_c(src % 6) == 1
    assert run_c(src % 7) == 0

def test_recursive_subtractive_gcd():
    src = ("int g(int a,int b){ if(a==b) return a; if(a>b) return g(a-b,b);"
           " return g(a,b-a);} int main(void){return g(48,36);}")
    assert run_c(src) == 12

def test_fib6_fits_256_bytes():
    """The recursive fib(6) program must fit the 256-byte machine (no 'too big'
    assembler error) and still compute 8."""
    src = ("int fib(int n){ if(n<2) return n; return fib(n-1)+fib(n-2); }"
           " int main(void){ return fib(6); }")
    asm = compile_c(src)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"fib(6) does not fit: {errors}"
    assert run_asm(asm) == 8


def _program_size(asm):
    """Bytes of code+data the assembler lays down for a .toys program."""
    _mem, listing, _syms, _da, errors, _ds = assemble(asm)
    assert errors == [], errors
    return max(a for a, *_ in listing if a is not None) + 1

def test_optimize_flag_shrinks_nonrecursive_program():
    """With -O, save/restore is dropped around calls whose caller is not
    recursive — so a program of only non-recursive functions must get SMALLER,
    with the SAME result."""
    src = ("int sq(int x){return x*x;}"
           " int main(void){return sq(2)+sq(3)+sq(4);}")
    plain = compile_source(src, "t", optimize=False)
    opt = compile_source(src, "t", optimize=True)
    assert run_asm(plain) == 29
    assert run_asm(opt) == 29
    assert _program_size(opt) < _program_size(plain)

def test_optimize_flag_keeps_recursive_results():
    """-O must never change results: recursive callers keep their save/restore."""
    src = ("int fib(int n){ if(n<2) return n; return fib(n-1)+fib(n-2); }"
           " int main(void){ return fib(6); }")
    assert run_asm(compile_source(src, "t", optimize=True)) == 8

def test_deep_recursion_fits_with_optimize():
    """A program that overflows the stack without -O (data ends too high,
    little stack room) fits and is correct WITH -O, because -O drops the
    unnecessary save/restore in the non-recursive caller (main), leaving more
    room. This documents the 256-byte stack limit and the -O workaround.
    Without -O this same program silently overflows — see the compiler README's
    'recursion depth' note; the CLI warns about low stack space."""
    src = ("int f(int n){ if(n==0) return 0; return f(n-1)+1; }"
           " int main(void){ return f(2)+f(3)+f(4); }")   # = 9
    assert run_asm(compile_source(src, "t", optimize=True)) == 9


# ── Optimizations (all opt-in via Opts; off by default) ──────────────────────
# These pin correctness (results unchanged, mod-256 exact) AND the size win,
# so a future refactor can't silently undo them. They also check that the
# DEFAULT (no flags) output stays unoptimized — the readable translation.

from pytoy.compiler import Opts

def _fold(src):
    return compile_source(wrap(src), "t", opts=Opts(fold=True))

def _compact(src):
    return compile_source(wrap(src), "t", opts=Opts(compact=True))

def _safecmp(src):
    return compile_source(wrap(src), "t", opts=Opts(safe_compare=True))

def test_fold_constant_arithmetic():
    """All-constant subexpressions fold at compile time (mod 256)."""
    cases = [("return 3 + 4;", 7), ("return 10 - 25;", (10 - 25) & 0xFF),
             ("return 200 + 100;", 300 & 0xFF), ("return 6 * 7;", 42),
             ("return 1 << 3;", 8), ("return 200 >> 7;", 1),
             ("return 12 & 10;", 8), ("return 5 | 2;", 7),
             ("return 6 ^ 3;", 5), ("return ~15;", 240)]
    for src, want in cases:
        assert run_asm(_fold(src)) == want, src

def test_fold_shrinks_constant_expr():
    """3 + 4 folds to a single load, not load+add of two constants."""
    folded = _fold("return 3 + 4;")
    unfolded_size = _program_size(_fold("int x=3; return x + 4;"))
    assert run_asm(folded) == 7
    assert _program_size(folded) < unfolded_size

def test_fold_identity_ops():
    """Identity operations simplify away; results unchanged."""
    for expr, want in [("x + 0", 42), ("x - 0", 42), ("x | 0", 42),
                       ("x ^ 0", 42), ("x & 255", 42), ("x << 0", 42),
                       ("x >> 0", 42), ("x * 1", 42), ("~~x", 42),
                       ("- -x", 42)]:
        assert run_asm(_fold(f"int x=42; return {expr};")) == want, expr

def test_fold_multiply_by_zero_and_one():
    """x*1 -> x and x*0 -> 0 drop the whole repeated-add loop."""
    mul1 = _fold("int x=42; return x * 1;")
    mul_real = _fold("int x=42; int y=3; return x * y;")
    assert run_asm(mul1) == 42
    assert run_asm(_fold("int x=42; return x * 0;")) == 0
    assert _program_size(mul1) < _program_size(mul_real)

def test_fold_off_by_default():
    """Without the fold flag, constant expressions are NOT folded."""
    asm = compile_c(wrap("return 3 + 4;"))
    assert run_asm(asm) == 7
    assert "add" in asm        # still emits a runtime add, not a folded load

def test_constant_shift_no_count_spill():
    """With compact codegen, a constant shift unrolls to right/left only; it
    must not load/store the (unused) shift count into a temp."""
    asm = _compact("int x=200; return x >> 7;")
    assert run_asm(asm) == 1
    assert "store t" not in asm, asm

def test_variable_shift_still_works():
    """The runtime (variable) shift path is unchanged, with and without compact."""
    assert run_asm(_compact("int x=200; int n=3; return x >> n;")) == 25
    assert run_c(wrap("int x=200; int n=3; return x >> n;")) == 25
    assert run_c(wrap("int x=1; int n=5; return x << n;")) == 32

def test_compare_zero_no_dead_sub():
    """With compact codegen, `x != 0` / `x == 0` drop the dead `sub c_0`."""
    ne = _compact("int x=5; if (x != 0) return 1; return 0;")
    assert run_asm(ne) == 1
    assert "sub   c_0" not in ne and "sub c_0" not in ne, ne
    assert run_asm(_compact("int x=0; if (x == 0) return 7; return 0;")) == 7
    assert run_asm(_compact("int x=3; if (x == 0) return 7; return 9;")) == 9

def test_unary_minus_no_spill_for_var():
    """With compact codegen, -x on a plain var subtracts from 0, no spill temp."""
    asm = _compact("int x=5; return -x;")
    assert run_asm(asm) == 251        # -5 mod 256
    assert "store t" not in asm, asm

def test_compact_off_by_default():
    """Without the compact flag, -x still spills (unoptimized but correct)."""
    assert run_c(wrap("int x=5; return -x;")) == 251

def test_prefer_no_stack_drops_sp_when_no_recursion():
    """--prefer-no-stack omits the sp byte for a non-recursive program, but
    keeps it (and stays correct) when a function recurses."""
    flat = compile_source("int add(int a,int b){return a+b;}"
                          " int main(void){return add(2,3);}", "t",
                          opts=Opts(prefer_no_stack=True))
    assert run_asm(flat) == 5
    assert "sp:" not in flat, flat
    rec = compile_source("int f(int n){if(n==0)return 0;return f(n-1)+1;}"
                         " int main(void){return f(3);}", "t",
                         opts=Opts(prefer_no_stack=True))
    assert run_asm(rec) == 3
    assert "sp:" in rec        # recursion still gets its stack

def test_optimize_all_on_preserves_results():
    """-O (everything on) must not change any result."""
    for src, want in [("int x=42; return x*1 + 0;", 42),
                      ("int x=5; return -x;", 251),
                      ("return 3 + 4;", 7),
                      ("int x=0; if (x==0) return 7; return 9;", 7)]:
        got = run_asm(compile_source(wrap(src), "t", opts=Opts.all_on()))
        assert got == want, src

def test_optimizations_preserve_examples():
    """Every committed C example still produces its // expect: value, both at
    default (no opts) and with everything on."""
    for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.toyc"))):
        src = open(path).read()
        m = re.search(r"//\s*expect:\s*(\d+)", src, re.IGNORECASE)
        if not m:
            continue
        want = int(m.group(1))
        name = os.path.basename(path)
        assert run_c(src, name) == want, f"{name} (default)"
        assert run_asm(compile_source(src, name, opts=Opts.all_on())) == want, \
            f"{name} (-O)"


# ── safe_compare: full unsigned comparison (opt-in, correctness/size trade) ───
# The default bit-7 comparison is correct only for operands < 128 apart.
# safe_compare makes all six relational ops correct over the full 0..255 range.

def test_default_compare_wrong_for_far_operands():
    """Documents the default limitation: bit-7 trick is wrong when |a-b|>=128."""
    # 10 < 200 is truly 1, but the compact bit-7 compare returns 0.
    assert run_c(wrap("int a=10; int b=200; if (a<b) return 1; return 0;")) == 0

def test_safe_compare_correct_for_far_operands():
    """safe_compare fixes every relational op for far-apart unsigned operands."""
    cases = [("a < b", 10, 200, 1), ("a < b", 200, 10, 0),
             ("a > b", 200, 10, 1), ("a > b", 10, 200, 0),
             ("a <= b", 10, 200, 1), ("a <= b", 200, 10, 0),
             ("a >= b", 200, 10, 1), ("a >= b", 10, 200, 0),
             ("a == b", 150, 150, 1), ("a != b", 150, 150, 0)]
    for expr, a, b, want in cases:
        src = f"int a={a}; int b={b}; if ({expr}) return 1; return 0;"
        got = run_asm(_safecmp(src))
        assert got == want, f"{expr} with a={a},b={b}: got {got} want {want}"

def test_safe_compare_value_context():
    """safe_compare also fixes comparisons used as a 0/1 value, not just in if."""
    assert run_asm(_safecmp("int a=10; int b=200; return a < b;")) == 1
    assert run_asm(_safecmp("int a=200; int b=10; return a < b;")) == 0

def test_safe_compare_agrees_for_small_operands():
    """For close operands, safe and default compare agree (both correct)."""
    for expr, want in [("3 < 5", 1), ("5 < 3", 0), ("4 == 4", 1),
                       ("7 > 2", 1), ("2 >= 2", 1), ("1 <= 0", 0)]:
        assert run_asm(_safecmp(f"return {expr};")) == want, expr
        assert run_c(wrap(f"return {expr};")) == want, expr

def test_safe_compare_not_in_optimize_all():
    """safe_compare is a correctness/size trade, NOT part of -O (which must not
    silently grow comparison code)."""
    assert Opts.all_on().safe_compare is False

def test_safe_compare_is_bigger():
    """safe_compare produces larger code than the default compact compare."""
    src = "int a=5; int b=9; return a < b;"
    big = _program_size(_safecmp(src))
    small = _program_size(compile_c(wrap(src)))
    assert big > small
