<img src="doc-typst/images/screenshot.png" alt="pytoy" width="100%"/>


# pytoy

A Python toolbox for the [Toy CPU](https://github.com/freedosproject/toycpu): an
assembler, a simulator with a GUI, and a small C compiler.

The Toy CPU is a minimal 8-bit processor with 256 bytes of memory, one
accumulator, and a program counter. It was built as a FreeDOS learning tool
with a switch-based interface (like an Altair 8800); this project keeps the same
CPU but replaces the binary switch input with readable assembly, a GUI, and a
CLI, plus a small C compiler on top.

It's deliberately simple, readable Python (standard library plus PySide6),
because the point is to *see* how a CPU works.

## The package and entry point

`run.py` at the repo root is the single entry point, with subcommands (`sim`,
`asm`, `cc`). The code lives in the `pytoy` package:

- `pytoy/simulator.py` — the simulator: runs programs, opens the GUI, has the
  CLI (`run.py sim`).
- `pytoy/assembler.py` — the assembler: turns `.toys` assembly into a `.toyo`
  byte listing (`run.py asm`).
- `pytoy/core.py` — the CPU core (opcodes, decode/execute). A library the others
  import.
- `pytoy/compiler.py` — the C compiler (`run.py cc`).

## Quick start

```bash
pip install PySide6                                 # required for the default GUI

python3 run.py                                       # open the GUI empty (Load an example)
python3 run.py sim examples/asm/fibonacci.toys       # open the GUI on an example
python3 run.py sim examples/asm/fibonacci.toys --cli --run   # or run in the terminal

python3 run.py asm examples/asm/fibonacci.toys       # assemble -> examples/asm/fibonacci.toyo
python3 run.py sim examples/asm/fibonacci.toyo --run # run a compiled .toyo directly

python3 run.py cc examples/c/multiply.toyc --run     # compile C and run
```

`run.py sim` opens a graphical interface by default (source + memory panels, with
Step / Run / Reset). With no arguments, `run.py` opens the GUI empty — load an
example via the Load button. Pass a `.toys` and it assembles first; pass a
`.toyo` and it loads and runs it. Use `-c` / `--cli` to run in the terminal
instead — that mode needs no PySide6. Run `python3 run.py sim -h` for all
options.

## A taste of the syntax

```
        load  a         # acc = a
        add   b         # acc = a + b
        stop
a:      10              # data goes after stop
b:      20
```

See [`examples/asm/`](examples/asm/) for complete programs (Fibonacci, multiply,
array sum/max, …).

## Write it in C instead

pytoy also ships **toycc**, a compiler for a small subset of C that targets the
Toy CPU — often nicer than writing assembly by hand:

```c
int main(void) {
    int a = 7;
    int b = 6;
    return a * b;   // no multiply opcode -> compiled to repeated addition
}
```

```bash
python3 run.py cc examples/c/multiply.toyc --run  # -> ACC = 42
```

See [`compiler/`](compiler/) for the C compiler.

## Documentation

The full manual is a PDF built from Typst sources in
**[`doc-typst/`](doc-typst/)** — written for newcomers with no assembly
background. It covers: how a CPU works (memory, accumulator, program counter,
the fetch–execute cycle), the full instruction set, assembly syntax, worked
example programs, using the GUI and CLI, and the C → assembly pipeline.

Grab the prebuilt [`doc-typst/pytoy.pdf`](doc-typst/pytoy.pdf), or rebuild it
with [Typst](https://typst.app):

```bash
cd doc-typst && ./build.sh   # -> doc-typst/pytoy.pdf
```

## Credits & license

The Toy CPU instruction set is by Jim Hall (FreeDOS Project) — see its
[official page](https://jimhall.itch.io/toy-cpu) and
[source](https://github.com/freedosproject/toycpu). pytoy's own code
(assembler, GUI, CLI, compiler) is independent.

pytoy is MIT-licensed (see [`LICENSE`](LICENSE)). toycpu is MIT too; its
original notice is reproduced in [`NOTICE`](NOTICE). The manual's "About the Toy
CPU" chapter spells out exactly what was reused vs. written from scratch.
