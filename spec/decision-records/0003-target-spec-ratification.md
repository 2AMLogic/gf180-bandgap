# 0003: Target spec ratification (conditional on #35 amendments)

- **Status**: ratified
- **Date**: 2026-07-31
- **Decided by**: Robb Walters (operator), recorded via
  [issue #1, comment 2026-07-31 "Ratification (operator decision, 2026-07-31)"](https://github.com/2AMLogic/gf180-bandgap/issues/1#issuecomment-5147916639)

## Context

`README.md` carried a DRAFT "Target specification" table (Vref 1.20 V ±1%
untrimmed, TC < 50 ppm/°C, PSRR > 60 dB DC, supply 3.3 V ±10%, Iq < 50 µA,
area < 0.05 mm², self-starting < 1 ms) pending engineering ratification per
issue #1. Design-phase work (schematic entry, testbench authoring, MC
methodology) had already been delegated to proceed on the DRAFT basis, but
formal ratification remained required before layout locks to the spec.

Before ratifying, the operator requested a spec-review opinion (skill run
against klayout-tools #124, posted as a comment on #1 on 2026-07-31). That
review, grounded in this repo's own device-characterization evidence
(`sim/device-pnp-vbe/`, `sim/device-pnp-mismatch/`, `sim/device-mos-mismatch/`,
`sim/device-mos-vth/`, `sim/device-resistor-tc/`), found the draft's untrimmed
±1% accuracy row **not credible as written**: the measured MOS input-pair
mismatch (σ(ΔVgs) ≈ 1.12 mV, `pfet_03v3 10/4`) amplified by the Brokaw gain
(G ≈ 14.3, from measured VBE/ΔVBE) implies ≈4% of Vref at 3σ from the
amplifier offset alone, plus a further ±0.6–0.7% direct VBE process-corner
shift — both of which contradict an untrimmed ±1% 3σ claim. The review also
found seven canonical spec lines missing entirely (trim strategy, line
regulation, PSRR-vs-frequency, output noise, load capability, long-term
drift, and a corner-binding statement per row) and returned a verdict of
**ratify-with-amendments**, restated as ten concrete edits (A1–A10) and filed
as issue #35 — input to this ratification, not itself a decision.

## Decision

**The operator ratified the target spec conditional on accepting the
amendments in #35 as-is.** Per the ratification comment on #1: "where the
draft and #35 conflict, the amended values govern immediately." This record
and the accompanying edit to `README.md`'s "Target specification" table
implement that decision:

- The DRAFT table is replaced by the amended table (A1–A10 applied), now
  labeled "RATIFIED 2026-07-31" in `README.md`.
- Three amendments (A4's PSRR load condition, A6's output-noise threshold,
  A7's load-row option) were proposed by the spec review as a *row shape*
  without a numeric value ("operator to pick X" / an either/or with no
  selection made) and are carried through into the ratified table as
  explicit open items rather than invented numbers — see the note
  immediately below the table in `README.md`. This is consistent with
  "amended values govern immediately": where #35 supplies a value, it
  governs now; where it supplies only a shape, the shape is ratified and the
  value remains a follow-on decision.
- The layout-lock gate from the 2026-07-28 delegation (recorded on #1) is
  satisfied once this record and the amended table land on `main`: this
  block's design work may proceed with layout locked to the ratified table.

This record supersedes the DRAFT table previously carried in `README.md`
under "Target specification (DRAFT — engineering to ratify, see issue #1)".
It does not supersede DR-0001 (topology selection) or DR-0002 (3.3V-only
supply scope), which the spec-review opinion assessed and found consistent
with the ratified table; those records are marked ratified alongside this
one (see Consequences).

## Alternatives considered

- **Ratify the DRAFT table unchanged.** Rejected — the operator's own
  spec-review opinion showed the untrimmed ±1% accuracy row is directly
  contradicted by this repo's measured device mismatch data; ratifying it
  as-is would lock the design to a target the repo's own evidence says is
  not achievable without either loosening the number or committing to
  offset mitigation neither of which the DRAFT table stated.
- **Defer ratification pending a full numeric resolution of every open
  amendment** (including A4/A6/A7's unresolved values). Rejected — the
  operator's ratification comment explicitly closes #1 "when the amended
  table merges," treating the nine fully-specified amendments (A1, A2, A3,
  A5, A8, A9, A10, plus the row-shape additions of A4/A6/A7) as sufficient
  to unblock layout-stage work now, with the three open numeric items
  tracked explicitly rather than blocking the whole ratification.
- **Resolve A4/A6/A7's open values unilaterally in this pass** (e.g., invent
  a load condition, noise threshold, or load-row choice). Rejected — the
  spec-review opinion that produced A4/A6/A7 did not supply these values,
  and per CLAUDE.md ("agents do not relax the ratified spec" / spec changes
  require a decision record), inventing a number here would be a design
  judgment call this record does not have standing to make. These remain
  open items for a future, narrowly-scoped decision record when the
  relevant design work (the output stage, tracked in #10) is ready to fix
  them.

## Consequences

- `spec/decision-records/0001-bandgap-topology-selection.md` and
  `spec/decision-records/0002-supply-voltage-scope.md` move from *proposed*
  to *ratified*, referencing this record, since the spec-review opinion this
  ratification accepted explicitly assessed both as consistent with the
  ratified table.
- Layout-stage issues gated on #1 (per the 2026-07-28 delegation) may now
  unblock; #1 closes in the same PR that lands this record, per the
  ratification comment.
- The accuracy row's tightened untrimmed target (±2%, up from ±1%) and its
  explicit 3σ/mismatch-MC/corner basis becomes the number the offset-budget
  work in #8, #10, and #13 designs against; two device-evidence facts the
  spec-review opinion flagged as needing to enter that budget — the
  effective PNP area ratio of 3.63 for a drawn 4:1 pair, and forward beta of
  0.89–2.82 across corners — are already recorded in
  `design/device-characterization.md` (§1, "What this changes for the
  design") and carried forward there; this record does not duplicate that
  content, only confirms it is now normative input to #8/#10/#13.
- Three table rows (PSRR load condition, output noise threshold, the load
  row's max-load-vs-unbuffered choice) remain open numeric decisions,
  explicitly flagged in `README.md` rather than silently assumed; each
  should close out as its own decision record when the output-stage design
  (#10) is ready to fix the value, rather than by amending this record.
- Trim strategy (A2) is now a ratified spec row (range ≥ ±5%, resolution
  ≤ 0.25%/step, at 27 °C), consistent with and further constraining
  DR-0001's already-adopted binary-weighted trim-segment mechanism.
