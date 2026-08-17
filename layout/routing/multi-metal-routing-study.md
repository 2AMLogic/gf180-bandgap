# Multi-level-metal routing for `bandgap_top`: scheme, and how much area it recovers

- **Issue**: [#160](https://github.com/2AMLogic/gf180-bandgap/issues/160)
  ("Explore multi-level-metal routing for `bandgap_top` to recover area
  headroom"), the follow-up
  [`spec/decision-records/0005-area-target-overrun.md`](../../spec/decision-records/0005-area-target-overrun.md)
  (DR-0005) named.
- **Status**: design + estimate — **now implemented**, see the outcome note
  immediately below. No routing code was changed *by this study*;
  [#166](https://github.com/2AMLogic/gf180-bandgap/issues/166) was filed
  separately on the strength of the numbers below, and did the rewrite.

> **Outcome (#166, 2026-08-17).** `layout/bandgap_top/generate.py` now draws
> the §3 scheme, so everything below describing the corridor-and-rail scheme
> as current ("as drawn today", "S0", §2's decomposition) is a **historical
> record of the pre-#166 block**, not a description of the repo today. The
> realised block measures **62,505.60 µm² / 2.47×** — 5.1 % *better* than
> S1's 65,896.39 µm² / 2.60× estimate, because the two conservatisms §5
> declares (the 1.0 µm/row landing band and the 0.20 µm left margin) both
> went to zero: the Metal3 rails ended up *inside* each row's own device
> content. §6's finding is unaffected and now governs — the remaining gap is
> row-stripe whitespace, needing the 2-D re-pack of §8, and the required row
> packing is **0.698** against today's 0.556. Estimate-vs-measurement
> write-up: `layout/bandgap_top/AREA.md` Finding 6.
>
> `routing_budget.py` was rebased onto the new block by the same issue, so it
> no longer re-derives the S0/S1c/S2 rows below (that geometry is no longer
> drawn); it carries S0 and S1 as named constants with provenance and
> measures the drawn block against them.
- **Reproduce every number here** with:

  ```bash
  uv run --with klayout python3 layout/bandgap_top/routing_budget.py
  ```

  and the study's load-bearing claims are pinned by
  `layout/bandgap_top/test_routing_budget.py` +
  `layout/drc/fixtures/m2m3_stack_probe/test_m2m3_stack_probe.py`. Per
  CLAUDE.md ("verification is the product"), nothing below is asserted that
  a tool run does not produce.

## 1. Verdict, up front

Multi-level-metal routing is **worth doing and does not, on its own, close
the area gap.**

| | drawn area | overhead multiplier | vs. ratified 50,000 µm² |
|---|---|---|---|
| **S0** — as drawn today (Metal1 + Poly2) | 80,813.72 µm² | 3.19× | +30,813.72 (FAIL) |
| **S1** — Metal2/Metal3 over-the-cell rails | **65,896.39 µm²** | **2.60×** | +15,896.39 (still FAIL) |
| S1c — S1, conservative landing band (§5) | 67,563.64 µm² | 2.67× | +17,563.64 |
| S2 — *bound*: S1 with a zero-height landing band (unbuildable) | 62,561.89 µm² | 2.47× | +12,561.89 |
| S3 — S1 **plus a 2-D re-pack** of the rows, 80 % packing | 45,927.92 µm² | 1.81× | −4,072.08 (PASS) |

- The ratified 0.05 mm² target needs the multiplier at **≤ 1.97×**
  (50,000 / 25,327.78 µm² of drawn device body area).
- Routing alone recovers **14,917.33 µm² (18.5 %)** — **48.4 %** of the
  30,813.72 µm² reduction the target needs, and it moves the multiplier
  3.19× → 2.60×, i.e. 48 % of the way from 3.19× to 1.97×.
- The remaining half is **not** in the routing at all. Even S2 — a physically
  unbuildable bound where routing costs *zero* block height and *zero*
  corridor width — still lands at 2.47×, 25 % over the target. What is left
  is whitespace inside the row-stripe floorplan (§6).

**Implication for DR-0005 (§7): it partially closes the gap. The interim
target could later be *narrowed*, not reverted — and not until the rework is
actually implemented and measured.** This study changes no spec number and
edits no ratified value.

## 2. Where the drawn area actually goes

`routing_budget.py` decomposes the drawn block into the terms
`generate.build()` itself places, and **checks** the decomposition: the
reconstructed bounding box must equal the drawn one to the nanometre
(`check_identity`), and the modelled "as drawn" area must equal what
`area_report.py` measures out of the committed GDS (80,813.72 µm², to the
0.01 µm²). So the split below is an accounting of real geometry, not a
plausible story about it.

| Axis | Term | Extent |
|---|---|---|
| width | Poly2 spine corridor + `FIELD_GAP` (25 nets × 0.64 µm + 0.9) | **16.90 µm** |
| width | device field (the widest row, `AMPPAIR`) | 215.30 µm |
| width | left margin (the `vss` spine's own half-width) | 0.20 µm |
| width | guard ring + clearance, both sides | 6.40 µm |
| height | device content (15 rows, tallest item each) | 258.83 µm |
| height | **stacked Metal1 rail bands** (`HEAD` + rails × `TRACK_PITCH`) | **56.42 µm** |
| height | inter-row gaps (14 × `ROW_GAP`) | 15.40 µm |
| height | bottom margin (`POLY_EXT`) | 0.40 µm |
| height | guard ring + clearance, both sides | 6.40 µm |
| both | guard ring's own Pplus marker overhang (in the GDS bbox) | +0.40 µm/axis |

Total: (0.20 + 16.90 + 215.30 + 6.40 + 0.40) × (0.40 + 258.83 + 56.42 +
15.40 + 6.40 + 0.40) = 239.20 × 337.85 = **80,813.72 µm²**.

The two bold rows are what single-metal routing costs: **16.90 µm of width
and 56.42 µm of height**, exactly the two mechanisms `generate.py`'s own
"Routing style, and why it looks like this" docstring describes — a
dedicated per-net Poly2 corridor down the left edge, and one Metal1 rail per
net stacked vertically above every row.

## 3. The proposed scheme

Replace the corridor-and-rail discipline with an ordinary two-layer
over-the-cell routing grid. Nothing about device drawing, the row order, the
matching arrays, the Nwell band or the guard ring changes.

| Layer | Role today | Role in the proposed scheme |
|---|---|---|
| `Poly2` (30/0) | per-net vertical spines in a left-edge corridor **+** device stubs/crossunders | gate poly and resistor bodies only — no routing, no corridor |
| `Metal1` (34/0) | one horizontal rail per net per row, stacked above each row | device-local straps only (already drawn: SD bars, resistor pads, taps) + Via1 landing pads; keeps the `vdd`/`vss`/`vref` label patches (34/10) the deck promotes to pins |
| `Via1` (35/0) | MIM cap only | Metal1 → Metal2 hop at every device terminal |
| `Metal2` (36/0) | MIM cap only | **vertical global spines, one per routed net, over the device field** (replaces the Poly2 corridor) |
| `Via2` (38/0) | MIM cap only | Metal2 ↔ Metal3 at each spine/rail crossing |
| `Metal3` (42/0) | MIM cap only | **horizontal per-row rails, running over that row's own devices** (replaces the stacked Metal1 rails) |
| `Metal4` (46/0) / `FuseTop` / `Via3`/`Via4` / `Metal5` | MIM cap only | **unchanged — deliberately not used for routing** (§4) |

Consequences for `generate.py`'s drawing code (for the implementation
issue, not done here):

- `draw_mos`'s poly gate stub gains a local Contact + Metal1 pad, so a gate
  can be reached by Via1 like every other terminal. Source/drain and
  resistor/tap/PNP terminals already terminate on Metal1 and need only a
  Via1 pad.
- The per-row rail loop in `build()` draws Metal3 at the row's own y range
  instead of Metal1 above it, and the corridor loop is deleted.
- The guard ring's `vss` tie currently runs as a Metal1 strap over the `vss`
  Poly2 spine (a poly strap would extract as a spurious NMOS where it crosses
  the ring's COMP). With no corridor, that tie becomes a short Metal1 strap
  from the ring up to the nearest `vss` Metal1 pad, then Via1 to the `vss`
  Metal2 spine.
- `_mim_cap` lands its `vdd`/`fb` via stacks on **already-drawn Metal1 rails**
  of the `AMPPCASC` row (`rail_geo`). Those rails move to Metal3, so the cap's
  two stacks shorten (they start at Metal3 rather than climbing from Metal1) —
  a re-point, not a redesign, but it touches the one piece of geometry in this
  block whose extraction behaviour was hard-won (#77/#82/#88/#89).

## 4. Sizing against the deck

Read out of the **installed** deck (`klayout_tools/decks/gf180mcu.py`,
`klt 0.2.0`, deck content hash
`sha256:e2726af8…` as recorded in the probe's DRC report), not from memory
or from `layout/README.md`'s prose.

| Rule | Deck minimum | Proposed | Margin |
|---|---|---|---|
| `metal2.width.1`, `metal3.width.1` | 0.28 µm | 0.40 µm track width | 1.43× |
| `metal2.space.1`, `metal3.space.1` | 0.28 µm | 0.32 µm track space | 1.14× |
| — track pitch — | — | **0.72 µm** | — |
| `via1.width.1`, `via2.width.1` | 0.26 µm | 0.26 µm (the DRM's fixed size) | 1.00× |
| `via1.space.1`, `via2.space.1` | 0.26 µm | single vias on a 0.72 µm grid — 0.46 µm edge to edge | 1.77× |
| `metal2.enclosing.via1.1`, `metal3.enclosing.via2.1` | 0.01 µm | 0.07 µm (0.40 µm pad on a 0.26 µm via) | 7× |
| `metal1.enclosing.via1.1` | 0.00 µm | 0.09 µm (0.44 µm Metal1 pad) | — |

**Two notes that matter more than the margins:**

- **`Metal4` is deliberately excluded from the routing scheme.** The deck has
  **no `metal4.width` / `metal4.space` rule at all** — `Metal4` (46/0) appears
  only inside the MiM-capacitor rules (`mim.space.1`, `mim.enclosing.fusetop.1`,
  `mim.enclosing.via4.1`), all three scoped to a *derived* "virtual bottom
  plate" layer (FuseTop sized by 1.06 µm ∧ Metal4). Routing on Metal4 would
  therefore put block geometry on a layer this repo's DRC cannot check —
  unacceptable under "verification is the product" — and ordinary Metal4
  routing near the compensation cap is exactly the geometry `mim.space.1`'s
  1.2 µm separation rule polices. `Metal5` is likewise left alone (it carries
  real width/space rules, but the scheme does not need a third routing level,
  and the MIM cap's `fb` wire already owns it locally). **Two routing levels
  are enough**: §5's track-fit check passes on every row with margin.
- **`via*.width.1` is why the current `VIA_W = 240` nm is already a
  violation.** The deck grew `via1..via4.width.1` (0.26 µm) after the MIM
  cap's via stack was drawn against a deck where the via layers were rule-free
  — that drift is [#159](https://github.com/2AMLogic/gf180-bandgap/issues/159),
  and it is the reason the *current* `bandgap_top.gds` reports 42 DRC
  violations today (16 of them `via*.width.1`). Any implementation of this
  scheme must size vias at ≥ 0.26 µm, which is what the numbers above do.

### Track-fit check

Two capacity questions decide whether "over the cell" really costs zero
block area. `routing_budget.py` answers both from the current plan:

- **Per row: do that row's Metal3 rails fit inside the row's own device
  height at 0.72 µm pitch?** Yes, all 15 rows, worst case `CORECASC` at
  8 rails = 5.76 µm inside 21.25 µm of content, and the tightest ratio
  `PBIAS` at 2.88 µm inside 5.00 µm (58 %). The single-rail `NTAP` row
  (1.60 µm tall) needs 0.72 µm.
- **Across the block: does the Metal2 spine bundle fit over the device
  field?** 25 routed nets × 0.72 µm = **18.00 µm of the 215.30 µm field
  (8.4 %)** — and unlike today's 16.90 µm Poly2 corridor, that 18 µm sits
  *above* devices instead of beside them, so it costs no width.

## 5. The arithmetic

The model changes exactly two terms of §2's decomposition and leaves every
other term untouched:

1. **Corridor → 0.** The 25 Poly2 spines and the 0.9 µm `FIELD_GAP` go away;
   the device field starts at the block edge. Width 239.20 → **222.30 µm**.
   (The 0.20 µm left margin is kept, conservatively — it disappears too.)
2. **Stacked rail bands → one landing band per row.** Each row keeps a
   vertical band above its devices for the Metal1 → Via1 → Metal2 hop off a
   gate stub, instead of `HEAD + (rails − 1) × 0.64 + 0.2` of stacked
   Metal1. Budget: `BAR_TOP` (0.70 µm of Metal1 bar already drawn above each
   MOS COMP) + half a via pad (0.20) + margin (0.10) = **1.00 µm × 15 rows =
   15.00 µm**, replacing 56.42 µm. Height 337.85 → **296.43 µm**.

```
S0  239.20 × 337.85 = 80,813.72 µm²   3.19× body area   (measured, area_report.py)
S1  222.30 × 296.43 = 65,896.39 µm²   2.60× body area
    ├── corridor removal alone : 222.30 × 337.85 = 75,104.06  (−5,709.66)
    ├── rail collapse alone    : 239.20 × 296.43 = 70,906.05  (−9,907.67)
    └── both (incl. cross term): 65,896.39                    (−14,917.33)
```

**Sensitivity to the one modelled parameter.** The landing band is the only
number here that is a judgement rather than a measurement, so the estimate is
bracketed rather than tuned:

- `LANDING_BAND = 1.5 µm` (S1c) — the *current* cost of a one-rail row
  (`NTAP`), i.e. assuming the rework saves nothing at all per row beyond
  collapsing the stack: 67,563.64 µm², 2.67×.
- `LANDING_BAND = 0` (S2) — an unbuildable lower bound: 62,561.89 µm², 2.47×.

The whole 1.5 µm → 0 sweep moves the answer by 5,001.75 µm² (7.6 %), against
a 15,896.39 µm² shortfall. **No plausible landing-band choice reaches the
target**, which is why §6 rather than §5 is where the rest of the gap lives.

## 6. What multi-metal routing does *not* fix: the row-stripe floorplan

| Nested footprint | Area | × body area |
|---|---|---|
| drawn device body area (from the netlist) | 25,327.78 µm² | 1.00× |
| sum of drawn item bounding boxes | 28,137.33 µm² | 1.11× |
| sum of per-row bounding boxes | 32,805.18 µm² | 1.30× |
| the full-width row-stripe box the rows sit in | 59,041.72 µm² | 2.33× |

The rows fill only **55.6 %** of the stripe box they occupy, because every
row is stacked at the *widest* row's width: `AMPPAIR` is 215.30 µm wide,
`NBIAS` is 31.80 µm, `NTAP` is 40.00 µm. That single fact — 26,236 µm² of
whitespace beside the narrow rows — is larger than the entire 14,917 µm²
routing recovery.

The row stripe exists **because** of the corridor: every rail has to reach a
net's spine at the left edge, so a row cannot be placed anywhere but in its
own full-width horizontal band. Removing that constraint is what makes a 2-D
re-pack (rows placed side by side, tall narrow rows paired with short wide
ones) legal at all — so multi-metal routing is a **prerequisite** for closing
the gap, just not sufficient by itself:

| Row-packing efficiency | Block area | Multiplier | vs. target |
|---|---|---|---|
| 0.556 (today's row stripe) | ~65,896 µm² (S1) | 2.60× | +15,896 |
| 0.60 | 60,717.89 µm² | 2.40× | +10,718 |
| 0.70 | 52,274.42 µm² | 2.06× | +2,274 |
| **0.733** | **50,000 µm²** | **1.97×** | **0 (the break-even)** |
| 0.80 | 45,927.92 µm² | 1.81× | −4,072 |
| 0.90 | 40,981.95 µm² | 1.62× | −9,018 |

(Square block, each row keeping its own footprint plus the 1.0 µm landing
band, guard ring added outside.)

So the ratified 0.05 mm² target is **reachable in principle** — it needs
multi-metal routing *and* a re-pack that gets row packing from 0.556 to
≥ 0.733. It is not reachable by re-routing alone under any assumption
modelled here.

## 7. Implication for DR-0005 (stated explicitly)

DR-0005 proposes revising the ratified Area row from `< 0.05 mm²` to
`< 0.085 mm²`, `Status: proposed`, pending operator ratification. Of the
three outcomes issue #160 asked this study to choose between:

- **"Fully closes the gap — the interim target could later be reverted"**:
  **no.** Routing alone lands at 2.60× (65,896 µm²), against the 1.97×
  (50,000 µm²) a revert would require.
- **"Partially closes it — the interim target could be narrowed"**:
  **yes, this is the finding.** If the scheme in §3 is implemented and
  measured at ≈65,900 µm², a successor record could narrow the interim
  ceiling to ≈**0.070 mm²** (65,896 × 1.05, keeping DR-0005's own ~5 %
  margin convention) — *after* the rework lands, never before. Per
  `spec/decision-records/TEMPLATE.md`, that is a **successor record**, not an
  edit to DR-0005.
- **"Does not close it materially — the interim target stands"**: **true
  today, and it is the state this study leaves things in.** Nothing is
  implemented; `area_report.py` still measures 80,813.72 µm² and still
  reports `FAIL` against the unedited ratified 50,000 µm². This study
  changes no spec value and no `RATIFIED_TARGET_UM2`.

The one substantive update to DR-0005's own reasoning: its "Alternatives
considered" entry judged the routing rewrite as needing to "beat the
floorplan's own 'generous' 4× assumption by more than the achieved 3.19×
already does." That framing is confirmed and now quantified — the rewrite
gets to 2.60×, roughly half the required move — and its conclusion (file the
rewrite separately rather than fold it into a spec-escalation issue) stands.

## 8. Evidence, and what is left open

### Evidence produced by this study

| Claim | How it was checked | Where |
|---|---|---|
| The Metal1→Via1→Metal2→Via2→Metal3 stack extracts as one net (klayout-tools#220 really covers it) | two `ppolyf_u` resistors wired into a **series loop** over nothing but the proposed stack; `klt extract` reports 2 devices and 2 routed nets (+ the synthesized `vsubs`), and both resistors share the *same* net pair — 4 nets would mean the stack is invisible, 1 would mean the tracks shorted | `layout/drc/fixtures/m2m3_stack_probe/`, `layout/lvs/reports/m2m3_stack_probe/20260817-005816-f5d9512.extract.json` |
| The proposed track/via sizing is DRC-clean under the deck as installed | `klt drc --deck gf180mcu` on that fixture: `status: clean`, 0 violations, with `30/0, 33/0, 34/0, 35/0, 36/0, 38/0, 42/0` in `coverage.layers_checked` — i.e. Metal2, Metal3, Via1 and Via2 rules all actually ran | `layout/drc/reports/m2m3_stack_probe/20260817-005752-f5d9512.drc.json` |
| Metal2/Metal3 tracks may run **over** a recognised device body | the fixture's Metal2 columns are drawn directly over each resistor's poly body and its Metal3 tracks cross both bodies; extraction still recognises both `ppolyf_u` devices | same two reports |
| The area decomposition is real geometry, not a story | `check_identity` (model bbox == drawn bbox, to the nm) and `test_baseline_scenario_matches_the_measured_gds_area` (model S0 == `area_report.py`'s measured 80,813.72 µm²) | `layout/bandgap_top/test_routing_budget.py` |

### Deliberately *not* re-verified here

`bandgap_top.gds` is **unchanged by this study**, so its DRC/LVS status is
exactly what `layout/README.md`'s "Table currency note" already records: the
committed reports are clean/match, and a `klt` installed today instead
reports 42 DRC violations and 18 LVS mismatches against the *same* geometry
— a `klt`-version drift tracked as
[#159](https://github.com/2AMLogic/gf180-bandgap/issues/159), independent of
this study and unaffected by it. (§4 notes that #159's `via*.width.1` half is
a hard prerequisite for the implementation.)

### Open questions for the implementation issue ([#166](https://github.com/2AMLogic/gf180-bandgap/issues/166))

1. **Parasitics.** Metal2/Metal3 rails plus Via1/Via2 stacks add series
   resistance on the supply and bias rails that the current single-metal
   scheme does not have. The extraction deck carries per-layer sheet/cap
   values for Metal2–Metal5, so this is measurable (`klt extract
   --parasitics`) rather than speculative — but it is not measured here, and
   it should gate the implementation, not follow it.
2. **Metal over matched devices.** Over-the-cell routing places metal above
   the tier-1 matched arrays (amp input pair, core mirror/cascode). No
   PDK-modelled mechanical/stress effect is available to this repo, so this is
   flagged as a design-review question (keep heavy rails off the matched
   arrays where the track budget allows — §4's fit check shows there is
   slack), not as a quantified risk.
3. **The 2-D re-pack is a separate change.** §6's S3 family assumes rows can
   be placed two-dimensionally. That is a `plan.py` floorplan change on top of
   the `generate.py` routing change, with its own matching/gradient
   implications (the common-centroid arrays and the PMOS Nwell band constrain
   which rows may move). It should be its own issue, sequenced after the
   routing rework is DRC/LVS-clean.

### Friction filed against klayout-tools

None from this study. Both tool capabilities it depends on — multi-metal
extraction and Metal2/Metal3/Via1/Via2 DRC coverage — are present and were
exercised directly (see the evidence table); the two gaps this design does
have to work around (no `metal4.width`/`metal4.space` rule; via layers that
gained rules after this repo's geometry was drawn against them) are already
recorded in `layout/README.md` § "The gf180mcu DRC deck: coverage" and in
[#159](https://github.com/2AMLogic/gf180-bandgap/issues/159) respectively.
Nothing in the analysis was *blocked*, so nothing is filed — per CLAUDE.md's
friction protocol, which asks for real gaps, not speculative ones.
