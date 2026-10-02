"""Full toycc: a non-recursive multi-function program must compile with the
sp byte dropped (no_stack) and still run correctly, confirming non-recursive
callers never emit push/pop that would reference an undefined sp."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import compiler
from pytoy.assembler import assemble
from pytoy import core


def run_cc(src, opts, limit=300000):
    asm = compiler.compile_source(src, "ns", opts=opts)
    assert "\nsp:" not in asm and not asm.startswith("sp:"), \
        "sp byte present though program is non-recursive"
    mem, l, s, d, errors, _ = assemble(asm)
    assert not errors, errors
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, st = core.execute_one(mem, pc, acc)
        if st:
            return acc
    raise AssertionError("no halt")


def test_nonrecursive_multifn_no_stack():
    src = ("int add(int a, int b) { return a + b; }\n"
           "int dbl(int x) { return add(x, x); }\n"
           "int main(void) { int r = dbl(add(3, 4)); return r; }\n")
    # add(3,4)=7 ; dbl(7)=14
    assert run_cc(src, compiler.Opts()) == 14
    assert run_cc(src, compiler.Opts.all_on()) == 14


def test_no_push_pop_emitted_nonrecursive():
    src = ("int add(int a, int b) { return a + b; }\n"
           "int main(void) { return add(1, 2); }\n")
    asm = compiler.compile_source(src, "ns", opts=compiler.Opts())
    assert "push" not in asm.lower()
    assert "<- mem[sp]" not in asm


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
