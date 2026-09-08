# toycc — a tiny C-to-assembly compiler for the Toy CPU

`toycc` compiles a small, standard-looking subset of C into `.toys` assembly
that the [toyasm](../toyasm.py) assembler/simulator can run.

It is a single self-contained Python program (`toycc.py`): a hand-written
lexer, a recursive-descent parser, and a straightforward code generator that
emits readable Toy assembly. No external libraries — Python standard library
only.

## The target machine (and why C is so restricted here)

The Toy CPU (see the [manual](../doc-typst/)) is deliberately minimal:

- **256 bytes of memory total.** Code and data share this one address space
  (addresses 0–255). A whole program — instructions *and* variables — must fit
  in 256 bytes.
- **One 8-bit accumulator (ACC).** All values are 0–255 and **all arithmetic
  wraps modulo 256** (`255 + 1 == 0`, `0 - 1 == 255`). There is no overflow
  flag.
- **The only conditional is `ifzero`** (branch when ACC == 0); the only jump is
  `goto`. Every `if`/`while`/comparison is built from these.
- **No multiply, divide, compare, or index register** in hardware.

Consequences for the C you can write:

- Every `int` is an **unsigned 8-bit** value (0–255) that wraps mod 256. A
  `char` and an `int` would be the same thing here. Keep results small.
- `*` is real multiplication, but it is compiled to a **runtime
  repeated-addition loop** (there is no multiply opcode). The product is taken
  mod 256.
- **Pointers and I/O are not supported.** Fixed-size local arrays ARE supported
  (see "Arrays" below), and so are functions — including recursive and mutually
  recursive ones (see below).

## Supported C subset

**Program shape**

```
int main(void) { ... }      // the entry point (no parameters)
int helper(int a, int b) { ... }   // optional extra functions (see below)
```

One `main` is the entry point; you may define additional functions and call
them (non-recursively — see "Functions" below). The execution result is
whatever value `return expr;` leaves in the accumulator when `main` stops.

**Statements**

- Local declarations: `int x;` and `int x = expr;`
- Array declarations: `int a[N];` and `int a[N] = {e0, e1, ...};` (N and the
  initializers must be constants; missing initializers default to 0)
- Assignment: `x = expr;`
- Indexed access: `a[i]` as an rvalue and `a[i] = expr;` (i is any expression);
  `a[i] += expr;` and the other compound forms work too
- Compound assignment: `+=  -=  *=  &=  |=  ^=  <<=  >>=`
- `if (cond) { ... }` and `if (cond) { ... } else { ... }`
- `while (cond) { ... }`
- `for (init; cond; post) { ... }` (desugars to `while`; `init` may declare a
  variable, e.g. `for (int i = 0; i < n; i += 1)`)
- Nested blocks `{ ... }`
- `return expr;`
- `//` and `/* ... */` comments

**Expressions / operators** (standard C precedence)

| Category      | Operators                        | Notes |
|---------------|----------------------------------|-------|
| Arithmetic    | `+`  `-`  `*`                    | `*` is a repeated-addition loop; all wrap mod 256 |
| Unary         | `-x`  `~x`  `!x`                 | `-x` is `0 - x` mod 256; `!x` yields 0/1 |
| Bitwise       | `&`  `\|`  `^`  `~`              | direct opcodes (`and`/`or`/`xor`/`not`) |
| Shifts        | `<<`  `>>`                       | constant amount → unrolled; variable amount → loop |
| Comparisons   | `==`  `!=`  `<`  `>`  `<=`  `>=` | yield 0/1; see note below |
| Grouping      | `( ... )`                        | |

Constants may be decimal (`42`) or hexadecimal (`0xF0`).

**Comparisons — what actually works.** `==` and `!=` are exact (via
subtraction + `ifzero`). The ordering comparisons `<`, `>`, `<=`, `>=` use the
sign-bit trick from `max.toys`: bit 7 of the mod-256 difference `a - b` tells
you whether `a < b`. This is correct as long as the two operands **differ by
less than 128**, which holds for the small unsigned values these programs work
with. It is *not* a signed comparison and it is not reliable if operands can be
more than 127 apart. Treat values as unsigned and keep them modest.

## Arrays (fixed-size, local)

`toycc` supports fixed-size local arrays of `int` bytes — see
`examples/bubblesort.toyc`:

```c
int a[10] = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3};  // size + initializers are constant
int a[4];                                     // uninitialized -> all zero
x = a[i];                                     // indexed read (i any expression)
a[i] = expr;                                  // indexed write
```

The size and the initializer values must be compile-time constants. An array is
laid out as a contiguous block of data bytes (like `arr:` in `examples/sum.toys`)
plus a base-pointer byte holding its address.

**How indexing works with no index register.** The Toy CPU has no index
register and no indirect load/store, so `a[i]` is compiled with **self-modifying
code** (the `sum.toys` / `bubblesort.toys` trick): compute the element address
`base + i`, write it into the address byte of a raw `LOAD` (or `STORE`)
instruction, then execute that instruction. `base` is the array's address, held
in a data byte the assembler fills in.

**Limitation — arrays are not saved/restored across recursive calls.** Scalar
locals are saved on the recursion stack around calls, but arrays are not (a whole
block would be expensive on 256 bytes). So a *recursive* function that keeps a
live array across a self-call would see it clobbered. Arrays in `main` and in
iterative (non-recursive) helpers are fine — the bubble sort above lives in
`main` and works. If you need an array preserved across recursion, hoist it out.

## Functions (non-recursive)

`toycc` supports multiple functions with parameters, calling each other — see
`examples/functions.toyc`:

```c
int square(int x) { return x * x; }
int sum_of_squares(int a, int b) { return square(a) + square(b); }
int main(void) { return sum_of_squares(3, 4); }   // 9 + 16 = 25
```

There is exactly one `main` (the entry point). **Recursion — self and mutual —
is supported** (see `examples/fibonacci_rec.toyc`).

### How calls work with no call/return instruction

The Toy CPU has no call/return, no stack pointer, and no indirect jump, so
`toycc` compiles each function with **global slots + marker dispatch**:

- Each function `f` gets fixed data bytes: one per parameter (`f__p_<name>`), a
  return-value slot (`f__ret`), and a return-marker slot (`f__mark`).
- Its body is emitted once, as a labeled block. `return e` stores `e` into
  `f__ret` and jumps to `f`'s dispatch.
- A call stores the arguments into the parameter slots, sets `f__mark` to a
  number identifying *this* call site, and jumps to the body.
- At the end of the body, a compare-chain on `f__mark` (`load f__mark; sub k;
  ifzero f__cont_k; …`) jumps back to the correct call site.

Arguments are fully evaluated into temporaries before any parameter slot is
written, so a nested call to the same function (`f(1, f(2,3))`) works.

### Recursion: a save/restore stack

Because a function has only one set of slots, a recursive call would clobber its
caller's values. So around **every** call, `toycc` saves the caller's live
values (the ones needed after the call) onto a real stack and restores them
afterward — giving each activation its own copies. The stack is one `sp` byte
plus self-modifying indirect load/store (the same trick as `sum.toys`), growing
*down* from address 255. This is the same mechanism the hand-written
`examples/fibonacci_rec.toys` uses, generated automatically.

### The `-O` flag

Save/restore around a call is only *needed* when the caller can be re-entered,
i.e. when the caller is recursive. `-O` / `--optimize-save-restore` (default
off) builds the call graph and *skips* save/restore at call sites whose caller
is non-recursive. Same results, smaller code. Default off keeps the compiler
uniform; `-O` makes it lean.

### Recursion depth limit

The stack grows down from 255 into whatever space is left above the program.
There is **no hardware bounds check**: if recursion goes deeper than the free
space, the stack overwrites data and the program gives wrong answers. On a
256-byte machine this space is small, so deep recursion is genuinely limited.
When little stack room remains, the compiler prints a warning; `-O` (smaller
code) and smaller inputs both buy depth. This is a real limit of the machine,
not a bug — the same "code and data share 256 bytes" reality as everywhere else.

## Memory model

Every variable and every function slot is a fixed data byte placed after the
code; the recursion stack occupies the top of memory and grows down toward the
data. A useful side effect of the code-then-data layout: the code/data boundary
is fixed, which is what `--detect-code-overwrite` (see the main README) relies
on.

## What is NOT supported

- Pointers, multi-dimensional arrays, and arrays passed to/returned from
  functions. Fixed-size local arrays ARE supported (see "Arrays" above), but
  they are not saved/restored across recursive calls.
- `void` functions are of limited use (there is no I/O or global state to
  affect), and a call used as a bare statement (`f();`) or a bare `return;` do
  not parse. Call functions in expression position: `y = f(a);`, `return f(a);`.
- Types other than `int` (`char`, `unsigned`, pointers, `float`, …).
- `do/while`, `switch`, `break`, `continue`, `goto`, the ternary `?:`.
- Short-circuit `&&` / `||` (the tokens are lexed but not compiled; build
  conditions with nested `if` instead).
- Standard library / `printf` / any I/O. The only "output" is the final ACC.
- Signed arithmetic and values/comparisons that rely on more than 8 bits.

If a program compiles to more than 256 bytes, `toycc` reports a clear
`too big` error and writes nothing (it checks the size via the assembler before
writing the `.toys`); keep programs small.

## Usage

```bash
# compile program.toyc -> program.toys
python3 compiler/toycc.py compiler/examples/fibonacci.toyc

# choose the output path
python3 compiler/toycc.py program.toyc -o build/program.toys

# compile and immediately run through toyasm (CLI, no pausing)
python3 compiler/toycc.py compiler/examples/fibonacci.toyc --run
```

Run a produced `.toys` directly through toyasm in the terminal (the graphical
debugger is toyasm's default, so pass `--cli`):

```bash
# from the repo root
python3 toyasm.py compiler/examples/fibonacci.toys --cli --run --quiet
# ...
# Result:  ACC = 55  (00110111  0x37  dec 55)
```

toyasm CLI flags used above: `--cli`/`-c` run in the terminal instead of the
GUI, `--run`/`-r` run all steps without pausing, `--quiet`/`-q` compact output.
Drop `--run` to single-step, or drop `--cli` to open the graphical debugger.

## Example programs

All examples live in [`examples/`](examples/) and are verified to produce the
expected accumulator result.

| File            | Computes                                   | Expected ACC |
|-----------------|--------------------------------------------|-------------:|
| `fibonacci.toyc` | fib(10) with an 8-bit overflow limit       | 55  |
| `multiply.toyc`  | 7 * 6 via repeated addition (`*`)          | 42  |
| `sevenfold.toyc` | 7 * 4                                       | 28  |
| `sum.toyc`       | 3+1+4+1+5+9+2 (separate vars, no arrays)    | 25  |
| `max.toyc`       | max(3,1,4,1,5,9,2) using `>`               | 9   |
| `countdown.toyc` | 5+4+3+2+1 via a countdown `while` loop      | 15  |
| `bitops.toyc`    | bitwise `&` `^`, shifts `>>` `<<`, `& 0x0F` | 36  |
| `factorial.toyc` | 5! via a `for` loop and `*`                | 120 |
| `gcd.toyc`       | gcd(48, 36) by subtraction, `if/else`, `>` | 12  |
| `ifelse.toyc`    | if/else picking `b - a` for `a < b`         | 5   |
| `bubblesort.toyc`| iterative bubble sort of 10 pi digits; returns `a[0]` | 1 |

Regenerate and re-verify them all:

```bash
cd /Users/manfred/github/pytoy
for f in compiler/examples/*.toyc; do
  python3 compiler/toycc.py "$f"
  python3 toyasm.py "${f%.toyc}.toys" --cli --run --quiet | tail -1
done
```

## How the compiler works (brief)

- **Lexer** turns the source into tokens, skipping `//` and `/* */` comments.
- **Parser** is recursive descent with a precedence-climbing expression parser;
  `for` is desugared to `while`, and compound assignments to `x = x op rhs`.
- **Code generator** evaluates every expression into ACC. Binary operators
  spill the right operand to a fresh temporary data byte, then reload the left
  operand and apply the matching opcode. Each C variable, each integer constant,
  and each temporary gets one named data byte placed after the code (so it is
  never executed). Comparisons and `!` materialize a 0/1 boolean; `if`/`while`
  conditions use a fast path that branches directly with `ifzero` where
  possible. `return` moves the value into ACC and emits `stop`.

The emitted `.toys` is commented and maps back to the source where helpful.
