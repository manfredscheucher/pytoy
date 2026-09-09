"""Ad-hoc probes constructed during a code review of the pointer feature.
Each PROBE compiles a small C program that SHOULD work per the spec, runs it
on the Toy CPU, and checks the result. Kept as a durable regression file.

Run:  python3 tests/probe_pointer_review.py
"""
import io, os, sys, contextlib

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, 'compiler'))
from toyasm import assemble
from toycpu import execute_one
from toycc import compile_source, CompileError


def run_c_read_mem(src):
    asm = compile_source(src, "probe.toyc")
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    if errors:
        raise AssertionError(f"assembler errors: {errors}\n{asm}")
    mem = list(mem)
    acc, pc, steps = 0, 0, 0
    while steps < 1_000_000:
        if mem[pc] == 0:
            break
        pc, acc, _arg, _stopped = execute_one(mem, pc, acc)
        steps += 1
    else:
        raise AssertionError("did not halt")
    return acc, mem, syms


PROBES = []
def probe(desc, src, expected, reader=None):
    PROBES.append((desc, src, expected, reader))


# 1. &a[i] with a VARIABLE index (tests only cover &a[1] constant)
probe("&a[i] variable index, read through *p",
      "int main(void){ int a[4]={10,20,30,40}; int i=2; int *p=&a[i]; return *p; }",
      30)

# 2. write through &a[i] variable index
probe("*p=... where p=&a[i], check memory",
      "int main(void){ int a[3]={0,0,0}; int i=1; int *p=&a[i]; *p=99; return a[1]; }",
      99)

# 3. pointer arithmetic p+1 then deref (spec says pointer is a scalar address;
#    a+i indexing decays; does *(p+1) work?)
probe("*(p+1) pointer arithmetic",
      "int main(void){ int a[3]={7,8,9}; int *p=&a[0]; return *(p+1); }",
      8)

# 4. nested indexing a[b[i]] sharing the index temp
probe("a[b[i]] nested index",
      "int main(void){ int a[4]={5,6,7,8}; int b[2]={3,1}; int i=0; return a[b[i]]; }",
      8)

# 5. &x passed to a function that mutates via pointer, x live-across another use
probe("inc(&x) then use x again (address-taken local not saved)",
      "int inc(int*p){*p=*p+1;return 0;} "
      "int main(void){int x=5; int y=10; inc(&x); return x+y; }",
      16)

# 6. pointer param + call that mutates, result read from caller array in memory
probe("fill via array param, read whole array",
      "int fill(int a[],int n){int i=0;while(i<n){a[i]=i*2;i=i+1;}return 0;} "
      "int main(void){int v[4]={0,0,0,0}; fill(v,4); return v[3]; }",
      6)

# 7. deref of an expression that itself contains a call
probe("*(getptr()) deref of a call result",
      "int g;int getp(void){return 0;} "  # placeholder, replaced below
      , None)
PROBES.pop()  # drop the malformed one above

# 7b. deref read where ptr is a function returning an address
probe("*p where p = f() returns &global-ish via array base",
      "int base(int a[]){return a;} "  # returns base address
      "int main(void){int v[3]={11,22,33}; int b=base(v); int*p=b; return *p; }",
      11)

# 8. &x where x is a function LOCAL (renamed slot), mutated, and the caller of
#    that function is itself recursive-ish? keep simple: two-level
probe("pointer to a param slot inside a called function",
      "int addvia(int*p,int q){*p=*p+q;return *p;} "
      "int main(void){int x=1; return addvia(&x,4)+x; }",
      10)  # *p becomes 5, returns 5, x is now 5 -> 5+5=10

# 9. array-decay param, then take &a[i] INSIDE the function (addr of element of
#    a pointer-based array)
probe("&a[i] inside a function on an array param",
      "int setone(int a[],int n){int*p=&a[n-1];*p=42;return 0;} "
      "int main(void){int v[3]={1,2,3}; setone(v,3); return v[2]; }",
      42)

# 10. compound assign through pointer to array element
probe("*p += x where p=&a[i]",
      "int main(void){int a[3]={1,2,3}; int*p=&a[2]; *p += 10; return a[2]; }",
      13)

# 11. Address-of a local inside a RECURSIVE function: &x is the address of x's
#     single global slot, which recursion can't follow (each activation's value
#     lives on the save/restore stack). This is REJECTED at compile time rather
#     than miscompiled. Documented as a "must raise CompileError" probe.
probe("&x in a recursive fn is rejected (not miscompiled)",
      "int nop(int*p){ return 0; }"
      " int f(int n){ int x; x=n; nop(&x); if(n==0) return x; return x + f(n-1); }"
      " int main(void){ return f(3); }",
      "COMPILE_ERROR")


def main():
    fails = []
    for desc, src, expected, reader in PROBES:
        # A probe can expect a clean compile-time rejection.
        if expected == "COMPILE_ERROR":
            try:
                run_c_read_mem(src)
                print(f"[FAIL] {desc}: compiled but a CompileError was expected")
                fails.append((desc, "compiled", expected, None))
            except CompileError:
                print(f"[OK ] {desc}: rejected with CompileError (as expected)")
            continue
        try:
            acc, mem, syms = run_c_read_mem(src)
            got = acc
            ok = (got == expected)
            print(f"[{'OK ' if ok else 'FAIL'}] {desc}: got {got}, want {expected}")
            if not ok:
                fails.append((desc, got, expected, None))
        except Exception as e:
            print(f"[ERR ] {desc}: {type(e).__name__}: {e}")
            fails.append((desc, None, expected, e))
    print(f"\n{len(PROBES)-len(fails)}/{len(PROBES)} probes passed")
    return fails


if __name__ == '__main__':
    main()
