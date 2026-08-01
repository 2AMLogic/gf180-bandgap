# Error amplifier design and offset/mismatch budget (issue #10)

This document allocates the ratified untrimmed output-accuracy target
(`README.md` "Target specification": **1.20 V ±2 % untrimmed, 3σ, mismatch
MC N≥300 + process corners, −40…125 °C** — [DR-0003](../spec/decision-records/0003-target-spec-ratification.md))
across the amplifier's own input-referred offset (systematic + random),
resistor mismatch and PNP mismatch, each derived from this topology's own
measured sensitivity (∂Vref/∂x), not assumed evenly. It also records the
amplifier sizing decision that replaces #8's provisional placeholder, the
loop's stability criterion and PVT verification, and its PSRR contribution.

**Bottom line, stated up front (no spec relaxation, per CLAUDE.md and this
issue's explicit escalation rule): the budget does *not* close.** Section 2
shows the amplifier's own random offset, even after a 10x (input pair) /
4x (mirror load) area increase over #8's provisional sizing, RSS-combines
with the (much smaller) resistor and PNP-mismatch terms to **~25.5 mV
(3σ)**, against a **24 mV (3σ)** budget — roughly 6 % over, before even
adding a systematic-offset reserve. Section 3 shows the amplifier's own
PSRR contribution falls **~5–28 dB short** of the ratified >60 dB DC–1 kHz
target across the PVT grid, and traces that shortfall to the amplifier (not
`bandgap_core`'s cascoded stage, which is shown separately to clear the bar
comfortably on its own). Both shortfalls are escalated per this issue's
"no spec relaxation" rule — see Section 5.

## 1. What is and is not in scope here

Per the issue's scope boundary against #4, #8 and #13:

- The **sensitivity derivations** below (∂Vref/∂Vos, ∂Vref/∂R) are this
  issue's own analysis, verified by simulation on this circuit's own
  netlist (Section 2, Section 4).
- The **mismatch coefficients** (MOS `A_pair`, PNP σ(ΔVBE)) are #4's
  characterized data (`design/device-characterization.md`), cited by
  record ID, scaled analytically to this amplifier's actual device
  geometry.
- **Resistor mismatch** cannot be simulated in this PDK release
  (`design/device-characterization.md` §2, "Known gaps": `mis_r = 0` is
  hard-coded in the resistor subcircuits) — the number used here is an
  **assumed, unverified** literature-typical Pelgrom coefficient, flagged
  explicitly as such, not a measured PDK value.
- **Statistical (Monte Carlo) verification of the whole assembled budget**
  is #13's scope. Everything below is a deterministic/analytic allocation,
  cross-checked by direct closed-loop simulation of the offset-sensitivity
  and loop-gain lines (Section 2, Section 4), not a circuit-level MC.

## 2. Amplifier offset budget

### 2.1 Topology and sizing decision

**Topology kept**: #8's real-device 5-transistor single-stage OTA
(`design/bandgap_amp.sch`) — NMOS differential pair (M1/M2), PMOS
current-mirror load (M3/M4, diode+mirror, no cascode), NMOS tail (M5)
mirroring `bandgap_core.ibias` via the `tail_bias` pin. A folded/telescopic
cascode alternative was evaluated and rejected for this issue's scope — see
Section 3.3 for why (PSRR was the motivating driver, and a first attempt at
cascoding the mirror load made PSRR *worse*, not better, absent a properly
regulated cascode bias, which is real analog design work beyond a single
pass; a mirror-load cascode does not touch the offset budget either way,
since cascode devices are common-gate stages that do not add
differential-pair input-referred offset).

**Sizing changed** (final, replaces #8's provisional 10 µm/4 µm placeholder
on every device except the tail):

| Device | Provisional (#8) | Final (#10) | Area ratio |
|---|---|---|---|
| M1, M2 (input pair) | `nfet_03v3` W=10 µm L=4 µm nf=1 | `nfet_03v3` W=100 µm L=4 µm nf=2 | 10x |
| M3, M4 (mirror load) | `pfet_03v3` W=10 µm L=4 µm nf=1 | `pfet_03v3` W=40 µm L=4 µm nf=1 | 4x |
| M5 (tail) | `nfet_03v3` W=10 µm L=4 µm nf=1 | unchanged | 1x |

L is held at 4 µm (unchanged from #8, and matching the characterized
geometry in `sim/device-mos-mismatch`, record `20260731-031718-8fb0ea6`) so
the measured `A_pair` Pelgrom coefficient applies directly with no
extrapolation in L. `nf=2` on M1/M2 is not a layout preference: gf180mcu's
`nfet_03v3` model is width-binned and a single finger tops out at 100 µm
(ngspice rejects a wider single-finger instance with "could not find a
valid modelname" — confirmed empirically while sizing this device), so a
100 µm-wide device needs ≥2 fingers.

**Why sizing was not pushed further** (a real, simulation-verified
constraint, not an unexamined stopping point): both directions tried during
this design pass — growing L (L=6 µm on M1–M4) and growing W further while
holding L (W=200–300 µm on M1/M2 alone, or with M3/M4 grown to W=80 µm) —
were verified against the loop-stability testbench (Section 4) to markedly
erode phase margin at specific PVT corners, down to single-digit degrees at
some `res_ss`/`fs`/`bjt` corners (against the 45° criterion). The added
Cgs/Cgd from bigger devices interacts with this single-stage topology's
parasitic Cgd feedthrough zero (Section 4.1's derivation) closely enough
that further area growth is not free the way a first-order weak-inversion
`gm` argument (roughly bias-current-set, not area-set, at these currents)
would suggest. **This specific self-biased, cascoded-core topology's loop
stability is unusually sensitive to amplifier device capacitance growth.**
Closing the remaining offset-budget gap (Section 2.4) needs a genuine
compensation or topology change — e.g. an explicit Miller/dominant-pole
compensation scheme, or splitting `gm` and `Cgs` across more devices via a
folded rather than single-stage structure — which is out of this issue's
scope; see Section 5's escalation.

Neither M1–M4 sizing change affects the amplifier's own quiescent current:
Iq is set by the M5/`bandgap_core.Mn5` mirror ratio (W/L = 2.5 vs 10, so
M5 draws ≈ 1/4 of the core's own branch current, measured 2.4–2.5 µA at
nominal per the offset-sensitivity op-point, consistent with
`design/bandgap_operating_point.md` §3's whole-circuit Iq accounting), which
this issue does not touch. The resize was "free" from an Iq-budget
perspective.

### 2.2 Input-referred offset — random component (measured/scaled)

Two independent contributors, both from `design/device-characterization.md`
§4 (MOS local mismatch, record `20260731-031718-8fb0ea6`), scaled to this
amplifier's actual device geometry by the PDK model's own Pelgrom law.
That law is not just the empirical `A_pair` table point — it is verified
directly from the model source (`sm141064.ngspice`'s `nfet_03v3`/
`pfet_03v3` `.subckt`, `p_sqrtarea = sqrt(Leff*Weff)`, with both the
threshold- and current-factor-mismatch variances scaled by `1/p_sqrtarea`),
so extrapolating `A_pair` to a new W (holding L fixed, as done here) is a
first-principles scaling, not curve-fit interpolation:

```
sigma(dVgs) = A_pair * sqrt(2) / sqrt(W * L)
```

**M1/M2 (input pair), direct contribution:**

`A_pair(nfet_03v3, 10/4) = 4.91 mV·µm` (device-characterization.md §4).
At W=100 µm, L=4 µm (WL = 400 µm²):

```
sigma_M1M2 = 4.91 * sqrt(2) / sqrt(400) = 0.347 mV   (3-sigma = 1.04 mV)
```

**M3/M4 (mirror load), referred to the input:**

`A_pair(pfet_03v3, 10/4) = 5.02 mV·µm`. At W=40 µm, L=4 µm (WL = 160 µm²):

```
sigma_M3M4 = 5.02 * sqrt(2) / sqrt(160) = 0.561 mV
```

Mirror-load mismatch is attenuated at the input by the standard
current-mirror-load OTA transfer, `gm3/gm1` — not assumed, measured
directly on this circuit's own DC operating point (`.op`, nominal `tt`/
27 °C/3.3 V, scratch verification against the final-sized netlist):
`gm(M1) = 28.39 µA/V`, `gm(M3) = 19.55 µA/V`, so `gm3/gm1 = 0.6888`.

```
sigma_M3M4_referred = 0.561 * 0.6888 = 0.387 mV
```

**Combined random input-referred offset (RSS):**

```
sigma_Vos_random = sqrt(0.347^2 + 0.387^2) = 0.520 mV
3-sigma_Vos_random = 1.559 mV
```

**Not credited: an `nf`-driven matching bonus.** The gf180mcu
`nfet_03v3`/`pfet_03v3` local-mismatch variance is scaled by a `par`
argument that is independent of `nf` (always 1 regardless of finger
count) — a device drawn as `nf=2` fingers of one logical transistor is,
per the PDK's own model and per standard Pelgrom-law physics, **not** the
same as two independently-mismatched unit devices averaged together (that
requires a deliberate interdigitated common-centroid *pair* of separate
instances, a layout technique — #16's job, not credited here). The
`sigma_M1M2` figure above already reflects this: it uses the full drawn
gate area (W×L = 400 µm²) as a single device, with no √2 bonus assumed for
the two-finger layout.

### 2.3 Input-referred offset — systematic component

Not independently simulated (no layout exists yet — #16). By construction,
this is expected to be small: M1=M2 and M3=M4 are drawn identically, the
differential pair and mirror load are each a single matching group, and
the amplifier's own bias (tail mirrored 1:1 in `Vgs` from `bandgap_core`)
does not introduce an asymmetric reference. A conservative **2 mV (3σ-
equivalent) reserve** is carried for this line pending #16's common-centroid
layout and any post-layout extracted verification; this is a placeholder,
not a measurement, and is flagged as such.

### 2.4 Amplifier-offset → Vref sensitivity (measured, not assumed)

Verified by simulation (per this issue's test plan): a series test-offset
source inserted between the core's `sns1` node and the amplifier's `in_n`
pin (electrically identical to an amplifier input-referred offset, since
`sns1` is the Q1 emitter node and — per
`design/bandgap_operating_point.md` §1 — connects to `bandgap_amp.in_n`
with nothing else in between), swept ±2 mV, full closed loop, full PVT.

- **Record**: [`sim/amp-offset-sensitivity/records/20260801-034212-c26da47.md`](../sim/amp-offset-sensitivity/records/20260801-034212-c26da47.md)
- **Result**: `dVref/dVos` = **16.07 mV/mV** (mean), range **15.96–16.17
  mV/mV** across the full 81-point PVT grid (1.34 % spread) — a tight,
  PVT-robust number. **Sign is positive** (see the record's Claim/checks
  field for the sign derivation: `in_n` is this OTA's inverting output
  path, and the loop's overall sign works out positive at `Vref`, contrary
  to what the R1/R2-magnitude-only hand estimate in
  `design/bandgap_operating_point.md` §2 might suggest — magnitude is
  consistent with that ~15.28 estimate and with the ~14.3 Brokaw-gain
  figure `spec/decision-records/0003-target-spec-ratification.md`'s
  spec-review input derived independently).

This same sensitivity applies to the PNP-mismatch line (Section 2.6): a
real Q1 `VEB` deviation from nominal is electrically indistinguishable
(by superposition, since the circuit is linear for a small perturbation)
from a series offset inserted at the same node — the same node this
testbench injects at.

### 2.5 Resistor mismatch (assumed coefficient — PDK cannot verify)

`design/device-characterization.md` §2 states plainly: local resistor
mismatch is not modeled in this gf180mcu release (`mis_r = 0`, hard-coded
and commented out in the resistor subcircuits). This line is therefore an
**assumed, literature-typical Pelgrom coefficient for polysilicon
resistors, Ar ≈ 1.5 %·µm**, explicitly flagged as unverified for this PDK
and requiring future silicon or a PDK update with resistor mismatch enabled
to confirm. (Ar for poly resistors is commonly cited in the 1–2 %·µm range
in the analog-design literature; 1.5 %·µm is a representative middle value,
not a measurement.)

```
sigma(dR/R) = Ar / sqrt(W * L)
```

- R2 (`ppolyf_u`, W=2 µm, L=18 µm, area=36 µm²): `sigma_e2 = 1.5/6 = 0.25 %`
- R1 (`ppolyf_u`, W=2 µm, L=280 µm, area=560 µm²): `sigma_e1 = 1.5/23.66 = 0.0634 %`

**Sensitivity** (derived from the topology, `design/bandgap_operating_point.md`
§1's `Vref = VEB(Q3) + I·R1` with `I = ΔVBE(I)/R2` set independently of
R1): an independent relative error in either R1 or R2 shifts the output
branch's `I·R1` term by the same magnitude, `R1·I`, to first order (R2
error moves `I` inversely; R1 error moves the term directly) — measured
directly from this design's own netlist, `R1·I = 50334.7 Ω × 10.06 µA =
0.506 V` (nominal, `tt`/27 °C/3.3 V, per `design/bandgap_operating_point.md`
§2–§3).

```
sigma_Vref_R = R1*I * sqrt(sigma_e1^2 + sigma_e2^2)
             = 0.506 V * sqrt(0.000634^2 + 0.0025^2)
             = 0.506 V * 0.00258 = 1.31 mV   (3-sigma = 3.92 mV)
```

Small relative to the amplifier term, consistent with
`device-characterization.md`'s framing that the MOS amplifier/mirror pair,
not the resistors or the PNP core pair, is where this budget's area spend
belongs.

### 2.6 PNP mismatch (measured, #4 data)

`design/device-characterization.md` §5, record `20260731-040850-187a336`:
the area-ratioed `pnp_05p00x05p00`/`pnp_10p00x10p00` pair's own `ΔVBE`
mismatch at 10 µA, 27 °C: **3σ = 0.128 mV**. Per Section 2.4, this enters
`Vref` through the same sensitivity as the amplifier offset (same node):

```
3-sigma_Vref_PNP = 0.128 mV * 16.0735 mV/mV = 2.06 mV
```

### 2.7 Budget table (RSS, untrimmed, 3σ)

| Line | 3σ contribution to Vref | Source |
|---|---|---|
| Amplifier offset, random (M1/M2 + M3/M4-referred) | 25.06 mV | Sections 2.2, 2.4 — analytic scaling of record `20260731-031718-8fb0ea6`, sensitivity from record `20260801-034212-c26da47` |
| Resistor mismatch (R1, R2, independent) | 3.92 mV | Section 2.5 — **assumed** coefficient, PDK cannot verify |
| PNP mismatch (Q1/Q2 pair) | 2.06 mV | Section 2.6 — record `20260731-040850-187a336`, sensitivity from record `20260801-034212-c26da47` |
| **RSS of random terms** | **25.45 mV** | `sqrt(25.06^2 + 3.92^2 + 2.06^2)` |
| Amplifier offset, systematic (reserve, unverified) | +2.00 mV | Section 2.3 — placeholder pending #16 layout |
| **Total (RSS random + systematic reserve)** | **~27.5 mV** | |
| **Ratified untrimmed target (3σ)** | **24.0 mV** (±2 % of 1.20 V) | `README.md`, DR-0003 |

**The budget does not close.** RSS of the random terms alone is already
~6 % over the 24 mV target; adding the systematic reserve pushes it to
~15 % over. The amplifier's own random offset is, by a wide margin, the
dominant term — exactly as `design/device-characterization.md` §4 and
DR-0003's spec-review input both anticipated, and exactly why this issue
exists as separately-budgeted design work rather than being folded into
schematic entry.

No allocation above has been loosened to make the table sum — see
Section 5.

## 3. PSRR contribution

### 3.1 Method

Closed-loop AC transfer `H(f) = Vref(f)/Vdd(f)` with a unit AC stimulus on
the supply source (`vsup ... ac 1`), full closed loop (real `bandgap_amp`,
final sizing), swept 0.01 Hz – 1 kHz (0.01 Hz stands in for "DC": every
device capacitance in this design is many decades into its high-impedance
region there). `PSRR_dB(f) = -20*log10(|H(f)|)`. This is a genuinely
single-port small-signal measurement — no loop break, no injection-point
ambiguity, unlike the loop-gain probe in Section 4.

- **Testbench**: `sim/amp-psrr/testbench/tb_psrr.spice`
- **Record**: [`sim/amp-psrr/records/20260801-034242-c26da47.md`](../sim/amp-psrr/records/20260801-034242-c26da47.md)

### 3.2 Result

| | Value | Corner |
|---|---|---|
| Nominal (`tt`/27 °C/3.3 V) | 51.0 dB | — |
| Worst case across full 81-point PVT grid | **31.9 dB** | `sf`/125 °C/3.63 V |
| Best case across full grid | 87.4 dB | `fs`/−40 °C/2.97 V |

**Overall: FAIL against the ratified >60 dB DC–1 kHz target** — every
corner at 125 °C and every corner at 3.63 V falls short, by as little as
~3 dB (`res_ff`/125 °C/2.97 V, 54.9 dB) and as much as ~28 dB
(`sf`/125 °C/3.63 V, 31.9 dB).

### 3.3 Root cause: the amplifier, not `bandgap_core`'s cascode

A diagnostic experiment isolates which half of the loop is responsible.
`bandgap_amp` is replaced entirely with an idealized infinite-gain,
zero-supply-sensitivity servo (a linear controlled source forcing
`sns1 = sns2` exactly) — by construction this has zero PSRR contribution of
its own, so whatever PSRR shortfall remains is 100 % attributable to
`bandgap_core`'s own cascoded output stage (DR-0001), and by elimination,
whatever *additional* shortfall the real-amplifier record (Section 3.2)
shows on top of this is attributable to the amplifier.

- **Testbench**: `sim/core-psrr-ideal-amp/testbench/tb_core_psrr_ideal_amp.spice`
  (diagnostic only — **not a spec claim**, see the testbench header)
- **Record**: [`sim/core-psrr-ideal-amp/records/20260801-033034-c26da47.md`](../sim/core-psrr-ideal-amp/records/20260801-033034-c26da47.md)
- **Result**: the large majority of the 81-point grid reads **80–99 dB**
  (comfortably clearing the ratified bar on the core's own contribution
  alone), with a small number of outlier corners (`bjt_ff`/125 °C/3.30 V,
  `bjt_ss`/125 °C/3.30 V, `sf`/125 °C/3.63 V) reading anomalously near 0 dB.
  These outliers are very likely a modeling artifact of the idealized
  infinite-gain, infinite-bandwidth controlled source (which has no
  physical bandwidth limit of its own and can interact with the real
  cascode's non-dominant poles in a way a real, bandwidth-limited amplifier
  never would) rather than a genuine property of `bandgap_core` — the
  *real*-amplifier record (Section 3.2) shows no such near-0 dB collapse
  anywhere in its own 81-point grid (its worst point is 31.9 dB, not
  −0.5 dB), which is inconsistent with the core itself being catastrophically
  bad at exactly those three corners. This diagnostic is not re-run with a
  bandwidth-limited ideal amp (out of this issue's scope) — the majority-of-
  grid result (80–99 dB) already answers the decomposition question clearly
  enough: **`bandgap_core`'s own cascoded stage is not the PSRR bottleneck;
  the amplifier is.**

### 3.4 Why a cascode fix was tried and reverted

Since the amplifier is the bottleneck, a telescopic cascode on the M3/M4
mirror load (the classic PSRR fix for a simple-mirror-load OTA, since a
plain mirror load's output node tracks `Vdd` almost directly through
`M4`'s `Vsd`) was implemented as a scratch experiment: `M3`/`M4` converted
to a genuine cascode current mirror (bottom diode-connected pair + cascode
pair), with a self-biased wide-swing cascode-bias generator modeled on
`bandgap_core`'s own `MCB`/`MNB` pattern (self-biased off `tail_bias`, so
it collapses in the zero-current degenerate state exactly as the rest of
this amplifier does — see `design/bandgap_amp.sch`'s header comment on why
that matters).

**Result: PSRR got *worse*, not better** (measured ~38–46 dB across a
spot-check grid, vs ~51 dB nominal for the plain mirror). The cascode-bias
node's own first-order supply tracking (a simple diode-connected PMOS bias
generator has `Vsg` only weakly dependent on its own bias current, so its
gate rides almost 1:1 with `Vdd` ripple) undoes the cascode's intended
isolation unless the bias itself is supply-regulated — a non-trivial
addition (a genuinely low-impedance, supply-independent cascode bias
reference) that is real analog design work beyond what a single scratch
iteration can respectably close out. This attempt was **not** committed to
`design/bandgap_amp.sch` — the schematic keeps the plain (uncascoded)
mirror-load OTA, and this negative result is recorded here so a future PSRR
pass does not have to rediscover it.

## 4. Loop stability

### 4.1 Method and sign convention

The servo loop closes through exactly one wire in this topology: the
amplifier's `out` pin directly drives the core's `fb` net (the four mirror
gates). Because the break point is a single conductor — one voltage
difference, one shared branch current — a single series AC test-voltage
injection at that break gives the loop gain **exactly** (Middlebrook/Tian
dual injection is provably equivalent to single injection for a 1-port
break of this kind; dual injection exists to handle the harder general
2-port case, which does not arise here).

Let `B` = the `fb` net feeding the forward path (core → amp), `A` = the
amplifier's own output. Breaking the wire and inserting an ideal AC test
source (`B = A + vt`, `vt` = 1∠0°, DC = 0, so the DC operating point is
identical to the closed loop) and measuring `x = V(B)/vt` gives the return
ratio exactly via `T = 1 - 1/x` — pure algebra from the `B = A + vt`
wiring, with no sign assumption about the circuit.

**Because this loop's characteristic equation is `1 - T = 0` (a `T = +1`
danger point), not the classic op-amp `1 + T = 0` form (`T = -1` danger),
the Nyquist danger point for this `T` is magnitude 1 **and** phase 0° (mod
360°) — not magnitude 1 and phase 180°.** Measured at nominal PVT this
circuit's `T` has DC phase ≈180° (a real, physical extra inversion from the
R2-mediated asymmetry between the `sns1`/`sns2` branches), and `|T(f)|`
does not cross 0 dB in the classical single-crossing sense: DC gain ≈42 dB
rolls off to a local minimum, then *rises again* to a high-frequency
plateau (a parasitic Cgd feedthrough path around the single gain stage).
`T`'s phase stays in a band roughly 80–205° throughout — nowhere near the
true danger phase of 0° (mod 360°) — so the Nyquist locus never approaches
the critical point `(+1, 0)` regardless of how thin the magnitude margin
looks in isolation.

### 4.2 Stability criterion (this design's own choice, not a ratified spec line)

Phase margin, defined as the angular distance of `T`'s phase — evaluated at
the frequency of **global minimum** `|T(f)|` over 0.1 Hz – 2 GHz (the
worst-case approach to the critical point) — from 0° (mod 360°), **must
stay ≥45° at every PVT corner**. The worst-case loop-gain magnitude at that
same frequency is reported alongside for context. 45° is a standard
minimum-PM bar for a general-purpose loop; it is not a ratified spec line
(the ratified spec has no stability-margin row), so it is stated here
explicitly rather than imported silently, per this issue's instruction.

### 4.3 Result

- **Testbench**: `sim/amp-loop-stability/testbench/tb_loop_stability.spice`
- **Record**: [`sim/amp-loop-stability/records/20260801-034142-c26da47.md`](../sim/amp-loop-stability/records/20260801-034142-c26da47.md)

| | Value | Corner |
|---|---|---|
| Phase margin, minimum across full 81-point PVT grid | **132.5°** | `tt`/−40 °C/2.97 V |
| Phase margin, maximum | 177.3° | `res_ss`/−40 °C/3.63 V |
| DC loop gain range | 37.7–42.9 dB | — |
| Worst-case (minimum) loop-gain magnitude at the critical frequency | 0.09–8.4 dB (always ≥0 dB) | — |

**Overall: PASS at every PVT corner**, with substantial margin (worst case
132.5° against the 45° criterion — nearly 3x). This large margin is exactly
why Section 2.1's sizing-growth attempts (which eroded PM to single digits
at some corners) were tried at all — there appeared to be plenty of room
before this record was in hand at each candidate sizing, and each attempt
was independently verified against this same testbench before being
accepted or reverted.

## 5. Escalation (no spec relaxation)

Per this issue's explicit instruction and CLAUDE.md's "agents do not relax
the ratified spec to make results pass": **no allocation in Section 2.7 or
Section 3 has been loosened to make either table close.** Two shortfalls
are recorded here and escalated rather than fudged:

1. **Untrimmed accuracy budget** (Section 2.7): amplifier random offset
   alone is ~104 % of the full 24 mV (3σ) budget; RSS-combined with the
   (much smaller) resistor and PNP terms, ~106 %; with the systematic
   reserve, ~115 %. Closing this within the existing 5T single-stage
   topology would require either accepting the loop-stability regression
   Section 2.1 measured from further area growth (not acceptable without a
   compensation redesign) or moving to a different amplifier topology
   (folded cascode, two-stage, or auto-zero/chopper) — a scope decision for
   #1 (spec) or #14 (trim), not this issue, per the issue's own escalation
   rule. **Note the ratified untrimmed target exists precisely so trim
   (#14, ratified range ≥±5 %) can close exactly this kind of gap on a
   per-die basis** — a ~6–15 % overshoot on an *untrimmed* 3σ target is a
   meaningfully different situation than the same overshoot would be on a
   trimmed one, and #14 should have this number when it scopes the trim
   network.
2. **PSRR**: the amplifier's own contribution (Section 3.2–3.4) falls
   5–28 dB short of the ratified >60 dB DC–1 kHz target across the PVT
   grid, while `bandgap_core`'s own cascoded stage does not appear to be
   the limiter (Section 3.3). Closing this needs either a properly
   supply-regulated cascode bias for the mirror load (Section 3.4's
   reverted attempt shows the naive version makes PSRR worse) or a
   different PSRR-oriented topology change — real analog design work
   deserving its own scoped follow-up issue, not a fix squeezed into this
   one's remaining budget.

This document, its cited `sim/` records, and this note collectively are
the evidence-backed shortfall report this issue's escalation rule calls
for; a comment pointing back here is posted on #1 (and a new follow-up
issue is filed for the amplifier-topology work implied by both shortfalls)
per that rule.

## 6. Summary of acceptance criteria

| Criterion | Status |
|---|---|
| Budget table allocating untrimmed accuracy, with sensitivity derivation, summing within target | Table exists, sensitivities are simulation-derived (Section 2) — **does not sum within target**, see Section 5 |
| Amplifier schematic replaces #8's provisional sizing, netlists cleanly, wrapper pin set unchanged | Done — `design/bandgap_amp.sch` resized (Section 2.1); `design/bandgap_top.sch`/`.sym` pin set untouched; netlists cleanly via `xschem --rcfile design/xschemrc -n -x -q` |
| Corner results in `sim/` for loop gain and phase margin, full PVT, meeting the stated criterion | **PASS**, Section 4, record `20260801-034142-c26da47` |
| Offset-sensitivity result in `sim/`, consistent with the budget's amp allocation | Done, Section 2.4, record `20260801-034212-c26da47` |
| PSRR contribution result in `sim/` supporting the >60 dB DC target | Result recorded, Section 3 — **does not support the target**, see Section 5 |
| Operating-point doc updated, provisional-amp caveat removed, final sizing/bias recorded with #4 citations | Done — `design/bandgap_operating_point.md` |
| All `sim/` records follow the append-only evidence format, full PVT coverage | Done — all four new/updated experiments (`amp-loop-stability`, `amp-offset-sensitivity`, `amp-psrr`, `core-psrr-ideal-amp`) use the corner runner, full 81-point grid where applicable |
