# pytoy documentation (Typst source)

This is the source for the pytoy PDF manual — the primary documentation.

- `main.typ` — the document: title page, outline, and `#include`s of each chapter.
- `chapters/` — one file per chapter (concepts, instruction set, assembly,
  usage, compiler pipeline, Toy CPU background).
- `images/` — screenshots used in the PDF.

## Build the PDF

```bash
./build.sh
# or directly:
typst compile main.typ pytoy.pdf
```

Requires [Typst](https://typst.app) (`brew install typst` on macOS). The output
`pytoy.pdf` is written next to `main.typ`.

While editing, `typst watch main.typ pytoy.pdf` rebuilds on save.
