# Chipalooza Challenge #5 proposal — `bandgap_top`

Open Circuit Design's [Chipalooza](https://opencircuitdesign.com/chipalooza/)
Challenge #5 is a GF180MCU shuttle (Wafer.Space), structured the same way as
Challenge #3: a fixed per-design slot on an organizer-supplied test chip, with
a shared harness (bandgap-referenced bias, digital control/test I/O, a small
number of shared analog lines and dedicated pads, SPI control) and open-source
DRC/LVS/PVT sign-off. This document is the brief-conformant proposal for this
repository's block, `bandgap_top` — a standalone bandgap voltage reference.

Every claim below is re-derived from evidence already committed under
`sim/`, `layout/`, and `spec/` in this repository; nothing here is a new
simulation or a relaxed spec value. Where a row is unmet, it is stated as
unmet.

## 1. Block type

A **Brokaw-topology bandgap voltage reference** (`design/bandgap_top.sch`),
comprising:

- `bandgap_core` — the Brokaw PNP core (PTAT/CTAT summing) with a cascoded
  current-mode bias/output stage.
- `bandgap_amp` — a telescopic-cascode, dominant-pole-compensated
  error-amplifier servoing the loop (issue #42's redesign of the original 5T
  OTA).
- `bandgap_startup` — a current-sensing, self-disabling startup circuit that
  kicks the core out of its degenerate (zero-current) operating point.
- A 6-bit binary-weighted `ppolyf_u` trim ladder (`bandgap_trim`) in series
  with the core's fixed base resistor, providing ±1-point resistor trim.

Target rails: 3.3 V ±10% (2.97–3.63 V), per
[DR-0002](../../spec/decision-records/0002-supply-voltage-scope.md) — see
§4 ("Supply / 5.0V rail") for how that maps against Challenge #5's 3.3–5.0V
analog-rail expectation.

## 2. Relationship to the harness reference — ordinary catalog entry, not a harness candidate

The Chipalooza common structure (per the published rules for #2/#3, which #5
follows) states that **the harness itself supplies a bandgap-referenced bias
voltage** to every slot, as fixed shared infrastructure alongside the digital
control/test I/O and shared analog lines. That reference is organizer-owned
and is not swapped per submission.

`bandgap_top` is therefore proposed as **an ordinary catalog entry occupying
one design slot**, not as a candidate to replace or supply the harness's own
reference. It draws power from the slot's own supply/ground and presents its
`vref` output on one of the harness's shared analog lines for measurement,
exactly like any other analog IP block on the shuttle. Nothing about this
design requires or assumes integration into the harness's own bias
distribution.

## 3. I/O list mapped to the slot budget

`bandgap_top`'s top-level netlist (`design/netlist/bandgap_top.spice`,
`.subckt bandgap_top vdd vss vref`) exposes exactly **three functional
pins** — there is no fourth physical pin. The LVS reference netlist
(`layout/lvs/bandgap_top.ref.spice`) declares the same three pins; its
substrate and Nwell ties land on `vss`/`vdd`.

| Pin | Direction | Function | Slot-budget mapping |
|---|---|---|---|
| `vdd` | power | 3.3 V ±10% supply | slot power rail (not a counted digital/analog line) |
| `vss` | power | ground | slot ground rail (not a counted digital/analog line) |
| `vref` | analog output | ~1.2 V bandgap reference | **1 of the harness's 4 shared (multiplexed) analog lines** |

No digital control input and no digital test output are required:

- **Trim is not runtime-programmable.** The trim ladder's six segments
  (`RS0`..`RS5`) are set by a mask/metal-option strap internal to
  `bandgap_core`, per `sim/trim-coverage/`'s record and
  `design/bandgap_trim_network.md` — trim code is fixed at layout time, not
  driven by a pin, so it consumes **0 of the harness's 24 digital control
  inputs**.
- No status or comparator output exists to drive a digital test output, so
  this design uses **0 of the harness's 12 digital test outputs**.
- No dedicated pad is required for correct operation; a dedicated pad on
  `vref` (instead of routing through the shared analog mux) would trade one
  of the harness's 0–4 dedicated-pad slots for lower mux-loading measurement
  error, but is an optional bench-quality improvement, not a functional
  requirement.

Net footprint against the shared slot budget: **1 of 4 shared analog lines,
0 of 24 digital control inputs, 0 of 12 digital test outputs, 0 (optionally
up to 1) of 0–4 dedicated pads** — the leanest possible I/O footprint the
brief's structure allows.

## 4. Functional description

`bandgap_top` regulates `vref` to a PTAT+CTAT-summed bandgap voltage
(nominal 1.20 V) referenced to `vss`, independent of `vdd` (within the
supply range) and, to first order, of temperature. The Brokaw core forces
equal emitter currents through a PNP pair of unequal emitter area — since
[DR-0007](../../spec/decision-records/0007-q2-array-dvbe-ratio.md) (ratified
by the operator 2026-10-02) `core.Q2` is **four parallel `pnp_05p00x05p00`
units** against `core.Q1`'s one, an effective ΔVBE ratio measured at
**4.0209** at the 5.07 µA design current (`bjt_typical`, 27 °C; 4.0185–4.0281
across three BJT corners × −40/27/125 °C, record
[`20261008-120404-44d1a83`](../../sim/device-pnp-array/records/20261008-120404-44d1a83.md))
— producing a PTAT voltage across the sense resistor `core.R2`; that PTAT
term is summed with the PNP's own CTAT base-emitter voltage at the output
node. The telescopic-
cascode error amplifier closes the loop around the core's two sense nodes.
On power-up, the core's fully-off state is a stable (degenerate) equilibrium
of the loop; `bandgap_startup` senses the absence of bias current and
injects current into the mirror/cascode gate nodes until the core reaches
its intended operating point, then self-disables (no continuous current
draw once started — verified in `sim/startup/` and `sim/startup-state-search/`).

## 5. Spec table (re-derived from `sim/` at 3.3 V)

Ratified spec source:
[`spec/decision-records/0003-target-spec-ratification.md`](../../spec/decision-records/0003-target-spec-ratification.md)
and `README.md`'s "Target specification" table. Min/typ/max below are
re-derived directly from the cited `sim/` records, not restated from the
ratified table's own wording. "Typ" is the `tt` process corner at 27 °C /
3.30 V unless noted; "min/max" are the worst schematic-level corner over the
full 81-point PVT grid (process × −40/27/125 °C × 2.97/3.30/3.63 V), per
`sim/output-voltage-tc/`, `sim/psrr-dc/`, `sim/line-regulation/`, `sim/iq/`,
`sim/startup/`, `sim/trim-coverage/`, `design/bandgap_error_budget.md` §5,
and `sim/postlayout-delta.md`.

**Which evidence each column rests on.** The schematic columns are the
**final-DUT** fleet records indexed in
[`sim/suite/fleet-evidence-239.md`](../../sim/suite/fleet-evidence-239.md),
taken against the canonical DUT `sim/dut/bandgap_top.spice`
(sha256 `9ef5f8c5…`) **after** DR-0007's `core.Q2` array amendment and the
`R2` re-derivation / `R1` re-null it required
(`design/bandgap_error_budget.md` §5e/§5f) — rolled up over exactly those
pinned records in
[`sim/suite/summaries/20261016-015258-1c4f2a2.md`](../../sim/suite/summaries/20261016-015258-1c4f2a2.md),
which reports all six indexed spec lines passing. Three qualifications the
rows below carry individually:

- **Startup** simulates its own embedded, synchronized core, which lumps
  `R1` + 32 trim units into one resistor (exact at `tt`/27 °C only;
  −0.18 % / +0.27 % at −40 / 125 °C; `res_ff`/`res_ss` not exercised), so it
  is not a simulation of the canonical netlist itself
  (`sim/startup-embedded-core-sync.md`).
- **Trim** and **Output noise** have no final-DUT record: their newest
  records (2026-08-02 and 2026-09-10) are on **superseded DUTs** and predate
  DR-0007's retuning. Those rows are labelled accordingly and no verdict is
  carried forward from them to the amended design.
- The **post-layout** column is `sim/postlayout-delta.md` and
  `sim/startup-extracted/`, whose newest records are all dated 2026-08-03
  and therefore **also predate DR-0007** — see the subsection after the
  table.

**No 5.0 V characterization exists or is claimed** — see the "Supply / 5.0V
rail" row below; this is the one row this document scopes as *not
evaluated* rather than met/unmet, per
[DR-0002](../../spec/decision-records/0002-supply-voltage-scope.md).

| Row | Typ (schematic, tt/27°C/3.3V) | Min/Max (schematic, 81-corner) | Post-layout extracted (pre-DR-0007) | Schematic verdict | **Extracted (post-layout) verdict** |
|---|---|---|---|---|---|
| Output reference (1.20 V ±2% untrimmed, 1.176–1.224 V) | 1.20198 V | 1.18859 V – 1.21120 V ([`20261016-010723-ee8a503`](../../sim/output-voltage-tc/records/20261016-010723-ee8a503.md)) | 1.23361 V (typ), up to 1.25187 V worst-case | **MET** (27/27 fleet units, each internally swept −40…125 °C = the full 81-point grid) | **UNMET** — the failure is entirely high-side: worst extracted 1.25187 V at `bjt_ss_125c_2.97v` against the 1.224 V ceiling; the 1.176 V floor is not violated (extracted minimum 1.2219 V). `sim/postlayout-delta.md` marks the row FAIL on the two limits taken together |
| Output reference, combined basis (mismatch MC N≥300 + process corners, 3σ) | — | **0 of 81 corners fail**, tightest margin **+1.356 mV** (`bjt_ff_125c_3.63v`), from [`sim/suite/combined/20261016-013300-999e5cf.md`](../../sim/suite/combined/20261016-013300-999e5cf.md) over the final-DUT corner leg and the N=300 mismatch leg ([`20261016-013258-999e5cf`](../../sim/mc-untrimmed/records/20261016-013258-999e5cf.md)) | not re-run post-layout | **MET** — with the report's own caveat that the verdict is **sensitive to `par_r`**: scaling that assumed mismatch coefficient ×2 flips 3 of 27 corners at 125 °C to FAIL, so the coefficient must be validated before the verdict is treated as final ([DR-0004](../../spec/decision-records/0004-par-r-mismatch-coefficient-risk.md)) | **not evaluated** — the mismatch-MC leg (`sim/mc-untrimmed/`) has no post-layout-extracted counterpart; only the deterministic-corner leg has been re-run extracted, and that leg alone already fails (row above) |
| Temp coefficient (−40…125 °C, <50 ppm/°C box) | 25.917 ppm/°C | 11.224 – 44.6557 ppm/°C (worst at `bjt_ff` / 3.63 V) | 62.5948 ppm/°C (typ), up to 90.2239 ppm/°C worst-case | **MET** (27/27 units = 81-point grid), 10.7 % under the limit | **UNMET** — worst extracted corner (`bjt_ss_-40c_3.30v`, 90.2239 ppm/°C) is 1.8× the 50 ppm/°C limit |
| PSRR (>60 dB DC–1 kHz) | 110.82 dB (1 Hz) / 96.1977 dB (1 kHz) | worst 77.524 dB (1 Hz) / 77.3002 dB (1 kHz), both `res_ss_125c_3.63v` ([`20261016-013458-999e5cf`](../../sim/psrr-dc/records/20261016-013458-999e5cf.md)) | worst 74.7351 dB (1 Hz) / 72.896 dB (1 kHz) | **MET** (81/81) | **MET** (81/81) |
| Line regulation (<1 mV/V, DC, 2.97–3.63 V) | — | worst 0.027133 mV/V (`res_ss_125c_3.30v`, [`20261016-013457-999e5cf`](../../sim/line-regulation/records/20261016-013457-999e5cf.md)) | worst 0.0372934 mV/V | **MET** (27/27) | **MET** (27/27) |
| Supply / output reference over supply (3.3 V ±10%: Vref stays 1.176–1.224 V across 2.97–3.63 V) | — | same as Output reference row (continuous 133-point supply sweep per corner: 1.18859 – 1.21109 V) | same as Output reference row | **MET** | **UNMET** (same cause as Output reference) |
| Supply / 5.0V rail (stretch: "also 5V flavor"; Challenge #5 brief expects 3.3–5.0V analog-rail operation) | — | — | — | **not evaluated** | **not evaluated** — no 5.0V device flavor, testbench, or layout exists per DR-0002 (3.3V-only, wave 1); Challenge #5's brief text expects analog blocks to operate 3.3–5.0V, and this design has not been shown to |
| Quiescent current (<50 µA) | 20.7644 µA | worst 33.8425 µA (`ff_125c_3.63v`, gated record [`20261016-015234-71a0fef`](../../sim/iq/records/20261016-015234-71a0fef.md), ingested by #344) | worst 36.2719 µA | **MET** (81/81) | **MET** (81/81) |
| Trim (1-point, ≥±5% range, ≤0.25%/step at 27°C) | span 178.2 mV, LSB 2.83 mV | span 135.389–240.737 mV, LSB 2.14904–3.82124 mV over 81 corners | not re-run post-layout | **MET** (81/81) **on the pre-DR-0007 netlist only** — the newest record ([`20260802-035959-5066d85`](../../sim/trim-coverage/records/20260802-035959-5066d85.md)) is on a superseded DUT (sha256 `9d38148b…`), so this row is **not re-verified** against the amended `R1`/`R2` sizing | **not evaluated** — no post-layout-extracted trim-coverage bench exists yet |
| Startup (self-starting all corners, <1 ms to 1%) | 14.57 µs | worst 36.6392 µs (`ss_125c_3.30v`, [`20261016-013501-999e5cf`](../../sim/startup/records/20261016-013501-999e5cf.md)) | worst 29.131 µs (`ss_125c_2.97v`, well under 1 ms) | **MET** (81/81) — on this bench's embedded lumped-`R1` core, not the canonical netlist (see the preamble) | **MET** (81/81) |
| Area (ratified `< 0.05 mm²`, DR-0003; interim ceiling `< 0.066 mm²`, DR-0006) | — | drawn 0.06492 mm² (64,924.27 µm², bbox 222.10 × 292.32 µm) | same (physical layout) | n/a (not a sim claim) | **PASS against DR-0006's interim `< 0.066 mm²` ceiling** — 1,075.73 µm² (1.6 %) of headroom — and **FAIL against the originally ratified `< 0.05 mm²`** (DR-0003) — 14,924.27 µm² (29.8 %) over ([`layout/bandgap_top/AREA.md`](../../layout/bandgap_top/AREA.md), re-measured 2026-10-30 against the regenerated GDS). [DR-0006](../../spec/decision-records/0006-area-target-narrowed-post-166.md)'s own header still reads `Status: proposed`, although its diff landed: `README.md`'s Area row and `area_report.py`'s `RATIFIED_TARGET_UM2` both carry 0.066 mm²/66,000 µm² |
| PSRR @ 1 MHz (stretch, >30 dB) | 31.6977 dB | worst 28.706 dB (`ss_125c_2.97v`) over all 81 corners | not separately gated | reference only — recorded, not gated; the stretch goal is **not** met at every corner | reference only |
| Output noise, Load (open items, no numeric target ratified) | — | 0.1–10 Hz integrated noise is measured (`sim/output-noise/records/`, 2026-09-10, schematic and extracted) but on a superseded DUT and against **no ratified threshold** | — | **not claimed** | **not claimed** — `sim/suite/spec.py`'s `NOT_CLAIMED_HERE` list; the band is defined but the threshold (A6) and the load row (A7) are open items per `README.md` |
| Long-term drift | — | — | — | **not specified** (canary block) | **not specified** |

### The output-reference and temperature-coefficient rows are UNMET at the post-layout level

This is the single most important caveat in this document, per the epic's
own instruction, and it is restated here rather than left to the table
alone: **the committed `bandgap_top` GDS is DRC-clean (0 violations) and
LVS-matching, but the parasitic-extracted netlist drawn from it fails the
ratified output-reference and temperature-coefficient spec rows.**
DRC/LVS-clean GDS and post-layout spec conformance are two different
claims, and only the first is currently true for this row pair.

**Every post-layout number in this document predates DR-0007.** The records
`sim/postlayout-delta.md` pairs are dated 2026-08-03, and that is also the
date of the newest extracted record in the repo for any gated bench.
`README.md`'s Status paragraph states the position directly: the committed
GDS and the LVS reference netlist still carry the **prior `R2` sizing**, so
their clean DRC/LVS reports do not certify the amended schematic. The
extracted FAILs below are evidence about the pre-amendment circuit; they are
not a post-DR-0007 result, and no row is moved to met on the strength of
them.

- Full per-corner data: [`sim/postlayout-delta.md`](../../sim/postlayout-delta.md)
  (records paired: `sim/output-voltage-tc/records/20260803-100317-ba091ea.md`
  schematic vs. `sim/output-voltage-tc/records/20260803-055357-31e5efc.md`
  extracted, 81/81 corners aligned) — both pre-DR-0007.
- Root cause: [issue #87](https://github.com/2AMLogic/gf180-bandgap/issues/87)
  — the drawn PNP array realizes Q2 as four parallel `pnp_05p00x05p00` unit
  devices (for common-centroid matching, per `layout/floorplan.md` §4.1),
  which measures an effective dVBE ratio of **4.03**, against the
  then-schematic's single `pnp_10p00x10p00` device at **3.63**. That +8%
  dVBE gain is a first-order error on `Vref = VBE3 + (R1+trim)/R2 · dVBE`.
  This is characterized as a device-physics/schematic-vs-layout-intent
  divergence, not a DRC or extraction defect — LVS cannot catch it because
  the LVS reference is itself derived from the drawn layout
  (`layout/lvs/make_reference.py`), so it structurally matches four drawn
  units against four reference units regardless of which side's intent is
  "correct."
- **That divergence has since been decided, and the schematic side of it is
  closed.**
  [DR-0007](../../spec/decision-records/0007-q2-array-dvbe-ratio.md) was
  **ratified by the operator on 2026-10-02** (Option A: the schematic adopts
  the drawn 4× unit array; no ratified spec limit moved).
  `design/netlist/bandgap_top.spice` now carries
  `XQ2 vss vss e2 pnp_05p00x05p00 m=4`; the array's effective ratio was
  re-measured over the corner axis as DR-0007's Decision item 1 required
  ([`20261008-120404-44d1a83`](../../sim/device-pnp-array/records/20261008-120404-44d1a83.md)),
  `R2` was re-derived from that measurement and `R1` re-nulled / `Vref`
  re-centred against the full-PVT bench rather than inferred from the `λ`
  algebra (`design/bandgap_error_budget.md` §5e/§5f — the pre-retune DUT did
  **not** keep its TC null through the `R2` change: 54.39 ppm/°C, over the
  ratified 50, before `R1` moved to 446.0 µm). §5's schematic columns are
  that amended design.
- **What remains open is the physical and extracted side.** The GDS has not
  been regenerated against the amended netlist and no extracted re-run
  exists on it, so the extracted column cannot yet say how much of the gap
  DR-0007 closes. That is
  [#204](https://github.com/2AMLogic/gf180-bandgap/issues/204) (regenerate
  the layout and record pinned extracted verification), with
  [#87](https://github.com/2AMLogic/gf180-bandgap/issues/87) still open for
  the extracted re-run its operator ruling asks for and
  [#94](https://github.com/2AMLogic/gf180-bandgap/issues/94) tracking the
  gap to the T1 sim-validated tier. **Tapeout is not scheduled** pending
  that re-verification.

No other row in this table is relaxed, omitted, or presented more favorably
than its cited evidence supports.

## 6. Verification status summary

All of the physical-verification reports below are the newest committed runs
against the current GDS (sha256 `97944732…`, regenerated 2026-10-28 for
DRC-cleanliness under `klt` 0.8.0), and they are the two reports
[`signoff/block-manifest.json`](../../signoff/block-manifest.json) cites for
T1 items 3 and 4. They certify the **drawn layout**, which still carries the
pre-DR-0007 `R2` sizing — see §5's post-layout subsection.

- **DRC**: `status: clean`, `violation_count: 0`, 82 rules checked
  (`layout/drc/reports/bandgap_top/20261028-065229-f32fe48.drc.json`;
  `klt` 0.8.0 / KLayout 0.30.12, `gf180mcu` deck).
- **LVS**: `status: match` from `klt lvs` (klayout engine) — **164/164
  devices, 82/82 nets, 3/3 pins** matched, `error_count: 0`
  (`layout/lvs/reports/bandgap_top/20261028-065214-f32fe48.lvs.json`). That
  run records 9 warnings and no errors: 6 `topology` and 3
  `device.geometry_not_compared` (KLayout compares only *primary* device
  parameters, so the MIM cap's `A`/`P` and the `ppolyf_u` resistors'
  `A`/`L`/`P`/`W` did **not** take part in the compare — a named limit of
  the verdict, not a defect). Body-terminal verification reads
  `verified` on this run.
  - The independent **`netgen` cross-check has not been re-run against this
    GDS**: its newest report
    (`layout/lvs/reports/bandgap_top/20260819-070132-1e66285.lvs-netgen.json`,
    2026-08-19) is against the *previous* GDS and is cited here as
    historical. On that older layout the two engines disagreed by design —
    `netgen` reported one `device.property` mismatch, root-caused in
    [issue #168](https://github.com/2AMLogic/gf180-bandgap/issues/168) to a
    netgen-only pairing artifact on graph-symmetric dummy devices rather
    than a layout defect; the `klayout` engine's `match` is this repo's
    acceptance gate.
  - See `layout/README.md` for what an LVS verdict here does and does not
    cover (e.g. substrate/well-tap body-terminal coverage is a named,
    standing caveat of the gf180mcu extraction deck, not specific to this
    layout). Note that file's own "Expected results" table still quotes the
    2026-08-17 report IDs and net/pin counts; the figures above are read
    directly from the committed 2026-10-28 JSON.
- **Area**: drawn **64,924.27 µm² (0.06492 mm²)**
  (`layout/bandgap_top/AREA.md`, re-measured 2026-10-30) — **PASS** against
  DR-0006's interim `< 0.066 mm²` ceiling with 1.6 % of headroom, and
  **FAIL** against the originally ratified `< 0.05 mm²`
  ([DR-0003](../../spec/decision-records/0003-target-spec-ratification.md)) by
  29.8 %. [DR-0005](../../spec/decision-records/0005-area-target-overrun.md)'s
  `< 0.085 mm²` proposal is **superseded by**
  [DR-0006](../../spec/decision-records/0006-area-target-narrowed-post-166.md),
  whose own header still reads `Status: proposed` even though its diff
  landed in `README.md` and in `area_report.py`'s `RATIFIED_TARGET_UM2`.
- **Schematic-level spec suite**: all six indexed spec lines pass against the
  amended (post-DR-0007) DUT —
  [`sim/suite/summaries/20261016-015258-1c4f2a2.md`](../../sim/suite/summaries/20261016-015258-1c4f2a2.md),
  rolled up over the pinned final-DUT records indexed in
  [`sim/suite/fleet-evidence-239.md`](../../sim/suite/fleet-evidence-239.md)
  (`design/bandgap_error_budget.md` §5's running tally through issues
  #96/#147/#151 and #209/DR-0007, §5a–§5f). Two qualifications travel with
  it: the Startup bench runs an embedded lumped-`R1` core rather than the
  canonical netlist, and the combined untrimmed-accuracy verdict is
  sensitive to the assumed `par_r` mismatch coefficient (§5). The Trim and
  Output-noise benches have **not** been re-run on the amended DUT.
- **Post-layout extracted**: output-reference and temperature-coefficient
  rows FAIL (§5 above); PSRR, line regulation, quiescent current, and
  startup rows PASS extracted; the mismatch-MC leg of the combined accuracy
  verdict and the trim-coverage bench have not been re-run against the
  extracted netlist at all (open work, not a claimed pass or fail). All of
  it predates DR-0007.
- **Graded signoff verdict**: the machine-graded record of record is
  [`signoff/README.md`](../../signoff/README.md) and the committed
  `signoff/reports/` verdict it produces; T1 item 7 (post-layout) is
  `unmet` there, and no `klt pex` report exists, so nothing in this document
  claims a body-biased extracted measurement.

## 7. Bench test plan

`measurements/` is empty pending tape-out (this repo's convention — see
`README.md` §History). The bench plan below mirrors the existing simulation
testbenches (`sim/output-voltage-tc/`, `sim/psrr-dc/`, `sim/line-regulation/`,
`sim/iq/`, `sim/startup/`, `sim/trim-coverage/`) so that a measured result can
be compared line-for-line against the same spec rows and PVT convention used
in simulation.

1. **DC output reference vs. supply and temperature.** Sweep `vdd` over
   2.97–3.63 V at each of −40 °C / 27 °C / 125 °C (temperature chamber,
   precision multimeter or source-measure unit on `vref`); compute the
   temperature-coefficient box statistic the same way
   `sim/output-voltage-tc/` does (`(Vmax − Vmin)/(V_27C × ΔT) × 1e6`).
   Compare directly against the 1.176–1.224 V window and the 50 ppm/°C
   limit.
2. **Line regulation.** At fixed 27 °C, sweep `vdd` continuously across
   2.97–3.63 V and record the resulting `vref` box
   (`(Vmax − Vmin)/0.66 V`), against the <1 mV/V limit.
3. **Quiescent current.** Measure total supply current into `vdd` at each
   PVT corner reachable on the bench (temperature via chamber; process
   corner is not directly selectable post-fab, so this measures whichever
   die/lot is on hand — record it as such rather than claiming full
   process-corner coverage), against the <50 µA limit.
4. **PSRR.** Inject a small-signal AC ripple on `vdd` (network/spectrum
   analyzer or lock-in referenced to the injected tone) and measure the
   `vref` ripple transfer function from DC through 1 MHz; report the DC–1 Hz
   asymptote and the 1 kHz figure against the >60 dB limit, and the 1 MHz
   figure against the >30 dB stretch goal.
5. **Startup transient.** Step `vdd` from 0 V to nominal (fast supply
   ramp or a switch) and capture `vref`'s transient on an oscilloscope;
   measure time to within 1% of the settled value against the <1 ms limit,
   at as many of the accessible PVT corners as the bench setup allows.
6. **Trim characterization.** Because trim is a mask/metal-option
   (pre-fabrication) choice rather than a runtime input (§3), trim
   characterization on measured silicon means comparing the single trim
   code drawn into the fabricated die against the corresponding
   `sim/trim-coverage/` schematic prediction for that code, not sweeping
   codes on one packaged part.
7. **Reconciliation.** Every measured result is logged into a future
   `measurements/` record and reconciled against both the schematic-level
   and post-layout-extracted predictions in this document's spec table —
   per `CLAUDE.md`, no claim is recorded without this testbench-style
   comparison, and PVT-corner coverage is reported honestly (bench
   measurement typically covers far fewer discrete corners than the 81-point
   simulated grid; the gap is stated, not hidden).

## References

- `README.md` — "Target specification (RATIFIED 2026-07-31)" table.
- Decision records: `spec/decision-records/0002-supply-voltage-scope.md`
  (3.3 V-only scope), `0003-target-spec-ratification.md` (the ratified
  table, including the `< 0.05 mm²` Area row),
  `0004-par-r-mismatch-coefficient-risk.md` (the mismatch-coefficient
  assumption the combined accuracy verdict is sensitive to),
  `0005-area-target-overrun.md` (**superseded by 0006**),
  `0006-area-target-narrowed-post-166.md` (interim `< 0.066 mm²` Area
  ceiling) and `0007-q2-array-dvbe-ratio.md` (**ratified 2026-10-02** —
  `core.Q2` as a 4× unit-PNP array, ΔVBE ratio input amended).
- Schematic evidence (final DUT, post-DR-0007):
  `sim/suite/fleet-evidence-239.md` (index and caveats),
  `sim/suite/summaries/20261016-015258-1c4f2a2.md` (roll-up),
  `sim/suite/combined/20261016-013300-999e5cf.md` (combined untrimmed
  accuracy), `sim/device-pnp-array/records/20261008-120404-44d1a83.md`
  (measured array ratio), `design/bandgap_error_budget.md` §5e/§5f.
- Pre-DR-0007 evidence, cited as such: `sim/postlayout-delta.md`,
  `sim/startup-extracted/`, `sim/trim-coverage/`, `sim/output-noise/`.
- Physical verification: `layout/README.md`,
  `layout/bandgap_top/AREA.md`,
  `layout/drc/reports/bandgap_top/20261028-065229-f32fe48.drc.json`,
  `layout/lvs/reports/bandgap_top/20261028-065214-f32fe48.lvs.json`,
  `signoff/block-manifest.json`, `signoff/README.md`.
- [issue #87](https://github.com/2AMLogic/gf180-bandgap/issues/87) (dVBE
  ratio divergence; decided by DR-0007, extracted re-run outstanding),
  [issue #94](https://github.com/2AMLogic/gf180-bandgap/issues/94)
  (T1 sim-validated tracking issue, gates tapeout on #87's resolution),
  [issue #204](https://github.com/2AMLogic/gf180-bandgap/issues/204)
  (DR-0007 phase B: regenerate the layout and record pinned extracted
  verification).
