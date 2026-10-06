# toycc — a tiny C-to-assembly compiler for the Toy CPU

`toycc` compiles a small, standard-looking subset of C into `.toys` assembly
that the [simulator](../pytoy/simulator.py) can run (and that the
[assembler](../pytoy/assembler.py) turns into a `.toyo` byte listing).

It is a single self-contained Python module (`pytoy/compiler.py`): a hand-written
lexer, a recursive-descent parser, and a straightforward code generator that
emits readable Toy assembly. No external libraries — Python standard library
only.

## The target machine (and why C is so restricted here)

The Toy CPU (see the [manual](../doc/)) is deliberately minimal:

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
- **I/O is not supported.** Fixed-size local arrays ARE supported (see "Arrays"
  below), as are one-byte **pointers** (`int *p`, `&x`, `*p` — see "Pointers"),
  and functions — including recursive and mutually recursive ones (see below).
  An array can be passed to a function, where it decays to a pointer.

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
- Pointers: `int *p;`, `int *p = &x;`, `&x`, `&a[i]`, `*p` (read), `*p = expr;`
  (write, incl. compound forms) — see "Pointers" below
- Bare call statement: `f(a);` (the return value is discarded)
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
sign-bit trick from `examples/asm/03-programs/max_array.toys`: bit 7 of the mod-256 difference `a - b` tells
you whether `a < b`. This is correct as long as the two operands **differ by
less than 128**, which holds for the small unsigned values these programs work
with. It is *not* a signed comparison and it is not reliable if operands can be
more than 127 apart. Treat values as unsigned and keep them modest.

If you do need comparisons that are correct across the full 0–255 range, pass
`--safe-compare`. It emits a proper unsigned comparison (bit 7 of the borrow
from `a - b`) for `<`, `>`, `<=`, `>=`. The trade-off is size: each such compare
grows by ~30 bytes, so tight programs may no longer fit. It is a correctness vs.
size choice, not an optimization, so `-O` does **not** turn it on.

## Arrays (fixed-size, local)

`toycc` supports fixed-size local arrays of `int` bytes — see
`examples/c/sort_array_inline.toyc`:

```c
int a[10] = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3};  // size + initializers are constant
int a[4];                                     // uninitialized -> all zero
x = a[i];                                     // indexed read (i any expression)
a[i] = expr;                                  // indexed write
```

The size and the initializer values must be compile-time constants. An array is
laid out as a contiguous block of data bytes (like `arr:` in `examples/asm/03-programs/sum_array.toys`)
plus a base-pointer byte holding its address.

**How indexing works with no index register.** The Toy CPU has no index
register and no indirect load/store, so `a[i]` is compiled with **self-modifying
code** (the `examples/asm/03-programs/sum_array.toys` / `examples/asm/03-programs/sort_array.toys` trick): compute the element address
`base + i`, write it into the address byte of a raw `LOAD` (or `STORE`)
instruction, then execute that instruction. `base` is the array's address, held
in a data byte the assembler fills in.

**Limitation — arrays are not saved/restored across recursive calls.** Scalar
locals are saved on the recursion stack around calls, but arrays are not (a whole
block would be expensive on 256 bytes). So a *recursive* function that keeps a
live array across a self-call would see it clobbered. Arrays in `main` and in
iterative (non-recursive) helpers are fine — the bubble sort above lives in
`main` and works. If you need an array preserved across recursion, hoist it out.

## Pointers (one-byte addresses)

An address on the Toy CPU is just a byte (0–255), so a pointer is an ordinary
one-byte variable that happens to hold an address:

```c
int x = 5;
int *p;          // pointer declaration (a one-byte scalar)
p = &x;          // &x  -> address of x
*p = 9;          // write through the pointer: x becomes 9
int y = *p;      // read through the pointer
int *q = &a[i];  // &a[i]  -> address of an array element
```

`&x` compiles to a data byte initialised to `x`'s address (the assembler fills
in the label), exactly like an array's base-pointer byte. `*p` (read) and
`*p = expr` (write) use the **self-modifying-code trick**: the address in `p` is
patched into the address byte of a raw `LOAD`/`STORE`, which is then executed —
the same mechanism as array indexing.

**Arrays decay to pointers as parameters.** A function can take an array:

```c
int suma(int a[], int n) { int s = 0; for (int i = 0; i < n; i += 1) s += a[i]; return s; }
int main(void) { int v[3] = {4, 5, 6}; return suma(v, 3); }   // 15
```

The caller passes the array's base address; inside the function `a` is a pointer
and `a[i]` means `*(a + i)` — indirect access through the passed address. So a
function can sort or fill the caller's array **in place** (see
`examples/c/sort_array_function.toyc`). This unifies indexing: `a[i]` computes
`(value of a) + i` whether `a` is a real local array (its name evaluates to its
base address) or a pointer/parameter (its byte holds the address).

**Limitation — no `&local` inside a recursive function.** `&x` is the address of
`x`'s single global slot, but a recursive function keeps each activation's value
on the save/restore stack, so a pointer can't follow it. Taking a local's address
(`&x` or `&a[i]`) inside a recursive function is therefore a **compile error**
(same spirit as the recursive-local-array rejection). In non-recursive code it
works fully: a callee that writes `*p` really changes the caller's `x`, because an
address-taken local is not save/restored (its value lives in its memory slot).

## Functions (non-recursive)

`toycc` supports multiple functions with parameters, calling each other — see
`examples/c/functions.toyc`:

```c
int square(int x) { return x * x; }
int sum_of_squares(int a, int b) { return square(a) + square(b); }
int main(void) { return sum_of_squares(3, 4); }   // 9 + 16 = 25
```

There is exactly one `main` (the entry point). **Recursion — self and mutual —
is supported** (see `examples/c/fibonacci_rec.toyc`).

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
plus self-modifying indirect load/store (the same trick as `examples/asm/03-programs/sum_array.toys`), growing
*down* from address 255. This is the same mechanism the hand-written
`examples/asm/03-programs/fibonacci_rec.toys` uses, generated automatically.

### Save/restore is automatic; `--stackfree`

Save/restore around a call is only *needed* when the caller can be re-entered,
i.e. when the caller is recursive. That is fully determined by the call graph,
so the compiler does it **automatically**: save/restore is inserted only at call
sites whose caller is recursive, and skipped everywhere else. A program with no
recursion therefore emits no push/pop and no `sp` byte at all — nothing to
configure.

`--stackfree` makes that a hard requirement: compile with **no call stack**, all
state in global slots. If any function recurses (a cycle in the call graph), it
is an error, because recursion genuinely needs a stack. Use it to guarantee a
stack-free, all-global translation (and to catch accidental recursion).

### The `-O` flag

`-O` / `--optimize` turns on the size optimizations: `--fold-constants`
(constant folding + identity simplification) and `--compact-codegen` (smaller
shift / `== 0` / unary-minus codegen). All are off by default so the plain
output stays a direct, readable translation. `-O` does **not** enable
`--safe-compare` or `--stackfree` (those are correctness/mode choices, not size
wins).

### Recursion depth limit

The stack grows down from 255 into whatever space is left above the program.
There is **no hardware bounds check**: if recursion goes deeper than the free
space, the stack overwrites data and the program silently gives wrong answers.
On a 256-byte machine this space is small, so deep recursion is genuinely
limited.

The compiler prints a warning when the *compiled program itself* leaves little
stack room (a **static** check on code+data size). Note this is **not** a depth
guard: because the code size doesn't grow with the recursion argument, a program
that fits with headroom shows no warning yet can still overflow at run time if it
recurses deep enough. So the warning catches "this program barely fits," not
"this run will recurse too deep." Keep recursion shallow, use `-O` (smaller
code) and small inputs. This is a real limit of the machine, not a bug — the same
"code and data share 256 bytes" reality as everywhere else.

(Non-recursive programs never hit this: save/restore is skipped automatically and
there is no stack to overflow.)

## Memory model

Every variable and every function slot is a fixed data byte placed after the
code; the recursion stack occupies the top of memory and grows down toward the
data. A useful side effect of the code-then-data layout: the code/data boundary
is fixed, which is what `--detect-code-overwrite` (see the main README) relies
on.

## What is NOT supported

- Multi-dimensional arrays, pointer arithmetic beyond `p + i` / `&a[i]`,
  pointers-to-pointers, and returning arrays/pointers from functions.
  One-byte pointers (`int *p`, `&x`, `*p`) and array-decays-to-pointer
  parameters ARE supported (see "Pointers" above); local arrays are not
  saved/restored across recursive calls.
- `void` functions are of limited use (there is no I/O or global state to
  affect). A call used as a bare statement (`f(a);`) DOES parse now (its result
  is discarded); a bare `return;` still does not.
- Types other than `int` (`char`, `unsigned`, `float`, …). A pointer is just a
  one-byte `int` holding an address.
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
python3 run.py cc examples/c/fibonacci_iter.toyc

# choose the output path
python3 run.py cc program.toyc -o build/program.toys

# compile and immediately run through the simulator (CLI, no pausing)
python3 run.py cc examples/c/fibonacci_iter.toyc --run
```

Run a produced `.toys` directly through the simulator in the terminal (the
graphical debugger is the default, so pass `--cli`):

```bash
# from the repo root
python3 run.py sim examples/c/fibonacci_iter.toys --cli --run --quiet
# ...
# Result:  ACC = 55  (00110111  0x37  dec 55)
```

Simulator CLI flags used above: `--cli`/`-c` run in the terminal instead of the
GUI, `--run`/`-r` run all steps without pausing, `--quiet`/`-q` compact output.
Drop `--run` to single-step, or drop `--cli` to open the graphical debugger.

## Example programs

All examples live in [`examples/c/`](../examples/c/) and are verified to produce
the expected accumulator result.

| File               | Computes                                        | Expected ACC |
|--------------------|-------------------------------------------------|-------------:|
| `sum3.toyc`        | a+b+c for the first 3 pi digits (3,1,4)         | 8   |
| `max3.toyc`        | max(3,1,4) via `>`                              | 4   |
| `sort3.toyc`       | sort 3,1,4 and return the smallest              | 1   |
| `multiply.toyc`    | 7 * 6 via repeated addition (`*`)               | 42  |
| `sevenfold.toyc`   | 7 * 4                                           | 28  |
| `countdown.toyc`   | 5+4+3+2+1 via a countdown `while` loop          | 15  |
| `bitops.toyc`      | bitwise `&` `^`, shifts `>>` `<<`, `& 0x0F`     | 36  |
| `popcount.toyc`    | count set bits of 37 (`x & 1`, `>>`)            | 3   |
| `ifelse.toyc`      | if/else picking `b - a` for `a < b`             | 5   |
| `functions.toyc`   | helper functions calling each other             | 25  |
| `fibonacci_iter.toyc` | fib(10), iterative                           | 55  |
| `fibonacci_rec.toyc`  | fib(10), recursive                           | 55  |
| `fibonacci_array.toyc`| first 10 Fibonacci numbers in an array; a[9] | 34  |
| `count_iter.toyc`  | count up to 10, iterative (`while` loop)        | 10  |
| `count_rec.toyc`   | count up to 10, recursive                       | 10  |
| `gcd_iter.toyc`    | gcd(48,36) by subtraction, iterative            | 12  |
| `gcd_rec.toyc`     | gcd(48,36) by subtraction, recursive            | 12  |
| `sum_array.toyc`   | sum of an array of the 10 pi digits             | 39  |
| `max_array.toyc`   | max of an array of the 10 pi digits             | 9   |
| `sort_array_inline.toyc`  | bubble sort of the 10 pi digits (array in main); a[0] | 1 |
| `sort_array_function.toyc` | bubble sort in a FUNCTION (array by pointer); a[0] | 1   |

The generated `.toys` files are build artifacts (not tracked in git). Build and
re-verify all of them from the C sources with one command:

```bash
python3 scripts/build_examples.py
```

It compiles every `examples/c/*.toyc`, writes the `.toys` next to it, and
checks each result against its `// expect:` header.

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

## minicc — the minimal version for reading

If you want to see the whole idea in one short, linear file, read
[`pytoy/minicc.py`](../pytoy/minicc.py). It is a cut-down teaching compiler:
`main()` only (so no call stack, no recursion, no function machinery) and no
optimizations. It still compiles most single-function examples. Details in
[`doc/design/minicc.md`](../doc/design/minicc.md).

    python3 -m pytoy.minicc examples/c/sum_array.toyc --run
