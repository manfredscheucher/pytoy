= About the Toy CPU

toyasm is a Python assembler and simulator for the *Toy CPU*, a minimal
educational processor created by Jim Hall for the FreeDOS Project. This chapter
records where the machine comes from and how toyasm relates to it.

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
    flip, enter = done_. toyasm exists to spare you exactly this bit-by-bit
    entry, without hiding what it produces.],
)

== Why toyasm exists

The Toy CPU itself is wonderful because it is _small_ --- the whole machine fits
in your head. But driving it through LEDs and switches gets tiring fast: entering
a program bit by bit is slow, you can't see much of what's going on, and you tend
to give up experimenting before you've really explored. That switch-and-light
workflow has its own charm --- it's honest about how bare a computer really is
--- but it's a narrow doorway.

The sharpest difference is what you can _see at once_. On the original front
panel you look at one value at a time --- one register, one address --- and step
or click through the rest; the machine only ever shows you a single 8-bit box.
toyasm shows everything simultaneously: the whole program, every byte of memory,
the accumulator, and the program counter, all on screen together, updating as you
step. Watching the PC move and the bytes change in one view is what makes a bug
obvious instead of invisible.

So toyasm keeps the tiny, comprehensible machine and widens the doorway. With a
graphical view of all of memory and the accumulator, an assembly layer, and a C
layer on top, you spot your mistakes almost immediately (instead of staring at
LEDs that tell you nothing) and you can keep experimenting far longer. The limits
are still real and instructive: 256 addresses means both the assembly and the C
you can write stay small, and it's easy to run out of room --- which is itself
part of the lesson (see the note on memory limits below).

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
Hall's original alongside toyasm:

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
and their behaviour. It is the specification, not copied code.

*Written from scratch for toyasm (not present in toycpu):*

- The two-pass *assembler* --- labels, symbols, comments, data bytes. toycpu has
  no assembler; it reads pre-built binary via the switch-panel input shown
  above.
- The *Qt/PySide6 GUI debugger*. toycpu uses a DOS text-mode / ncurses display
  --- a different language and toolkit entirely.
- The *CLI* verbose/step mode, the `EXPLAIN` output, the listing/export, and the
  `.toys`/`.toyo` file formats.

Both toyasm's Python is deliberately *simple, single-file, standard-library +
PySide6 code* --- readability is a feature, since the point is to _see_ how the
machine works.

== Licensing

Both projects are MIT-licensed, so the provenance is clean.

- toycpu is MIT, Copyright (c) 2022 Jim Hall (FreeDOS Project).
- toyasm is MIT, Copyright (c) 2026 Manfred Scheucher, for its own code
  (assembler, GUI, CLI).

Strictly, an instruction set on its own (a list of opcodes and what they do) is
likely not copyrightable --- interfaces generally are not. So reusing only the
opcode numbers and semantics, with everything else rewritten, probably carries
no attribution obligation at all. But since toycpu is MIT anyway, toyasm
reproduces Jim Hall's original MIT notice in the repository's `NOTICE` file,
which makes the question moot: MIT-on-MIT, both copyright holders credited side
by side.
