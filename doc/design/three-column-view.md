# Three-column adaptive view + transitive highlighting

Big restructure of the simulator UI, decided with Manfred. Build pytoy-first,
then port to ktoy. Supersedes the earlier "C|asm window" (part 3) design — the
window becomes a full adaptive column layout.

## The vision

Adaptive 1/2/3-column layout, driven by what was loaded:
- **bytecode (.toyo)** → 1 column: bytecode/memory only.
- **assembly (.toys)** → 2 columns: asm + bytecode.
- **C (.toyc)** → 3 columns: C (or mini-C) + asm + bytecode.

Transitive highlighting across all present levels (C ↔ asm ↔ bytecode):
- **Click** a line in any column → the linked lines in the other columns light up
  (one C line → several asm lines → their bytecode cells).
- **Change propagation**: a runtime STORE that overwrites a byte highlights the
  byte (red, as today) AND transitively the asm line and the C line it came from.
- **Clicking out / deselect clears everything** — today there's leftover marking;
  fix it so nothing stays highlighted when the selection is dropped.

C import:
- Importing C asks: **full C (toycc)** or **mini C (minicc — no stack, closer to
  the asm)**. A **switch** button in the view toggles compiler (= recompile).
  If the chosen compiler can't handle it (minicc + recursion, or too long / >240
  bytes), show an error dialog and stay on the current one.
- Right-click to edit works on the C column AND the asm column; saving recompiles
  / re-assembles fresh (transitively updating the columns below).

Errors everywhere: bad input files, C that won't compile, asm that won't
assemble, bytecode too long — all surface a clear dialog, never a silent/crash.
C → asm → byte can be validated at compile time (does the result fit in 256?).

## The mapping infrastructure (already partly built)

- **C ↔ asm**: the compiler's `# @c:N` annotation (parse to c_line↔asm_line map).
  NOTE: ktoy's F1 port currently MISSES the markers on function-call setup/
  teardown asm — fix before relying on it (pytoy is correct). Port pytoy's test
  `test_toycc_recursive_save_restore_lines_point_at_call`.
- **asm ↔ bytecode**: the listing's `addr_to_line` / `line_to_addr` (exists).
- Transitive = compose the two maps: C line → asm lines → byte addresses.

## minicc

Ported to Kotlin for ktoy (pytoy already has it) so the full-C/mini-C choice +
switch is real. minicc = minimal, no stack, no recursion — its asm maps more
directly to the C, which is the didactic point.

## Build order (pipeline)

pytoy first, each part tested + fresh-reviewed, reviewer must agree with writer:
1. 3-column adaptive layout + transitive click highlight + deselect-clears.
2. Change-propagation (STORE → red up through asm → C).
3. C-import compiler choice + switch + error dialogs; right-click edit on C & asm.
Then port the whole thing to ktoy (incl. the ktoy F1 call-annotation fix and the
Kotlin minicc port, which can start in parallel since they don't touch the UI).

Reviewer agents verify each part against this doc and against pytoy; iterate until
reviewer and writer agree and tests cover it.

## Status (pytoy)

- [x] **Part 1 — adaptive layout + transitive click highlight + deselect-clears.**
  The debugger's two-panel splitter is now a three-widget `QSplitter`:
  `c_box` | `source_box` | `mem_box`. Visibility is driven by `has_c_source`
  (C column) and `has_source` (asm column); memory is always shown. A `.toyo`
  shows memory only, a `.toys` shows asm+memory, a `.toyc` shows all three.
  After a C load the debugger keeps the C source and the C↔asm maps (previously
  discarded when the C|asm window closed): new state `self._c_text`,
  `self._c_to_asm`, `self._asm_to_c`, `self.has_c_source`, `self.selected_c_line`,
  set via `_set_c_source` on the C|asm window's OK and cleared via
  `_clear_c_source` on every asm/bytecode load. The C column has its own
  line-number gutter, like the asm panel.

  Transitive highlight: pure helpers `c_line_to_asm_rows`, `asm_rows_to_addrs`,
  `addr_to_c_line`, `transitive_selection` compose the two maps. A click in any
  column sets `selected_c_line` and/or `selected_addr` through `_select(...)`;
  `refresh()` renders all three panels from that one shared selection
  (`_selection_sets`), so one C line lights its asm rows and their bytes, an asm
  click resolves up to its C line (and back down to the whole statement), and a
  memory click resolves up to C.

  Deselect: `_select()` with both anchors None (an unmapped/blank click) clears
  `selected_c_line`, `selected_addr` and `mem_selected_addr`, so nothing stays
  highlighted — the leftover-marking bug is fixed.

- [x] **Part 2 — change propagation (STORE → red up).** `_change_sets()` takes
  `changed_cell` (set on a STORE, cleared next step / while stopped) and walks
  `addr_to_line` → `asm_to_c` to the owning asm row and C line; `_refresh_source`
  and `_refresh_c` render those red (HL_CODE). The existing per-line
  "memory differs from source" red (HL_CODE for code, HL_DATA for data) and the
  blue byte highlight are unchanged.

- [x] **Part 3 — compiler choice + switch button + right-click edit on the C
  column.** The existing CAsmDialog file-preview flow and the compiler-detection
  on `.toyc` load are retained. Added:
  - **C-column right-click edit.** `c_view` gets a CustomContextMenu handler
    `_edit_c_clicked` (mirrors `_edit_asm_clicked`): with no C loaded it pops a
    "Nothing to edit" info box, else it confirms discard then opens `EditCDialog`
    (parallel to `EditAsmDialog`). Save recompiles with the active compiler
    (falling back to `_detect_compilers` if none pinned), re-assembles via
    `_load_asm_text`, and on success re-parses the `# @c:N` markers
    (`parse_c_line_map`) and re-attaches via `_set_c_source`. A compile error
    (`show_error_dialog`) or assemble error keeps the dialog open; the old
    program/C is untouched.
  - **Compiler switch button** in the C-box header (`btn_switch_compiler`,
    label = the OTHER compiler, "Switch to mini C" / "Switch to full C"). Shown
    only while `has_c_source` (wired into `_set_c_source` / `_clear_c_source`).
    `_switch_compiler` recompiles `_c_text` with the target and verifies it both
    compiles (catches minicc's recursion `MiniError`) AND assembles within 240
    bytes (catches minicc overflow, surfaced by `_load_asm_text`). Either failure
    shows `show_error_dialog` and leaves the simulator exactly on the current
    compiler/program — no half-load. Success reloads at step 0, pins the new
    compiler, re-parses the maps, re-attaches the C column, and flips the label.

  Tests: `tests/test_part3.py` (C-edit valid/invalid/no-C, switch success both
  directions, switch rollback on recursion and on overflow) +
  `tests/test_probe_compiler_accept.py` (locks the fixture properties: sum3 both
  accept, fibonacci_rec minicc-rejects, bigint_add minicc-overflows).

Tests: `tests/test_three_column.py` (pure transitive mapping + headless
debugger: adaptive visibility for .toyo/.toys/.toyc, C/asm/memory click
resolution, deselect-clears, STORE change propagation). The earlier
`tests/test_casm_window.py` C|asm window tests still pass unchanged.

## GUI follow-up fixes (Manfred, round 2)

A batch of UI fixes requested after using the three-column view:

- **A. Format picker in the I/O panel.** The IOPanel now has its own format
  combo (decimal/binary/hex/ascii = `iofmt.FORMATS`, 7segment disabled). It and
  the View-menu "I/O format" radio group drive the same format and stay in sync:
  both route through `ToyDebugger._set_io_format`, which checks the matching
  menu action and calls `io_widget.set_output_format`; `set_output_format` syncs
  the combo back via `sync_combo` (guarded by `_syncing_combo` so it can't loop).

- **B. Removed the 'set ready' input row.** The ready register (255) is set like
  any other cell — click it. Dropped `in_row_widget` + `in_edit` + `btn_set_in` +
  `IOPanel._set_input`, the View-menu `'set ready' input` toggle + its
  `set_input_row_visible`, and `ToyDebugger.set_input_byte` (now dead; only the
  removed row and its test called it).

- **B/C. Default I/O format = ascii.** `format._DEFAULTS["output"]` is now
  `ascii` (single source of truth; `io_config["output"]` is GUI-only). A program
  with no `# pytoy: output=` directive shows its I/O as characters; an explicit
  directive still wins. The two GUI fallbacks (`get("output", "ascii")`) match.

- **C. Edit-dialog note is format-aware.** `ValueDialog` shows a note that
  depends on the selected format and updates live: integer formats (decimal/hex/
  binary) note "Value 0–255 (wraps mod 256)."; ascii notes "Enter a single
  character." (the mod-256 wrap note is meaningless for a character).
  `_edit_cell` now passes a neutral "New value:" prompt and lets the dialog own
  the note.

- **D. Bottom bar order.** `Load Examples Reload` · (small spacing) · `Step Run`
  · `steps/sec` · `Undo Reset` · (stretch) · **Edit** pushed to the far right.

- **E. Selection fan direction.** A click in the **C column** fans DOWN to all of
  the statement's asm rows + their bytes (as before). A click in the **asm** or
  **memory** column now highlights ONLY that one row + its bytes and resolves UP
  to its C line, without fanning back out to the statement's sibling asm rows.
  `transitive_selection` gained a `from_c` flag; `_select` tracks the origin
  (`selected_from_c`, also snapshotted for undo); `_source_clicked`,
  `_mem_clicked` and `_edit_cell` pass `from_c=False`, `_c_clicked` keeps True.

- **F. PC highlight in the C column.** `_refresh_c` maps the current PC's asm row
  up to its C line (`addr_to_c_line`) and paints that C line yellow (HL_PC), so
  the C view shows roughly what's executing.

- **G. Scroll-to-selection (centered).** On every `refresh()`,
  `_scroll_to_selection` centers each column (`_center_on_block`) on the first
  line of the current selection: the C panel on the first selected C line, the
  asm panel on the first selected row, the memory panel on the first selected
  address' row. A no-op when nothing is selected, so the asm panel's own PC
  auto-scroll keeps running while stepping. (QTextEdit has no `centerCursor()`;
  we center by nudging the vertical scrollbar by the cursor's offset from mid.)

Tests: extended `tests/test_three_column.py` (no-sibling-fanout for asm/mem
clicks, PC highlights the C line, from-asm click scrolls the C panel) and
`tests/test_io_gui.py` (format combo ↔ menu sync, ascii default, format-aware
edit note). `tests/test_format.py` updated for the ascii default.
