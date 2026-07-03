# pytoy documentation

These docs explain what pytoy is, the machine it simulates, and how to
program it — written for newcomers with no prior assembly experience.

Read them roughly in this order:

1. **[Concepts](concepts.md)** — What a CPU actually does, and how the Toy
   CPU works: memory, the accumulator, the program counter, and the
   fetch–decode–execute cycle. Start here if machine language is new to you.
2. **[Instruction set](instruction-set.md)** — Every opcode, what it does,
   and how instructions are encoded as bytes.
3. **[Assembly syntax](assembly.md)** — How to write `.toy` programs:
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
