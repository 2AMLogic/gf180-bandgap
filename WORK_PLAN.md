# Work Plan

This roadmap is generated from the current GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
_Generated: 2026-11-26T01:00:34Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence
- **#204**: DR-0007 phase B: regenerate layout and record pinned extracted verification *(held)*
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run *(held)*

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

_None._

## Proposed

Issues carrying `loom:curated`.

- **#87**: Layout's 4x unit-PNP array for core.Q2 gives an effective dVBE ratio of 4.03, not the schematic's 3.63 — floorplan 4.1 asserts the opposite *(curated)* *(held)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence *(curated)*
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run *(curated)* *(held)*
- **#308**: ci: fail when committed bandgap_top.gds differs from generate.py output *(curated)* *(held)*
- **#358**: T1 item 11: declare ERC well/substrate ties now that klayout-tools#2169 is fixed, then cite item 11 *(curated)* *(held)*

## Proposed (Architect / Hermit)

- **#540**: Draw bandgap device rows once and reuse their terminal positions *(hermit)*
- **#564**: Remove the default PNP emitter area from extracted DUT generation *(hermit)*

## Epics

- **#94**: Track the gap to T1 sim-validated (klayout-tools design-evidence tiers) *(held)*
- **#202**: Q2 array (DR-0007): corner-covered PVT re-run, R1 re-null, extracted re-run on pinned klt *(held)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 5 |
| Architect / Hermit proposals | 2 |
| Active epics | 3 |
<!-- guide:plan-body:end -->
