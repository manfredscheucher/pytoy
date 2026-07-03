# Using pytoy

pytoy assembles a `.toy` file and then either opens a graphical interface
(the default) or runs it in the terminal.

## Requirements

- Python 3
- [PySide6](https://pypi.org/project/PySide6/) — only for the GUI. The CLI
  works without it.

```bash
pip install PySide6
```

## GUI (default)

Just point pytoy at a program:

```bash
python3 pytoy.py examples/fibonacci.toy
```

The window has:

- **Source panel** — your program, with the current instruction highlighted
  in yellow and any memory it references in green.
- **Memory panel** — every address and its value in binary, so you watch the
  bits change as the program runs.
- **Controls** — Step, Run, and Reset buttons.

Keyboard shortcuts:

| Key      | Action |
|----------|--------|
| `Space`  | Step one instruction |
| `R`      | Run to completion |
| `Escape` | Reset to the start |

Click any line to highlight it (orange) on both panels — handy for tracing
which memory box a label refers to.

## CLI

Use `-c` / `--cli` to run in the terminal instead of opening the window:

```bash
python3 pytoy.py examples/fibonacci.toy --cli
```

By default the CLI runs step-by-step with full verbose output; press Enter to
advance each instruction.

### CLI options

| Flag              | Effect |
|-------------------|--------|
| `-c`, `--cli`     | Run in the terminal instead of the GUI |
| `-r`, `--run`     | Run all steps without pausing |
| `-q`, `--quiet`   | Compact, one line per step |
| `-x`, `--export`  | Also write the compiled listing to a `.out` file |

Run `python3 pytoy.py -h` for the full list.

Examples:

```bash
# Run to the end, compact output:
python3 pytoy.py examples/multiply.toy --cli --run --quiet

# Assemble and export the byte layout to examples/max.out:
python3 pytoy.py examples/max.toy --cli --export --run
```

The final line reports the result in the accumulator in binary, hex, and
decimal.
