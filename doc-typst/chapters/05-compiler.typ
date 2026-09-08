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

=== Functions

toycc supports multiple functions that call each other (see
`examples/functions.toyc`). The Toy CPU has no call/return instruction, no stack
pointer, and no indirect jump, so each function is compiled with *global slots +
marker dispatch*:

- each function `f` gets fixed data bytes --- one per parameter, a return-value
  slot, and a return-marker slot;
- its body is emitted once; `return e` stores `e` and jumps to `f`'s dispatch;
- a call writes the arguments into the parameter slots, sets the marker to a
  number identifying *this* call site, and jumps to the body;
- a compare-chain on the marker jumps back to the correct call site.

=== Recursion

Because a function has only one set of slots, a naive recursive call would
clobber its caller's values. So around *every* call, toycc saves the caller's
live values onto a real stack (one `sp` byte plus self-modifying indirect
push/pop, growing down from address 255) and restores them afterward --- giving
each activation its own copies. This makes recursion, including mutual
recursion, work automatically; `examples/fibonacci_rec.toyc` is a recursive
Fibonacci. It is the same _idea_ as the hand-written `fibonacci_rec.toys` (next
chapter) --- a self-modifying-code stack --- though the compiler's stack grows
*down* from 255 while the hand-written one grows up; the direction is a free
choice, the principle is identical.

The `-O` / `--optimize-save-restore` flag (default off) skips the save/restore
around calls whose caller is not recursive --- a pure size win with identical
results. The stack has no bounds check and shares the 256 bytes with code and
data, so deep recursion can overflow into data and corrupt it. toycc warns when
the *compiled program itself* leaves little room for the stack --- but note this
is a static size check, not a depth guard: a program that fits with plenty of
headroom can still overflow at run time if it recurses deep enough, silently.
Keep recursion shallow, or use `-O` and small inputs.

=== Arrays

Fixed-size local arrays (`int a[10] = {...};`, `a[i]` read/write with any index
expression) are supported. With no index register, `a[i]` compiles with
self-modifying code: compute `base + i`, patch it into a raw load/store's
address byte, and execute it --- the same trick the `sum.toys` and
`bubblesort.toys` assembly examples use. `array_sum.toyc`, `array_max.toyc` and `bubblesort.toyc`
operate on the ten digits of pi. (Arrays are not saved across recursive calls,
so a recursive function may not declare one --- the compiler rejects that.)

=== Pointers

An address on the Toy CPU is just a byte, so a pointer is an ordinary one-byte
variable holding an address. toycc supports `int *p`, address-of `&x` (and
`&a[i]`), and dereference `*p` as both an rvalue and an assignment target
(`*p = e`). `&x` compiles to a data byte initialised to `x`'s address; `*p`
read/write reuse the same self-modifying-code trick as array indexing (patch the
address from `p` into a raw load/store, then execute it).

Crucially, an array passed to a function *decays to a pointer*: `int f(int a[],
int n)` receives the array's address, and `a[i]` inside `f` means `*(a + i)`
through that address --- so a function can sort or fill the caller's array in
place. `bubblesort_fn.toyc` is the bubble sort written as such a function.
(Taking the address of a local inside a *recursive* function is rejected, since
`&x` names a single shared slot the recursion stack can't follow.)

Because the recursion stack, array indexing and pointer dereference all store
into patched instructions, toycc's output uses self-modifying code by design.
Don't run it with `--detect-code-overwrite` (previous chapters): that guard
flags any store below the data region as overwriting code, so it would
false-trip on this legitimate self-modification and halt the program.

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
