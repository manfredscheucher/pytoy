#!/usr/bin/env python3
"""Fresh-eyes probe of the toycc function-inlining pass.

Compiles + simulates tricky C programs through the real pipeline
(compile_source -> assemble -> simulate) and checks ACC against
hand-computed expected values. Run: python3 scripts/review_inliner_probe.py
"""
import io
import os
import sys
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "compiler"))

from toyasm import assemble
from toysim import simulate
from toycc import compile_source, CompileError


def run_c(src, name="probe.toyc"):
    asm = compile_source(src, name)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    if errors:
        return ("ASM-ERROR", errors, asm)
    with contextlib.redirect_stdout(io.StringIO()):
        acc = simulate(mem, syms, data_addrs)
    return ("OK", acc, asm)


CASES = []
def case(name, src, expected):
    CASES.append((name, src, expected))


# 1) nested calls f(g(x)) — evaluation order + unique prefixes
case("nested_calls", """
int inc(int x){ return x + 1; }
int dbl(int x){ return x + x; }
int main(void){
    // dbl(inc(10)) = dbl(11) = 22
    return dbl(inc(10));
}
""", 22)

# 2) same-named local in caller and callee
case("same_named_local", """
int f(int a){ int t = a + 5; return t; }
int main(void){
    int t = 100;      // caller's t must survive f's internal t
    int r = f(3);     // = 8
    return t + r;     // 108
}
""", 108)

# 3) return deep inside nested control flow (while + if)
case("return_deep_in_loop", """
int f(int n){
    while (1) {
        if (n == 0) return 5;
        n = n - 1;
    }
}
int main(void){
    return f(7);   // must exit loop -> 5
}
""", 5)

# 4) a call used in a while condition, re-evaluated each iteration
case("call_in_while_cond", """
int done(int x){ return x == 0; }
int main(void){
    int i = 5;
    int c = 0;
    while (!done(i)) {   // done re-evaluated each pass
        c = c + 1;
        i = i - 1;
    }
    return c;   // 5
}
""", 5)

# 5) same function inlined 3 times
case("inlined_three_times", """
int sq(int x){ return x * x; }
int main(void){
    return sq(2) + sq(3) + sq(4);  // 4 + 9 + 16 = 29
}
""", 29)

# 6) f(a(), b()) with observable side effects via globals — order check.
#    NOTE: this compiler has no globals mutable across calls in the usual
#    sense; emulate order sensitivity with subtraction of two calls.
case("left_right_order_sub", """
int a(void){ return 10; }
int b(void){ return 3; }
int main(void){
    return a() - b();   // must be 7, not -7 (253)
}
""", 7)

# 7) void function with no return value used as a statement, then read a var
case("void_call_stmt", """
void setup(void){ int z = 1; }
int main(void){
    setup();
    return 42;
}
""", 42)

# 8) function that falls off the end (no return) whose value is used
case("falls_off_end_value", """
int f(int x){ int y = x; }   // no return -> result temp defaults to 0
int main(void){
    return f(9) + 7;   // 0 + 7 = 7 (per doc: default 0)
}
""", 7)

# 9) two different calls to same fn in one expression, distinct args
case("two_calls_same_fn", """
int add1(int x){ return x + 1; }
int main(void){
    return add1(10) + add1(20);  // 11 + 21 = 32
}
""", 32)

# 10) nested call where inner is used inside outer's body with a local clash
case("nested_with_clash", """
int g(int x){ int r = x + 1; return r; }
int f(int x){ int r = x * 2; return r + g(x); }
int main(void){
    return f(5);  // r=10, g(5)=6 -> 16
}
""", 16)

# 11) return inside if inside while, counting iterations before return
case("return_from_nested_if_while", """
int find(int n){
    int i = 0;
    while (i < 100) {
        if (i == n) return i * 10;
        i = i + 1;
    }
    return 255;
}
int main(void){
    return find(4);  // 40
}
""", 40)

# 12) call in for-loop condition-ish via while, with body call too
case("call_in_body_and_cond", """
int pos(int x){ return x > 0; }
int dec(int x){ return x - 1; }
int main(void){
    int i = 4;
    int s = 0;
    while (pos(i)) {
        s = s + i;
        i = dec(i);
    }
    return s;  // 4+3+2+1 = 10
}
""", 10)


def main():
    fails = []
    for name, src, expected in CASES:
        try:
            status, val, asm = run_c(src)
        except (CompileError, NotImplementedError, Exception) as e:
            print(f"[EXC ] {name}: {type(e).__name__}: {e}")
            fails.append((name, "exception", str(e), None))
            continue
        if status != "OK":
            print(f"[ERR ] {name}: {val}")
            fails.append((name, "asm-error", val, asm))
            continue
        ok = (val == expected)
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {name}: got {val}, expected {expected}")
        if not ok:
            fails.append((name, "wrong", val, asm))

    print()
    if fails:
        print(f"{len(fails)} FAILURE(S):")
        for name, why, val, asm in fails:
            print(f"  - {name}: {why} ({val})")
            if asm:
                print("    --- asm ---")
                for line in asm.splitlines():
                    print("    " + line)
    else:
        print("ALL PROBES PASSED")


if __name__ == "__main__":
    main()
