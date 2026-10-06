# Design: the I/O widget and the View menu

A working design note for the memory-mapped I/O widget in the simulator GUI and
the `View` menu that drives it. It records what Manfred asked for and the
decisions taken, so the behaviour can be checked against the intent.

The CPU core (`core.py`) is untouched by any of this — I/O is purely a view over
the top of memory (`io0`..`io14` = 240..254, `ready` = 255). See chapter 9,
_Memory-mapped I/O_, for the machine-level model.

## The I/O widget (`IOPanel` in `simulator.py`)

What the panel shows and how it behaves:

- **16 cells in one row.** `io0`..`io14` plus `ready` (255) as a 16th cell. One
  row normally; **two rows only in binary mode**, where each value is eight
  characters wide and sixteen would not fit on a line. The split is picked by
  `_relayout()` from the current format; everything else is a single row.
- **`ready` is shown like the others**, as the 16th cell, not on a separate line.
  It follows the chosen format — *except* ascii, where it stays **decimal**,
  because its value is a flag/count, not a character.
- **ascii non-printable** shows as a middle dot `·`, kept distinct from a real
  `.` (code 46). (The `.` was once floated as an input terminator for names, but
  the length is given via `ready` now, so no character is special.)
- **Polling marker.** While the current instruction is `load 255` (the program
  is busy-polling for input), the `ready` cell is highlighted red. Cleared as
  soon as the PC moves off the poll.
- **Click a cell to edit it.** Clicking any I/O cell opens the *same* edit dialog
  as the CPU & memory panel (routes through the debugger's `_edit_cell`). This
  was an explicit requirement: "if you click the I/O display it should be exactly
  the same as clicking Edit on that entry in the memory panel — it is 1:1 the
  same." No bespoke input path for the cells.
- **Edit default format** (`_edit_default_fmt(addr)`). The dialog opens in the
  format that matches the cell, so typing matches what you see:
  - `io0`..`io14` (240..254) → the format the I/O panel is *currently* showing
    (read live from the panel, so a mid-run `View → I/O format` change applies).
  - `ready` (255) → **always decimal**, by request — its value is a flag/count,
    never a character or a lit digit.
  - ordinary memory → decimal.
- **Optional "set ready" input row.** A line edit + Set button that writes
  `mem[255]`. Hidden by default; toggled from `View → 'set ready' input`. The
  panel used to always show it plus a format dropdown; Manfred found that "way
  too bloated — I really only wanted to see two rows." So the panel now shows
  only the cells, and the controls moved to the menu.

## The View menu

A single `View` menu in the window's menu bar, holding everything that used to be
inline controls plus new visibility and font toggles:

- **Panel visibility** (checkable, on by default): _Assembly panel_, _CPU &
  memory panel_, _I/O panel_, and _'set ready' input_ (off by default). Each just
  shows/hides its widget.
- **Font size** (exclusive group): _Normal_, _Large (1.5×)_, _Double (2×)_,
  _Triple (3×)_. Scales the mono font across both panels, the buttons, and the
  I/O cells together. Base size is 13 pt; `_apply_font_scale()` multiplies it and
  re-applies to every fonted widget.
- **I/O format** (exclusive group): decimal / binary / hex / ascii. (7segment is
  disabled for now — see below.) This replaces the old dropdown. The initial choice
  comes from the program's `# pytoy: output=…` directive. Picking a format also
  changes how a clicked cell's current value is shown for editing.

Requirement, in Manfred's words: "just a window menu with what's visible, and
font size normal / double etc." — hence the plain `View` menu rather than
in-widget controls or a toolbar.

## 7-segment: disabled, parked

7-segment is **off** for now. The first attempt used the wrong model — it mapped
the low nibble to a hex digit (`0`..`9`, `A`..`F`). The intended model is one bit
per segment: the byte *is* the segment pattern (7 segments a..g + bit 7 = the
dot, which you can toggle). Rather than ship the wrong one, `7segment` is removed
from the active `FORMATS`, so it never appears in the View menu or in a `# pytoy:
output=` directive. The `seven_segment()` helper (commented out in `format.py`)
and the `SevenSegDisplay` widget (no longer instantiated) are kept as a starting
point if it is redone later. The `numbers_7seg` example was dropped with it.

## Examples

`numbers.toys` writes `0`..`14` to `io0`..`io14`. Two siblings write the same
bytes but open in a different default format, so those display modes have a ready
demo:

- `numbers_hex` → hex (`0`..`9`, `a`..`e`)
- `numbers_ascii` → ascii (codes 0..14 are control chars, shown as `·`; the point
  is that the raw bytes are identical, only the view differs)

Only fifteen values (0..14) are written, not a full sixteen hex digits: `io0`..`io14`
is fifteen cells, and `ready` is left alone as its normal flag rather than
pressed into service as a sixteenth output cell.

`hello_world.toys` writes "Hello world!" (with the exclamation mark) into
`io0`..`io11`.

All four `numbers*` and `hello_world` are deterministic headless, so they are in
the snapshot table (`tests/snapshot/asm_snapshot.json`); the busy-poll demos
(`poll_demo`, `greet_name`, `sort`) are excluded because they spin without a GUI
to feed `ready`.

## Window title

The window title shows the loaded program's filename: `pytoy — greet_name.toys`,
or just `pytoy` when nothing is loaded. `_update_title()` reads the basename of
`_current_path` (the single source of truth for the loaded file) and runs on
startup, Load, and Reload.

## Related CLI change

The simulator's stop line was shortened from `Stopped after N steps with result
ACC=… (b…, 0x…)` to just **`Stopped after N steps.`** — the ACC value already
appears on the line directly below, so repeating it was redundant.
