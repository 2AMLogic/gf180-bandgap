# 0004: `par_r` resistor-mismatch coefficient accepted as a documented risk

- **Status**: proposed
- **Date**: 2026-08-03
- **Decided by**: Builder (issue #97), pending operator ratification

> This record changes **no ratified spec value**. It records a *methodology*
> risk in how one leg of the untrimmed-accuracy row is simulated, the bound
> measured on what that risk can cost, and the decision to proceed with it
> named rather than removed. Per CLAUDE.md the spec itself is untouched.

## Context

`sim/mc-untrimmed/` supplies the mismatch-MC leg of the ratified
Output-reference row. Of the three device groups it perturbs (MOS, BJT,
resistors), the **resistor** group has no live model support: every
poly-resistor `.subckt` in the gf180mcu deck carries the per-instance
mismatch hook (`rb ... r='...*(1+mis_r*sw_stat_mismatch)'`) but ships
`mis_r` fixed at `0`, alongside a **commented-out** Pelgrom-style sigma
formula whose coefficient is `par_r = 0.021`
(`var_r = 0.7071*par_r*1e-6/sqrt(par*r_l*r_w)`). `run_mc_untrimmed.py`
reuses that disabled coefficient as its resistor-mismatch sigma source
(`resistor_mismatch_sigma()`), injecting the draw through drawn-length
jitter so it stays independently gateable from MOS/BJT mismatch.

The coefficient is therefore **the foundry's own constant, used in a mode
the foundry does not document**: it is present only as a comment, with no
statement anywhere this repo has found that it is the intended value, how it
was extracted, or over what geometry range it holds. Restated in the units
mismatch coefficients are usually published in, it is
`A_R ≈ 1.485 %·µm` on the model's edge-corrected dimensions
(`σ_R/R [%] = 1.4847 / sqrt(W·L [µm²])`), which is the number an independent
source would have to be compared against.

A bandgap's untrimmed accuracy depends on a resistor *ratio*, so an
unvalidated resistor-mismatch sigma is not a cosmetic caveat: it is a term
in the claimed 3σ spread. Issue #97 required this to be validated, formally
accepted as a documented risk, or routed to the friction-protocol tracker
before the combined untrimmed-accuracy verdict is treated as final.

## Decision

**Accept `par_r = 0.021` as a named, bounded methodology risk**, on these
three conditions, all of which are now in force:

1. **The bound is measured, not asserted.** Every combined-verdict report
   (`sim/suite/combined.py`, `python3 sim/run_combined_accuracy.py`) re-judges
   the whole 81-corner matrix with the resistor contributor scaled ×0.5 and
   ×2 — a 4× span on the coefficient — using
   `σ_all(k)² = σ_all² + (k² − 1)·σ_res²`, anchored on the *measured* all-on
   spread so only the contributor in doubt moves. Against records
   `20260801-232002-960f726` (MC) and `20260801-234837-960f726` (corners),
   the 3σ half-width moves from **16.217 / 16.364 / 16.811 mV**
   (−40/27/125 °C) to **16.686 / 17.143 / 18.152 mV** at ×2 and
   **16.097 / 16.163 / 16.459 mV** at ×0.5 — a worst-case **+1.34 mV (+8.0 %)
   at 125 °C** — and **no corner's pass/fail verdict changes** under either
   scaling.
2. **The risk is structurally subordinate.** The same MC record measures the
   resistor-only 3σ contribution at 2.268 / 2.951 / 3.953 mV against an
   all-on 16.217 / 16.364 / 16.811 mV, i.e. a **2–6 % share of the
   variance**; MOS+BJT mismatch (14.92 / 14.96 / 15.19 mV) dominates it by
   roughly an order of magnitude. A coefficient error would have to be
   several-fold *and* in the pessimistic direction before it could govern the
   verdict — the arithmetic above says even 2× does not.
3. **The verdict re-checks it every run.** The sensitivity band is emitted by
   the tool, not copied into prose, so if a future re-run (a re-centred mean,
   a resized `R1`/`R2`, a post-layout DUT) ever makes a corner's verdict
   depend on the coefficient, the report says so in the same run that first
   makes it true, rather than at the next audit.

The risk is **not** closed by this record; it is bounded and tracked. It
closes on silicon (a measured poly-resistor mismatch coefficient for this
process) or on the PDK documenting the coefficient for enabled use.

## Alternatives considered

- **Validate against an independent source (#97's option a)** — not
  achievable honestly today. Validation means either a published Pelgrom
  coefficient for *this* process's unsilicided poly resistor, or measured
  silicon. This repo has neither, and a literature number for a different
  process/sheet-resistivity would be a substitution dressed up as a
  validation. Recording an unsupported citation would be worse than
  recording a bounded assumption. The restated `A_R ≈ 1.485 %·µm` above is
  left here precisely so the comparison is a one-line job when a source does
  appear.
- **Block the combined verdict until the coefficient is validated** —
  rejected. It would stall a verdict whose outcome the coefficient
  demonstrably does not decide (condition 1), on a block whose accuracy row
  is failing for an unrelated and much larger reason (an un-recentred mean).
  Stating the bound is more informative than withholding the result.
- **Drop resistor mismatch from the MC leg entirely** — rejected. That would
  *lower* the reported spread by removing a real contributor, i.e. relax the
  claim by omission, which CLAUDE.md forbids more clearly than it forbids a
  documented assumption. The 3σ spread would read 14.92 / 14.96 / 15.19 mV
  (the MOS+BJT-only columns) instead of 16.22 / 16.36 / 16.81 mV, i.e. wrong
  in the optimistic direction by up to 1.6 mV.
- **Edit the vendored PDK model to enable `mis_r`** — rejected on the same
  grounds #97 states: vendored PDK files are not edited here, and doing so
  would make every record depend on a local patch that no reviewer's PDK
  install reproduces. (The parameter *can* be overridden from the instance
  line without touching the deck — `run_mc_untrimmed.py`'s docstring explains
  why that route was still not taken: `mis_r` rides the same global
  `sw_stat_mismatch` switch as MOS/BJT mismatch, so it cannot be gated
  per-family, which the sensitivity groups require.)
- **File it as a friction-protocol issue instead (#97's option c)** — the
  *tool/PDK* half of this genuinely is a friction item, and has been filed:
  [`2AMLogic/klayout-tools#355`](https://github.com/2AMLogic/klayout-tools/issues/355),
  written generically (a device family whose deck mismatch ships disabled
  makes an MC run silently sample fewer families than it appears to; the
  disabled coefficient is undocumented; the mismatch switch is global across
  families). But filing it upstream does not decide what *this block* does
  in the meantime — that is a design-side judgement the tool tracker must not
  carry, per CLAUDE.md's instruction to keep design specifics out of it.
  Hence: friction issue **and** this record, not one or the other.

## Consequences

- The combined untrimmed-accuracy verdict is reportable now, with its
  dependence on this coefficient quantified in the same document rather than
  named in prose elsewhere.
- Any future report where the ×0.5/×2 sensitivity band *does* flip a corner
  supersedes the "structurally subordinate" finding above and must trigger a
  new decision record — the tool emits the check that would catch it.
- Where a mismatch record's committed logs lack the resistor-only group, the
  combined report says the band is **not evaluable from this record** and
  points here, instead of quietly omitting the section. The bound therefore
  has to be re-established from a record that carries all four MC groups.
- If silicon or PDK documentation later contradicts `par_r = 0.021`, every
  `sim/mc-untrimmed/` record and every combined report is re-run against the
  corrected value; the affected records are superseded, not edited
  (`sim/README.md`'s append-only rule).
- This record does not weaken the ratified ±2 % window, the 3σ convention, or
  the N ≥ 300 floor. Nothing in the spec table moves.
