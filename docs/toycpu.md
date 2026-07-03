# About the Toy CPU

pytoy is a Python assembler and simulator for the **Toy CPU**, a minimal
educational processor created by Jim Hall for the FreeDOS Project. This page
summarizes where the machine comes from — helpful for understanding *why* it
looks the way it does.

Original project: <https://github.com/freedosproject/toycpu>

## Why it exists

The Toy CPU was built to teach machine language to complete beginners in an
introductory, non-CS university course. The goal was to demystify computing by
having students program a real machine "the old-school way" — one instruction
at a time, in binary — but with a machine simple enough that anyone could
follow along.

## The "switches and lights" heritage

Early microcomputers like the **Altair 8800** and **IMSAI 8080** (both 1975)
had no keyboard or screen. You entered programs by flipping a bank of
**switches** to set each binary instruction, and read results from a row of
**LEDs** ("lights"). Programming meant knowing the raw opcodes by heart and
toggling them in bit by bit.

The Toy CPU faithfully recreates this experience — a counter, an instruction,
an accumulator, and status, all shown as 8 lights each — but with a tiny,
approachable instruction set instead of the real Altair opcodes. Off-the-shelf
Altair emulators reproduced the full 8080, which was far too much for a
first lesson; the Toy CPU strips it down to the essentials.

## The machine

- **256 bytes of memory**, holding both program and data.
- **One accumulator** for arithmetic.
- **A program counter** that starts at 0.
- **14 opcodes**: load/store, add/sub, the bitwise operations, shifts, an
  unconditional `goto`, a single conditional `ifzero`, `nop`, and `stop`.

The original went through three versions: an experimental FreeDOS prototype,
a Linux/ncurses prototype, and finally a FreeDOS graphics-mode program.

## How pytoy relates

The original Toy CPU is a C program where you enter programs bit by bit with
the arrow keys and Space, mimicking the switch panel. **pytoy keeps the same
CPU** — identical memory model, accumulator, program counter, and opcodes —
but replaces the switch-flipping input with:

- **Readable assembly** in `.toy` files (labels, named data, comments) instead
  of hand-entered binary. See [assembly.md](assembly.md).
- **A modern GUI and a CLI** for running and stepping through programs. See
  [usage.md](usage.md).

So the concepts you learn here transfer directly to the original hardware-style
simulator — you're just spared the switch-flipping.

## Credits

Toy CPU by Jim Hall (FreeDOS Project), MIT-licensed. pytoy is an independent
assembler/simulator for that same instruction set.
