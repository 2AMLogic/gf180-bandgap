# Diagnostic-bench fleet rerun — preparation plan (#362)

Part of #239 and #211. **Preparation only.** Nothing was simulated, probed,
submitted or provisioned to write this; no adapter code, record, manifest, DUT
or spec file is changed by it. Completing this plan is not evidence completion,
does not close #239 / #211 / #203, and relaxes or adds no numerical limit.

Verification stamp: every figure below was read from the tree at
`origin/main` @ `d97db470` on 2026-10-20 (checkout clean, equal to origin)
unless marked **not traced** or **unverified**. The only commands run were file
reads, `sha256sum` and the static `python3 -I sim/tools/check_embedded_cores.py`
(10/10 embedded cores in sync).

## 1. Scope and benches

The six active diagnostic benches that embed `bandgap_core`
(`sim/embedded-core-inventory.md`): `amp-psrr`, `core-psrr-ideal-amp`,
`amp-offset-sensitivity`, `amp-loop-stability`, `core-mirror-sensitivity`,
`bandgap-loop-smoke`. They are intentional experimental variants. Their input
synchronization (`check_embedded_cores.py`) is a parameter check, not rerun/PVT
evidence, and not a byte-identity or equivalence claim.

### 1.1 Current harness inventory (as of `d97db470`)

| Piece | Location | Covers the six? |
|---|---|---|
| Request generator | `sim/tools/mk_klt_fleet_request.py` — `BENCHES` line 129 = `psrr-dc, line-regulation, startup, iq`; `CHARACTERIZATION_BENCHES`, `MEASUREMENT_BENCHES` (noise); `build_plan` line 468; the only embedded-core branch is `embedded = bench == "startup"` (line 483) | No |
| Ingest / assessment | `sim/tools/fleet_ingest.py` — `BENCHES` line 66, `SPEC_CHECKS` line 76, `MEASUREMENT_BENCHES` + `MEASURED` verdict | No |
| Shared helpers | `sim/tools/fleet_common.py` — `provenance_problems`, `hash_problems`, `collect_units`, `report_identity_problems`, `execution_rejection` | Reusable as-is |
| Offline tests | `sim/tests/test_fleet_ingest.py` (synthetic reports/waveforms, stub PDK include, no network) | No cases for the six |
| Static sync check | `sim/tools/check_embedded_cores.py` | Already covers all six |

None of the six is in any of those tables. The missing adapters are a design-repo
gap, not a klt defect.

### 1.2 Manifest facts per bench (from each `tb.json`)

| Bench | Corner set / points | Analysis | Checks (threshold source: tb.json, unchanged) | Core realization |
|---|---|---|---|---|
| `amp-psrr` | `full` (9 process) × 3 T × 3 V = 81 | `ac dec 20 0.01 1k` + `let`/`while` worst-PSRR scan | `psrr_worst_db ≥ 60` | lumped R1 (545.639857u) + `sim/dut/bandgap_amp.spice` |
| `core-psrr-ideal-amp` | 81 | same `ac` sweep | `psrr_worst_db ≥ 60` — tb.json states **not a spec claim** | lumped core, amp replaced by ideal `Efb fb 0 sns2 sns1 1e6`; no DUT key |
| `amp-offset-sensitivity` | 81 | `dc vos -2m 2m 4m` (2 points) | `dvref_dvos` in [8, 25] | lumped core + amp; `vos vos_node sns1` |
| `amp-loop-stability` | 81 | `ac dec 15 0.1 2000meg`; `T = 1 - 1/v(fb_gates)`; `let`/`while` min-\|T\| and Nyquist-crossing scans (`-999` no-crossing sentinel) | `pm_deg ≥ 45`, `gm_crit_db ≤ 0`, `dc_gain_db ≥ 10` | lumped core + amp |
| `core-mirror-sensitivity` | 81 | five `dc vos_*` cards + `op` in one deck | 13 checks: 5 mirror sensitivities, sum, 5 headroom margins, `v_ibias_op`, `amp_tail_ua` | explicit trim ladder per inventory (**not re-traced**) + amp |
| `bandgap-loop-smoke` | `tt`, 27 C, tolerance 0.0 → **1 point** | `op` | `vref`, `sns1`, `iq_ua` sanity windows only | lumped core + inline provisional amp (no `dut` key) |

All six drive the supply from a DC source named `vsup` (e.g.
`vsup vdd 0 dc {vdd_val} ac 1` in `tb_psrr.spice`), so the existing
`corners.supply_v` → `alter vsup` route applies; none uses PWL/PULSE/SIN, so
klt's refusal of `supply_v` on a time-varying source (documented at the top of
`mk_klt_fleet_request.py`) does not trigger. (Source names in the other five
decks: **not individually traced**.)

## 2. Minimum extensions and decomposition (acceptance item 1)

Reuse `fleet_common`, the plan/report schema `gf180-bandgap/fleet-plan/1`, the
`collect_units` coverage logic, and the `MEASUREMENT`-style verdict path. Do not
add a second runner.

| Bench | Proposed fleet mapping | Reuses |
|---|---|---|
| `amp-psrr` | one `ac` request, 81 units; worst-case PSRR reduced from the returned waveform | `psrr-dc` pattern (1 `ac` request) |
| `core-psrr-ideal-amp` | same, with the embedded core and **no** DUT include | `psrr-dc` + `startup`'s embedded-core branch |
| `amp-offset-sensitivity` | one `dc` request, slope from the two waveform points | `line-regulation` `dc` waveform reduction |
| `bandgap-loop-smoke` | one `op` request, one unit | `psrr-dc`'s `op` request |
| `core-mirror-sensitivity` | one `op` + five `dc_<k>` requests, plot names renumbered per request | `output-noise` adapter's multi-request split |
| `amp-loop-stability` | one `ac` request needing complex-valued data (U1) | `psrr-dc` `ac` request, new reduction |

**Recommendation: one increment is too much; use three build issues**, filed
afterwards at `loom:triage` by whoever approves this plan (this issue files none):

1. **Simple four** — `amp-psrr`, `core-psrr-ideal-amp`, `amp-offset-sensitivity`,
   `bandgap-loop-smoke`. Existing patterns; one PR.
2. **`amp-loop-stability`** — blocked on unknown U1 (complex ac data).
3. **`core-mirror-sensitivity`** — six-request split and saved device parameters
   (U2); its own risk.

Rejected: a second runner (forbidden by the issue); one monolithic adapter PR
(mixes three independent risk levels); replacing diagnostic decks with the
canonical DUT (would silently change the experiment).

### 2.1 Verdict semantics

These claims are not ratified spec lines. Diagnostic/reference rows stay
**outside `SPEC_CHECKS` and outside the suite roll-up**. The adapters report
tb.json thresholds unchanged as *diagnostic checks* and use a
`MEASURED` / `INCOMPLETE` distinction (as `output-noise` does), never spec
PASS/FAIL. The `amp-psrr` 60 dB row cites the ratified PSRR line but over a
different band and DUT shape than the gated `psrr-dc` row, so it is not
promoted either. No limit is added, relaxed or ratified here. The existing
`SPEC_CHECKS`-vs-suite pinning test must remain untouched by the new benches.

## 3. Identity requests and results must carry (acceptance item 2)

Each plan/record must state, separately and never merged:

- **Source commit** of this repo at request generation (the plan carries none
  today; `plan.json` has `submitting_klt_version`, DUT sha256,
  `tb_netlist_sha256`, `manifest_sha256`, per-request `deck_sha256` /
  `request_sha256`).
- **Canonical DUT** `sim/dut/bandgap_top.spice` sha256
  `9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`
  (last touched `aeaca90e`; read 2026-10-20).
- **Amplifier** `sim/dut/bandgap_amp.spice` sha256
  `db539d5fe9ad2185bb6a9a8ff90303fca86073fdfdd4e4a51d6872e9f8049302`
  (read 2026-10-20). The newest `amp-psrr`, `amp-offset-sensitivity`,
  `amp-loop-stability` and `core-mirror-sensitivity` records pin
  `dcdad1a6fec28b5977b72f9da2cf58f0a673fe4cc5fbe16cf85ad6ab6a969883`, so the amp
  has changed since; those records are older-core evidence and **not comparable**
  (not golden values).
- **Embedded deck identity**, kept separate from the canonical DUT as `startup`
  does: per bench the testbench sha256, the embedded realization (lumped
  545.639857u vs explicit trim ladder), and the `check_embedded_cores.py` output.
  The plan must repeat the `sim/embedded-core-inventory.md` limits: lumped R1 is
  exact at tt/27 C only (-0.18 % / +0.27 % at -40 / 125 C), only `res_typical`
  was exercised for that fit, and `bandgap-loop-smoke` / `core-psrr-ideal-amp`
  still carry the older mirror sizing (L=6u W=60u vs canonical L=8.5u W=85u,
  ratios equal; sizing figures per curator, smoke deck re-read here, the
  `core-psrr-ideal-amp` deck **not re-traced**). No byte-identity or equivalence
  is claimed.
- **Tool / PDK** from the report `environment`: `engine_version`,
  `models_lib_sha256`, `remote.runner_klt_version`, `remote.runner_compatibility`,
  instance type. Last fleet run on record
  (`sim/iq/fleet-raw/20261016-klt-sim-ec2e1a1364c1/report.json`): ngspice 46,
  `models_lib_sha256` `f6f4a96e18fc5ad11270ad3451aaecc7ac37fc81eb61e15b0d7d94c7bc594a24`,
  runner klt 0.7.0, `runner_compatibility: match`. The lumped-R1 derivation used
  ngspice 42 locally; the fleet runs 46 — this difference must be recorded.

## 4. Offline fixture / parity check plan (acceptance item 2, plan only)

New cases go in a new `sim/tests/test_fleet_diagnostic.py`, in the style of
`sim/tests/test_fleet_ingest.py` (synthetic reports/waveforms, stub PDK include,
no network). **No adapter code is added by this issue.** Cases, per bench unless
noted:

| Case | Asserts |
|---|---|
| analysis kind / units | each measurement comes from the declared analysis kind (`ac`/`dc`/`op`) and unit (dB, V/V, deg, mV, uA) |
| finite values | NaN/inf/null/missing measurement → rejected |
| coverage | expected 81 (smoke: 1) points present, no duplicate or foreign corner id |
| failed/errored unit | any failed/errored/inconclusive unit → bench `INCOMPLETE` |
| identity mismatch | DUT / deck / testbench / manifest sha256 or runner-compatibility mismatch → `INCOMPLETE` |
| diagnostic semantics | `amp-loop-stability`: probe node `fb_gates`; `amp-offset-sensitivity`: `vos` source position; `core-psrr-ideal-amp`: `Efb` ideal servo and no amp instance; `core-mirror-sensitivity`: five `vos_m*` sources + explicit trim realization |
| not a spec row | none of the six appears in `fleet_ingest.SPEC_CHECKS` or the suite roll-up |

Parity: derive figures from analytic synthetic waveforms with known answers
(single-pole PSRR; a T-locus with known PM and the `-999` no-crossing case) and
compare to a Python port of the tb.json `let` logic. Historical records are not
golden values.

## 5. Rerun matrix and estimates (acceptance item 3)

Manifest-justified minimum; no reductions invented. Units are mapped per §2.

| Bench | Requests | Units | Runtime / cost |
|---|---|---|---|
| `amp-psrr` | 1 | 81 | unknown (ac) |
| `core-psrr-ideal-amp` | 1 | 81 | unknown (ac; convergence aid, U3) |
| `amp-offset-sensitivity` | 1 | 81 | dc, 2 points — expected small; unmeasured |
| `amp-loop-stability` | 1 | 81 | unknown (wide ac, 0.1–2000meg) |
| `core-mirror-sensitivity` | 6 | 486 | unknown |
| `bandgap-loop-smoke` | 1 | 1 | trivial; unmeasured |
| **Total** | **11** | **811** | computed from the table, **not measured** |

Only basis for time: the archived iq fleet run (27 units, `elapsed_seconds` 36 on
one spot `c7i.8xlarge`, concurrency 2, per-unit `runtime_s` 7.35–23.8 s, all dc
temperature sweeps). AC and six-way fan-out will differ. **Per-unit runtime for
ac/loop-stability decks and dollar cost are named unknowns**, to be bounded by a
later separately authorized single-unit probe. This plan does not run one.

Capacity prerequisites (recorded in `sim/suite/fleet-evidence-239.md` and its
blocker history; values **not re-checked today**): `BATCH_MAX_CONCURRENT_INSTANCES=8`,
`BATCH_MAX_VCPU=224`, earlier `batch_no_capacity` refusals; the 2026-10-09 runner
version-mismatch blocker is in `sim/fleet-blockers/20261009-issue-239-runner-version-mismatch/`.

**Finite stop/retry rule (proposed):** at most 2 resubmits per request on a
capacity refusal; then stop and record the blocker under
`sim/fleet-blockers/<date>-.../`. A submit failure is reported, never worked
around by running the grid locally (host policy: grids go to the fleet only).

## 6. Prerequisite unknowns (acceptance item 4 — stated, not probed)

- **U1** — whether `artifacts.waveform` returns complex ac vectors (real/imag of
  `v(fb_gates)`), or whether `measurements[].expr` can express the `while`/`let`
  reductions. Blocks `amp-loop-stability`. If verified and not already tracked, it
  is a candidate generic klt gap to file at `2AMLogic/klayout-tools` under the
  friction protocol **after** deduplication (compare #2893/#2938 for the related
  noise gaps), described generically with no design detail.
- **U2** — whether saved device parameters (`@m.xm1.m0[vds]`, `[vdsat]`) used by
  the `core-mirror-sensitivity` headroom margins are returnable from an `op`
  request.
- **U3** — whether `.options itl1/itl2/itl6` and `.nodeset` are honoured on the
  runner, and whether the convergence aid in `core-psrr-ideal-amp` (verified only
  at tt / 27 C-class corners on the dispatch host) holds across the 9 process
  corners and ±10 % supply. `amp-offset-sensitivity` and `core-mirror-sensitivity`
  also carry a `.nodeset` (solver hint only).
- **U4** — the older four-bench `could not find a valid modelname` failure for
  `nfet_03v3 L=6u W=300u nf=12` (`sim/embedded-core-inventory.md`) was observed on
  the **dispatch host's** PDK. The device line (`W=300u`) appears twice in each of
  `bandgap_top.spice` and `bandgap_amp.spice`, and the fleet ingested final-DUT
  rows against that DUT on 2026-10-16, so the fleet PDK likely has the bin —
  an **inference, not verification for today's runner**. Before any run, compare
  the runner's `models_lib_sha256` / version with the last good report above.
- **U5** — reviewer question, not decided here: `bandgap-loop-smoke` has a
  1-point manifest (tt/27 C/3.3 V); widening it to full PVT would need a manifest
  change and is out of scope.

## 7. Linking plan (acceptance item 5)

Mirror the iq pattern: raw request/report/body under
`sim/<bench>/fleet-raw/<date>-klt-sim-<id>/`; ingested append-only records under
`sim/<bench>/records/` with `corners/` and one
`netlist-snapshots/<record>.spice` (flat layout, as `sim/check_records.py`
requires); an index, e.g. `sim/suite/diagnostic-evidence-239.md`, listing job
ids, hashes and verdicts; and a comment on #239 / #211 linking it. Historical
records and failures (including the 2026-10-09 blocker directory) are never
edited; new records reference what they supersede and do not alter it. Records
for these benches are diagnostic evidence and are not added to the gated
suite roll-up.

## 8. Not authorized by this plan

Adapter or ingest implementation, any `klt sim` or ngspice run (local or batch),
capability probes, spending or provisioning, filing the build sub-issues, edits to
records/manifests/DUT/spec, the resistor-mismatch (`par_r`) model-risk review, the
#203/#204 gates, and closing #239 / #211 / #203. Each requires separate authority.
