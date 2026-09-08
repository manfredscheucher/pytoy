"""Skeptical fresh-eyes attack probes for the pointer feature in toycc.

Uses the `stopped` flag from execute_one (robust) rather than mem[pc]==0.
Run:  python3 tests/review_ptr_attack.py
"""
import os, sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, 'compiler'))
from toyasm import assemble, execute_one
from toycc import compile_source, CompileError


def run_c(src, optimize=False, max_steps=2_000_000):
    asm = compile_source(src, "attack.toyc", optimize=optimize)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    if errors:
        raise AssertionError(f"assembler errors: {errors}\n{asm}")
    mem = list(mem)
    acc = pc = steps = 0
    while steps < max_steps:
        next_pc, acc, _arg, stopped = execute_one(mem, pc, acc)
        if stopped:
            break
        pc = next_pc
        steps += 1
    else:
        raise AssertionError("did not halt")
    return acc, mem, syms, asm


def val(mem, syms, name):
    return mem[syms[name]]


CASES = []
def case(desc, src, expected, reader=None):
    CASES.append((desc, src, expected, reader))


# ---- angle 1: SMC reentrancy: multiple derefs / index in one expr/stmt ----
case("*p + *q  (two deref reads in one expr)",
     "int main(void){int a=7;int b=9;int*p=&a;int*q=&b;return *p + *q;}", 16)

case("*p = *q  (deref read feeds deref write)",
     "int main(void){int a=0;int b=42;int*p=&a;int*q=&b;*p=*q;return a;}", 42)

case("*p = *p + 1  (read+write same pointer)",
     "int main(void){int a=5;int*p=&a;*p=*p+1;return a;}", 6)

case("a[i]=a[j] pointer param, same-style patch",
     "int f(int a[]){a[0]=a[2];return 0;}"
     "int main(void){int v[3]={1,2,3};f(v);return v[0];}", 3)

case("*p = *q + *r (three derefs)",
     "int main(void){int a=0;int b=3;int c=4;int*p=&a;int*q=&b;int*r=&c;"
     "*p=*q+*r;return a;}", 7)

# ---- angle 2: pointer/array param aliasing ----
case("f(a,a) same array as two params, a[i]=b[j]",
     "int f(int a[],int b[]){a[0]=b[2];return 0;}"
     "int main(void){int v[3]={5,6,7};f(v,v);return v[0];}", 7)

# ---- angle 3: &local across a call, write must persist ----
case("inc(&x) twice -> 7",
     "int inc(int*p){*p=*p+1;return 0;}"
     "int main(void){int x=5;inc(&x);inc(&x);return x;}", 7)

case("inc(&x); x live-across with y",
     "int inc(int*p){*p=*p+1;return 0;}"
     "int main(void){int x=5;int y=10;inc(&x);return x+y;}", 16)

# ---- angle 4: pointer param + recursion (pointee is a caller local) ----
# Smaller variant that FITS: recursion increments *acc directly. The pointee
# (main's s) is a NON-recursive local; the recursive fn only carries the
# address as a value param. Address must survive the save/restore stack.
case("ptr param carried through recursion, deref-increment *acc",
     "int rec(int n,int*acc){if(n==0)return 0;*acc=*acc+1;return rec(n-1,acc);}"
     "int main(void){int s=0;rec(4,&s);return s;}",
     4, lambda mem, syms: mem[syms['v_s']])

# The pointer param itself must be saved/restored across the recursive call
# (it is a caller-owned slot live across the call). Check it still points at s
# after the deep recursion returns.
case("ptr param live across recursion, write after return",
     "int rec(int n,int*acc){if(n==0){*acc=99;return 0;}return rec(n-1,acc);}"
     "int main(void){int s=0;rec(3,&s);return s;}",
     99, lambda mem, syms: mem[syms['v_s']])

# original larger variant kept as a size-limit note (helper fn pushes it over)
case("[size-overflow] ptr param + helper fn in recursion",
     "int add1(int*p){*p=*p+1;return 0;}"
     "int rec(int n,int*acc){if(n==0)return 0;add1(acc);return rec(n-1,acc);}"
     "int main(void){int s=0;rec(5,&s);return s;}", 5)

# ---- angle 5: array param writes in a loop: reverse in place ----
case("reverse array in place via pointer param (read a[0])",
     "int rev(int a[],int n){int i=0;int j=n-1;while(i<j){int t=a[i];a[i]=a[j];a[j]=t;i=i+1;j=j-1;}return 0;}"
     "int main(void){int v[5]={1,2,3,4,5};rev(v,5);return v[0];}", 5,
     reader=lambda mem, syms: [mem[syms['arr_v'] + k] for k in range(5)],
     )
# override: expect the full reversed array in memory
CASES[-1] = ("reverse array in place via pointer param (whole array)",
     "int rev(int a[],int n){int i=0;int j=n-1;while(i<j){int t=a[i];a[i]=a[j];a[j]=t;i=i+1;j=j-1;}return 0;}"
     "int main(void){int v[5]={1,2,3,4,5};rev(v,5);return v[0];}",
     [5, 4, 3, 2, 1],
     lambda mem, syms: [mem[syms['arr_v'] + k] for k in range(5)])

case("fill via pointer walk (whole array in memory)",
     "int fill(int a[],int n){int i=0;while(i<n){a[i]=i+1;i=i+1;}return 0;}"
     "int main(void){int v[4]={0,0,0,0};fill(v,4);return v[0];}",
     [1, 2, 3, 4],
     lambda mem, syms: [mem[syms['arr_v'] + k] for k in range(4)])

# ---- angle 6: &a[i] with variable i then deref ----
case("int*p=&a[2]; return *p",
     "int main(void){int a[4]={1,2,3,4};int*p=&a[2];return *p;}", 3)

case("*(&a[i]) round trip, variable i",
     "int main(void){int a[4]={1,2,3,4};int i=3;return *(&a[i]);}", 4)

# ---- angle 7: pointer arithmetic ----
case("*(p+1)",
     "int main(void){int a[3]={7,8,9};int*p=&a[0];return *(p+1);}", 8)

case("p = p + 1; *p",
     "int main(void){int a[3]={7,8,9};int*p=&a[0];p=p+1;return *p;}", 8)

case("walk pointer with p=p+1 in loop, sum",
     "int main(void){int a[4]={1,2,3,4};int*p=&a[0];int s=0;int i=0;"
     "while(i<4){s=s+*p;p=p+1;i=i+1;}return s;}", 10)

# ---- angle 8: deref of a call result ----
case("*base(v) where base returns array address",
     "int base(int a[]){return a;}"
     "int main(void){int v[3]={11,22,33};int b=base(v);int*p=b;return *p;}", 11)

# ---- angle 10: liveness: pointer value live across a call ----
case("pointer value live across an unrelated call",
     "int side(int x){return x+1;}"
     "int main(void){int a=5;int*p=&a;int z=side(3);*p=z;return a;}", 4)

case("addvia(&x,4)+x",
     "int addvia(int*p,int q){*p=*p+q;return *p;}"
     "int main(void){int x=1;return addvia(&x,4)+x;}", 10)


# ---- extra angle-1: variable-index a[i]=a[j] on pointer param (shared index
#      temp reused for two separate element-address computations) ----
case("a[i]=a[j] variable indices, pointer param",
     "int f(int a[],int i,int j){a[i]=a[j];return 0;}"
     "int main(void){int v[4]={10,20,30,40};f(v,0,3);return v[0];}", 40)

case("swap via variable indices on pointer param, whole array",
     "int sw(int a[],int i,int j){int t=a[i];a[i]=a[j];a[j]=t;return 0;}"
     "int main(void){int v[3]={1,2,3};sw(v,0,2);return v[0];}",
     [3, 2, 1], lambda mem, syms: [mem[syms['arr_v'] + k] for k in range(3)])

# ---- reject cases: &local inside a recursive fn must be rejected ----
REJECTS = [
    ("&x inside recursive fn",
     "int f(int n){int x;x=n;int*p=&x;if(n==0)return *p;return *p+f(n-1);}"
     "int main(void){return f(2);}"),
    ("&a[i] inside recursive fn",
     "int f(int n){int a[2]={0,0};int*p=&a[0];if(n==0)return 0;return f(n-1);}"
     "int main(void){return f(1);}"),
    ("&param inside recursive fn",
     "int f(int n){int*p=&n;if(n==0)return *p;return *p+f(n-1);}"
     "int main(void){return f(2);}"),
]


def run_rejects():
    print("\n=== rejection checks (recursive &local) ===")
    fails = []
    for desc, src in REJECTS:
        try:
            run_c(src)
            print(f"[FAIL] {desc}: compiled (expected CompileError)")
            fails.append(desc)
        except CompileError as e:
            print(f"[OK ] {desc}: rejected: {e}")
        except Exception as e:
            print(f"[?? ] {desc}: {type(e).__name__}: {e}")
    return fails


# ---- angle 10 deeper: address-taken local in a NON-main, non-recursive caller,
#      live across a call. The caller IS itself save/restored when its own caller
#      (main) is non-recursive? main never re-enters, so no push. But the callee
#      writes through the pointer; the address-taken local must NOT be
#      save/restored by mid(), else the write is lost. mid() is non-recursive so
#      -O skips anyway; without -O, x is excluded from mid's slots. ----
case("addr-taken local in intermediate non-recursive caller, write persists",
     "int inc(int*p){*p=*p+1;return 0;}"
     "int mid(int seed){int x;x=seed;inc(&x);inc(&x);return x;}"
     "int main(void){return mid(10);}", 12)

# two calls with the address-taken local live between them (its value read after)
case("addr-taken local live across TWO calls, read between",
     "int inc(int*p){*p=*p+1;return 0;}"
     "int add(int a,int b){return a+b;}"
     "int mid(int s){int x;x=s;inc(&x);int y=add(x,100);inc(&x);return x+y;}"
     "int main(void){return mid(1);}", 105)
# hand: x=1; inc->2; y=add(2,100)=102; inc->3; return 3+102=105


# ---- angle 1 deeper: shared index temp / patch reentrancy stress ----
case("a[a[0]] = a[a[1]] nested index on both sides, pointer param",
     "int f(int a[]){a[a[0]]=a[a[1]];return 0;}"
     # a={2,3,7,9}; a[1]=3 -> a[3]=9; a[0]=2 -> a[2]=a[3]=9
     "int main(void){int v[4]={2,3,7,9};f(v);return v[2];}", 9)

case("*p = *p + *p (three uses of same deref)",
     "int main(void){int a=5;int*p=&a;*p=*p+*p;return a;}", 10)

case("a[i]=a[i]+a[i] pointer param, variable index",
     "int f(int a[],int i){a[i]=a[i]+a[i];return 0;}"
     "int main(void){int v[3]={1,7,3};f(v,1);return v[1];}", 14)

case("deref index chain: a[b[i]] with pointer params",
     "int f(int a[],int b[]){int i=0;return a[b[i]];}"
     "int main(void){int a[4]={5,6,7,8};int b[2]={3,1};return f(a,b);}", 8)


def run_all(optimize):
    fails = []
    for desc, src, expected, reader in CASES:
        tag = f"[-O]" if optimize else "[  ]"
        try:
            acc, mem, syms, asm = run_c(src, optimize=optimize)
            got = reader(mem, syms) if reader else acc
            ok = (got == expected)
            print(f"{tag}[{'OK ' if ok else 'FAIL'}] {desc}: got {got}, want {expected}")
            if not ok:
                fails.append((optimize, desc, got, expected, None))
        except Exception as e:
            print(f"{tag}[ERR ] {desc}: {type(e).__name__}: {e}")
            fails.append((optimize, desc, None, expected, e))
    return fails


def main():
    fails = []
    for opt in (False, True):
        print(f"\n=== optimize={opt} ===")
        fails += run_all(opt)
    run_rejects()
    print(f"\n{2*len(CASES)-len(fails)}/{2*len(CASES)} runs passed")
    if fails:
        print("\nFAILURES:")
        for opt, desc, got, exp, err in fails:
            print(f"  opt={opt} {desc}: got={got} want={exp} err={err}")
    return fails


if __name__ == '__main__':
    main()
