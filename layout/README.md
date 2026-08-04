# layout — `bandgap_top` GDS, DRC and LVS (klayout-tools)

Layout work for this repo is driven by
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`), per
`CLAUDE.md`. This directory holds **the block layout itself** plus the DRC and
LVS flows that verify it.

`layout/bandgap_top/` is a real, drawn physical layout of the whole block
(`bandgap_core` + `bandgap_amp` + `bandgap_startup` + trim ladder), generated
from the committed schematic netlist and **LVS-matching** against its
mechanically-derived reference netlist across all device classes `klt
extract` recognises — 81 MOS, 65 `ppolyf_u` + 1 `ppolyf_u_1k` resistors, 8
`bjt` and 1 MIM capacitor. **DRC is clean against the current deck**
(`status: clean`, `violation_count: 0`) — the `fb` top-plate routing tab that
used to draw `mim.enclosing.fusetop.1`
([#82](https://github.com/2AMLogic/gf180-bandgap/issues/82)) is gone:
[#88](https://github.com/2AMLogic/gf180-bandgap/issues/88) redrew that
contact as a DRM-legal `Via4` landing directly inside the recognised top
plate once klayout-tools#364/PR #368 made that possible without `klt
extract` reading it as a `vdd`/`fb` short; see "Findings and escalations"
below. What the LVS verdict does and does not prove is spelled out in "What
the LVS verdict does and does not cover" below.

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
    run_lvs.py         klt extract + klt lvs -> committed report (--engine selects the comparator)
    test_run_lvs.py    unit tests for run_lvs.py's engine selection (no klt/netgen needed)
    bandgap_top.ref.spice  generated reference netlist (do not hand-edit)
    reports/bandgap_top/   <record-id>.{extract.json,extracted.spice,lvs.json,lvs.txt,lvs-request.json}
                           plus <record-id>.lvs-netgen.{json,txt} + .lvs-netgen-request.json
                           from the optional netgen cross-check (--engine netgen/both)
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

# 4b. (optional) same run, cross-checked by a second, independent comparator.
#     Needs the `netgen` binary on PATH; see "The netgen cross-check" below.
python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds --engine both

# 5. Area budget
uv run --with klayout python3 layout/bandgap_top/area_report.py
```

Expected results (as committed):

| Step | Result |
|---|---|
| `matching_report.py` | all tier-1/2/3 checks pass, exit 0 |
| `run_drc.py` | `status: clean`, `violation_count: 0` (`20260803-054725-8d21bf1.drc.json` — first clean verdict since klayout-tools#318 stopped false-negativing `mim.enclosing.fusetop.1`; see #88) |
| `run_lvs.py` | `status: match`, 156/156 devices, 92/92 nets (`20260803-054735-8d21bf1.lvs.json`; reproduced unchanged by `20260804-143026-c876a0f.lvs.json` and `20260804-151012-fefb292.lvs.json`) |
| `run_lvs.py --engine both` | klayout `match`, 14 mismatches; netgen `match`, 2 mismatches — **both engines agree** (`20260804-151012-fefb292.lvs-netgen.json`) — see "The netgen cross-check" below |
| `area_report.py` | 48,805.68 µm² vs. 50,000 µm² target — PASS, 2.4 % headroom |

`net_count` is 92, not 93, because gf180-bandgap#88 redrew the MiM cap's `fb`
up-hop contact to land inside the recognised top plate — the top plate no
longer extracts as its own isolated net, so it no longer contributes a
distinct entry to the net count (see "Findings and escalations" below).

**RESOLVED — `run_lvs.py`'s `match` result went stale between commits,
independent of any code change here** ([#89](https://github.com/2AMLogic/gf180-bandgap/issues/89)).
The installed `klt` picked up
[`klayout-tools#329`](https://github.com/2AMLogic/klayout-tools/pull/329)
(merged 2026-08-02), which ties a recognised MiM capacitor's plates into the
deck's ordinary `metals[]` connectivity when their plate/via-landing layers
are among the deck's tracked metals, instead of leaving them as isolated
nodes. `layout/lvs/make_reference.py` still modelled both `amp.CC` plates as
synthesized floating nets — the pre-#329 assumption — so the comparison
mismatched (18 mismatches, all on `amp.CC`/`vdd`/`fb` and
structurally-resolved `topology` warnings — 0 mismatches involving any
resistor). Verified directly against the installed `klt` (deck content hash
`sha256:be1a89e0…872b1d`) rather than assumed from the upstream PR
description: a real `klt extract` of the committed GDS reports the bottom
plate (`Metal4`) resolved onto the real `vdd` net (`C$90 vdd $16 …`), while
the top plate (`FuseTop`) stays its own isolated net — its `Via4` up-hop
lands on the `fb` routing tab drawn outside `CAP_MK`/`MIM_L_MK` (#82), which
the deck's top-plate connectivity wiring never sees touch the recognised top
plate. `make_reference.py` now models the bottom plate on the cap's real net
(`vdd` here) and leaves the top plate as its own floating net, matching that
verified behaviour — `status: match` again, 156/156 devices, 93/93 nets
(`20260803-010614-44fde28.lvs.json`). The drawn GDS did not change
(`sha256:736d4a63…ad5cdf0`, unchanged; `generate.py`/`plan.py`'s docstring
updates carry no geometry) — only the reference-netlist derivation moved.
`20260803-002521-dbcd5ab.lvs.json` remains committed as the "before" evidence
of the regression this resolves.

`run_lvs.py`'s 156 compared devices are 34 `nfet` + 47 `pfet` (81 MOS,
including the 14 edge dummies), 65 `ppolyf_u` + 1 `ppolyf_u_1k` resistors, 8
`bjt` and 1 `cap_mim_2f0_m4m5_noshield`. That is up from the 81 MOS-only
devices #62–#72 compared: the deck gained bipolar (klayout-tools#223),
MiM-capacitor (klayout-tools#225) and resistor (klayout-tools#222)
recognition upstream, [#73](https://github.com/2AMLogic/gf180-bandgap/issues/73)
drew this layout's own `RES_MK`/`SAB`/`CAP_MK` marker geometry so the last
two fire against it, [#75](https://github.com/2AMLogic/gf180-bandgap/issues/75)
taught `make_reference.py` to model all three classes (it briefly reported
`mismatch` in between, purely from the reference being MOS-only), and
[#78](https://github.com/2AMLogic/gf180-bandgap/issues/78) took up the deck's
new `ppolyf_u_1k` entry so `startup.RPU` extracts as a real resistor instead
of a short.

Of the current 14 mismatches, all are `warning`-severity and not defects: two
`device.body_unverified` entries are the deck's standing "no substrate/well
tap layer" caveat (see below), and 12 `topology` entries are ambiguous net
pairings the comparer resolved structurally — the six per-unit PNP Nwell
nets and the symmetric interior nodes of the strapped-out trim loops. There
are no `error`-severity mismatches. `status` is `NetlistComparer`'s own
boolean verdict, which `klt lvs` never re-derives from the mismatch list.

The MiM cap's **top** plate now resolves to the real `fb` net directly
([#88](https://github.com/2AMLogic/gf180-bandgap/issues/88) — its `Via4`
lands inside the recognised top plate, no longer on the `FuseTop` tab #82
tracked), so `klt lvs`'s `match` verdict itself is the proof, the same as
for the bottom plate. `layout/netlist/verify_mim_routing.py`
([#17](https://github.com/2AMLogic/gf180-bandgap/issues/17)) is kept as a
cheap regression guard rather than the primary proof it used to be.

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

`klt`'s gf180mcu **extraction** deck used to model exactly **one** metal
level (`Metal1`, 34/0) — no `Metal2`..`Metal5`, so a block routed above
Metal1 extracted as a pile of disconnected nets. That constraint is why this
layout is routed entirely on `Metal1` plus `Poly2`, using poly as the
crossunder layer: per-net vertical Poly2 spines in a corridor down the left
edge, one horizontal Metal1 rail per net per row, and short Poly2 stubs from
each device terminal up to its rail. The extraction deck has since gained the
full Metal1–Metal5 stack with vias
([`klayout-tools#220`](https://github.com/2AMLogic/klayout-tools/issues/220)),
which is what lets the one exception below exist at all.

That is a correct single-metal discipline, but it is not how this block would
be routed with a real multi-metal stack, and it costs significant area —
quantified in [`bandgap_top/AREA.md`](bandgap_top/AREA.md).

**Corrected claim (was stale, gf180-bandgap#82):** the separate **DRC**
deck was never Metal1-only, and is even less so today — since
[`klayout-tools#188`](https://github.com/2AMLogic/klayout-tools/issues/188)
it also carries `metal2`/`metal3`/`metal5`.width|space, `metaltop`.* and
`mim.space.1`/`mim.enclosing.fusetop.1` rules; see "The gf180mcu DRC deck:
coverage" below for the current, non-stale list. **Above Metal1** the only
rule-free layers are the four vias (`Via1`..`Via4`, 35/0/38/0/40/0/41/0) —
everything else drawn above Metal1, including `Metal4`/`FuseTop`, is
checked. (Taken over the whole stream the rule-free set is larger — twelve
layers, including the implant and device-marker layers; the coverage section
below enumerates them from the report itself.)

**One exception**: the compensation MIM capacitor's `Metal4`/`FuseTop` plates
are wired down to the Metal1 `vdd`/`fb` rails through a real `Via1`..`Via4`
stack ([#77](https://github.com/2AMLogic/gf180-bandgap/issues/77), redrawn
by [#88](https://github.com/2AMLogic/gf180-bandgap/issues/88)) — this
layout's only use of `Metal2`..`Metal5`. See `generate._mim_cap`'s own
docstring for the shape of that stack: both plates' up-hop vias now land
*inside* their own recognised plate's footprint (the bottom plate's inside
the Metal4 box it itself draws; the top plate's `Via4` inside the recognised
`FuseTop & CAP_MK & MIM_L_MK` region, well inside the Metal4 bottom-plate
footprint per `MIMTM.2`), and a standalone landing pad carries the `fb`
down-hop clear of the bottom plate. **Both contacts are now DRM-legal** —
see "Findings and escalations" below (#82, #88) for the history of the
top-plate contact, which was not always true of this geometry.

## What the LVS verdict does and does not cover

**Historical note (superseded — kept for context, see below):**
`klt`'s gf180mcu extraction deck originally recognised exactly two device
classes — `nfet` and `pfet` (from `Comp`/`Poly2`/`Nwell`) — and treated
`Poly2` as a plain conductor, with no resistor, bipolar or MIM-capacitor
extractor. That gap was filed upstream as
[`klayout-tools#219`](https://github.com/2AMLogic/klayout-tools/issues/219)
(now **closed**) and closed via klayout-tools#222 (resistor)/#223
(bipolar)/#225 (MiM capacitor). `layout/lvs/make_reference.py` used to derive
its reference from that MOS-only premise; #73 (marker geometry) and #75
(reference) between them retired it.

**Current state.** All recognised device classes are compared, including
both poly-resistor sheet-rho flavours. `make_reference.py`'s docstring lists
the nine mechanical transformations it applies to get from
`design/netlist/bandgap_top.spice` to the reference — MOS finger expansion,
the layout's edge dummies, body-terminal re-targeting, one resistor card per
drawn `ppolyf_u` body, one `ppolyf_u_1k` card for `startup.RPU`, trim-strap
resolution at the drawn code, one bipolar card per drawn PNP unit, and the
MIM cap's bottom and top plates on their real nets
([#88](https://github.com/2AMLogic/gf180-bandgap/issues/88) retired the last
synthesized/floating plate net). Every one of them is a consequence of the
extraction deck's own capabilities or of how this layout draws the device;
none is a design simplification, and nothing in the reference is hand-written.

- **Covered**: every MOS device (81, including the 14 edge dummies) and its
  W/L; every drawn `ppolyf_u` resistor body (`core.R1`, `core.R2` and all 63
  trim units) and its extracted `R`; the drawn `ppolyf_u_1k` body
  (`startup.RPU`) and its extracted `R`; all 8 recognised `bjt` devices (one
  per drawn PNP unit, klayout-tools#304) and their `AE`; the MIM capacitor and
  its `C`; **both** the MIM cap's bottom-plate connection to `vdd`
  (klayout-tools#329, gf180-bandgap#89) and its top-plate connection to `fb`
  (klayout-tools#364/PR #368, gf180-bandgap#88); and the full
  Metal1/Poly2/Contact connectivity joining everything else — i.e. the drawn
  topology of the amplifier, the core mirror/cascode, the PNP array, the
  resistor strip, the trim ladder with its drawn metal strap option, and the
  start-up kick path. A resistor drawn at the wrong length or fold count, a
  PNP with its emitter and base swapped, a trim strap landing on the wrong
  ladder node, or the MIM cap's either plate wired to the wrong rail all now
  fail this check.
- **Not covered** (each a tool-capability limit, each stated at its source):
  - **Device body/well terminals.** The deck draws no substrate- or
    well-tap layer, so every NMOS body compares against the synthesised
    `vsubs` global and every PMOS body against one anonymous well net —
    `klt lvs`'s own two `device.body_unverified` warnings.
  - **RESOLVED — the MIM capacitor's top-plate net**
    ([#88](https://github.com/2AMLogic/gf180-bandgap/issues/88)). Until #88,
    klayout-tools#329's plate-to-`metals[]` join (see "Covered" above,
    gf180-bandgap#89) only reached the bottom plate: the top plate's `Via4`
    up-hop landed on a routing tab drawn outside `CAP_MK`/`MIM_L_MK`
    specifically to avoid a DRM-legal on-plate via being misread as a
    `vdd`/`fb` short (klayout-tools#364), so the deck's top-plate
    connectivity wiring never saw that via touch the *recognised* top plate
    and it extracted as its own floating net regardless of how the layout
    routed it — a wiring mistake there would have passed `klt lvs` silently.
    As gf180-bandgap#82 found for that exact geometry, the tab also used to
    pass `klt drc`, not because DRC does not check the layers involved (it
    does, see "The gf180mcu DRC deck: coverage" below) but because of an
    `enclosing_check` false negative on a shape drawn entirely outside the
    enclosing layer
    ([klayout-tools#318](https://github.com/2AMLogic/klayout-tools/issues/318),
    checked by inspection at review time instead) — resolved upstream by
    klayout-tools#327 (2026-08-02), after which the deck genuinely reported
    `mim.enclosing.fusetop.1` on the tab. **klayout-tools#364/PR #368 then
    fixed the connectivity-graph gap itself**, and #88 redrew the contact
    against it: the `fb` up-hop `Via4` now lands directly inside the
    recognised top plate, `klt extract` resolves it to the real `fb` net,
    and `klt lvs` compares the top-plate connection the same way it already
    compared the bottom-plate one — no blind spot remains on either plate.
  - **Resistor and bipolar *values* versus the schematic.** The comparison
    is layout-vs-layout-prediction for these: the reference predicts the
    `R`/`AE PE AB PB AC PC` the extractor will measure off the drawn marker
    geometry (`plan.res_body_area_nm2`, `plan.pnp_emitter_area_nm2` and,
    since gf180-bandgap#111, `plan.pnp_emitter_perimeter_nm` /
    `plan.pnp_base_area_nm2` / `plan.pnp_base_perimeter_nm`), because
    KLayout's own extractors report a serpentine's `R` from an
    area/perimeter fit that does not equal `sheet_rho · r_length/r_width`
    (corner squares are shared). So a *drawn* geometry error is caught; a
    disagreement between KLayout's serpentine model and the PDK's own
    `ppolyf_u` subcircuit is not — see `layout/netlist/README.md`'s "Known
    additional fidelity gaps".

### The netgen cross-check (`--engine both`)

`klt lvs` ships two comparators (klayout-tools#343/#360), and `run_lvs.py`
can drive either or both:

```bash
python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds              # klayout only (default)
python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds --engine netgen
python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds --engine both
```

The default is unchanged: `--engine klayout` writes exactly the
`<record-id>.lvs.{json,txt}` + `.lvs-request.json` series it always has, with
a request document byte-identical to the pre-`--engine` ones. `netgen` writes
its own `<record-id>.lvs-netgen.*` series alongside, so the two engines can
never overwrite each other and the trail stays append-only. `netgen` is
**opt-in** because it needs the `RTimothyEdwards/netgen` binary on `$PATH`
(not bundled, not pip-installable); asking for it without that binary is an
actionable `klt lvs` error and a non-zero exit, never a silent fall back to
the klayout engine.

**What the second engine is worth: comparator independence, not extraction
independence.** netgen has no layout front-end here — both engines compare
the *same* `klt extract` output — so a bug in extraction is invisible to
both. What it independently exercises is the graph-matching step, in a
separate codebase (`netgen -batch lvs` vs. `klayout.db.NetlistComparer`).

**First cross-checked run (`20260804-143026-c876a0f`, netgen 1.5.323): the
two engines DISAGREED, and the disagreement was entirely device-parameter and
pin-matching, not topological.**

| | klayout | netgen |
|---|---|---|
| `status` | `match` | `mismatch` |
| `mismatch_count` | 14 | 25 |
| categories | 2 `device.body_unverified`, 12 `topology` | 2 `device.body_unverified`, 22 `device.property`, 1 `pin.unmatched` |
| nets / devices | 92/92, 156/156 | layout 92 vs reference 92, layout 156 vs reference 156 |

netgen reported **zero** unmatched nets and **zero** unmatched devices, and
both engines saw the same 92 nets and 156 devices on each side. Its 22
`device.property` entries all landed on the 8 `bjt` devices, and its 1
`pin.unmatched` entry traced to two gaps in the reference generator, not the
drawn layout:

- `klt extract` emits six junction parameters per PNP
  (`AE PE AB PB AC PC`), but `make_reference.py` modelled only `AE` — so
  `PE`/`AB`/`PB`/`AC`/`PC` read as `0` on the reference side. The `AE` values
  themselves agreed (`2.5e-11` both sides). KLayout's deck-driven comparer
  ignores the unmodelled five; netgen, comparing parameters with no
  PDK-specific tolerance rules, did not.
- The two `M` deltas (layout `2`/`4` vs. reference `1`) were the same gap
  downstream: netgen folded layout-side parallel PNP units into `M=2`/`M=4`
  groups and paired them against single-unit reference cards.
- The single `pin.unmatched` was the top-level pin-count asymmetry **both**
  engines saw — the reference declared five pins
  (`.SUBCKT bandgap_top vdd vss vref vsubs nwl`) and extraction yielded four.
  KLayout's comparer tolerated it (`counts.pins`: layout 4, reference 5,
  matched 5); netgen called it a top-level pin-matching failure.

**RESOLVED** ([#111](https://github.com/2AMLogic/gf180-bandgap/issues/111)):
both gaps were in `make_reference.py`, not the drawn layout, and both are
mechanical consequences of drawn geometry already available in `plan.py` —
so the fix is Option 1 (model the missing BJT parameters) *and* Option 2
(reconcile the pin count) from that issue's suggested scope, not Option 3
(accept the delta). Rationale for choosing 1+2 over 3: netgen's stricter
parameter comparator is a legitimate second reading of the same `klt
extract` output — accepting a self-inflicted 25-entry delta indefinitely
would make every future genuinely-new netgen mismatch (an actual
regression) harder to see against a permanently-noisy baseline, which cuts
against CLAUDE.md's "verification is the product." Both gaps closed without
touching drawn geometry (the GDS is byte-identical, `sha256:17e27435…`,
before and after):

- `plan.py` gained `pnp_emitter_perimeter_nm` (`PE = 4 * emitter_side`) and
  `pnp_base_nwell_side_nm`/`pnp_base_area_nm2`/`pnp_base_perimeter_nm`,
  which derive `AB`/`PB` from the side length of the drawn Nwell island
  already computed by `pnp_size` (`base_outer + 2*PNP_NW_ENC` —
  `generate.draw_pnp`'s own `nwell` local uses the identical expression).
  `make_reference.py` now emits all six parameters per `bjt` card, with
  `AC`/`PC` set equal to `AB`/`PB`. That duplication is not a
  simplification: verified against `klt extract`'s real output
  (`20260804-143026-c876a0f.extracted.spice`), every drawn unit reports
  `AC`/`PC` numerically identical to `AB`/`PB` — the deck's vertical-BJT
  extractor has no drawn collector-region shape to measure separately (the
  collector is the undrawn substrate beneath the whole cell), so it reports
  the same enclosing-Nwell geometry for both junctions. This is the same
  layout-vs-layout-prediction relationship already noted for `AE` (see
  "Resistor and bipolar *values* versus the schematic" above) — the
  reference predicts what the extractor measures off the drawn geometry,
  not the schematic's own BJT model, and that was already true of `AE`
  before this change.
- `make_reference.py`'s pin list no longer appends `nwl` unconditionally.
  The comment immediately above that code already documented why: only
  `vdd`/`vss`/`vref` carry a Metal1 label in the layout (plus the
  deck-synthesized `vsubs`), so those four are the only nets the deck ever
  promotes to a top-level pin — `nwl` (the PMOS band's Nwell) never gets
  one, because the deck never connects Nwell to Contact. The reference
  simply hadn't been updated to match its own documented pin set.

Fresh evidence (`20260804-151012-fefb292`, same `netgen 1.5.323`, GDS
unchanged): **netgen mismatch count 25 → 2, status `mismatch` → `match`.**
The `22 device.property` and `1 pin.unmatched` categories are gone
entirely; the remaining 2 are `device.body_unverified` — the same
standing "no substrate/well-tap layer" caveat klayout already carries (and
carried before this change too), unrelated to this issue, not silently
re-labelled to make a count look better. Both engines now agree the layout
matches its reference.

| | klayout | netgen |
|---|---|---|
| `status` | `match` | `match` |
| `mismatch_count` | 14 | 2 |
| categories | 2 `device.body_unverified`, 12 `topology` | 2 `device.body_unverified` |
| nets / devices / pins | 92/92, 156/156, 4/4 | 92/92, 156/156, 4/4 |

`options.netgen_setup` (a PDK-specific netgen setup `.tcl`, resolvable via
`klayout_tools.pdk.netgen_setup_file()`) is deliberately **not** wired in:
an uncommitted one-off probe pointing netgen at the installed
`gf180mcuA_setup.tcl` raised the count to 43 `device.property`-dominated
entries rather than reducing it, and the resolved path is machine-specific,
which would break the request documents' machine-independence. netgen's own
default setup is still topologically correct, which is the part this
cross-check is for.

**Limitation carried from klayout-tools:** DRC is whole-layout, flattened per
top cell — there is no `--top <cell>` filter to scope a check to one cell
inside a larger layout (`docs/cli/drc.md` § "Limitation: whole-layout,
flattened"). This layout is a single flat cell, so it does not bite here.

## The gf180mcu DRC deck: coverage

The `gf180mcu` deck (`klayout-tools/src/klayout_tools/decks/gf180mcu.py`) is a
**curated starter subset**, not the full GlobalFoundries 180nm MCU Design Rule
Manual. **Corrected claim (was stale, gf180-bandgap#82):** since
[`klayout-tools#188`](https://github.com/2AMLogic/klayout-tools/issues/188) it
covers width/spacing/enclosure rules across `Poly2` (30/0), `Comp` (22/0),
`Contact` (33/0), `Metal1` (34/0), `Metal2` (36/0), `Metal3` (42/0), `Metal5`
(81/0) and the `MetalTop` thickness variant (`metaltop.width.1`/
`metaltop.space.1` — carried by the deck, but *skipped* on this layout, see
below), plus `Nwell` (21/0) space/enclosure-of-`Comp` rules, one
BJT marker-layer separation rule, and a MiM-capacitor pair
(`mim.space.1`/`mim.enclosing.fusetop.1`, both scoped to `Metal4` (46/0) as
the bottom plate and `FuseTop` (75/0) as the top plate). There is no
dedicated `Metal4` width/space rule (`Metal4` only appears inside those MiM
rules), no HV/5V-variant rules, and no tap-specific rule beyond the `Nwell`
pair above.

**What this run actually checked**, straight out of the committed report
(`20260802-215251-59c294c.drc.json`, `coverage.*`) rather than from memory:

- `coverage.layers_checked` — `21/0, 22/0, 30/0, 33/0, 34/0, 36/0, 42/0,
  46/0, 75/0, 81/0, 127/5`. So above Metal1, `Metal2`/`Metal3`/`Metal4`/
  `FuseTop`/`Metal5` all carry rules and are checked.
- `coverage.rules_skipped` — `metaltop.width.1` and `metaltop.space.1`. The
  deck *carries* the `MetalTop` pair, but this layout draws nothing on 53/0,
  so neither rule ran here: deck contents and this-run coverage are not the
  same thing.
- `coverage.layers_in_stream_without_rules` — **twelve** drawn layers have no
  rule at all: `31/0` (`Pplus`), `32/0` (`Nplus`), `34/10` (the `Metal1`
  label layer), `35/0`/`38/0`/`40/0`/`41/0` (`Via1`..`Via4`), `49/0` (`SAB`),
  `62/0` (`RESISTOR_MK`), `110/5` (`RES_MK`), `117/5` (`CAP_MK`) and `117/10`
  (`MIM_MK`). Only four of the twelve are vias; the drawn **implant** and
  **device-recognition marker** geometry is entirely unchecked — including
  `CAP_MK`/`MIM_MK` (see "Findings and escalations"; before
  [#88](https://github.com/2AMLogic/gf180-bandgap/issues/88) these markers'
  clipping was also what let the now-removed `fb` top-plate routing tab
  stay outside the recognised plate — see that section's `#82`/`#88` entries
  for the history).

So the accurate scoped statement is: *above* Metal1 the only rule-free layers
are the four vias, but taken over the whole stream twelve layers are rule-free.
Even a `clean` DRC verdict from this deck would therefore be a real but
partial check. See "Friction filed".

**Historical note (superseded by klayout-tools#327 and gf180-bandgap#88,
kept for context).** Until 2026-08-02, `mim.enclosing.fusetop.1`'s
`Region.enclosing_check` check reported nothing when a shape lay *entirely*
outside the enclosing layer rather than flagging the under-enclosure — a
false negative, not a passing check. That let this layout's `fb` top-plate
tab pass `klt drc` with a `clean` verdict despite genuinely violating the
rule; see "Findings and escalations" below (gf180-bandgap#82) for the
geometry that hit exactly this case, and
[`klayout-tools#318`](https://github.com/2AMLogic/klayout-tools/issues/318)
for the upstream report. **Then:** `klayout-tools#318` was resolved
(klayout-tools#327), and the deck correctly reported this layout's
`mim.enclosing.fusetop.1` violation — the committed
`20260802-215251-59c294c.drc.json` above is `status: violations`,
`violation_count: 1`, not `clean`. **Current state:** gf180-bandgap#88
redrew the `fb` up-hop contact as a DRM-legal `Via4` landing inside the
recognised top plate, so the tab this rule was firing on is gone; `klt drc`
now reports `status: clean`, `violation_count: 0` (see the summary at the
top of this file and "Findings and escalations" below).

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
stale or hand-edited reference can never quietly pass. That guard covers
*hand-editing*; it does not, by itself, catch a reference whose generator has
gone stale against a newer extraction deck — exactly what happened between
klayout-tools#304 (resolved 2026-08-02) and this repo's reference emitting a
now-nonexistent artefact `bjt` card, until
[#84](https://github.com/2AMLogic/gf180-bandgap/issues/84) regenerated it
against the current deck (see "Findings and escalations").

**The determinism contract covers the GDS, not the extracted netlist.**
`generate.py`'s output is a pure function of the geometry (`git diff` stays
empty across re-runs). `klt extract`'s is not guaranteed to be, at least not
observably: two runs on byte-identical GDS, the same deck content hash and
the same KLayout 0.30.10 once produced `.extracted.spice` files differing on
exactly one line — the MiM cap's two terminals written in opposite order
(`\$16 \$17 …` vs. `\$17 \$16 …`), with the capacitance value bit-identical.
That was recorded as an **observation, not a tested claim**: seen once,
across the two committed records `20260802-202601-302dc67` and
`20260802-210739-392b549`. gf180-bandgap#84 attempted to reproduce it
deliberately against the current deck — five consecutive `klt extract` runs
on the same GDS produced byte-identical `.extracted.spice` output every time
— so the nondeterminism did **not** reproduce in that attempt. The original
observation stands unexplained (not retracted), but with a 0/5 reproduction
rate on top of the original single sighting, there is not yet a confirmed,
generically-describable tool gap to file upstream per CLAUDE.md's friction
protocol. Do not treat a byte-level diff of two `.extracted.spice` records as
a geometry-changed signal on its own.

## Findings and escalations

CLAUDE.md forbids silently absorbing a gap between the drawn layout and the
schematic. Seven were found while drawing and maintaining this block; all
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
- **RESOLVED — the drawn trim strap was not the strap the schematic
  specifies** — [#75](https://github.com/2AMLogic/gf180-bandgap/issues/75).
  `draw_trim` drew *one* Metal1 strap across the whole strapped group
  (ladder chain node 0 to node 31). `design/bandgap_trim.sch` specifies six
  binary-weighted straps, of which `S0..S4` are closed at
  `DRAWN_TRIM_CODE = 32` — shorting nodes 0, 1, 3, 7, 15 and 31 *together*.
  The two are electrically identical (both leave 32 units in series to
  `vref`) but are different networks: the drawn version left nodes 1/3/7/15
  as interior nodes of one 31-unit loop, where the schematic has a
  self-loop plus 2-, 4-, 8- and 16-unit loops on one node. It was invisible
  while every resistor extracted as a short, and surfaced the moment #73's
  markers made the ladder a real 63-device network. `plan.trim_strap_spans`
  now derives the drawn straps from the schematic's own `RS*` expressions
  at the drawn code, so `generate.py` draws one strap per closed bit and the
  reference does not have to be told about a layout shortcut.
- **RESOLVED — the compensation MIM capacitor was drawn but not wired** —
  [#77](https://github.com/2AMLogic/gf180-bandgap/issues/77). `_mim_cap`
  used to stack `amp.CC` over the device field on Metal4/FuseTop/Metal5 with
  no via stack down to the Metal1 routing, on the (then-true) premise that
  those layers were invisible to both `klt` decks. Once the extraction deck
  gained the full Metal1–Metal5 stack (klayout-tools#220) and this layout's
  own `CAP_MK` marker (#73) made `klt extract` recognise the cap as a real
  device, that premise no longer held — the cap extracted as a device with
  two floating plates instead of a cap physically between `vdd` and `fb`.
  #77 wired both plates for real: a `Via1`..`Via4` stack ties the Metal4
  bottom plate to the `vdd` rail and, via a routing tab off the FuseTop top
  plate (kept outside the `CAP_MK`/`MIM_L_MK` recognition markers so the
  extracted capacitance is unaffected) and a standalone landing pad for the
  down-hop, the top plate to the `fb` rail — both piggy-backing on the
  already-drawn rails in the `AMPPCASC` row the cap's footprint stacks over.
  At the time, `klt extract` could not confirm either connection (see "What
  the LVS verdict does and does not cover"), so the reference modelled both
  plates as floating; the routing itself was checked by inspection, not by
  `klt drc`/`klt lvs` passing. **Update (gf180-bandgap#89):** klayout-tools#329
  (merged 2026-08-02) taught the deck to confirm the bottom-plate connection
  — the reference now models the bottom plate on its real net (`vdd`) and
  verified that against a real `klt extract` run rather than assuming it.
  The top-plate connection is still not confirmed, because its via lands on
  the routing tab kept outside `CAP_MK`/`MIM_L_MK` (see the next bullet), so
  the reference still models the top plate as floating.
- **The `fb` top-plate routing tab #77 drew is not manufacturable, and
  `klt drc`'s `clean` verdict on it is a false negative** —
  [#82](https://github.com/2AMLogic/gf180-bandgap/issues/82), filed against
  the geometry #77 landed on `main` (the review that would have caught it
  auto-merged before the changes-requested verdict could block it — see #82
  for the trace). Measured out of the drawn GDS: the FuseTop routing tab
  extends 0.8um past the Metal4 bottom plate's own edge with **zero**
  bottom-plate overlap there — versus `MIMTM.3`'s 0.6um minimum
  (`mim.enclosing.fusetop.1`, which `MIM_PLATE_INSET` honours on the other
  three edges of the same box) — and the `fb` up-hop `Via4` landing on that
  tab has **zero** `Metal4` overlap, versus `MIMTM.2`'s 0.4um minimum
  (`MIMTM.2` is not transcribed into the deck at all, so this half has no
  rule to even false-negative on). `_mim_cap`'s docstring previously called
  the tab "the standard MiM-cap top-plate routing technique, not a
  workaround specific to this tool"; that was wrong — `MIMTM.2`'s own text
  says a real top-plate contact is a `Via4` landing *inside* the
  bottom-plate footprint, relying on the MiM dielectric (which `klt
  extract`'s connectivity graph does not model) to keep it from shorting to
  `Metal4`. #82 corrected that claim (and the "DRC deck models only Metal1"
  claim above it, which had made the tab look free of consequence) rather
  than re-drawing the geometry: the `vdd` half of #77's via stack, the
  down-hop `Metal4` pad, the marker clipping that keeps the recognised top
  plate — and its extracted `C` — bit-identical, and the `Metal5` wire all
  remain exactly as #77 drew and independently re-verified them; only the
  `fb` up-hop tab/via is affected, and it is affected in documentation only.
  The tab is real copper and genuinely not manufacturable as drawn; revisit
  once
  [klayout-tools#314](https://github.com/2AMLogic/klayout-tools/issues/314)
  (plate nets joined to the connectivity stack) makes it possible to draw
  the DRM-legal contact without `klt extract` reading it as a `vdd`/`fb`
  short, at which point the `fb` half of #77 can be re-drawn for real.
  **Update (gf180-bandgap#84):** the false-negative half of this finding is
  now stale — klayout-tools#327 (2026-08-02) closed klayout-tools#318, and
  the current deck genuinely reports `mim.enclosing.fusetop.1` on this exact
  tab (`20260802-215251-59c294c.drc.json`: `status: violations`,
  `violation_count: 1`) instead of false-negativing it. The tab is still real
  copper and still not manufacturable as drawn — only DRC's ability to catch
  it changed, and this PR intentionally leaves the geometry untouched (still
  gated on klayout-tools#314, as above) so the violation is now visible in
  the committed evidence rather than re-drawn around.
  **RESOLVED (gf180-bandgap#88):** the gate this finding named,
  klayout-tools#314, shipped but turned out to have its own follow-on gap —
  a DRM-legal top-plate `Via4` (one landing inside the bottom-plate
  footprint, exactly what `MIMTM.2` requires) still read as a `vdd`/`fb`
  short, filed as
  [klayout-tools#364](https://github.com/2AMLogic/klayout-tools/issues/364)
  and fixed by
  [PR #368](https://github.com/2AMLogic/klayout-tools/pull/368) (excludes a
  capacitor's own `top_plate_via`/`bottom_plate` overlap from the deck's
  generic per-layer connectivity loop). #88 re-verified that fix directly
  (a minimal repro: a `Via4` landing inside both a capacitor's declared
  `top_plate`/`bottom_plate` footprints extracts `net_count == 2`, not `1`)
  before redrawing this contact against it: the tab, the `Metal5` wire that
  routed around the bottom plate, and the standalone down-hop pad are gone;
  the `fb` up-hop `Via4` now lands directly on the recognised top plate,
  well inside the `Metal4` bottom-plate footprint (see `generate._mim_cap`'s
  asserts for the exact margins against `MIMTM.2`). `klt drc` now reports
  `status: clean`, `violation_count: 0` — the first clean verdict on this
  GDS since klayout-tools#318 stopped false-negativing the rule — and the
  top plate extracts on the real `fb` net with no marker widening, so
  `mk_extracted_dut.py`'s `BA4` back-annotation is deleted.
- **RESOLVED — the committed DRC/LVS evidence was produced against a
  *pinned* deck, and the LVS reference netlist was stale against the current
  one** — [#84](https://github.com/2AMLogic/gf180-bandgap/issues/84). The
  evidence records added by
  [#82](https://github.com/2AMLogic/gf180-bandgap/issues/82)
  (`20260802-210735-392b549.drc.json`, `20260802-210739-392b549.lvs.json`)
  were deliberately generated with `gf180mcu.py` at content hash
  `sha256:dcd6c84a4e9f541f47907dbc493d00758b0eeb89f2dc54d9a9d3662587acb4d8`
  (klayout-tools commit `3af4716`) — one deck revision behind HEAD at the
  time — so that a documentation-only change could be shown to move nothing.
  That pin was a legitimate controlled comparison for that PR but left the
  repo's LVS reference asserting an extractor artefact
  ([klayout-tools#302](https://github.com/2AMLogic/klayout-tools/issues/302))
  that the very next deck commit (`be4b4f82`,
  [klayout-tools#304](https://github.com/2AMLogic/klayout-tools/issues/304))
  had already resolved upstream by excluding `Nplus` from the bipolar
  emitter region. #84 regenerated `make_reference.py`'s step 8 to emit one
  `bjt` card per drawn PNP unit (the artefact card's basis,
  `plan.pnp_base_ring_area_nm2`, is deleted) and re-ran both flows against
  the current, unpinned deck (`gf180mcu.py` content hash
  `sha256:90a7f0ef…`, klayout-tools commit `0d5ebde`):
  `20260802-215216-59c294c.lvs.json` — `status: match`, 156/156 devices
  (`bjt: 8`, down from 164/164 with `bjt: 16`), 94/94 nets; and
  `20260802-215251-59c294c.drc.json` — see the #82 update above for its
  (unrelated to the `bjt` count) `mim.enclosing.fusetop.1` finding. The
  drawn GDS did not change (`sha256:93fadc35…3010bd`, unchanged) and the MIM
  cap's extracted capacitance did not change (`6.91488e-12 F`, now reported
  as device `C$90` rather than `C$98` purely because the device count
  shrank) — only the reference-netlist derivation and the deck version moved.

## Friction filed (klayout-tools tracker)

Per CLAUDE.md's friction protocol, every klayout-tools gap this work
surfaced is tracked generically (tool capability, never this design's
specifics) on the public
[klayout-tools issue tracker](https://github.com/2AMLogic/klayout-tools/issues):

- **Extraction decks recognise MOS only** — no resistor/bipolar/capacitor
  device classes, so an analog block's LVS cannot be a full-device LVS:
  [`#219`](https://github.com/2AMLogic/klayout-tools/issues/219) —
  **resolved upstream** (#222/#223/#225); this block's reference netlist now
  models all four classes.
- **A curated deck's poly-resistor list covers one sheet-rho flavour of the
  PDK's poly-resistor family** — any drawn instance of another flavour
  collapses to a short:
  [`#299`](https://github.com/2AMLogic/klayout-tools/issues/299) — **resolved
  upstream** on 2026-08-02. The deck now carries a `ppolyf_u_1k` entry
  (`SAB` + `Resistor` + `RES_MK`), and
  [#78](https://github.com/2AMLogic/gf180-bandgap/issues/78) took it up:
  `generate.py` now draws `RES_MK` on `startup.RPU`'s `high_rho` body too, so
  it extracts as a real `ppolyf_u_1k` device at 1000 Ω/□ instead of a short
  on either side of the comparison. The last remaining marker difference
  between the two flavours' bodies is the base flavour's `Pplus`, which the
  high-rho recogniser deliberately omits.
- **A bipolar recogniser that keys off a bare diffusion layer cannot tell a
  base-contact ring from the emitter it surrounds** — a curated deck that
  models no implant layers recognised *two* bipolars per drawn vertical-PNP
  unit cell (the real one, plus one whose "emitter" is the base ring):
  [`#302`](https://github.com/2AMLogic/klayout-tools/issues/302) — **resolved
  upstream** on 2026-08-02 by
  [`#304`](https://github.com/2AMLogic/klayout-tools/issues/304) (deck commit
  `be4b4f82`), which excludes `Nplus` from the emitter region so the n+ tie
  ring is dropped. **This repo has taken it up** ([#84](https://github.com/2AMLogic/gf180-bandgap/issues/84)):
  `make_reference.py` now emits one `bjt` card per drawn PNP unit, and the
  committed LVS evidence was regenerated against the current (post-#304)
  deck — see the resolved deck-pin finding above.
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
- **`enclosing` check false-negatives on a shape drawn entirely outside the
  enclosing layer, instead of flagging the under-enclosure** — found via the
  `fb` top-plate tab above (#82):
  [`#318`](https://github.com/2AMLogic/klayout-tools/issues/318) —
  **resolved upstream** on 2026-08-02 by
  [`#327`](https://github.com/2AMLogic/klayout-tools/issues/327); the current
  deck now genuinely flags this layout's `fb` tab instead of false-negativing
  it (see the #82 update above and gf180-bandgap#84).
- **A recognised MiM cap's plate nets are isolated from the connectivity
  stack**, so no via stack to either plate can ever be confirmed by `klt
  extract`/`klt lvs` — the same limitation that made the `fb` tab's
  workaround necessary in the first place:
  [`#314`](https://github.com/2AMLogic/klayout-tools/issues/314) —
  **resolved upstream** (joins a recognised plate to the ordinary metal
  stack when its via lands on that plate). Its own follow-on gap — a
  DRM-legal top-plate via still misread as a `vdd`/`fb` short — was filed as
  [`#364`](https://github.com/2AMLogic/klayout-tools/issues/364) and fixed
  by [`PR #368`](https://github.com/2AMLogic/klayout-tools/pull/368);
  gf180-bandgap#88 redrew this layout's contact against it (see "Findings
  and escalations" above) and is the consumer that closed the loop on both.

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
