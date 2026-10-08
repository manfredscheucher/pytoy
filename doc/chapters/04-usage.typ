= Using pytoy

One entry point, `run.py`, with subcommands. `run.py asm` is the *assembler*: it
turns a `.toys` file into a `.toyo` byte listing and nothing else. `run.py sim`
is the *simulator*: it runs a program and either opens a graphical interface (the
default) or runs it in the terminal. Point `run.py sim` at a `.toys` and it
assembles first; point it at a `.toyo` and it loads and runs it directly.

#figure(
  image("../images/screenshot.png", width: 100%),
  caption: [The pytoy GUI: source panel on the left (current instruction
    highlighted), memory panel on the right showing every byte in binary.],
)

== Requirements

- Python 3
- PySide6 --- only for the GUI. The CLI works without it.

```bash
pip install PySide6
```

== GUI (default)

Just point the simulator at a program (or run `python3 run.py` with no arguments
to open the GUI empty and load an example via the Load button):

```bash
python3 run.py sim examples/asm/03-programs/fibonacci_iter.toys
```

The window has:

- *Source panel* --- your program, with the current instruction highlighted in
  yellow and any memory it references in green. Each row is prefixed with a
  display-only line number (right-aligned, like `3 |`) matching the line numbers
  your text editor shows for the `.toys` file. The numbers are never written
  into the source or any saved file --- assembly refers to lines by label, so
  the numbering is just a reading aid.
- *Memory panel* --- every address and its value in binary, so you watch the
  bits change as the program runs.
- *Controls* --- Step, Run, and Reset buttons.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  table.header([*Key*], [*Action*]),
  [`Space`],  [Step one instruction],
  [`R`],      [Run to completion],
  [`Escape`], [Reset to the start],
)

Click any line to highlight it (orange) on both panels --- handy for tracing
which memory box a label refers to.

*Right-click the source panel* to open an _Edit assembly_ window: a plain-text
editor prefilled with the current program's assembly source. Change it and press
Save --- pytoy re-assembles the edited text fresh and reloads the program at
step 0, so you can tweak a program and re-run without leaving the GUI. If the
edited text has an assembly error, the error is shown and the editor stays open
so you can fix it; Cancel discards your changes. (A `.toyo` loaded as bytecode
has no assembly source, so right-click there just says there is nothing to
edit.)

Once you've edited the assembly this way, Load/Reload/Examples ask before
discarding it (the same confirmation that guards hand-edited memory), so a stray
Reload can't silently throw your edit away.

=== Loading C --- the C #sym.arrow assembly view

The Load button also accepts C sources (`.toyc`), and so does the Examples
browser (which lists the C examples grouped per compiler). A C file is never
loaded blindly: pytoy compiles it first and opens a *C #sym.arrow assembly
window* so you see exactly what the compiler produced before anything runs.

The window shows two panels side by side: your C source on the left and the
generated assembly on the right, each with the same line-number gutter as the
main source panel. The title says which compiler was used (`minicc` or `toycc`).
*Click a line on either side* to highlight it and every matching line on the
other: one C statement normally compiles to several assembly lines, so clicking
`int x = 5;` lights up its `load`/`store` pair, and clicking an assembly line
lights up the C statement it came from. Lines with no counterpart (the generated
header, data bytes) simply don't highlight.

Press *Load* to assemble the shown assembly and load it into the simulator at
step 0 (Cancel discards it). The compiler records which C line each assembly
line came from as a harmless `\# @c:N` comment on the line; the assembler ignores
comments, so the loaded program is byte-for-byte what you'd get without them, and
the markers stay visible in the assembly panel. If the C source fails to compile,
the error is shown and no window opens. For a `.toyc` opened via Load (where you
haven't picked a compiler), pytoy tries both and prefers `toycc` --- the fuller
one --- when both accept the file; the Examples browser uses the compiler of the
node you picked. Reload remembers that choice: reloading the same `.toyc` reuses
the compiler it was loaded with, so a file both compilers accept doesn't silently
switch between them.

== CLI

Use `-c` / `--cli` to run in the terminal instead of opening the window:

```bash
python3 run.py sim examples/asm/03-programs/fibonacci_iter.toys --cli
```

By default the CLI runs step-by-step with full verbose output; press Enter to
advance each instruction.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  table.header([*Flag*], [*Effect*]),
  [`-c`, `--cli`],    [Run in the terminal instead of the GUI],
  [`-r`, `--run`],    [Run all steps without pausing],
  [`-q`, `--quiet`],  [Compact, one line per step],
  [`-x`, `--export`], [Also write the compiled listing to a `.toyo` file],
)

Run `python3 run.py sim -h` for the full list.

`sim` expects an assembly (`.toys`) or bytecode (`.toyo`) program. Pointing it at
a C source (`.toyc`) stops with a hint to compile it first (`run.py cc …`); the
C #sym.arrow assembly view is a GUI feature, reached via the Load/Examples
buttons.

```bash
# Run to the end, compact output:
python3 run.py sim examples/asm/02-extended/multiply_repeated.toys --cli --run --quiet

# Assemble to a standalone .toyo, then run it:
python3 run.py asm examples/asm/03-programs/max_array.toys      # -> examples/asm/03-programs/max_array.toyo
python3 run.py sim examples/asm/03-programs/max_array.toyo --cli --run
```

The final line reports the result in the accumulator in binary, hex, and
decimal.

Two ready-made `.toyo` examples are checked in under `examples/toyo/`
(`sum3.toyo` and `fibonacci.toyo`), so you can try loading a compiled byte
listing without assembling one first. They were generated from the matching
assembly sources with `run.py asm`:

```bash
python3 run.py asm examples/asm/03-programs/sum3.toys      -o examples/toyo/sum3.toyo
python3 run.py asm examples/asm/03-programs/fibonacci_iter.toys -o examples/toyo/fibonacci.toyo
```

Loading a `.toyo` shows only the memory panel — a compiled listing carries no
re-runnable source. (Most `.toyo` files are build artifacts and git-ignored;
these two are committed on purpose as examples.)

== Memory limits and code-overwrite detection

The Toy CPU has exactly 256 bytes, shared by code and data. Two things can go
wrong at that boundary, and pytoy handles both:

*Too big to fit.* If a program assembles to more than 256 bytes, the assembler
stops with a clear message rather than crashing:

```
ERROR: Program is too big: it needs 402 bytes, but the Toy CPU has only 256.
```

The C compiler `toycc` performs the same check on its generated output, so an
oversized C program is caught at compile time instead of failing later.

*Overwriting code.* Because code and data share memory, a `store` can write over
your own instructions. That is a legitimate technique (the array examples use it
deliberately --- see the writing-programs chapter), so it is allowed by default.
But when you _don't_ mean to do it, it is a nasty bug. The optional
`-d` / `--detect-code-overwrite` flag turns on a guard:

```bash
python3 run.py sim myprog.toys --cli -d
```

The guard uses the `# data` marker in your source --- a line whose only content
is `# data` --- to know where the code region ends and data begins. If a `store`
writes below that line (into code), the simulator warns and asks whether to continue; in
the GUI it pops up a dialog. If the program has no `# data` marker, the guard
can't know the boundary and prints a note that detection is off. The flag is off
by default, keeping the bare machine's "anything goes" behaviour unless you opt
in.
