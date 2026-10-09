# Evidence packet: the three TBD rows (A4 / A6 / A7)

- **Status**: preparation packet for operator decisions (issue #234). **Not a
  decision record, not a spec change, not a verdict.** No row is ratified, no
  threshold is set, and no output stage is selected here. No decision-record
  number is reserved.
- **Snapshot**: `origin/main` @ `3524ca42` (2026-10-09). Every path, record ID,
  hash and commit below was checked against that tree; see
  [Provenance verification](#provenance-verification).
- **Scope**: existing committed evidence only. No simulation was run to
  prepare this packet. `sim/` records are cited, never edited.

## How to read this packet

**Current DUT.** The current canonical schematic DUT is
`sim/dut/bandgap_top.spice`, sha256
`9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`, last
changed by `aeaca90e` (DR-0007 retune, #209). The committed extracted netlist
`layout/netlist/bandgap_top_extracted.spice` (sha256
`eea17aad965755204a6ddccf1397d2fc969a2bca1cc48343a0a793bffa326356`) last
changed in `ba091ea0` (2026-08-03). That predates both the #151 amp-mirror
resize (`94df4d77`) and DR-0007, and `README.md` already says the committed
layout does not certify the amended schematic.

**Applicability labels used below.**

| Label | Meaning |
|---|---|
| **CURRENT** | The recorded DUT sha256 equals the current DUT above. |
| **HISTORICAL** | Taken against an earlier DUT. The record is valid for that DUT and supports nothing about the current one. |
| **DIAGNOSTIC** | The bench does not drive the canonical `bandgap_top` DUT. It uses an embedded or partial circuit. Useful as corroboration, but it cannot carry a top-level row claim. |

**Required PVT matrix** (CLAUDE.md, `README.md`): temperature −40 / 27 /
125 °C; supply 2.97 / 3.30 / 3.63 V (3.3 V ±10 %); process corners. Every
record cited below ran the harness's 9-corner set (`tt ff ss fs sf res_ff
res_ss bjt_ff bjt_ss`) × 3 temperatures × 3 supplies = 81 points. None of them
ran against the current DUT.

**Headline: no evidence for any of the three rows is CURRENT.** Each row below
gives the historical evidence, says what it can and cannot support, lists the
gaps, and ends with one operator question.

| Row | Ratified shape | Newest schematic evidence | DUT applicability | Load | Fleet backend |
|---|---|---|---|---|---|
| PSRR (A4) | > 60 dB DC–1 kHz; stretch > 30 dB @ 1 MHz; **load condition TBD** | `sim/psrr-dc/records/20260816-145206-1ca1c95.md` | HISTORICAL (`f408e30d…`) | unloaded only | adapter exists (#237), no fleet record |
| Output noise (A6) | 0.1–10 Hz integrated, µVrms; **threshold TBD** | `sim/output-noise/records/20260910-060222-a6f8b96.md` | HISTORICAL (`faf74311…`) | unloaded only | no adapter |
| Load (A7) | **max DC load + load regulation, or explicit unbuffered (high-Z only)** | none: no bench exists | n/a | n/a | n/a |

---

## Row 1: PSRR load condition (amendment A4)

### Exact current wording

`README.md`, ratified table, line 37:

> `| PSRR | > 60 dB DC–1 kHz | > 30 dB @ 1 MHz | load condition TBD — to be fixed when the output stage is designed (see DR-0001) |`

The text below the table (`README.md` lines 47–51) says the PSRR load
condition, the output-noise threshold and the load-row option "are amendments
A4/A6/A7 from #35 carried through verbatim as open items … each will be closed
out as its own future decision record when the relevant design work (output
stage, #10) resolves it."

### Original decision context

- **#35 A4** (spec-review amendment, input to ratification): "add
  frequency-qualified points, e.g. `> 60 dB DC–1 kHz; > 30 dB @ 1 MHz`, at a
  stated load condition (DC-only PSRR overstates the hard case)."
- **DR-0003** (`spec/decision-records/0003-target-spec-ratification.md`)
  ratified A4's *shape* (frequency points) but not the load condition. The
  record says to close the load condition in its own decision record "when the
  output-stage design (#10) is ready", rather than by amending DR-0003.
- **DR-0001** (`spec/decision-records/0001-bandgap-topology-selection.md`)
  selects "a cascoded current-mode output/bias stage rather than a raw
  voltage-node tap" and notes that a Brokaw output "is a moderate-impedance
  summing node unless buffered". It also says to revisit as a superseding
  record if that stage does not clear the PSRR target.
- **Gap (pointer drift):** `README.md` names "#10" as the output-stage work.
  #10 ("Error amplifier design with offset/mismatch budget") closed
  2026-08-01 as amplifier work. No open issue tracks output-stage or load
  design (checked with `gh issue list --state open` on 2026-10-09).

### Measurement definitions

| Bench | DUT the bench drives | Stimulus / output | Gated quantities | Reference-only | Load |
|---|---|---|---|---|---|
| `sim/psrr-dc/` (`testbench/tb.json`, `tb_psrr_dc.spice`) | canonical `sim/dut/bandgap_top.spice` (or `--dut` extracted) | `vsup … ac 1`, output `vref`; PSRR(f) = −db(v(vref)); `ac dec 20 0.1 10meg` | `psrr_1hz_db` ≥ 60 (the "DC" asymptote, stated as 1 Hz), `psrr_1khz_db` ≥ 60 | 10 Hz, 100 Hz, 10 kHz, 100 kHz, 1 MHz spot columns plus the 161-point curve in the raw logs; the 1 MHz stretch is recorded, not gated | **none** ("Load condition: none", tb comment) |
| `sim/amp-psrr/` (`testbench/tb.json`, `tb_psrr.spice`) | `sim/dut/bandgap_amp.spice`, plus an **embedded lumped core** and startup inside the testbench (R1 lumped at 545.639857 µm, no `bandgap_trim` instance; `sim/embedded-core-inventory.md` line 39) | `vsup … ac 1`, output `vref` of the embedded core; `ac dec 20 0.01 1k` | `psrr_worst_db` ≥ 60 (minimum over 0.01 Hz–1 kHz) | `psrr_dc_db` | **none** |

`sim/suite/spec.py` grades the PSRR row from `psrr-dc` only, with the note
"Unloaded -- the row's load condition is open item A4". `amp-psrr` is not a
suite line.

### Evidence inventory

All records ran on 81/81 points (9 process × 3 temp × 3 supply), with local
ngspice and no fleet job id.

**`sim/psrr-dc/records/` (12 records):**

| Record | Provenance | DUT sha256 (prefix) | Worst 1 Hz / 1 kHz / 1 MHz (dB) | Overall | Applicability |
|---|---|---|---|---|---|
| `20260801-032726-82ea7db` | schematic | `324384fd` | 30.68 / 30.68 / 24.63 | FAIL | HISTORICAL (pre-#42 amp) |
| `20260801-085458-76ee943` | schematic | `c7b6f9e1` | 31.91 / 31.91 / 6.22 | FAIL | HISTORICAL |
| `20260801-143203-cfd0146` | schematic | `0e73ce9f` | 87.41 / 87.07 / 30.39 | PASS | HISTORICAL |
| `20260801-202602-0ecce11` | schematic | `0e73ce9f` | 87.41 / 87.07 / 30.39 | PASS | HISTORICAL |
| `20260802-045149-cf2ab8d` | schematic | `9d38148b` | 73.93 / 73.84 / 30.61 | PASS | HISTORICAL |
| `20260803-002113-24df70f` | extracted | `fe89758e` | 76.53 / 73.92 / 17.83 | PASS | HISTORICAL |
| `20260803-020204-feab5b5` | extracted, **dirty tree** | `816278d3` | 74.37 / 72.53 / 18.20 | PASS | HISTORICAL, not clean-citable |
| `20260803-031631-294fb1d` | schematic, **dirty tree** | `f5975273` | 74.30 / 74.22 / 30.98 | PASS | HISTORICAL, not clean-citable |
| `20260803-063546-31e5efc` | extracted | `eea17aad` (= current extracted file) | 74.74 / 72.90 / 18.55 | PASS | HISTORICAL: the extracted netlist predates #151 and DR-0007 |
| `20260803-094523-ba091ea` | schematic | `f5975273` | 74.30 / 74.22 / 30.98 | PASS | HISTORICAL |
| `20260815-022028-40321ca` | schematic | `f5975273` | 74.30 / 74.21 / 30.98 | PASS | HISTORICAL |
| `20260816-145206-1ca1c95` | schematic, **dirty tree** | `f408e30d` | 77.61 / 77.40 / 28.96 | PASS | HISTORICAL. This is the record the latest suite summary cites (`sim/suite/summaries/20260816-142719-1ca1c95.md`) |

**`sim/amp-psrr/records/` (7 records):** `20260801-034242-c26da47` (dirty,
FAIL, 31.87 dB worst), `20260801-073426-a7fd16a` (frozen amp, FAIL, 31.87),
`20260801-073633-a7fd16a` (PASS, 77.61), `20260801-133427-cfd0146` (PASS,
86.98), `20260801-231234-960f726` (dirty, PASS, 73.81),
`20260802-034356-5066d85` (PASS, 73.80), `20260816-145949-1ca1c95` (dirty,
PASS, 77.09). All are **DIAGNOSTIC** and HISTORICAL:

- the embedded core in `tb_psrr.spice` was re-synced to the DR-0007 core in
  `cb5d07c6` (#227) *after* the newest record;
- the current testbench sha256 is `e97dd1b5…`, and no record carries that
  hash (the newest record carries `59babaf3…`, which is the testbench at
  `3f207c6e`).

### Can the amplifier-only result support a top-level claim?

**No.**

- `amp-psrr` measures `vref` of a testbench-embedded core, not the canonical
  `bandgap_top` DUT. That core lumps the trim ladder into R1 and has no
  `bandgap_trim` instance.
- The embedded core has drifted from the DUT before (#227 had to re-sync
  it), so equality with the DUT has to be checked per record, not assumed.
- `sim/suite/spec.py` does not grade it.

It can corroborate a `psrr-dc` result taken on the same core generation
(e.g. 86.98 vs 87.07 dB in the `cfd0146` pair). A top-level PSRR claim still
needs a `psrr-dc` record on the canonical DUT.

### PVT coverage against requirements

| Axis | Required | Observed (any DUT) | Observed on current DUT `9ef5f8c5…` |
|---|---|---|---|
| Temperature | −40 / 27 / 125 °C | −40 / 27 / 125 °C, every record | **none** |
| Supply | 2.97 / 3.30 / 3.63 V | 2.97 / 3.30 / 3.63 V, every record | **none** |
| Process | corners | 9 (`tt ff ss fs sf res_ff res_ss bjt_ff bjt_ss`) | **none** |
| Load | **TBD (this question)** | unloaded only | **none** |
| Frequency | DC–1 kHz gated; 1 MHz stretch | 0.1 Hz–10 MHz curve (`psrr-dc`); 0.01 Hz–1 kHz (`amp-psrr`) | **none** |
| Extracted | (signoff item 7) | `eea17aad` extracted, pre-#151/pre-DR-0007 | **none** |

### Gaps (unresolved, not inferred)

1. **No CURRENT-DUT PSRR record.** Every passing figure above belongs to an
   earlier DUT. DR-0007 changed Q2, R2 and R1 (`git diff 3f207c6e aeaca90e --
   sim/dut/bandgap_top.spice`; `94df4d77` also changed the amp's M3/M4).
   Fresh evidence depends on #239/#211.
2. **No loaded PSRR at any frequency.** Every record is unloaded by
   construction. This is exactly the case A4 says "DC-only PSRR overstates".
3. **1 MHz stretch is not met at the worst corner in the newest records.** The
   recorded worst is 28.96 dB in the newest schematic record and 18.55 dB in
   the newest extracted record, against the > 30 dB stretch. This is recorded
   only: the stretch is not gated, and this packet makes no claim on it.
4. **Backend:** `sim/tools/mk_klt_fleet_request.py` / `fleet_ingest.py`
   (`467e589b`, #237) can express `psrr-dc` for the Spot fleet, but no
   fleet-ingested `psrr-dc` record exists yet. `amp-psrr` has no fleet
   adapter.
5. **Provenance:** records `20260816-145206-1ca1c95` and
   `20260816-145949-1ca1c95` were taken on a dirty tree at commit `1ca1c95`,
   which **does not exist on GitHub** (API 422). They landed in `3f207c6e`,
   whose committed DUT matches the recorded `f408e30d…` hash. Records
   `20260803-020204-feab5b5` and `20260803-031631-294fb1d` are also
   dirty-tree records.

### Coupling with the output-stage choice (Row 3)

The load condition for PSRR is meaningful only once the output's loading
contract exists. If the block stays unbuffered, `vref` is the drain of the
cascoded mirror leg MC3/M3 driving the R1 + trim ladder + Q3 branch
(`design/bandgap_operating_point.md` §1). Any DC load current then diverts
current from that branch, and any load capacitance shapes the
high-frequency rejection. If a buffer is added, PSRR becomes a property of the
buffer at its rated load. Either way, the A4 load is the A7 answer evaluated
under ripple, which is why A4 should not close before A7.

### Operator question 1 (A4)

> **At what load condition should the ratified PSRR row (> 60 dB DC–1 kHz;
> stretch > 30 dB @ 1 MHz) be evaluated?**

| Rank | Option | Why this rank | Evidential limits | Consequences |
|---|---|---|---|---|
| 1 | **Tie A4 to the A7 answer**: evaluate PSRR at the same load that Question 3 ratifies. For unbuffered, that is a high-Z test load, quantified only after an output-impedance measurement. For buffered, it is the rated max DC load (and a stated capacitance). | Keeps one load definition for two rows. Answers A4's "stated load" requirement without inventing a number. Matches DR-0001/DR-0003's "fix it with the output stage". | No load has been simulated, so no loaded margin is known. Unloaded margins (~74–87 dB historical) do not transfer. | A4's DR waits for A7's DR. `psrr-dc` gains the load and mints a new record set (its tb comment already says so). |
| 2 | **Ratify "unloaded (high-Z), DC–1 kHz" now**, matching how every existing record was taken. | Fastest closure. Makes the existing bench gradable as-is once re-run on the current DUT. | It is the case A4's own text says "overstates the hard case". Nothing is known about loaded behaviour. | If A7 later picks buffered or a finite load, this needs a superseding DR, and the earlier PSRR "pass" would not carry over. |
| 3 | **Dual condition**: unloaded *and* max-rated load, worst governs. | The most conservative wording. | Only meaningful if A7 defines a non-zero max load (buffered). It adds nothing for a high-Z-only contract. | Two loaded/unloaded record sets per run. Depends on a load bench that does not exist. |

In all options the 1 MHz figure stays a recorded stretch, unless the operator
explicitly makes it a target in that DR.

---

## Row 2: Output-noise threshold (amendment A6)

### Exact current wording

`README.md` line 39:

> `| Output noise | not yet quantified — band: 0.1–10 Hz integrated µVrms (threshold TBD; add a spot-noise point if a later wave feeds an ADC) | — | n/a |`

### Original decision context

- **#35 A6:** "Add output-noise row: `Output noise | < X µVrms integrated
  0.1–10 Hz` (state the band; add a spot-noise point if a later wave feeds an
  ADC)."
- **DR-0003** ratified the band and units (0.1–10 Hz integrated, µVrms) but
  not X. A spot-noise point is a *potential* separate requirement that only
  applies if a later wave feeds an ADC.
- `sim/suite/spec.py` `NOT_CLAIMED_HERE` keeps "Output noise" unclaimed. The
  latest suite summary (`sim/suite/summaries/20260816-142719-1ca1c95.md`,
  line 117) predates the bench and still says "no bench yet".

### Measurement definition

`sim/output-noise/testbench/tb.json` + `tb_output_noise.spice` (#188, landed
in `c153489a` as #189):

- `noise v(vref) vsup dec 20 0.1 10`: integrated over exactly 0.1–10 Hz →
  `onoise_int_0p1_10hz_uvrms = sqrt(noise2.onoise_total) * 1e6`.
- `noise v(vref) vsup dec 20 0.1 100k`: spot density at 1 / 10 / 100 kHz →
  `onoise_*khz_nv_rthz = sqrt(noise3.onoise_spectrum[i]) * 1e9`.
- Frequency-index assertions (0.1 Hz, 10 Hz, 1/10/100 kHz) and a `vref_op`
  sanity window are gated. The integrated noise is gated only by a
  `min_spread_pct = 5` integrity floor. **There is no noise threshold.** The
  record's "Overall: PASS" means the measurement completed and passed its
  integrity checks. It is **not** a pass against a noise spec, and this
  packet does not present it as one.
- Load: **none** ("Load condition: none. Like sim/psrr-dc/ …").

### Evidence inventory

| Record | Provenance | DUT sha256 | Points | Integrated 0.1–10 Hz, as recorded (min / mean / max) | 1 kHz spot, as recorded (min / max) | Applicability |
|---|---|---|---|---|---|---|
| `sim/output-noise/records/20260910-060222-a6f8b96.md` | schematic | `faf74311…` (DUT at `94df4d77`) | 81/81 | 3937.29 / 4314.8 / 4800.56 "µVrms" | 8.572e5 / 1.252e6 "nV/√Hz" | HISTORICAL |
| `sim/output-noise/records/20260910-060236-a6f8b96.md` | extracted | `eea17aad…` (= current extracted file) | 81/81 | 4786.21 / 5243.25 / 5835.86 "µVrms" | 8.575e5 / 1.244e6 "nV/√Hz" | HISTORICAL (extracted netlist is pre-#151/pre-DR-0007) |

Both ran with ngspice-46, run locally (no fleet job id), at provenance commit
`a6f8b96` on `feature/issue-188`. That commit exists on GitHub but is not an
ancestor of `main`, because the branch was squash-landed as `c153489a`. The
testbench hash `dbeee2ca…` equals the current testbench.

**DUT drift.** `git diff 94df4d77 aeaca90e -- sim/dut/bandgap_top.spice`
changes only Q2 (`pnp_10p00x10p00 m=1` → `pnp_05p00x05p00 m=4`), R2
(36.34 → 39.20 µm) and R1 (443.4 → 446.0 µm). The amplifier, which the
record's own breakdown names as the main contributor (68.74 % at 1 Hz,
92.24 % at 1 kHz), is textually unchanged. This does **not** make the record
CURRENT: a core change moves bias currents and noise gain. It does say what a
re-run is expected to test.

**Stale caveat text.** The record's claim text (copied from `tb.json`) says
"bandgap_amp is #8's provisional 5T OTA". `design/bandgap_operating_point.md`
§1 says #42 replaced the 5T OTA with a telescopic-cascode OTA, and the
recorded DUT does contain that amp (`ncasc`/`XCC`). The record is
append-only and stays as written. A later bench edit should correct the
`tb.json` claim text.

### Units: unresolved discrepancy that blocks any numeric threshold

The bench treats ngspice's `onoise_spectrum` as V²/Hz and `onoise_total` as
V², and takes a square root. Three pieces of in-repo or installed evidence
suggest the outputs are already amplitudes (V/√Hz and V rms). If so, both
columns were square-rooted twice:

1. **ngspice release notes.** The packaged NEWS (`/usr/share/doc/ngspice/NEWS.gz`,
   Ngspice-27 section) says: "noise analysis, deliver results in V/sqrt(Hz)
   and A/sqrt(Hz)", plus a `.control` variable `sqrnoise` "to deliver noise
   data in squared representation". `grep -rn sqrnoise` over the repo finds
   no use, and the records ran ngspice-46.
2. **The repo's own breakdown tool.** `sim/output-noise/nominal_noise_breakdown.py`
   (`summarize_section` docstring) found empirically that per-device values
   "combine in quadrature" (Σ(vᵢ/total)² = 1). That is the behaviour of
   amplitude quantities, not of power densities.
3. **Arithmetic on the recorded numbers.** The nominal record notes give
   `onoise_spectrum` = 8.452e-6 at 1 Hz.
   - Read as V/√Hz with a 1/f shape, it integrates over 0.1–10 Hz to
     ≈ 18.1 µVrms. The recorded `tt_27c_3.30v` figure, squared back, is
     (4280.44e-6)² V = 18.3 µVrms.
   - Read as V²/Hz, the same assumption gives ≈ 6.2 mVrms, which does not
     match the recorded 4.28 mV.
   This is a consistency check on recorded values, not a new measurement.

**If** the amplitude reading is right, the recorded figures map to roughly:

| Quantity | Reading | Schematic record | Extracted record |
|---|---|---|---|
| 0.1–10 Hz integrated | as recorded | 3937–4801 "µVrms" | 4786–5836 "µVrms" |
| 0.1–10 Hz integrated | amplitude (squared back) | **15.5–23.1 µVrms** | **22.9–34.1 µVrms** |
| 1 kHz spot | as recorded | 8.57e5–1.25e6 "nV/√Hz" | 8.58e5–1.24e6 "nV/√Hz" |
| 1 kHz spot | amplitude (squared back) | **≈ 735–1567 nV/√Hz** | **≈ 735–1548 nV/√Hz** |

These are reinterpretations of HISTORICAL records under an unverified
hypothesis. They are neither evidence nor a measurement. Resolving the
hypothesis needs a reviewed bench correction (or an explicit `sqrnoise`) and
a new record set. Until then, **no numeric noise figure in this repo is
usable for a threshold**: the two readings differ by about 200×.

### PVT coverage against requirements

| Axis | Required | Observed (historical DUT) | Observed on current DUT |
|---|---|---|---|
| Temperature | −40 / 27 / 125 °C | all three | **none** |
| Supply | 2.97 / 3.30 / 3.63 V | all three | **none** |
| Process | corners | 9 corners | **none** |
| Band | 0.1–10 Hz integrated, µVrms | 0.1–10 Hz (frequency-asserted); units disputed (above) | **none** |
| Spot noise | not required (conditional on an ADC consumer) | 1 / 10 / 100 kHz recorded, reference-only | **none** |
| Load | unspecified | unloaded | **none** |

### Gaps

1. Units discrepancy (above): unresolved and blocking. Tracked in #252.
2. No CURRENT-DUT noise record, schematic or extracted.
3. **Backend:** no fleet adapter for `output-noise`. `mk_klt_fleet_request.py`
   documents `ac`/`dc`/`tran` as the analysis kinds it uses. Whether the
   pinned `klt sim` request contract accepts a `noise` analysis has **not**
   been verified in-repo. If it does not, that is a klayout-tools
   friction-protocol issue. An 81-point local re-run is not allowed on shared
   dispatch workers.
4. No downstream consumer (ADC or other) is defined, so there is no basis yet
   for a spot-noise requirement.
5. No mismatch / Monte Carlo noise data. The row's corner binding reads
   "n/a", so this is noted but not required.

### Candidate derivation (a proposal, not ratified)

The only ratified number a noise limit can be anchored to without inventing a
consumer is the trim row: resolution ≤ 0.25 %/step, i.e. 3.0 mV at 1.20 V.
A common rule keeps the 0.1–10 Hz peak-to-peak noise (≈ 6.6 × rms) at or below
one tenth of the smallest intentional adjustment:

  X ≤ (0.1 × 3.0 mV) / 6.6 ≈ **45 µVrms** (0.1–10 Hz integrated).

The derivation's choices (a 1/10 fraction and a 6.6 crest factor) are
judgment calls for the operator to accept or replace. Whether any historical
DUT would meet ~45 µVrms depends entirely on resolving the units question:
"yes" under the amplitude reading, "no by ~100×" under the recorded reading.
This packet claims neither.

### Operator question 2 (A6)

> **What numeric threshold, in µVrms over 0.1–10 Hz integrated, should the
> output-noise row carry, and should a spot-noise point be added now?**

| Rank | Option | Why this rank | Evidential limits | Consequences |
|---|---|---|---|---|
| 1 | **Defer and measure**: keep X TBD; first correct or verify the bench's noise units, then re-measure the current DUT (schematic + extracted, full PVT, via the fleet); decide X afterwards in its own DR. No spot-noise point until an ADC consumer exists. | The only option that does not risk a ~200× error in either direction. | Delays closing A6. Needs a fleet path for `noise` (gap 3). | Follow-ups: units issue, noise fleet adapter or klt capability check, new records. `NOT_CLAIMED_HERE` stays until the DR. |
| 2 | **Ratify X ≈ 45 µVrms now** using the derivation above (or an operator-chosen fraction/crest factor), with grading held until units-corrected CURRENT records exist. No spot-noise point. | Ties X to a ratified number (trim step), not to a guess. Lets bench and suite work proceed in parallel. | The pass/fail outcome is unknown until units are resolved. The 1/10 fraction is a convention, not a derived necessity. | Its own DR; `sim/suite/spec.py` moves the row into `SUITE` with a `max` limit once evidence exists. A later re-scope needs a superseding DR. |
| 3 | **Characterize-only**: ratify the row as "reported, no limit" for this canary block, keeping the recorded-not-gated pattern. | Honest for a block with no consumer, but it leaves a ratified row unbounded, which A6 explicitly asked to avoid ("< X"). | Same units problem: the reported number must still be correct. | Its own DR. The suite keeps the row unclaimed, and the signoff disclosure must say so. |

Spot noise (a separate potential requirement, nV/√Hz at a stated frequency)
should only be added when the operator names an ADC consumer. Every option
above leaves it out.

---

## Row 3: Load row, buffered or explicitly unbuffered (amendment A7)

### Exact current wording

`README.md` line 42:

> `| Load | TBD — pending output-stage design (DR-0001): either max DC load + load regulation, or explicit unbuffered — high-Z load only | — | n/a |`

### Original decision context

- **#35 A7:** "Add load row: either `max DC load + load regulation` or an
  explicit `unbuffered — high-Z load only`."
- **DR-0003** ratified the either/or shape, with no selection.
- **DR-0001** chose "a cascoded current-mode output/bias stage rather than a
  raw voltage-node tap" to help PSRR and "keep the reference-output node
  low-impedance". It also lists "output node is a moderate-impedance summing
  node unless buffered" as a Brokaw con. DR-0001 does **not** specify a
  buffer.
- `sim/suite/spec.py` `NOT_CLAIMED_HERE`: "load condition is open item A7
  (README.md); no bench yet".

### What the current design provides

From `design/bandgap_operating_point.md` §1 and §5, and
`sim/dut/bandgap_top.spice`:

- `bandgap_top` exposes only `vdd`, `vss` and `vref`. **There is no output
  buffer.** `vref` is the drain of the cascoded mirror leg MC3 (fed by M3),
  and it drives `bandgap_trim` → R1 → Q3 (diode-connected PNP) to `vss`.
- The cascode stage DR-0001 calls for is implemented (MC1–MC4 + MCB/MNB,
  §4.3). It is a bias/output **current** stage. It does not drive a load:
  M3/MC3 are not individually servoed by the amp (§1, "M3/R1/Q3 … are **not**
  individually servoed").
- So any DC current drawn from `vref` comes out of the R1/trim/Q3 branch.
  How far `vref` moves per µA of load is set by the output impedance at
  `vref`, which **no committed record measures**.

### Evidence inventory

| Evidence | Exists? | Notes |
|---|---|---|
| Output-impedance (Zout) or load-sensitivity bench | **No** | `grep -ril 'zout\|output impedance\|load regulation\|iload'` over benches and records finds only internal-mirror output-impedance material (`sim/core-mirror-sensitivity/`) and a generic `"iload"` params example in `sim/harness/README.md`. Neither is an output-loading measurement. |
| Load-regulation bench | **No** | |
| Max DC load or capacitive-load records | **No** | |
| Output-stage / buffer schematic | **No** | `design/` has core, amp, startup, trim and top only. |
| Loaded PSRR / noise | **No** | Every PSRR and noise record is unloaded (Rows 1–2). |

**No load limit can be inferred from the unloaded records.** Their passing
PSRR, TC or accuracy figures say nothing about behaviour with any current or
capacitance drawn from `vref`. This packet does not propose a numeric load
current.

### PVT coverage against requirements

| Axis | Required | Observed |
|---|---|---|
| Temperature / supply / process | −40/27/125 °C; 2.97/3.30/3.63 V; corners | **none (no bench)** |
| Load current / capacitance | TBD (this question) | **none** |

### Gaps

1. No bench for load in either form. The row is unmeasured, not failing.
2. No tracker for output-stage or load design (the README's "#10" pointer is
   closed amp work).
3. Budgets a buffer would consume are tracked on HISTORICAL DUTs only:
   - Iq: worst 34.01 µA at the binding `ff`/125 °C/3.63 V corner, against
     < 50 µA (`design/bandgap_operating_point.md` §6, pre-DR-0007).
   - Area: interim ceiling < 0.066 mm² (DR-0006).
   Neither has a CURRENT-DUT margin to spend.

### Operator question 3 (A7)

> **Should the Load row ratify an explicit "unbuffered — high-Z load only"
> contract, or commit to a buffered output with "max DC load + load
> regulation"?**

| Rank | Option | Why this rank | Evidential limits | Consequences |
|---|---|---|---|---|
| 1 | **Explicitly unbuffered, high-Z load only**, with "high-Z" quantified later from a measured `vref` output impedance (e.g. the maximum load current or minimum load resistance that keeps the Vref shift within a stated fraction of the accuracy budget). That bound is chosen in the DR after measurement, not now. | Matches the circuit that exists and is being verified (DR-0007 path), adds no Iq or area, and keeps all existing benches structurally valid. DR-0001's cascoded stage is about PSRR, not drive. | Zout is unmeasured, so how high "high-Z" must be is unknown. The consumer is undefined. | Its own DR. A new Zout / load-sensitivity bench (slug TBD) on the current DUT via the fleet. A4 can then close at "the high-Z test load" (Question 1, option 1). No circuit change. |
| 2 | **Buffered: add an output stage with max DC load + load regulation.** The numbers come from that stage's design, not from this packet. | Gives a usable reference for a real consumer and is the conventional catalog-grade answer. Ranked second because nothing in the repo needs it yet, and it reopens verified rows. | No buffer design, sizing or evidence exists. Its Iq/area cost is unknown against budgets measured only on historical DUTs. | New design issue and schematic. Regenerate `sim/dut/` and `layout/`. Re-verify every ratified row (Iq, PSRR, noise, TC, accuracy, startup, area). New load-regulation bench. DR-0001 may need a superseding record for the output-stage scope. |
| 3 | **Keep TBD** until a consumer (next wave) is named. | Avoids committing early. | It leaves A4 blocked too (coupling), and the block cannot claim a complete row set. | Signoff item 5 disclosure stays as is. No work. |

---

## Follow-up map

These are separate stages. None of them is done or claimed by this packet. A
single suite rerun cannot grade rows whose thresholds or benches do not exist
yet.

| Stage | Work | Depends on | Files affected (names only, nothing edited here) |
|---|---|---|---|
| **0. This packet** | Evidence + questions (#234) | none | `spec/tbd-row-evidence.md`, `signoff/README.md` (link) |
| **1. Operator answers** | Answer Questions 3, 1 and 2. Only the operator decides thresholds and the output stage. | Stage 0 | none (issue comment) |
| **2a. DR: load row (A7)** | One decision per record. | Answer to Q3 | new `spec/decision-records/NNNN-*.md`, `README.md` Load row |
| **2b. DR: PSRR load condition (A4)** | One decision per record. | 2a (coupling), answer to Q1 | new `spec/decision-records/NNNN-*.md`, `README.md` PSRR row |
| **2c. DR: noise threshold (A6)** | One decision per record. | Answer to Q2; for option 1, also 3a | new `spec/decision-records/NNNN-*.md`, `README.md` Output-noise row |
| **3a. Noise bench units** (#252) | Verify or correct the `onoise_*` conversions, fix the stale "5T OTA" claim text, mint new records (never edit old ones). | none (can start now) | `sim/output-noise/testbench/tb.json`, `tb_output_noise.spice`, `nominal_noise_breakdown.py` |
| **3b. Noise fleet path** | Check whether `klt sim` accepts a `noise` analysis. Adapter and ingestion, or a klayout-tools friction issue. | none | `sim/tools/mk_klt_fleet_request.py`, `sim/tools/fleet_ingest.py`, `sim/tests/test_fleet_ingest.py` |
| **3c. Load bench / output stage** | Unbuffered: Zout / load-sensitivity bench. Buffered: output-stage design, then a load-regulation bench. | 2a | new `sim/<slug>/` (TBD after 2a). If buffered: `design/*.sch`, `design/netlist/bandgap_top.spice`, `sim/dut/bandgap_top.spice` (via `sim/tools/mk_dut.py`), `layout/` |
| **3d. PSRR load in bench** | Add the ratified load to `psrr-dc`, then new records. | 2b, 3c | `sim/psrr-dc/testbench/tb.json`, `tb_psrr_dc.spice` |
| **3e. Suite grading** | Move noise/load rows from `NOT_CLAIMED_HERE` into `SUITE` with ratified limits; update the PSRR note. | 2a–2c, 3a–3d | `sim/suite/spec.py`, `sim/suite/README.md`, `sim/run_suite.py` (dispatch, if a new slug is added) |
| **4. Validation** | Fleet suite run on the current DUT (schematic), then extracted re-run on the regenerated layout; update the signoff disclosure. | 3e, #239/#211 (schematic fleet suite), #204 (extracted) | `sim/suite/summaries/`, `signoff/README.md` item 5 |

**DR numbering.** Each new record must re-check every filename in
`spec/decision-records/` on `main` immediately before choosing a number
(`spec/decision-records/TEMPLATE.md`). The highest number today is 0007, and
this packet reserves none. Two DRs drafted concurrently must not assume
consecutive numbers.

**Related trackers.** #94 (T1 gap), #202/#203/#204/#211/#238/#239 (DR-0007
evidence). Their results can refresh the "CURRENT" column above. None of them
is a prerequisite for the operator answering the questions.

---

## Provenance verification

All checks were run read-only on 2026-10-09 against `origin/main` @ `3524ca42`
(`git ls-tree`, `sha256sum`, `git merge-base --is-ancestor`, GitHub commits
API).

| Item | Check | Result |
|---|---|---|
| All 21 cited record files (12 `psrr-dc`, 7 `amp-psrr`, 2 `output-noise`) | path exists on `main` | present |
| Current DUT `sim/dut/bandgap_top.spice` | sha256 | `9ef5f8c5…4560`; equals **no** cited record's DUT hash |
| `output-noise` schematic DUT `faf74311…` | maps to `main` commit | `sim/dut/bandgap_top.spice` at `94df4d77` |
| `psrr-dc` 20260816 DUT `f408e30d…` | maps to `main` commit | `sim/dut/bandgap_top.spice` at `3f207c6e` |
| `psrr-dc` 20260815 / 20260803-094523 DUT `f5975273…` | maps to `main` commit | `sim/dut/bandgap_top.spice` at `a51bbb89` |
| Extracted DUT `eea17aad…` | equals current `layout/netlist/bandgap_top_extracted.spice` | yes; last changed `ba091ea0` (2026-08-03) |
| `output-noise` testbench `dbeee2ca…` | equals current file | yes |
| `psrr-dc` testbench `3a675bf0…` | equals current file | yes (all 12 records) |
| `amp-psrr` testbench | newest record `59babaf3…` vs current | **differs**: current `e97dd1b5…` (changed in `cb5d07c6`, #227) |
| Provenance commit `a6f8b96` (noise) | on GitHub / ancestor of `main` | on GitHub; not an ancestor (squash-landed as `c153489a`) |
| Provenance commit `1ca1c95` (`psrr-dc` + `amp-psrr` 20260816) | on GitHub | **not found** (HTTP 422); dirty tree; landed in `3f207c6e` |
| Provenance commit `5066d85` (`amp-psrr` 20260802) | on GitHub | **not found** (HTTP 422); landed in `b7c4a33f` |
| Other `psrr-dc` / `amp-psrr` provenance commits | on GitHub | present (some only as squash-landed branch commits) |
| `#237` fleet adapters | commit `467e589b` on `main` | yes; benches `psrr-dc`, `line-regulation`, `startup` only |
| `sqrnoise` usage | `grep -rn sqrnoise` (repo) | none |

Review cases exercised:

- **Missing PVT points:** none within any record (all 81/81). All points are
  missing on the current DUT.
- **Missing backend support:** `output-noise` and `amp-psrr` (no adapter);
  `psrr-dc` (adapter, no record).
- **Stale or provisional DUT evidence:** every cited record. Dirty-tree
  provenance is flagged per record.

---

## Unit-contract correction (2026-10-09, issue #252)

The "Units: unresolved discrepancy" section above is now resolved by
measurement. A PDK-free known-resistor probe
(`sim/output-noise/unit-probe/`, ngspice-42, 5 kohm, 27 C, 0.1-10 Hz and
0.1 Hz-100 kHz, default vs `set sqrnoise`) shows that with `sqrnoise` unset
(ngspice's default) `onoise_spectrum` is V/sqrt(Hz) and `onoise_total` is V
rms, both within 0.1 % of the analytical sqrt(4kTR) and sqrt(4kTR*(fh-fl)).
Under `set sqrnoise` both are squared. The recorded `sqrt()` conversions were
therefore a double square root.

- `sim/output-noise/testbench/tb.json` now scales only
  (`noise2.onoise_total * 1e6`, `noise3.onoise_spectrum[i] * 1e9`) and forces
  `unset sqrnoise`; the stale "provisional 5T OTA" caveat is replaced (the DUT
  amp is the #42 telescopic-cascode OTA).
- Historical records `20260910-060222-a6f8b96` and `20260910-060236-a6f8b96`
  are unchanged. Their "uVrms" and "nV/sqrt(Hz)" columns are square-rooted
  amplitudes and are not corrected measurements; the "squared back" figures
  in the table above remain an arithmetic reinterpretation of old numbers,
  not new evidence.
- This is unit verification on a resistor, not a DUT measurement. **No new
  current-DUT noise record exists and no A6 threshold or pass is claimed.**
- Deferred: current schematic and extracted DUT records over the full
  -40/27/125 C, +/-10 % supply, process matrix must be minted through the
  fleet after #268 supplies noise request/ingestion support (#268 Phase B
  consumes this contract). Full-PVT grids do not run on shared dispatch
  workers.
