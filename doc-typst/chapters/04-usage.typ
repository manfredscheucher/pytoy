= Using toyasm

Two tools do the work. `toyasm.py` is the *assembler*: it turns a `.toys` file
into a `.toyo` byte listing and nothing else. `toysim.py` is the *simulator*:
it runs a program and either opens a graphical interface (the default) or runs
it in the terminal. Point `toysim.py` at a `.toys` and it assembles first;
point it at a `.toyo` and it loads and runs it directly.

#figure(
  image("../images/screenshot.png", width: 100%),
  caption: [The toyasm GUI: source panel on the left (current instruction
    highlighted), memory panel on the right showing every byte in binary.],
)

== Requirements

- Python 3
- PySide6 --- only for the GUI. The CLI works without it.

```bash
pip install PySide6
```

== GUI (default)

Just point toysim at a program:

```bash
python3 toysim.py examples/fibonacci.toys
```

The window has:

- *Source panel* --- your program, with the current instruction highlighted in
  yellow and any memory it references in green.
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

== CLI

Use `-c` / `--cli` to run in the terminal instead of opening the window:

```bash
python3 toysim.py examples/fibonacci.toys --cli
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

Run `python3 toysim.py -h` for the full list.

```bash
# Run to the end, compact output:
python3 toysim.py examples/multiply.toys --cli --run --quiet

# Assemble to a standalone .toyo, then run it:
python3 toyasm.py examples/max_array.toys           # -> examples/max_array.toyo
python3 toysim.py examples/max_array.toyo --cli --run
```

The final line reports the result in the accumulator in binary, hex, and
decimal.

== Memory limits and code-overwrite detection

The Toy CPU has exactly 256 bytes, shared by code and data. Two things can go
wrong at that boundary, and toyasm handles both:

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
python3 toysim.py myprog.toys --cli -d
```

The guard uses the `# data` marker in your source --- a line whose only content
is `# data` --- to know where the code region ends and data begins. If a `store`
writes below that line (into code), toyasm warns and asks whether to continue; in
the GUI it pops up a dialog. If the program has no `# data` marker, the guard
can't know the boundary and prints a note that detection is off. The flag is off
by default, keeping the bare machine's "anything goes" behaviour unless you opt
in.
