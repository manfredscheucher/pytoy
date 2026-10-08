# C in the simulator — design

Feature: open a C file in the GUI, auto-compile it, show a C-vs-asm view, load the
asm. Plus a runtime Examples browser. Decided with Manfred; built pytoy-first,
then ported to ktoy.

## Decisions (from Manfred)

- **Flow**: C → asm → GUI. Loading a `.toyc` compiles it, shows a C|asm window
  (own window in pytoy; maybe an overlay in ktoy), and OK loads the asm into the
  existing asm↔bytecode simulator. The simulator stays asm-based.
- **C↔asm highlighting**: the compiler tracks a C-line → asm-line mapping so the
  window can highlight corresponding lines on both sides. One C line often maps to
  several asm lines; statement-level granularity is enough.
- **Mapping storage**: IN-MEMORY only (GUI-internal). The `.toys` text format does
  NOT change; `compile_source(..., with_line_map=True)` returns the map as an extra
  value. The GUI holds it while the compiled program is loaded; never written to disk.
- **minicc vs toycc**: selectable separately. The Examples browser lists C examples
  per compiler (minicc = minimal, toycc = full; a given .toyc may support one or both).
- **Examples**: enumerated at RUNTIME from the examples/ folder (not a hardcoded
  list), grouped: asm by subfolder, C by compiler, bytecode (.toyo). Same approach
  in ktoy, where examples ship as assets and are enumerated at runtime.
- **Own-file upload**: the Load dialog also accepts user files (.toys/.toyo/.toyc).

## Parts (parallelism)

1. **Compiler C↔asm line map** (compiler.py + minicc.py). `annotate_c_lines=True`
   tags each emitted asm line with a trailing `# @c:N` comment (see "Decided
   after kickoff" below). Default path unchanged (byte-identical output). Tests.
   — INDEPENDENT.
2. **Runtime example enumeration** (new module). Scans examples/, categorises
   asm/c/toyo, detects minicc-vs-toycc compatibility per C example. Tests. — INDEPENDENT.
3. **GUI compile+load + C|asm window** (simulator.py). Load accepts .toyc → compile
   → 2-column C|asm window with cross-highlighting (mirrors asm↔bytecode) → OK loads
   asm. Needs Part 1. **DONE** (see "Part 3 implementation" below).
4. **Examples browser UI** (simulator.py). "Examples" entry lists enumerated
   examples grouped by type; selecting a C one compiles with the chosen compiler.
   Needs Part 2.

Parts 1+2 run in parallel; then 3 (needs 1) and 4 (needs 2). Each part is tested
and fresh-reviewed before integration. Loop until reviewers are satisfied.

## Decided after kickoff: mapping persisted as asm comment

The C-line → asm-line mapping is written into the .toys as a trailing `# @c:N`
comment on each emitted line (opt-in via `annotate_c_lines=True`; default output
unchanged). It survives save/reload; the assembler ignores comments so the mem
image is identical. (Supersedes the earlier "in-memory only" note.)

Implementation (how the C line reaches each asm line):

- The parser records each statement node's C line in a `stmt_lines` side-map
  keyed by `id(node)` (toycc: `Parser.stmt_lines`, stamped in `parse_statement`;
  minicc: same, in `parse_stmt`). Statement-level granularity only.
- toycc rebuilds the AST (fold → CallLifter → a liveness pass → a peephole that
  drops lines), so the map is CARRIED forward: `_carry_line(old, new)` at every
  statement rebuild in `fold_stmt`/`_rename`/the liveness `if`/`while`/`block`
  rebuilds, and a per-statement `self._cur_line` that `self._stamp(node)` applies
  to the nodes `_lift_stmt`/`lift_call`/`_expand_call` create. The pre-lift AST
  stays alive through codegen, so `id()` can't be reused under us.
- Codegen tags emitted lines: `gen_stmt` sets `self._cur_c_line` (save/restore
  around nested children), and `emit`/`comment` push it onto a parallel
  `code_lines` list. `_peephole` filters `code_lines` in lockstep with `code`, so
  a dropped `load` drops its line entry too. Only after the peephole is each line
  annotated — so the marker lands on the correct FINAL line. minicc has no
  transforms and no peephole, so it just annotates `self.code` in `finish`.
- The marker is appended as `  # @c:N` (fresh comment) or ` @c:N` inside an
  existing comment; either way there is exactly one comment, which the assembler
  ignores. The GUI (`simulator._compile_c`, Examples browser) passes
  `annotate_c_lines=True`; the CLI/`build_examples` keep the default (off).

## Also requested (pytoy + ktoy, tested + documented + slides)

5. **asm line numbers in the view** — show line numbers in the source panel's
   display ONLY (not written into the asm, since labels exist). pytoy + ktoy.
   DONE (pytoy): `_refresh_source` in `pytoy/simulator.py` prepends a right-aligned
   gutter `f"{i+1:>{w}} | "` (w = digit count of the listing length) to each row,
   1-based, one number per listing row (comments/blank/data included) so it matches
   the text-editor line of the `.toys` file. The gutter is built inside the render
   loop only; `orig` and saved files are untouched. Click-to-select is unaffected
   (`_source_clicked` maps by `blockNumber()`, and the gutter is inline, not an
   extra line). The row highlight (HL_PC/SELECTED/ARG/DATA/CODE) spans the whole
   row including the gutter, like an editor's current-line highlight. Test:
   `tests/test_source_gutter.py`.
6. **asm edit mode** — right-click the asm (left) panel → a window opens to edit
   the assembly text → Save re-assembles it fresh and reloads. pytoy + ktoy.
   DONE (pytoy): the loaded program's source is now retained as `self._asm_text`
   in `_load_asm_text` (set to `None` in `_load_toyo_text` and the constructor,
   since a `.toyo`/empty window has no source). The source panel gets
   `setContextMenuPolicy(Qt.CustomContextMenu)` and
   `customContextMenuRequested → _edit_asm_clicked`; this is a separate mechanism
   from the existing left-click `mouseReleaseEvent = _source_clicked`, so
   select-address still works. `_edit_asm_clicked` guards the no-source case (an
   info box, no-op) and the live-edit discard (`_confirm_discard`, same as
   Load/Reload), then opens `EditAsmDialog` (mirrors ExamplesDialog: resizable
   QDialog, monospace editable QTextEdit prefilled with `_asm_text`,
   Save/Cancel). Save routes the edited text through the SAME re-assemble+load
   path as a fresh load (`_load_asm_text(text, _current_path or "<edited>")`):
   success reloads at step 0 and updates `_asm_text`; failure shows the shared
   error dialog and keeps the editor open. Test: `tests/test_edit_asm_gui.py`.

NOTE on orchestration: parts 4, 5, 6 all touch simulator.py — they must be done
SERIALLY (one at a time), not in parallel, to avoid clobbering the same file.
Part 1 (compiler.py/minicc.py) and Part 2 (examples_index.py) don't touch
simulator.py and run in parallel with it.

## Mirror for highlighting

The asm↔bytecode link already works via: listing tuples `(addr, bytes, orig,
is_data)` + `addr_to_line` / `line_to_addr` maps built in `load_program`
(simulator.py ~658-688), highlighted in `_refresh_source` / `_refresh_memory`.
C↔asm mirrors this: a `c_line → asm_lines` map drives the C|asm window's
two-sided highlight, reusing `highlight_row()`.

## Part 3 implementation (DONE)

GUI compile+load + the C|asm window, all in `pytoy/simulator.py`. Test file:
`tests/test_casm_window.py` (plus updated `tests/test_examples_browser.py`).

- **Line map** — module-level pure `parse_c_line_map(asm_text)` returns
  `(c_to_asm, asm_to_c)`: it scans each asm line for an `@c:N` marker (regex
  `@c:(\d+)`, matches both the standalone `# @c:N` and the embedded-in-a-comment
  form), building `c_line → sorted [0-based asm rows]` and the inverse
  `asm row → c_line`. The asm indices are 0-based rows so a QTextEdit
  `blockNumber()` from a click maps straight through. Unattributed lines
  (headers, data, blanks) carry no marker and are absent from both maps.
- **The window** — `CAsmDialog(QDialog)`, a closure-local class mirroring
  `EditAsmDialog`/`ExamplesDialog`. Two read-only monospace panels in a
  horizontal `QSplitter` (C left, asm right), each with the same right-aligned
  line-number gutter as the main source panel. Rendering reuses
  `highlight_row()` with `HL_SELECTED`. Title shows the compiler; the OK button
  is relabelled "Load".
- **Cross-highlight: CLICK, not hover** (judgment call — matches the prompt's
  recommendation and the existing `_source_clicked`). `mouseReleaseEvent` on
  each panel resolves `blockNumber()` to a C line (left: row+1; right: via
  `asm_to_c`) and calls `select_c_line()`, which stores the selected C line and
  re-renders both panels: the C line tinted on the left, all its `c_to_asm` rows
  tinted on the right. One C line → many asm rows is the normal case. Clicking an
  unattributed asm line clears the selection (maps to `None`).
- **Routing** — `_compile_and_show_casm(c_text, compiler, path)` is shared by
  both entry points: compiles with `annotate_c_lines=True`, pops
  `show_error_dialog` on failure (no window), else opens the window; on OK
  (`exec() == Accepted`) it sets `_current_path`/Reload/title.
  - *Load dialog*: filter gained `*.toyc`; `_load_toyc(path)` reads the file,
    uses `examples_index._detect_compilers` to pick a compiler (prefer `toycc`
    when both accept, error if neither), then `_compile_and_show_casm`.
  - *Examples browser*: `_load_example`'s C branch now routes through
    `_compile_and_show_casm` with the tree node's chosen compiler (previously it
    loaded the asm directly).
- **OK-load path** — `CAsmDialog._on_ok` calls the debugger's existing
  `_load_asm_text(self._asm_text, source_path)` (assemble + `load_program`,
  step 0) and `accept()`s on success; on failure the shared error dialog shows
  and the window stays open.
- **Comments: KEPT, not stripped** (judgment call). The `# @c:N` markers stay in
  the loaded asm — the assembler ignores comments so the mem image is identical
  (pinned by `test_c_line_annotation.py`), and keeping them means the asm panel /
  Edit-assembly window still show each line's C origin. Stripping would only add
  code for no benefit.
- **Line-number gutter in the asm panel: YES** — both panels get the gutter (the
  prompt listed it as optional/nice; it's a two-line helper and reads better, so
  kept it).

Tests (`tests/test_casm_window.py`): `parse_c_line_map` bidirectional
correctness on a known program (a specific C line → its expected asm rows, the
inverse agrees, header/data unmapped) and the empty-without-markers case; the
window built headlessly (recording pre-existing windows, picking the new
ToyDebugger) asserting both panels populated, that selecting a C line highlights
exactly the mapped asm rows (and an unmapped C line highlights none), that an asm
click resolves back to its C line, and that OK loads a non-empty program at
step 0. `tests/test_examples_browser.py` updated: the C-example load now drives
through the captured C|asm window's OK path instead of loading directly.
