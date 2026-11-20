# `par_r` resistor-mismatch validation plan (#386)

Part of #239. **Plan only, kept separate from execution.** Nothing was
simulated, measured, purchased or sent to a vendor to write it. Executing any
step needs its own operator authorization. It validates nothing, relaxes no
limit and makes no PASS claim. Companion to proposed
[`spec/decision-records/0008-par-r-mismatch-model-risk-successor.md`](../spec/decision-records/0008-par-r-mismatch-model-risk-successor.md);
format follows [`sim/diagnostic-bench-fleet-plan.md`](diagnostic-bench-fleet-plan.md).

Verification stamp: read from the tree at `origin/main` @ `1d498351` on
2026-10-24, plus the installed PDK (`~/.ciel/gf180mcuD`, open_pdks `f6eeac7d`).
The review calculations use the same pinned records. Unmeasured items are
marked **unmeasured**.

## 1. Question to answer

Is `par_r = 0.021` (≡ `A_R` = 1.485 %·µm on edge-corrected area) a correct
mismatch coefficient for this design's `ppolyf_u` resistors, and is the
length-jitter injection a fair stand-in for it? At 125 °C the recorded all-on
3σ width exceeds the isolated groups' quadrature sum by 0.660 mV. The
combined tool's rule predicts 3/27 crossings at ×2 and a first crossing
near k = 1.9. DR-0008 gives k ≈ 1.68–2.18 across three treatments of that
gap, including one with zero crossings at ×2.

## 2. Steps, cheapest first

| # | Step | Closes | Needs | Resource estimate |
|---|---|---|---|---|
| S1 | Read-only review of public PDK documentation and the upstream PDK source history for `par_r`/`mis_r` (pair-vs-single convention, why Xyce enables it and ngspice does not). Offline reading; no contact. | G1 (partly) | none beyond reading | ~0.5 agent-day; no spend |
| S2 | Locate any published or foundry-supplied `ppolyf_u` mismatch data for widths ≈ 2 µm. Unauthorised sources (NDA data) are not used. | G2 (partly) | S1 | ~0.5 agent-day; no spend |
| S3 | Ask the PDK owner/maintainers a written question for G1 and G2. **Vendor contact: needs operator authorization.** | G1, G2 | operator ok | operator time; response time **unknown** |
| S4 | Compare one new body-only mismatch MC family with the pinned length-jitter family at the same resistor σ. Measure all four groups and check the variance excess at each temperature. **New simulation requires authorization.** | G4, G6 (diagnostic) | S1 | fleet estimate in §3 |
| S5 | Layout matching assumptions (orientation, dummies, unit interleaving) written down before layout, so the independent-draw model can be judged. No layout exists for the final DUT. | G3 | layout phase | none now |
| S6 | Silicon / test-structure measurement of resistor mismatch. **Spending and fab access: operator decision.** | G2 (definitive) | operator ok | **unknown**; not estimated here |

Not accepted as validation by themselves (DR-0008 Decision 2): another
process's coefficient, or a larger N.

## 3. Compute estimate for S4 (the only simulation step)

Use the existing [length-jitter record](mc-untrimmed/records/20261016-013258-999e5cf.md)
as the comparator. Budget one new body-only family at the same nominal supply,
three temperatures (−40, 27 and 125 °C), per-instance σ and seed convention.
Use all four groups at each temperature: deterministic control (`mm_ctrl`),
resistors only (`mm_res`), MOS+BJT only (`mm_fetbjt`) and both (`mm_all`).
**4 groups × 3 temperatures = 12 jobs, 300 samples per job = 3,600 ngspice
runs.** S4 fleet wall time and dollar cost are **unmeasured**.

The stock `mis_r` body multiplier shares `sw_stat_mismatch` with MOS+BJT.
For the comparison, give the resistor multiplier its own enable in a
bench-local copy of `ppolyf_u` and keep the foundry body equation and
nominal geometry. Turn the resistor draw and native mismatch on separately
in the two isolated groups and together in `mm_all`. Check that `mm_ctrl`
reproduces the nominal operating point and has zero spread. This makes a
resistor-only measurement possible while retaining a direct all-on measurement.

For each family and temperature report the measured all-on 3σ width, the
quadrature sum and their difference. Preserve sample IDs and seeds. Compare
the correlation of the paired isolated Vref outputs with the correlation
implied by the all-on variance (G6). Shared seeds can assign different
draws to devices as groups change. If the residual persists, report G6
as open. A repeat with independent random streams to test the common-seed
hypothesis would require a separate estimate and authorization.

Submission goes through `klt sim` with `monte_carlo` and the batch backend
(never a local grid). Capacity caveats from `sim/suite/fleet-evidence-239.md`
(`BATCH_MAX_CONCURRENT_INSTANCES=8`, earlier `batch_no_capacity`) are **not
re-checked today**. Proposed stop rule: at most 2 resubmits on a capacity
refusal, then record a blocker under `sim/fleet-blockers/` and stop.

## 4. Evidence required before anyone may call it validated

- A cited authoritative source or measurement for G1 and G2, with identity of
  the process and geometry range covering 2 µm width.
- S4's measured change in all-on 3σ width between injection methods in mV
  at 125 °C, plus the variance comparison at all three temperatures. Using
  a break-even factor for signoff also requires evidence for how the
  unexplained variance changes with k (G6).
- A re-run combined report whose sensitivity table is generated by the tool,
  superseding (not editing) the 2026-10-16 records.
- Both-key review (`ratification/`) and then operator ratification.

## 5. Decision for the operator

Authorize S1–S2 (read-only, near-free) first; they may shrink or sharpen G1/G2
before any spending. S3, S4 and S6 are separate yes/no decisions.
