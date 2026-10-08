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
   asm. Needs Part 1.
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
6. **asm edit mode** — right-click the asm (left) panel → a window opens to edit
   the assembly text → Save re-assembles it fresh and reloads. pytoy + ktoy.

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
