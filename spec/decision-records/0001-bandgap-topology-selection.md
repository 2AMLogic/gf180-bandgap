# DR-0001: Bandgap topology selection for gf180mcu 3.3V

- **Status**: Proposed (recommended by survey below; pending engineering
  ratification, same governance path as the target spec — see #1)
- **Date**: 2026-07-29
- **Author**: Builder agent, issue #3
- **Related**: #1 (spec ratification), #4 (device characterization, feeds
  final component sizing), #6 (decision-record template — this record
  predates that template landing; reconcile format if #6 defines a
  different convention), #7 (3.3V-only vs. dual-flavor scope decision)

## Context

This project's first canary block is a bandgap voltage reference on
gf180mcu, 3.3V flavor primary (see README target spec: 1.20 V ±1%
untrimmed, TC < 50 ppm/°C, PSRR > 60 dB DC, Iq < 50 µA, area < 0.05 mm²,
self-starting < 1 ms). Before design work locks to a schematic, we need a
topology decision informed by prior art, because the topology choice
drives device sizing, startup-circuit design, trim strategy, and the
device characterization work in #4.

The central question specific to this project: gf180mcu 3.3V gives
generous headroom compared to the sub-1V constraints that motivate a
family of "low-voltage" bandgap architectures. Do we still want the
extra complexity those architectures bring, or does the classic
approach dominate here?

## Options considered

### 1. Brokaw cell (classic BJT bandgap core)

The Brokaw cell [1] uses an op-amp to force equal collector currents (or
equal voltage drops through matched resistors) in two vertical bipolar
devices of different emitter area, generating a PTAT (proportional-to-
absolute-temperature) ΔVBE across a resistor. That PTAT voltage is
scaled and summed with a CTAT (complementary-to-absolute-temperature)
VBE to produce the ~1.2 V bandgap-referenced output. It is the oldest,
most-analyzed bandgap topology in the literature [1][3][4][5], with
well-understood offset, noise, and curvature-error behavior, and a large
body of published trim and curvature-correction techniques ([5], [6]).

Minimum supply headroom for a Brokaw cell is typically ~1.4–2 V
(one VBE plus the op-amp's own headroom plus margin) — well inside our
3.3 V ±10% supply range (2.97–3.63 V). Because our node offers plenty of
headroom, the Brokaw cell's traditional weakness (poor low-voltage
scalability) is not a factor here.

**Pros**: mature, well-characterized error budget, straightforward to
verify against PVT corners, minimal transistor count, forgiving of
process characterization gaps early in a program (fewer matched-device
groups to get right on the first pass).

**Cons**: output node is a moderate-impedance summing node unless
buffered; PSRR at the reference node itself is mediocre without
additional cascoding/output buffering.

### 2. Banba (sub-1V current-summing) architecture

Banba et al. [2] generate the reference by summing a PTAT current and a
CTAT current (both current-mode, from MOS current mirrors referenced off
diode-connected bipolars) into a single output resistor, rather than
summing voltages directly across a bipolar's VBE. Because the output
voltage is set by `I_total x R` rather than being pinned to a VBE-based
node, the output can be trimmed to a value *below* 1.2 V — the whole
point of the architecture is enabling bandgap operation from supplies
that can't sit a full bandgap voltage plus headroom above ground.

That headroom-saving property has no payoff at 3.3 V: we are not
supply-constrained, and our target output (1.20 V, matching the natural
bandgap voltage) doesn't need sub-1V current summing to hit. What Banba
*does* cost is complexity: more current-mirror branches, more matching
groups, and correspondingly higher sensitivity to mirror mismatch,
finite output impedance, and layout parasitics — real risk on a process
(gf180mcu) whose device models we are still characterizing (#4) and
whose layout flow (klayout-tools) is itself the thing this canary block
is stress-testing.

**Pros**: enables sub-1V output, which is irrelevant to this project's
3.3V-primary target; current-mode summing node does have inherently
better PSRR than a voltage-mode Brokaw output if not otherwise buffered.

**Cons**: added current-mirror matching groups, added device count and
layout complexity, no benefit for a 3.3V/1.2V design point — pure cost
with no corresponding gain here.

### 3. Current-mode bandgap (general)

"Current-mode" in the literature covers a spectrum, but the common
thread is: generate PTAT and CTAT quantities as currents (via matched
current mirrors) and either (a) deliver a current reference directly, or
(b) sum the currents into a resistor to produce a voltage reference, as
in Banba. Current-mode summing nodes are lower impedance than a raw VBE
node, which generally improves PSRR and supply-noise rejection at the
reference node, and decouples the reference-generation core from
whatever output buffer/driver stage follows it [4].

This is not mutually exclusive with a Brokaw *core* — many practical
high-PSRR references use a Brokaw-style op-amp-servoed core to establish
the PTAT/CTAT relationship, then route the result through a cascoded,
current-mode output stage rather than reading the bandgap node directly.
That hybrid gets the PSRR benefit of current-mode design without paying
for Banba's full current-summing architecture (which exists to solve a
headroom problem we don't have).

## Decision

**Use a Brokaw-cell core (op-amp-servoed matched vertical-PNP pair,
gf180mcu's only bipolar device) to generate the PTAT/CTAT relationship,
with a cascoded current-mode output/bias stage rather than a raw
voltage-node tap.** We explicitly reject the Banba sub-1V
current-summing architecture: its defining benefit (operation below the
~1.2 V bandgap voltage on a headroom-starved supply) is not needed at
3.3 V ±10%, and its added current-mirror matching groups are pure
downside risk for a first block on a process we are still
characterizing (#4).

This is not "Brokaw vs. current-mode" as an either/or — it's a Brokaw
core (for the mature, well-understood PTAT/CTAT generation and error
budget) combined with current-mode techniques only where they earn their
keep (the output/bias stage, to help hit the >60 dB DC PSRR target and
keep the reference-output node low-impedance), while explicitly not
adopting Banba's full current-summing topology, since nothing about our
supply headroom asks for it.

**Startup circuit**: a current-sensing (zero-current-detect),
self-disabling startup circuit — a small branch that senses whether the
core's bias current is near zero, injects a kick current until the loop
settles to its intended (nonzero-current) operating point, and then goes
high-impedance / draws negligible current in normal operation. This is
preferred over a voltage-detect startup because voltage-detect has a
chicken-and-egg problem (the reference voltage it would compare against
isn't valid until startup completes), and because a self-disabling
current-based branch has minimal static current contribution — important
given the < 50 µA (stretch < 20 µA) Iq budget. A continuously-conducting
bleeder was considered and rejected for the same Iq-budget reason. A
fully self-starting bias network (e.g., via depletion-mode devices) was
considered and rejected as unavailable/out of scope for gf180mcu's
standard device set and as unnecessary added process risk for a first
block.

**Trim strategy**: a minimal resistor-trim network — a small number of
binary-weighted trim resistor segments, switched in via probe-pad straps
or a simple fuse/metal-option selection at test — sized to close the gap
between the ratified spec's untrimmed (±1%) and trimmed (±0.5% stretch)
targets. A full digital/OTP trim system (calibration DAC + non-volatile
fuse bank + register interface) was considered and explicitly deferred:
it is standard practice for production references, but for a first
canary block whose primary goal is proving out the design-to-silicon
flow (not multi-point production calibration), the schedule and
complexity cost isn't justified yet. This can be revisited as a later,
separate decision record if trim requirements tighten.

## Prior art: sky130 open-source bandgap designs, and what we do differently

There are known open-source sky130 bandgap reference designs circulating
in the open-silicon community (e.g., submissions built for
efabless/Skywater MPW-style shuttles). Described at the generic
architectural level publicly documented by such projects — not from any
proprietary or NDA'd source — these designs typically:

- Use a simple two-transistor (or small array) bipolar core exploiting
  sky130's parasitic BJTs, driven by a compact single- or two-stage
  op-amp servo loop — architecturally a Brokaw/Widlar-family core, sized
  small to fit MPW shuttle area/power budgets.
- Target sky130's lower core-supply operating points, which pushes
  toward headroom-conscious design choices that a 3.3V-primary process
  doesn't need to make.
- Are generally sim-only or lightly measured, with limited PVT corner
  coverage (often room-temperature plus a small set of corners rather
  than full −40…125 °C x supply x process sweeps).
- Commonly ship with little or no trim, and treat startup-circuit
  robustness and trim as documented "known limitations" / future work,
  consistent with their role as approachable, didactic open-silicon
  reference designs rather than production or catalog-grade IP.

What this project does differently, specifically because it targets
gf180mcu 3.3V rather than sky130's lower-voltage characteristics:

- **Headroom is not scarce here.** We don't need to bend the topology
  toward sub-1V tricks (Banba-style current summing) the way a
  low-voltage-flavor design might; we can spend that headroom on a
  cascoded current-mode output stage purely for PSRR, which is a
  strictly additive win rather than a necessary complexity tax.
- **Full PVT verification is a hard requirement, not a stretch.** Per
  CLAUDE.md ("Verification is the product: no claim without a
  testbench"), every recorded result must carry −40/27/125 °C, ±10%
  supply, and process-corner coverage. This is a harder bar than the
  limited-corner sim coverage typical of hobby/didactic sky130 bandgap
  projects.
- **Startup-circuit robustness and a trim strategy are in scope from
  day one** (this decision record specifies both), not deferred as
  known gaps.
- **We're targeting measured silicon**, not sim-only: the maturity
  ladder in the README goes simulation-complete -> layout DRC/LVS-clean
  -> shuttle seat (wafer.space) -> measured silicon over temperature.
- **The layout flow itself is a deliverable.** Per the friction
  protocol, every place klayout-tools is awkward or missing a capability
  for this design gets filed as a generic tool-gap issue on the public
  klayout-tools tracker — aiming for a reproducible, documented gf180mcu
  bandgap layout flow, which most sky130 hobby references don't attempt
  to produce as a reusable artifact.

## Consequences

- Final device sizing (bipolar emitter-area ratio, resistor ratios,
  trim-segment values) depends on #4's characterization of the vertical
  PNP and resistor flavors (rpolyh and alternatives) on gf180mcu; this
  record fixes the topology, not the component values.
- This decision assumes 3.3V-primary per the README target spec; if #7
  decides to also pursue a 5V flavor, the added headroom only makes this
  topology choice more comfortable (Brokaw/current-mode headroom margin
  only grows), but resistor sizing for the current-mode output stage may
  need a voltage-flavor-specific pass.
- The core op-amp's offset and systematic-error budget must be verified
  in sim, since it directly limits how close we get to the untrimmed
  ±1% spec target before relying on trim.
- The startup circuit's static current draw in steady state must be
  accounted for inside the < 50 µA Iq budget.
- The trim network introduces a wafer-probe calibration step ahead of
  shuttle submission; this should be reflected in a future test-plan
  issue covering the trim procedure itself.
- If a later measurement or #4's characterization data shows the
  current-mode output stage doesn't clear the PSRR target with adequate
  margin, revisit as a superseding decision record rather than silently
  drifting the implementation from this one.

## References

1. A. P. Brokaw, "A simple three-terminal IC bandgap reference," *IEEE
   Journal of Solid-State Circuits*, vol. 9, no. 6, pp. 388–393,
   Dec. 1974.
2. H. Banba et al., "A CMOS bandgap reference circuit with sub-1-V
   operation," *IEEE Journal of Solid-State Circuits*, vol. 34, no. 5,
   pp. 670–674, May 1999.
3. R. J. Widlar, "New developments in IC voltage regulators," *IEEE
   Journal of Solid-State Circuits*, vol. 6, no. 1, pp. 2–7, Feb. 1971.
4. B. Razavi, *Design of Analog CMOS Integrated Circuits*, 2nd ed.,
   McGraw-Hill, 2017 — Ch. 11, "Bandgap References" (startup circuits,
   current-mode references, PSRR).
5. P. R. Gray, P. J. Hurst, S. H. Lewis, R. G. Meyer, *Analysis and
   Design of Analog Integrated Circuits*, 5th ed., Wiley — bandgap
   reference chapter (trim and curvature-correction techniques).
6. R. A. Pease, "The design of band-gap reference circuits: trials and
   tribulations," in *Proc. IEEE Bipolar Circuits and Technology
   Meeting*, 1990 — practical startup and trim lore.
7. GlobalFoundries gf180mcu open PDK documentation (vertical PNP and
   poly resistor device availability referenced qualitatively; final
   numeric characterization tracked in #4).
8. Open-source sky130 bandgap reference designs circulating in the
   open-silicon community (e.g., efabless/Skywater MPW-style shuttle
   submissions), described here only at the generic architectural level
   documented publicly by such projects — no proprietary or NDA'd
   content referenced.
