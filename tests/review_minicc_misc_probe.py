"""More minicc probes: bare call as if-condition, call result as array index,
callstmt as last statement of main, helper whose only path is a loop-return."""
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


def test_call_as_bare_condition():
    src = ("int nz(int x){return x;}"
           "int main(void){int r=0; if(nz(0)){r=1;} else {r=2;} return r;}")
    assert run_mini(src) == 2


def test_call_result_as_array_index():
    src = ("int which(void){return 2;}"
           "int main(void){int a[3]={7,8,9}; return a[which()];}")
    assert run_mini(src) == 9


def test_callstmt_last_in_main_then_implicit():
    # main ends with a callstmt; the appended stop must halt cleanly
    src = ("int noop(int x){return x;}"
           "int main(void){int y=5; noop(y);}")
    # main falls through to the appended stop; acc is whatever last ran
    run_mini(src)  # just must halt without error


def test_helper_loop_return():
    src = ("int f(int n){int i=0; while(i<n){i=i+1;} return i;}"
           "int main(void){return f(4);}")
    assert run_mini(src) == 4


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
