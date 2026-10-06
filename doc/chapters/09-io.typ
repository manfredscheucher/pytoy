= Memory-mapped I/O

// NOTE: chapter cross-references here are by NAME, not number (headings are
// auto-numbered via `#set heading(numbering: ...)` in main.typ). If chapters are
// reordered, the numbers shift automatically but the NAMES must still match the
// chapters they point at ("Instruction set", "A stack, and recursion",
// "Using pytoy"). Keep these names in sync if a chapter is renamed or moved.

So far the Toy CPU has been a closed box: 256 bytes of memory, an accumulator, a
program counter, and nothing else. A program can compute, but it has no way to
reach anything _outside_ itself. This chapter adds the one mechanism that lets a
CPU talk to the outside world: *memory-mapped I/O*.

== The idea: some addresses are not really memory

The trick is almost embarrassingly simple. You pick a few memory addresses and
agree that they don't behave like ordinary RAM. Writing to one of those
addresses sends a byte _out_; reading from one brings a byte _in_. The CPU core
does not change at all. It still just loads and stores bytes. It is the world on
the other side of those addresses that does something special with them.

This is not a toy simplification. It is how real CPUs talk to real hardware. A
keyboard controller, a disk, a network card, a screen: each one is wired to a
range of addresses, and the CPU drives it by reading and writing those
addresses with the same `load`/`store` it uses for everything else. There is no
separate "I/O instruction set" on most machines. I/O _is_ memory access, aimed
at an address that happens to have a device behind it instead of a RAM chip.

It is worth saying plainly, because it is easy to assume otherwise: *I/O is not
only user input.* Typing characters at a keyboard is just one thing that can sit
behind an address. The same door opens onto a disk, a sensor, a second
processor, or a much larger memory than the CPU can address directly. The Toy
CPU can only name 256 bytes; think of those 256 bytes as a small window, almost
a cache, and memory-mapped I/O as the hatch through which a far bigger outside
world is passed in and out, a few bytes at a time. The human at the keyboard is
one peripheral among many.

== The map: `io0`..`io14` and `ready`

pytoy reserves the top of memory for I/O:

#table(
  columns: (auto, auto, 1fr),
  align: (left, left, left),
  stroke: 0.5pt + luma(200),
  table.header([*Address*], [*Label*], [*Role*]),
  [`240`--`254`], [`io0`--`io14`], [15 bidirectional I/O registers],
  [`255`],        [`ready`],       [a plain register the program polls],
)

The labels `io0` through `io14` and `ready` are *reserved names in the
assembler* — you write `store io0` or `load ready` and the assembler fills in
addresses 240 and 255 for you, the same way it resolves any label. They are not
special opcodes; `store io0` is an ordinary `store` (see the _Instruction set_
chapter) that happens to target address 240.

The 15 `io` cells are *bidirectional*: a program writes them to send a value
out, or reads them to take a value in. Which direction they mean is pure
convention between the program and whoever is on the other side.

`ready` (address 255) is just as ordinary. It is a single byte the program reads
to decide whether input has arrived. The convention is: `0` means _nothing yet_,
and a non-zero value means _input is available_ — often the non-zero value is
the _count_ of valid `io` cells. Nothing enforces this. `ready` is a normal byte
like any other; the meaning lives entirely in the program and the convention.

One housekeeping consequence: because 240--255 are reserved, the software
recursion stack (see _A stack, and recursion_) now starts at address 239 and
grows downward, keeping clear of the I/O region.

== Busy-poll: waiting without interrupts

The Toy CPU has no interrupts and no blocking "read a byte" instruction. Its
only conditional is `ifzero`. So how does a program wait for input to show up?
It _busy-polls_: it reads `ready` over and over in a tight loop, and only moves
on once `ready` is non-zero.

```
wait:   load  ready       # read the ready flag
        ifzero wait        # still 0? loop back and read again
        ...                # ready != 0 -> input is here, go use it
```

That two-line loop is the whole pattern. While `ready` is `0` the program spins,
doing nothing but checking again. The instant `ready` becomes non-zero the
`ifzero` falls through and the program reads the `io` cells.

Polling is a trade: it burns CPU cycles for the sake of being dead simple. A
real system would usually let the CPU sleep and wake it with an interrupt. But
the pattern also generalises nicely — a polling loop could do other work between
checks, or give up after a while (a timeout), or take a different branch if the
input never comes. The canonical loop above just waits forever.

== I/O is a GUI feature

In pytoy, I/O lives in the *GUI*. The simulator's I/O widget shows the 15 `io`
cells plus the `ready` register as a 16th cell, all in one row (two rows in
binary mode, where each value is eight characters wide). While the program is
polling — the current instruction is `load 255` — it highlights `ready` in red
so you can see the machine waiting on you. The running program is the device's
software; _you_ are the device. You click any cell to edit it — the exact same
dialog as editing memory in the CPU panel — and the program, spinning in its
poll loop, reacts. `ready` can also be set from the optional "set ready" input
row, which you enable from the _View_ menu.

The headless `--run` (see _Using pytoy_) has no outside world to talk to, so it
treats 240--255 as plain memory: writes land there and stay, reads return
whatever is there. A program that busy-polls `ready` under `--run` will spin
until it hits the step cap, because nothing ever sets `ready`. That is expected;
busy-polling only makes sense when something can change `ready` from outside,
which is what the GUI provides.

== Output: `hello_world`

The simplest direction is output: the program writes bytes to the `io` cells and
the widget displays them. `examples/asm/04-io/hello_world.toys` writes the ASCII
codes for "Hello world!" into `io0`..`io11`:

```
        load  H
        store io0
        load  e
        store io1
        ...
        stop
H:   72
e:  101
...
```

Each `io` cell holds one character code. Pick _ascii_ under _View → I/O format_
and the bytes read as letters; a non-printable code (a control code, or a high
byte) shows as a middle dot `·`, kept distinct from a real `.`. The same bytes
in _decimal_, _hex_, or _binary_ mode are just different views of the identical
memory — the program never changed, only the display did.

== Input: `greet_name`

Input combines the busy-poll with reading the `io` cells.
`examples/asm/04-io/greet_name.toys` reads a name and writes back a greeting.
In the GUI you type one ASCII character per cell (`io0`, `io1`, …), then set
`ready` to the _number_ of characters you typed. The program waits, then uses
that count as the length:

```
wait:   load  ready
        ifzero wait
        load  ready
        store n              # n = number of name characters
```

With `n` in hand it copies the name out of the `io` cells into a scratch area,
writes "hallo " into `io0`..`io5`, appends the name after it, and finishes with
a `!`. Type `Max` with `ready = 3` and `io0`..`io9` come back as `h a l l o _ M
a x !`.

Two details are worth noticing. First, the program must copy the name to scratch
_before_ writing "hallo ", because the greeting overwrites `io0`..`io5`, which
may still hold name characters. Second, it indexes the `io` cells by the runtime
count `n` using *self-modifying code* — patching the address byte of a
`load`/`store` on each pass — exactly the indirect-access technique from the _A
stack, and recursion_ chapter. The same machinery drives
`examples/asm/04-io/sort.toys`, which reads `N` values, bubble-sorts them, and
writes them back.

== The rest of the examples

`examples/asm/04-io/` collects the I/O programs:

#table(
  columns: (auto, 1fr),
  align: (left, left),
  stroke: 0.5pt + luma(200),
  table.header([*Program*], [*What it shows*]),
  [`numbers`],       [write `0`..`14` into `io0`..`io14` — the minimal output program (decimal view)],
  [`numbers_hex`],   [same bytes, opens in hex view (`0`..`9`, `a`..`e`)],
  [`numbers_ascii`], [same bytes, opens in ascii view],
  [`hello_world`],   [write the ASCII of "Hello world!" (output, ascii view)],
  [`fibonacci`],   [write the Fibonacci numbers `0`..`233` into the `io` cells],
  [`countdown`],   [count down from 10, writing each step to a cell],
  [`poll_demo`],   [the canonical busy-poll: wait on `ready`, echo `io0` to `io1`],
  [`greet_name`],  [read a name, write "hallo NAME!" (input + output)],
  [`sort`],        [read `N` values, sort ascending, write them back],
  [`pin_check`],   [read a 4-digit PIN (ascii), check it against 1337, write "succ"/"fail"],
)

Most have a `# pytoy: output=…` hint on the first line that sets the I/O
widget's default display format (overridable any time from _View → I/O format_).
Several have C counterparts under `examples/c/04-io/` (see the next section).

== I/O from C: `read` and `write`

The C compiler (toycc) exposes memory-mapped I/O through two built-in functions,
so a C program never has to touch the `io` cells by hand:

#table(
  columns: (auto, 1fr),
  align: (left, left),
  stroke: 0.5pt + luma(200),
  table.header([*Call*], [*What it does*]),
  [`write(data, k)`], [send `data[0]`..`data[k-1]` out to `io0`, `io1`, … (addresses 240, 241, …)],
  [`read(data)`],     [clear `ready`, busy-poll until it is non-zero, then copy that many values from `io0`.. into `data[0]`.., and return the count],
)

`read` returns the number of values it read (the `ready` value), so the usual
shape is `int k = read(buf);` followed by a loop up to `k`. Both take a buffer
that is any address expression — an array name, or pointer arithmetic such as
`read(data + 6)` to read into the middle of a buffer.

Character literals make ascii programs readable: `data[0] = 'H';` compiles to the
byte 72, so `hello_world.toyc` spells out the greeting instead of writing raw
codes. By default a compiled I/O program opens the widget in ascii view; add a
`// pytoy: output=decimal` line to override it.

*Limits are part of the lesson.* pytoy is a tool for learning and visualising how
a CPU works, not an applied compiler. The whole program — code and data — must
fit in 256 bytes (and below address 240, since 240..255 are the I/O region), so
anything real runs out of space fast. On top of that every value is an 8-bit int
that wraps at 256, the recursion stack is tiny, and there is no overflow or
bounds checking anywhere. These are not bugs to fix; they are the machine. The
point is to see the moving parts clearly, then reach for a real toolchain when you
want to _apply_ it.

The I/O built-ins follow the same spirit. `read` and `write` only move the 15
`io` cells, so a count is always 0..15 in practice. The copy loop tests
`i < count` with the machine's sign bit, which is exact up to 128 — far more than
15. A larger count is only reachable if the outside world writes a bogus `ready`
value, and the loop then copies nothing. That is left unguarded on purpose: a
full unsigned compare would cost code for a case a well-behaved device never
produces.

The C I/O examples under `examples/c/04-io/`:

#table(
  columns: (auto, 1fr),
  align: (left, left),
  stroke: 0.5pt + luma(200),
  table.header([*Program*], [*What it shows*]),
  [`hello_world`], [write "Hello world!" from a constant array (output, ascii)],
  [`greet_name`],  [put "Hallo " in a buffer, `read(data + 6)` the name, `write(data, k + 6)` the greeting],
  [`pin_check`],   [`read` a 4-digit PIN, compare to 1337 digit by digit, `write` "succ" or "fail"],
)
