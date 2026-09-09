#!/usr/bin/env python3
"""Verify the global-slots + marker-dispatch function scheme in toycc.

Compiles a set of C programs that exercise function calls (single call site,
multiple call sites, nested calls, calls in expression position, returns inside
if, single-main), assembles + simulates each, and checks the final ACC. Also
reports the assembled byte size of a small multi-call program to confirm it fits
the 256-byte Toy CPU.

Run from anywhere:  python3 compiler/verify_functions.py
"""
import io
import os
import sys
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from pytoy.assembler import assemble            # noqa: E402
from pytoy.simulator import simulate            # noqa: E402
from pytoy.compiler import compile_source       # noqa: E402


def run(src):
    asm = compile_source(src, "verify.toyc")
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"assembler errors: {errors}\n{asm}"
    with contextlib.redirect_stdout(io.StringIO()):
        acc = simulate(mem, syms, data_addrs)
    return acc, asm


CASES = [
    ("add",
     "int add(int a,int b){return a+b;} int main(void){return add(2,3);}", 5),
    ("mul-loop",
     "int mul(int a,int b){int r=0;int i=0;while(i<b){r=r+a;i=i+1;}return r;}"
     " int main(void){return mul(6,7);}", 42),
    ("return-in-if",
     "int max2(int a,int b){if(a>b)return a;return b;}"
     " int main(void){return max2(3,9);}", 9),
    ("two-call-sites",
     "int sq(int x){return x*x;}"
     " int main(void){int a=sq(3);int b=sq(4);return a+b;}", 25),
    ("nested",
     "int inc(int x){return x+1;} int add(int a,int b){return a+b;}"
     " int main(void){return add(inc(2),inc(3));}", 7),
    ("call-in-expr",
     "int sq(int x){return x*x;} int main(void){return sq(4)+1;}", 17),
    ("single-main",
     "int main(void){int a=6;int b=7;return a*b;}", 42),
]


def main():
    ok = True
    for name, src, expected in CASES:
        acc, asm = run(src)
        status = "OK" if acc == expected else "FAIL"
        if acc != expected:
            ok = False
        print(f"[{status}] {name:16s} ACC={acc:3d} (expected {expected})")

    # byte size of the two-call-sites program
    two = "int sq(int x){return x*x;}" \
          " int main(void){int a=sq(3);int b=sq(4);return a+b;}"
    asm = compile_source(two, "size.toyc")
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    used = max(syms.values()) if syms else 0
    # count actual emitted bytes: assemble pass tracks via data_addrs + code
    # Simpler: recompute total size the way the assembler does.
    from pytoy.assembler import parse_source
    from pytoy.core import OPCODES, has_operand
    addr = 0
    for label, mn, _op, _orig in parse_source(asm):
        if mn is None:
            continue
        addr += 2 if (mn in OPCODES and has_operand(OPCODES[mn])) else 1
    print(f"\ntwo-call-sites program assembles to {addr} bytes "
          f"(fits 256: {addr <= 256})")

    print("\nALL PASS" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
