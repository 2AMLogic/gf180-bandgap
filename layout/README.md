# layout — `bandgap_top` GDS, DRC and LVS (klayout-tools)

Layout work for this repo is driven by
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`), per
`CLAUDE.md`. This directory holds **the block layout itself** plus the DRC and
LVS flows that verify it.

`layout/bandgap_top/` is a real, drawn physical layout of the whole block
(`bandgap_core` + `bandgap_amp` + `bandgap_startup` + trim ladder), generated
from the committed schematic netlist and **DRC-clean** against the `gf180mcu`
deck. It is currently **not** LVS-matching against its mechanically-derived
reference netlist — see "What the LVS verdict does and does not cover" below
and [#75](https://github.com/2AMLogic/gf180-bandgap/issues/75), which tracks
bringing that reference up to date with what `klt extract` now recognises.

```
layout/
  README.md          this file
  floorplan.md       the matching/floorplan plan this layout implements (#16)
  bandgap_top/
    netlist_model.py  parse + flatten design/netlist/bandgap_top.spice
    plan.py           declarative row/matching plan built from that netlist
    generate.py       draws bandgap_top.gds (klayout.db API)
    matching_report.py verifies the drawn geometry against floorplan.md §0
    area_report.py    drawn area vs. floorplan.md §8 / the ratified target
    AREA.md           the area-budget finding (§11.1's owed re-check)
    bandgap_top.gds   committed, deterministic block GDS
  drc/
    run_drc.py        reproducible klt drc invocation -> committed report
    fixtures/trivial_poly_res/   DRC bring-up proof fixture (#15)
    reports/
      bandgap_top/         <record-id>.drc.{json,txt}
      trivial_poly_res/    <record-id>.drc.{json,txt}
  lvs/
    make_reference.py  derives the LVS reference netlist from the schematic
    run_lvs.py         klt extract + klt lvs -> committed report
    bandgap_top.ref.spice  generated reference netlist (do not hand-edit)
    reports/bandgap_top/   <record-id>.{extract.json,extracted.spice,lvs.json,lvs.txt,lvs-request.json}
  netlist/
    run_extract.py     reproducible klt extract --parasitics invocation (#17) -> committed report
    README.md           post-layout parasitic-extraction findings; resistor/MiM-cap
                         recognition resolved by #73, LVS reference staleness tracked as #75
    reports/bandgap_top/   <record-id>.{extract.json,extracted.spice}
```

## Install `klt`

No PyPI release yet — install from the klayout-tools git repo:

```bash
uv tool install git+https://github.com/2AMLogic/klayout-tools
# or: pip install git+https://github.com/2AMLogic/klayout-tools

klt --version
klt drc --help
```

`klt` runs fully headless: it drives the pip `klayout` package's native
`klayout.db` primitives directly, with **no dependency on the standalone
KLayout GUI/application binary or its `.drc`/`.lydrc` script runner**. Every
command below ran to completion in a shell with no KLayout application
installed, no `DISPLAY`, and no Qt.

## Reproducing the whole flow

From the repo root, in order:

```bash
# 1. Draw the layout (byte-for-byte deterministic -- git diff stays empty)
uv run --with klayout python3 layout/bandgap_top/generate.py

# 2. Check the drawn geometry against floorplan.md §0's matching plan
uv run --with klayout python3 layout/bandgap_top/matching_report.py

# 3. DRC
python3 layout/drc/run_drc.py layout/bandgap_top/bandgap_top.gds

# 4. Extract + LVS
python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds

# 5. Area budget
uv run --with klayout python3 layout/bandgap_top/area_report.py
```

Expected results (as committed):

| Step | Result |
|---|---|
| `matching_report.py` | all tier-1/2/3 checks pass, exit 0 |
| `run_drc.py` | `status: clean`, `violation_count: 0` |
| `run_lvs.py` | **`lvs status: mismatch`** — see "What the LVS verdict does and does not cover" below; tracked as [#75](https://github.com/2AMLogic/gf180-bandgap/issues/75) |
| `area_report.py` | 48,339.11 µm² vs. 50,000 µm² target — PASS, 3.3 % headroom |

`run_lvs.py`'s `match` verdict (81/81 devices, 23/23 nets) held through #62–#72,
but stopped once `klt`'s gf180mcu deck gained bipolar (klayout-tools#223) and
MiM-capacitor (klayout-tools#225) device recognition upstream — recognition
`layout/lvs/make_reference.py`'s MOS-only reference derivation doesn't model.
[#73](https://github.com/2AMLogic/gf180-bandgap/issues/73) additionally drew
this layout's own resistor-recognition marker geometry (closing a *different*,
`layout/netlist/`-scoped gap — see that directory's README), which makes the
same reference-staleness gap larger (65 more recognised devices) but did not
create it: the `bjt`/MiM-cap portion of the mismatch reproduces against `main`
before #73's changes. See `layout/netlist/README.md`'s "Still blocking"
section and [#75](https://github.com/2AMLogic/gf180-bandgap/issues/75), which
tracks updating `make_reference.py` to model all three newly-recognised
classes.

## How the layout is built

Three modules, layered, with the committed schematic netlist as the single
source of truth at the bottom:

1. **`netlist_model.py`** parses and flattens
   `design/netlist/bandgap_top.spice` into primitive devices with
   hierarchically-resolved net names, in integer nanometres. Nothing
   downstream restates a device size.
2. **`plan.py`** turns that flat netlist into an ordered list of **rows** of
   **items** — the placement plan, including finger splitting, the
   common-centroid finger order of each matched array, and the edge dummy
   devices. `generate.py` and `layout/lvs/make_reference.py` both read this
   one module, so the drawn geometry and the LVS reference cannot disagree
   about how a device was folded or which dummies exist.
3. **`generate.py`** draws the GDS with the `klayout.db` API — the same
   construction pattern the `trivial_poly_res` DRC fixture uses (`klt` has no
   layout-*write* verb; `klt gen` runs named PCell generators, not an
   arbitrary block builder).

Output is deterministic: the GDSII writer's header timestamps are disabled, so
the written file is a pure function of the geometry and re-running step 1
leaves `git diff` empty.

### Matching, and how it is verified

`matching_report.py` is the mechanical form of "open it in KLayout and eyeball
it". It reads the *drawn* x position of every finger back out of the
generator's own placement and checks `floorplan.md` §0's three tiers:

```
AMPPAIR      §0 tier 1 / §6 — amp input pair
  drawn order    : D A B B A A B B A A B B A A B B A D
  centroid spread: 0.000 um (tolerance 2.900 um) -> OK
COREMIRROR   §0 tier 1 / §5 — core mirror M1-M3
  drawn order    : D A B C C B A A B C C B A D
  centroid spread: 0.000 um (tolerance 3.900 um) -> OK
PNP array (§0 tier 3 / §4.1)
  drawn order    : D Q3 Q2 Q2 Q1 Q2 Q2 D
  Q1/Q2 centroid spread 0.00 unit cells -> OK
```

Every tier-1 array (amp input pair, amp mirror load, both amp cascode pairs,
core mirror, core cascode) is drawn as a palindromic interdigitated array with
dummy devices at both edges, and all members share one centroid *exactly*.
Tier 2 is a single `ppolyf_u` unit width across `R1`, `R2` and all 63
trim-ladder segments. Tier 3 is the PNP array; see `plan.py`'s tier-3 note for
why `Q1`/`Q2` is the pair given the exact centroid (two single-unit devices
cannot both have it, and the `Q1`/`Q2` `dVBE` error reaches `vref` with
~12.8× the gain `Q3`'s does).

### Routing style, and why it looks like this

`klt`'s gf180mcu decks model exactly **one** metal level (`Metal1`, 34/0) —
there is no `Metal2`..`Metal5` in either the DRC deck or the extraction
deck's connectivity graph. A block routed on layers the extraction deck
cannot see extracts as a pile of disconnected nets, so this layout is routed
entirely on `Metal1` plus `Poly2`, using poly as the crossunder layer:
per-net vertical Poly2 spines in a corridor down the left edge, one
horizontal Metal1 rail per net per row, and short Poly2 stubs from each device
terminal up to its rail.

That is a correct single-metal discipline, but it is not how this block would
be routed with a real multi-metal stack, and it costs significant area —
quantified in [`bandgap_top/AREA.md`](bandgap_top/AREA.md). Filed upstream:
[`klayout-tools#220`](https://github.com/2AMLogic/klayout-tools/issues/220).

## What the LVS verdict does and does not cover

**Historical note (superseded — kept for context, see below):**
`klt`'s gf180mcu extraction deck originally recognised exactly two device
classes — `nfet` and `pfet` (from `Comp`/`Poly2`/`Nwell`) — and treated
`Poly2` as a plain conductor, with no resistor, bipolar or MIM-capacitor
extractor. `layout/lvs/make_reference.py` derives its reference netlist
mechanically from that premise (its docstring lists the seven
transformations: poly resistors collapse to shorts, `pnp_*` and `cap_mim_*`
drop out, the ideal `RS0..RS5` trim straps resolve at the drawn trim code,
each MOS expands to its drawn finger count, the layout's edge dummies are
added, and body terminals re-target to the nets the deck actually produces).
That gap was filed upstream as
[`klayout-tools#219`](https://github.com/2AMLogic/klayout-tools/issues/219)
(now **closed**) and closed via klayout-tools#222 (resistor)/#223
(bipolar)/#225 (MiM capacitor).

**Current state.** The deck itself now recognises all three classes.
[#73](https://github.com/2AMLogic/gf180-bandgap/issues/73) additionally drew
this layout's own missing resistor/MiM-cap recognition marker geometry
(`RES_MK`/`SAB`/`CAP_MK` — see `layout/netlist/README.md`), so `klt extract`
against this GDS now recognises 65 `ppolyf_u` resistors and 1 MiM capacitor,
in addition to the 16 `bjt` devices it already recognised. **What has *not*
caught up is `make_reference.py` itself** — it still emits a MOS-only
reference (the seven transformations above), so `run_lvs.py`'s comparison
against the now-fuller extracted netlist reports `mismatch`, not because
either side is wrong but because they now model genuinely different device
sets. Tracked as
[#75](https://github.com/2AMLogic/gf180-bandgap/issues/75).

Until #75 lands:

- **Covered**: every MOS device (81 of them, including the 14 edge dummies),
  their W/L, and the full Metal1/Poly2/Contact connectivity between them —
  i.e. the drawn topology of the amplifier, the core mirror/cascode, the
  start-up kick path and every net that joins them. (`klt lvs`'s own device
  match count still confirms this half cleanly: 81/81 devices matched even
  in a `mismatch`-status run, since the mismatch is *additional* recognised
  devices/nets the reference lacks, not a discrepancy in the MOS ones.)
- **Not (yet) compared**: the drawn `ppolyf_u` resistors (`R1`, `R2`, and all
  63 trim units — `startup.RPU` stays a short on both sides even after #75,
  see `layout/netlist/README.md`), the six PNP unit devices, and the
  compensation MIM capacitor — all now *extracted* correctly, but not yet
  *modelled in the reference* to compare against. A resistor drawn at the
  wrong length, or a PNP with its emitter and base swapped, would still not
  be caught by `run_lvs.py` today.

**Limitation carried from klayout-tools:** DRC is whole-layout, flattened per
top cell — there is no `--top <cell>` filter to scope a check to one cell
inside a larger layout (`docs/cli/drc.md` § "Limitation: whole-layout,
flattened"). This layout is a single flat cell, so it does not bite here.

## The gf180mcu DRC deck: coverage

The `gf180mcu` deck (`klayout-tools/src/klayout_tools/decks/gf180mcu.py`) is a
**curated starter subset**, not the full GlobalFoundries 180nm MCU Design Rule
Manual. It covers width/spacing/enclosure rules across `Poly2` (30/0), `Comp`
(22/0), `Contact` (33/0) and `Metal1` (34/0), plus one BJT marker-layer rule.
No well/tap rules, no HV/5V-variant rules, no Metal2–4 rules. A `clean` DRC
verdict from it is therefore a real but partial check — the drawn Nwell,
implant and MIM geometry in this layout is unchecked. See "Friction filed".

## Reports are append-only evidence

`run_drc.py` and `run_lvs.py` write under
`layout/<flow>/reports/<block>/<record-id>.*` and **never overwrite an
existing report** — mirroring the append-only evidence convention
`sim/README.md` documents (`CLAUDE.md`: "`sim/` results are append-only
evidence"; this repo applies the same rule to `layout/` reports). A re-run
mints a new `<record-id>` (`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`) rather than
clobbering the last one.

`layout/lvs/bandgap_top.ref.spice` is the one generated file that *is*
overwritten — `run_lvs.py` regenerates it before every run precisely so a
stale or hand-edited reference can never quietly pass.

## Findings and escalations

CLAUDE.md forbids silently absorbing a gap between the drawn layout and the
schematic. Three were found while drawing and maintaining this block; all
are reported, not patched around:

- **RESOLVED — schematic `nf=1` on 15 devices the layout must finger** —
  [#65](https://github.com/2AMLogic/gf180-bandgap/issues/65). Total `W` and
  `L` were drawn exactly as the schematic specified, but the finger count was
  not, because a single-finger device cannot be interdigitated and
  `floorplan.md` §0 ranks those very devices as the highest matching
  priority. Since `ad`/`as`/`pd` are written as expressions in `nf`, this
  meant every simulated junction capacitance corresponded to a geometry that
  could not be drawn (drain area and perimeter both roughly halve when the
  device is fingered). #65 corrected `nf` in the schematic to match the
  drawn finger counts, re-emitted `design/netlist/`, re-ran the affected
  `sim/` suites, and emptied `bandgap_top/plan.py`'s `LAYOUT_FOLDS` — the
  drawn geometry for those 15 devices is unchanged (total `W`/`L` per device
  was already correct; only which artifact declared the finger count moved).
  The committed GDS also carries #70/#71's independent resistor fold-count
  fix (`core.R1`/`R2` `segments` 14/2 → 28/4), so it is not byte-identical to
  the pre-#65 GDS — that delta is #70/#71's, not #65's; see the third finding
  below.
- **`floorplan.md` §8's area estimate is 1.85× stale, and the drawn block
  lands at 96.7 % of the ratified 0.05 mm² target** — see
  [`bandgap_top/AREA.md`](bandgap_top/AREA.md). The budget *passes*, with
  1,660.89 µm² (3.3 %) of headroom, and is reported as-is rather than
  adjusted. §8's tally predates #56 (telescopic-cascode amp), #60 (core
  mirror/cascode resizing) and #69 (`core.R1`/`R2`/trim `k=2` co-scale).
- **#69's `R1`/`R2` length doubling briefly regressed the drawn area over
  budget; fixed by co-scaling the resistor fold count, not the resistor
  value** — [#70](https://github.com/2AMLogic/gf180-bandgap/issues/70).
  #69 doubled `core.R1`/`R2`'s drawn length to close the `Iq < 50 uA` spec
  row but never regenerated this layout; doing so surfaced a real
  50,897.23 µm² (1.8 % over budget) drawn area, because folding a longer
  resistor into the same fixed leg count inflates leg *height*, and every
  row's height multiplies against the block's full width. The fix
  co-scales `core.R1`'s fold count 14 → 28 and `core.R2`'s 2 → 4 (in step
  with #69's `k=2`), restoring each resistor's leg height to
  approximately its pre-#69 value while spending the extra length on
  width the `RSTRIP` row had to spare. No resistor value changed, so no
  spec row was touched and no PVT re-verification was needed. See
  [`bandgap_top/AREA.md`](bandgap_top/AREA.md) Finding 3 for the full
  numbers.

## Friction filed (klayout-tools tracker)

Per CLAUDE.md's friction protocol, every klayout-tools gap this work
surfaced is tracked generically (tool capability, never this design's
specifics) on the public
[klayout-tools issue tracker](https://github.com/2AMLogic/klayout-tools/issues):

- **Extraction decks recognise MOS only** — no resistor/bipolar/capacitor
  device classes, so an analog block's LVS cannot be a full-device LVS:
  [`#219`](https://github.com/2AMLogic/klayout-tools/issues/219).
- **gf180mcu extraction deck declares one metal level and no vias** — forces
  single-metal routing on any block that wants to LVS, at a real area cost:
  [`#220`](https://github.com/2AMLogic/klayout-tools/issues/220).
- **`gf180mcu` deck coverage gap (well/tap, BJT-specific rules)** —
  [`#157`](https://github.com/2AMLogic/klayout-tools/issues/157), filed from
  the #15 DRC bring-up.
- **Missing `klt lvs` / extraction capability** — the original gap
  ([`#54`](https://github.com/2AMLogic/klayout-tools/issues/54), superseded
  by epic [`#153`](https://github.com/2AMLogic/klayout-tools/issues/153)) —
  **resolved upstream**, and this block's layout is the consumer that closed
  the loop on it.

## The `trivial_poly_res` DRC fixture (#15)

The DRC bring-up fixture predating this layout is kept as the deck's
regression proof: a single `Poly2` resistor with two `Contact`-and-`Metal1`
terminals and **one seeded rule violation** (the body is drawn 100 dbu wide,
under `poly2.width.1`'s 180 dbu minimum), so the report proves the deck
catches a real violation without drowning it in incidental ones.

```bash
# Regenerate the fixture and confirm it matches the committed GDS
uv run --with klayout python3 layout/drc/fixtures/trivial_poly_res/generate.py
git diff --stat layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds   # empty

# Re-run DRC and confirm the same single violation reproduces
python3 layout/drc/run_drc.py layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds
# -> status: violations, violation_count: 1, rule_counts: {"poly2.width.1": 1}
```
