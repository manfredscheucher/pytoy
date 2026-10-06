= About the Toy CPU

pytoy is a Python toolbox (assembler, simulator, and C compiler) for the *Toy
CPU*, a minimal educational processor created by Jim Hall for the FreeDOS
Project. This chapter records where the machine comes from and how pytoy relates
to it.

- Official page: #link("https://jimhall.itch.io/toy-cpu") (free, MIT-licensed)
- Source: #link("https://github.com/freedosproject/toycpu")
- Jim Hall's talk (VCF East, ~50 min):
  #link("https://www.youtube.com/watch?v=zhoL1ZSjGfM")

== The "switches and lights" heritage

Early microcomputers like the *Altair 8800* and *IMSAI 8080* (both 1975) had no
keyboard or screen. You entered programs by flipping a bank of *switches* to set
each binary instruction, and read results from a row of *LEDs* ("lights").
Programming meant knowing the raw opcodes by heart and toggling them in bit by
bit.

The Toy CPU faithfully recreates this: a counter, an instruction, and an
accumulator, each shown as 8 lights, with a tiny instruction set instead of the
real Altair opcodes.

#figure(
  image("../images/toycpu-screen.png", width: 90%),
  caption: [Jim Hall's original Toy CPU (v2, ncurses). The `count`, `instr`, and
    `accum` boxes are 8-bit LED patterns; the legend on the right lists every
    opcode. You program it by flipping bits: _left/right = prev/next, space =
    flip, enter = done_. pytoy exists to spare you exactly this bit-by-bit
    entry, without hiding what it produces.],
)

== Why pytoy exists

I started pytoy because I find the Toy CPU very elegant. It shows clearly how a
CPU works, with few enough parts that the whole machine fits in your head.
Working at the assembly level makes it far more accessible than entering bits by
hand, and the Toy CPU is really just bytecode, so the assembly maps straight onto
what the machine runs.

On top of that, pytoy adds a small C (minicc) and a fuller C with a real stack,
so you can follow the whole transition: what happens when you write C, how it is
translated down to bytecode, and how input/output works. (I/O for C is still
being added.) The 256-address limit stays real and instructive throughout:
programs have to stay small, and it is easy to run out of room (see the note on
memory limits below).

== The machine

- *256 bytes of memory*, holding both program and data.
- *One accumulator* for arithmetic.
- *A program counter* that starts at 0.
- *14 opcodes*: load/store, add/sub, the bitwise operations, shifts, an
  unconditional `goto`, a single conditional `ifzero`, `nop`, and `stop`.

The original went through three versions: an experimental FreeDOS prototype, a
Linux/ncurses prototype, and finally a FreeDOS graphics-mode program.

== Building the original (and why v2 on macOS)

The three versions build very differently, which matters if you want to run Jim
Hall's original alongside pytoy:

- *v3* (current `main`, the FreeDOS graphics-mode program) builds with a `.bat`
  script that calls *OpenWatcom C* (`wcl -q -2 -os toy.c …`). That toolchain
  targets DOS; it does not build on macOS out of the box.
- *v2* (the Linux/ncurses prototype) ships a plain *Makefile* using *gcc* and
  `-lncurses`. That is the version to check out on macOS --- it builds with
  make + gcc and a terminal ncurses UI, no OpenWatcom or DOS needed. The
  screenshot above is this v2 build.

So on macOS: check out v2 to actually build and run the original. v3 is
FreeDOS/OpenWatcom-only.

== What comes from toycpu, and what is original

*Taken from toycpu (the instruction set):*

- The opcode values are identical: `STOP=0, RIGHT=1, LEFT=2, NOT=15, AND=17,
  OR=18, XOR=19, LOAD=20, STORE=21, ADD=22, SUB=23, GOTO=24, IFZERO=25,
  NOP=128`.
- The FETCH bit (bit 4, `0x10`) marking instructions that carry an address byte.
- The execution semantics of each instruction, including the 8-bit wraparound on
  ADD/SUB (`>255 #sym.arrow #sym.minus 256`, `<0 #sym.arrow #sym.plus 256`).

This is unavoidable: matching the instruction set _means_ matching these numbers
and their behaviour.

*Written from scratch for pytoy (not present in toycpu):*

- The two-pass *assembler* --- labels, symbols, comments, data bytes. toycpu has
  no assembler; it reads pre-built binary via the switch-panel input shown
  above.
- The *Qt/PySide6 GUI debugger*. toycpu uses a DOS text-mode / ncurses display
  --- a different language and toolkit entirely.
- The *CLI* verbose/step mode, the `EXPLAIN` output, the listing/export, and the
  `.toys`/`.toyo` file formats.

pytoy's Python is deliberately *simple, standard-library + PySide6 code* ---
readability is a feature, since the point is to _see_ how the machine works.

== Credits and license

The Toy CPU instruction set and design are by Jim Hall (FreeDOS Project). pytoy's
own code (assembler, GUI, compiler) is independent.

Both projects are MIT-licensed: toycpu Copyright (c) 2022 Jim Hall (FreeDOS
Project), pytoy Copyright (c) 2026 Manfred Scheucher. Jim Hall's original notice
is reproduced in the repository's `NOTICE` file.
