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
pins** — there is no fourth physical pin; the LVS reference netlist's
`vsubs` terminal is a deck-synthesized substrate net used only for
extraction/LVS bookkeeping (`layout/lvs/bandgap_top.ref.spice`), not a drawn
I/O.

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
equal collector currents into a PNP pair of unequal emitter area (nominal
drawn ratio: see §5's dVBE caveat) through a resistor ladder, producing a
PTAT voltage across a sense resistor; that PTAT term is summed with the
PNP's own CTAT base-emitter voltage at the output node. The telescopic-
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

**No 5.0 V characterization exists or is claimed** — see the "Supply / 5.0V
rail" row below; this is the one row this document scopes as *not
evaluated* rather than met/unmet, per
[DR-0002](../../spec/decision-records/0002-supply-voltage-scope.md).

| Row | Typ (schematic, tt/27°C/3.3V) | Min/Max (schematic, 81-corner) | Post-layout extracted | Schematic verdict | **Extracted (post-layout) verdict** |
|---|---|---|---|---|---|
| Output reference (1.20 V ±2% untrimmed, 1.176–1.224 V) | 1.19249 V | 1.18142 V – 1.20185 V | 1.23361 V (typ), up to 1.25187 V worst-case | **MET** (81/81) | **UNMET** — fails both the low bound (`res_ss_-40c_3.63v`, 1.2219 V vs. floor irrelevant here; the failure is high-side) and the high bound (`bjt_ss_125c_2.97v`, 1.25187 V vs. 1.224 V max) |
| Output reference, combined basis (mismatch MC N≥300 + process corners, 3σ) | — | 81/81 corners, worst margin **+2.194 mV** (`design/bandgap_error_budget.md` §5c/§5d, post-#147/#151) | not re-run post-layout | **MET** | **not evaluated** — the mismatch-MC leg (`sim/mc-untrimmed/`) has no post-layout-extracted counterpart; only the deterministic-corner leg has been re-run extracted, and that leg alone already fails (row above) |
| Temp coefficient (−40…125 °C, <50 ppm/°C box) | 13.6851 ppm/°C | 13.56 – 29.84 ppm/°C | 62.59 ppm/°C (typ), up to 90.22 ppm/°C worst-case | **MET** (81/81) | **UNMET** — worst extracted corner (`bjt_ss_-40c_3.30v`, 90.22 ppm/°C) is 1.8× the 50 ppm/°C limit |
| PSRR (>60 dB DC–1 kHz) | 111.755 dB (1 Hz) / 96.8106 dB (1 kHz) | worst 74.2966 dB (1 Hz) / 74.215 dB (1 kHz), both `res_ss_125c_3.63v` | worst 74.7351 dB (1 Hz) / 72.896 dB (1 kHz) | **MET** (81/81) | **MET** (81/81) |
| Line regulation (<1 mV/V, DC, 2.97–3.63 V) | — | worst 0.0399 mV/V (`res_ss_125c_3.30v`) | worst 0.0373 mV/V | **MET** (27/27) | **MET** (27/27) |
| Supply / output reference over supply (3.3 V ±10%: Vref stays 1.176–1.224 V across 2.97–3.63 V) | — | same as Output reference row | same as Output reference row | **MET** | **UNMET** (same cause as Output reference) |
| Supply / 5.0V rail (stretch: "also 5V flavor"; Challenge #5 brief expects 3.3–5.0V analog-rail operation) | — | — | — | **not evaluated** | **not evaluated** — no 5.0V device flavor, testbench, or layout exists per DR-0002 (3.3V-only, wave 1); Challenge #5's brief text expects analog blocks to operate 3.3–5.0V, and this design has not been shown to |
| Quiescent current (<50 µA) | 20.7144 µA | worst 34.0054 µA (`ff_125c_3.63v`) | worst 36.2719 µA | **MET** (81/81) | **MET** (81/81) |
| Trim (1-point, ≥±5% range, ≤0.25%/step at 27°C) | span 178.2 mV, LSB 2.83 mV | span 135.4–240.7 mV over 81 corners | not re-run post-layout | **MET** (81/81) | **not evaluated** — no post-layout-extracted trim-coverage bench exists yet |
| Startup (self-starting all corners, <1 ms to 1%) | — | worst 43.97 µs (`fs_-40c_2.97v`) | worst ~15.6 µs (well under 1 ms) | **MET** (81/81) | **MET** (81/81) |
| Area (<0.05 mm²) | — | drawn 0.06251 mm² (62,505.60 µm²) | same (physical layout) | n/a (not a sim claim) | **UNMET** — 25.0% over the ratified target; [DR-0005](../../spec/decision-records/0005-area-target-overrun.md) proposes an interim 0.085 mm² ceiling but is `Status: proposed`, not ratified, so the ratified 0.05 mm² row still reads FAIL |
| PSRR @ 1 MHz (stretch, >30 dB) | — | not separately gated | not separately gated | reference only | reference only |
| Output noise, Load (open items, no numeric target ratified) | — | — | — | **not claimed** | **not claimed** — `sim/suite/spec.py`'s `NOT_CLAIMED_HERE` list; open per README.md amendments A6/A7 |
| Long-term drift | — | — | — | **not specified** (canary block) | **not specified** |

### The output-reference and temperature-coefficient rows are UNMET at the post-layout level

This is the single most important caveat in this document, per the epic's
own instruction, and it is restated here rather than left to the table
alone: **`bandgap_top` is DRC-clean (0 violations) and LVS-matching, but its
parasitic-extracted netlist currently fails the ratified output-reference
and temperature-coefficient spec rows.** DRC/LVS-clean GDS and post-layout
spec conformance are two different claims, and only the first is currently
true for this row pair.

- Full per-corner data: [`sim/postlayout-delta.md`](../../sim/postlayout-delta.md)
  (records paired: `sim/output-voltage-tc/records/20260803-100317-ba091ea.md`
  schematic vs. `sim/output-voltage-tc/records/20260803-055357-31e5efc.md`
  extracted, 81/81 corners aligned).
- Root cause: [issue #87](https://github.com/2AMLogic/gf180-bandgap/issues/87)
  — the drawn PNP array realizes Q2 as four parallel `pnp_05p00x05p00` unit
  devices (for common-centroid matching, per `layout/floorplan.md` §4.1),
  which measures an effective dVBE ratio of **4.03**, against the
  schematic's single `pnp_10p00x10p00` device at **3.63**. That +8% dVBE
  gain is a first-order error on `Vref = VBE3 + (R1+trim)/R2 · dVBE`. This
  is characterized as a device-physics/schematic-vs-layout-intent
  divergence, not a DRC or extraction defect — LVS cannot catch it because
  the LVS reference is itself derived from the drawn layout
  (`layout/lvs/make_reference.py`), so it structurally matches four drawn
  units against four reference units regardless of which side's intent is
  "correct."
- Resolution is blocked on a spec/design decision (issue #87: resize the
  schematic's PNP to a 4.00 ratio, or redraw the layout to a single 10×10
  device) and a subsequent passing extracted-netlist re-run
  ([issue #94](https://github.com/2AMLogic/gf180-bandgap/issues/94)).
  **Tapeout is not scheduled** pending that decision and re-verification.

No other row in this table is relaxed, omitted, or presented more favorably
than its cited evidence supports.

## 6. Verification status summary

- **DRC**: clean, 0 violations
  (`layout/drc/reports/bandgap_top/20260817-125327-972f6d5.drc.txt`).
- **LVS**: `status: match` on both independent comparators —
  `klt lvs` (klayout engine): 164/164 devices, 92/92 nets, 4/4 pins matched
  (`layout/lvs/reports/bandgap_top/20260817-125346-972f6d5.lvs.json`, per
  `layout/README.md`'s "Expected results" table); the cross-check run
  (`layout/lvs/reports/bandgap_top/20260819-070132-1e66285.lvs.txt`) reports
  the same klayout `match` verdict with 14 recorded warnings (12
  `topology`, 2 `device.body_unverified` — both documented as benign
  connectivity/deck-coverage notes, not netlist errors, in that report and
  in `layout/README.md`'s "What the LVS verdict does and does not cover"),
  plus an independent `netgen` comparator that also reads `match` once a
  netgen-only dummy-device pairing artifact is accounted for (issue #168).
  See `layout/README.md` for the full detail on what this LVS verdict does
  and does not cover (e.g., substrate/well-tap body-terminal coverage is a
  named, standing caveat of the gf180mcu extraction deck, not specific to
  this layout).
- **Area**: FAIL against the ratified `<0.05 mm²` target — drawn
  62,505.60 µm² (0.06251 mm²), 25.0% over budget
  (`layout/bandgap_top/AREA.md`); an interim `<0.085 mm²` revision is
  proposed but not ratified
  ([DR-0005](../../spec/decision-records/0005-area-target-overrun.md)).
- **Schematic-level spec suite**: every sim-verifiable ratified row passes
  (`python3 sim/run_suite.py`; `design/bandgap_error_budget.md` §5's
  running tally through issues #96/#147/#151).
- **Post-layout extracted**: output-reference and temperature-coefficient
  rows FAIL (§5 above); PSRR, line regulation, quiescent current, and
  startup rows PASS extracted; the mismatch-MC leg of the combined accuracy
  verdict and the trim-coverage bench have not been re-run against the
  extracted netlist at all (open work, not a claimed pass or fail).

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
- `spec/decision-records/0002-supply-voltage-scope.md`,
  `spec/decision-records/0003-target-spec-ratification.md`,
  `spec/decision-records/0005-area-target-overrun.md`.
- `sim/postlayout-delta.md`, `design/bandgap_error_budget.md`.
- `layout/README.md`, `layout/bandgap_top/AREA.md`.
- [issue #87](https://github.com/2AMLogic/gf180-bandgap/issues/87) (dVBE
  ratio divergence), [issue #94](https://github.com/2AMLogic/gf180-bandgap/issues/94)
  (T1 sim-validated tracking issue, gates tapeout on #87's resolution).
