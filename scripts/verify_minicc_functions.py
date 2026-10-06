#!/usr/bin/env python3
"""Verify minicc's non-recursive function support against examples/c/.

Compiles each listed example with minicc, runs it on the Toy CPU simulator, and
checks the ACC against the file's `// expect:` value. Also checks that recursive
examples are rejected and that undefined-call / wrong-arg-count errors fire.

Run: python3 scripts/verify_minicc_functions.py
(from the repo root). Prints PASS/FAIL per case and a final summary.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pytoy.minicc import compile_source, MiniError
from pytoy.assembler import assemble
from pytoy.simulator import simulate

EX = os.path.join(ROOT, "examples", "c")

# examples that should compile+run and match their // expect: value
FUNC_OK = ["sum3", "max3", "gcd_iter", "functions"]
MAIN_ONLY_OK = ["ifelse", "sum_array", "max_array", "multiply", "sevenfold",
                "bitops", "fibonacci_array", "msb_shift_vs_mask", "count_iter"]
# recursive -> must be rejected with a recursion/stackfree message
REC_REJECT = ["count_rec", "fibonacci_rec", "gcd_rec"]
# big / uses unsupported syntax -> noted, not a pass/fail
NOTE = ["fibonacci_iter", "popcount", "sort_array_function"]


def expect(path):
    src = open(path).read()
    m = re.search(r"//\s*expect:\s*(\d+)", src, re.IGNORECASE)
    return int(m.group(1)) if m else None


def run(src, name):
    asm = compile_source(src, name)
    mem, _l, syms, data_addrs, errors, _ds = assemble(asm)
    if errors:
        raise RuntimeError(f"assembler errors: {errors}")
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return simulate(mem, syms, data_addrs), len(mem)


def main():
    fails = []
    for name in FUNC_OK + MAIN_ONLY_OK:
        path = os.path.join(EX, name + ".toyc")
        src = open(path).read()
        want = expect(path)
        try:
            got, _n = run(src, name)
            ok = got == want
            print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {got}, want {want}")
            if not ok:
                fails.append(name)
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
            fails.append(name)

    for name in REC_REJECT:
        src = open(os.path.join(EX, name + ".toyc")).read()
        try:
            compile_source(src, name)
            print(f"[FAIL] {name}: expected MiniError (recursion), compiled")
            fails.append(name)
        except MiniError as e:
            ok = "recursion" in str(e).lower() or "stackfree" in str(e).lower()
            print(f"[{'PASS' if ok else 'FAIL'}] {name}: rejected: {e}")
            if not ok:
                fails.append(name)

    # undefined call + wrong arg count
    for label, src in [
        ("undefined-call", "int main(void){ return nope(1); }"),
        ("wrong-arg-count",
         "int f(int a, int b){ return a+b; } int main(void){ return f(1); }"),
    ]:
        try:
            compile_source(src, label)
            print(f"[FAIL] {label}: expected MiniError, compiled")
            fails.append(label)
        except MiniError as e:
            print(f"[PASS] {label}: rejected: {e}")

    print("\n-- notes (big / unsupported syntax; not pass/fail) --")
    for name in NOTE:
        path = os.path.join(EX, name + ".toyc")
        src = open(path).read()
        want = expect(path)
        try:
            got, n = run(src, name)
            print(f"  {name}: got {got}, want {want}, program {n} bytes"
                  + ("" if n <= 256 else "  <-- EXCEEDS 256 bytes"))
        except Exception as e:
            print(f"  {name}: {type(e).__name__}: {e}")

    print(f"\n{'ALL REQUIRED PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
