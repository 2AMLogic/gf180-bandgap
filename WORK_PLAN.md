# Work Plan

This roadmap is generated from the current GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run
- **#386**: Prepare the revised par_r resistor-mismatch model-risk assessment and validation plan (part of #239)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#386**: Prepare the revised par_r resistor-mismatch model-risk assessment and validation plan (part of #239)

## In Progress

Issues currently being built (`loom:building`).

- **#450**: Remove the never-read is_mos attribute from the five layout plan item classes
- **#453**: Remove dead fleet_common.corner_key and the duplicate klt_version() in the fleet request builders
- **#454**: Read Netlist provenance through one function: postlayout_delta's copy rejects fleet-ingested records

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#387**: docs: propose DR-0008 par_r model-risk successor and validation plan
- **#455**: refactor(layout): drop the never-read is_mos flag from plan item classes
- **#456**: refactor(sim/tools): drop dead fleet_common.corner_key, single-source klt_version()

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#87**: Layout's 4x unit-PNP array for core.Q2 gives an effective dVBE ratio of 4.03, not the schematic's 3.63 — floorplan 4.1 asserts the opposite *(curated)*
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence *(curated)*
- **#239**: DR-0007: execute final-DUT fleet suite and mismatch evidence run *(curated)*
- **#308**: ci: fail when committed bandgap_top.gds differs from generate.py output *(curated)*
- **#358**: T1 item 11: declare ERC well/substrate ties now that klayout-tools#2169 is fixed, then cite item 11 *(curated)*
- **#386**: Prepare the revised par_r resistor-mismatch model-risk assessment and validation plan (part of #239) *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

- **#94**: Track the gap to T1 sim-validated (klayout-tools design-evidence tiers)
- **#202**: Q2 array (DR-0007): corner-covered PVT re-run, R1 re-null, extracted re-run on pinned klt
- **#203**: DR-0007 phase A: measure array ratio and finalize schematic PVT evidence

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 3 |
| Approved PRs awaiting merge | 0 |
| Curated | 6 |
| Architect / Hermit proposals | 0 |
| Active epics | 3 |
<!-- guide:plan-body:end -->
