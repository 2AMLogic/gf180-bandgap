# Trim network: sizing and coverage (issue #14)

This document is the sizing rationale the ratified mechanism
([DR-0001](../spec/decision-records/0001-bandgap-topology-selection.md),
"Trim strategy" subsection) and `README.md`'s ratified Trim row point to:
*"1-point resistor trim (binary-weighted segments per DR-0001), range
≥ ±5%, resolution ≤ 0.25%/step (≥5 bits equiv.), magnitude only, performed
at 27 °C."* It ties that ratified target to `sim/mc-untrimmed/`'s untrimmed-spread
data (the sizing input), `design/bandgap_trim.sch` / `bandgap_core.sch` (the
implementation) and `sim/trim-coverage/` (the coverage evidence).

## 1. Phase 1 — scoping decision (no changes needed)

Phase 1 of #14 asked whether wave 1 reserves trim hooks even if trim isn't
productized yet. That question is already answered: DR-0001's trim-strategy
subsection — ratified as part of #1 (`spec/decision-records/0003-target-spec-ratification.md`)
— adopts *"a minimal resistor-trim network — a small number of
binary-weighted trim resistor segments, switched in via probe-pad straps or
a simple fuse/metal-option selection at test"* and explicitly rejects a
full digital/OTP calibration system for wave 1. `README.md`'s ratified
target-spec table already carries the resulting Trim row. No new or
amended decision record is needed; this document and the schematic/netlist
changes below are the phase 2 (design) follow-through DR-0001 already
called for.

The reserved tap point on the core resistor network is node `tn0`
(`design/bandgap_core.sch`): the output-branch summing resistor `R1` no
longer runs directly to `vref`, it runs to `tn0`, and the trim subcircuit
(`XTRIM`) picks up from `tn0` to `vref`. That is the "reserved tap point"
phase 1's acceptance criteria asked #8's network to carry.

## 2. Phase 2 sizing input — untrimmed spread from #13/#14's MC record

**Source**: `sim/mc-untrimmed/records/20260801-053436-6bbbdb7.md`, `mm_all`
group (full device-level mismatch — MOS + BJT + resistor together — on
`bandgap_top`, #10's final offset-budgeted amplifier and #11's startup
branch, **no trim network in the DUT** — this is the pre-trim baseline the
trim range must absorb). This record supersedes the provisional-amp record
(`20260801-033856-7c40876`) per the caveat #13 itself carried; it is the
first mm_all record run against the current (final-amp) `bandgap_top`.

| T (°C) | mean Vref (V) | 1σ (mV) | 3σ (mV) | 3σ (% of 1.20 V) |
|---|---|---|---|---|
| −40 | 1.21689 | 11.1342 | 33.403 | 2.784% |
| 27 | 1.22776 | 11.0821 | 33.246 | 2.771% |
| 125 | 1.23808 | 11.3361 | 34.008 | 2.834% |

The ratified Trim row's corner binding is **27 °C** (a 1-point trim is
performed once, at test) — so the number the trim range is *directly* sized
against is the 27 °C row (33.246 mV 3σ). All three temperatures land within
a narrow band (33.2–34.0 mV), so sizing against the 27 °C figure carries
essentially no risk from temperature-dependent drift of the mismatch
distribution itself.

**Sensitivity ranking** (same record): MOS+BJT mismatch dominates resistor
mismatch by roughly an order of magnitude at every temperature
(resistor-only 3σ ≈ 3.2–5.6 mV vs. MOS+BJT-only 3σ ≈ 30.1–30.6 mV). A
resistor trim still corrects the *combined* spread, not just the
resistor-only component: per `bandgap_core.sch`'s own derivation, `vref =
VEB(Q3) + I·(R1 + Rtrim)` with the PTAT current `I` set entirely by the
`R2`/`Q1`/`Q2` loop, independent of what sits in the output branch — so the
trim resistor is a magnitude-only correction on the sum of *every* error
source that lands on `vref`, wherever it originates (amplifier offset, MOS
mirror mismatch, PNP mismatch, or resistor mismatch itself). The trim range
below is therefore sized against the `mm_all` (combined) spread, not the
resistor-only column.

## 3. Required range and resolution

- **Range** (ratified floor): ≥ ±5% of 1.20 V = ±60 mV, i.e. ≥ 120 mV total
  span, code 0 → code 63.
- **Range** (mismatch-driven floor): the trim must be able to null a die
  whose untrimmed offset from the group mean is as large as ±3σ at 27 °C,
  i.e. ≥ ±33.246 mV each side of the nominal (default-code) point, ≥ 66.5 mV
  total. The ratified ±5% floor (120 mV) already exceeds this by ~1.8×, so
  the ratified spec is the binding constraint, not the raw MC number — the
  design below still reports both floors and the margin against each,
  because the ratified floor was set independently of this circuit's actual
  measured spread and it is worth confirming it stayed the tighter one.
- **Resolution** (ratified cap, binds at 27 °C only): ≤ 0.25% of 1.20 V =
  3.00 mV/step, ≥ 5 bits equivalent (i.e. ≥ 32 codes covering the range).

## 4. Implementation: 6-bit unit-segment binary-weighted ladder

`design/bandgap_trim.sch` (subcircuit `bandgap_trim`, pins `bot`/`top`/`sub`,
inserted `tn0 → vref` in `bandgap_core.sch`): **63 identical `ppolyf_u` unit
segments** (`W=2 µm`, `L=1.215 µm`) in one series string, tapped after 1, 3,
7, 15, 31 units into six groups of 1/2/4/8/16/32 units (weights
2⁰…2⁵), each group shunted by one strap `RS0`…`RS5` modeling a
metal-option/probe-pad link (closed → group shorted out, open → group in
circuit). The trim code (0..63) selects how many unit segments remain in
circuit: `Rtrim(code) = code · R_unit`. Default code is **32** (MSB group
only), chosen so that `R1 (230.180 µm) + 32 unit segments` reproduces the
pre-trim drawn 280 µm summing resistor to within a fraction of an ohm — so
every record taken against the schematic's default state (i.e., every
record from #8/#10/#11 and this repo's whole existing test suite) stays
electrically valid; the code that actually centers a given die's `vref`
near 1.200 V is the wafer-probe 1-point trim, not the schematic default.

**Update (#61).** The unit-segment length and `R1`'s length above are #8's
pre-trim baseline geometry and are retained unedited here. Both were
co-scaled by `k = 2` in #61 to close the ratified quiescent-current row
(`R1`: 230.180 µm → 460.701871 µm; unit segment: 1.215 µm → 2.771871 µm,
each length *solved* for double the resistance rather than doubled directly,
since `ppolyf_u` is a compound device) — see
`design/bandgap_error_budget.md` Sec 5a. This is a current-and-resistance
rescaling, not a ladder-structure change: the unit segments are still
identical, the group weights are still exact powers of two by construction,
and the trim step's value in volts (`I·R_unit`) is unchanged because `R_unit`
doubled exactly as `I` halved — `sim/trim-coverage/`'s re-run confirms this
(span and per-step resolution both unchanged within simulation noise,
record [`20260801-231346-960f726`](../sim/trim-coverage/records/20260801-231346-960f726.md)).

**Why identical unit segments and not six differently-sized resistors**: a
`ppolyf_u` instance is a compound device — body resistance proportional to
drawn length, plus a fixed per-instance terminal/contact resistance
(measured on this PDK at `W=2 µm`: `R = 179.547·L_µm + 61.382 Ω` at
tt/27 °C). Six single instances sized to hit exact `2^b` ratios at tt/27 °C
do not hold those ratios at other corners, because the contact-resistance
fraction differs by bit (the LSB instance is mostly contact resistance,
the MSB instance is mostly body resistance) and the two terms skew
differently over process/temperature. This was measured, not assumed: an
earlier six-different-length version of this ladder read an MSB weight of
58.6–68.9 LSBs (instead of the intended 64.0) across the 81-point PVT grid
— at the high end that opens a real, unreachable gap at the code-31/32
transition, i.e. a trim ladder with a dead zone. Unit segments cannot do
that: every group is an integer count of the identical physical device, so
the `2^b` ratios are exact by construction at every corner, and the ladder
is monotonic by construction. The cost is a larger aggregate contact-resistance
fraction in the output branch (63 terminal pairs instead of one).

`RS0`…`RS5` are not fabricated devices — each is a behavioral resistor
(`1e-3 Ω` when the group is shorted out, `1e12 Ω` when the group is left in
circuit) standing in for a metal-option link or probe-pad strap, decoded
from the subcircuit-local parameter `trim_code`. This is exactly the
verification-time modeling `sim/trim-coverage/` sweeps via `alterparam` —
see `sim/trim-coverage/testbench/tb_trim_coverage.spice` for the mechanism.
The physical realization of the strap (metal-option mask select vs.
laser/e-fuse) is a layout/test decision for #16 and the future wafer-probe
calibration-procedure issue DR-0001 flags as follow-on work; it does not
change this sizing.

## 5. Coverage evidence

**Record**: `sim/trim-coverage/records/20260801-061650-083d402.md`. Bench: `sim/trim-coverage/`,
81-point full PVT grid (−40/27/125 °C × 2.97/3.30/3.63 V × 9 process
corners: `tt`, `ff`, `ss`, `fs`, `sf`, `res_ff`, `res_ss`, `bjt_ff`,
`bjt_ss`). The bench sweeps 9 codes per corner (`0, 1, 2, 4, 8, 16, 32, 63`,
plus `22` — the code nearest 1.200 V at tt/27 °C, carried across the whole
grid to report trimmed accuracy over PVT) and reports:

| Check | Ratified/derived requirement | Result across the 81-point grid | Margin |
|---|---|---|---|
| Span (code 0 → 63) | ≥ 120 mV (ratified ±5% floor) | 132.6–240.6 mV | ≥ 1.10× the ratified floor everywhere; ≥ 1.9× the mismatch-driven 66.5 mV floor everywhere |
| Trim reach, either direction from default | ≥ 33.25 mV (27 °C mismatch 3σ) | `trim_down_mv` 67.3–122.2 mV, `trim_up_mv` 65.2–118.4 mV | ≥ 1.9× the 27 °C mismatch-driven need in the worst corner |
| Resolution (LSB), 27 °C rows only (ratified binding) | ≤ 3.00 mV/step | 2.69–2.94 mV/step across process/supply at 27 °C | inside the cap at every 27 °C point |
| Resolution (LSB), full grid (envelope, not itself a spec line) | monotonic, non-degenerate | 2.10–3.82 mV/step | grows PTAT with temperature, as expected — never collapses or reverses sign |
| Binary weighting (`w5_lsb`, MSB group vs. 1 LSB) | 32.0 ± 0.1 | 31.94–32.01 | exact by construction, confirmed empirically |
| Linearity residual (superposition check) | \|residual\| ≤ 1 mV | −0.020 … +0.010 mV | confirms the trim is magnitude-only, per §2's transfer-function argument, not assumed |

**Overall: PASS**, all 81 corners. Record:
`sim/trim-coverage/records/20260801-061650-083d402.md`.

## 6. No spec relaxation

Every check above compares against the ratified `README.md` Trim row and
the mismatch-driven floor derived from #13's own data — none of the
thresholds were adjusted to make this design pass, per CLAUDE.md. The
design closes both the ratified ±5%/0.25% floor and the mismatch-driven
floor with margin; there is no shortfall to escalate on this issue.

## 7. Explicitly out of scope (deferred, per DR-0001)

- A digital/OTP calibration system (calibration DAC, non-volatile fuse
  bank, register interface) — DR-0001 rejects this for wave 1.
- The wafer-probe calibration *procedure* itself (how a tester picks the
  code, timing, equipment) — DR-0001 notes this deserves its own future
  issue; this issue only delivers the trim *network* and demonstrates its
  range/resolution covers the untrimmed spread.
- Trim-hook placement/matching in the physical floorplan — #16's scope,
  informed by this document's segment count and the `tn0` tap location.
