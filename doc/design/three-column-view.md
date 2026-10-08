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

- [ ] **Part 3 — compiler choice + switch button + right-click edit on the C
  column.** Not done yet. The existing CAsmDialog file-preview flow and the
  compiler-detection on `.toyc` load are retained; the inline per-column switch
  button and C-column right-click-to-edit are the remaining work.

Tests: `tests/test_three_column.py` (pure transitive mapping + headless
debugger: adaptive visibility for .toyo/.toys/.toyc, C/asm/memory click
resolution, deselect-clears, STORE change propagation). The earlier
`tests/test_casm_window.py` C|asm window tests still pass unchanged.
