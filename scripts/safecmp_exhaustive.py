#!/usr/bin/env python3
"""
EXHAUSTIVE 256x256 check of safe_compare correctness for <,>,<=,>= in both
value and cond context, WITHOUT recompiling 65536 programs.

Sound approach: compile ONCE per (op,ctx) with two distinct placeholder input
values A0,B0 chosen to NOT collide with the structural constants 0,1,128. The
inputs a,b enter the program only through their constant data bytes c_A0 and
c_B0 (the prologue is `load c_A0; store v_a; load c_B0; store v_b`, and the
peephole may fuse a later reload straight from that same ACC/const). So patching
the two constant bytes c_A0 and c_B0 feeds arbitrary (a,b) correctly regardless
of peephole fusion. We assert c_A0 != c_B0 and neither equals 0/1/128 so the
three are distinct deduped bytes.

Earlier harness (NOP-ing the prologue) was UNSOUND: for > and <= the operands
are swapped and the peephole dropped the reload, so the init store's ACC was
load-bearing; NOP-ing it broke the program. Patching the source constant bytes
avoids that entirely.
"""
import io, sys, contextlib

import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pytoy.compiler import compile_source, Opts
from pytoy.assembler import assemble
from pytoy.simulator import simulate

A0, B0 = 37, 211   # distinct, not 0/1/128


def value_src(op):
    return f"int main(void){{ int a={A0}; int b={B0}; return a {op} b; }}"

def cond_src(op):
    return (f"int main(void){{ int a={A0}; int b={B0}; "
            f"if (a {op} b) return 1; return 0; }}")

def truth(a, b, op):
    return {'<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[op]


def prep(src):
    asm = compile_source(src, "p.toyc", opts=Opts(safe_compare=True))
    mem, listing, syms, data_addrs, errors, _ = assemble(asm)
    assert not errors, errors
    ca, cb = syms[f'c_{A0}'], syms[f'c_{B0}']
    assert ca != cb
    for forbidden in ('c_0', 'c_1', 'c_128'):
        if forbidden in syms:
            assert syms[forbidden] not in (ca, cb)
    return mem, syms, data_addrs, ca, cb


def main():
    bad = 0
    checked = 0
    for ctx, mk in (('value', value_src), ('cond', cond_src)):
        for op in ['<', '>', '<=', '>=']:
            mem0, syms, data_addrs, ca, cb = prep(mk(op))
            for a in range(256):
                for b in range(256):
                    mem = list(mem0)
                    mem[ca] = a
                    mem[cb] = b
                    with contextlib.redirect_stdout(io.StringIO()):
                        acc = simulate(mem, syms, data_addrs)
                    exp = 1 if truth(a, b, op) else 0
                    checked += 1
                    if acc != exp:
                        bad += 1
                        if bad <= 20:
                            print(f"MISMATCH {ctx} a={a} b={b} {op} -> {acc} exp {exp}")
    print(f"checked {checked} cases; mismatches: {bad}")
    print("VERDICT:", "PASS" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
