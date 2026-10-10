# output-noise fleet capability report (issue #268)

This is a capability report and a diagnostic only. It is not a measurement: it
contains no DUT noise figure and no A6 verdict, and it changes no spec limit.
It records what the pinned `klt sim` request contract can return for the
`output-noise` bench, how the fleet adapter uses that, and what could not be
verified.

Evidence: `evidence/` (tool versions, PDK-free probe requests/reports/
waveforms, the batch-submit error, and a value-redacted single-corner contract
probe against the canonical DUT).

## Tool and backend

| Item | Value |
|---|---|
| Submitting client | `klt 0.7.0+g5e5b55992a7f` (`evidence/version.txt`) |
| Local engine (probes) | ngspice-46 |
| Batch backend | `KLT_SIM_BACKEND=batch`; worker klt version **not observed** (no capacity, see below). The last recorded worker was klt 0.5.0 (`sim/fleet-blockers/20261009-issue-239-runner-version-mismatch/`) |
| Request schema | `klt sim` request JSON (`netlist`, `engine`, `models`, `corners`, `analysis`, `measurements[]`, `options`); report `schema_version` 3 |

## What the contract supports (verified)

Every row below comes from a single-corner `--backend local` run. No grid was
run locally.

| Need | Supported route | Evidence |
|---|---|---|
| `noise` analysis | Scalar `analysis: {"kind": "noise", "args": "v(vref) vsup dec 20 ..."}` is emitted as-is, one analysis per corner | `resistor-probe/corner-default.cir` |
| Integrated noise (0.1-10 Hz) | `measurements[].expr` `noise2.onoise_total` | `resistor-probe/report-default.json`: 2.864464e-08 V = sqrt(4kT*5k*9.9) |
| Spectral density | `expr` `noise1.onoise_spectrum[i]` (plot-qualified, see #2893) | 9.103864e-09 V/sqrt(Hz) = sqrt(4kT*5k) |
| Band / spot frequency endpoints | `expr` `real(noise1.frequency[i])`, `length(noise1.frequency)` | 0.1 Hz, 10 Hz, 41 points |
| Forced unit mode | `options.ngspice_init: ["unset sqrnoise"]`, written as the corner's `.spiceinit` | `resistor-probe/report-*.json` |
| Runtime mode check | `expr` `$?sqrnoise` -> 0 (unset) / 1 (set) | both reports |
| Integrated-noise unit metadata | `artifacts.waveform` (`options.waveforms`) = the integrated plot: `plotname` `Integrated Noise`, `onoise_total` type `voltage` (amplitude). Under `set sqrnoise`: `Integrated Noise - V^2 or A^2`, type `voltage^2` | `resistor-probe/waveform-*.json` |
| Operating-point companion | `analysis: {"kind": "op", "args": ""}` + `expr` `op1.v(vref)`; waveform `Operating Point` | `dut-contract-probe/summary.json` |
| Supply corners | `corners.supply_v: {"vsup": [...]}` (`vsup` is `dc {vdd_val} ac 1`, so `alter` applies) | plan requests |
| Canonical DUT, end to end | `op`, `noise_1`, `noise_2` each ran one corner `pass` with every measurement present, the expected units, `n_points` 41/121, `sqrnoise_set` 0, exact endpoint frequencies | `dut-contract-probe/summary.json` (values redacted) |

## What the contract does not provide (gaps)

1. `.meas` has no `noise` type, so every noise value has to be a
   `measurements[].expr` (klayout-tools #2938). Runners that predate `expr`
   (klt 0.5.0) reject the request outright.
2. After `noise`, `expr` sees the integrated plot. Spectrum values need
   hard-coded `noise1.` plot prefixes (klayout-tools #2893), and
   `analysis_steps[]` cannot reference the spectrum plot at all. The adapter
   therefore uses one scalar request per noise card.
3. The waveform artifact is the integrated plot only. The spectrum (frequency
   + density) is never returned as an artifact, so spot densities exist only
   as printed `expr` values (7 significant digits).
4. **Unit metadata.** `measurements[].unit` is the caller's label, echoed
   unchanged. A squared (`set sqrnoise`) value labelled `V` passes with no
   diagnostic. The report does not record the noise representation. Filed as
   **2AMLogic/klayout-tools#3006** (generic tool gap). The adapter works
   around it in two ways: it forces the mode with `ngspice_init`, and it
   verifies the mode per corner from the `$?sqrnoise` probe and the
   integrated artifact's plot name and variable type. Any disagreement makes
   the corner INVALID.
5. A relative `-o` directory makes the corner's own `write`/log paths miss
   (`resistor-probe` first attempt, not kept). The adapter always passes
   absolute paths.

## Batch submit (not verified)

Two submits of the PDK-free 3-temperature probe (`evidence/batch-probe/`) on
2026-10-10 failed before any job ran:

```
batch backend failed: batch-fleet-provision.sh launch failed (exit 1): error: no capacity in any of the 30 pools after 3 attempt(s) -- code batch_no_capacity
```

Nothing was run locally as a substitute. Whether the batch worker accepts
`expr` + `ngspice_init` and returns the artifacts is still open. The ingestor
does not trust it either way: it refuses any report whose
`runner_compatibility` is not `match` or whose worker version is unrecorded
(`fleet_common.provenance_problems`).

## How the adapter uses this

- **Requests** (`sim/tools/mk_klt_fleet_request.py output-noise WORK`): three
  requests, each process x supply x temperature (81 units): `op`, `noise_1`
  (`dec 20 0.1 10`) and `noise_2` (`dec 20 0.1 100k`). All of them come from
  tb.json through `noise_spec()`. Each request evaluates the tb.json `measure`
  expression with its plot renumbered (`noise3` -> `noise1`) and its scale
  stripped, so the fleet returns raw SI values.
- **Ingestion** (`sim/tools/fleet_ingest.py output-noise WORK`): multiplies by
  tb.json's own scale (#252: `* 1e6` -> uVrms, `* 1e9` -> nV/sqrt(Hz), no
  square root). It takes the integrated total and `vref_op` at full precision
  from the waveform, and uses the printed `expr` as a cross-check. A corner is
  INVALID on any of: missing artifacts, null or non-finite values, `sqrnoise`
  set, squared-mode artifacts, a reported unit other than the plan's, the
  wrong point count, an endpoint outside its window, or `vref_op` outside its
  window. Missing corners/requests, identity mismatches (DUT, deck, testbench,
  tb.json, worker/client klt) and a grid spread under the tb.json floor make
  the run INCOMPLETE. A complete run is `MEASURED`, which means measurement
  completion only. It is never PASS: A6 has no ratified threshold, and the
  Output-noise row stays unclaimed.
- PDK-free fixtures: `sim/tests/test_fleet_ingest.py` (`NoiseRequests`,
  `NoiseIngest`, `NoiseFails`).
