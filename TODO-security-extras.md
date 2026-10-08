# TODO — security-extras (for the other agent)

This file is the hand-off for the **pytoy** (and later **ktoy**) *code* changes
that back the new "security basics with the Toy CPU" teaching material. The
examples, docs and slides are being written by another agent in parallel — do
**not** touch:

- `examples/c/04-io/pin_check*.toyc`, `examples/asm/04-io/pin_check*.toys`
- `doc/design/pin-security.md`, `doc/chapters/09-io.typ` (I/O chapter)
- `_private/slides/special/pin/**`

Everything under `pytoy/` and `tests/` is yours. When the three features below
are done, run the tests, then pick up doc/slide polish only if the other agent
has already landed its files (coordinate via git status; if its files aren't
there yet, leave docs/slides alone).

The motivation for all of this: a 4-digit PIN example (`1337`) that, when
correct, reveals "the answer" (`42`, Hitchhiker's Guide). The slides walk
through how an attacker beats it — brute force, reading the bytecode, side
channels, and fault injection — and the three features here make those attacks
*demonstrable live in the simulator*.

---

## Feature 1 — right-click **edit ACC and PC** (fault-injection demo)

**Why.** The fault-injection slide shows: if the attacker can force `ACC = 0` at
the right moment, every `x != y` check (compiled as `x - y` then `ifzero`)
passes, because the comparison sees `0` instead of the real difference. To demo
this live, the user must be able to right-click the accumulator and set it to 0
mid-run. Same for PC (jump the program past the check).

**Current state.** Memory cells are already right-click editable via
`ToyDebugger._edit_cell(addr)` (`pytoy/simulator.py` ~line 1925), driven from
`_mem_clicked` (~1893). But **ACC and PC are not editable** — they are rendered
as plain text lines at the top of `_refresh_memory` (~line 2126):

```
    acc_text = f"  ACC={self.acc}=b{self.acc:08b}"
    ...
    lines.append(_esc(f"  PC={self.pc}"))
```

**What to build.**

1. Make the ACC line and the PC line **right-click editable**, reusing the
   existing `ValueDialog` (the same dialog `_edit_cell` uses). Add two methods
   next to `_edit_cell`, e.g. `_edit_acc()` and `_edit_pc()`:
   - `_edit_acc()`: open `ValueDialog` (default_fmt decimal), write the parsed
     byte into `self.acc`, mask mod 256, set `self.acc_written = True` so it
     highlights, snapshot via `self._push_history()` first so it is undoable
     with Back, set `self._has_live_edits = True`, then `self.refresh()`.
   - `_edit_pc()`: same, but write `self.pc` (mask mod 256). **PC edit must
     update the highlight**: `_refresh_memory` already derives `pc_bytes` and
     the `>>` marker from `self.pc` and re-decodes the instruction at `self.pc`
     each refresh, so once `self.pc` changes and you call `self.refresh()`, the
     yellow `HL_PC` bytes, the `>>` marker, and the `OPn=`/`EXPLAIN:` lines all
     follow automatically. **Verify** this: set PC to an address mid-program and
     confirm the yellow highlight + `>>` jump to the new location and the
     EXPLAIN line shows the instruction now under PC. If any of those lag, fix
     them (they are all computed in `_refresh_memory`, so they shouldn't).

2. Wire the clicks. The memory panel uses `_mem_line_addrs` (line-index → addr)
   for `_mem_clicked`. The ACC/PC lines are not memory addresses, so give them
   their own handling. Simplest: track the line indices of the ACC and PC lines
   (like `_mem_line_addrs` does for cells) and in the click handler, if the
   clicked line is the ACC line → `_edit_acc()`, if PC line → `_edit_pc()`.
   Right-click (`Qt.RightButton`) to match the memory-cell convention.

3. Add `acc`/`pc` to the undo snapshot if not already covered — they are already
   in `_SNAPSHOT_FIELDS` (~line 1550), so Back already restores them; just make
   sure the `_push_history()` call in the new editors runs **before** the write.

**Docs.** Add a short note to `doc/design/io-gui.md` (or wherever right-click
editing is documented) that ACC and PC are now editable the same way as memory
cells, and that editing PC re-homes the PC highlight. Keep it to a few lines.

**Tests.** Add a test (pure, no Qt event loop — call the methods directly on a
constructed debugger or factor the write logic into testable helpers) that:
- editing ACC writes the masked value and sets `acc_written`;
- editing PC moves the PC and that a subsequent `_refresh_memory` marks the new
  PC bytes (you can assert on the computed `pc_bytes`/marker, or factor that
  into a helper and test the helper).

---

## Feature 2 — optional **"Extra info"** panel (side-channel demo)

**Why.** The side-channel slides need numbers that leak with the input: how many
steps ran, how many jumps were taken, and simulated cache hits. These must be
**optional** (off by default, toggled from the View menu) and must add **no**
cost when hidden — just counters incremented in the step loop.

**Where.** Counters live on `ToyDebugger`; the widget renders below the IOPanel.
View menu wiring is in the `_build_view_menu`-style code (~line 1357, the
`"&View"` menu). The IOPanel class is at ~line 938.

**What to count.** Maintain these on the debugger, reset in the same place the
machine resets (`reset`/load, where `self.acc`/`self.pc`/`self.step_count` are
zeroed, ~line 1434):

- `steps`  — total steps. Already exists as `self.step_count`; just surface it.
- `steps1` — number of **1-byte** instructions executed (PC advanced by 1).
- `steps2` — number of **2-byte** instructions executed (PC advanced by 2).
  `steps1 + steps2 == steps` (STOP counts as a step; classify it as 1-byte).
- `jumps`  — number of times the PC was changed by a **taken** jump: every
  `goto` (opcode 24, unconditional) **plus** every `ifzero` (opcode 25) that
  **actually jumped** (i.e. `acc == 0` at that point so `next_pc == arg_addr`).
  An `ifzero` that fell through does **not** count.
- `cachehits` — `{8: x, 16: y, 32: z, 64: w}`, see Feature 3.

**How to count (in `step()`, ~line 1487).** You already decode the instruction
(`instr, arg_addr, _ = decode(...)`) before executing. Classify there:
- two-byte iff `core.has_operand(instr)` (bit 4 set) → `steps2 += 1` else
  `steps1 += 1`.
- For jumps, you know the pre-execution `self.pc`/`self.acc` and the
  post-execution `self.pc`. A taken jump = `instr == 24` OR
  (`instr == 25` and the pre-exec `acc == 0`). Increment `jumps` accordingly.
  (Equivalently: `goto` always; `ifzero` only when it took the branch.)

Put the counter updates in `step()` and make them part of the undo snapshot
(`_SNAPSHOT_FIELDS`) so Back rewinds them too. **Important:** cache state is a
mutable object — snapshot a *copy* (like `mem`/`touched` are copied in
`History`), not a reference, or Back won't restore it.

**The widget.** A small read-only widget styled like the IOPanel, shown directly
below it, listing:

```
steps=…   steps1=…   steps2=…   jumps=…
cachehits = {8: …, 16: …, 32: …, 64: …}
```

- Add a **checkable** `QAction` "Extra info" to the View menu (off by default),
  next to the existing panel-visibility toggles (~line 1363). Toggling it
  shows/hides the widget. Follow the exact pattern of the existing
  `'set ready' input` toggle (~line 1377) — same idiom, so it stays consistent.
- The widget refreshes from the debugger's counters inside the existing
  `refresh()` path (where `_refresh_memory`/`_refresh_source` are called, ~line
  2019). Only refresh it when visible.

**No-cost-when-hidden:** the counters update every step regardless (cheap ints);
only the *widget render* is gated on visibility. That matches the user's ask
("kannst im Hintergrund mitschleppen, kein Mehraufwand").

**Tests.** Pure tests on the counters: run a known program (e.g. the multiply
loop, or pin_check) N steps and assert `steps1 + steps2 == steps`, that `jumps`
matches the taken branches, and that Back rewinds all counters.

---

## Feature 3 — a **Cache simulator** class (timing side-channel demo)

**Why.** Real caches make execution time depend on the *access pattern*, which
depends on the *data* — a timing side channel. Simulate it so different PINs can
produce different hit counts, which the slides use to motivate "constant-time"
code.

**What to build.** A small, self-contained class (put it in its own module,
e.g. `pytoy/cache.py`, so it is unit-testable without Qt), that models a
**direct-mapped cache keyed by `address mod size`**. The user only wants hit
*counting*, not real data — so store nothing but presence:

```python
class Cache:
    """Direct-mapped cache over 8-bit addresses, keyed by (addr % size).
    Counts hits only — it models timing, not data."""
    def __init__(self, size):
        self.size = size
        self.lines = {}     # slot -> the address currently resident
        self.hits = 0
    def access(self, addr):
        slot = addr % self.size
        if self.lines.get(slot) == addr:
            self.hits += 1          # same address already resident -> hit
        else:
            self.lines[slot] = addr # miss: bring it in (evict whatever was there)
    def copy(self):   # for undo snapshots
        ...
```

Instantiate four of them — `size in (8, 16, 32, 64)` — on the debugger, e.g.
`self.caches = {n: Cache(n) for n in (8, 16, 32, 64)}`. Reset them on load/reset.
`cachehits` in Feature 2 is `{n: c.hits for n, c in self.caches.items()}`.

**What accesses to feed the caches, and in what order** (this matters — the user
was specific). On each executed instruction, the memory addresses *touched* are:

1. the **opcode byte** at `PC`,
2. the **operand byte** at `PC+1` — only for two-byte instructions
   (`core.has_operand(instr)`),
3. the **data address** `arg_addr` — only for instructions that read/write a
   data cell (`load/store/add/sub/and/or/xor`, i.e. those with an operand that
   dereference it; `goto`/`ifzero` have an operand byte but do **not** touch
   `arg_addr` as *data* — they use it as the jump target, not a RAM read. Treat
   goto/ifzero as touching only PC and PC+1, **not** arg_addr).

**Order / priority.** Feed them in execution order: **PC, then PC+1, then the
data address.** The user noted that when the data address collides with PC/PC+1
in a cache slot, *data has priority* — because it is accessed last, it stays
resident. Feeding in the order (PC, PC+1, arg_addr) and having `access()`
overwrite the slot on a miss gives exactly that: the data access, coming last,
wins the slot. Example from the user: first instruction `LOAD 64` at PC=0 →
addresses 0, 1, 64; for size 8/16/32/64, addrs 0 and 64 are congruent, so after
feeding 0 then 64 (data last) the slot holds 64. Good — just feed in order.

Do the feeding in `step()`, after you've decoded and know `arg_addr`, using the
same `instr`/`arg_addr` already in scope. Only count a data access for the
opcodes that actually dereference the address (the `'av'`/`'a'`-with-read set:
`load/add/sub/and/or/xor` read it, `store` writes it — all touch the data cell;
`goto`/`ifzero` do not). Use `core._INSTR` or an explicit set to decide.

**Snapshot for undo.** Add the caches to `_SNAPSHOT_FIELDS` and snapshot
**copies** (via `Cache.copy()`), same as `mem`/`touched`.

**Tests** (`tests/test_cache.py`, pure, no Qt):
- `Cache(8)`: access 0 (miss), 8 (miss, same slot evicts 0), 8 again (hit), 0
  (miss again). Assert hit count.
- Congruence: for `Cache(64)`, addresses 0 and 64 share a slot; 0, 64 → 1
  resident, 64 again → hit.
- Integration-ish (can construct a debugger or a thin driver): run `LOAD 64`
  as the first instruction and assert, per the user's example, that after it the
  size-8/16/32/64 caches hold 64 in the colliding slot (feed order PC=0, PC+1=1,
  data=64; data wins).
- Determinism: same program + same input → same `cachehits`; and show (in a
  test or at least a comment) that two *different* PINs through the naive
  digit-by-digit `pin_check` can yield *different* hit counts — that is the
  leak the slides talk about.

---

## Order of work & done criteria

1. Feature 1 (ACC/PC edit) — smallest, unblocks the fault-injection demo.
2. Feature 3 (Cache class) — pure, testable in isolation; no GUI risk.
3. Feature 2 (Extra-info panel) — wires 3's output + counters into the View menu.

**Done =** all three implemented, `pytoy` imports clean, the GUI launches and
does not crash with the Extra-info panel toggled on/off, and the new pure tests
pass. Run the **targeted** tests only (per house rule: short timeouts, no full
slow suites):

```
.venv/bin/python -m pytest tests/test_cache.py tests/test_extra_info.py \
    tests/test_acc_pc_edit.py -q
```

(create those test files). Do **not** run the whole suite unprompted — if you
think a broader run is needed, ask Manfred first.

**GUI smoke (do not skip):** the house pipeline rule is that the GUI must not
crash before Manfred tests. Launch the simulator on `pin_check` once, toggle
"Extra info" on and off, right-click ACC and set it to 0, right-click PC and set
it somewhere, step, and confirm no crash and the PC highlight follows. Then hand
back to Manfred for his manual sign-off on JVM/desktop (he gives the final OK).

When the other agent's example/doc/slide files are present (check `git status`),
you may also help polish `doc/chapters/09-io.typ` cross-refs to these features —
but only then, to avoid edit conflicts.
