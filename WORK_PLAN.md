# Work Plan

This roadmap is generated from the current GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

_None._

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#234**: spec: prepare evidence and ranked operator questions for the three TBD rows
- **#235**: docs: trim README Status paragraph to durable facts; point at signoff/ and WORK_PLAN.md for live state

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#87**: Layout's 4x unit-PNP array for core.Q2 gives an effective dVBE ratio of 4.03, not the schematic's 3.63 — floorplan 4.1 asserts the opposite *(curated)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence *(curated)*
- **#234**: spec: prepare evidence and ranked operator questions for the three TBD rows *(curated)*
- **#235**: docs: trim README Status paragraph to durable facts; point at signoff/ and WORK_PLAN.md for live state *(curated)*

## Proposed (Architect / Hermit)

- **#219**: sim harness: share the batch-backend guard and cap default local --jobs *(architect)*

## Epics

- **#94**: Track the gap to T1 sim-validated (klayout-tools design-evidence tiers)
- **#202**: Q2 array (DR-0007): corner-covered PVT re-run, R1 re-null, extracted re-run on pinned klt
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Operator priority | 0 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 4 |
| Architect / Hermit proposals | 1 |
| Active epics | 3 |
<!-- guide:plan-body:end -->
