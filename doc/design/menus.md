# Design: the File and Help menus (and Line-numbers toggle)

A design note for the menu-bar additions Manfred asked for, recording what was
wanted and the decisions taken. The I/O widget and the View menu are documented
separately in [`io-gui.md`](io-gui.md); this covers File, Help, and the
line-number toggle. ktoy is to get the same menus afterwards (pytoy first).

## What Manfred asked for

- A **File menu** with Load (there is already a Load button) plus a **Save** of
  the current bytecode / asm / C, with a choice of which to export now that
  there is edit functionality.
- An **About / info menu** with a version number and commit info "like hex610".
- **Line numbers optional**, toggled from the View menu.
- And: review what else a menu could sensibly offer. Agreed additions (Manfred
  picked these from a list): **Reload** in the File menu, **keyboard shortcuts**
  on the menu items, and a **Help** entry with an instruction-set / shortcuts
  quick reference.

## File menu (`_build_file_menu`)

- **Load…** (`Cmd/Ctrl+O`) — mirrors the existing Load button (`_load_clicked`);
  the button stays. Same discard-edits confirmation.
- **Reload** (`Cmd/Ctrl+R`) — re-reads the current file from disk
  (`_reload_clicked`), which already existed; now reachable from the menu too.
  On macOS `QKeySequence.Refresh` is `Cmd+R`, so it does not clash with the bare
  `R` run/stop shortcut.
- **Save…** (`Cmd/Ctrl+S`) — `_save_clicked`. Asks **which format** to export,
  then where. The formats offered are **dynamic** (`_save_formats()`): only the
  ones that fit the loaded program.
  - `.toyo` (bytecode) — **always** available. Writes the *live* compiled byte
    image via `assembler.export(self.listing, self.syms, self.mem, path)`, so it
    reflects runtime state and any hand edits.
  - `.toys` (assembly) — when `self._asm_text` is present. Writes the current
    (possibly GUI-edited) assembly source.
  - `.toyc` (C) — only when `self._c_text is not None`, i.e. a C program was
    loaded. Writes the current C source.
  - With a single applicable format the picker is skipped.

Decision: the Save format follows what the program *is*, not a fixed list — a
bytecode-only load (`.toyo`) can't offer `.toys`/`.toyc` because that source
doesn't exist, and `.toyc` only makes sense after a C load. This matches the
"select which should be exported" ask without offering nonsense.

## Help menu (`_build_help_menu`)

- **Instruction set & shortcuts** — `_show_reference`, a read-only monospaced
  dialog (`show_text_dialog`). The text (`_REFERENCE_TEXT`) is **built from
  `core._INSTR`** at import time, so the 14-instruction table can't drift from
  the actual ISA; it also lists the GUI keyboard shortcuts.
- **About pytoy** — `_show_about`, a standard about box showing the build
  identity from `pytoy/version.py`.

## Version / commit info (`pytoy/version.py`)

Modelled on hex610's convention (version / commit / dirty / commitDate) so the
two projects report build identity the same way — but adapted to how pytoy runs:

- The release number lives in the top-level **`VERSION`** file (bump by hand).
- commit sha / dirty / commit-date are read from **git at runtime**
  (`git rev-parse --short`, `git status --porcelain`, `git show -s --format=%cI`).
  No build step (hex610 generates `version.js` at build time; pytoy runs straight
  from the checkout, so reading git live is simpler and always current).
- Everything **degrades gracefully**: no git or no VERSION file → fields become
  `None` / `"unknown"`, and About still shows something. This matters if pytoy is
  ever run outside a git checkout.

## Line numbers toggle

`View → Line numbers` (checkable, on by default). The line-number gutter in the
main C and assembly panels was always on; it is now `self._line_numbers`-gated in
both `_refresh_source` (asm) and `_refresh_c` (C). It is display-only — the gutter
is never part of `orig` or any saved file, since asm refers to lines by *label*,
not number.

The modal **C|asm comparison window** (shown when a `.toyc` is opened, before it
loads) keeps its gutter on regardless of the toggle: it is a transient
side-by-side where the line numbers are the whole point of lining C up against
asm, and it has no live link to the main window's view state. The toggle governs
the persistent panels only.

## Verified

- `tests/test_menu_and_version.py`: version-info keys + VERSION-file read + the
  no-git fallback; the reference text lists all 14 instructions (from `_INSTR`)
  and the shortcuts; the File/View/Help menus are present on a built window; the
  line-numbers toggle flips state; `_save_formats()` returns `.toyo` only for a
  bytecode load, `+.toys` with assembly, and all three for a C program.
- Full suite stays green (450 tests).

## TODO — ktoy

Port the same three menus (File / View-line-numbers / Help+About) to ktoy's
Compose `SimulatorScreen`. Build identity there follows the Kotlin-Multiplatform
`GeneratedVersionInfo` convention (as in hex610/OYS), not runtime git.
