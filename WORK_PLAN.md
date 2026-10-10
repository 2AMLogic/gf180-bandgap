# Work Plan

This roadmap is generated from the current GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

- **#244**: docs: remove stale hard-coded harness unit-test count

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#281**: docs: document guard-compatible evidence copies and assignment-chain reproduction
- **#288**: sim: classify reduced corner-set suite runs as diagnostic subsets
- **#291**: sim: validate Monte Carlo process and mismatch seed components
- **#294**: sim: reject duplicate waveform columns before deriving verdicts
- **#298**: sim: validate standalone TC outer temperature before corner aggregation

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#299**: sim: validate standalone TC outer corner identity (#298)

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#244**: docs: remove stale hard-coded harness unit-test count

## Proposed

Issues carrying `loom:curated`.

- **#87**: Layout's 4x unit-PNP array for core.Q2 gives an effective dVBE ratio of 4.03, not the schematic's 3.63 — floorplan 4.1 asserts the opposite *(curated)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence *(curated)*
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run *(curated)*
- **#243**: docs: remove stale hard-coded harness unit-test count (40 vs 256) *(curated)*
- **#281**: docs: document guard-compatible evidence copies and assignment-chain reproduction *(curated)*

## Proposed (Architect / Hermit)

- **#219**: sim harness: share the batch-backend guard and cap default local --jobs *(architect)*

## Epics

- **#94**: Track the gap to T1 sim-validated (klayout-tools design-evidence tiers)
- **#202**: Q2 array (DR-0007): corner-covered PVT re-run, R1 re-null, extracted re-run on pinned klt
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Operator priority | 0 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 1 |
| Curated | 5 |
| Architect / Hermit proposals | 1 |
| Active epics | 3 |
<!-- guide:plan-body:end -->
