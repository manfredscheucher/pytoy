#!/usr/bin/env python3
"""minisim: run a Toy CPU bytecode file (one integer per line, the rest is 0, # starts a comment)."""
import sys


def load(text):
    rows = [line.split("#")[0].strip() for line in text.splitlines()]
    mem = [int(r) for r in rows if r]
    if len(mem) > 256 or not all(0 <= x <= 255 for x in mem):
        raise ValueError("expected at most 256 integers 0..255")
    return mem + [0] * (256 - len(mem))


def run(mem, verbose=False):
    pc = acc = steps = 0
    while True:
        op, arg = mem[pc], mem[(pc + 1) % 256]
        steps += 1
        print(f"step={steps} acc={acc} pc={pc} op={op}")
        if verbose:
            for i in range(0, 256, 16):
                print(f"x_{i:03}...x_{i + 15:03}:" + "".join(f" {x:3}" for x in mem[i:i + 16]))
        if op == 0:
            print(f"stopped after {steps} step{'' if steps == 1 else 's'}, acc={acc}")
            return acc, steps
        pc = (pc + 1 + (op >> 4 & 1)) % 256   # bit 4: two-byte instruction
        if   op == 1:  acc >>= 1              # right
        elif op == 2:  acc <<= 1              # left
        elif op == 15: acc = ~acc             # not
        elif op == 17: acc &= mem[arg]        # and
        elif op == 18: acc |= mem[arg]        # or
        elif op == 19: acc ^= mem[arg]        # xor
        elif op == 20: acc = mem[arg]         # load
        elif op == 21: mem[arg] = acc         # store
        elif op == 22: acc += mem[arg]        # add
        elif op == 23: acc -= mem[arg]        # sub
        elif op == 24: pc = arg               # goto
        elif op == 25 and acc == 0: pc = arg  # ifzero
        acc &= 0xFF                           # any other opcode: nop


if __name__ == "__main__":
    files = [a for a in sys.argv[1:] if a != "-v"]
    if len(files) != 1:
        sys.exit("usage: minisim.py <program> [-v]")
    run(load(open(files[0]).read()), "-v" in sys.argv)
