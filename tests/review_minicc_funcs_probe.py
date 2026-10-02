"""Reviewer probe for the new minicc function support (marker-dispatch).

Exercises calls end-to-end: basic, multi-site, call-as-argument, and the
nested same-function case f(y, f(x)) that the arg-spill ordering claims to fix.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy.minicc import compile_source
from pytoy.assembler import assemble
from pytoy import core


def run(src, name="probe", limit=500000):
    asm = compile_source(src, name)
    mem, listing, syms, data_addrs, errors, _ = assemble(asm)
    assert not errors, (name, errors)
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, stopped = core.execute_one(mem, pc, acc)
        if stopped:
            return acc
    raise AssertionError(f"{name}: did not halt")


def test_basic_add():
    assert run("int add(int a,int b){return a+b;} int main(void){return add(3,4);}") == 7


def test_call_as_argument():
    src = ("int sub2(int a,int b){return a-b;}"
           "int inc(int x){return x+1;}"
           "int main(void){return sub2(10, inc(3));}")
    assert run(src) == 6  # 10 - 4


def test_multi_site_same_fn():
    src = ("int dbl(int x){return x+x;}"
           "int main(void){int a=dbl(5); int b=dbl(a); return b;}")
    assert run(src) == 20


def test_nested_same_fn_second_arg():
    # f(20, f(8,3)) = f(20, 5) = 15 ; checks arg-spill fixes clobbering
    src = ("int f(int a,int b){return a-b;}"
           "int main(void){return f(20, f(8,3));}")
    assert run(src) == 15


def test_nested_same_fn_first_arg():
    # f(f(8,3), 1) = f(5,1) = 4
    src = ("int f(int a,int b){return a-b;}"
           "int main(void){return f(f(8,3), 1);}")
    assert run(src) == 4


def test_call_in_condition():
    src = ("int pos(int x){return x;}"
           "int main(void){int r=0; if(pos(5)>pos(2)){r=9;} return r;}")
    assert run(src) == 9


def test_call_in_while():
    src = ("int dec(int x){return x-1;}"
           "int main(void){int i=3; int s=0; while(i>0){s=s+i; i=dec(i);} return s;}")
    assert run(src) == 6


def test_helper_calls_helper():
    src = ("int inc(int x){return x+1;}"
           "int twice(int x){return inc(inc(x));}"
           "int main(void){return twice(40);}")
    assert run(src) == 42


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
