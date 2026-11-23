# 0008: `par_r` resistor-mismatch model risk — revised assessment (successor to 0004)

- **Status**: proposed
- **Date**: 2026-10-24
- **Decided by**: Builder (issue #386, part of #239), pending both-key review and operator ratification

> This record changes **no ratified spec value** and makes **no PASS claim**.
> It is the operator-authorized preparation of 2026-10-19 (option 1 on #239):
> a revised model-risk assessment plus a pointer to a bounded validation plan.
> [0004](0004-par-r-mismatch-coefficient-risk.md) is left byte-identical (it is
> history); this record supersedes its *conclusion* only once ratified, and
> until then 0004 stays `proposed` and this one is additive. Nothing was
> simulated, measured, bought or sent to a vendor to write it. Final schematic
> signoff stays blocked on #239.

Verification stamp: figures were read from the tree at `origin/main` @
`1d498351` on 2026-10-24, from the pinned records named inline, and from the
installed PDK (`~/.ciel/gf180mcuD`, `SOURCES` = open_pdks `f6eeac7d`, ngspice
deck sha256 prefix `f6f4a96e`, matching `models_lib_sha256` of the 2026-10-16
fleet run). The review calculations below use those same records, including
the per-sample MC reports. Anything not re-derived is marked **not traced**.

## Context

0004 accepted `par_r = 0.021` as a bounded risk because, on the then-current
evidence, "no corner's pass/fail verdict changes" when the resistor
contributor is scaled ×0.5/×2. That premise no longer holds on the final-DUT
evidence (`sim/suite/combined/20261016-013300-999e5cf.md`, built from
`sim/output-voltage-tc/records/20261016-010723-ee8a503.md` and
`sim/mc-untrimmed/records/20261016-013258-999e5cf.md`): the baseline passes
81/81 corners. The combined tool's ×2 sensitivity rule puts **3/27 corners
outside the window at 125 °C**. The ×0.5/×2
exercise is a sensitivity test, not an uncertainty interval; `par_r = 0.021`
is **not** accepted here as validated.

### Why the tool reports a flip, and when the result changes

Let A, R and F be the measured 3σ half-widths of the all-on, resistor-only
and MOS+BJT-only MC groups. Scaling resistor σ by k, `par_r_sensitivity()`
in `sim/suite/combined.py` uses `H(k)² = A² + (k² − 1)R²`. It treats the
resistor variance as independent when scaling it. Anchoring at A keeps the
observed excess `E = A² − F² − R²` fixed at every k. The pinned MC record's
sensitivity-ranking table (N = 300 per group) shows the discrepancy. All
widths and their differences are in mV.

| T (°C) | A | R | F | Quadrature Q = √(F² + R²) | A − Q | E/A² | Implied ρ = E/(2RF) |
|---|---|---|---|---|---|---|---|
| −40 | 10.6922 | 2.0583 | 9.7368 | 9.9520 | +0.740 | 13.4 % | +0.38 |
| 27 | 10.8287 | 2.6503 | 9.7749 | 10.1278 | +0.701 | 12.5 % | +0.28 |
| 125 | 11.1807 | 3.5245 | 9.9125 | 10.5205 | +0.660 | 11.5 % | +0.21 |

At 125 °C the 0.660 mV gap is nearly half the tightest baseline margin.
The combined report gives `bjt_ff_125c_3.63v` 1.356 mV above the lower
limit at k = 1. With its centre held fixed, the half-width can grow to
11.1807 + 1.356 ≈ 12.537 mV before reaching the limit. The table solves
for k at that width and checks all 27 hot corners at k = 2.

| Treatment of the excess E | H(k)² | H(2) (mV) | Hot corners outside at ×2 | Break-even k at 3.63 V |
|---|---|---|---|---|
| E scales as covariance, assuming fixed correlation | F² + k²R² + kE | 13.289 | 3/27 | 1.68 |
| Tool rule, E held fixed | F² + k²R² + E | 12.739 | 3/27 | 1.89 |
| Rebuild from independent components, E omitted | F² + k²R² | 12.163 | 0/27 | 2.18 |

Under the tool rule, ×2 adds 1.558 mV. That consumes the 1.356 mV margin
and the 1.376 mV margins at `bjt_ff_125c_2.97v` and `bjt_ff_125c_3.30v`
(break-even k ≈ 1.91 for those two). The next-tightest hot corner has
2.196 mV of margin. Rebuilding by quadrature gives the tightest corner
2.016 mV of margin at k = 1, enough for its 1.643 mV step at ×2.
The three treatments give a first-crossing range of **k ≈ 1.68–2.18**.
These are conditional calculations on the same data. A physical bound on
the coefficient would require evidence for how E changes with k (G6).

Three things changed relative to 0004's evidence (records
`20260801-232002-960f726` / `20260801-234837-960f726`):

1. **Margin, not sensitivity, is what changed.** 0004's own text states the
   accuracy row was then failing "for an unrelated and much larger reason (an
   un-recentred mean)", so a corner could not flip: it had already failed. On
   the final DUT the row passes with a worst margin of 1.356 mV, so a 1.5 mV
   shift is decisive. The coefficient did not become more important; the
   headroom it was hiding behind is gone.
2. **The mismatch spread shrank.** All-on 3σ at 125 °C is 11.181 mV now
   versus 16.811 mV in 0004; MOS+BJT-only fell from 15.19 to 9.91 mV. What
   changed in the DUT to cause that is **not traced here** (canonical DUT last
   touched in `aeaca90e`, DR-0007 retune); only the records, not a cause, are
   cited. The resistor-only 3σ is nearly unchanged (3.953 → 3.525 mV at
   125 °C), so its variance share rose from 2–6 % to 3.7–9.9 %.
3. **Re-centring consumed the slack.** The 125 °C corners sit at the low edge
   (deterministic Vref 1.18859–1.18861 V for `bjt_ff`, window floor 1.176 V),
   so the 3σ lower bound has only ≈1.4 mV to spare.

### What the model actually does (and does not) represent

- **Source of the coefficient.** In the installed PDK the ngspice deck
  (`libs.tech/ngspice/sm141064.ngspice`, `ppolyf_u`, line 38723 on this
  install) sets `mis_r=0` and contains **no occurrence of `par_r` or `var_r`**.
  The coefficient appears only in the Xyce variant of the same release
  (`libs.tech/xyce/sm141064.spice`, line 38371): `par_r=0.021`,
  `par_sqrtarea='sqrt(par*(r_l)*(r_w))'`, `var_r='0.7071*par_r*1e-06/par_sqrtarea'`,
  `mis_r='agauss(0,var_r,1)'`. 0004 and `run_mc_untrimmed.py` (line 205) describe
  it as a commented-out line in the ngspice deck; that description does **not**
  reproduce against this install and should be corrected in a later record or
  tool note, not edited in place. Either way the value is the foundry's own
  constant in a mode the ngspice flow does not enable, with no documented
  extraction, geometry range, temperature or process-corner dependence.
- **Units.** `var_r = 0.7071·par_r·1e-6/√(r_l·r_w)` with `r_l`, `r_w` in metres
  is `A_R/√(W·L)` with `A_R = 0.7071·0.021 µm = 0.01485 µm` ≡ **1.485 %·µm**
  of relative σ for a 1 µm² (edge-corrected) device. The 0.7071 factor is the
  usual 1/√2 pair-to-single conversion; whether `par_r` is a *pair* difference
  coefficient or a single-device σ in the foundry's own convention is
  **unconfirmed** — a √2 ambiguity is itself inside the ×2 case.
- **Injection method.** `run_mc_untrimmed.py` (`resistor_mismatch_sigma()`,
  `inject_resistor_mismatch()`) applies `r_length = L·(1 + agauss(0, σ, 1))` per
  `ppolyf_u` instance. In the pinned ngspice deck (lines 38723–38743), the
  draw changes the body resistance `rb` through `r_n = r_l/r_w` and the
  fringe capacitors `c1` and `c2` through `l='r_l/2'`. The two terminal
  resistors `rt1` and `rt2` have fixed length `l='s*1u'`, independent of
  `r_length`. This corrects the terminal-segment description in the pinned
  MC record. In its DC operating-point bench the caps carry no current,
  so only the body change contributes to the DC comparison with `mis_r`.
  Draws are independent per instance, so there is **no
  gradient, no layout correlation and no common-centroid benefit**
  (`sim/mc-untrimmed/records/20261016-013258-999e5cf.md` lists 65 injected
  instances: `XR1`, `XR2` and 63 identical 2 µm × 2.77 µm trim units at
  σ = 0.639 % each). Whether that is conservative or optimistic for the
  actual layout is **unknown**.
- **Geometry.** Per-instance σ: `XR1` (2 × 446 µm) 0.050 %, `XR2` (2 × 39.2 µm)
  0.170 %, trim units 0.639 %. Pelgrom scaling to small, narrow poly is the
  extrapolation most likely to be wrong (narrow-width effects, edge roughness
  and contact resistance do not follow 1/√area); this is a physical
  argument, not a measured finding, and is recorded as a risk driver.

## Decision

1. **Record the risk as open and not bounded by 0004's argument.** The
   statement "no corner changes verdict" is withdrawn as a basis for
   acceptance. The pinned baseline passes 81/81 corners. The tool's rule
   puts three hot corners outside at ×2, while the quadrature reconstruction
   puts zero outside. The choice between these treatments is unresolved.
2. **`par_r = 0.021` stays a named assumption, not a validated value.** No
   coefficient from another process, and no larger N, is accepted as
   validation by itself: the unknown is the process/model assumption (units
   convention, extraction, geometry range, injection method), not sampling noise.
   N=300 already gives ≈4 % standard error on σ.
3. **Adopt the bounded validation plan** in
   [`sim/par-r-validation-plan.md`](../../sim/par-r-validation-plan.md) as the
   route to closing or quantifying the risk. The plan is **not executed** by
   this record; execution needs its own operator authorization.
4. **Named data gaps** (each blocks any validation claim until closed):
   - G1: authoritative statement from the PDK owner of what `par_r` is
     (pair vs single-device σ, extraction geometry range, temperature/corner
     behaviour) and why it is enabled in Xyce but `mis_r=0` in ngspice.
   - G2: measured (or foundry-published) `ppolyf_u` resistor mismatch at this
     design's widths/lengths (2 µm × {2.77, 39.2, 446} µm). None exists in this
     repo.
   - G3: layout-dependent matching assumptions (unit orientation, dummies,
     interdigitation) — layout is not drawn for the final DUT.
   - G4: effect of the length-jitter approximation versus a body-only `mis_r`
     injection — needs a new simulation, so it is plan-only.
   - G5: why the DUT's MC spread fell from 16.8 to 11.2 mV since 0004 (not
     traced), since it set the margin that the resistor term now threatens.
   - G6: the cause and scaling of the excess all-on variance are unknown.
     The implied ρ in the table assigns the entire excess to covariance.
     Pairing `mm_res` and `mm_fetbjt` by sample index and seed in the
     [pinned MC reports](../../sim/mc-untrimmed/corners/20261016-013258-999e5cf)
     gives Vref correlations of −0.05, −0.06 and −0.08 in temperature order.
     The positive implied values therefore cannot be read as measured
     correlations between those isolated outputs. Reuse of common random
     numbers across groups and a circuit interaction are hypotheses to test.
5. **Ratified limits are untouched.** The ±2 % window, the 3σ convention and
   N ≥ 300 stand. Nothing is relaxed to make the ×2 case pass. Final signoff
   remains #239's, through both keys under `ratification/` and then the operator.

## Alternatives considered

- **Edit DR-0004 in place** — rejected; history is preserved and the lint
  enforces append-only on ratified records.
- **Declare ×2 an upper bound and accept** — rejected: the ×0.5/×2 span is an
  arbitrary sensitivity, not a derived interval, and a larger 125 °C error
  than 2× is not excluded by any source in the repo.
- **Raise N or add a second process's coefficient to "validate"** — rejected;
  neither addresses the process-specific model assumption (Decision 2).
- **Re-centre or resize R1/R2 to regain margin** — out of scope (circuit
  change); it would also change the evidence the verdict rests on.
- **Run the plan now** — out of scope per the 2026-10-19 ruling: no new
  simulations, measurements, spending or vendor contact.

## Consequences

- The combined-accuracy report retains its ×2/125 °C FAIL under the tool's
  rule. Any future use of that result for signoff must account for G6.
- #239 keeps its blocker; this record gives its reviewers a self-contained
  statement of what is and is not known, and the cheapest next steps.
- If ratified, 0004's acceptance condition 1 is treated as no longer in force;
  conditions 2 (structurally subordinate — still true in rank, resistor share
  ≤ 9.9 %) and 3 (tool re-checks each run) remain.
- Any later validation that changes `par_r` supersedes the affected
  `sim/mc-untrimmed/` and combined records by new records, never by edits.
- The combined tool reaches the first hot-corner limit at k ≈ 1.9. The
  alternative treatments above reach it at 1.68 and 2.18. The physical
  upper bound on resistor mismatch remains unknown.
