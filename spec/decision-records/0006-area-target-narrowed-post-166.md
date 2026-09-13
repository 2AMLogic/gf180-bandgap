# 0006: Area target narrowed post-#166 (ratification-via-PR)

- **Status**: proposed — submitted for EE-key/market-key review via PR #177
- **Date**: 2026-08-21
- **Decided by**: Builder (issue #156), submitted via the ratification-via-PR
  path (operator redirect, 2026-08-21) — pending EE-key + market-key review,
  per `2AMLogic/2am` `FLEET.md` §Compute (ruled 2026-08-19 in
  `2AMLogic/2am#357`, amended 2026-08-20 by epic `2AMLogic/2am#372`)

> This record proposes changing a **ratified spec value** (`README.md`
> "Target specification", Area row, ratified by
> [DR-0003](0003-target-spec-ratification.md)) and supersedes
> [DR-0005](0005-area-target-overrun.md)'s own still-`proposed` interim
> ceiling. Per the standing ratification-via-PR policy, this proposal's
> diff (this same PR: `README.md`'s Area row and
> `layout/bandgap_top/area_report.py`'s `RATIFIED_TARGET_UM2`) is the
> proposal itself — it takes effect only once the two-key review (a
> non-author EE key plus a non-author market key) approves and the PR
> merges, or an operator rules on it directly. The author of this record
> and this PR is **not** eligible to hold either key on it.

## Context

[DR-0005](0005-area-target-overrun.md) proposed an interim Area ceiling of
`< 0.085 mm²` (85,000 µm²) against a **measured 80,813.72 µm²** drawn GDS
area (issue #156, PR #162, 2026-08-16) — a body-area-driven 61.6 % overrun
of the originally-ratified `< 0.05 mm²` (50,000 µm²) target
([DR-0003](0003-target-spec-ratification.md)). That record was filed
`Status: proposed`, explicitly `pending operator ratification`, and named a
multi-level-metal routing rewrite (filed separately as
[#160](https://github.com/2AMLogic/gf180-bandgap/issues/160)) as the
mechanism that could recover area over time and justify narrowing the
ceiling later, "once the rework is implemented and measured" — DR-0005's own
Consequences section and the routing study
(`layout/routing/multi-metal-routing-study.md` §7) both said this
explicitly, in advance.

**That rework has since landed and been measured.** Issue #166 implemented
the Metal2/Metal3 over-the-cell re-route the study (#160, PR #165) designed
and costed, replacing `generate.py`'s Metal1/Poly2-only corridor-and-rail
scheme. Re-running the unedited tooling against the current, committed,
DRC-clean/LVS-matching `bandgap_top.gds` (verified in this record's own
worktree, `uv run --with klayout python3 layout/bandgap_top/area_report.py`,
reproducing exactly what's already committed at `layout/bandgap_top/AREA.md`
Finding 6 and `layout/README.md`'s "Expected results" table):

```
Drawn device body area, by group (from the current netlist):
  amp              11242.40 um^2
  core              5688.11 um^2
  startup           8048.00 um^2
  trim ladder        349.27 um^2
  TOTAL            25327.78 um^2

floorplan.md §8 estimate      :   10425.45 um^2
  -> current netlist is               2.43x that estimate

drawn GDS bounding box        : 222.10 x 281.43 um
drawn GDS area                :   62505.60 um^2 (0.06251 mm^2)
ratified target               :   50000.00 um^2 (0.05000 mm^2)
  -> FAIL: 12505.60 um^2 (25.0%) OVER budget
  -> layout overhead multiplier : 2.47x body area
```

The measured area **dropped from 80,813.72 µm² to 62,505.60 µm²** (a
22.7 % recovery, beating the routing study's own 65,896.39 µm² / 2.60×
estimate by 5.1 % — the two conservatisms the study declared, a 1.0 µm/row
landing band and a 0.20 µm left margin, both realised at zero; see
`layout/bandgap_top/AREA.md` Finding 6 for the full estimate-vs-measurement
accounting). The block is still `FAIL` against the original 50,000 µm²
target (25.0 % over, down from 61.6 %) because the remainder is row-stripe
floorplan whitespace, not routing — the rows fill only 55.6 % of the
full-width stripe box they sit in, and closing the gap needs a separate 2-D
floorplan re-pack to ≥69.8 % row packing (`routing_budget.py`; filed as its
own follow-up per DR-0005/§166's own scoping, not attempted here).

**DR-0005's own 85,000 µm² proposal is now stale evidence, not a live
number to ratify.** Both the routing study (§7) and `AREA.md` (Finding 6)
already named the correct next step in advance: *"a realised 62,505.60 µm²
would justify narrowing the interim ceiling (to ≈0.066 mm² on DR-0005's own
~5 % margin convention) ... per `spec/decision-records/TEMPLATE.md` that is
a successor record, not an edit to DR-0005."* This record is that successor,
filed now because issue #156's disposition changed today (2026-08-21,
operator re-route to the ratification-via-PR path) from
"escalated, pending operator ratification" (parked) to ordinary dispatchable
work — see the issue's own comment thread for the full policy citation.

## Decision

**Propose narrowing the interim Area ceiling from DR-0005's `< 0.085 mm²`
to `< 0.066 mm²` (66,000 µm²)** — 3,494.40 µm² (5.3 %) of headroom over the
current measured 62,505.60 µm², matching the ~5 % margin convention both
DR-0005 and the routing study already used, and rounded to the same
two-significant-figure convention DR-0005 itself used (`0.085`, not
`0.0852`). This is the value both `layout/routing/multi-metal-routing-study.md`
§7 and `layout/bandgap_top/AREA.md` Finding 6 already anticipated in
advance of this record.

Per the ratification-via-PR mechanism, the diff in this same PR carries the
proposal directly:

- `README.md`'s Target specification table's Area row: `< 0.05 mm²` →
  `< 0.066 mm²`.
- `layout/bandgap_top/area_report.py`'s `RATIFIED_TARGET_UM2` constant:
  `50000.0` → `66000.0`.
- [DR-0005](0005-area-target-overrun.md)'s `Status` becomes
  `superseded by 0006` (its `85,000 µm²` proposal is withdrawn in favor of
  this record's `66,000 µm²`; DR-0005's own body and analysis are left
  intact as the historical record of the pre-#166 state, per
  `spec/decision-records/TEMPLATE.md`'s "do not delete or rewrite ... a
  ratified record" convention, applied here to a proposed-but-superseded
  one for the same reason: it is the paper trail).

**Relax-after-measured-FAIL disclosure.** Relative to the *originally
ratified* `< 0.05 mm²` (DR-0003), this is still a relaxation of a spec value
after a measured `FAIL` — the block is 25.0 % over that original target even
after #166's recovery. This record does not attempt to characterize this
proposal's competitiveness against named public bandgap-reference-IP die
areas — that sourcing is the market key's job per the standing policy, not
the author's; this Context section states the measured facts and lets the
market key evaluate them against public parts. (Relative to DR-0005's own
still-`proposed`, never-ratified `0.085 mm²`, this is a *tightening*, not a
further relaxation — but DR-0005 was never ratified, so the operative
comparison for the relax-after-FAIL gate is against DR-0003's ratified
`0.05 mm²`, not against DR-0005's unratified proposal.)

## Alternatives considered

- **Ratify DR-0005's `0.085 mm²` as originally proposed, unchanged.**
  Rejected — it was explicitly sized against the *pre-#166* measurement
  (80,813.72 µm²) and #166 has since recovered 22.7 % of that area. Ratifying
  a number the evidence has already outgrown would be "inventing slack the
  evidence does not currently call for," the same reasoning DR-0005 itself
  used to reject a round `0.1 mm²` target.
- **Edit DR-0005 in place to the new number.** Rejected — both DR-0005's own
  Consequences section and the routing study's §7 explicitly pre-committed
  to the successor-record path for exactly this situation ("supersede this
  record rather than editing it, per `spec/decision-records/TEMPLATE.md`'s
  rule"), and `TEMPLATE.md` itself directs the same. Editing it now would
  discard that paper trail and the record of what was actually proposed and
  why, at the time it was proposed.
- **Hold at `0.05 mm²` (revert to the original ratified target, propose no
  interim ceiling at all).** Rejected for the same reason DR-0005 rejected
  it: reaching `≤ 1.97×` overhead needs both the routing re-route (now done,
  landing at 2.47×) *and* a 2-D floorplan re-pack to ≥69.8 % row packing
  (not yet attempted, filed as its own follow-up). Proposing `0.05 mm²` now
  would misstate the current, measured state as a `PASS` it is not.
- **Propose a target wider than `0.066 mm²` for extra headroom against
  future device growth.** Rejected on the same basis DR-0005 used against
  `0.1 mm²`: `design/bandgap_error_budget.md` §5 shows every ratified
  electrical row currently passes, so there is no known pending growth to
  pad against; and keeping the same ~5 % margin convention DR-0005 and the
  routing study both already used keeps this record's number traceable to
  precedent rather than picked freehand.

## Consequences

- If this PR's diff is approved (two-key ratification-via-PR, or direct
  operator ruling): `README.md`'s Area row reads `< 0.066 mm²`,
  `area_report.py`'s `RATIFIED_TARGET_UM2` is `66000.0`, and re-running
  `area_report.py` against the currently-committed `bandgap_top.gds`
  reports **PASS, 5.3 % headroom** (62,505.60 µm² vs. 66,000 µm²) — verified
  in this record's own worktree before filing (Context, above).
- [#160](https://github.com/2AMLogic/gf180-bandgap/issues/160)'s own
  Consequences already named the 2-D floorplan re-pack (study §6/§8, row
  packing 0.556 → ≥0.733) as the remaining mechanism to close the gap all
  the way back to the *original* `0.05 mm²` target; that follow-up is
  unaffected by this record and remains filed separately (not yet filed as
  its own numbered issue as of this record — a future record or issue can
  do so on the strength of `AREA.md` Finding 6 / study §6).
- If a future device resize or floorplan change moves the measured area
  again, this record's `0.066 mm²` can go stale the same way DR-0005's
  `0.085 mm²` and the original `0.05 mm²` both did — re-run `area_report.py`
  and, if it overruns again (or a further recovery justifies narrowing
  again), supersede this record rather than editing it, per
  `spec/decision-records/TEMPLATE.md`.
- `layout/bandgap_top/AREA.md`'s Headline table and
  `layout/README.md`'s "Expected results" table are updated in this same PR
  to carry the post-#166, post-this-proposal verdict, so the tooling's own
  documented expected output stays truthful once this PR's diff is live.
