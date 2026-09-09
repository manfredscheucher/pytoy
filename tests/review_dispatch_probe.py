#!/usr/bin/env python3
"""Skeptical fresh-eyes probes for the marker-dispatch call scheme in
compiler/toycc.py. Compiles each C program, assembles+simulates via toyasm,
and checks the final ACC against the expected value.

Run: python3 tests/review_dispatch_probe.py
"""
import os
import sys
import io
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pytoy.assembler import assemble
from pytoy.simulator import simulate
from pytoy import compiler as toycc


def run(src):
    asm = toycc.compile_source(src, "probe.toyc")
    mem, listing, syms, data_addrs, errors, data_start = assemble(asm)
    if errors:
        return ('ERR', errors, asm)
    with contextlib.redirect_stdout(io.StringIO()):
        acc = simulate(mem, syms, data_addrs)
    return ('OK', acc, asm)


CASES = [
    # (label, source, expected_acc)  expected None => expect compile error
    ("nested same fn f(1,f(2,3))",
     "int f(int a,int b){return a*10+b;} int main(void){return f(1, f(2,3));}",
     33),
    ("5 call sites of one fn",
     "int inc(int a){return a+1;}"
     "int main(void){int s=0; s=inc(1); s=s+inc(10); s=s+inc(20);"
     "s=s+inc(30); s=s+inc(40); return s;}",
     # inc(1)=2 ; then +inc(10)=11 ->13 ; +inc(20)=21 ->34 ; +inc(30)=31 ->65 ; +inc(40)=41 ->106
     106),
    ("6 call sites, last returns",
     "int id(int a){return a;}"
     "int main(void){int s=0;s=id(1);s=s+id(2);s=s+id(3);s=s+id(4);"
     "s=s+id(5);return s+id(6);}",
     21),
    ("arg order clobber f(a,g(b))",
     "int g(int b){return b+100;}"
     "int f(int a,int b){return a;}"   # returns first arg
     "int main(void){return f(7, g(3));}",
     7),
    ("nested same fn deeper f(f(1,2),3)",
     "int f(int a,int b){return a*10+b;}"
     "int main(void){return f(f(1,2),3);}",
     # f(1,2)=12 ; f(12,3)=123 mod256 =123
     123),
    ("indirect chain a->b->c",
     "int c(int x){return x+1;}"
     "int b(int x){return c(x)+1;}"
     "int a(int x){return b(x)+1;}"
     "int main(void){return a(10);}",
     13),
    ("callee only via callee (transitive)",
     "int helper(int x){return x*2;}"
     "int mid(int x){return helper(x)+1;}"
     "int main(void){return mid(5);}",
     11),
    ("fn that falls off end (no return)",
     "int noret(int a){int x; x=a;}"
     "int main(void){return noret(9);}",
     # f__ret default 0
     0),
    ("two calls same fn in one expr",
     "int sq(int a){int r; r=a*a; return r;}"
     "int main(void){return sq(3)+sq(4);}",
     25),
    ("nested same fn as both args f(f(1,2),f(3,4))",
     "int f(int a,int b){return a*10+b;}"
     "int main(void){return f(f(1,2),f(3,4));}",
     # inner f(1,2)=12, f(3,4)=34, outer f(12,34)=12*10+34=154
     154),
    ("mutual recursion rejected",
     "int a(int x){return b(x);} int b(int x){return a(x);}"
     "int main(void){return a(1);}",
     None),
    ("self recursion rejected",
     "int f(int x){return f(x);} int main(void){return f(1);}",
     None),
    ("call as bare statement (void-ish)",
     "int f(int a){return a;} int main(void){f(5); return 1;}",
     1),
]


def main():
    fails = []
    for label, src, expected in CASES:
        if expected is None:
            status, val, asm = 'SKIP', None, ''
        else:
            status, val, asm = run(src)
        if expected is None:
            # expect compile error
            try:
                toycc.compile_source(src, "x")
                ok = False
                got = "compiled OK (no error)"
            except toycc.CompileError as e:
                ok = True
                got = f"CompileError: {e}"
            print(f"[{'PASS' if ok else 'FAIL'}] {label} -> {got}")
            if not ok:
                fails.append((label, "expected CompileError", got, asm))
            continue

        if status == 'ERR':
            print(f"[FAIL] {label} -> assemble errors: {val}")
            fails.append((label, expected, f"asm errors {val}", asm))
            continue
        ok = (val == expected)
        print(f"[{'PASS' if ok else 'FAIL'}] {label} -> got {val}, expected {expected}")
        if not ok:
            fails.append((label, expected, val, asm))

    print()
    if fails:
        print(f"{len(fails)} FAILURE(S):")
        for label, exp, got, asm in fails:
            print("=" * 70)
            print(f"CASE: {label}")
            print(f"expected {exp}, got {got}")
    else:
        print("all probes passed")
    return fails


if __name__ == '__main__':
    fails = main()
    sys.exit(1 if fails else 0)
