= The C #sym.arrow assembly #sym.arrow CPU pipeline

toyasm ships with *toycc*, a small compiler that turns a simplified subset of C
into Toy CPU assembly (`.toys`). Writing C is more pleasant than hand-writing
assembly, and it lets you see, stage by stage, how a high-level program becomes
raw machine bytes.

The compiler lives in `compiler/`; its README documents the exact supported C
subset.

== The stages

```
 program.toyc                              (simplified C source)
     |
     |  toycc  --  lex -> parse -> code generation
     v
 program.toys                              (Toy CPU assembly text)
     |
     |  toyasm assembler (two-pass)
     v
 256-byte memory image + symbol table      (opcodes & data bytes)
     |
     |  toyasm simulator (fetch -> decode -> execute)
     v
 final accumulator (ACC)                   (the program's result)
```

#table(
  columns: (auto, auto, 1fr, 1fr),
  stroke: 0.5pt + luma(200),
  table.header([*Stage*], [*Tool*], [*Input*], [*Output*]),
  [1. Compile],  [`toycc`],  [`.toyc` source text], [`.toys` assembly text],
  [2. Assemble], [toyasm],   [`.toys` text],        [memory image + symbols, or errors],
  [3. Simulate], [toyasm],   [memory image],        [final ACC value],
)

=== Stage 1 --- toycc (C #sym.arrow assembly)

toycc is a hand-written compiler (standard library only): a *lexer* splits the
source into tokens, a *recursive-descent parser* builds a syntax tree, and a
*code generator* walks that tree emitting Toy CPU instructions. Because the
machine is so small, code generation makes concrete choices you can inspect in
the output:

- Every C variable gets a fixed *data byte* in memory; temporaries get their own
  bytes too.
- `a * b` becomes a *repeated-addition loop* (there is no multiply opcode).
- Comparisons reduce to the one available conditional, `ifzero` --- e.g.
  `a == b` compiles to `a - b` followed by `ifzero`, and ordering uses the
  sign-bit-of-difference trick.
- `while` / `for` / `if` become `goto` and `ifzero` with generated labels.

=== Stage 2 --- the assembler (assembly #sym.arrow bytes)

toyasm's two-pass assembler resolves labels to addresses and emits the 256-byte
memory image. This is the same assembler used for hand-written `.toys` programs;
toycc's output is nothing special to it. Invalid input yields errors instead of
a memory image.

=== Stage 3 --- the simulator (bytes #sym.arrow result)

The simulator runs the fetch--decode--execute cycle until `stop`, leaving the
program's `return` value in the accumulator, printed as the final
`Result: ACC = …` line.

== Running the pipeline by hand

```bash
# Stage 1: compile C to assembly
python3 compiler/toycc.py compiler/examples/multiply.toyc

# Stages 2+3: assemble and simulate
python3 toyasm.py compiler/examples/multiply.toys --cli --run --quiet
#   -> Result: ACC = 42

# Or all three at once with toycc's --run flag:
python3 compiler/toycc.py compiler/examples/multiply.toyc --run
```

== How the pipeline is tested

The whole pipeline is exercised by automated tests in `tests/test_toycc.py`,
run with `pytest`. The tests are *data-driven*: every `compiler/examples/*.toyc`
file carries a machine-readable `// expect: N` annotation stating its correct
result. For each example the harness runs all three stages
(`compile_source #sym.arrow assemble #sym.arrow simulate`) and asserts the
accumulator equals `N`. Adding a new example automatically adds a test.

Focused unit tests cover individual compiler features (arithmetic, bitwise ops,
shifts, `if`/`else`, `while`, `for`, comparisons, wraparound) so a failure
points at the specific feature. A git pre-commit hook (installed via
`scripts/install-hooks.sh`) runs this suite before each commit.
