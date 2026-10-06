"""C-level memory-mapped I/O builtins: write(data, k) and read(data).

write(data, k) copies data[0..k-1] out to io0,io1,... (addresses 240..).
read(data) clears `ready`, busy-polls until it is non-zero, then copies that
many bytes from io0.. into data[0..] and returns the count.

write is deterministic headless, so we assemble + run and read the io cells back.
read busy-polls `ready`, which never changes in a plain headless loop, so these
tests drive the CPU step by step and inject input (set the io cells + ready) the
first time the program reads `ready` — exactly what the GUI does for the user.
"""

import io
import contextlib

from pytoy.assembler import assemble
from pytoy.compiler import compile_source, CompileError
from pytoy.core import decode, execute_one

import pytest

IO_BASE = 240
IO_READY = 255


def _assemble(src, name="test.toyc"):
    asm = compile_source(src, name)
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    assert errors == [], f"assembler errors: {errors}\n--- asm ---\n{asm}"
    return list(mem)


def _run(mem, on_ready=None, max_steps=200_000):
    """Run to STOP. If on_ready is given, it is called the first time the program
    LOADs `ready` (opcode 20 of address 255) and it is currently 0; it returns a
    dict of {addr: value} writes to inject (the simulated input), applied once."""
    acc, pc, steps = 0, 0, 0
    injected = False
    while steps < max_steps:
        instr, arg_addr, _ = decode(mem, pc)
        if instr == 0:  # STOP
            return acc, steps, mem
        if (on_ready and not injected and instr == 20 and arg_addr == IO_READY
                and mem[IO_READY] == 0):
            for a, v in on_ready().items():
                mem[a] = v & 0xFF
            injected = True
        pc, acc, arg_addr, _stopped = execute_one(mem, pc, acc)
        steps += 1
    raise AssertionError(f"did not halt within {max_steps} steps")


def _io(mem, n):
    return [mem[IO_BASE + i] & 0xFF for i in range(n)]


# ── write ───────────────────────────────────────────────────────────────────

def test_write_sends_bytes_to_io_cells():
    src = """
    int main(void) {
        int data[16];
        data[0] = 'H'; data[1] = 'i'; data[2] = '!';
        write(data, 3);
        return 0;
    }
    """
    mem = _assemble(src)
    _, _, mem = _run(mem)
    assert _io(mem, 4) == [ord('H'), ord('i'), ord('!'), 0]


def test_write_char_literals_hello_world():
    # 'H','e','l','l','o' spelled out, written to io0..io4.
    src = """
    int main(void) {
        int d[16];
        d[0]='H'; d[1]='e'; d[2]='l'; d[3]='l'; d[4]='o';
        write(d, 5);
        return 0;
    }
    """
    mem = _assemble(src)
    _, _, mem = _run(mem)
    assert "".join(chr(c) for c in _io(mem, 5)) == "Hello"


def test_write_count_from_variable():
    src = """
    int main(void) {
        int d[16];
        int k = 2;
        d[0] = 65; d[1] = 66; d[2] = 67;
        write(d, k);      // only the first k cells go out
        return 0;
    }
    """
    mem = _assemble(src)
    _, _, mem = _run(mem)
    assert _io(mem, 3) == [65, 66, 0]   # io2 untouched (still 0)


# ── read ──────────────────────────────────────────────────────────────────

def test_read_returns_count_and_fills_buffer():
    # read(data) returns ready's value AND copies that many io cells into data.
    # Prove the bytes really landed in the buffer: copy each one into a separate
    # result array by index, then write THAT out. If read hadn't filled data,
    # the result would be zeros, not "Max".
    src = """
    int main(void) {
        int data[16];
        int out[16];
        int k = read(data);
        out[0] = data[0];
        out[1] = data[1];
        out[2] = data[2];
        write(out, k);
        return k;
    }
    """
    mem = _assemble(src)
    acc, _, mem = _run(mem, on_ready=lambda: {
        IO_BASE + 0: ord('M'), IO_BASE + 1: ord('a'),
        IO_BASE + 2: ord('x'), IO_READY: 3})
    assert acc == 3
    assert "".join(chr(c) for c in _io(mem, 3)) == "Max"


def test_read_then_write_echo():
    src = """
    int main(void) {
        int data[16];
        int k = read(data);
        write(data, k);
        return 0;
    }
    """
    mem = _assemble(src)
    _, _, mem = _run(mem, on_ready=lambda: {
        IO_BASE + 0: ord('Y'), IO_BASE + 1: ord('o'),
        IO_BASE + 2: ord('!'), IO_READY: 3})
    # after echo, io0..io2 hold the same bytes that were read
    assert "".join(chr(c) for c in _io(mem, 3)) == "Yo!"


def test_read_clears_ready_so_poll_is_clean():
    # Even if ready is non-zero at start (stale), read clears it first and waits
    # for a fresh value, so the count reflects the injected input, not the stale.
    src = """
    int main(void) {
        int data[16];
        return read(data);
    }
    """
    mem = _assemble(src)
    mem[IO_READY] = 99          # stale value present before the program runs
    acc, _, mem = _run(mem, on_ready=lambda: {
        IO_BASE + 0: 7, IO_BASE + 1: 8, IO_READY: 2})
    assert acc == 2             # not 99


def test_read_with_pointer_offset_argument():
    # read(data + 3) must read into data starting at index 3 (pointer arithmetic
    # as the buffer argument). We prefill data[0..2], read 2 into data[3..4],
    # then write all 5 out and check.
    src = """
    int main(void) {
        int data[16];
        data[0]='a'; data[1]='b'; data[2]='c';
        int k = read(data + 3);
        write(data, k + 3);
        return 0;
    }
    """
    mem = _assemble(src)
    _, _, mem = _run(mem, on_ready=lambda: {
        IO_BASE + 0: ord('X'), IO_BASE + 1: ord('Y'), IO_READY: 2})
    assert "".join(chr(c) for c in _io(mem, 5)) == "abcXY"


# ── errors / arity ──────────────────────────────────────────────────────────

def test_write_wrong_arity_is_error():
    with pytest.raises(CompileError):
        compile_source("int main(void){ int d[4]; write(d); return 0; }", "t")


def test_read_wrong_arity_is_error():
    with pytest.raises(CompileError):
        compile_source("int main(void){ int d[4]; return read(d, 1); }", "t")
