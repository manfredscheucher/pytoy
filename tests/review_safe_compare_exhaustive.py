"""Exhaustive-ish check that --safe-compare gives correct unsigned results for
operand pairs that are >=128 apart (where the bit-7 trick is known wrong).
Compiles one program per op with constant operands and runs it."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import compiler
from pytoy.assembler import assemble
from pytoy import core


def run_cc(src, limit=200000):
    asm = compiler.compile_source(src, "sc", opts=compiler.Opts(safe_compare=True))
    mem, l, s, d, errors, _ = assemble(asm)
    assert not errors, errors
    pc, acc = 0, 0
    for _ in range(limit):
        pc, acc, aa, st = core.execute_one(mem, pc, acc)
        if st:
            return acc
    raise AssertionError("no halt")


def py(op, a, b):
    return {'<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b,
            '==': a == b, '!=': a != b}[op]


def test_safe_compare_far_pairs():
    # sample pairs spanning the >=128 danger zone
    pairs = [(0, 255), (255, 0), (200, 10), (10, 200), (128, 0), (0, 128),
             (127, 255), (255, 127), (100, 230), (230, 100), (1, 200), (200, 1)]
    for op in ('<', '>', '<=', '>='):
        for a, b in pairs:
            src = f"int main(void){{ if ({a} {op} {b}) {{ return 1; }} return 0; }}"
            got = run_cc(src)
            want = 1 if py(op, a, b) else 0
            assert got == want, f"{a}{op}{b}: got {got} want {want}"


if __name__ == "__main__":
    test_safe_compare_far_pairs()
    print("ok safe_compare far pairs")
