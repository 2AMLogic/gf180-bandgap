# spec — ratified spec + decision records

The ratified target spec table lives in the top-level
[`README.md`](../README.md#target-specification-ratified-2026-07-31-see-issue-1-and-35).
This directory holds the **decision records** that justify each ratified
value and any future change to it: per CLAUDE.md, spec changes go through a
decision record here — agents do not relax the ratified spec to make results
pass.

```
spec/
  README.md               this file
  decision-records/
    TEMPLATE.md            copy this to start a new record
    NNNN-<slug>.md          one decision per record, numbered sequentially
```

## Decision records

One page per decision: the context that forced it, the decision itself
(stated as a concrete spec change), alternatives considered, and
consequences. See [`decision-records/TEMPLATE.md`](decision-records/TEMPLATE.md)
for the format and the numbering rule (next unused `NNNN`, checked against
every filename in this directory on `main`, including superseded records).

| Record | Title | Status |
|---|---|---|
| [0001](decision-records/0001-bandgap-topology-selection.md) | Bandgap topology selection for gf180mcu 3.3V | Ratified |
| [0002](decision-records/0002-supply-voltage-scope.md) | Supply voltage scope — 3.3V-only for wave 1 | Ratified |
| [0003](decision-records/0003-target-spec-ratification.md) | Target spec ratification (conditional on #35 amendments) | Ratified |
| [0004](decision-records/0004-par-r-mismatch-coefficient-risk.md) | `par_r` resistor-mismatch coefficient accepted as a documented risk | Proposed |

A record is never deleted or rewritten once ratified — a later change
supersedes it with a new record rather than editing history in place (same
append-only convention as `sim/`, see [`sim/README.md`](../sim/README.md)).
