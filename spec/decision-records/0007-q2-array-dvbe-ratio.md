# 0007: `core.Q2` realised as a 4× unit-PNP array — the effective ΔVBE ratio input amended from 3.634

- **Status**: proposed
- **Date**: 2026-09-14
- **Decided by**: Builder (issue
  [#87](https://github.com/2AMLogic/gf180-bandgap/issues/87)), pending
  two-key ratification review on the PR carrying this record
  (`ratification/ee-key`, `ratification/market-key`)

> **What this record does and does not change.** It proposes amending one
> *device-level input value* that
> [DR-0003](0003-target-spec-ratification.md) carried forward as normative —
> the effective PNP area ratio `A = 3.634` — and **no ratified `README.md`
> target row**. Every ratified limit (Vref 1.200 V ±2 % untrimmed, TC
> < 50 ppm/°C, PSRR, Iq < 50 µA, area, startup) is unchanged by this record
> and must still be met, by the same benches, after the re-sizing it
> implies. Per DR-0005's precedent this record **does not take effect on
> filing**: `design/bandgap_core.sch`, `design/netlist/bandgap_top.spice`,
> `layout/bandgap_top/plan.py`, `layout/floorplan.md` §4.1 and
> `design/bandgap_error_budget.md` §5 are all left unedited here and move
> only in #87's second PR, after ratification. Filing this record does not
> close #87.
>
> **Numbering**: `main` carries DR-0001…DR-0005; DR-0006 is claimed by open
> PR #177 (`0006-area-target-narrowed-post-166.md`). 0007 is the next free
> number that cannot collide with it, per TEMPLATE.md's numbering rule.

## Context

`design/bandgap_core.sch` and `design/netlist/bandgap_top.spice` model the
Brokaw core's large PNP as **one** device:

```
XQ2 vss vss e2 pnp_10p00x10p00 m=1
```

`layout/bandgap_top/plan.py` draws it instead as **four parallel
`pnp_05p00x05p00` unit devices** (`core.Q2#0`…`#3`), placed
`D Q3 Q2 Q2 Q1 Q2 Q2 D` so that `Q1` and `Q2` share an exact centroid —
the common-centroid treatment `layout/floorplan.md` §0/§4.1 committed to.

**Those two circuits do not have the same ΔVBE.** The PDK's saturation
currents for the two drawn geometries are in ratio 3.671, not 4.000, so the
monolithic device's effective ratio measures **3.634** at equal emitter
current (`design/device-characterization.md` §1, record
[`20260731-030932-8fb0ea6`](../../sim/device-pnp-vbe/records/20260731-030932-8fb0ea6.md),
3 BJT corners × 6 temperatures). Four parallel instances of the *same*
subcircuit have, by construction, exactly `4 × is` of one unit, at every
corner and every temperature — the ratio is a topological identity, not an
extraction result. (That identity is an *equal-collector-current* one; the
Brokaw core enforces equal *emitter* currents, which moves the effective
ratio off 4.000 by ≈1 % — see Alternatives argument 2 and Decision item 1.)
Measured directly (ngspice, `bjt_typical`, 27 °C,
6.5 µA/branch, `exp(ΔVBE/VT)` against one `pnp_05p00x05p00` at the same
current; #87's Finding):

| `core.Q2` realisation | VBE @ 6.5 µA | ΔVBE vs 1× 5×5 | effective ratio |
|---|---|---|---|
| one `pnp_10p00x10p00` (schematic) | 0.678096 V | 33.34 mV | **3.632** |
| four `pnp_05p00x05p00` (as drawn) | 0.675423 V | 36.01 mV | **4.027** |

ΔVBE is **+8.0 %** in the drawn circuit, and `Vref = VEB(Q3) + I·(R1+Rtrim)`
with `I = ΔVBE/R2`, so this is a first-order error on the ratified
output-reference row. Neither DRC nor LVS can see it: `layout/lvs/make_reference.py`
derives its reference netlist *from the drawn layout* (step 8, "one `bjt`
card per drawn PNP unit"), so four drawn units match four reference units
and both comparators report clean. It is a schematic-vs-layout **intent**
divergence, invisible to every structural check this repo runs.

**What it costs, on the record.** `sim/postlayout-delta.md` (#17's
schematic-vs-extracted pairing) shows the extracted side failing exactly the
rows a ΔVBE error moves, while PSRR / line regulation / Iq — the rows it does
not — still pass:

| Spec row | Ratified limit | Schematic worst | Extracted worst |
|---|---|---|---|
| Output reference | `vref ≤ 1.224 V` | 1.20185 PASS | **1.25187 FAIL** |
| Temp coefficient | `tc_ppm ≤ 50` | 29.84 PASS | **90.22 FAIL** |
| PSRR (1 Hz / 1 kHz) | `≥ 60 dB` | PASS | PASS |
| Line regulation | `≤ 1 mV/V` | PASS | PASS |
| Quiescent current | `≤ 50 µA` | PASS | PASS |

The attribution is already carried in three places and is not new here:
`README.md`'s Status paragraph ("that gap is attributed to the drawn PNP
array's 4.03 effective dVBE ratio versus the schematic's 3.63"),
`layout/netlist/README.md` (the post-#88 extracted re-run: "the same three
ratified rows that have FAILed at extracted level since #17's original
post-layout re-run … rooted in #87"), and
`sim/mc-untrimmed/records/20260803-012729-feab5b5.md`'s netlist-state note.
#94's items 5 and 6 are blocked on it.

`layout/floorplan.md` §4.1 asserts the opposite — that a 4-unit array "still
measures 3.634, not 4" — which is wrong under **either** option and is
corrected in #87's second PR regardless of what this record decides.

Finally, `DR-0003` made `3.63` normative: its Consequences section records
"the effective PNP area ratio of 3.63 for a drawn 4:1 pair … is now
normative input to #8/#10/#13." That is why this choice needs a decision
record rather than a fix.

## Decision

**Adopt Option A: the schematic and netlist are changed to match the drawn
layout** — `core.Q2` becomes four parallel `pnp_05p00x05p00` unit devices —
and the effective ΔVBE ratio `A` carried as normative design input is
**amended from 3.634 to the unit-array ratio**, nominally **4.000** by model
construction, with the small equal-Ie excess to be re-measured (4.027 at the
one operating point measured so far). Specifically:

1. **The realisation is what this record ratifies, not the number.** The
   4.027 figure above is a single corner, a single temperature, and the
   #17-era operating point; it does not meet the corner coverage a normative
   input deserves. #87's second PR must re-measure the array's effective
   ratio with a device-level record in the style of `sim/device-pnp-vbe/`
   (BJT corners × the −40/27/125 °C temperature axis) **at the current
   design current**, `I = ΔVBE/R2 = 33.374 mV / 6586.5 Ω ≈ 5.07 µA` — not
   at 6.5 µA — and the sizing below locks to *that* measured value.

2. **The `R2` rescale is a single-parameter, closed-form change *to first
   order*, and the TC null must then be re-verified — not assumed.**
   `ΔVBE(T) = VT(T)·ln A`, so replacing `A_old` by `A_new` rescales ΔVBE by
   `λ = ln A_new / ln A_old`, and `R2 → λ·R2` restores `I`, `I·(R1+Rtrim)`
   and `Vref` **at the temperature `λ` was computed at**. Using the
   same-bench pair from the finding table above (4.027 against 3.632, both
   measured on the same setup — *not* the 3.634 three-temperature figure,
   which is a different bench) that is `λ = 1.0800`: `R2`
   `L = 36.341871 µm → 39.2508 µm` (6586.5 Ω → 7113.7 Ω). At an
   exactly-4.000 ratio on the same basis, `λ = 1.0748`. `R1`, the trim unit
   segment and every MOS device are untouched *by the rescale itself*.

   **`λ` is not a temperature-invariant multiplier, and this record makes no
   claim that the TC null survives untouched.** A constant `λ` would require
   `A_old` *and* `A_new` both to be temperature-independent. `A_new` is, by
   the construction argued above. `A_old` measurably is not — inverting the
   same `bjt_typical` row this record already cites
   ([`20260731-030932-8fb0ea6`](../../sim/device-pnp-vbe/records/20260731-030932-8fb0ea6.md))
   with `A_old(T) = exp(ΔVBE/VT)`:

   | T | ΔVBE (measured) | `A_old(T)` |
   |---|---|---|
   | −40 °C | 25.660 mV | 3.5865 |
   | 27 °C | 33.374 mV | 3.6339 |
   | 125 °C | 44.664 mV | 3.6758 |

   `A_old` drifts **+2.5 %** across the ratified temperature axis. This is
   the same fact as ΔVBE_old's known linearity error: it is very *linear* in
   `T` but not *proportional* to `T`, extrapolating to zero near −10 K
   rather than 0 K. The drawn array's ΔVBE is the cleaner PTAT of the two —
   which is an argument *for* Option A — but it is precisely why the two
   realisations cannot be related by a single constant.

   **Magnitude — an order-of-magnitude estimate, not a result.** Applying a
   single `λ(27 °C) = 1.07438` (taking `A_new = 4.000` flat) against
   `R1_total = 97562.8 Ω` at trim code 32, relative to the present TC-nulled
   curve, gives **+4.1 mV at −40 °C, 0 at 27 °C, −6.1 mV at 125 °C** (a
   +3.9/−5.8 mV bow on the PTAT term, plus the `VT·ln(I_new/I_old)` shift in
   `VEB(Q3)`). A ≈10 mV monotonic excursion on a 1.2 V reference across
   −40…125 °C is **≈50 ppm/°C of *new* drift** — against a ratified
   50 ppm/°C limit and a present schematic worst case of 29.84 ppm/°C. That
   residual is very nearly affine in `T`: decomposed, it is a ≈+17.7 mV
   constant offset, a −0.059 mV/K slope (≈ a −3.6 % move in `R1_total`), and
   only ≈0.04 mV of genuine curvature (≈0.2 ppm/°C). So an `R1` re-null plus
   a `Vref` re-centre should recover most of it — but "should" is a
   prediction from one corner's device data with `A_new` assumed exactly
   4.000, which is exactly the kind of claim this repo does not accept
   without a testbench.

   **Therefore PR 2 must, as a precondition of claiming the sizing is
   correct:** (a) re-run the temperature-coefficient bench over the ratified
   PVT axis *after* the `R2` rescale, and (b) where the measured TC or
   `Vref` centring no longer meets its ratified row with margin, re-null
   `R1` and re-centre `Vref` against that measurement, by #147's method.
   PR 2 may **not** infer the TC null from the `λ` algebra. #96's
   Chebyshev-optimal `R1`, #147's `R1` re-centring and #61's `k = 2`
   quiescent-current margin are **starting points** for that
   re-verification, not results preserved by construction. All the figures
   in this item are indicative; the final `λ`, `R2` and `R1` come from
   item 1's re-measurement plus (a) and (b).

3. **No ratified spec row moves.** Every `README.md` limit stays as
   ratified, and #87's acceptance criteria still require the full schematic
   suite plus the extracted re-run to pass against them before the work is
   done. This record does not make any failing measurement pass by moving a
   threshold; it corrects an input the design was mis-sized against, and
   leaves the design to meet the unchanged thresholds.

**Relationship to DR-0003 (explicit, per #87's revision comment): this
amends DR-0003's carried-forward value; it does not preserve it.** DR-0003
is **not** superseded — its ratified target table, its #35 amendments and
its other two carried-forward device facts (forward beta 0.89–2.82) all
stand. What changes is the scope of one sentence: `3.634` remains the
correct, measured figure for a `pnp_10p00x10p00`-vs-`pnp_05p00x05p00` pair
and stays exactly as recorded in `design/device-characterization.md` §1 and
in `sim/device-pnp-vbe/`, but it ceases to be *this design's* ΔVBE input,
because this design no longer builds that pair. Two things make that a
narrow amendment rather than a reopening of DR-0003:

- DR-0003 ratified `device-characterization.md` §1 **by reference**, and §1
  itself offers exactly this alternative in the same sentence that supplies
  the 33.37 mV figure: *"Use **33.37 mV at 27 °C**, or design for an
  explicit N:1 unit-device array whose ratio you re-measure."* Option A is
  the second branch of a choice the ratified source document already put on
  the table; `layout/floorplan.md` §4.1 inverted that advice, which is how
  the divergence survived review.
- The amendment is to an *input*, not to a *requirement*. It changes no
  pass/fail threshold in either direction, and item 1 replaces the old
  value's corner-covered evidence with equally corner-covered evidence
  rather than with a weaker claim.

## Alternatives considered

- **Option B — redraw the layout as a single `pnp_10p00x10p00`, preserving
  DR-0003's 3.634 untouched.** Rejected, for four reasons in descending
  weight:

  1. **It spends matching, which this block cannot measure, to buy paper
     continuity, which it can.** `plan.py`'s own weighting: a
     gradient-induced VBE error between `Q1` and `Q2` reaches `vref`
     multiplied by `R1_total/R2`, i.e. ~**14.8×** what the same error at
     `Q3` costs at the current ratio `14.81259` — which is recorded in
     `design/bandgap_core.sch`'s #147 header block
     (`R1_total/R2 14.63021 -> 14.81259`), not in `bandgap_error_budget.md`,
     whose §5a/§5b still carry the pre-#147 `15.28425` and `14.63021`.
     (`plan.py`'s own prose says "~13×", from the pre-#147
     `R1/R2 ≈ 12.8`; the multiplier has grown, not shrunk, since it was
     written.) That weighting is precisely
     why the drawn array gives `Q1`/`Q2` an *exact* shared centroid
     (verified by `matching_report.py`). A monolithic 10×10 sitting beside a
     5×5 cannot share a centroid with it at all, so the first-order linear
     process gradient across the PNP row stops cancelling. The gf180mcu
     models carry no gradient term — `design/bandgap_error_budget.md` §2.6
     budgets only the *random* Q1/Q2 ΔVBE mismatch (3σ = 0.128 mV →
     2.06 mV at `Vref`) — so Option B's added systematic term would be
     **unbudgeted and unmeasurable in this flow**. Trading a quantified,
     exactly-correctable 8.0 % sizing error for an unquantifiable matching
     risk is the wrong direction for a block whose entire premise is "no
     claim without a testbench."
  2. **3.634 is a model artifact; 4.000 is a topological identity.** The
     3.634/3.671 figures come from how the PDK extracted `is` for two
     *different* drawn geometries — a number with real silicon uncertainty
     (perimeter-vs-area injection, sidewall effects) that this repo has no
     way to validate before tape-out. `N` parallel instances of one unit
     device give exactly `N × is` in the model, and in silicon the ratio is
     set by drawn geometry replication, which is the standard reason analog
     design uses unit arrays for ratioed devices at all.

     **That identity is an equal-*collector*-current one, and the Brokaw
     core enforces equal *emitter* currents** — through devices whose
     forward beta is 0.89–2.82 across corners
     (`device-characterization.md` §1) and whose per-unit current differs
     4:1 from the reference, so the base-current split moves the effective
     ratio off `N` by ≈1 %. That is the mechanism behind the measured
     **4.027** rather than 4.000, and it is why Decision item 1 re-measures
     rather than assuming. The advantage over Option B is therefore narrower
     than a bare "exactly 4" would suggest — but it is still real and still
     decisive: a ≈1 % equal-Ie excess that a testbench can measure at every
     corner is a far better constant than an 8 % divergence rooted in an
     `is` extraction across two different drawn geometries, which this repo
     has no way to validate. Option A makes the design's most sensitive
     constant robust to a PDK model revision; Option B keeps it hostage to
     one.
  3. **The drawn layout is already DRC-clean and LVS-matching in the
     Option A configuration.** Option B redraws `plan.py`'s PNP row,
     invalidates the committed `bandgap_top.gds`, `matching_report.py`'s
     centroid verification and both LVS comparators' reports, and needs the
     full physical-verification loop re-run — on top of the same extracted
     re-run Option A needs. The re-verification cost is not symmetric.
  4. **Option B's one genuine advantage does not pay for the above.**
     Four separately enclosed 5×5 unit cells plus two dummy units do occupy
     more drawn area than a single 10×10 cell at the same 100 µm² total
     emitter area, so Option B would shave a little off the area overrun
     DR-0005 records (80,813.72 µm² against a 50,000 µm² ratified target —
     a 30,813.72 µm² gap). A handful of PNP-cell enclosures is not a
     material dent in that gap, and DR-0005/#160 already identify the
     routing and floorplan levers that are.

- **Change nothing; carry the +8.0 % as a documented schematic-vs-layout
  delta.** Rejected — it is a first-order error on a ratified row, currently
  responsible for 75 of 81 failing extracted corners (#143 item 5) and for
  the extracted leg of #94's items 5/6. A permanently-diverging schematic
  and layout also means no future schematic-level result predicts the
  silicon, which is a worse property than either option's cost.

- **Adopt Option A *and* fold a speculative `R1` re-optimisation into the
  same pass.** Rejected — narrowly, and *not* because `R1` is expected to
  stand still. Decision item 2 establishes that the `λ` rescale is only a
  first-order correction, carrying a predicted ≈50 ppm/°C residual, and it
  makes the post-rescale TC re-measurement plus a conditional `R1` re-null
  and `Vref` re-centre an explicit **obligation** on PR 2. What is rejected
  here is the different thing: pre-emptively re-opening #96's Chebyshev
  search or #147's re-centring against the *modelled* residual, before the
  post-rescale bench that would justify a target exists. A
  measurement-driven `R1` re-null is in scope for PR 2; a re-optimisation
  against a prediction would make the re-run impossible to attribute, and
  would re-tune the design to a number no testbench produced. Any `R1` move
  beyond restoring the ratified TC and `Vref` rows should be driven by its
  own measured objective, in its own issue.

- **Ratify `A = 4.027` as the new normative number directly in this
  record.** Rejected — one corner, one temperature, at an operating point
  the design no longer uses. Ratifying it here would repeat, in the opposite
  direction, the evidence-thinness this issue exists to correct. The
  realisation is ratified; the number is re-measured (Decision item 1).

## Consequences

- **#87's second PR is unblocked and fully specified** once this record is
  ratified: edit `design/bandgap_core.sch` + `design/netlist/bandgap_top.spice`
  (`XQ2` → four parallel `pnp_05p00x05p00`, or `m=4`), take the corner-covered
  ratio re-measurement, rescale `R2` by the resulting `λ`, **re-measure the
  TC over the ratified PVT axis and re-null `R1` / re-centre `Vref` if the
  measurement requires it (Decision item 2 (a)/(b) — this is an obligation,
  not a contingency to be waved through on the `λ` algebra)**, correct
  `layout/floorplan.md` §4.1, re-derive `design/bandgap_error_budget.md` §5,
  and re-run the full schematic suite plus the extracted re-run per #87's
  acceptance criteria. `layout/bandgap_top/plan.py` needs no change — that
  is the point of the option chosen.
- **Every document carrying `A = 3.634` as this design's input must move in
  that PR**, and none may be left behind (a partial update is exactly the
  self-inconsistency #87's Test Plan warns about, and no structural check
  catches it): `design/bandgap_error_budget.md` (§2.6a's servo constraint and
  §5's `I = ΔVBE/R2` derivation), `design/bandgap_operating_point.md`'s
  device table, `design/bandgap_core.sch`'s header comment, and
  `layout/floorplan.md` §4.1. `design/device-characterization.md` §1 and the
  `sim/device-pnp-vbe/` records are **measurements of the two-geometry
  pair** and stay exactly as they are — they were never wrong.
- **The accuracy budget is expected to improve slightly, and this record
  claims nothing about it.** §2.6a's `ρ = VT/(VT + ΔVBE) = 1/(1 + ln A)`
  falls from 0.4365 to ≈0.4179 at 27 °C (at `A = 4.027`), so the servoed-leg
  amplification `1/(1−ρ)` falls from 1.775 to 1.718 (−3.2 %), which should
  reduce the `M1`/`M2` mirror-mismatch
  coefficients and, through §2.4's shared mechanism, the amplifier-offset
  sensitivity by a few percent. Direction is favourable; the magnitude is a
  measurement §2.7b's table must actually re-take in the second PR, not a
  number ratified here.
- **The cost is a full, expensive re-verification.** Everything that keys on
  ΔVBE must be re-run at both provenance levels — schematic suite and
  extracted — including `mc-untrimmed`'s Monte Carlo. That is the most
  expensive re-run class this repo has, and it is unavoidable under either
  option.
- **The final `R2` is not known until the re-measurement lands.** If the
  re-measured ratio differs from 4.027, `λ` and `R2` move with it, so any
  corner or MC record taken before that measurement cannot be reused as
  evidence for the resized design.
- **A re-measurement that undercuts the premise supersedes this record
  rather than patching it.** Forward beta on these devices is 0.89–2.82
  across corners (`device-characterization.md` §1) and the equal-Ie/equal-Ic
  distinction is a ≈1 % effect on the ratio, so if the array's effective
  ratio turns out to be materially current- or corner-dependent, Option A's
  "ratio is a topological identity" advantage narrows and the choice should
  be re-opened in a successor record, per `TEMPLATE.md`'s append-only rule.
- **If the two-key review rules for Option B instead**, the work that record
  would imply is: redraw `plan.py`'s PNP row as a single `pnp_10p00x10p00`
  (dropping the `Q1`/`Q2` shared centroid), regenerate `bandgap_top.gds`,
  re-run DRC and both LVS comparators, regenerate `matching_report.py`,
  revise `layout/floorplan.md` §0/§4.1/§9's matching rationale, and record
  the resulting unbudgeted gradient term as an accepted, unmeasurable risk
  in `design/bandgap_error_budget.md` §2.6 — the shape DR-0004 uses for the
  `par_r` coefficient. The sizing would then stand unchanged, and
  `floorplan.md` §4.1's incorrect paragraph would still need correcting.
