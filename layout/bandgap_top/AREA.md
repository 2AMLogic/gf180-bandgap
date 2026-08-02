# `bandgap_top` area budget — drawn GDS vs. `floorplan.md` §8

Closes `layout/floorplan.md` §11.1 ("GDS-verified area re-check", owner:
*the future layout-implementation issue*). Regenerate every number here with:

```bash
uv run --with klayout python3 layout/bandgap_top/area_report.py
```

## Headline

| Quantity | Value |
|---|---|
| Drawn GDS bounding box (incl. guard ring) | **154.70 × 312.47 µm** |
| Drawn GDS area | **48,339.11 µm² (0.04834 mm²)** |
| Ratified target (`README.md` "Target specification", issue #1/#35) | 50,000 µm² (0.05 mm²) |
| Margin | **PASS — 1,660.89 µm² (3.3 %) of headroom** |
| Device body area, current netlist | 19,994.36 µm² |
| Realised overhead multiplier | **2.42× body area** |
| `floorplan.md` §8 body-area estimate | 10,425.45 µm² |
| Current netlist vs. that estimate | **1.92×** |

Verdict: **inside the ratified budget, but only just.** Three findings below
are flagged rather than smoothed over, per CLAUDE.md's no-spec-relaxation
rule.

## Finding 1 — `floorplan.md` §8's body-area estimate is 1.92× stale

§8's table was tallied against the schematic as it stood when #16 was
written. The design has changed three times since, all in the direction of
more area:

- **#56** replaced the 5T error amplifier with a telescopic-cascode,
  dominant-pole-compensated OTA. §8 budgeted the amp at 1,160 µm² (M1/M2
  800 + M3/M4 320 + M5 40). The amp now draws **8,140 µm²** — the input
  pair alone is 2 × (200 µm × 4 µm) = 1,600 µm² against §8's 2 × (100 µm ×
  4 µm), the PMOS cascodes MC3/MC4 add 2 × 640 µm², and the compensation MIM
  `CC` (60 µm × 60 µm = 3,600 µm²) is a device §8's table does not contain
  at all.
- **#60** budgeted and resized `bandgap_core`'s mirror/cascode devices for
  mismatch. §8 budgeted M1–M4/MC1–MC4 at 8 × (20 µm × 2 µm) = 320 µm²;
  they now draw 6 × (60 µm × 6 µm) + 2 × (7.5 µm × 6 µm) = 2,250 µm².
- **#69** co-scaled `core.R1`/`R2`/the trim unit by `k=2` to close the
  `Iq < 50 uA` spec row. §8 (and this file, before #69) carried `R1` at
  230.180 µm × 2 µm = 460.36 µm²; it now draws 460.701871 µm × 2 µm =
  **921.40 µm²**, and `R2` similarly doubles from 36.34 µm² to 72.68 µm².
  `core`'s group total moves from 2,959.36 µm² to **3,457.09 µm²**.

This is a **stale estimate, not an overrun**: the drawn area still fits.
`area_report.py` deliberately recomputes the body-area tally from the
*current* `design/netlist/bandgap_top.spice` rather than transcribing §8's
numbers, so it cannot go stale the same way again — §8's figure is carried
only as a single named constant to compare against.

## Finding 2 — 3.3 % headroom is thin, and single-metal routing is why

The realised overhead multiplier is **2.42×**, comfortably better than the
4× §8 called "generous". The problem is the base it multiplies: at
19,994 µm² of body area, even a 2.42× multiplier lands at 96.7 % of the
ceiling.

Where the overhead goes: `klt`'s gf180mcu decks — both the DRC deck and the
extraction deck — model exactly **one** metal level (`Metal1`, 34/0), with no
`Metal2`..`Metal5` and no vias. A block routed on layers the extraction deck
cannot see extracts as disconnected nets and cannot LVS, so this layout is
routed entirely on Metal1 with Poly2 as the crossunder layer (see
`generate.py`'s "Routing style" note). That costs area two ways:

1. a 25-track Poly2 corridor down the left edge of the block — 16.0 µm of
   width consumed before any device is placed;
2. one Metal1 rail per net per row, stacked above each row on a 0.64 µm
   pitch, so every row grows vertically by the number of distinct nets it
   touches instead of routing over the devices on an upper metal.

With a real gf180mcu metal stack, most of that disappears — supplies and
long haul nets go up to Metal2/Metal3 directly over the device field. The
tool gap is filed generically against klayout-tools (see `layout/README.md`
§ "Friction filed"); the area consequence is recorded here so nobody reads
2.42× as an intrinsic property of the block.

**Two named risks to the 3.3 % margin:**

- `startup.RPU`, the 2 MΩ start-up bleeder, is **8,000 µm² of body area —
  40 % of the block's entire device area and ~16 % of the ratified target on
  its own.** §8 already flagged it as the single largest line item; that is
  still true and the drawn serpentine (57 legs) does nothing to shrink it.
  Any future reduction of the ceiling pressure should start here.
- Any further device growth is now roughly 1:1 against the remaining
  1,661 µm². A 2× on `core.R1` again (or an equivalent-sized new line item)
  would bust the budget unless it is co-folded the way Finding 3 describes.

## Finding 3 — #69's `R1`/`R2` length doubling regressed the budget; fixed here by co-scaling the fold count (#70)

#69 doubled `core.R1`/`R2`'s drawn length (`k=2`, closing the `Iq < 50 uA`
spec row) but never regenerated this layout — `layout/bandgap_top/` had no
changes in that PR's diff at all. Regenerating against the resized
resistors (required incidentally by #65's unrelated `nf` fix) surfaced a
real, reproducible regression: the drawn block grew to **50,897.23 µm²**,
897.23 µm² (1.8 %) **over** the ratified 50,000 µm² budget —
`area_report.py` exited 3.

Root cause: `RSTRIP`'s `ResItem`s fold each resistor into a fixed number of
serpentine legs (`segments`) independent of drawn length. Doubling `R1`'s
length at a fixed `segments=14` roughly doubled its **leg height**
(14.31 µm → 30.77 µm) without touching its width — and because the whole
block's rows stack vertically at the full block width, that one row's
height increase multiplied by the block's ~154.7 µm width, turning a
461 µm² body-area increase in `R1` into a ~2,547 µm² drawn-area increase.

The fix (this issue, #70) is a pure layout re-fold, **not** a resistor
value change: `core.R1`'s `segments` co-scales from 14 → 28 and `core.R2`'s
from 2 → 4, in step with #69's `k=2` length growth. Folding into twice as
many, half-as-long legs restores each resistor's leg height to
approximately its pre-#69 value while growing its *width* instead — headroom
that exists because `RSTRIP` was never the block's width-limiting row (the
`startup.XRPU` row is, at 147.7 µm). Net effect: the drawn block returns to
**48,339.11 µm²**, 10.83 µm² off #69's own pre-regression starting point
(48,349.94 µm²) and within measurement/rounding noise of it.

No `design/netlist/*.spice` value changed, so no spec row is affected and no
PVT re-verification was required — `core.R1`/`R2`'s resistance (and
therefore `Iq`) is exactly what #69 set it to. `matching_report.py`'s tier-2
check (single `ppolyf_u` unit width across `R1`/`R2`/the trim ladder) is
insensitive to fold count and continues to pass; DRC and LVS were re-run
against the regenerated GDS and are clean/matching (see `layout/README.md`
"Expected results").

## Body area by group (current netlist)

| Group | Body area (µm²) |
|---|---|
| amp | 8,140.00 |
| startup | 8,048.00 |
| core | 3,457.09 |
| trim ladder | 349.27 |
| **TOTAL** | **19,994.36** |

Largest single line items: `startup.RPU` 8,000; `amp.CC` (MIM) 3,600;
`core.R1` 921.40; `amp.M1`/`amp.M2` 800 each; `amp.MC3`/`amp.MC4` 640 each.
