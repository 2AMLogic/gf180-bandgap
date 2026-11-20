# Roadmap

gf180-bandgap is a bandgap voltage reference on the open gf180mcu PDK, built to exercise klayout-tools and the
open analog flow end to end and to turn every tool gap it hits into an upstream issue.

Status as of 2026-11-13, `main` @ `843879b9`.

This file says where the block is going and why. Live label state is in [`WORK_PLAN.md`](../WORK_PLAN.md)
(generated); the graded verdict of record is the newest file under [`signoff/reports/`](../signoff/reports/).
Where this file and either of those disagree, they win.

## Where it stands

**Spec.** Ratified 2026-07-31 (DR-0003), amended by DR-0006 (interim area ceiling) and DR-0007 (Q2 as a 4x
unit-PNP array, R2 rescaled; ratified 2026-10-02). Three rows are still TBD by ratification itself: PSRR load
condition, output-noise threshold and the load row.

**Schematic, post-DR-0007.** The array ratio was measured (#208), R2/R1 retuned (#209, PR #222) and the embedded
benches synchronized (#210). The final-DUT evidence run is indexed in
[`sim/suite/fleet-evidence-239.md`](../sim/suite/fleet-evidence-239.md): TC, mismatch Monte Carlo (N=300), PSRR,
line regulation, startup and Iq all have records, the combined two-legged accuracy verdict passes 81/81 corners,
and the roll-up `sim/suite/summaries/20261016-015258-1c4f2a2.md` reports all 6 indexed spec lines passing. It is
**not** a final schematic signoff: the `par_r` resistor-mismatch x2 sensitivity case flips 3 corners at 125 C,
and the six diagnostic benches that embed the core have not been re-run.

**Layout.** The committed `layout/bandgap_top/bandgap_top.gds` predates DR-0007. It is DRC-clean and LVS-matched
under the pinned klt 0.8.0 (PR #410, reports `20261028-*`), but those reports do not certify the amended
schematic. The last extracted-netlist comparison, [`sim/postlayout-delta.md`](../sim/postlayout-delta.md), shows
the output-reference and TC rows failing post-layout; it also predates DR-0007.

**T1 sim-validated, graded.** `signoff/reports/20261028-065240-f32fe48.signoff.json` (klt 0.8.0): **4 of 11
items met**.

| Item | State | What moves it |
|---|---|---|
| 1 Design sources | unmet, no evidence | #393, after #204 |
| 2 Layout | unmet, no evidence | #394, after #204 |
| 3 DRC clean | met | re-cut by #204 |
| 4 LVS clean | met | re-cut by #204 |
| 5 Corner verification | unmet, no evidence | #395, after #239 and #204; needs the TBD rows ratified |
| 6 Monte Carlo | unmet, no evidence | #396, after #239 |
| 7 Post-layout | unmet, no evidence | #357 (`klt pex` report), after #204 |
| 8 Characterization report | unmet, no evidence | #397, after #395 |
| 9 Testbenches shipped | met | |
| 10 Repo hygiene | met | |
| 11 Power delivery | unmet, no evidence | #358, after #204 |

The tracking epic is #94; the DR-0007 chain is #202 (phase A #203, phase B #204).

## Now

1. **Review PR #387** (closes #386): proposed DR-0008, the `par_r` model-risk successor to DR-0004, plus
   `sim/par-r-validation-plan.md`. Documentation only, CI green, labelled `loom:review-requested`.
   Done when: the PR is approved and merged with DR-0008 at status `proposed` and DR-0004 byte-identical to `main`.
2. **Bring `signoff/README.md` disclosures up to the cited evidence** (no issue; seed 1). The item 3 and item 4
   sections still describe the August envelopes and say item 4 renders `stale_evidence`; the manifest now cites
   the `20261028-*` reports and item 4 grades `met`. The item 5 section cites the August suite summary, not the
   October final-DUT roll-up.
   Done when: each disclosure quotes the envelope the manifest cites, and `python3 signoff/check_signoff.py`
   passes.
3. **Refresh the Chipalooza proposal against current evidence** (no issue; seed 2).
   `docs/chipalooza/challenge-5-proposal.md` still cites the superseded DR-0005 area ceiling, August DRC/LVS
   reports and pre-DR-0007 sim records.
   Done when: every cited record, report and decision record is the current one, and unmet rows are still stated as
   unmet.
4. **ERC tie declaration probe on the pinned klt** (carved out of #358 step 1; seed 3). klayout-tools#2169 is
   closed; whether klt 0.8.0 computes `erc.missing_tie` on this block without the false single-island collapse
   has not been recorded.
   Done when: a new report under `layout/erc/reports/bandgap_top/` shows the result with `ties[]` declared, and
   `layout/erc/README.md` states it. The item 11 citation itself stays with #358.

## Next

Unblocked by a named item above or by a decision listed under Blocked.

- **Both-key review of DR-0008, then the final `par_r` risk disposition** on #239. Follows PR #387. Done when
  DR-0008 carries a ratified or rejected status and #239 records the disposition.
- **Close phase A** (#211, then #203). Follows #239. Done when the final schematic records and the required
  diagnostic/reference reruns are cross-linked and #203's acceptance list is met without touching a ratified
  limit.
- **Phase B, #204**: regenerate the GDS and LVS reference from the final sizing, re-run DRC and both LVS engines
  on the pinned toolchain, re-extract, and run the extracted PVT suite. Follows #203. Done when new reports and
  records exist for the regenerated layout and the manifest pins move with them. This is also what answers #87.
- **After #204, in any order:** #393 (attest item 1), #394 (item 2 envelope), #357 (item 7 `klt pex` report),
  #358 (item 11 citation), and PR #313 / #308 (CI check that the committed GDS equals `generate.py` output; held
  until the regenerated GDS lands).
- **After #239 and #204:** #395 (item 5 as `klt sim` envelopes), #396 (item 6 `klt yield` report with a negative
  control), then #397 (item 8 generic envelope).

## Later

Direction, each with the question that has to be answered first.

- **The three TBD spec rows.** Question: buffered or explicitly unbuffered output, and at what load is PSRR
  graded, and what is the noise threshold? The evidence and one ranked question per row are in
  [`spec/tbd-row-evidence.md`](../spec/tbd-row-evidence.md); its follow-up map lists the decision records and
  benches that follow each answer. Item 5 cannot grade `met` until these rows are ratified and covered.
- **Post-layout accuracy and TC.** Question: does the DR-0007 array and the regenerated layout close the
  extracted Vref/TC failure recorded in `sim/postlayout-delta.md`? Only #204's extracted run answers it.
- **Substrate ties in ERC.** Question: can a p-substrate tie be expressed at all for a block with no drawn
  p-well layer? `layout/erc/README.md` records that it cannot today, so item 11's tie rule would cover only the
  n-well half.
- **Area.** Question: what does the regenerated layout measure against the DR-0006 interim ceiling, and what
  limits it? Re-measure in `layout/bandgap_top/AREA.md` after #204.
- **Silicon.** `measurements/` is empty and no tapeout is scheduled. Question: is T1 complete on the regenerated
  layout?

## Blocked and waiting

- **#239** (`loom:operator`, `loom:blocked`): final execution and signoff wait on the independent `par_r` risk
  disposition and on the diagnostic/reference reruns. Everything from #211 down the DR-0007 chain waits on it.
- **Diagnostic-bench fleet reruns**: the plan exists (`sim/diagnostic-bench-fleet-plan.md`, #362), but adapter
  implementation and the runs need a separate authorization per the 2026-10-19 ruling on #239.
- **#353**: removing `layout/netlist/verify_mim_routing.py` is parked; the coverage audit found no replacement
  for its negative checks, and the choice between a GDS-fixture test and keeping it on demand is the operator's.
- **PR #313**: held by operator triage (2026-10-15) until #204 lands; it also conflicts with `main`.
- **PR #198** (Renovate config): open since 2026-09-21 with no review label.
- **#214**: no Python interpreter in the auditor runtime; a host capability request, not repository work.

With PR #387 in review and PR #313 held, the tracker has **no Builder-ready issue today**. The three seeds under
Now are the dispatchable work.

## Not planned

- Relaxing a ratified limit to make a result pass (`CLAUDE.md`; spec changes go through a decision record).
- Local multi-point simulation grids on shared workers (refused by the harness since PR #429) and evidence
  minted by CI.
- Editing or deleting existing evidence records; `sim/` and `signoff/reports/` are append-only.
- Long-term drift: not specified for this block (README spec table).
