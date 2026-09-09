#!/usr/bin/env python3
"""Manual check of the new pointer support in toycc.

Compiles each snippet, assembles it, runs the real fetch/execute loop to STOP,
and prints the returned ACC plus (for the sort) the sorted array read from
memory, and the assembled byte size. Durable script (kept in scripts/).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pytoy.assembler import assemble
from pytoy.core import execute_one
from pytoy.compiler import compile_source


def run(src, name="chk"):
    asm = compile_source(src, name)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"assembler errors: {errors}\n{asm}"
    top = max((a for a, *_ in listing if a is not None), default=0)
    size = top + 1
    mem = list(mem)
    acc, pc, steps = 0, 0, 0
    while steps < 1_000_000:
        if mem[pc] == 0:
            break
        pc, acc, _arg, _stopped = execute_one(mem, pc, acc)
        steps += 1
    else:
        raise AssertionError("did not halt")
    return acc, mem, syms, size


CASES = [
    ("write through pointer",
     "int main(void){ int x=5; int *p; p=&x; *p=9; return x; }", 9),
    ("read through pointer",
     "int main(void){ int x=7; int *p=&x; return *p; }", 7),
    ("swap via pointers",
     "int main(void){ int a=3; int b=8; int *pa=&a; int *pb=&b;"
     " int t=*pa; *pa=*pb; *pb=t; return a; }", 8),
    ("array param sum",
     "int suma(int a[], int n){ int s=0; int i=0; while(i<n){ s=s+a[i]; i=i+1; }"
     " return s; } int main(void){ int v[3]={4,5,6}; return suma(v, 3); }", 15),
    ("pointer param mutates caller local",
     "int inc(int *p){ *p = *p + 1; return 0; }"
     " int main(void){ int x=5; inc(&x); inc(&x); return x; }", 7),
]

for label, src, expected in CASES:
    acc, mem, syms, size = run(src)
    ok = "OK" if acc == expected else "FAIL"
    print(f"[{ok}] {label}: got {acc}, expected {expected}  (size {size} bytes)")

BUBBLE = """
int bubblesort(int a[], int n){
  int i; int j; int t;
  i=0;
  while(i<n){ j=0; while(j<n-1-i){ if(a[j]>a[j+1]){ t=a[j]; a[j]=a[j+1]; a[j+1]=t; } j=j+1; } i=i+1; }
  return 0;
}
int main(void){ int a[10]={3,1,4,1,5,9,2,6,5,3}; bubblesort(a, 10); return a[0]; }
"""
acc, mem, syms, size = run(BUBBLE)
base = syms['arr_a']
arr = [mem[base + k] for k in range(10)]
exp = [1, 1, 2, 3, 3, 4, 5, 5, 6, 9]
ok = "OK" if (acc == 1 and arr == exp) else "FAIL"
print(f"[{ok}] bubblesort param: return {acc} (want 1), array {arr}")
print(f"       want                                {exp}")
print(f"       size {size} bytes (budget 256)")
