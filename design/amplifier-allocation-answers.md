# Amplifier allocation answers (Q4–Q6) for gf180-opamp DR-0007

`2AMLogic/gf180-opamp` cannot set its input-offset and noise spec rows: its
[DR-0007](https://github.com/2AMLogic/gf180-opamp/blob/main/spec/decision-records/0007-noise-offset-requirement-basis.md)
§3.3 requires each consumer to post its allocated limits on its own tracker
(blocked issue: [2AMLogic/gf180-opamp#62](https://github.com/2AMLogic/gf180-opamp/issues/62)).
This note answers the three questions from committed evidence only. It is a
compilation and currency check, not a new derivation: no spec row, decision
record or threshold is proposed or changed, and no new simulation record is
added. (Not to be confused with this repo's own
[DR-0007](../spec/decision-records/0007-q2-array-dvbe-ratio.md), the Q2-array
record.)

**Amplifier slot.** This block keeps its in-tree `bandgap_amp`
(telescopic-cascode OTA, #42 topology, #147/#151 sizings); `reuse.lock.json`
carries the sibling `2AMLogic/gf180-opamp` at status `evaluate`. Any amplifier
in this slot must meet the Q4 input-offset allocation for the untrimmed budget.

## Q4 — input-offset share of the untrimmed accuracy budget

| Quantity | Value | DUT status | Source |
|---|---|---|---|
| Input-referred random offset | **0.5319 mV (3σ)** (σ = 0.1773 mV) | budget figure, historical schematic | `design/bandgap_error_budget.md` §2.2 (post-#151) |
| At VREF | **8.58 mV (3σ)** = 0.5319 mV × 16.13 V/V | same | §2.2, §2.7b `#151` column — the budget table in force |
| Systematic reserve | **+2.00 mV** (3σ-equivalent, unverified placeholder) | same | §2.3 |
| Offset-to-VREF gain (DC) | **16.13 V/V** mean, 16.02–16.21 over 81 PVT corners | **historical DUT** (clean run, #42-era core) | §2.4; record `sim/amp-offset-sensitivity/records/20260801-073817-a7fd16a.md` (mean 16.1293) |
| Later gain re-run | 16.0979 V/V mean, 16.0473–16.1354, 81 corners | **historical DUT**, dirty working tree | record `sim/amp-offset-sensitivity/records/20260816-183233-0acc856.md` (#151 mirror sizing; flags itself "not citable as a clean-tree result") |
| ±0.5 % trimmed budget | **not budgeted** | — | `design/bandgap_error_budget.md` allocates the untrimmed ±2 % budget only |

The ±2 % untrimmed window is ±24 mV (3σ) at VREF. The amplifier's random line
is the **8.58 mV** entry of the §2.7b table. Random contributors (amplifier,
core mirror, cascode, resistor, PNP) combine by **RSS**; the +2.00 mV
systematic reserve is added linearly **after** the RSS (§2.7b: 11.42 mV random
RSS + 2.00 mV = 13.42 mV total).

**DUT currency.** Both gain records' netlist snapshots instantiate one
`pnp_10p00x10p00` at Q2, i.e. they predate the post-DR-0007 core (Q2 = 4×
`pnp_05p00x05p00` array, `R2`/`R1` retuned by #209 — §5e/§5f). The amplifier
geometry the 0.5319 mV figure is scaled to is current (DR-0007/#209 touched
core devices only), but the 16.13 V/V multiplier was measured on the
pre-array core, and §5e explicitly does not re-take the sensitivity tables
after the array change (ρ expected to fall, ~0.4365 → ~0.418). Label both
records **historical DUT**; the 8.58 mV line is the budget in force, carried
from the historical schematic, not a post-DR-0007 measurement.

## Q5 — 0.1–10 Hz output-noise threshold and noise gain

- **Threshold: not budgeted — threshold TBD, awaiting operator ruling (A6).**
  `spec/tbd-row-evidence.md` Row 2 holds the open operator question and a
  candidate derivation — X ≤ (0.1 × 3.0 mV) / 6.6 ≈ **45 µVrms** (0.1–10 Hz
  integrated) — explicitly labelled **unratified**. Row 2's 2026-10-09
  "Unit-contract correction" (issue #252) settled the bench units
  (`onoise_total` is V rms; the historical records square-rooted twice) but
  states that no current-DUT noise record exists and no A6 threshold or pass
  is claimed. No threshold or amplifier share is proposed here.
- **Amplifier-input-to-VREF noise gain: not stated.** The only committed
  input-to-VREF transfer is the Q4 offset sensitivity above, and it is the
  same transfer **at DC** (a series-offset measurement, §2.4). No committed
  record extends it across the 0.1–10 Hz noise band.

## Q6 — amplifier-input common-mode voltage

- Nominal point (TT, 27 °C, 3.30 V): **`sns1` = 0.704787 V, `sns2` =
  0.704621 V** (mean 0.704704 V) — record
  `sim/bandgap-loop-smoke/records/20260802-043753-5066d85.md` (clean tree).
  `sns1` = VEB(Q1) = `bandgap_amp.in_n`, `sns2` = top of R2 =
  `bandgap_amp.in_p` (`design/bandgap_operating_point.md` §1;
  `design/bandgap_error_budget.md` §2.1). It is the latest record in that
  experiment's `records/` directory and supersedes the older nominal table in
  `design/bandgap_operating_point.md` §3, whose own convention is to cite the
  latest ID. **Label: historical DUT** — its netlist snapshot also predates
  the DR-0007 Q2 array.
- Over the requested −40…125 °C, 2.97–3.63 V range the common mode is
  **unreported**: no committed record measures `sns1`/`sns2` at any corner
  other than tt / 27 °C / 3.30 V (`sim/core-mirror-sensitivity/` records
  carry only transfer sensitivities involving `sns1`, not its operating
  voltage). Uncovered on any DUT: −40 °C and 125 °C, 2.97 V and 3.63 V, and
  every process corner except tt.

## Sources

- `design/bandgap_error_budget.md` §2.2, §2.3, §2.4, §2.7b, §5e, §5f
- `sim/amp-offset-sensitivity/records/20260801-073817-a7fd16a.md` (clean, #42 amp)
- `sim/amp-offset-sensitivity/records/20260816-183233-0acc856.md` (dirty tree, #151 sizing)
- `spec/tbd-row-evidence.md` Row 2 and "Unit-contract correction (2026-10-09, issue #252)"
- `sim/bandgap-loop-smoke/records/20260802-043753-5066d85.md`
- `design/bandgap_operating_point.md` §1, §3
- `reuse.lock.json` (in-tree `bandgap_amp`, sibling status `evaluate`)
- `README.md` target-spec table (untrimmed ±2 % row; trimmed ±0.5 % column, no amplifier split)
