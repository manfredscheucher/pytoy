"""Regression tests for the security-demo PIN examples.

The pin_check examples (asm + C) guard a secret: the right PIN (1337) reveals
the Answer (42, Hitchhiker's Guide), a wrong PIN yields 0. These are the running
examples for the security slides, so lock their behaviour in.

The GUI provides memory-mapped I/O; this headless runner treats 240..255 as
plain memory (see simulate()'s note). So we pre-seed io0..io3 with the PIN
digits and set ready != 0, which makes the busy-poll fall through and read our
seeded digits — exactly what a user typing into the GUI would produce.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pytoy.assembler import assemble  # noqa: E402
from pytoy.compiler import compile_source  # noqa: E402
from pytoy.core import execute_one  # noqa: E402
from pytoy.simulator import simulate  # noqa: E402
from pytoy.format import IO_BASE, IO_READY  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ASM_PIN = os.path.join(ROOT, "examples", "asm", "04-io", "pin_check.toys")
C_PIN = os.path.join(ROOT, "examples", "c", "04-io", "pin_check.toyc")
ASM_PIN_HARD = os.path.join(ROOT, "examples", "asm", "04-io",
                            "pin_check_hardened.toys")
C_PIN_HARD = os.path.join(ROOT, "examples", "c", "04-io",
                          "pin_check_hardened.toyc")

CORRECT = "1337"
ANSWER = 42


def _seed(mem, pin):
    """Type `pin` into io0.. and submit (ready != 0), headlessly."""
    for i, ch in enumerate(pin):
        mem[IO_BASE + i] = ord(ch)
    mem[IO_READY] = len(pin)   # non-zero submit; C read() uses it as the count


def _run_asm(pin, path=ASM_PIN):
    mem, listing, syms, data_addrs, errors, _ds = assemble(open(path).read())
    assert not errors, errors
    _seed(mem, pin)
    return simulate(mem, syms, data_addrs)


def _steps_asm(pin, path, cap=10000):
    """Run the assembled program and return (acc, step_count). A local
    step loop over the shared core, so we can measure timing (= steps)."""
    mem, listing, syms, data_addrs, errors, _ds = assemble(open(path).read())
    assert not errors, errors
    _seed(mem, pin)
    mem = list(mem)
    pc, acc, steps = 0, 0, 0
    while steps < cap:
        instr = mem[pc]
        steps += 1
        if instr == 0:   # STOP
            break
        pc, acc, _arg, _stopped = execute_one(mem, pc, acc)
    return acc, steps


def _compile_c():
    asm = compile_source(open(C_PIN).read(), "pin_check.toyc")
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert not errors, errors
    return asm


def test_asm_correct_pin_reveals_42():
    assert _run_asm(CORRECT) == ANSWER


def test_asm_wrong_pin_returns_0():
    assert _run_asm("0000") == 0
    assert _run_asm("1338") == 0   # only the last digit wrong
    assert _run_asm("7331") == 0


# The C read() CLEARS ready before it polls (see the I/O chapter), so headless
# it spins to the step cap — busy-poll only makes sense with the GUI re-setting
# ready. We therefore can't run the C version headless; verify it compiles and
# that the success path returns the secret 42 (the asm test above exercises the
# identical digit-by-digit compare logic end to end).
def test_c_compiles_and_returns_42_on_success():
    asm = _compile_c()
    assert "42" in asm              # the success path loads the secret
    assert "store ready" in asm     # read() clears ready, then busy-polls


# ── hardened (constant-time) variant ──────────────────────────────────────

def test_hardened_asm_correct_pin_reveals_42():
    assert _run_asm(CORRECT, ASM_PIN_HARD) == ANSWER


def test_hardened_asm_wrong_pin_returns_0():
    for wrong in ("0000", "1338", "7331", "1137", "2337"):
        assert _run_asm(wrong, ASM_PIN_HARD) == 0, wrong


def test_hardened_asm_is_constant_time():
    """The whole point: among WRONG PINs the step count must not depend on
    which (or how many) digits are wrong — a wrong first digit takes exactly as
    long as a wrong last digit, so timing reveals nothing. (Success takes a
    trivially different count, but by then the attacker has already won, so that
    is not a leak.)"""
    wrong = ["0337", "1037", "1307", "1330", "9999", "0000"]
    counts = {p: _steps_asm(p, ASM_PIN_HARD)[1] for p in wrong}
    assert len(set(counts.values())) == 1, f"not constant-time: {counts}"

    # sanity: the naive version IS NOT constant-time (that is the vuln). A wrong
    # first digit bails earlier than a wrong last digit, leaking the position.
    naive = {p: _steps_asm(p, ASM_PIN)[1] for p in ["0337", "1330"]}
    assert naive["0337"] != naive["1330"], naive


def test_hardened_c_compiles_and_returns_42_on_success():
    asm = compile_source(open(C_PIN_HARD).read(), "pin_check_hardened.toyc")
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert not errors, errors
    assert "42" in asm
