# Error amplifier design and offset/mismatch budget (issues #10, #42)

This document allocates the ratified untrimmed output-accuracy target
(`README.md` "Target specification": **1.20 V ±2 % untrimmed, 3σ, mismatch
MC N≥300 + process corners, −40…125 °C** — [DR-0003](../spec/decision-records/0003-target-spec-ratification.md))
across the amplifier's own input-referred offset (systematic + random),
resistor mismatch and PNP mismatch, each derived from this topology's own
measured sensitivity (∂Vref/∂x), not assumed evenly. It also records the
amplifier sizing and topology decision, the loop's stability criteria and
PVT verification, and its PSRR contribution.

**Bottom line, stated up front: both of #10's recorded shortfalls now
close.** #10 sized a 5-transistor single-stage OTA against this budget and
found two ratified-spec lines it could not meet — the untrimmed accuracy
budget came in at ~106–115 % of target, and PSRR fell 5–28 dB short of the
>60 dB DC–1 kHz row — and escalated both (its Section 5) rather than
relaxing anything. **#42 is that escalation's answer**: `bandgap_amp` is
now a telescopic-cascode OTA with explicit dominant-pole compensation
(Section 2.1), and against the same testbenches, on the same PVT grid:

| Line | #10 (5T OTA) | #42 (telescopic cascode) | Ratified target |
|---|---|---|---|
| Untrimmed accuracy, RSS 3σ at Vref | 25.45 mV random / ~27.5 mV with reserve | **13.79 mV random / 15.79 mV with reserve** | ≤ 24.0 mV (±2 % of 1.20 V) |
| PSRR, worst of 81 PVT points | 31.87 dB (19/81 corners pass) | **77.61 dB (81/81 corners pass)** | > 60 dB DC–1 kHz |
| Loop phase margin, worst corner | 119.1° | 177.8° | ≥ 45° (this design's own criterion) |
| Loop Nyquist gain margin, worst corner | no critical-axis crossing | **−7.0 dB** | < 0 dB (added in #42, Section 4.4) |

Section 5 records what did **not** close, unrelaxed: the ratified
quiescent-current row, which was already failing before this issue and is
~1.5 µA (nominal) / ~3.0 µA (worst corner) worse because of it.

## 1. What is and is not in scope here

Per #10's scope boundary against #4, #8 and #13, carried forward:

- The **sensitivity derivations** below (∂Vref/∂Vos, ∂Vref/∂R) are
  simulation-verified on this circuit's own netlist (Section 2, Section 4).
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
  is #13's scope (`sim/mc-untrimmed/`). Everything below is a
  deterministic/analytic allocation, cross-checked by direct closed-loop
  simulation of the offset-sensitivity and loop-gain lines.
- **The accuracy/trim split is #14's decision, not this document's.** This
  budget closes untrimmed against the ratified target; it does not scope
  trim range.

## 2. Amplifier offset budget

### 2.1 Topology and sizing decision (#42)

**Topology changed.** #8 entered a 5-transistor single-stage OTA; #10 kept
it and resized it; #42 replaces it with a **telescopic cascode with an
explicit dominant-pole compensation capacitor**
(`design/bandgap_amp.sch`):

| Device | Type | #10 sizing | #42 sizing | Role |
|---|---|---|---|---|
| M1, M2 | `nfet_03v3` | W=100 µm L=4 µm nf=2 | **W=200 µm L=4 µm nf=4** | input pair (in_p = core `sns2`, in_n = core `sns1`) |
| MC1, MC2 | `nfet_03v3` | — (new) | **W=20 µm L=16 µm** | NMOS cascodes on the input-pair drains, gate `ncasc` |
| M3, M4 | `pfet_03v3` | W=40 µm L=4 µm | **W=20 µm L=16 µm** | PMOS mirror load |
| MC3, MC4 | `pfet_03v3` | — (new) | **W=40 µm L=16 µm** | wide-swing PMOS cascodes on the mirror load, gate `pbias` |
| M5 | `nfet_03v3` | W=10 µm L=4 µm | unchanged | tail, gate = `tail_bias` (core `ibias`) |
| MBN2 | `nfet_03v3` | — (new) | W=2 µm L=16 µm | ground-referenced sink off `tail_bias` |
| MBP1 | `pfet_03v3` | — (new) | W=1 µm L=50 µm | PMOS diode → the vdd-referenced `pbias` rail |
| MB1 | `pfet_03v3` | — (new) | W=5 µm L=50 µm | mirrors MBP1, feeds the `ncasc` stack |
| MBD1, MBD2 | `nfet_03v3` | — (new) | W=1 µm L=4 µm each | stacked diodes → the ground-referenced `ncasc` |
| CC | `cap_mim_2f0_m4m5_noshield` | — (new) | 60 µm × 60 µm (≈7.2 pF) | dominant-pole compensation, `out` → **vdd** |

L on the input pair is held at 4 µm (unchanged from #8/#10, and matching
the characterized geometry in `sim/device-mos-mismatch`, record
`20260731-031718-8fb0ea6`) so the measured `A_pair` Pelgrom coefficient
applies directly with no extrapolation in L. `nf=4` at W=200 µm is not a
layout preference: gf180mcu's `nfet_03v3`/`pfet_03v3` models are
width-binned with a 100 µm top bin edge per finger, so 200 µm needs ≥2
fingers; 4 fingers of 50 µm keeps each finger inside the *same* bin #10's
100 µm/nf=2 device used, so no bin extrapolation is introduced either.

**Why each piece is there** — the three problems and the three answers:

1. **PSRR (Section 3) is fixed by the *NMOS* cascode, and only by it.**
   The core's four PMOS mirror legs sit with their sources on `vdd` and
   their gates on this amp's `out`, so what the core actually needs held
   constant under supply ripple is `u = out − vdd`, not `out`. Writing the
   amp's output node as a current balance between the PMOS load
   (conductance `gds4` to `vdd`) and the NMOS branch (conductance `G_n` to
   ground),

   ```
   s   = dout/dvdd            = gds4 / (gds4 + G_n)
   A   = gm1 / (gds4 + G_n)                            (amp DC gain)
   (1 - s) / A = 1 / (gm1 * Ro,nmos)      where Ro,nmos = 1/G_n
   ```

   i.e. **the amplifier's supply-referred input error is exactly the
   reciprocal of the NMOS branch's intrinsic gain, and is independent of
   the PMOS load's output resistance.** That is a closed-form explanation
   for #10's negative result (Section 3.4): cascoding the *mirror load*
   raises `Ro,pmos`, which does not appear in that expression at all, so it
   could not help — and the naive cascode-bias generator it needed made
   things actively worse. Cascoding the NMOS side multiplies `Ro,nmos` by
   `gm·ro` of MC1/MC2 and moves the term directly.

   The NMOS cascode gate `ncasc` must be **ground-referenced** for this to
   hold. A supply-following cascode gate would drag the input pair's drains
   along with `vdd` and re-introduce exactly the `Vds` modulation the
   cascode exists to remove — hence the MBD1/MBD2 diode stack rather than a
   copy of `bandgap_core`'s own (correctly vdd-referenced) MCB/MNB
   generator.

2. **The offset budget (Section 2.2) is fixed by the mirror load's `L`,
   and the PMOS cascode is what makes that affordable.** The mirror's
   input-referred contribution is `σ(M3/M4) · gm3/gm1`; with
   `σ ∝ 1/√(W₃L₃)` and, in strong inversion, `gm3 ∝ √(W₃/L₃)`, the product
   scales as **1/L₃ at any W₃**. So L₃ goes 4 µm → 16 µm and W₃ 40 µm →
   20 µm: measured `gm3/gm1` falls 0.689 → **0.283** while the gate area
   doubles. Lower `gm3` means a larger `Vov3`, which needs `Vsd(M3)`
   headroom the uncascoded stack did not have to spare — the wide-swing
   PMOS cascode (MC3/MC4 off `pbias`, sized for `Vsg ≈ Vth + 2·Vov`) is
   what buys it back. Measured at `tt`/27 °C/3.30 V: `Vsd(M3) = 400 mV`
   against `Vdsat = 209 mV`, i.e. **191 mV of saturation margin**, and
   `Vsd(MC4) = 629 mV` against `Vdsat = 161 mV`.

   The PMOS cascode also removes a **systematic** error the plain mirror
   had: with M3 diode-connected and M4 driving the output node, the two
   devices ran at different `Vsd` (0.83 V vs 1.03 V at nominal), a
   first-order mirror-ratio error. Cascoded, the two mirror drains sit at
   2.9003821 V and 2.9003860 V — **4 µV apart**. The 2 mV systematic
   reserve carried in Section 2.3 is therefore now conservative rather than
   merely unverified.

3. **The compensation capacitor is what makes (1) and (2) survivable.**
   Cascoding both sides raises the amp's DC gain from ~62 dB to ~110 dB and
   the loop's from ~42 dB to ~103 dB. That much extra gain does not fit
   inside #10's compensation, which was *no compensation at all* — the
   loop's poles were whatever the parasitics happened to be. An
   intermediate revision of this design, uncompensated, measured **phase
   margin 179.8° at every one of the 81 PVT corners** by #10's criterion
   while its Nyquist locus crossed the positive real axis at |T| = +33 dB —
   an encirclement of the +1 critical point — and oscillated with volts of
   ripple in transient. See Section 4.4 for the criterion added to catch
   that, and Section 4.5 for the sized result.

   `CC` returns to **`vdd`, not `vss`**, deliberately: `out` must track
   `vdd` for reason (1), and a cap to `vss` would fight that at exactly the
   frequencies the ratified PSRR row covers.

**Bias-chain ordering is load-bearing, not cosmetic.** Every bias node in
this amp still collapses with the core in the degenerate zero-current state
— there is no independent reference anywhere, which is what keeps #11's
startup circuit doing real work instead of being masked (see
`design/bandgap_operating_point.md` §4.2). But a self-biased chain can
acquire a *second* dead state of its own. An earlier revision of this
design took MB1's gate from `nd1`; when the amp is off, `nd1` rails to
`vdd`, MB1 never turns on, `ncasc` never rises, and the amp stays off — a
latch the startup kick could not clear, which showed up as a transient that
settled at `vref ≈ 2.9 V` with the loop wide open. The shipped chain is
ordered `tail_bias → MBN2 → pbias → MB1 → ncasc`, every link driven from
the core's own `ibias` (which the startup circuit forces), so it cannot
latch. `sim/startup-state-search/` (record
[`20260801-074416-a7fd16a`](../sim/startup-state-search/records/20260801-074416-a7fd16a.md))
re-verifies recovery from the adversarial degenerate seed at all 81 points
with the new amp.

**Iq cost.** The two bias branches draw 0.139 µA (MBN2/MBP1) and 0.725 µA
(MB1 and the `ncasc` diode stack) at nominal, and the tail moves 2.58 →
2.66 µA. Whole-block Iq goes 46.78 → **48.24 µA** at `tt`/27 °C/3.30 V and
77.5 → **80.5 µA** at the binding `ff`/125 °C/3.63 V corner. That row
already failed before this issue; see Section 5.

### 2.2 Input-referred offset — random component (measured/scaled)

Two independent contributors, both from `design/device-characterization.md`
§4 (MOS local mismatch, record `20260731-031718-8fb0ea6`), scaled to this
amplifier's actual device geometry by the PDK model's own Pelgrom law.
That law is verified directly from the model source
(`sm141064.ngspice`'s `nfet_03v3`/`pfet_03v3` `.subckt`,
`p_sqrtarea = sqrt(Leff*Weff)`, with both the threshold- and
current-factor-mismatch variances scaled by `1/p_sqrtarea`), so
extrapolating `A_pair` to a new W (holding L fixed, as done here) is a
first-principles scaling, not curve-fit interpolation:

```
sigma(dVgs) = A_pair * sqrt(2) / sqrt(W * L)
```

**M1/M2 (input pair), direct contribution:**

`A_pair(nfet_03v3, 10/4) = 4.91 mV·µm`. At W=200 µm, L=4 µm (WL = 800 µm²):

```
sigma_M1M2 = 4.91 * sqrt(2) / sqrt(800) = 0.2455 mV   (3-sigma = 0.737 mV)
```

**M3/M4 (mirror load), referred to the input:**

`A_pair(pfet_03v3, 10/4) = 5.02 mV·µm`. At W=20 µm, L=16 µm (WL = 320 µm²):

```
sigma_M3M4 = 5.02 * sqrt(2) / sqrt(320) = 0.3969 mV
```

Mirror-load mismatch is attenuated at the input by `gm3/gm1` — not
assumed, measured directly on this circuit's own DC operating point (`.op`,
nominal `tt`/27 °C/3.30 V, against the final netlist):
`gm(M1) = 31.18 µA/V`, `gm(M3) = 8.819 µA/V`, so `gm3/gm1 = 0.2829`
(#10's plain mirror measured 0.6888).

```
sigma_M3M4_referred = 0.3969 * 0.2829 = 0.1123 mV
```

**Cascode devices contribute no input-referred offset to first order.**
MC1–MC4 are common-gate stages: a `ΔVgs` mismatch between MC1 and MC2
appears in series at the input pair's drain nodes, where it is divided by
the input devices' own intrinsic gain before it reaches the input. Same for
MC3/MC4 against the mirror. The bias devices (MBN2, MBP1, MB1, MBD1/MBD2)
generate nodes that are **common** to both signal branches, so their
mismatch is a common-mode term, not a differential one.

**Combined random input-referred offset (RSS):**

```
sigma_Vos_random = sqrt(0.2455^2 + 0.1123^2) = 0.2700 mV
3-sigma_Vos_random = 0.8099 mV      (#10: 1.559 mV)
```

**Not credited: an `nf`-driven matching bonus.** The gf180mcu
`nfet_03v3`/`pfet_03v3` local-mismatch variance is scaled by a `par`
argument that is independent of `nf` (always 1 regardless of finger count).
A device drawn as `nf=4` fingers of one logical transistor is, per the
PDK's own model and per standard Pelgrom-law physics, **not** the same as
four independently-mismatched unit devices averaged together (that requires
a deliberate interdigitated common-centroid *pair* of separate instances —
#16's job, not credited here). `sigma_M1M2` above uses the full drawn gate
area (W×L = 800 µm²) as a single device, with no √nf bonus assumed.

### 2.3 Input-referred offset — systematic component

Not independently simulated (no layout exists yet — #16). A conservative
**2 mV (3σ-equivalent) reserve** is carried for this line pending #16's
common-centroid layout and post-layout extracted verification. It is
carried at #10's value deliberately, even though #42's PMOS cascode removes
the one systematic mirror term that *was* identifiable at schematic level
(the `Vsd(M3) ≠ Vsd(M4)` mirror-ratio error, now 4 µV — Section 2.1): the
reserve exists for layout-induced asymmetry that no schematic-level
simulation can see, so it is not credited down here.

### 2.4 Amplifier-offset → Vref sensitivity (measured, not assumed)

Verified by simulation: a series test-offset source inserted between the
core's `sns1` node and the amplifier's `in_n` pin (electrically identical
to an amplifier input-referred offset, since `sns1` is the Q1 emitter node
and — per `design/bandgap_operating_point.md` §1 — connects to
`bandgap_amp.in_n` with nothing else in between), swept ±2 mV, full closed
loop, full PVT.

- **Record (#42 amp)**: [`sim/amp-offset-sensitivity/records/20260801-073817-a7fd16a.md`](../sim/amp-offset-sensitivity/records/20260801-073817-a7fd16a.md)
- **Result**: `dVref/dVos` = **16.13 mV/mV** (mean), range **16.02–16.21
  mV/mV** across the full 81-point PVT grid (1.18 % spread).
- **Paired baseline (#10's amp on the same bench)**:
  [`20260801-073550-a7fd16a`](../sim/amp-offset-sensitivity/records/20260801-073550-a7fd16a.md)
  — 16.07 mV/mV mean, 15.83–16.26 range.

The two agree to 0.4 %, which is the point of running both: **this
sensitivity is a property of `bandgap_core`'s Brokaw gain, not of the
amplifier**, so the amp redesign must not move it, and does not. Sign is
positive (see the record's Claim field for the derivation; magnitude is
consistent with the ~15.28 R1/R2 hand estimate in
`design/bandgap_operating_point.md` §2 and with the ~14.3 Brokaw-gain
figure derived independently in
`spec/decision-records/0003-target-spec-ratification.md`'s spec-review
input).

This same sensitivity applies to the PNP-mismatch line (Section 2.6): a
real Q1 `VEB` deviation is electrically indistinguishable, by
superposition, from a series offset injected at the same node.

### 2.5 Resistor mismatch (assumed coefficient — PDK cannot verify)

Unchanged from #10 — this issue did not touch `bandgap_core`.
`design/device-characterization.md` §2 states plainly that local resistor
mismatch is not modeled in this gf180mcu release (`mis_r = 0`, hard-coded
and commented out in the resistor subcircuits). This line is therefore an
**assumed, literature-typical Pelgrom coefficient for polysilicon
resistors, Ar ≈ 1.5 %·µm**, explicitly flagged as unverified for this PDK.

```
sigma(dR/R) = Ar / sqrt(W * L)
```

- R2 (`ppolyf_u`, W=2 µm, L=18 µm, area=36 µm²): `sigma_e2 = 1.5/6 = 0.25 %`
- R1 (`ppolyf_u`, W=2 µm, L=280 µm, area=560 µm²): `sigma_e1 = 1.5/23.66 = 0.0634 %`

**Sensitivity** (from `design/bandgap_operating_point.md` §1's
`Vref = VEB(Q3) + I·R1` with `I = ΔVBE(I)/R2` set independently of R1): an
independent relative error in either resistor shifts the output branch's
`I·R1` term by the same magnitude, `R1·I = 50334.7 Ω × 10.06 µA = 0.506 V`
(nominal).

```
sigma_Vref_R = 0.506 V * sqrt(0.000634^2 + 0.0025^2)
             = 0.506 V * 0.00258 = 1.31 mV   (3-sigma = 3.92 mV)
```

### 2.6 PNP mismatch (measured, #4 data)

`design/device-characterization.md` §5, record `20260731-040850-187a336`:
the area-ratioed `pnp_05p00x05p00`/`pnp_10p00x10p00` pair's own `ΔVBE`
mismatch at 10 µA, 27 °C: **3σ = 0.128 mV**. Per Section 2.4 this enters
`Vref` through the same sensitivity as the amplifier offset:

```
3-sigma_Vref_PNP = 0.128 mV * 16.129 mV/mV = 2.06 mV
```

### 2.7 Budget table (RSS, untrimmed, 3σ)

| Line | 3σ contribution to Vref (#10) | 3σ contribution to Vref (**#42**) | Source |
|---|---|---|---|
| Amplifier offset, random (M1/M2 + M3/M4-referred) | 25.06 mV | **13.06 mV** | Sections 2.2, 2.4 — analytic scaling of record `20260731-031718-8fb0ea6`, sensitivity from record `20260801-073817-a7fd16a` |
| Resistor mismatch (R1, R2, independent) | 3.92 mV | 3.92 mV | Section 2.5 — **assumed** coefficient, PDK cannot verify |
| PNP mismatch (Q1/Q2 pair) | 2.06 mV | 2.06 mV | Section 2.6 — record `20260731-040850-187a336` |
| **RSS of random terms** | 25.45 mV | **13.79 mV** | `sqrt(13.06^2 + 3.92^2 + 2.06^2)` |
| Amplifier offset, systematic (reserve, unverified) | +2.00 mV | +2.00 mV | Section 2.3 — placeholder pending #16 layout |
| **Total (RSS random + systematic reserve)** | ~27.5 mV | **15.79 mV** | |
| **Ratified untrimmed target (3σ)** | 24.0 mV (±2 % of 1.20 V) | 24.0 mV | `README.md`, DR-0003 |
| **Margin** | −15 % (over) | **+34 % (66 % of budget used)** | |

**The budget closes.** The amplifier's own random offset is still the
largest single term (13.06 of 13.79 mV RSS), so it remains where any
further accuracy work should go; but it is now 54 % of the target rather
than 104 % of it.

No allocation above was loosened to make the table sum: every line except
the amplifier's own is numerically identical to #10's, and the amplifier
line moved because the amplifier changed. See Section 5 for what still does
not close.

### 2.8 Circuit-level Monte Carlo cross-check (#13's bench)

The analytic RSS above is a deterministic allocation. `sim/mc-untrimmed/`
(#13, `run_mc_untrimmed.py`) measures the same quantity the other way — a
live N=300 mismatch Monte Carlo on the whole `bandgap_top` netlist — and
its existing record `20260801-033856-7c40876` carries an explicit
"provisional-amp caveat": it was minted against **#8's** unbudgeted amp
(neither #10's nor #42's) and reads 3σ = 5.5–5.8 % of 1.20 V. Because that
bench takes `design/netlist/bandgap_top.spice` directly as its DUT, it
re-runs against this amp with no bench edit; see
`sim/mc-untrimmed/records/` for the record this issue minted and the
superseding note it carries. The MC result is the authority on the
*combined* mismatch distribution; this section's RSS is the allocation that
says where the spread comes from and which device to spend area on.

## 3. PSRR contribution

### 3.1 Method

Closed-loop AC transfer `H(f) = Vref(f)/Vdd(f)` with a unit AC stimulus on
the supply source (`vsup ... ac 1`), full closed loop (real `bandgap_amp`,
final sizing, with `bandgap_startup` instantiated), swept 0.01 Hz – 1 kHz.
`PSRR_dB(f) = -20*log10(|H(f)|)`. This is a genuinely single-port
small-signal measurement — no loop break, no injection-point ambiguity.

- **Testbench**: `sim/amp-psrr/testbench/tb_psrr.spice`
- **Record (#42 amp)**: [`20260801-073633-a7fd16a`](../sim/amp-psrr/records/20260801-073633-a7fd16a.md)
- **Paired baseline (#10's amp, same bench)**: [`20260801-073426-a7fd16a`](../sim/amp-psrr/records/20260801-073426-a7fd16a.md)

### 3.2 Result

| | #10 amp (same bench) | **#42 amp** |
|---|---|---|
| Worst of the 81-point PVT grid | 31.87 dB (`sf`/125 °C/3.63 V) | **77.61 dB** (`res_ss`/125 °C/3.63 V) |
| Best of the grid | 87.25 dB (`fs`/−40 °C/2.97 V) | 105.87 dB (`ff`/27 °C/3.30 V) |
| Corners meeting the ratified >60 dB | 19 / 81 | **81 / 81** |
| Overall | **FAIL** | **PASS**, worst-corner margin +17.6 dB |

The baseline column reproduces #10's own record (31.9 dB at the same
`sf`/125 °C/3.63 V corner) to two decimal places, which is what makes the
+45.7 dB worst-corner delta a measurement rather than an assertion: the
testbench was rebuilt in #42 (Section 3.5), and running #10's amp through
the rebuilt bench lands on #10's published number.

### 3.3 Root cause, and why the amp is no longer the limiter

`sim/core-psrr-ideal-amp/` (#10's diagnostic — `bandgap_amp` replaced by an
idealized infinite-gain, zero-supply-sensitivity servo, record
`20260801-033034-c26da47`) put `bandgap_core`'s own cascoded output stage
at 80–99 dB over the large majority of the grid. #10 concluded from that
the amp, not the core, was the bottleneck; #42's result is consistent —
having removed ~46 dB of amp contribution, the whole loop now measures
77.6–105.9 dB, i.e. it has moved into the band the core-only diagnostic
predicted. **That diagnostic was deliberately not re-run in #42**: it does
not instantiate `bandgap_amp` at all, so this issue's change cannot affect
it, and re-running it would mint a record identical to #10's for no
information. (Its own known artifact — three near-0 dB outlier corners from
the idealized amp's unbounded bandwidth — is unchanged and still not a
property of the core; the real-amp record shows no such collapse anywhere.)

### 3.4 Why #10's cascode attempt failed, in closed form

#10 recorded, as a negative result, that cascoding the M3/M4 *mirror load*
made PSRR **worse** (~38–46 dB spot-checked, vs ~51 dB nominal for the
plain mirror), and attributed it to the cascode-bias node's own supply
tracking. Section 2.1's derivation explains it exactly:
`(1 − s)/A = 1/(gm1 · Ro,nmos)`. The PMOS load's output resistance does not
appear. Cascoding it therefore cannot improve the amp's supply-referred
input error at all — while the extra bias generator it requires can, and
did, inject a new supply-coupled term. #42 keeps a PMOS cascode (for the
*offset* reason in Section 2.1, item 2, and with a bias generator whose
current is set by a ground-referenced sink rather than by a device whose
`Vds` rides the supply), and adds the NMOS cascode that actually moves the
PSRR term.

### 3.5 Testbench changes in #42 (comparability note)

The three `sim/amp-*` benches were rebuilt, for reasons that are
independent of this issue's design change but change what the records mean:

- **#10's `.ic` seed was doing nothing.** ngspice honours `.ic` in
  transient analysis, not in the DC solve that `.op`/`.ac` performs. #10's
  benches converged on the intended operating point because the solver
  happened to, not because the seed steered it — and a bench whose answer
  depends on which of two physical DC solutions the solver picks is not
  evidence. The benches now instantiate `bandgap_startup` (#11), which
  removes the degenerate solution *physically*, and carry a `.nodeset` as a
  solver hint only.
- **The embedded `bandgap_core` copy was pre-#11** (7 pins, no `casc`
  port), so the benches no longer described the shipping block.
- **`bandgap_amp` now comes from a DUT netlist** (`sim/dut/bandgap_amp.spice`,
  generated from `design/netlist/bandgap_amp.spice`) rather than being
  pasted into each fragment, which is what allows the paired baseline runs
  above: `--dut sim/dut/frozen/bandgap_amp-20260801-issue10.spice` re-runs
  the new bench against #10's amp, and the record's **Netlist provenance**
  field names which amp it measured, by path and sha256.

Because of this, #10's records and #42's are **not byte-comparable**; every
before/after number quoted in this document comes from the paired
same-bench runs instead. The one place where that could have hidden a
change — PSRR — is directly checked above: same bench, #10's amp, #10's
published worst-corner number.

## 4. Loop stability

### 4.1 Method and sign convention

The servo loop closes through exactly one wire: the amplifier's `out` pin
directly drives the core's `fb` net (the four mirror gates). Breaking that
wire and inserting an ideal AC test source (`B = A + vt`, `vt` = 1∠0°,
DC = 0, so the DC operating point is identical to the closed loop) and
measuring `x = V(B)/vt` gives `T = 1 − 1/x`.

**Correction to #10's methodology claim.** #10's testbench header asserted
this single injection is *exact* for a one-wire break. It is not. Writing
`A = G(B)` treats the forward path's output as an ideal voltage source, so
the result is the true return ratio only while the forward path's output
impedance at `out` is small against the load impedance the core's mirror
gates present at `fb`. At DC and through the ratified band that holds. At
high frequency both nodes become capacitive and comparable, and the
measured `T` tends to the pure capacitive-divider ratio `−C(fb)/C(out)` —
which is *exactly* the frequency-independent high-frequency plateau #10
attributed to "a parasitic Cgd feedthrough path around the single gain
stage". It is a measurement artifact of voltage-only injection, not a gain
path. Middlebrook/Tian dual injection is what removes it; #42 deliberately
does **not** switch to it, because changing the measurement would break
comparability with #10's records, and because the plateau sits far above
the ratified band and the AC verdict is cross-checked in transient
(Section 4.6).

**Critical point.** Because this loop's characteristic equation is
`1 − T = 0` (a `T = +1` danger point), not the classic op-amp `1 + T = 0`
form, the Nyquist danger point for this `T` is magnitude 1 **and** phase 0°
(mod 360°) — not 180°.

### 4.2 Stability criterion #1 (#10's, unchanged)

Phase margin, defined as the angular distance of `T`'s phase — evaluated at
the frequency of **global minimum** `|T(f)|` over 0.1 Hz – 2 GHz — from 0°
(mod 360°), **must stay ≥45° at every PVT corner**. 45° is a standard
minimum-PM bar; it is not a ratified spec line (the ratified spec has no
stability-margin row), so it is stated here explicitly rather than imported
silently. #42 gates this criterion unchanged.

### 4.3 Why criterion #1 alone is not sufficient (#42 finding)

Criterion #1 inspects the phase at **one** frequency. It is structurally
blind to an encirclement of the `+1` critical point that occurs anywhere
else on the locus — and the extra loop gain a cascoded amp brings makes
that failure mode reachable. Concretely, during this issue's design work an
intermediate (uncompensated) revision of the telescopic amp measured:

- `pm_deg` = **179.8°** at every one of the 81 PVT corners — a comfortable
  "pass" by criterion #1, nearly 4× the bar;
- and, at the same corners, a Nyquist locus crossing the **positive real
  axis** at `|T|` = **+33 dB**, i.e. passing to the right of `+1` and
  enclosing it;
- and a startup transient that **oscillated with ~2.4 V of ripple** and
  never settled.

Criterion #1 called that circuit stable at every corner. It is not.

### 4.4 Stability criterion #2 (added in #42; strictly stronger)

The measurement scans the whole AC sweep for crossings of the positive real
axis (`imag(T)` changing sign with `real(T) > 0`) and reports the largest
`|T|` in dB at any such crossing, as `gm_crit_db`. For `1 − T = 0` the
locus must cross to the **left** of `+1`, so:

```
gm_crit_db < 0 dB          (and -999 dB is the sentinel for
                            "the locus never reaches phase 0 mod 360")
```

This is the classical gain margin, expressed for this topology's own
critical point. **Nothing was relaxed**: criterion #1 is retained and still
gated at ≥45°; criterion #2 is an additional gate that #10's amp also
passes (trivially — its locus never reaches phase 0, so `gm_crit_db` reads
the −999 sentinel at all 81 corners, confirmed by the paired baseline run).

### 4.5 Result

- **Testbench**: `sim/amp-loop-stability/testbench/tb_loop_stability.spice`
- **Record (#42 amp)**: [`20260801-073725-a7fd16a`](../sim/amp-loop-stability/records/20260801-073725-a7fd16a.md)
- **Paired baseline (#10's amp, same bench)**: [`20260801-073511-a7fd16a`](../sim/amp-loop-stability/records/20260801-073511-a7fd16a.md)

| | #10 amp (same bench) | **#42 amp** | Criterion |
|---|---|---|---|
| DC loop gain | 37.75–42.94 dB | **89.13–106.06 dB** | ≥10 dB sanity floor |
| Phase margin, worst corner | 119.1° (`res_ss`/−40 °C/3.63 V) | **177.8°** (`ff`/125 °C/3.63 V) | ≥45° |
| Nyquist gain margin, worst corner | −999 dB (no crossing) | **−7.007 dB** (`ff`/−40 °C/2.97 V) | <0 dB |
| Overall | PASS | **PASS**, 81/81 | |

**No new violation versus the #10 baseline**: both criteria pass at every
one of the 81 corners, phase margin is *higher* than the baseline at every
corner, and the added Nyquist gain margin holds ≥7 dB of margin at its
worst corner.

### 4.6 Transient cross-check

Because the AC verdict rests on a loop-break measurement with a known
high-frequency artifact (Section 4.1), it is cross-checked against a
physical, full-PVT transient: `sim/startup/` ramps `vdd` from 0 and
measures settling to within ±1 % of the final value, at all 81 points. An
encircling loop shows up there as ringing or a wrong settled value, and did
— that is how the uncompensated revision in Section 4.3 was caught. With
`CC` sized, record
[`20260801-073947-a7fd16a`](../sim/startup/records/20260801-073947-a7fd16a.md)
settles at every corner, `startup_time` 17.2–37.0 µs against the ratified
1 ms bound (~27× margin at the worst corner), `vref_final` 1.217–1.260 V.

## 5. What still does not close (no spec relaxation)

Per CLAUDE.md's "agents do not relax the ratified spec to make results
pass", one ratified row is reported here as a miss rather than fudged, and
this issue makes it slightly worse:

**Quiescent current.** Ratified `< 50 µA`, binding at `ff`/125 °C/3.63 V.

| | before #42 | after #42 |
|---|---|---|
| `tt`/27 °C/3.30 V | 46.78 µA | **48.24 µA** |
| `ff`/125 °C/3.63 V (binding) | 77.5 µA | **80.5 µA** |

This row was **already failing by ~55 %** at the binding corner before this
issue — `design/bandgap_operating_point.md` §4.3 records it as an open
core/cascode-sizing item that neither #10 nor #11 closed, and the amplifier
is not where the current goes (the four core branches at ~10 µA each are).
#42 adds ~1.5 µA at nominal and ~3.0 µA at the binding corner: the two new
bias branches (0.86 µA nominal) plus a small tail/core shift. It does not
change the row's pass/fail state, but it is a regression on a failing line
and is recorded as such rather than buried.

**The concrete lever, if a later issue wants it back**: MB1 (W=5 µm/L=50 µm)
sets the `ncasc` branch at 0.725 µA, the single largest addition. Narrowing
it to W=2 µm would recover ≈0.45 µA at the cost of a lower `ncasc` and some
PSRR margin — of which Section 3.2 leaves 17.6 dB at the worst corner. That
trade was not taken here because closing the Iq row needs the
core/cascode sizing pass §4.3 calls for (tens of µA), not 0.45 µA of
amplifier bias, and spending PSRR margin for 0.6 % of a 55 % overshoot is a
bad trade to make unilaterally.

**Explicitly not decided here**: the accuracy/trim split. Section 2.7
closes the *untrimmed* budget against the ratified target, which removes
the reason #10 gave for handing a shortfall to #14; #14 remains free to
size trim range against the full ratified basis (mismatch MC + process
corners together — Section 2.8), which is a wider basis than this
document's allocation and is #14's call, not this one's.

## 6. Summary of acceptance criteria

| Criterion | Status |
|---|---|
| Amp redesigned/recompensated to close both #10 shortfalls simultaneously | **Done** — telescopic cascode + dominant-pole compensation, Section 2.1 |
| Loop stability re-verified full PVT, PM ≥45°, no new violation vs #10 | **PASS** 81/81, Section 4.5 (and a second, stronger Nyquist criterion added, Section 4.4) |
| Offset sensitivity re-verified; updated RSS budget vs ±2 % (3σ) untrimmed | **PASS** — 15.79 mV vs 24.0 mV target, Section 2.7; sensitivity unchanged at 16.13 mV/mV, Section 2.4 |
| PSRR re-verified full PVT vs >60 dB DC–1 kHz | **PASS** 81/81, worst corner 77.61 dB, Section 3.2 |
| `design/bandgap_error_budget.md` and `design/bandgap_operating_point.md` updated | Done — this document and `design/bandgap_operating_point.md` §2/§4.1 |
| New `sim/` records appended, not edited | Done — 10 new records (3 amp-* × 2 amps, 4 startup re-runs), no existing record touched |
| No spec relaxation; residual gaps reported explicitly | Done — Section 5 (Iq row, a pre-existing failure this issue makes ~3 µA worse) |
| Accuracy/trim split not decided here | Done — Section 5's closing note |
