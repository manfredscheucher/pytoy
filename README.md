<img src="doc-typst/images/screenshot.png" alt="toyasm" width="100%"/>


# toyasm

Assembler and simulator for the [Toy CPU](https://github.com/freedosproject/toycpu) in Python.

The Toy CPU is a minimal 8-bit processor with 256 bytes of memory, one
accumulator, and a program counter. It was built as a FreeDOS learning tool
with a switch-based interface (like an Altair 8800); this project keeps the same
CPU but replaces the binary switch input with readable assembly, a GUI, and a
CLI, plus a small C compiler on top.

It's deliberately simple, readable Python (standard library plus PySide6),
because the point is to *see* how a CPU works.

## The three files

- `toysim.py` — the simulator: runs programs, opens the GUI, has the CLI. **This
  is the one you run.**
- `toyasm.py` — the assembler: turns `.toys` assembly into a `.toyo` byte
  listing. Doesn't run anything.
- `toycpu.py` — the CPU core (opcodes, decode/execute). A library the other two
  import; not run directly.

## Quick start

```bash
pip install PySide6                                 # required for the default GUI

python3 toysim.py examples/fibonacci.toys           # open the GUI on an example
python3 toysim.py examples/fibonacci.toys --cli --run   # or run in the terminal

python3 toyasm.py examples/fibonacci.toys           # assemble -> examples/fibonacci.toyo
python3 toysim.py examples/fibonacci.toyo --run     # run a compiled .toyo directly

python3 compiler/toycc.py compiler/examples/multiply.toyc --run   # compile C and run
```

`toysim.py` opens a graphical interface by default (source + memory panels, with
Step / Run / Reset). Pass a `.toys` and it assembles first; pass a `.toyo` and
it loads and runs it. Use `-c` / `--cli` to run in the terminal instead — that
mode needs no PySide6. Run `python3 toysim.py -h` for all options.

## A taste of the syntax

```
        load  a         # acc = a
        add   b         # acc = a + b
        stop
a:      10              # data goes after stop
b:      20
```

See [`examples/`](examples/) for complete programs (Fibonacci, multiply, array
sum/max, …).

## Write it in C instead

toyasm also ships **toycc**, a compiler for a small subset of C that targets the
Toy CPU — often nicer than writing assembly by hand:

```c
int main(void) {
    int a = 7;
    int b = 6;
    return a * b;   // no multiply opcode -> compiled to repeated addition
}
```

```bash
python3 compiler/toycc.py compiler/examples/multiply.toyc --run  # -> ACC = 42
```

See [`compiler/`](compiler/) for the C compiler.

## Documentation

The full manual is a PDF built from Typst sources in
**[`doc-typst/`](doc-typst/)** — written for newcomers with no assembly
background. It covers: how a CPU works (memory, accumulator, program counter,
the fetch–execute cycle), the full instruction set, assembly syntax, worked
example programs, using the GUI and CLI, and the C → assembly pipeline.

Grab the prebuilt [`doc-typst/toyasm.pdf`](doc-typst/toyasm.pdf), or rebuild it
with [Typst](https://typst.app):

```bash
cd doc-typst && ./build.sh   # -> doc-typst/toyasm.pdf
```

## Credits & license

The Toy CPU instruction set is by Jim Hall (FreeDOS Project) — see its
[official page](https://jimhall.itch.io/toy-cpu) and
[source](https://github.com/freedosproject/toycpu). toyasm's own code
(assembler, GUI, CLI, compiler) is independent.

toyasm is MIT-licensed (see [`LICENSE`](LICENSE)). toycpu is MIT too; its
original notice is reproduced in [`NOTICE`](NOTICE). The manual's "About the Toy
CPU" chapter spells out exactly what was reused vs. written from scratch.
