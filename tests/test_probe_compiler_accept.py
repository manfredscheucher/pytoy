"""Locks in the compiler-acceptance properties the Part-3 switch tests rely on,
so a fixture choice can't silently rot (e.g. if an example or a compiler
changes). Mirrors scripts/probe/probe_compiler_accept.py, but as real assertions:

  - sum3.toyc          BOTH minicc and toycc accept + assemble (switch succeeds).
  - fibonacci_rec.toyc minicc rejects at compile (recursion -> MiniError).
  - bigint_add.toyc    minicc compiles but OVERFLOWS 240 bytes (assemble error).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pytoy.simulator import _compile_c
from pytoy.assembler import assemble
from pytoy.minicc import MiniError

_ROOT = os.path.join(os.path.dirname(__file__), "..")
SUM3 = os.path.join(_ROOT, "examples/c/03-programs/sum3.toyc")
FIB_REC = os.path.join(_ROOT, "examples/c/03-programs/fibonacci_rec.toyc")
BIGINT = os.path.join(_ROOT, "examples/c/03-programs/bigint_add.toyc")


def _compiles_and_assembles(src, compiler):
    asm = _compile_c(src, compiler, "p.toyc", annotate_c_lines=True)
    _, _, _, _, errors, _ = assemble(asm)
    return not errors


def test_sum3_both_compilers_succeed():
    src = open(SUM3).read()
    assert _compiles_and_assembles(src, "toycc")
    assert _compiles_and_assembles(src, "minicc")


def test_fibonacci_rec_minicc_rejects_at_compile():
    src = open(FIB_REC).read()
    assert _compiles_and_assembles(src, "toycc")
    try:
        _compile_c(src, "minicc", "p.toyc", annotate_c_lines=True)
        assert False, "minicc should reject recursion"
    except MiniError:
        pass


def test_bigint_add_minicc_overflows_at_assemble():
    src = open(BIGINT).read()
    assert _compiles_and_assembles(src, "toycc")
    # minicc compiles (no MiniError) but the inlined result won't assemble.
    asm = _compile_c(src, "minicc", "p.toyc", annotate_c_lines=True)
    _, _, _, _, errors, _ = assemble(asm)
    assert errors, "minicc bigint_add should overflow and fail to assemble"
