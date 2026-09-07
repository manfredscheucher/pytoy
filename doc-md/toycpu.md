# About the Toy CPU

toyasm is a Python assembler and simulator for the **Toy CPU**, a minimal
educational processor created by Jim Hall for the FreeDOS Project. This page
summarizes where the machine comes from — helpful for understanding *why* it
looks the way it does.

Original project: <https://github.com/freedosproject/toycpu>

Jim Hall's own talk on the machine (VCF East, ~50 min):
<https://www.youtube.com/watch?v=zhoL1ZSjGfM>

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

## How toyasm relates

The original Toy CPU is a C program where you enter programs bit by bit with
the arrow keys and Space, mimicking the switch panel. **toyasm keeps the same
CPU** — identical memory model, accumulator, program counter, and opcodes —
but replaces the switch-flipping input with:

- **Readable assembly** in `.toys` files (labels, named data, comments) instead
  of hand-entered binary. See [assembly.md](assembly.md).
- **A modern GUI and a CLI** for running and stepping through programs. See
  [usage.md](usage.md).

So the concepts you learn here transfer directly to the original hardware-style
simulator — you're just spared the switch-flipping.

## What comes from toycpu, and what is original

To keep the provenance honest and precise:

**Taken from toycpu (the instruction set):**

- The opcode values are identical: `STOP=0, RIGHT=1, LEFT=2, NOT=15, AND=17,
  OR=18, XOR=19, LOAD=20, STORE=21, ADD=22, SUB=23, GOTO=24, IFZERO=25,
  NOP=128`.
- The FETCH bit (bit 4, `0x10`) marking instructions that carry a second
  address byte.
- The execution semantics of each instruction, including the 8-bit wraparound
  on ADD/SUB (`>255 → −256`, `<0 → +256`).

This is unavoidable: matching the instruction set *means* matching these
numbers and their behaviour. It is the specification, not copied code.

**Written from scratch for toyasm (not present in toycpu):**

- The two-pass **assembler** — labels, symbols, comments, data bytes. toycpu
  has no assembler; it reads pre-built binary via a switch-panel-style input.
- The **Qt/PySide6 GUI debugger** (source view, memory view, click
  navigation, Step/Run/Reset). toycpu uses a DOS text-mode display
  (`conio.h`, `kbhit`) — a different language and toolkit entirely.
- The **CLI** verbose/step mode, the `EXPLAIN` output, the listing/export, and
  the `.toys`/`.toyo` file formats.

## Licensing

Both projects are MIT-licensed, so the provenance is clean.

- toycpu is MIT, Copyright (c) 2022 Jim Hall (FreeDOS Project).
- toyasm is MIT, Copyright (c) 2026 Manfred Scheucher, for its own code
  (assembler, GUI, CLI).

Strictly, an instruction set on its own (a list of opcodes and what they do)
is likely not copyrightable — interfaces generally are not. So reusing only
the opcode numbers and semantics, with everything else rewritten, probably
carries no attribution obligation at all. But since toycpu is MIT anyway,
toyasm includes Jim Hall's original MIT notice in a `NOTICE` file, which makes
the question moot: MIT-on-MIT, both copyright holders credited side by side.
