<img src="doc-typst/images/screenshot.png" alt="toyasm" width="100%"/>


# toyasm

Assembler and simulator for the [Toy CPU](https://github.com/freedosproject/toycpu) in Python.

The Toy CPU is a minimal 8-bit processor with 256 bytes of memory, one
accumulator, and a program counter. It was built as a FreeDOS learning tool
with a switch-based interface (like an Altair 8800); toyasm keeps the same CPU
but replaces the binary switch input with readable assembly, a GUI, and a CLI.

It's deliberately simple, readable Python — standard library plus PySide6, the
whole machine in one file — because the point is to *see* how a CPU works.

## Quick start

```bash
pip install PySide6                          # required for the default GUI
python3 toyasm.py examples/fibonacci.toys    # opens the GUI
python3 toyasm.py examples/fibonacci.toys -c # or run in the terminal (--cli)
```

By default toyasm opens a graphical interface (source + memory panels, with
Step / Run / Reset). Use `-c` / `--cli` to run in the terminal instead — that
mode needs no PySide6. Run `python3 toyasm.py -h` for all options.

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

The Toy CPU instruction set is by Jim Hall (FreeDOS Project), from the
[toycpu](https://github.com/freedosproject/toycpu) project. toyasm's own code
(assembler, GUI, CLI, compiler) is independent.

toyasm is MIT-licensed (see [`LICENSE`](LICENSE)). toycpu is MIT too; its
original notice is reproduced in [`NOTICE`](NOTICE). The manual's "About the Toy
CPU" chapter spells out exactly what was reused vs. written from scratch.
