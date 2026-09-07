# The C → assembly → CPU pipeline

toyasm ships with **toycc**, a small compiler that turns a simplified subset of
C into Toy CPU assembly (`.toys`). Writing C is more pleasant than hand-writing
assembly, and it lets you see, stage by stage, how a high-level program becomes
raw machine bytes. This page describes that pipeline and how it is tested.

The compiler lives in [`compiler/`](../compiler/); see its
[README](../compiler/README.md) for the exact supported C subset.

## The stages

```
 program.toyc                                       (simplified C source)
     │
     │  toycc  —  lex → parse → code generation
     ▼
 program.toys                                       (Toy CPU assembly text)
     │
     │  toyasm assembler (two-pass)
     ▼
 256-byte memory image  +  symbol table             (opcodes & data bytes)
     │
     │  toyasm simulator (fetch → decode → execute)
     ▼
 final accumulator (ACC)                            (the program's result)
```

Each stage has one job and a well-defined output that the next stage consumes:

| Stage | Tool | Input | Output |
|-------|------|-------|--------|
| 1. Compile | `toycc` (`compile_source`) | `.toyc` source text | `.toys` assembly text |
| 2. Assemble | toyasm (`assemble`) | `.toys` text | memory image + symbols, or errors |
| 3. Simulate | toyasm (`simulate`) | memory image | final ACC value |

### Stage 1 — toycc (C → assembly)

toycc is a hand-written compiler (standard library only): a **lexer** splits the
source into tokens, a **recursive-descent parser** builds an abstract syntax
tree, and a **code generator** walks that tree emitting Toy CPU instructions.

Because the machine is so small, code generation makes concrete choices you can
inspect in the output:

- Every C variable gets a fixed **data byte** in memory; temporaries get their
  own bytes too.
- `a * b` becomes a **repeated-addition loop** (there is no multiply opcode).
- Comparisons are reduced to the one available conditional, `ifzero` — e.g.
  `a == b` compiles to `a - b` followed by `ifzero`, and ordering uses the
  sign-bit-of-difference trick from `max.toys`.
- `while` / `for` / `if` become `goto` and `ifzero` with generated labels.

The emitted `.toys` is ordinary assembly with comments — read it to see exactly
how your C was translated. (See [assembly.md](assembly.md) and
[instruction-set.md](instruction-set.md).)

### Stage 2 — the assembler (assembly → bytes)

toyasm's two-pass assembler resolves labels to addresses and emits the 256-byte
memory image. This is the same assembler used for hand-written `.toys` programs;
toycc's output is nothing special to it. If toycc ever emitted something
invalid, this stage reports errors instead of a memory image.

### Stage 3 — the simulator (bytes → result)

The simulator runs the fetch–decode–execute cycle until `stop`, leaving the
program's `return` value in the accumulator. toyasm prints it as the final
`Result: ACC = …` line.

## Running the pipeline by hand

```bash
# Stage 1: compile C to assembly
python3 compiler/toycc.py compiler/examples/multiply.toyc
#   -> writes compiler/examples/multiply.toys

# Stages 2+3: assemble and simulate
python3 toyasm.py compiler/examples/multiply.toys --cli --run --quiet
#   -> Result: ACC = 42

# Or do all three at once with toycc's --run flag:
python3 compiler/toycc.py compiler/examples/multiply.toyc --run
```

## How the pipeline is tested

The whole pipeline is exercised by automated tests in
[`tests/test_toycc.py`](../tests/test_toycc.py), run with `pytest`:

```bash
python3 -m pytest -q
```

The tests are **data-driven**: every `compiler/examples/*.toyc` file carries
a machine-readable `// expect: N` annotation stating its correct result. The
test harness, for each example, runs all three stages —
`compile_source → assemble → simulate` — and asserts that the accumulator
equals `N`. Adding a new example (with its `// expect:` line) automatically adds
a test; no test code changes are needed.

Alongside the end-to-end example tests, focused unit tests cover individual
compiler features (arithmetic, bitwise ops, shifts, `if`/`else`, `while`,
`for`, comparisons, wraparound) so that when something breaks, the failure
points at the specific feature rather than a whole program.

A git pre-commit hook (installed via
[`scripts/install-hooks.sh`](../scripts/install-hooks.sh)) runs this suite
before each commit, so the pipeline is verified continuously.
