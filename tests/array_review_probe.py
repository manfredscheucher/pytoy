#!/usr/bin/env python3
"""Adversarial probe for ARRAY support in toycc. Skeptical fresh-eyes review.

Compiles small C programs, simulates them on the Toy CPU, and checks the
returned ACC (and optionally array bytes) against hand-derived expected values.

Run: python3 tests/array_review_probe.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'compiler'))

import toyasm
import toycpu
from toycc import compile_source, CompileError


def run(src, optimize=False, max_steps=200000):
    """Compile+assemble+run. Return (acc_at_stop, mem, syms, toys)."""
    toys = compile_source(src, 't', optimize=optimize)
    mem, listing, syms, data_addrs, errors, data_start = toyasm.assemble(toys)
    assert not errors, f"assemble errors: {errors}\n{toys}"
    acc, pc, steps = 0, 0, 0
    while steps < max_steps:
        next_pc, acc, arg_addr, stopped = toycpu.execute_one(mem, pc, acc)
        if stopped:
            return acc, mem, syms, toys
        pc = next_pc
        steps += 1
    raise RuntimeError("did not stop in max_steps\n" + toys)


def arr(mem, syms, name, size):
    base = syms['arr_' + name]
    return [mem[base + i] for i in range(size)]


CASES = []
def case(name, src, expected, optimize=False, check=None):
    CASES.append((name, src, expected, optimize, check))


# 1. SMC reentrancy: two indexed reads in one expression
case("1a a[i]+a[j]",
     "int main(){int a[4]={1,2,3,4}; int i=0; int j=3; return a[i]+a[j];}", 5)
case("1b swap via temp",
     "int main(){int a[4]={1,2,3,4}; int i=0; int j=3; int t=a[i]; a[i]=a[j]; a[j]=t; return a[0]*10+a[3];}",
     4*10+1)
case("1c a[i]=a[j]",
     "int main(){int a[4]={1,2,3,4}; int i=0; int j=3; a[i]=a[j]; return a[0];}", 4)
case("1d three reads a[i]+a[j]+a[k]",  # a[0]+a[1]+a[3] = 10+20+40
     "int main(){int a[4]={10,20,30,40}; int i=0;int j=1;int k=3; return a[i]+a[j]+a[k];}", 70)

# 2. index is itself an array element (indirection)
case("2a a[a[0]] -> a[2]=0",
     "int main(){int a[4]={2,0,0,9}; return a[a[0]];}", 0)
case("2b a[a[0]] -> a[1]=2",
     "int main(){int a[3]={1,2,0}; return a[a[0]];}", 2)
case("2c a[a[a[0]]]",  # a[0]=1 -> a[1]=2 -> a[2]=3
     "int main(){int a[4]={1,2,3,4}; return a[a[a[0]]];}", 3)

# 3. index with call / call in index
case("3a a[f(1)]",
     "int f(int x){return x+1;} int main(){int a[4]={5,6,7,8}; return a[f(1)];}", 7)  # f(1)=2 -> a[2]=7
case("3b a[i]=f(a[j])",
     "int f(int x){return x+100;} int main(){int a[4]={1,2,3,4}; int i=0;int j=3; a[i]=f(a[j]); return a[0];}",
     (4+100) & 0xFF)
case("3c a[f(i)]+a[g(j)]",
     "int f(int x){return x;} int g(int x){return x;}"
     "int main(){int a[4]={11,22,33,44}; int i=1;int j=2; return a[f(i)]+a[g(j)];}", 22+33)

# 1e/3d: STORE and LOAD address bytes interleaved in one statement.
# a[i] = a[j] + a[k] : one raw STORE (to &a[i]) patched, then its value needs
# two raw LOADs (&a[j], &a[k]). If the store-address patch survives across the
# value computation is the crux. a[1] = a[0]+a[3] = 1+4 = 5.
case("1e a[i]=a[j]+a[k] interleave",
     "int main(){int a[4]={1,2,3,4}; int i=1;int j=0;int k=3; a[i]=a[j]+a[k]; return a[1];}", 5)
# index is a call whose arg is itself an indexed read
case("3d a[f(a[0])]",
     "int f(int x){return x+1;} int main(){int a[4]={1,7,8,9}; return a[f(a[0])];}", 8)  # a[0]=1,f=2,a[2]=8
# two DIFFERENT arrays, indexed cross: a[b[i]]
case("3e a[b[i]]",
     "int main(){int a[4]={5,6,7,8}; int b[4]={3,2,1,0}; int i=0; return a[b[i]];}", 8)  # b[0]=3 -> a[3]=8

# 4. loops with running index
case("4a prefix sum total",
     "int main(){int a[4]={1,2,3,4}; int i=0; int s=0; while(i<4){s=s+a[i];i=i+1;} return s;}", 10)
case("4b reverse in place then read a[0]",
     "int main(){int a[4]={1,2,3,4}; int i=0; int j=3; while(i<j){int t=a[i]; a[i]=a[j]; a[j]=t; i=i+1; j=j-1;} return a[0]*10+a[3];}",
     4*10+1)
case("4c fill a[i]=i*i then sum",
     "int main(){int a[5]; int i=0; while(i<5){a[i]=i*i;i=i+1;} int s=0;i=0; while(i<5){s=s+a[i];i=i+1;} return s;}",
     0+1+4+9+16)

# 5. write then read same index via variable
case("5a a[i]=5; a[i]=a[i]+1",
     "int main(){int a[3]={0,0,0}; int i=1; a[i]=5; a[i]=a[i]+1; return a[i];}", 6)
case("5b compound += on element",
     "int main(){int a[3]={1,2,3}; int i=2; a[i]+=10; return a[i];}", 13)

# 6. out of bounds (report behavior, no crash expected)
case("6a oob read i=5", "int main(){int a[3]={1,2,3}; int i=5; return a[i];}", None)

# 7. arrays + functions
case("7a array local in called non-main fn",
     "int g(){int b[3]={7,8,9}; return b[1];} int main(){return g();}", 8)
case("7b main array + non-recursive helper",
     "int inc(int x){return x+1;} int main(){int a[3]={1,2,3}; int r=inc(a[2]); return a[0]+a[1]+a[2]+r;}",
     1+2+3+4)

# 8. multiple arrays distinct base pointers
case("8a a[1]+b[2]",
     "int main(){int a[3]={1,2,3}; int b[3]={4,5,6}; return a[1]+b[2];}", 8)
case("8b write a doesn't touch b",
     "int main(){int a[3]={1,2,3}; int b[3]={4,5,6}; int i=0; while(i<3){a[i]=0;i=i+1;} return b[0]+b[1]+b[2];}",
     15)

# 10. big array
case("10a int a[20] fill and sum",
     "int main(){int a[20]; int i=0; while(i<20){a[i]=1;i=i+1;} int s=0;i=0; while(i<20){s=s+a[i];i=i+1;} return s;}",
     20)


def main():
    fails = []
    for name, src, expected, optimize, check in CASES:
        try:
            acc, mem, syms, toys = run(src, optimize=optimize)
        except Exception as e:
            fails.append((name, f"EXCEPTION {e}", None))
            print(f"ERR  {name}: {e}")
            continue
        if expected is not None and acc != (expected & 0xFF):
            fails.append((name, expected & 0xFF, acc))
            print(f"FAIL {name}: expected {expected & 0xFF}, got {acc}")
        else:
            print(f"ok   {name}: acc={acc}" + ("" if expected is not None else " (behavior-only)"))

    # 9. -O consistency: run every case both ways, compare
    print("\n-- optimize on/off consistency --")
    for name, src, expected, _o, check in CASES:
        try:
            a0, *_ = run(src, optimize=False)
            a1, *_ = run(src, optimize=True)
        except Exception as e:
            print(f"ERR  {name} (-O compare): {e}")
            fails.append((name + " -O", "exc", str(e)))
            continue
        if a0 != a1:
            print(f"FAIL {name}: optimize=False -> {a0}, optimize=True -> {a1}")
            fails.append((name + " -O", a0, a1))
        else:
            print(f"ok   {name}: both -> {a0}")

    print(f"\n{len(CASES)} cases, {len(fails)} failures")
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
