"""Edge probes for minicc function support: arrays in helpers, same-named
arrays across functions, callstmt vs expression call, fall-through return,
and the safe_compare path in the full toycc (compiler.py)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import minicc
from pytoy import compiler
from pytoy.assembler import assemble
from pytoy import core


def run_mini(src, name="probe", limit=500000):
    asm = minicc.compile_source(src, name)
    mem, listing, syms, data_addrs, errors, _ = assemble(asm)
    assert not errors, (name, errors)
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, stopped = core.execute_one(mem, pc, acc)
        if stopped:
            return acc
    raise AssertionError(f"{name}: did not halt")


def run_cc(src, opts, name="probe", limit=500000):
    asm = compiler.compile_source(src, name, opts=opts)
    mem, listing, syms, data_addrs, errors, _ = assemble(asm)
    assert not errors, (name, errors)
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, stopped = core.execute_one(mem, pc, acc)
        if stopped:
            return acc
    raise AssertionError(f"{name}: did not halt")


def test_array_in_helper():
    src = ("int sumfirst(int n){int a[3]={10,20,30}; int s=0; int i=0;"
           " while(i<n){s=s+a[i]; i=i+1;} return s;}"
           "int main(void){return sumfirst(2);}")
    assert run_mini(src) == 30


def test_same_named_array_two_funcs():
    src = ("int g(void){int a[2]={1,2}; return a[1];}"
           "int h(void){int a[2]={5,6}; return a[0];}"
           "int main(void){return g()+h();}")
    assert run_mini(src) == 2 + 5


def test_callstmt_discards_value():
    # call as a statement; result discarded, then use a real return
    src = ("int noop(int x){return x;}"
           "int main(void){int y=3; noop(99); return y;}")
    assert run_mini(src) == 3


def test_fallthrough_no_return():
    # helper with no explicit return: f__ret keeps last value (0 default)
    src = ("int setz(int x){int z=x;}"   # no return
           "int main(void){int r=setz(5); return r+1;}")
    # f__ret was never written -> 0, so r+1 == 1
    assert run_mini(src) == 1


def test_safe_compare_far_apart():
    # 200 vs 10: differ by 190 (>128). Bit-7 trick is WRONG; safe_compare right.
    src = "int main(void){ if (200 < 10) { return 1; } return 0; }"
    safe = compiler.Opts(safe_compare=True)
    plain = compiler.Opts()
    assert run_cc(src, safe) == 0, "safe_compare: 200<10 must be false"
    # document the plain-trick behaviour (expected wrong) without asserting value
    got_plain = run_cc(src, plain)
    print("plain 200<10 ->", got_plain, "(bit-7 trick, may be wrong)")


def test_safe_compare_gt():
    src = "int main(void){ if (200 > 10) { return 1; } return 0; }"
    assert run_cc(src, compiler.Opts(safe_compare=True)) == 1


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
