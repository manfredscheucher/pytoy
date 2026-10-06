= Concepts: how the Toy CPU works

If you have never written machine language before, this chapter is the
foundation. Everything else builds on it.

== What is a CPU?

A CPU (central processing unit) is a machine that does one thing over and over,
extremely fast: it reads a number from memory, treats that number as an
_instruction_, and does what the instruction says. Then it reads the next
number, and the next, forever --- until an instruction tells it to stop.

That is the whole idea. There is no magic. A program is just a list of numbers
sitting in memory. The CPU walks through them one at a time. The Toy CPU is a
deliberately tiny version of this idea, small enough to hold in your head all
at once.

== The three things you need to know about

The Toy CPU has exactly three pieces of state. That's it.

=== Memory --- 256 bytes

Memory is a row of *256 numbered boxes*, addressed `0` to `255`. Each box
("byte") holds one number from `0` to `255`.

```
address:   0    1    2    3    4    5   ...  255
value:   [ 20 ][ 7 ][ 22 ][ 8 ][ 0 ][ 5 ] ...  [ 0 ]
```

Crucially, *memory holds both your program and your data.* There is no separate
"code" and "data" --- it's all just numbers in boxes. The CPU can't tell them
apart on its own; _you_ decide the layout, and the CPU trusts you.

=== The accumulator (ACC)

The accumulator is a single box _inside_ the CPU where arithmetic happens. It
holds 8 bits (a value `0`--`255`). Almost every operation flows through it: to
add two numbers you `load` one into the accumulator, then `add` the other; to
save a result you `store` the accumulator back into a memory box. Think of the
accumulator as your hands --- you can only hold one value at a time, and you
have to put it down (store it) before picking up another.

=== The program counter (PC)

The program counter is the CPU's "you are here" marker. It holds the address of
the _next_ instruction to run. It starts at `0`, so every Toy CPU program
begins at memory address 0. After running an instruction the PC moves forward;
`goto` and `ifzero` change it on purpose --- that's how loops and branches work.

== The cycle: fetch, decode, execute

Everything the CPU does is this loop, repeated:

+ *Fetch* --- read the byte at the address in the PC.
+ *Decode* --- figure out which instruction that byte means (its _opcode_).
+ *Execute* --- do it. If the instruction needs an address (like `add`), the
  CPU also reads the _next_ byte to know which memory box to use.
+ *Advance* --- move the PC forward, and repeat.

This continues until the CPU fetches a `stop` instruction.

== One-byte and two-byte instructions

Some instructions are self-contained and take *one byte* (`stop`, `right`,
`left`, `not`, `nop`). Others need to know _which memory box_ to work with, so
they take *two bytes*: the opcode, followed by the address.

```
load  a     ->  two bytes:  [ 20 ][ 7 ]     "load, from address 7"
right       ->  one byte:   [ 1 ]           "shift the accumulator right"
```

The CPU knows which is which from the opcode itself (a specific bit marks
two-byte instructions --- see the instruction set chapter).

== What's missing (on purpose)

Compared to a real CPU, the Toy CPU leaves out almost everything: no
multiply/divide, no multiple registers, no stack, no interrupts, no overflow
flags. Values simply wrap around modulo 256. This is a feature --- with so few
parts you can understand _the entire machine_, and build up multiplication,
comparison, and loops yourself from the primitives.

Modern CPUs are built specifically around a stack plus a base/frame pointer. The
Toy CPU has none of that in hardware, but you can simulate one in software: the C
compiler builds a stack itself, which is what makes recursion work (see the
stack-and-recursion chapter).

== The ladder: from C down to the lights

On the original Toy CPU you enter a program the hard way: one byte at a time, in
binary, by flipping switches and reading LEDs. That _is_ the lesson --- with no
tools, *you are the assembler*, translating in your head. It teaches you what
the machine really does, but it is slow and error-prone for anything longer than
a few instructions.

pytoy adds layers on top that make programs easier to write, without ever
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

- *Assembly maps 1:1 to machine code.* Each mnemonic is exactly one opcode
  byte; a label is just a name for an address. Assembling is a direct
  substitution --- when you step through a program you can see each source line
  become the very bytes in memory.
- *The C layer is optional.* `toycc` compiles a small subset of C down to
  assembly (turning `a * b` into repeated addition, since the CPU has no
  multiply). It sits on top of the machine, not inside it --- you can understand
  the Toy CPU completely without ever writing a line of C.
