# `bandgap_top` area budget — drawn GDS vs. `floorplan.md` §8

Closes `layout/floorplan.md` §11.1 ("GDS-verified area re-check", owner:
*the future layout-implementation issue*). Regenerate every number here with:

```bash
uv run --with klayout python3 layout/bandgap_top/area_report.py
```

## Headline

| Quantity | Value |
|---|---|
| Drawn GDS bounding box (incl. guard ring) | **239.20 × 337.85 µm** |
| Drawn GDS area | **80,813.72 µm² (0.08081 mm²)** |
| Ratified target (`README.md` "Target specification", issue #1/#35) | 50,000 µm² (0.05 mm²) |
| Margin | **FAIL — 30,813.72 µm² (61.6 %) OVER budget** |
| Device body area, current netlist | 25,327.78 µm² |
| Realised overhead multiplier | **3.19× body area** |
| `floorplan.md` §8 body-area estimate | 10,425.45 µm² |
| Current netlist vs. that estimate | **2.43×** |

Verdict: **over the ratified budget** — see Finding 5. Four findings below
are flagged rather than smoothed over, per CLAUDE.md's no-spec-relaxation
rule; the headline numbers above are current as of issue #156 (regenerated
2026-08-16), superseding the "inside the ratified budget, but only just"
verdict this file previously carried (48,938.26 µm², PASS at 2.1 % headroom,
last regenerated at `ba091ea`/#105 — stale since #96/#147/#151).

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

## Finding 2 — headroom is thin, and single-metal routing is why

The realised overhead multiplier is **2.45×**, comfortably better than the
4× §8 called "generous". The problem is the base it multiplies: at
19,994 µm² of body area, even a 2.45× multiplier lands at 97.9 % of the
ceiling.

Where the overhead goes: `klt`'s gf180mcu **extraction** deck used to model
exactly **one** metal level (`Metal1`, 34/0), with no `Metal2`..`Metal5` and
no vias. A block routed on layers the extraction deck could not see would
extract as disconnected nets and could not LVS, so this layout is routed
entirely on Metal1 with Poly2 as the crossunder layer (see `generate.py`'s
"Routing style" note). (The extraction deck has since gained the full
Metal1–Metal5/via stack, klayout-tools#220, and the separate **DRC** deck was
never Metal1-only in the first place — see `layout/README.md` § "The
gf180mcu DRC deck: coverage"; this layout's single-metal routing predates
both facts and has not been revisited for the block as a whole, per that
same section — the one exception is the compensation MIM cap's own via
stack, which does not move this area finding.) That costs area two ways:

1. a 25-track Poly2 corridor down the left edge of the block — 16.0 µm of
   width consumed before any device is placed;
2. one Metal1 rail per net per row, stacked above each row on a 0.64 µm
   pitch, so every row grows vertically by the number of distinct nets it
   touches instead of routing over the devices on an upper metal.

With a real gf180mcu metal stack, most of that disappears — supplies and
long haul nets go up to Metal2/Metal3 directly over the device field. The
tool gap is filed generically against klayout-tools (see `layout/README.md`
§ "Friction filed"); the area consequence is recorded here so nobody reads
2.45× as an intrinsic property of the block.

**Two named risks to the margin:**

- `startup.RPU`, the 2 MΩ start-up bleeder, is **8,000 µm² of body area —
  40 % of the block's entire device area and ~16 % of the ratified target on
  its own.** §8 already flagged it as the single largest line item; that is
  still true and the drawn serpentine (57 legs) does nothing to shrink it.
  Any future reduction of the ceiling pressure should start here.
- Any further device growth is now roughly 1:1 against the remaining
  1,062 µm². A 2× on `core.R1` again (or an equivalent-sized new line item)
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

## Finding 4 — #86's fold-link length fix grows `RSTRIP`'s row height ~13 %

`res_geometry()`'s leg-length formula budgeted a whole fold *pitch*
(`width_nm + POLY_SP`) of resistive length per serpentine link, but a link's
box overlaps both legs it joins by a full leg width, so it only contributes
`POLY_SP` of *new* drawn length. Every folded resistor was therefore drawn
`(n - 1) * width_nm` (net of a small `IMPLANT_ENC` pad-sliver credit) short
of its schematic `r_length` — see gf180-bandgap#86 for the full derivation
and its "Measured effect" table. Fixing the formula makes each leg *longer*
for the same schematic length (there is less length hidden in double-counted
fold links to draw from), which grows every folded resistor's leg height:

| Item | Leg height before (#86) | Leg height after | Growth |
|---|---|---|---|
| `core.R1` (n=28) | 14.235 µm | 16.150 µm | +13.5 % |
| `core.R2` (n=4) | 7.360 µm | 8.760 µm | +19.0 % |
| `startup.RPU` (n=57) | 67.915 µm | 69.873 µm | +2.9 % |

`RSTRIP` (the row holding `R1`/`R2`) absorbs `R1`'s +13.5 % leg-height
growth directly, since a row's height is its tallest item's; `startup.RPU`
sits in its own row and absorbs its own, much smaller, growth. Net effect on
the whole block: drawn GDS area grows from 48,339.11 µm² to
**48,938.26 µm²** (+1.2 %), and headroom against the ratified 50,000 µm²
target narrows from 3.3 % to **2.1 %** — still comfortably inside budget
(see "Headline" above), but Finding 2's margin risk is now a little closer.

No `design/netlist/*.spice` value changed here either — same as Finding 3,
this is a pure re-fold that corrects a *drawing* bug, not a resistor value
change. Unlike Finding 3, though, this one *does* change what `klt extract`
reports for `R1`/`R2`/`RPU`'s resistance: the drawn body was previously
short of the schematic's intent (a first-order error on the PTAT ratio
`(R1 + trim)/R2` feeding `vref`, per #86), so the extracted `R` now matches
the schematic-intended value far more closely than before — confirmed
directly against `klt extract`'s per-device `R` (`core.R1`: 80,622.5 Ω vs.
80,622.85 Ω intended; `core.R2`: 6,359.5 Ω vs. 6,359.85 Ω intended;
`startup.RPU`: 1,999,980.5 Ω vs. 2,000,000 Ω intended — all within the
formula's own one-dbu-per-fold rounding tolerance).

## Finding 5 — #96/#147/#151's accuracy/stability resizes broke the budget; this file's own committed GDS masked it (issue #156)

This file's "Headline" and Findings 1–4 above described the layout as
regenerated through `#86` (`ba091ea`, 2026-08-03) — 48,938.26 µm², PASS at
2.1 % headroom. **No layout code changed after that commit, but three
circuit-sizing issues did**: `#96` (TC/output-reference corner closure),
`#147` (combined untrimmed-accuracy verdict — input pair to 300 µm/6 µm),
and `#151` (M3/M4 mirror-load resize to 33 µm/26.4 µm for loop-stability
margin; see `design/bandgap_error_budget.md` §5c/§5d for the electrical
justification and measured PASS verdicts each closed). None of those issues
touched `layout/bandgap_top/`, so the committed GDS silently drifted out of
sync with the netlist it is supposed to represent — this file's own PASS
verdict went stale without anyone re-running `generate.py` to catch it.

`#156` regenerated `bandgap_top.gds` from the current netlist (no
`generate.py`/`plan.py` change) and found the real verdict: **80,813.72 µm²
drawn, 61.6 % over the ratified 50,000 µm² target** (current "Headline"
table above). Root-caused directly against Finding 2's own overhead-
multiplier framing: the realised multiplier is **3.19×** — *better* than the
4× `floorplan.md` §8 called "generous," so single-metal routing overhead is
not the problem. Drawn device body area itself grew from 19,994.36 µm² to
**25,327.78 µm²** (+26.7 %, almost entirely `amp` — 8,140.00 → 11,242.40
µm² from `#147`'s input-pair resize and `#151`'s mirror-load resize; `core`
also grew 3,457.09 → 5,688.11 µm² from `#96`'s `core.R1` re-null and
`#147`'s `core.M1`–`core.M4`/`MC1`–`MC4` resize to 85 µm/8.5 µm) — a real
device-area increase required to close previously-failing electrical
verdicts (§5c/§5d), not a layout regression to fix.

Per CLAUDE.md's no-silent-relaxation rule, this is escalated rather than
absorbed: `spec/decision-records/0005-area-target-overrun.md` proposes an
interim revised Area target (`< 0.085 mm²`), filed `Status: proposed`
pending operator ratification — `README.md`'s ratified Area row and this
tool's `RATIFIED_TARGET_UM2` constant are unchanged until that ratification
lands, so `area_report.py` keeps reporting `FAIL` honestly until then. A
genuine fix — multi-level-metal routing, extraction-viable since
klayout-tools#220, replacing the current Metal1/Poly2-only corridor-and-rail
scheme — is named in that record and filed as
[#160](https://github.com/2AMLogic/gf180-bandgap/issues/160), not attempted
here.

(Separately, and unrelated to this finding: regenerating the GDS surfaced a
`klt`-version drift affecting DRC/LVS — see
[#159](https://github.com/2AMLogic/gf180-bandgap/issues/159) and
`layout/README.md`'s "Table currency note.")

## Body area by group (current netlist)

| Group | Body area (µm²) |
|---|---|
| amp | 11,242.40 |
| startup | 8,048.00 |
| core | 5,688.11 |
| trim ladder | 349.27 |
| **TOTAL** | **25,327.78** |

Largest single line items (current netlist, issue #156): `startup.RPU`
8,000; `amp.CC` (MIM) 3,600; `amp.M1`/`amp.M2` (input pair, `#147`) 1,800
each; `core.R1` 886.80; `amp.M3`/`amp.M4` (mirror load, `#151`) 871.20 each;
`core.M1`/`core.MC1`/`core.M2` (mirror/cascode, `#147`) 722.50 each.
