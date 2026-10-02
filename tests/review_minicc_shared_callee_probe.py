"""Shared callee reached from two different callers (main and a helper): the
marker-dispatch must return each call to its own continuation across caller
boundaries."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import minicc
from pytoy.assembler import assemble
from pytoy import core


def run_mini(src, limit=500000):
    asm = minicc.compile_source(src, "m")
    mem, l, s, d, errors, _ = assemble(asm)
    assert not errors, errors
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, st = core.execute_one(mem, pc, acc)
        if st:
            return acc
    raise AssertionError("no halt")


def test_shared_callee_two_callers():
    # k called from main (site 0) and from g (site 1).
    # g(x) = k(x) + 100 ; main = k(5) + g(2)
    # k(5)=6 ; g(2)=k(2)+100=3+100=103 ; total 6+103 = 109
    src = ("int k(int x){return x+1;}"
           "int g(int x){return k(x)+100;}"
           "int main(void){return k(5)+g(2);}")
    assert run_mini(src) == 109


def test_callee_from_both_order_matters():
    # subtract to make site confusion visible
    # s(a,b)=a-b. g(x)=s(x,1). main=s(50, g(10))
    # g(10)=9 ; main=s(50,9)=41
    src = ("int s(int a,int b){return a-b;}"
           "int g(int x){return s(x,1);}"
           "int main(void){return s(50, g(10));}")
    assert run_mini(src) == 41


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
