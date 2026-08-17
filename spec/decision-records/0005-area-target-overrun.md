# 0005: Area target overrun — escalated, revision proposed pending ratification

- **Status**: proposed
- **Date**: 2026-08-16
- **Decided by**: Builder (issue #156), pending operator ratification

> This record proposes changing a **ratified spec value** (`README.md`
> "Target specification", Area row, ratified by
> [DR-0003](0003-target-spec-ratification.md)). Per CLAUDE.md and DR-0003's
> own precedent (operator sign-off), this proposal does **not** take effect,
> and `README.md`'s Area row is left unedited, until an operator ratifies
> it — filing this record does not itself close issue #156.

## Context

`layout/bandgap_top/bandgap_top.gds` — the block's only committed physical
layout — was last regenerated at `ba091ea` (#105, 2026-08-03), before three
device-sizing issues landed against `design/netlist/bandgap_top.spice`
(`design/bandgap_error_budget.md` §5 tracks each): `#96` (TC/output-reference
corner closure, re-nulling `core.R1`), `#147` (combined untrimmed-accuracy
verdict — the amp input pair resized to 300 µm/6 µm, `core.M1`–`M4`/
`MC1`–`MC4` resized to 85 µm/8.5 µm), and `#151` (amp `M3`/`M4` mirror-load
resize to 33 µm/26.4 µm for loop-stability margin). The committed GDS
therefore reports a stale
area verdict: `layout/bandgap_top/area_report.py` against it shows **PASS,
2.4 % headroom** (48,805.68 µm² vs. the ratified 50,000 µm² / 0.05 mm²
target from DR-0003).

Regenerating the GDS from the current netlist (`generate.py`, unchanged —
no routing/floorplan code in this repo moved) instead measures:

```
Drawn device body area, by group (from the current netlist):
  amp              11242.40 um^2
  core              5688.11 um^2
  startup           8048.00 um^2
  trim ladder        349.27 um^2
  TOTAL            25327.78 um^2

floorplan.md §8 estimate      :   10425.45 um^2
  -> current netlist is               2.43x that estimate

drawn GDS bounding box        : 239.20 x 337.85 um
drawn GDS area                :   80813.72 um^2 (0.08081 mm^2)
ratified target               :   50000.00 um^2 (0.05000 mm^2)
  -> FAIL: 30813.72 um^2 (61.6%) OVER budget
  -> layout overhead multiplier : 3.19x body area
```

**The overrun is a body-area problem, not a routing-efficiency problem.**
`layout/floorplan.md` §8 assumed "even a generous 4× overhead multiplier ...
would land at ≈0.042 mm², still inside budget" against its own
schematic-derived floor of 10,425.45 µm². Two things are true at once:

1. The realised single-metal (Metal1 + Poly2) routing overhead — **3.19×**
   drawn area over drawn device body area — is *better* than the 4× §8
   called "generous," so the routing discipline `generate.py`'s own
   docstring documents (a Metal1/Poly2-only corridor-and-rail scheme, kept
   for extraction-deck coverage reasons that predate klayout-tools#220) is
   not, by itself, an outlier inefficiency.
2. The body area it multiplies has grown to **2.43×** §8's original
   estimate, driven by real, already-ratified accuracy/stability work: per
   `design/bandgap_error_budget.md` §5c/§5d, `#147`'s input-pair resize and
   `#151`'s mirror-load resize (33 µm/26.4 µm, 2.72× area, adopted to clear
   an amplifier loop-stability phase-margin cliff with real headroom) were
   both required to close the combined untrimmed-accuracy verdict — as of
   `#151` that verdict passes 81/81 PVT corners with **+2.194 mV** worst-case
   margin (up from #147's own thin +0.836 mV). Reversing either resize to
   claw back area would reopen a closed, ratified electrical verdict; that
   is out of scope for a layout/area issue and not proposed here.

**Whether routing/floorplan changes can plausibly close the gap instead of
revising the target**: closing a 61.6 % overrun through routing alone would
require cutting the realised overhead multiplier from 3.19× to ≤1.97×
(50,000 / 25,327.78) — a **larger** cut than the gap between the achieved
3.19× and the floorplan's own "generous" 4×. `generate.py`'s docstring notes
the `klt` gf180mcu extraction deck has gained the full Metal1–Metal5/via
stack since this layout's single-metal routing discipline was adopted
(klayout-tools#220), so a real multi-level-metal re-route — rails on
Metal2/Metal3 running over the device field instead of one Metal1 rail per
net stacked vertically per row, and no dedicated Poly2 corridor — is a
plausible way to recover area over time. It is **not**, however, a
parameter tweak: it is a rewrite of this block's routing algorithm (the
per-row rail/spine architecture in `generate.py`'s `build()`), touching
every drawn net, and would need its own DRC/LVS-clean re-verification from
scratch. That is out of proportion for this issue to attempt speculatively
and is filed instead as its own follow-up,
[#160](https://github.com/2AMLogic/gf180-bandgap/issues/160) (see
Consequences), rather than attempted here under an area-budget issue's
scope.

## Decision

**Propose revising the ratified Area row from `< 0.05 mm²` to `< 0.085 mm²`
(85,000 µm²)** — ≈5.2 % headroom over the current measured 80,813.72 µm²,
matching the spirit of the original target's own 2.4 % margin — **pending
operator ratification**, per the same process DR-0003 itself went through
(operator sign-off recorded on the originating issue). Until ratified:

- `README.md`'s Area row stays `< 0.05 mm²` (unedited by this record).
- `layout/bandgap_top/area_report.py` continues to report the current
  measurement as a `FAIL` against that unedited ratified number — this
  record does not silently make the tool pass.
- Issue #156 stays open (or is left in an explicitly "escalated, pending
  ratification" state if closed administratively), consistent with its own
  acceptance criteria: filing this record alone does not resolve it.

## Alternatives considered

- **Ratify no change; treat the overrun as an open, unresolved gap
  indefinitely.** Rejected as a permanent state — an area row nothing can
  ever satisfy without either reversing ratified electrical work or
  committing to a routing rewrite is not a useful spec line; but this
  alternative is functionally what happens *by default* unless and until an
  operator ratifies a different number, so it is the fallback if this
  proposal is rejected outright.
- **Reverse `#147`/`#151`'s device resizes to reclaim area.** Rejected —
  both resizes closed a previously-failing, ratified electrical verdict
  (combined untrimmed accuracy, loop-stability phase margin) with measured,
  recorded evidence; unwinding them would reopen those failures to satisfy
  a physical-implementation row, which is backwards per CLAUDE.md's "no
  claim without a testbench" (it would replace a measured PASS with an
  unmeasured area saving).
- **Attempt the multi-metal routing rewrite within this issue before
  proposing any target revision.** Rejected for *this* issue's scope —
  evaluated above: it needs to beat the floorplan's own "generous" 4×
  assumption by more than the achieved 3.19× already does, is a rewrite of
  `generate.py`'s routing architecture (not a parameter change), and would
  need a full fresh DRC/LVS-clean re-verification. Filed instead as a
  separate, explicitly-scoped follow-up issue so it can be attempted (and
  reviewed) on its own terms rather than folded into a spec-escalation
  issue's diff.
- **Propose a larger target (e.g., a round `0.1 mm²`) for more headroom
  against future device growth.** Rejected — `design/bandgap_error_budget.md`
  §5's own accounting shows every ratified electrical row this document is
  responsible for now passes as of `#151` (Section 5's "as of #61, every
  ratified row ... passes," updated through `#96`/`#147`/`#151`), so no
  further device-sizing growth is currently expected from open work.
  Padding the target further than the original's own margin convention
  would be inventing slack the evidence does not currently call for.

## Consequences

- If ratified: `README.md`'s Target specification table's Area row becomes
  `< 0.085 mm²`, and `layout/bandgap_top/area_report.py`'s
  `RATIFIED_TARGET_UM2` constant is updated to match in the same PR that
  records ratification —
  neither is changed by this record alone.
- [#160](https://github.com/2AMLogic/gf180-bandgap/issues/160) is filed
  proposing the multi-level-metal routing rewrite of `generate.py` as an
  architecture-level effort that could bring the realised area back under
  the *original* 0.05 mm² target over time; this record's proposed
  0.085 mm² is treated as an interim ceiling, not a
  claim that 0.05 mm² is permanently unreachable.
- If a future device resize grows body area further, this record's proposed
  0.085 mm² can go stale the same way the original 0.05 mm² did — any such
  growth should re-run `area_report.py` against the (by-then-ratified or
  still-proposed) number and, if it overruns again, supersede this record
  rather than editing it, per `spec/decision-records/TEMPLATE.md`'s rule.
- `layout/floorplan.md` §8/§11.1 are updated (same PR) to carry this
  measured verdict instead of the "once real layout exists, this is future
  work" framing they carried before — see those sections for the full
  reconciliation against §8's schematic-derived floor.
