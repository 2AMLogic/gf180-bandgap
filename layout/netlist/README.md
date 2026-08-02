# layout/netlist — post-layout parasitic extraction (#17)

`run_extract.py` produces a parasitic-extracted SPICE netlist of
`bandgap_top` via `klt extract --parasitics`, for #17's "post-layout
extracted re-run of the full verification suite". This directory holds the
extraction tooling and its append-only reports; it does **not** hold a
`sim/dut`-ready netlist yet — see "Blocking finding" below for why.

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

## Confirmed device coverage against this layout

```
extracted devices: 97 {'bjt': 16, 'nfet': 34, 'pfet': 47}
net_count        : 31   (pin_count 4: vdd, vref, vss, vsubs)
device_classes   : [nfet, pfet, bjt, cap_mim_2f0_m4m5_noshield, resistor]
warning          : 279 poly-layer shapes not part of any recognised
                   nfet/pfet gate touch contact at 2+ separate points (the
                   resistor-body signature); this deck may not model the
                   device class drawn here, and its terminals have been
                   absorbed into ordinary interconnect as an unintended
                   short -- see docs/cli/extract.md's 'Known limitation:
                   unmodelled device geometry'.
```

- **MOS (81 devices: 34 nfet + 47 pfet)** — recognised, real drawn
  W/L, bound to the real `nfet_03v3`/`pfet_03v3` models via `--pdk`.
- **Bipolar (16 `bjt` devices)** — newly recognised (klayout-tools#223).
  This is a genuine improvement over the MOS-only extraction #62/PR#66's
  LVS work used: the compensation PNP array's unit devices now extract as
  real `DeviceExtractorBJT3Transistor` devices with drawn `AE`/`PE`/etc.,
  not a short.
- **Resistor (`ppolyf_u`, klayout-tools#222) — 0 recognised.** Confirmed by
  `grep -c '^R' <extracted netlist>` = 21, all of which are the
  `--parasitics` Γ-section cards (`R$N node node__par <ohms>`), not device
  resistors — no `R$N a b <value> ppolyf_u` card exists anywhere in the
  output.
- **MiM capacitor (`cap_mim_2f0_m4m5_noshield`, klayout-tools#225) — 0
  recognised.** No `C$N ... cap_mim_2f0_m4m5_noshield` device card exists
  (only the `--parasitics` ground-C cards).

## Blocking finding: this layout does not draw the marker geometry the new recognisers require

This is **not** a klayout-tools defect — the tool's behaviour here is
correct and documented ("unmarked conductor is never reclassified", and it
prints an explicit warning rather than silently guessing). It is a gap in
**this repo's own committed layout**, drawn under `#62`/PR#66 before the
resistor/capacitor device-class recognisers existed upstream:

- `klayout_tools.decks.gf180mcu.EXTRACTION_DECK.resistors` recognises a
  `ppolyf_u` resistor body as `Poly2 & RES_MK (110/5)`, additionally
  requiring `Pplus (31/0)` + `SAB (49/0)` over the same segment.
  `layout/bandgap_top/generate.py`'s `draw_res`/`draw_trim` **do** draw
  `Pplus` around every resistor body (`# A ppolyf_u body is p+ implanted,
  unsalicided poly` — the design intent already matches the real device),
  but draw neither `RES_MK` nor `SAB`. Without the `RES_MK` marker
  specifically, the deck has no segment to intersect against `Pplus`/`SAB`
  at all, so the resistor bodies of `core.R1`, `core.R2` and all 63
  trim-ladder segments extract as ordinary Poly2 interconnect — i.e. a
  dead short between each resistor's two heads.
- `klayout_tools.decks.gf180mcu.EXTRACTION_DECK.capacitors` requires **both**
  `CAP_MK (117/5)` and `MIM_L_MK (117/10)` on the MiM cap's `FuseTop` top
  plate. `layout/bandgap_top/generate.py`'s `_mim_cap` draws `MIM_L_MK`
  already but not `CAP_MK`, so the compensation cap's plates extract as
  unconnected/absent rather than a recognised device.
- Separately: `startup.RPU` uses the `ppolyf_u_1k` high-sheet-rho poly
  resistor variant (schematic: `XRPU det vdd vss ppolyf_u_1k ...`), which
  has **no** entry in `EXTRACTION_DECK.resistors` at all yet (only the base
  `ppolyf_u` flavor is wired) — even after the marker-layer fix above,
  `RPU` would still extract as a short. This half **is** a klayout-tools
  coverage gap (the deck's resistor list covers one sheet-rho flavor per
  PDK, not the full family), reported upstream generically (see "Friction
  filed" below).

**Why this blocks a meaningful full-PVT extracted-netlist re-run**: a
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

**This issue's remaining scope (full #12 suite re-run over the full PVT
matrix, #13 Monte Carlo re-run, the schematic-vs-extracted delta summary,
and the #11 startup re-check) is therefore blocked** on a follow-up layout
change that draws the missing marker layers, regenerates `bandgap_top.gds`,
and re-passes DRC/LVS/matching/area-budget. That follow-up is tracked as
[gf180-bandgap#73](https://github.com/2AMLogic/gf180-bandgap/issues/73)
(filed alongside this finding) rather than done inline here: it changes
`layout/bandgap_top/generate.py` and the committed GDS, which `#17`'s own
Affected Files scope this issue as "reference only" against, and it carries
its own DRC/LVS/matching/area re-verification acceptance criteria distinct
from #17's.

## Known additional fidelity gaps (once recognition itself is fixed)

Worth recording now so a future increment does not re-discover them:

- The `X`-card MOS binding (`--pdk`) does not carry `AS`/`AD`/`PS`/`PD`
  (source/drain area/perimeter) — a real fidelity loss relative to the
  schematic, which #65/PR#72 specifically corrected `nf` for so those
  junction capacitances would be geometry-accurate. `klt extract`'s own
  docs mark this as a deliberate scope limit of the PDK-model-binding
  feature (schematic-equivalent, no-parasitics scope), not a bug.
- Even once `RES_MK`/`SAB`/`CAP_MK` are drawn, `DeviceExtractorResistor`
  emits a **linear, value-only** `R` card (`R = L/W · sheet_rho`, a single
  ohms figure) — not a call into the real `ppolyf_u` SPICE subcircuit the
  schematic uses, which carries its own temperature-coefficient and
  mismatch modeling. This is a real fidelity gap the extracted netlist will
  carry going forward; not something this repo's layout can fix, since the
  extraction engine's resistor recognizer is defined upstream to write a
  bare `R` card.
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
  [`klayout-tools#299`](https://github.com/2AMLogic/klayout-tools/issues/299).
