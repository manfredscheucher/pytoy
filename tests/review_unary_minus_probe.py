"""The refactored unary minus in toycc now routes through _gen_diff((num,0),x).
Check 0 - x mod 256 for a few values, compact and non-compact."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import compiler
from pytoy.assembler import assemble
from pytoy import core


def run_cc(src, opts, limit=200000):
    asm = compiler.compile_source(src, "u", opts=opts)
    mem, l, s, d, errors, _ = assemble(asm)
    assert not errors, errors
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, st = core.execute_one(mem, pc, acc)
        if st:
            return acc
    raise AssertionError("no halt")


def test_unary_minus_mod256():
    for v in (0, 1, 5, 127, 128, 200, 255):
        src = f"int main(void){{ int x = {v}; return -x; }}"
        want = (-v) & 0xFF
        for opts in (compiler.Opts(), compiler.Opts(compact=True)):
            got = run_cc(src, opts)
            assert got == want, f"-{v}: got {got} want {want} opts={opts.__dict__}"


def test_unary_minus_of_constant():
    for v in (0, 3, 128, 255):
        src = f"int main(void){{ return -{v}; }}"
        want = (-v) & 0xFF
        assert run_cc(src, compiler.Opts(compact=True)) == want


if __name__ == "__main__":
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
