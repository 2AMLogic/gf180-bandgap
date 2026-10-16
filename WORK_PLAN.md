# Work Plan

This roadmap is generated from the current GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#340**: fix(signoff): default re-grade uses the repo klt pin via uvx

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#308**: ci: fail when committed bandgap_top.gds differs from generate.py output

## In Progress

Issues currently being built (`loom:building`).

- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#340**: fix(signoff): default re-grade uses the repo klt pin via uvx

## Proposed

Issues carrying `loom:curated`.

- **#87**: Layout's 4x unit-PNP array for core.Q2 gives an effective dVBE ratio of 4.03, not the schematic's 3.63 — floorplan 4.1 asserts the opposite *(curated)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence *(curated)*
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run *(curated)*
- **#308**: ci: fail when committed bandgap_top.gds differs from generate.py output *(curated)*
- **#326**: layout/bandgap_top: routing-budget S1 area disagrees with committed GDS bbox (klayout-gated test fails on main) *(curated)*

## Proposed (Architect / Hermit)

- **#219**: sim harness: share the batch-backend guard and cap default local --jobs *(architect)*
- **#306**: ci: run klayout/klt-gated layout tests in the signoff job and fail on skips *(architect)*

## Epics

- **#94**: Track the gap to T1 sim-validated (klayout-tools design-evidence tiers)
- **#202**: Q2 array (DR-0007): corner-covered PVT re-run, R1 re-null, extracted re-run on pinned klt
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 5 |
| Architect / Hermit proposals | 2 |
| Active epics | 3 |
<!-- guide:plan-body:end -->
