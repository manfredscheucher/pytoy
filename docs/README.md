# pytoy documentation

These docs explain what pytoy is, the machine it simulates, and how to
program it — written for newcomers with no prior assembly experience.

Read them roughly in this order:

1. **[Concepts](concepts.md)** — What a CPU actually does, and how the Toy
   CPU works: memory, the accumulator, the program counter, and the
   fetch–decode–execute cycle. Start here if machine language is new to you.
2. **[Instruction set](instruction-set.md)** — Every opcode, what it does,
   and how instructions are encoded as bytes.
3. **[Assembly syntax](assembly.md)** — How to write `.toys` programs:
   labels, data, number formats, and how pytoy lays them out in memory.
4. **[Writing programs](writing-programs.md)** — Worked examples building up
   from a straight-line program to loops and conditionals.
5. **[Using pytoy](usage.md)** — Running programs in the GUI and the CLI.
6. **[The C → assembly pipeline](compiler-pipeline.md)** — How **toycc**
   compiles a subset of C down to Toy CPU assembly, and how that pipeline is
   tested.
7. **[About the Toy CPU](toycpu.md)** — Background: where this machine comes
   from and how pytoy relates to the original.

If you just want to run something, jump to **[Using pytoy](usage.md)**.

## Why the project is structured this way

- **`toyasm.py` bundles the assembler, the simulator, and the GUI together.**
  That is deliberate. The whole point of the Toy CPU is to *see* how a CPU
  executes assembly / bytecode — and assembly maps 1:1 to machine code, so
  human-readable and machine form are the same thing. The GUI visualization
  (watch the program counter move, the accumulator change, the bytes in
  memory) *is* the lesson. Keeping these in one file means the entire machine
  is readable in one place; splitting it into separate modules would serve
  code tidiness at the expense of that clarity.

- **`toycc` (the C compiler) lives in its own `compiler/` folder because it is
  optional pre-processing.** You can understand the Toy CPU completely without
  ever writing C — toycc is just a convenience layer that produces `.toys`
  assembly for you. It sits *in front of* the CPU, it is not part of it, and
  the separate folder signals exactly that.
