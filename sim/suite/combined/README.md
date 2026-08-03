# sim/suite/combined — the two-legged untrimmed-accuracy verdict

```bash
python3 sim/run_combined_accuracy.py            # newest record of each leg
python3 sim/run_combined_accuracy.py --no-write # print, write nothing
python3 sim/run_combined_accuracy.py \
    --mc-record <id> --corner-record <id>       # pin a specific pair
```

README.md's ratified Output-reference row — "1.20 V ±2% untrimmed (3σ,
mismatch MC N≥300 **+** process corners, −40…125 °C)" — has a **two-legged**
basis, so neither `sim/output-voltage-tc/` (no device mismatch) nor
`sim/mc-untrimmed/` (tt/3.30 V only) is on its own the row's verdict. Each
file here is one joint verdict over both legs: one pass/fail per corner of
the 81-point matrix, rolled up per temperature, citing both source records by
path. The rule, the separability approximation it carries, the anchor
cross-check that guards it and the `par_r` sensitivity band are documented in
[`../README.md`](../README.md) and implemented in
[`../combined.py`](../combined.py).

These reports **simulate nothing** — they are a roll-up of records that
already exist, so they need neither ngspice nor the PDK. They are still
append-only like the rest of `sim/`: a re-run mints a new
`<YYYYmmdd>-<HHMMSS>-<short-sha>.md` beside the existing ones and never edits
one. Each report's own header states which two records it read, so two
reports minted from the same commit are told apart by their **Legs combined**
table, not by their filename.

## Reports so far

| Report | Legs read | Verdict |
|---|---|---|
| `20260803-023422-40990fd.md` | newest of each leg: corners `20260802-064729-75ca562`, MC `20260802-034414-5066d85` | FAIL — 66/81 corners |
| `20260803-023457-ae39de2.md` | pinned pair, both from commit `960f726`: corners `20260801-234837-960f726`, MC `20260801-232002-960f726` | FAIL — 66/81 corners |
| `20260803-024856-b4a0e6a.md` | same legs as `…-40990fd` — supersedes it (corrected methodology text) | FAIL — 66/81 corners |
| `20260803-024953-3e50aad.md` | same legs as `…-ae39de2` — supersedes it (corrected methodology text) | FAIL — 66/81 corners |

The first two reports are superseded, not withdrawn: their **Methodology**
section stated the graft offset as `mean(mm_all, T) − vref(mm_ctrl, T)`, which
is not what the tool computes — `delta` is anchored on the corner leg's own
`tt`/3.30 V point and `mm_ctrl` feeds only the anchor cross-check. Every
number in those two reports was always computed from the real rule and is
unchanged in the reports that supersede them; only the prose was wrong. They
stay here because this directory is append-only.

The pinned pair (`…-ae39de2`, superseded by `…-3e50aad`) is pinned
deliberately: that MC record is the newest one whose committed logs carry **all four** Monte Carlo groups, so it is the one
that can evaluate the two checks the newest record cannot — the anchor
cross-check (`mm_ctrl` vs the corner leg's `tt`/3.30 V point: agreement
within 0.5 µV at every temperature, against a 100 µV tolerance) and the
`par_r` sensitivity band (`mm_res`; ×0.5/×2 on the coefficient moves the 3σ
half-width by at most +1.34 mV and changes no corner's verdict). It is the
evidence behind
[`spec/decision-records/0004-par-r-mismatch-coefficient-risk.md`](../../../spec/decision-records/0004-par-r-mismatch-coefficient-risk.md).

## Re-running after a design change

Both legs default to the newest record under their own `records/` directory,
so once either bench is re-run — after the centre re-centring / TC work, or
against a post-layout extracted DUT — a bare
`python3 sim/run_combined_accuracy.py` judges the new evidence with no
argument changes. Nothing in this directory is edited to reflect the new
result; the new report supersedes the old one by being newer, and the old one
stays as the record of what was true before.
