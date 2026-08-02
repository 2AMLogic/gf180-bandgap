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
- **`startup.RPU` must *not* pick up the same `RES_MK`/`SAB` markers.**
  `RPU`'s schematic model is `ppolyf_u_1k` (a high-sheet-rho flavor this
  deck's `resistors` list has no entry for — klayout-tools#299, unchanged by
  this issue), not the base `ppolyf_u` this repo's other resistors use.
  Marking its body identically would have gotten it recognised as a *base*
  `ppolyf_u` device at the wrong (350 Ω/□ vs. its real ~1000 Ω/□) sheet
  resistance — silently wrong, worse than the documented-short status quo.
  `generate.py`'s `ResItem.high_rho` flag (set from the schematic's own
  `Device.model`) makes `draw_res` mark `RPU`'s body with `Resistor` (62/0)
  instead — one of `ResistorDevice.excludes` for the base flavor — so it
  stays a short, exactly as klayout-tools#299 says it should.

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
  `startup.RPU` is *not* among them — see above — and is exactly the kind of
  shape the remaining warning (213 shapes, down from the pre-#73 finding's
  279) flags: real drawn poly this deck has no device extractor for.
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
- **`startup.RPU` still collapses to a short on both sides**, by design —
  see "RESOLVED (#73)" above. klayout-tools#299 has since been resolved
  upstream, so the deck now *has* a `ppolyf_u_1k` entry this layout could
  draw for; taking it up is tracked as
  [gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78).

**#17's remaining scope is therefore no longer blocked on `layout/lvs`.**
One thing to settle before running #12/#13 against the extracted netlist:
the compensation MIM capacitor extracts with two *floating* plates, because
this layout draws no via stack from it down to the Metal1 routing (and the
deck could not confirm that connection even if it did — see
`layout/README.md`). A stability/phase-margin re-run against a netlist with
no compensation cap is not representative; tracked as
[gf180-bandgap#77](https://github.com/2AMLogic/gf180-bandgap/issues/77).

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
  — **resolved upstream** 2026-08-02; taking up the new entry for
  `startup.RPU` is tracked as
  [gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78).
- **A bipolar recogniser keyed on a bare diffusion layer counts a
  base-contact ring as a second emitter** — a curated deck that models no
  implant layers cannot tell the base-contact ring of a standard vertical
  bipolar unit cell apart from the emitter it surrounds, so every drawn unit
  extracts as two devices of the bipolar class sharing one base net. Filed
  as [`klayout-tools#302`](https://github.com/2AMLogic/klayout-tools/issues/302)
  (found while closing #75; the reference netlist has to model the artefact
  device for LVS to match).
