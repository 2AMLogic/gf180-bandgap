# 0002: Supply voltage scope — 3.3V-only for wave 1

- **Status**: proposed (input to spec ratification, see #1)
- **Date**: 2026-07-29

## Context

The bandgap block's target specification (`README.md`, "Target specification"
table) lists `Supply` as `3.3 V ±10%` under the **Target** column, with
`also 5 V flavor` listed only under the **Stretch** column. `CLAUDE.md`
separately states the working default: "PDK: gf180mcu (open PDK), 3.3V
flavor primary." Neither of these constitutes a recorded decision — the 5V
stretch goal has been sitting undecided, which risks scope drifting into
dual-flavor territory (in device selection, testbenches, or layout) without
anyone having deliberately chosen that tradeoff.

This block is the first canary (wave 1, block 1) for a brand-new IP catalog.
Per `CLAUDE.md`, "verification is the product" — every recorded result must
carry PVT corners (−40/27/125 °C, ±10% supply, process corners), and no claim
ships without a testbench. The supply-voltage scope directly determines the
shape of that verification work (device Vgs/Vds qualification, supply-sweep
testbench ranges, layout spacing/well rules), so it needs to be fixed before
device selection and testbench work begin in earnest.

## Decision

**3.3V-only for wave 1.** This block targets the gf180mcu 3.3V device
flavor exclusively, with supply range 3.3 V ±10% as already stated as the
Target (not Stretch) value in `README.md`. No 5V-flavor work is undertaken
in wave 1.

This does not relax or contradict the existing DRAFT spec table — it
promotes the already-implicit choice (3.3V primary, per `CLAUDE.md`; 3.3V as
Target vs. 5V as Stretch, per `README.md`) to an explicit, recorded decision,
so it can be treated as settled scope during spec ratification (#1) rather
than re-litigated implicitly through drift.

## Alternatives considered

1. **Dual 3.3V/5V flavor from wave 1.** Rejected. See Consequences below —
   this roughly doubles the device, testbench, and layout scope of the first
   block, which works against the goal of fastest time to measured silicon
   for the very first shuttle run in a new catalog.
2. **5V-only.** Rejected. `README.md`'s stretch goal frames dual/5V support
   as *additive* to the 3.3V target ("also 5 V flavor"), not as a
   replacement for it — 3.3V is explicitly the primary target, not merely
   one of two equally-weighted options. Dropping 3.3V entirely would
   contradict the existing spec framing rather than clarify it.
3. **3.3V-only for wave 1, 5V deferred to a later wave (this decision).**
   Accepted. Matches both the existing README Target/Stretch framing and
   CLAUDE.md's stated primary flavor; keeps wave 1 scope minimal without
   discarding the 5V stretch goal — it remains available as a future,
   separately-scoped decision.

## Consequences

**In scope now:**
- Supply range for this block is 3.3 V ±10% only — no 5V supply-range
  testbenches.
- A single set of PVT-corner testbenches/sweeps at 3.3 V ±10% (per
  `CLAUDE.md`'s −40/27/125 °C × supply × process corner matrix) is
  sufficient; no separate 5V corner matrix is required for wave 1.
- Device selection uses only the gf180mcu 3.3V device flavor (single set of
  Vgs/Vds ratings and models to qualify against).
- Layout work targets only 3.3V-flavor spacing/well rules — no dual-flavor
  well-spacing or DRC scope expansion for this block.

**Explicitly deferred (not decided here):**
- A future dual 3.3V/5V-flavor variant of this block remains a possible
  stretch goal, as already noted in `README.md`. If pursued, it would be
  scoped as its own separate issue and decision record — this record does
  not commit to it, schedule it, or imply timing for it.
- This record does not itself ratify the target spec (#1 remains open and
  is the authoritative ratification step); it is meant to be referenced
  from that ratification as the settled rationale for the Supply row.

**What is avoided by deciding now:** without this record, device selection,
testbench range, and layout work could each independently and implicitly
assume different supply scope, causing inconsistent or wasted work across
the block. Fixing 3.3V-only now removes that ambiguity before implementation
work begins.
