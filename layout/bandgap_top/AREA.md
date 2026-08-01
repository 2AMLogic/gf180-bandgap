# `bandgap_top` area budget — drawn GDS vs. `floorplan.md` §8

Closes `layout/floorplan.md` §11.1 ("GDS-verified area re-check", owner:
*the future layout-implementation issue*). Regenerate every number here with:

```bash
uv run --with klayout python3 layout/bandgap_top/area_report.py
```

## Headline

| Quantity | Value |
|---|---|
| Drawn GDS bounding box (incl. guard ring) | **154.70 × 312.54 µm** |
| Drawn GDS area | **48,349.94 µm² (0.04835 mm²)** |
| Ratified target (`README.md` "Target specification", issue #1/#35) | 50,000 µm² (0.05 mm²) |
| Margin | **PASS — 1,650 µm² (3.3 %) of headroom** |
| Device body area, current netlist | 19,300.45 µm² |
| Realised overhead multiplier | **2.51× body area** |
| `floorplan.md` §8 body-area estimate | 10,425.45 µm² |
| Current netlist vs. that estimate | **1.85×** |

Verdict: **inside the ratified budget, but only just.** Two findings below
are flagged rather than smoothed over, per CLAUDE.md's no-spec-relaxation
rule.

## Finding 1 — `floorplan.md` §8's body-area estimate is 1.85× stale

§8's table was tallied against the schematic as it stood when #16 was
written. The design has changed twice since, both times in the direction of
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

This is a **stale estimate, not an overrun**: the drawn area still fits.
`area_report.py` deliberately recomputes the body-area tally from the
*current* `design/netlist/bandgap_top.spice` rather than transcribing §8's
numbers, so it cannot go stale the same way again — §8's figure is carried
only as a single named constant to compare against.

## Finding 2 — 3.3 % headroom is thin, and single-metal routing is why

The realised overhead multiplier is **2.51×**, comfortably better than the
4× §8 called "generous". The problem is the base it multiplies: at 19,300 µm²
of body area, even a 2.51× multiplier lands at 96.7 % of the ceiling.

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
2.51× as an intrinsic property of the block.

**Two named risks to the 3.3 % margin:**

- `startup.RPU`, the 2 MΩ start-up bleeder, is **8,000 µm² of body area —
  42 % of the block's entire device area and ~16 % of the ratified target on
  its own.** §8 already flagged it as the single largest line item; that is
  still true and the drawn serpentine (57 legs) does nothing to shrink it.
  Any future reduction of the ceiling pressure should start here.
- Any further device growth is now roughly 1:1 against the remaining
  1,650 µm². A 2× on any one of the top-five line items above busts the
  budget.

## Body area by group (current netlist)

| Group | Body area (µm²) |
|---|---|
| amp | 8,140.00 |
| startup | 8,048.00 |
| core | 2,959.36 |
| trim ladder | 153.09 |
| **TOTAL** | **19,300.45** |

Largest single line items: `startup.RPU` 8,000; `amp.CC` (MIM) 3,600;
`amp.M1`/`amp.M2` 800 each; `amp.MC3`/`amp.MC4` 640 each; `core.R1` 460.36.
