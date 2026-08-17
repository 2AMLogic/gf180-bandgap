# Floorplan and matching plan (issue #16)

This document is the layout floorplan/matching-plan deliverable for the
Brokaw-cell bandgap: `design/bandgap_top.sch` = `design/bandgap_core.sch`
(matched PNP pair, PTAT/CTAT summing resistors, cascoded current-mode
mirror, trim ladder) + `design/bandgap_amp.sch` (5T OTA) +
`design/bandgap_startup.sch` (current-sensing kick circuit), per
[DR-0001](../spec/decision-records/0001-bandgap-topology-selection.md).

**This issue produces a document, not GDS.** Nothing here is drawn; it is
the plan the future layout-implementation work and `layout/` DRC/LVS
bring-up (#15, `layout/README.md`) draw against. Every quantitative claim
below cites the `sim/` record or `design/` document it derives from, per
CLAUDE.md ("Verification is the product" / "no claim without a
testbench") — where a number is a floorplan-stage *estimate* rather than a
simulated or measured quantity, it is labeled as such explicitly, not
presented as verified.

## 0. Matching priority order (what gets the best treatment, and why)

The layout-matching effort for this block is not evenly distributed. The
final-netlist circuit-level Monte Carlo (`sim/mc-untrimmed/records/
20260801-053436-6bbbdb7.md`, `mm_all`/`mm_res`/`mm_fetbjt` groups, #10's
final amp + #11's startup branch, no trim in the DUT — the untrimmed
pre-trim baseline) gives a direct, circuit-level sensitivity breakdown at
all three temperatures:

| T (°C) | resistor-only 3σ (mV) | MOS+BJT-only 3σ (mV) | ratio (MOS+BJT / resistor) |
|---|---|---|---|
| −40 | 3.203 | 30.505 | 9.5× |
| 27 | 4.180 | 30.127 | 7.2× |
| 125 | 5.618 | 30.603 | 5.4× |

**MOS+BJT mismatch dominates resistor mismatch by roughly an order of
magnitude at every temperature.** Within the MOS+BJT bucket, device-level
evidence (not a live circuit-level split — see that record's own
achievability note) indicates the split is itself lopsided: the amplifier
input pair's own random offset alone is ~25.06 mV (3σ, referred to
`vref`) against a ~2.06 mV (3σ) PNP-mismatch contribution —
`design/bandgap_error_budget.md` §2.7 — i.e. **MOS device mismatch (amp
input pair, mirror load, core current mirror/cascode), not intrinsic PNP
`VBE` mismatch, is the dominant term inside the dominant bucket.** The
intrinsic PNP pair mismatch was separately measured and confirmed
negligible: `sim/device-pnp-mismatch/records/20260731-040850-187a336.md`
puts the matched `pnp_05p00x05p00`/`pnp_10p00x10p00` pair's own `ΔVBE`
mismatch at 3σ = 0.128 mV at 10 µA/27 °C — two to three orders of
magnitude below the MOS figures (issue #25, absorbed into #16's
Dependencies, confirms this does not change the priority order below).

This gives a three-tier matching priority, in descending order of layout
effort spent per contributor:

1. **MOS devices — amp input pair (M1/M2), amp mirror load (M3/M4), core
   current mirror + cascode (M1–M4/MC1–MC4 in `bandgap_core`)** get the
   best matching treatment: common-centroid/interdigitated placement,
   dummy devices at every array edge, matched routing. This is ~90 % of
   the untrimmed spread's *random* budget (§2, §5 below).
2. **Resistor array (R1/R2 + trim ladder)** gets a layout-discipline
   matching treatment (common-centroid/interdigitated unit segments,
   dummies) even though its simulated contribution is an order of
   magnitude smaller — because the PDK cannot simulate resistor local
   mismatch at all (`mis_r = 0`, §3.1 below); the 3.2–5.6 mV figures in
   the table above are themselves an **assumed, literature-typical
   Pelgrom coefficient** (`design/bandgap_error_budget.md` §2.5,
   `Ar ≈ 1.5 %·µm`), not a PDK-verified number, so the *true* resistor
   contribution could be larger than what this MC record reports. Trim
   ladder placement (§3.2) additionally has its own hard constraint
   (adjacency to `tn0`) independent of this priority ranking.
3. **PNP array (Q1/Q2/Q3)** gets a standard common-centroid layout as
   good practice, but the operative concern here is **not** intrinsic
   device mismatch (shown negligible above) — it is base-resistance /
   substrate-tie **routing symmetry** (§4.2), a distinct layout-routing
   requirement the device-level MC records above do not capture at all
   (they measure device mismatch, not routing-induced asymmetry).

Nothing here is a pass/fail claim against the ratified accuracy target —
that comparison already exists and already fails untrimmed
(`sim/mc-untrimmed/records/20260801-053436-6bbbdb7.md`'s own
window-check table, all three temperatures FAIL against ±2 % 3σ) and
already passes trimmed (`sim/trim-coverage/records/
20260801-061650-083d402.md`, 81/81 PASS). This floorplan's job is to make
sure the *layout* does not add avoidable systematic error on top of that
already-measured, already-budgeted spread — not to re-litigate whether
the spread itself meets spec.

## 1. Floorplan overview

```
   +----------------------------------------------------------------+
   |                    guard ring (p+/psub taps, tied vss)         |
   |  +------------------------------------------------------------+ |
   |  |                                                            | |
   |  |   +------------------+   +----------------------------+   | |
   |  |   |  PNP array       |   |  MOS mirror/cascode group   |   | |
   |  |   |  Q1/Q2(x4)/Q3    |   |  M1-M4(core) + MC1-MC4(core)|   | |
   |  |   |  + dummies       |   |  interdigitated, dummies    |   | |
   |  |   |  (sec. 4)        |   |  (sec. 5)                   |   | |
   |  |   +------------------+   +----------------------------+   | |
   |  |                                                            | |
   |  |   +--------------------------------------------------+     | |
   |  |   |  Resistor / trim strip (sec. 3)                   |     | |
   |  |   |  [ R2 array ]--[ R1 array ]--tn0--[ 63-unit trim  |     | |
   |  |   |                                    ladder ]--vref |     | |
   |  |   |  RS0..RS5 straps adjacent to their tap groups      |     | |
   |  |   +--------------------------------------------------+     | |
   |  |                                                            | |
   |  |   +------------------+   +----------------------------+   | |
   |  |   |  Amp core (sec.6)|   |  Startup circuit (sec. 7)   |   | |
   |  |   |  M1/M2 in pair,  |   |  XMSENSE, XRPU (serpentine  |   | |
   |  |   |  M3/M4 load, M5  |   |  ~2 MOhm), XMKFB, XMKCASC   |   | |
   |  |   +------------------+   +----------------------------+   | |
   |  |                                                            | |
   |  +------------------------------------------------------------+ |
   |         dedicated analog vdd/vss ring, decoupling near fb/casc |
   +----------------------------------------------------------------+
```

The PNP array and the resistor/trim strip are placed adjacent to each
other because the output branch's electrical path runs
`Q3(e3) -> R1 -> tn0 -> trim ladder -> vref` and the PTAT branch runs
`Q2(e2) -> R2 -> sns2` — keeping these two blocks physically adjacent
keeps both of those routes short. The MOS mirror/cascode group sits next
to the PNP array because every mirror leg (`d1`…`d4`) feeds directly into
`sns1`/`sns2`/`vref`/`ibias`, i.e. into the PNP-array/resistor-strip
nodes; keeping that routing short and symmetric matters more than any
other floorplan choice here, per DR-0001's cascode discussion
(`design/bandgap_operating_point.md` §1). The startup circuit is
deliberately placed at the block's periphery, closest to `vdd`, since its
only steady-state interaction with the rest of the block is the two kick
taps into `fb`/`casc` (`design/bandgap_operating_point.md` §1a) — it does
not need to sit inside the matched-device core.

## 2. Why matching matters here (topology recap)

Per `design/bandgap_operating_point.md` §1, the amp forces `sns1 = sns2`.
Because M1/M2 (core mirror) share the same gate (`fb`) and the amp forces
the same drain-side condition, they carry equal current unconditionally —
so the reference's accuracy is not limited by mirror *current-ratio*
matching so much as by the amp's own *input-referred offset* and by
every other node that is not directly inside the amp's servo loop
(the output branch `M3/R1/Q3` and the bias branch `M4/Mn5`, which track
the servoed legs via the cascode rather than being individually forced —
`design/bandgap_operating_point.md` §1, §3's leg-matching measurement).
This is exactly why the amp input pair and the core mirror/cascode
devices are the dominant matching-priority tier in §0: they are either
the direct source of the offset (M1/M2 of the amp) or the devices whose
mismatch converts most directly into a leg-to-leg current error that the
cascode only partially (not fully) suppresses.

## 3. Resistor array (R1, R2, trim ladder)

### 3.1 Flavor, geometry, and the PDK's known blind spot

R1, R2, and every trim-ladder unit segment use **`ppolyf_u`**, per
`design/device-characterization.md` §2's explicit recommendation (record
`20260731-031750-8fb0ea6`): *"use `ppolyf_u` for R1 and R2 of the Brokaw
core, at W ≥ 2 µm, built from identical unit segments... use
`ppolyf_u_1k` only for non-ratio-critical bulk resistance (start-up
bleeder, trim ladder rungs)"* — the trim ladder itself does **not** use
`ppolyf_u_1k`: #14's sizing work (`design/bandgap_trim_network.md` §4)
deliberately chose `ppolyf_u` unit segments identical in flavor and width
to R1/R2, because the ladder sits in series with R1 in the same
ratio-critical output branch, not as an independent bulk resistance the
way the startup bleeder (`XRPU`, §7) is.

All three elements are drawn at **W = 2 µm** (not the characterized
W = 1 µm/5 µm points) — the actual drawn widths, per
`design/bandgap_operating_point.md` §2 and `design/bandgap_trim_network.md`
§4:

| Element | Drawn geometry | Squares | Role |
|---|---|---|---|
| R2 | W=2 µm, L=18 µm | 9 | PTAT-setting resistor |
| R1 | W=2 µm, L=230.180 µm | 115.09 | Output-branch CTAT/PTAT summing resistor (shrunk from 280 µm by #14 to land on `tn0`) |
| Trim unit segment (×63) | W=2 µm, L=1.215 µm each | 0.6075 each | Binary-weighted trim ladder, `tn0 → vref` |

**Matching technique**: R1 and R2 are the same flavor and same unit
width (both `ppolyf_u`, W = 2 µm) built from identical unit segments in a
**common-centroid or interdigitated array with dummy segments at both
ends**, per `design/device-characterization.md` §2's "Matching-plan
implications for #16" subsection (quoted directly — this is not a
paraphrase). The 7.1 % `Rsh` difference measured between W = 1 µm and
W = 5 µm drawn width (`device-characterization.md` §2) is a systematic
width-bias error that only cancels between R1 and R2 if every unit
segment — across R1, R2, *and* the trim ladder — shares the identical
drawn width (W = 2 µm here, uniformly).

**Known PDK blind spot, stated explicitly, not silently assumed away**:
gf180mcu's `ppolyf_u` model (`sm141064.ngspice`, `.subckt ppolyf_u`) hard-codes
`mis_r = 0` — local resistor mismatch is **not simulatable** in this PDK
release. `design/device-characterization.md` §2 ("Known gaps") and
`design/bandgap_error_budget.md` §2.5 both confirm this and flag the
resistor-mismatch line in the error budget as an **assumed, unverified**
literature-typical coefficient (`Ar ≈ 1.5 %·µm`), not a measured PDK
value. `sim/mc-untrimmed/records/20260801-053436-6bbbdb7.md`'s
`mm_res`-group resistor-mismatch numbers (§0's table) are produced by an
**out-of-band mismatch injection** (per-instance `r_length` jitter
against that same assumed coefficient — see that record's "Statistical
convention" section), not the PDK's own `mis_r` hook. **The matching
argument for R1/R2/trim ladder here is therefore a layout-discipline
argument — area, common-centroid placement, dummy segments, identical
unit geometry — not a simulation-verified one.** Do not read the §0
resistor-only 3σ figures as a PDK-native, independently-verified number;
they are a best-available proxy built on an assumed coefficient.

### 3.2 Trim ladder placement — adjacent to `tn0`

Per `design/bandgap_trim_network.md` §1 and §4 and `design/bandgap_core.sch`,
the trim ladder is **not** a separate block elsewhere on the die: R1 (now
230.180 µm, shrunk from the original 280 µm placeholder) lands on the
reserved tap node `tn0`, and `design/bandgap_trim.sch`'s subcircuit
(`XTRIM`, pins `bot`/`top`/`sub`) picks up `tn0 → vref`. The floorplan
places the ladder as a **physical continuation of the R1/R2 array's
output branch**:

```
  [ R2 unit array ]---[ R1 unit array ]---tn0---[ trim ladder: 63 identical
                                                    ppolyf_u unit segments,
                                                    tapped after unit 1/3/7/
                                                    15/31 into 6 groups ]---vref
                                                        |    |    |
                                                       RS0  RS1  ... RS5
                                                       (straps, adjacent to
                                                        their own tap group)
```

- The 63 unit segments are laid out with the **same common-centroid /
  interdigitation discipline as R1/R2** (identical W = 2 µm, identical
  per-segment contact geometry, identical orientation) — not a
  restatement of #14's schematic rationale, but a distinct floorplan
  requirement flowing from the same underlying physics
  `design/bandgap_trim_network.md` §4 documents: an earlier six-different-
  length version of this ladder measured an MSB weight of 58.6–68.9 LSBs
  (should be 64.0) across the PVT grid because the per-instance
  contact-resistance fraction (measured `R = 179.547·L_µm + 61.382 Ω` at
  W = 2 µm, tt/27 °C) differs by bit and skews differently over
  process/temperature. Unit segments fix this by construction at the
  schematic level, but **only if every physical instance is drawn
  identically** — a layout requirement, not a schematic one.
- The six `RS0`…`RS5` metal-option/probe-pad straps are placed adjacent
  to their respective tap groups (group boundaries after unit 1, 3, 7,
  15, 31 — `design/bandgap_trim.sch`'s header comment), not routed to a
  separate strap bank elsewhere, so each strap's own routing parasitic
  does not become a new source of code-dependent asymmetry across the
  6-bit range.
- `tn0` itself stays a short, low-impedance net: the tap point sits
  physically between R1's last unit segment and the trim ladder's first
  unit segment, with no other routing between them.

### 3.3 Resistor-array area, this element's own line item

63 unit segments at W = 2 µm, L = 1.215 µm each is a materially larger
aggregate contact-resistance-pair count than R1's single instance (63 vs.
1) — per this issue's Acceptance Criteria, the trim ladder gets its own
area line item rather than being folded into the R1/R2 array's figure;
see §8's tally.

## 4. PNP array (Q1, Q2, Q3)

### 4.1 Sizing and the ratio caveat

Per `design/bandgap_core.sch`: **Q1** (`pnp_05p00x05p00`, unit, diode-
connected, base=collector=`vss`) senses branch 1; **Q2**
(`pnp_10p00x10p00`, drawn 4× Q1) sits through R2 on branch 2; **Q3**
(`pnp_05p00x05p00`, same unit type as Q1) sits through R1/trim on the
output branch. `design/device-characterization.md` §1 (record
`20260731-030932-8fb0ea6`) measured the **effective** area ratio at
**3.634, not the drawn 4.00** — the PDK's saturation currents for the two
geometries are in ratio 3.671, and at equal emitter current the measured
effective ratio (via `exp(ΔVBE/VT)`) is 3.634.

**This is a device-physics finding, not a layout defect, and layout
cannot "fix" it.** If the array is built as **4 identical unit
`pnp_05p00x05p00` devices** for Q2 (rather than the monolithic
`pnp_10p00x10p00` device) to keep every element in the common-centroid
array the same physical unit type as Q1/Q3, the effective ΔVBE ratio
still measures 3.634, not 4 — the discrepancy is intrinsic saturation-
current physics (`design/device-characterization.md` §1's "What this
changes for the design" note), carried forward as a finding from #4/#8,
not something this floorplan resizes the unit count to correct.

**Array construction**: Q2 realized as **4 unit `pnp_05p00x05p00`
devices** (not the monolithic `pnp_10p00x10p00` cell) is the layout
choice recommended here specifically so every element in the array —
Q1 (×1), Q3 (×1), and Q2 (×4) — is the identical physical unit,
arranged in a common-centroid pattern with dummy units at the array
perimeter (standard analog common-centroid practice for a ratioed
device array; this repo has no `sim/` record measuring the
dummy-count/edge-effect tradeoff specifically, so this bullet is layout
convention, not a simulated claim). 6 core units total (1 + 1 + 4).

### 4.2 Base-resistance routing symmetry (the real matching concern here)

Per `design/device-characterization.md` §1: forward beta for these PNPs
is **≈1.6 typical at 27 °C and drops below 1 at `ss`/−40 °C** — base
current is comparable to, and at some corners exceeds, collector current.
Because every PNP in this design is diode-connected (base = collector =
`vss` = the shared p-substrate — `design/bandgap_operating_point.md` §1's
"Why the PNP collector is grounded" note, and confirmed directly in the
PDK model: `pnp_05p00x05p00`'s `.subckt` exposes `c b e` with `rb`, a
finite base-resistance model parameter), each device's emitter node sees
the **sum** of collector and base current sinking into the local
substrate tie (`design/bandgap_operating_point.md` §4.4).

**This is the operative PNP-array matching concern for this floorplan —
not intrinsic `VBE` mismatch, which §0 already showed is negligible
(3σ = 0.128 mV, record `20260731-040850-187a336`).** If Q1's substrate
tie is not routed symmetrically with Q2's (e.g. a different distance to
the nearest `vss`/guard-ring contact, or a different trace width), the
resulting difference in local substrate IR drop from each device's own
(strongly PVT-dependent, up to 3:1-swinging) base current shows up
directly as a `ΔVBE` error at the amp's `sns1`/`sns2` sensing nodes —
indistinguishable, electrically, from an amp offset of the same
magnitude (§2.4's superposition argument in
`design/bandgap_error_budget.md` applies equally to this error source,
even though this specific term is not what that section budgets).
Reflected in the floorplan's routing plan, not just geometric placement:

- Every PNP unit device's substrate/collector connection routes to the
  guard ring (§9) with matched trace length and width from Q1's units to
  Q2's units — symmetric placement in the common-centroid array (§4.1)
  is necessary but not sufficient; the substrate-tie routing itself must
  be matched too.
- Q3 (output branch) is not part of the amp's differentially-sensed pair
  (the amp sees `sns1`/`sns2`, not `e3`), so it does not need routing
  symmetry *with* Q1/Q2 for offset-cancellation purposes — but it is the
  same unit type as Q1, and is placed in the same common-centroid group
  for process-gradient consistency (systematic `VBE` tracking between Q1
  and Q3, both unit `pnp_05p00x05p00` devices).

## 5. Core current mirror + cascode (`M1–M4`, `MC1–MC4` in `bandgap_core`)

Per `design/bandgap_operating_point.md` §2's device table: "MC1–MC4
(core)... deliberately identical to M1–M4 so the whole stage is one
matching group for #16's common-centroid layout" — quoted directly, this
issue's own forward reference. All eight devices are `pfet_03v3`,
W = 20 µm, L = 2 µm, `m = 1`, and per §0/§2 this is one of the two
highest-priority matching groups in the whole block (the other being the
amp input pair, §6): mismatch here converts directly into the leg-to-leg
current error the cascode only partially suppresses
(`design/bandgap_operating_point.md` §3's leg-matching table — 130× 
reduction from the cascode, but not to zero).

- One 8-device common-centroid/interdigitated array, dummy devices at
  every array edge.
- `MCB` (W=4 µm, L=12 µm) and `MNB` (W=5 µm, L=2 µm) are differently
  sized (the cascode-bias generator, `design/bandgap_operating_point.md`
  §2's "MCB sizing derivation") and are **not** part of this matching
  group — they set a bias point shared by every leg equally, so their
  own device-to-device matching (they are single instances, not a pair)
  is not a differential-error source the way M1–M4/MC1–MC4 is.
- `Mn5` (W=20 µm, L=2 µm) mirrors `ibias` into the amp's tail
  (`bandgap_amp.tail_bias`) and is likewise a single instance, not part
  of this matching group.

## 6. Amplifier input pair and mirror load

**Note (issue #151): this section's device table was #16-era (#10's 5T OTA
topology) and had not been re-synced through #42's telescopic-cascode
rebuild or #147's resize — only the row this issue itself touches (M3/M4)
is corrected here; the rest of §8's floor carries the same staleness and is
flagged there rather than fully re-derived by this change (§11.1 owns the
eventual full resync against real geometry).** Current sizing, read directly
from `design/bandgap_amp.sch`:

| Device | Type | Current size | Matching group |
|---|---|---|---|
| M1, M2 (input pair) | `nfet_03v3` | W=300 µm, L=6 µm, `nf=12` (#147) | Group A — highest priority |
| M3, M4 (mirror load) | `pfet_03v3` | W=33 µm, L=26.4 µm, `nf=2` (**#151**, was W=20 µm/L=16 µm after #147) | Group B |
| MC1–MC4 (cascodes) | `nfet_03v3` / `pfet_03v3` | W=20 µm / W=40 µm, L=16 µm, `nf=2` (#42, unchanged by #151) | Group B (paired with M1/M2 or M3/M4 respectively) |
| M5 (tail) | `nfet_03v3` | W=10 µm, L=4 µm | not matched (single instance, mirrors `bandgap_core.ibias`) |

**Layout technique**: M1 and M2 are laid out as an interdigitated,
common-centroid pair — each device's `nf=2` fingers interleaved with the
other device's fingers (e.g. an A-B-B-A finger ordering), with dummy
fingers at both array ends, mirroring the same discipline
`design/device-characterization.md` §2 already specifies for the
resistor array. M3/M4 form a second, separate interdigitated group at
the mirror load.

**Why this matters for a budget line that is not yet closed by
simulation**: `design/bandgap_error_budget.md` §2.2's random-offset
figure (σ = 0.347 mV for M1/M2, 3σ = 1.04 mV — the number entering §0's
25.06 mV total, §2.7's table) is computed from the drawn gate area alone
(`sigma = A_pair * sqrt(2) / sqrt(W*L)`), and that same section states
explicitly: *"a device drawn as `nf=2` fingers of one logical transistor
is... not the same as two independently-mismatched unit devices averaged
together (that requires a deliberate interdigitated common-centroid
*pair* of separate instances, a layout technique — #16's job, not
credited here)."* This floorplan's interdigitation of M1 against M2 (not
just each device's own two fingers) does not change the *random*-offset
number already budgeted (that number already assumes the full drawn
area, with no additional averaging credited) — its effect is on the
**systematic** offset component, `design/bandgap_error_budget.md` §2.3's
2 mV (3σ-equivalent) placeholder reserve *"pending #16's common-centroid
layout and any post-layout extracted verification."* This floorplan
commits to the common-centroid technique that placeholder assumed; **it
does not, by itself, replace the placeholder with a verified number** —
that requires post-layout parasitic extraction, out of this document's
scope (the same "document, not GDS" boundary stated throughout).

## 7. Startup circuit (issue #11 devices)

Per `design/bandgap_operating_point.md` §1a/§2, four devices, none of
which are part of a matching group (no differential pair among them):

- `XMSENSE` (`nfet_03v3`, W=20 µm/L=2 µm) — sized to replicate
  `bandgap_core.Mn5`; a single instance, no matching requirement.
- `XRPU` (`ppolyf_u_1k`, W=2 µm/L=4000 µm, ≈2 MΩ) — the always-on
  pull-up bleeder. This is the **single largest area line item in the
  whole block** (§8) at ~8000 µm² of drawn poly body at W = 2 µm; a
  literal straight-line 4 mm-long resistor is not a realistic floorplan
  shape, so this element is laid out as a folded/serpentine meander
  (standard practice for a high-value poly resistor; gf180mcu's
  `ppolyf_u_1k` model has no bend-specific TC/resistance correction term
  this repo has characterized, so the folded layout's electrical value
  should be re-verified once drawn rather than assumed identical to the
  straight-line hand value — flagged as an open item, §11.3). Per
  `design/bandgap_operating_point.md` §1a, this device carries no
  ratio-critical role (it sets a static pull-up current, not a matched
  ratio), so it uses `ppolyf_u_1k` rather than `ppolyf_u`, consistent
  with `design/device-characterization.md` §2's recommendation to
  reserve `ppolyf_u_1k` for "non-ratio-critical bulk resistance."
- `XMKFB` / `XMKCASC` (`nfet_03v3`, W=2 µm/L=2 µm each) — small kick
  devices, placed close to the `fb`/`casc` nets they drive (§1's
  floorplan overview) to keep those kick-path routing runs short, since
  they only need to act at power-up, not to match anything.

Per §1, this whole block sits at the die periphery, away from the
matched core, since its only interaction with the matched devices is two
kick taps.

## 8. Area budget

**Status of the target**: `README.md`'s "Target specification" table —
ratified 2026-07-31 per issue #1/#35
([`spec/decision-records/0003-target-spec-ratification.md`](../spec/decision-records/0003-target-spec-ratification.md))
— carries an Area row: **< 0.05 mm² (50,000 µm²)**, marked "n/a (not a
PVT line)." This row **is** part of the ratified spec (not draft), unlike
some earlier drafts of this issue's own text assumed — worth stating
plainly here since the spec's own ratification postdates some of this
issue's curation passes.

**What this tally is, and is not**: this floorplan has no GDS behind it
(§ intro) — the figures below are computed directly from drawn device
geometry in the schematics/design docs (a "floor," not a measurement),
excluding contacts, inter-device spacing, guard-ring rings, well/tap
area, and metal routing, none of which have been drawn. This is the same
limitation `design/device-characterization.md` §2's own "~620 µm² per
branch" resistor-area estimate carries (body area only). Per CLAUDE.md
("no claim without a testbench"), this is reported as an **informed,
schematic-derived floor**, not a GDS-verified area — the authoritative
figure is the layout-implementation issue's job once real geometry
exists (named as the open item in §11.1).

**Line-item currency note (issue #151):** every row below except "Amp:
M3/M4" is this document's original #16-era estimate and predates #42's
telescopic-cascode amp rebuild and #55/#61/#96/#147's core/amp resizes —
`design/bandgap_error_budget.md` §5c/§5d already flags this table as stale
for that reason. Only the M3/M4 row is corrected here, to the geometry issue
#151 actually draws; a full resync against every device's current schematic
size remains owned by the layout-implementation follow-up (§11.1). The
subtotal below uses the corrected M3/M4 figure (so it is not simply the sum
of #16-era numbers), but every other row still carries #16-era, not current,
device sizes.

| Line item | Basis | Drawn body area (µm²) |
|---|---|---|
| PNP array (Q1×1 + Q3×1 + Q2×4 unit devices, §4.1) | 6 × 25 µm² (drawn emitter, `pnp_05p00x05p00`) | 150 |
| Resistor array — R1 | 230.180 µm × 2 µm (§3.1) | 460.36 |
| Resistor array — R2 | 18 µm × 2 µm (§3.1) | 36 |
| Trim ladder (63 unit segments, §3.2/3.3) | 63 × (1.215 µm × 2 µm) | 153.09 |
| Amp: M1/M2 (input pair) — #16-era, stale (§6: current is 300 µm/6 µm, `nf=12`, per #147) | 2 × (100 µm × 4 µm) | 800 |
| **Amp: M3/M4 (mirror load) — current as of #151** | 2 × (33 µm × 26.4 µm) | **1742.4** |
| Amp: M5 (tail) | 10 µm × 4 µm | 40 |
| Core mirror+cascode: M1–M4, MC1–MC4 — #16-era, stale (current is 85 µm/8.5 µm per #147) | 8 × (20 µm × 2 µm) | 320 |
| Core: MCB | 4 µm × 12 µm | 48 |
| Core: MNB | 5 µm × 2 µm | 10 |
| Core: Mn5 | 20 µm × 2 µm | 40 |
| Startup: XMSENSE | 20 µm × 2 µm | 40 |
| Startup: XRPU (2 MΩ bleeder, §7) | 2 µm × 4000 µm | 8000 |
| Startup: XMKFB, XMKCASC | 2 × (2 µm × 2 µm) | 8 |
| **Subtotal (drawn active/body area only, M3/M4 current, all else #16-era)** | | **11,847.85** |
| **≈ mm²** | | **≈ 0.0118 mm²** |
| **Ratified target** | | **0.05 mm²** |
| **Fraction of target consumed by this floor alone** | | **≈ 23.7 %** |

Delta from this issue's own resize: M3/M4 body area 320 → 1742.4 µm²
(+1422.4 µm² against the #16-era 320 µm² baseline in this table — see
`design/bandgap_error_budget.md` §5d for the delta against the more relevant
pre-#151/post-#147 baseline of 640 µm², which is +1102.4 µm²).

**Cross-check against `layout/bandgap_top/area_report.py` (issue #151)** — a
tool that already exists and computes drawn device body area live from
`design/netlist/bandgap_top.spice` (not a hand tally): run before and after
this issue's resize, it reports the amp group's body area moving
10,140.00 → 11,242.40 µm² (**+1,102.40 µm²**), independently confirming the
`design/bandgap_error_budget.md` §5d delta above to the last decimal place.

**Update (issue #156 — resolved, GDS-verified verdict, not a floorplan-stage
estimate any more):** the tool's *other* number — `drawn GDS area` read back
from the checked-in `layout/bandgap_top/bandgap_top.gds` — used to report
only **2.4 % headroom** against the ratified 0.05 mm² target, but that GDS
file's last commit (`ba091ea`, before #55/#61/#96/#147/#151's device
resizes) predated all of those resizes, so the 2.4 % figure was stale.
**#156 regenerated `bandgap_top.gds` from the current netlist and committed
it as the current baseline; the real, GDS-verified area budget is broken:
80,813.72 µm² drawn vs. the ratified 50,000 µm² target — 61.6 % OVER
budget** (up from a bracketing measurement taken mid-investigation, before
`#151`'s own change, of 58.5 % over on the post-`#147` netlist —
`#151` adds a further ~3 percentage points on an already-broken budget, not
the cause of it). This is no longer an open risk to track down — it is the
measured verdict; see `spec/decision-records/0005-area-target-overrun.md`
for the analysis (routing overhead is *not* the problem — at 3.19× drawn
area over drawn body area it beats this section's own "generous" 4×
assumption; drawn body area itself grew 2.43× past this section's estimate,
driven by already-ratified accuracy/stability work) and the proposed
resolution (an interim revised target, **pending operator ratification** —
not silently applied by that record alone, per CLAUDE.md).

**Reading this table**: the drawn-body-area floor is comfortably under
the ratified 0.05 mm² ceiling — even a generous 4× overhead multiplier
for contacts, dummy devices, guard rings, well/tap spacing, and routing
(a plausible range for a small analog block with no dense digital
content) would land at ≈0.042 mm², still inside budget. **This is not a
pass claim** — it is a floor-plan-stage estimate, and the real overhead
multiplier is unknown until GDS exists (§11.1's owned follow-up). Two
concrete, named risks within this estimate, not generic hand-waving:

1. **`XRPU`'s 8000 µm² alone is ~16 % of the entire target** and the
   single largest line item by a wide margin (it does not need to be
   matched to anything, but it does need to fit; §7's folding note).
2. **PNP-array and MOS-array real cell pitch (guard rings, base/collector
   contact rings for the substrate PNP device, well spacing between the
   analog core and any adjacent digital circuitry) is not characterized
   anywhere in this repo** — no PCell/GDS data for `pnp_05p00x05p00` /
   `pnp_10p00x10p00` exists yet. This is the largest source of
   uncertainty in the table above.

**No spec relaxation**: at this floorplan stage, no gap against the
0.05 mm² target is found — the drawn-body floor above leaves substantial
headroom even under a conservative overhead multiplier. This is reported
as-is, not adjusted to make the comparison land more favorably. If the
real, GDS-derived area (once drawn) turns out to exceed the target, that
finding belongs to the layout-implementation follow-up issue named in
§11.1, which should re-run this comparison against real geometry rather
than this document's estimate.

## 9. Substrate and guard-ring strategy

Per `design/bandgap_operating_point.md` §1's "Why the PNP collector is
grounded" note: gf180mcu's vertical PNP collector **is** the p-substrate,
and every instance on the die shares one substrate node — confirmed
directly against the PDK model (`pnp_05p00x05p00`'s `.subckt c b e`, base
tied to collector tied to `vss` in this design). This has two concrete
layout implications:

- **A single, low-resistance guard ring** (p+/psub taps tied to `vss`)
  surrounds the whole matched-device core (PNP array + resistor/trim
  strip + MOS mirror/cascode + amp), isolating it from any
  digital-adjacent circuitry in a larger integration and providing the
  low-impedance substrate return path each PNP's base current
  (§4.2 — up to 3:1 PVT-swinging, comparable to or exceeding collector
  current) needs, symmetrically, per PNP unit.
- **`ppolyf_u`'s own substrate-coupling terminal does not carry the same
  concern the issue's original implementation guidance flagged.** That
  guidance pointed at "the resistor characterization bench swept the p+
  resistor's n-well tie over ±10% of 3.3V" (`design/device-
  characterization.md` §2, `sim/device-resistor-tc/`) as implying a real
  n-well bias choice for the resistor array. Checked directly against
  both the sim record and the PDK model: that n-well sweep was performed
  on **`pplus_u`** (a p+ diffusion resistor whose body sits in a
  reverse-biased n-well junction) — **not `ppolyf_u`**, the flavor R1/R2/
  the trim ladder actually use. `ppolyf_u`'s PDK subcircuit
  (`sm141064.ngspice`, `.subckt ppolyf_u 1 2 3 ...`) is a 3-terminal
  device whose third pin is a `fox_sub` parasitic-capacitance coupling
  node, not a bias-critical well junction — there is no n-well bias
  choice to make for R1/R2/trim the way there would be for a `pplus_u`
  resistor. What *is* a real layout decision: every `ppolyf_u` instance's
  substrate-coupling terminal should tie to the same defined,
  low-impedance node (`vss`, via the guard ring above) consistently
  across R1, R2, and all 63 trim-ladder segments, so the parasitic
  substrate coupling is uniform across the array rather than an
  unmodeled source of code-dependent or unit-to-unit asymmetry.

## 10. Supply routing

Per `design/bandgap_error_budget.md` §3.2–3.4 (Section 5's escalation),
the amplifier's own PSRR contribution falls **5–28 dB short** of the
ratified >60 dB DC–1 kHz target across the full PVT grid, while
`bandgap_core`'s cascoded stage does not appear to be the limiter
(§3.3's diagnostic, 80–99 dB on the majority of the grid). That shortfall
is escalated as real analog design work out of #10's scope (a
supply-regulated cascode bias or different PSRR topology) — but layout
supply-routing symmetry is the one lever available *today*, at the
floorplan stage, that can avoid making the already-short PSRR worse
without waiting on that redesign:

- A **dedicated analog `vdd`/`vss` routing pair**, separate from any
  digital supply in a larger integration, feeding the block from a
  single low-impedance point.
- **Matched routing length/width from that point to every mirror leg**
  (M1–M4/MC1–MC4's `vdd` connections) and to the amp's own `vdd` — an
  asymmetric supply-routing impedance across the four core legs would
  reintroduce exactly the kind of leg-to-leg mismatch
  `design/bandgap_operating_point.md` §3's cascode measurement shows the
  circuit design already suppresses 130×; layout should not undo that.
- **Decoupling capacitance placed close to `fb` and `casc`** (the two
  nodes the startup circuit's kick devices also target,
  `design/bandgap_operating_point.md` §1a) — these are the two nodes
  whose supply-coupled ripple most directly perturbs the servo loop and
  the cascode bias point.
- The startup branch's own current draw is already isolated via a
  dedicated zero-volt ammeter tap in every `sim/startup*` testbench
  (`design/bandgap_operating_point.md` §3a) — the floorplan keeps that
  same electrical separation by routing `XRPU`'s pull-up path (§7) off
  the shared core `vdd` rail at a point that does not inject its own
  (small, ≈1.1–2.4 µA per `design/bandgap_operating_point.md` §3a) current
  asymmetrically into the matched-device core's own supply node.

This is a routing-symmetry statement, not a PSRR fix — it does not close
the 5–28 dB gap (`design/bandgap_error_budget.md` §5 names that as a
real amplifier/topology redesign, out of this issue's scope), only
avoids adding avoidable layout-induced degradation on top of it.

## 11. Open items and owners (no silent gap-closing)

Per this issue's Acceptance Criteria ("if the area tally or matching plan
cannot meet the draft target, the document reports the gap and names an
owner") and the general "no spec relaxation" rule: the area comparison in
§8 does **not** currently show a gap, so there is nothing to escalate on
that front today. Two items are named explicitly as **not yet closed** by
this document, so they are not silently assumed away:

### 11.1 GDS-verified area re-check (closed by issue #156; §8's original "once real layout exists" framing is stale)

§8's original area tally was a schematic-geometry floor with no
contact/dummy/guard-ring/routing overhead included, and no characterized
real cell pitch for the PNP devices — this section originally deferred the
real, GDS-verified comparison to "the future layout-implementation issue
this floorplan feeds."

**That deferral is stale — the comparison is not future work; #156 ran it.**
Real (drawn) layout and a live comparison tool have existed since #66/#151
(`layout/bandgap_top/generate.py`, `layout/bandgap_top/area_report.py`), and
both had drifted out of sync with several device resizes by the time #156
regenerated the GDS. **Issue #156's findings, now the current, committed
state:**

- `layout/bandgap_top/bandgap_top.gds` is regenerated from the current
  `design/netlist/bandgap_top.spice` and committed as the baseline (no
  `generate.py`/`plan.py` code changed — this is a pure data refresh against
  already-ratified device sizing).
- The GDS-verified verdict is **FAIL: 80,813.72 µm² drawn vs. the ratified
  50,000 µm² (0.05 mm²) target, 61.6 % over budget** — not a floorplan-stage
  estimate, a measurement (§8's cross-check note above has the full
  `area_report.py` output).
- The overrun is **not** a routing-inefficiency problem: the realised
  overhead multiplier (3.19× drawn area over drawn device body area) is
  *better* than this document's own "generous" 4× assumption. It is a
  body-area problem — drawn device body area (25,327.78 µm²) has grown to
  2.43× §8's original schematic-derived floor, from already-ratified,
  measured accuracy/stability work (`#96`/`#147`/`#151`; see
  `design/bandgap_error_budget.md` §5c/§5d). Reopening those resizes to
  reclaim area would reopen closed electrical verdicts, which is out of
  this section's scope and not proposed.
- Per CLAUDE.md's no-silent-relaxation rule, the gap is **escalated, not
  closed by editing the target**:
  [`spec/decision-records/0005-area-target-overrun.md`](../spec/decision-records/0005-area-target-overrun.md)
  proposes an interim revised Area row (`< 0.085 mm²`) with the full
  feasibility analysis of a routing-only fix, but is filed `Status:
  proposed`, **pending operator ratification** — `README.md`'s ratified
  Area row and `area_report.py`'s `RATIFIED_TARGET_UM2` constant are
  deliberately left unedited until that ratification lands, so the tool
  keeps reporting `FAIL` honestly in the meantime.
- A genuine routing-architecture fix (multi-level-metal routing, now
  extraction-viable per klayout-tools#220, in place of the current
  Metal1/Poly2-only corridor-and-rail scheme) is named in DR-0005 and filed
  as [#160](https://github.com/2AMLogic/gf180-bandgap/issues/160), not
  attempted speculatively inside #156.

### 11.2 Amp systematic-offset placeholder (owner: post-layout extraction, tracked by #10's own escalation)

§6 notes that `design/bandgap_error_budget.md` §2.3's 2 mV (3σ-equivalent)
systematic-offset reserve remains a placeholder pending "post-layout
extracted verification" — this floorplan commits to the common-centroid
technique that placeholder assumed but does not itself produce a
verified replacement number. That verification is downstream of real
layout (out of this document's "document, not GDS" scope) and should be
tracked as part of whatever issue performs post-layout parasitic
extraction.

### 11.3 `XRPU` folded-layout electrical re-verification (owner: layout-implementation issue, §7)

The 4000 µm straight-line startup bleeder resistor is assumed to fold
into a serpentine/meander shape without changing its ≈2 MΩ value; gf180mcu's
`ppolyf_u_1k` model has no repo-characterized bend-correction term, so
this should be re-verified once the actual folded geometry is drawn.

## 12. Traceability summary

Every quantitative claim above traces to one of:

- `design/bandgap_operating_point.md` (§1, §1a, §2, §3, §4.4) — topology,
  device sizes, leg-matching measurement, base-current loading
- `design/bandgap_error_budget.md` (§2.1–2.7, §3.2–3.4, §5) — final amp
  sizing, offset budget lines and their sensitivities, PSRR shortfall
- `design/bandgap_trim_network.md` (§1, §4) — `tn0` tap point, trim
  ladder structure and sizing rationale
- `design/device-characterization.md` (§1, §2, §4) — PNP ratio/beta,
  resistor flavor recommendation and known gaps, MOS mismatch data
- `sim/mc-untrimmed/records/20260801-053436-6bbbdb7.md` — final-netlist
  sensitivity ranking (resistor vs. MOS+BJT), untrimmed window-check
- `sim/trim-coverage/records/20260801-061650-083d402.md` — trimmed
  coverage result (cited for context, §0)
- `sim/device-pnp-mismatch/records/20260731-040850-187a336.md` — intrinsic
  PNP mismatch (negligible, §0/§4.2)
- `sm141064.ngspice` (gf180mcu PDK model file) — `ppolyf_u`/`pnp_05p00x05p00`
  subcircuit pin definitions and `mis_r = 0` confirmation, checked
  directly against the installed PDK (`~/.volare/.../gf180mcuD/libs.tech/
  ngspice/sm141064.ngspice`) rather than assumed from documentation alone
- `spec/decision-records/0003-target-spec-ratification.md` — ratified
  status of the Area row
