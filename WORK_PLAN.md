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

_None._

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#244**: docs: remove stale hard-coded harness unit-test count

## Proposed

Issues carrying `loom:curated`.

- **#87**: Layout's 4x unit-PNP array for core.Q2 gives an effective dVBE ratio of 4.03, not the schematic's 3.63 — floorplan 4.1 asserts the opposite *(curated)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence *(curated)*
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run *(curated)*
- **#243**: docs: remove stale hard-coded harness unit-test count (40 vs 256) *(curated)*

## Proposed (Architect / Hermit)

- **#219**: sim harness: share the batch-backend guard and cap default local --jobs *(architect)*
- **#282**: sim: verify frozen request JSON hashes during fleet ingestion *(architect)*
- **#283**: sim: validate fleet corner execution status and error diagnostics *(architect)*
- **#284**: sim: prevent rejected fleet provenance from becoming suite-valid logs *(architect)*

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
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 4 |
| Architect / Hermit proposals | 4 |
| Active epics | 3 |
<!-- guide:plan-body:end -->
