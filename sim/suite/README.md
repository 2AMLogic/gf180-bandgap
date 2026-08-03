# sim/suite — one testbench per spec line

```bash
python3 sim/run_suite.py                  # every bench, full PVT matrix, mints records
python3 sim/run_suite.py --list           # the ratified-spec-row -> testbench index
python3 sim/run_suite.py --smoke          # nominal-only debugging run, records nothing
python3 sim/run_combined_accuracy.py      # the two-legged accuracy verdict, from records
```

`python3 sim/run_suite.py` is the single command that runs every spec-line
testbench over the full PVT matrix and prints a **per-spec-line pass/fail
summary** against README.md's ratified target-spec table. A run where every
line in that summary reads PASS is the operational definition of
**simulation-complete** on this block's maturity ladder.

The suite simulates nothing itself. It drives `sim/run_corners.py` once per
experiment slug — so every bench mints an ordinary append-only record under
`sim/<slug>/records/` in the format `sim/README.md` ratifies — and then reads
back the raw per-corner logs those runs wrote to roll individual
measurements up into per-spec-line verdicts. The summary is a *roll-up of
evidence*, never a substitute for it.

## The index

| Ratified row | Bench | Gate |
|---|---|---|
| **Output reference (both legs)** | `sim/output-voltage-tc/` **+** `sim/mc-untrimmed/` | mean ± 3σ mismatch interval ⊆ 1.176–1.224 V at every corner |
| Output reference (corner leg alone) | `sim/output-voltage-tc/` | `vref` ∈ 1.176–1.224 V at every corner |
| Temp coefficient | `sim/output-voltage-tc/` | `tc_ppm` ≤ 50 ppm/°C (box method) |
| PSRR | `sim/psrr-dc/` | `psrr_1hz_db` and `psrr_1khz_db` ≥ 60 dB |
| Line regulation | `sim/line-regulation/` | `linereg_mv_per_v` ≤ 1 mV/V |
| Supply (±10%) | `sim/line-regulation/` | Vref inside the accuracy window across 2.97–3.63 V |
| Quiescent current | `sim/iq/` | `iq_ua` ≤ 50 µA |
| Startup | `sim/startup/` (**owner #11**) | that bench's own verdict |

`sim/suite/spec.py` is the authoritative copy of that table in code, with the
measurement convention for each row. Rows the suite deliberately does *not*
claim — trim (#14), area (#15/#16), and the open items A6/A7 — are listed in
every summary it prints, because "simulation-complete" is only an honest
phrase if what is missing is stated in the same breath.

### The accuracy row takes two benches, not one

The ratified Output-reference row is written as "1.20 V ±2% untrimmed
(3σ, mismatch MC N≥300 **+** process corners, −40…125 °C)" — a **two-legged**
basis. Neither bench's own verdict is that row's verdict: `output-voltage-tc`
has no device mismatch, and `mc-untrimmed` runs at `tt`/3.30 V only.
`sim/suite/combined.py` states the combination rule and issues the joint
verdict; `python3 sim/run_combined_accuracy.py` runs it standalone (no PDK,
no ngspice — it reads both benches' committed records), and a full
`run_suite.py` run prints the same verdict inline.

- **Granularity: per corner, rolled up per temperature.** One pass/fail per
  corner of the 81-point matrix, because the process corner is an enumerated
  worst case rather than a distribution — a per-temperature-only verdict
  would hide *which* corner binds. The per-temperature table is then the
  worst-margin corner at each of −40/27/125 °C, the shape the MC record's own
  window table uses.
- **The rule.** `delta(T) = mean(mm_all,T) − vref_det(tt_<T>c_3.30v)`;
  each corner's interval is `vref_det(c) + delta(T) ± 3σ(mm_all,T)`, and it
  must fit inside 1.176–1.224 V. Anchoring `delta` on the one corner both
  benches simulate means the combined interval at `tt`/3.30 V *is* the MC
  record's own mean ± 3σ window — the combination adds corners to that
  record's table, it never restates its numbers as something else.
- **The approximation, and its guard.** The mismatch spread is measured at
  `tt`/3.30 V and applied at every corner, i.e. local mismatch is treated as
  separable from the global corner (first order: a slow corner shifts `gm/Id`
  and therefore the mismatch gain a little). The guard is an **anchor
  cross-check**: the MC bench's deterministic control group (`mm_ctrl`) and
  the corner leg's `tt/3.30 V` point are the same operating point reached by
  two independent code paths and must agree to 100 µV. If they disagree the
  verdict reads `INVALID`, never PASS and never a FAIL blamed on the design.
- **`par_r` sensitivity.** The mismatch leg's resistor sigma comes from a
  coefficient that ships commented out in the PDK model, so every report
  re-judges the matrix with that one contributor scaled ×0.5 and ×2 and says
  whether any corner's verdict moves. The accepted risk is recorded in
  [`spec/decision-records/0004-par-r-mismatch-coefficient-risk.md`](../../spec/decision-records/0004-par-r-mismatch-coefficient-risk.md).
- **Which two records get paired.** The legs are matched on a shared
  **Netlist provenance** class (`sim/README.md`'s required record field):
  the newest record across both benches names the class, and each leg then
  contributes its own **newest** record of that class — schematic with
  schematic, extracted with extracted. A bench that has not been re-run
  post-layout therefore never drags the other leg's extracted record into
  the graft. Where no same-provenance pair exists at all, the report says so
  and claims no verdict, rather than reporting the (guaranteed) anchor
  disagreement as if the two benches disagreed.
- **Re-running.** Within that pairing rule both legs default to their newest
  record, so after either bench is re-run a bare
  `python3 sim/run_combined_accuracy.py` re-judges against the new evidence
  with no argument changes; `--mc-record` / `--corner-record` pin a specific
  pair and are never overridden (pinning one leg makes the other match its
  provenance class; pinning both is honoured as given, including a
  deliberate cross-provenance comparison, which the report labels as such).
  Reports land in `sim/suite/combined/<record-id>.md` and are append-only
  like everything else under `sim/`.

### Startup is wired in, not reimplemented

The startup row is verified by **#11**'s transient bench. This suite runs the
`startup` slug if it exists and reports that bench's own overall verdict; it
does not invent limits for it. Until #11 lands, `sim/startup/` is absent and
the row reports **PENDING — bench not in the tree yet**: a missing bench is
never a silent pass, and never a hard error either.

## Measurement conventions (the parts that are easy to get wrong)

- **TC is box, not endpoints.** `output-voltage-tc` sweeps temperature
  *inside* one ngspice run (`dc temp -40 125 1`, 166 points) at every
  process/supply point, and reports
  `(Vref_max − Vref_min) / (Vref_27°C · 165 °C) · 10⁶`. A three-point
  (−40/27/125 °C) evaluation steps over the parabolic curvature peak
  whenever the peak falls between those temperatures, and understates TC.
  The bench measures the three endpoint values too, so every summary states
  what an endpoint-only evaluation *would* have claimed, and flags corners
  whose extremum lies strictly inside the sweep.
- **PSRR's "DC" is a stated frequency.** An AC analysis cannot evaluate
  0 Hz, so the claim is the low-frequency asymptote at 1 Hz, and the record
  says so. The ratified row is "> 60 dB DC–1 kHz", so 1 kHz is gated too.
  The rest of the curve (10 Hz … 1 MHz spot columns, plus the full 161-point
  sweep printed into each raw log) is reference data, not a claim.
- **Line regulation is a box over a dense sweep**, `(Vmax − Vmin)/0.66 V`
  across 133 supply points, not the endpoint chord — a three-point
  evaluation can step straight over a local nonmonotonicity.
- **Iq is the whole block**, at every corner, worst corner governs.
- **Everything is unloaded**, because the ratified PSRR/load rows leave the
  load condition open (amendments A4/A7). When those close, the benches get
  a load and mint a new record set; existing records are not reinterpreted.

## Harness-integrity cross-checks

A suite that reports confident numbers from a broken sweep is worse than no
suite. Three checks guard that, and their results are printed with every
summary:

1. Each bench asserts its internal sweep really ran (`sweep_points`,
   `v_lo_check`/`v_hi_check`, `f_dc_hz`/`f_band_edge_hz`) — so an index into
   a sweep means the temperature/voltage/frequency the record names.
2. The suite cross-checks the two independent temperature mechanisms: the
   operating point at the harness's outer `.temp` axis vs the same
   temperature inside the testbench's own `dc temp` sweep. They are the same
   physical quantity reached two different ways; a disagreement means one of
   them is not doing what the record claims.
3. `sim/suite/spec.py`'s ratified limits and each `tb.json`'s own checks are
   asserted equal by the unit tests, so the duplication (needed, because a
   bare `run_corners.py <slug>` must judge itself against the spec too)
   cannot drift.

## Re-running, and the append-only rule

Re-running is always safe and is the intended workflow: each bench mints a
fresh `<record-id>`, and the runner refuses to overwrite an existing record
or snapshot. The suite writes its own summary to
`sim/suite/summaries/<timestamp>-<sha>.md`, also new per run. Nothing under
`records/`, `netlist-snapshots/` or `corners/` is ever modified — `npm run
lint` fails the PR if it is (`sim/check_records.py`).

A run against a dirty working tree is marked as such in every record it
mints and is not citable as a clean-tree result; commit first, then run.

## Post-layout (#17)

```bash
python3 sim/run_suite.py --dut layout/netlist/bandgap_top_extracted.spice
```

No bench, manifest or limit changes: the DUT is an include, the record's
**Netlist provenance** field switches to `extracted`, and the new record set
sits beside the schematic-level one under the same experiment slugs. See
`sim/dut/README.md`.

## Adding a bench

1. Create `sim/<slug>/testbench/{tb.json,<name>.spice}` — a netlist fragment
   plus a manifest naming `"dut"`, the ratified `claim` text, and `checks`
   carrying the ratified numbers (see `sim/harness/README.md`).
2. Add a `SpecLine` to `sim/suite/spec.py` naming the README row it claims,
   the slug, and the same limits.
3. `python3 -m unittest discover -s sim/tests` — the index/manifest
   agreement test will tell you if the two copies of the number disagree.
