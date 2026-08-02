# layout/netlist — post-layout parasitic extraction (#17)

`run_extract.py` produces a parasitic-extracted SPICE netlist of
`bandgap_top` via `klt extract --parasitics`, for #17's "post-layout
extracted re-run of the full verification suite". This directory holds the
extraction tooling and its append-only reports; it does **not** hold a
`sim/dut`-ready netlist yet — see "Still blocking" below for why.

```
layout/netlist/
  README.md         this file
  run_extract.py    reproducible klt extract --parasitics invocation -> committed report
  reports/
    bandgap_top/    <record-id>.{extract.json,extracted.spice}
```

## Install / version used

Per #17's own Test Plan ("confirm the installed `klt` version actually
includes the resistor/BJT/MIM-cap device-class merges from
klayout-tools#222/#223/#225 before relying on it"):

```bash
uv tool install --force git+https://github.com/2AMLogic/klayout-tools
klt --version
```

Verified against a checkout of `2AMLogic/klayout-tools` at commit
`3b86194` (2026-08-02), which is at or after all three merges:

- `klayout-tools#217` (`klt extract --parasitics`) — merged, closed.
- `klayout-tools#222` (resistor device-class recognition) — merged via
  `klayout-tools#228` (commit `37a1e53`).
- `klayout-tools#223` (bipolar/BJT device-class recognition) — merged
  (already present at the previously-installed revision this repo's `klt`
  had cached; re-confirmed present at `3b86194`).
- `klayout-tools#225` (MiM-capacitor device-class recognition) — merged
  (same).

The `klt` binary this repo had installed prior to this issue (reported
`klt --version` → `0.1.0`, a static string that does not track upstream
commits) predated commit `37a1e53` (`#228`, resistor recognition) by 6
commits — i.e. it did **not** yet include the resistor merge #17's own
dependency history claims is "shipped". Builders re-running this script
should reinstall from a fresh `klayout-tools` checkout (`uv tool install
--force git+https://github.com/2AMLogic/klayout-tools`) rather than trust a
cached `klt` install's `--version` string, which does not change between
releases of this pre-1.0 tool.

## Reproducing

```bash
python3 layout/netlist/run_extract.py layout/bandgap_top/bandgap_top.gds
```

This runs `klt extract layout/bandgap_top/bandgap_top.gds --deck gf180mcu
--top bandgap_top --parasitics --pdk gf180mcuD -o
layout/netlist/reports/bandgap_top/<record-id>.extracted.spice`. `--pdk
gf180mcuD` (the 3.3V-flavor variant CLAUDE.md names as primary) makes `klt
extract` bind each extracted MOS device to the real gf180mcu
`nfet_03v3`/`pfet_03v3` subcircuit (`X$1 ... nfet_03v3 L=2U W=2.5U`)
instead of the deck's generic `nfet`/`pfet` class token, which is not a
simulatable model name on its own.

## RESOLVED (#73): the layout now draws the resistor/MiM-cap recognition markers

The original finding below (kept verbatim as the append-only record of what
was discovered and why) reported that `layout/bandgap_top/generate.py` drew
`Pplus` around every `ppolyf_u` resistor body and `MIM_L_MK` on the
compensation cap's top plate, but not the additional marker layers
(`RES_MK`/`SAB`/`CAP_MK`) the deck's resistor/MiM-capacitor recognisers also
require — so every resistor extracted as a short and the cap as absent.
[gf180-bandgap#73](https://github.com/2AMLogic/gf180-bandgap/issues/73) drew
those markers (plus a from-scratch check of the resulting geometry against
what KLayout's native `DeviceExtractorResistor` actually requires — see that
PR's `generate.py` diff for the two things a literal "just add the marker
boxes" reading of the finding above would have missed):

- **A contact landing *inside* a RES_MK-marked body does not recognise the
  device.** `DeviceExtractorResistor` needs its two-terminal ("C") region to
  *directly abut* the marked ("R") body — a contact that only reaches the
  body via a Metal1 bridge (this layout's original `draw_res`/`draw_trim`
  free-end design) leaves the extractor logging "Expected two polygons on
  contacts interacting with one resistor shape (found 0)" and the body still
  extracting as a short, even with every marker layer present. `draw_res`
  now draws a small unmarked poly pad directly past each resistor's true
  free edge (`RES_PAD`, kept outside the marker box); `draw_trim`'s `TRIM_PAD`
  contact-pad allowance at each unit's ends already had exactly this
  property once `RES_MK` itself was narrowed to the unit's `unit_length_nm`
  centre (it was previously drawn to the pad-inclusive full footprint,
  covering the very contacts it needed to stay clear of).
- **`startup.RPU` must *not* pick up the *base* `ppolyf_u` recogniser's
  `Pplus` marker.** `RPU`'s schematic model is `ppolyf_u_1k` (a
  high-sheet-rho flavor this deck's `resistors` list had no entry for at the
  time — klayout-tools#299), not the base `ppolyf_u` this repo's other
  resistors use. Marking its body identically to a base-flavor body would
  have gotten it recognised as a *base* `ppolyf_u` device at the wrong
  (350 Ω/□ vs. its real ~1000 Ω/□) sheet resistance — silently wrong, worse
  than the then-current documented-short status quo. `generate.py`'s
  `ResItem.high_rho` flag (set from the schematic's own `Device.model`) made
  `draw_res` mark `RPU`'s body with `Resistor` (62/0) instead of `Pplus` —
  one of `ResistorDevice.excludes` for the base flavor — so it extracted as
  a short, exactly as klayout-tools#299 said it should at the time.
  **Superseded by [gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78)**:
  klayout-tools#299 is now resolved and the deck carries a `ppolyf_u_1k`
  entry recognised by `SAB` + `Resistor` (62/0) + `RES_MK` — deliberately
  *not* `Pplus` — so `generate.py` now also marks `RPU`'s body with `RES_MK`,
  and it extracts as a real `ppolyf_u_1k` device at 1000 Ω/□ instead of a
  short.

**Current coverage**, from `<record-id>` `20260802-172927-741c4ae`'s
committed report (regenerated by #75, whose trim-strap fix merged four
formerly-distinct ladder nodes — `net_count` was 97 before it):

```
extracted devices: 163 {'bjt': 16, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65}
net_count        : 93   (pin_count 4: vdd, vref, vss, vsubs)
warning          : 213 poly-layer shapes not part of any recognised
                   nfet/pfet gate touch contact at 2+ separate points (the
                   resistor-body signature) and carry no resistor-marker
                   layer at all; ... -- see docs/cli/extract.md's 'Known
                   limitation: unmodelled device geometry'.
```

- **Resistor (`ppolyf_u`) — 65/65 recognised**: `core.R1`, `core.R2`, and all
  63 trim-ladder segments, each a real `DeviceExtractorResistorWithBulk`
  device with drawn `L`/`W` (`r_ohm`/`l_um`/`w_um`/`area_um2` params).
  `startup.RPU` is *not* among them at this record-id — see above — and was
  at the time exactly the kind of shape the remaining warning (213 shapes,
  down from the pre-#73 finding's 279) flags: real drawn poly this deck had
  no device extractor for. **As of #78, `RPU` also extracts as a real
  `ppolyf_u_1k` device** (device count 164, not 163 — see "RESOLVED (#78)"
  below); this block's counts are the #73/#75-era snapshot, kept verbatim.
- **MiM capacitor (`cap_mim_2f0_m4m5_noshield`) — 1/1 recognised**: the
  compensation cap now extracts as a real `DeviceExtractorCapacitor` device
  instead of absent/disconnected plates.
- **Bipolar (`bjt`) — 16/16, unchanged by #73** (already recognised before
  this issue; see the original finding below).
- **MOS — 81/81, unchanged by #73.**

## RESOLVED (#75): `layout/lvs`'s connectivity check is solid end-to-end again

Between #73 and #75, `layout/lvs/run_lvs.py` reported `mismatch`. That was
**not** caused by #73's layout changes: `layout/lvs/make_reference.py`'s
reference netlist was mechanically derived, under #62/PR#66, on the premise
that `klt`'s gf180mcu extraction deck "recognises only `nfet`/`pfet`" — a
premise already false by the time #73 reinstalled `klt` (bipolar
recognition, klayout-tools#223, was merged upstream), and reproducibly false
against the then-`main` GDS *before* any of #73's own changes (`mismatch`,
27 entries, 81/81 devices matched, 18/23 nets — the 16 recognised `bjt`
devices/nets the MOS-only reference didn't model). #73's own fix made the
same structural gap larger (65 `ppolyf_u` + 1 MiM cap more), but did not
create it.

[gf180-bandgap#75](https://github.com/2AMLogic/gf180-bandgap/issues/75)
closed it by teaching `make_reference.py` to emit `ppolyf_u`/`bjt`/MiM-cap
reference cards from the same `plan.py` rows/items `generate.py` draws from
(mirroring how it already did this for MOS), including the device
*parameters* `klt lvs` compares — `R` and `AE` are predicted from the drawn
marker geometry, which is what the extractor measures. Current verdict:

```
extracted devices: 163 {'bjt': 16, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65}
lvs status       : match
devices matched  : 163 / 163
nets matched     : 93 / 93
```

Two things worth carrying forward from that work:

- **A real layout/schematic deviation surfaced and was fixed**: the drawn
  trim strap shorted ladder chain node 0 to node 31 in one span, where the
  schematic's `S0..S4` (closed at `DRAWN_TRIM_CODE = 32`) short nodes 0, 1,
  3, 7, 15 and 31 together. Electrically identical, topologically
  different — invisible while every resistor was a short. `generate.py` now
  derives its straps from the schematic's own `RS*` expressions
  (`plan.trim_strap_spans`).
- **`startup.RPU` still collapsed to a short on both sides at this
  record-id**, by design — see "RESOLVED (#73)" above. klayout-tools#299 has
  since been resolved upstream; see "RESOLVED (#78)" below for the current
  status.

**#17's remaining scope is therefore no longer blocked on `layout/lvs`.**
One thing to settle before running #12/#13 against the extracted netlist:
the compensation MIM capacitor still extracts with two *floating* plates,
because `klt extract`'s recognised cap plates are their own connectivity
nodes, never joined to the ordinary metal stack, regardless of how the
layout routes them (`decks.CapacitorDevice`'s "Known limitation" — see
`layout/README.md`). Since
[gf180-bandgap#77](https://github.com/2AMLogic/gf180-bandgap/issues/77) the
layout *does* draw a real via stack from both plates down to the Metal1
`vdd`/`fb` routing (`generate._mim_cap`), but that connection is still
invisible to `klt extract` for the reason above, so a parasitic-extraction
consumer working from this netlist directly still needs to be told the
compensation cap is present but disconnected — a stability/phase-margin
re-run against a netlist with no compensation cap in the loop is not
representative.

**Not the same gap as the `fb` plate's own contact geometry.** The
connectivity-modelling gap above is a tool limitation; the `fb` up-hop
contact is a *manufacturability* finding
([gf180-bandgap#82](https://github.com/2AMLogic/gf180-bandgap/issues/82)),
and it is worth stating here in full rather than by cross-reference, because
a consumer of this netlist is exactly who would otherwise assume the drawn
cap is shippable:

- The FuseTop routing tab that carries `fb` off the top plate extends 0.8 µm
  past the `Metal4` bottom plate's edge with **zero** bottom-plate overlap
  there, against `MIMTM.3`'s 0.6 µm minimum bottom-plate overlap of the top
  plate (transcribed in the deck as `mim.enclosing.fusetop.1`, and honoured
  by `MIM_PLATE_INSET` on the other three edges of the same box).
- The `Via4` that hops up onto that tab has **zero** `Metal4` overlap,
  against `MIMTM.2`'s 0.4 µm minimum bottom-plate overlap of `Via4`.
  `MIMTM.2` is not transcribed into the deck at all, so that half has no rule
  to be checked by.
- **The block as drawn is therefore not manufacturable at that contact.** It
  is not a "standard MiM-cap top-plate routing technique"; it is a workaround
  for `klt extract`'s dielectric-blind connectivity graph, which would read
  the DRM-legal contact (a `Via4` landing inside the bottom-plate footprint)
  as a `vdd`/`fb` short.
- **`klt drc`'s `clean` verdict on this geometry is a false negative, not a
  passing check.** `mim.enclosing.fusetop.1` maps onto KLayout's
  `Region.enclosing_check`, which reports nothing when a shape lies *entirely*
  outside the enclosing layer — filed upstream as
  [klayout-tools#318](https://github.com/2AMLogic/klayout-tools/issues/318).

Revisit once
[klayout-tools#314](https://github.com/2AMLogic/klayout-tools/issues/314)
(plate nets joined to the connectivity stack) makes the DRM-legal contact
drawable without the extractor reading it as a short. Full geometry trace:
`generate._mim_cap`'s docstring and `layout/README.md` § "Findings and
escalations".

## RESOLVED (#78): `startup.RPU` now extracts as a real `ppolyf_u_1k` device

klayout-tools#299 — the gap noted in "RESOLVED (#73)" above, that the deck's
`resistors` list covered only the base `ppolyf_u` sheet-rho flavor — is now
resolved upstream: the deck carries a `ppolyf_u_1k` `ResistorDevice` entry
(`SAB (49/0)` + `Resistor (62/0)` + `RES_MK (110/5)`, deliberately *not*
`Pplus`, at 1000 Ω/□) alongside the base entry.
[gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78) took
it up: `generate.py`'s `draw_res` now also draws `RES_MK` on a `high_rho`
body (it already drew `SAB`/`Resistor`), so `startup.RPU` matches the new
recogniser instead of being marked with only `Resistor` as an *exclude* for
the base one. `netlist_model.EXTRACTED_RES_MODELS` gained `ppolyf_u_1k` so
`reduce_nets` stops merging `RPU`'s two terminal nets, and
`layout/lvs/make_reference.py` predicts its `R` from the drawn marker area
at 1000 Ω/□ (`plan.PPOLYF_U_1K_SHEET_RHO`) instead of collapsing it to a
short. Current verdict:

```
extracted devices: 164 {'bjt': 16, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65,
                        'ppolyf_u_1k': 1}
lvs status       : match
devices matched  : 164 / 164
nets matched     : 94 / 94
```

`net_count` moved from 93 to 94: `RPU`'s `vdd`/`det` terminals are no longer
union-found into one net now that `ppolyf_u_1k` is in
`EXTRACTED_RES_MODELS`. No other device class's counts moved — this change
is additive/local to `startup.RPU`.

## Original finding (#17): this layout did not draw the marker geometry the new recognisers require

Re-running `klt extract --parasitics --deck gf180mcu --pdk gf180mcuD` against
the `bandgap_top.gds` committed at the time (see #62/PR#66) confirmed:

- **Bipolar: works.** 16 real `bjt` devices recognised with drawn
  `AE`/`PE`/etc. — a genuine improvement over the MOS-only extraction #62
  used.
- **Resistor: 0 recognised.** `klt extract` warns: "279 poly-layer shapes
  not part of any recognised nfet/pfet gate touch contact at 2+ separate
  points (the resistor-body signature) ... absorbed into ordinary
  interconnect as an unintended short." Every discrete `ppolyf_u` resistor
  (`core.R1`, `core.R2`, all 63 trim-ladder segments) extracts as a 0 ohm
  short between its two heads.
- **MiM capacitor: 0 recognised.** The compensation cap's plates extract as
  disconnected/absent rather than a device.

This was **not** a klayout-tools defect — the deck's resistor/capacitor
recognisers require specific marker geometry, and `layout/bandgap_top/generate.py`
did not draw all of it:

- `klayout_tools.decks.gf180mcu.EXTRACTION_DECK.resistors`'s `ppolyf_u`
  entry recognises `Poly2 & RES_MK (110/5)`, requiring `Pplus (31/0)` +
  `SAB (49/0)` over that same segment. `generate.py`'s `draw_res`/`draw_trim`
  **already drew `Pplus`** around every resistor body (correctly modeling
  the unsalicided p+ poly device) but drew neither `RES_MK` nor `SAB`.
  Without the `RES_MK` marker specifically, the deck had no segment to
  intersect against `Pplus`/`SAB` at all, so the resistor bodies of
  `core.R1`, `core.R2` and all 63 trim-ladder segments extracted as ordinary
  Poly2 interconnect — i.e. a dead short between each resistor's two heads.
- `klayout_tools.decks.gf180mcu.EXTRACTION_DECK.capacitors` requires **both**
  `CAP_MK (117/5)` and `MIM_L_MK (117/10)` on the MiM cap's `FuseTop` top
  plate. `generate.py`'s `_mim_cap` drew `MIM_L_MK` already but not
  `CAP_MK`, so the compensation cap's plates extracted as
  unconnected/absent rather than a recognised device.
- Separately: `startup.RPU` uses the `ppolyf_u_1k` high-sheet-rho poly
  resistor variant (schematic: `XRPU det vdd vss ppolyf_u_1k ...`), which
  has **no** entry in `EXTRACTION_DECK.resistors` at all (only the base
  `ppolyf_u` flavor is wired) — even after the marker-layer fix, `RPU` still
  extracts as a short, by design (see "RESOLVED (#73)" above). This half
  **is** a klayout-tools coverage gap (the deck's resistor list covers one
  sheet-rho flavor per PDK, not the full family), reported upstream
  generically (see "Friction filed" below).

**Why this blocked a meaningful full-PVT extracted-netlist re-run**: a
bandgap reference's entire PTAT/CTAT combination, feedback network and trim
mechanism is resistor-mediated. A netlist where `R1`/`R2`/the trim ladder
are literal 0 Ω shorts and the compensation cap is absent does not
represent the real drawn circuit — it is a different, almost certainly
non-functional topology. Running #12's spec-line suite against it would not
be a valid post-layout re-verification (it would demonstrate that a
short-circuited bandgap fails, which is not an informative result), and
reporting such numbers under `Netlist provenance: extracted` would violate
CLAUDE.md's "no claim without a testbench" / no-relaxation rule by
presenting a non-representative circuit's results as this block's
post-layout behavior.

**#17's remaining scope (full #12 suite re-run over the full PVT matrix,
#13 Monte Carlo re-run, the schematic-vs-extracted delta summary, and the
#11 startup re-check) was blocked on this** — first on the marker-layer gap
#73 closed, then on the `layout/lvs` reference staleness #75 closed. See
"RESOLVED (#75)" above for the current status and the one remaining
representativeness caveat (the unwired compensation cap, #77).

## Known additional fidelity gaps

Worth recording now so a future increment does not re-discover them:

- The `X`-card MOS binding (`--pdk`) does not carry `AS`/`AD`/`PS`/`PD`
  (source/drain area/perimeter) — a real fidelity loss relative to the
  schematic, which #65/PR#72 specifically corrected `nf` for so those
  junction capacitances would be geometry-accurate. `klt extract`'s own
  docs mark this as a deliberate scope limit of the PDK-model-binding
  feature (schematic-equivalent, no-parasitics scope), not a bug.
- Now that `RES_MK`/`SAB`/`CAP_MK` are drawn (#73), `DeviceExtractorResistor`
  still emits a **linear, value-only** `R` card (`R = L/W · sheet_rho`, a
  single ohms figure) — not a call into the real `ppolyf_u` SPICE subcircuit
  the schematic uses, which carries its own temperature-coefficient and
  mismatch modeling. This is a real fidelity gap the extracted netlist
  carries going forward; not something this repo's layout can fix, since
  the extraction engine's resistor recognizer is defined upstream to write
  a bare `R` card.
- The extracted top-level pin list is `vdd vref vss vsubs` (four pins) vs.
  `sim/dut/README.md`'s three-pin (`vdd`, `vss`, `vref`) convention — a
  `sim/dut`-ready wrapper will need to tie `vsubs` to `vss` (or expose it)
  before this netlist can be handed to `sim/run_corners.py --dut`.

## Friction filed (klayout-tools tracker)

Per CLAUDE.md's friction protocol (tool gap, described generically, no
design specifics):

- **gf180mcu extraction deck's resistor device-class list covers only one
  sheet-rho flavor of the PDK's poly-resistor family** — a PDK commonly
  ships several selectable sheet-rho variants of the same physical poly
  resistor (distinguished by an additional exclude-style marker layer), and
  the curated deck wires device recognition for only the base flavor, so
  any drawn instance of another flavor still collapses to a short even once
  the base flavor's marker geometry is drawn correctly. Filed as
  [`klayout-tools#299`](https://github.com/2AMLogic/klayout-tools/issues/299)
  — **resolved upstream** 2026-08-02; this repo took up the new entry for
  `startup.RPU` in
  [gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78)
  (see "RESOLVED (#78)" above).
- **A bipolar recogniser keyed on a bare diffusion layer counts a
  base-contact ring as a second emitter** — a curated deck that models no
  implant layers could not tell the base-contact ring of a standard vertical
  bipolar unit cell apart from the emitter it surrounds, so every drawn unit
  extracted as two devices of the bipolar class sharing one base net. Filed
  as [`klayout-tools#302`](https://github.com/2AMLogic/klayout-tools/issues/302)
  (found while closing #75) — **resolved upstream** 2026-08-02 by
  [`klayout-tools#304`](https://github.com/2AMLogic/klayout-tools/issues/304),
  which excludes the n+ implant layer from the emitter region so the tie ring
  is dropped and each drawn unit extracts as one device.
  **This repo has not taken it up yet.** `make_reference.py`'s step 8 still
  emits two `bjt` cards per drawn PNP unit specifically to mirror the
  now-fixed artefact, so `layout/lvs/bandgap_top.ref.spice` is **stale**
  against the current deck: it asserts 16 `bjt` where the current deck
  extracts 8, and LVS will not match until it is regenerated. The committed
  LVS evidence was produced against the pre-#304 deck (`gf180mcu.py` content
  hash `sha256:dcd6c84a…`) on purpose, so that a documentation-only change
  could be shown to move nothing — see `layout/README.md` § "Findings and
  escalations". Regeneration is tracked as
  [gf180-bandgap#84](https://github.com/2AMLogic/gf180-bandgap/issues/84).
