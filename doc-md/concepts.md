# Concepts: how the Toy CPU works

If you have never written machine language before, this page is the
foundation. Everything else in these docs builds on it.

## What is a CPU?

A CPU (central processing unit) is a machine that does one thing over and
over, extremely fast: it reads a number from memory, treats that number as an
**instruction**, and does what the instruction says. Then it reads the next
number, and the next, forever — until an instruction tells it to stop.

That is the whole idea. There is no magic. A program is just a list of
numbers sitting in memory. The CPU walks through them one at a time.

The Toy CPU is a deliberately tiny version of this idea, small enough to hold
in your head all at once.

## The three things you need to know about

The Toy CPU has exactly three pieces of state. That's it.

### 1. Memory — 256 bytes

Memory is a row of **256 numbered boxes**, addressed `0` to `255`. Each box
("byte") holds one number from `0` to `255`.

```
address:   0    1    2    3    4    5   ...  255
value:   [ 20 ][ 7 ][ 22 ][ 8 ][ 0 ][ 5 ] ...  [ 0 ]
```

Crucially, **memory holds both your program and your data**. There is no
separate "code" and "data" — it's all just numbers in boxes. The box at
address 0 might be an instruction; the box at address 7 might be the number
you're adding. The CPU can't tell them apart on its own — *you* decide the
layout, and the CPU trusts you.

### 2. The accumulator (ACC)

The accumulator is a single box *inside* the CPU where arithmetic happens. It
also holds 8 bits (a value `0`–`255`).

Almost every operation flows through the accumulator:

- To add two numbers, you `load` one into the accumulator, then `add` the
  other. The result stays in the accumulator.
- To save a result, you `store` the accumulator back into a memory box.

Think of the accumulator as your hands: you can only hold one value at a
time, and you have to put it down (store it) before picking up another.

### 3. The program counter (PC)

The program counter is the CPU's "you are here" marker. It holds the address
of the **next** instruction to run. It starts at `0`, so every Toy CPU
program begins at memory address 0.

After the CPU runs an instruction, the PC automatically moves forward to the
next one. Some instructions (`goto`, `ifzero`) change the PC on purpose —
that's how loops and branches work.

## The cycle: fetch, decode, execute

Everything the CPU does is this loop, repeated:

1. **Fetch** — read the byte at the address in the PC.
2. **Decode** — figure out which instruction that byte means (its *opcode*).
3. **Execute** — do it. If the instruction needs an address (like `add`), the
   CPU also reads the *next* byte to know which memory box to use.
4. **Advance** — move the PC forward, and repeat.

This continues until the CPU fetches a `stop` instruction.

## One-byte and two-byte instructions

Some instructions are self-contained and take **one byte**:

- `stop`, `right`, `left`, `not`, `nop` — they act only on the accumulator (or
  halt), so they need no address.

Others need to know *which memory box* to work with, so they take **two
bytes**: the opcode, followed by the address.

```
load  a     ->  two bytes:  [ 20 ][ 7 ]     "load, from address 7"
right       ->  one byte:   [ 1 ]           "shift the accumulator right"
```

The CPU knows which is which from the opcode itself (a specific bit in the
byte marks two-byte instructions — see [instruction-set.md](instruction-set.md)).

## Why bits matter

Because everything is 8 bits, the Toy CPU is a great place to *see* binary.
The bitwise instructions (`and`, `or`, `xor`, `not`, `left`, `right`) let you
manipulate individual bits directly. In the GUI, memory and the accumulator
are shown in binary, so you literally watch the lights turn on and off — the
same "switches and lights" experience as the 1970s machines this is modeled
on (see [toycpu.md](toycpu.md)).

## What's missing (on purpose)

Compared to a real CPU, the Toy CPU leaves out almost everything: no
multiply/divide, no multiple registers, no stack, no interrupts, no
overflow flags. Values simply wrap around modulo 256. This is a feature —
with so few parts, you can understand *the entire machine*, and build up
multiplication, comparison, and loops yourself from the primitives.

## The ladder: from C down to the lights

On the original Toy CPU you enter a program the hard way: one byte at a time,
in binary, by flipping switches and reading LEDs. That *is* the lesson — with
no tools, **you are the assembler**, translating in your head. It teaches you
what the machine really does, but it is slow and error-prone for anything
longer than a few instructions.

toyasm adds layers on top that make programs easier to write, without ever
hiding what the machine executes:

```
  C source        (toycc)        int a = 7; return a * b;   most human
      |  compile
      v
  assembly        (.toys)        load a / add b / stop      readable, named
      |  assemble  (1:1)
      v
  machine code    (bytes)        [20][7][22][8][0]          what the CPU runs
      |  run
      v
  Toy CPU                        LEDs + switches            the bare machine
```

Two things make this honest rather than a black box:

- **Assembly maps 1:1 to machine code.** Each mnemonic is exactly one opcode
  byte; a label is just a name for an address. Assembling is a direct
  substitution, not a clever transformation — so when you step through a
  program you can see each source line become the very bytes in memory.
- **The C layer is optional.** `toycc` compiles a small subset of C down to
  assembly (for example, turning `a * b` into repeated addition, since the CPU
  has no multiply). It is a convenience on top of the machine, not part of it —
  you can understand the Toy CPU completely without ever writing a line of C.

So the ladder lets you work at whatever height you want and drop down a rung
whenever you want to see how it really works — all the way to the switches and
lights of the original.

Next: **[the instruction set](instruction-set.md)**.
