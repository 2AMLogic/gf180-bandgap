# Offset/mismatch budget: error amplifier and core mirror (issues #10, #42, #55, #61, #96, #147)

This document allocates the ratified untrimmed output-accuracy target
(`README.md` "Target specification": **1.20 V ±2 % untrimmed, 3σ, mismatch
MC N≥300 + process corners, −40…125 °C** — [DR-0003](../spec/decision-records/0003-target-spec-ratification.md))
across the amplifier's own input-referred offset (systematic + random),
**`bandgap_core`'s current-mirror/cascode mismatch (added in #55)**,
resistor mismatch and PNP mismatch, each derived from this topology's own
measured sensitivity (∂Vref/∂x), not assumed evenly. It also records the
amplifier sizing and topology decision, the loop's stability criteria and
PVT verification, and its PSRR contribution.

> **Section numbering.** `sim/` records are append-only and cite this
> document's Sec 2.7 (budget table) and Sec 2.8 (Monte Carlo cross-check)
> by number, so #55's new derivation is inserted as **Sec 2.6a** rather
> than renumbering those. Same lettered-insert convention
> `design/bandgap_operating_point.md` already uses (§1a, §3a).

**Bottom line, stated up front.** #10 sized a 5-transistor single-stage OTA
against this budget and found two ratified-spec lines it could not meet —
the untrimmed accuracy budget came in at ~106–115 % of target, and PSRR fell
5–28 dB short of the >60 dB DC–1 kHz row — and escalated both (its
Section 5) rather than relaxing anything. **#42 is that escalation's
answer**: `bandgap_amp` is now a telescopic-cascode OTA with explicit
dominant-pole compensation (Section 2.1). That fixed PSRR outright and cut
the amplifier's own offset line by 2×, but it left the *whole-circuit*
untrimmed accuracy row failing, because this document had never allocated
`bandgap_core`'s own four-leg PMOS mirror — 40 µm² of gate area per device,
provisional since #8. **#55 is that residual's answer**: Section 2.6a
derives, measures and allocates the core-mirror line, and the mirror is
resized to 360 µm² against it.

| Line | #10 (5T OTA) | #42 (telescopic cascode) | **#55 (+ core mirror sized)** | Ratified target |
|---|---|---|---|---|
| Untrimmed accuracy, RSS 3σ at Vref, **amp + R + PNP only** | 25.45 mV | 13.79 mV | 13.79 mV | — (partial) |
| Untrimmed accuracy, RSS 3σ at Vref, **all allocated terms** | 31.80 mV random / 33.80 with reserve | 23.53 mV random / 25.53 with reserve | **15.19 mV random / 17.19 mV with reserve** | ≤ 24.0 mV (±2 % of 1.20 V) |
| Same quantity, measured (`sim/mc-untrimmed/`, N=300, all devices, −40/27/125 °C) | — | 23.62 / 23.77 / 24.27 mV | **14.89 / 15.12 / 15.82 mV** | ≤ 24.0 mV |
| PSRR, worst of 81 PVT points | 31.87 dB (19/81 corners pass) | 77.61 dB (81/81) | **86.98 dB (81/81)** | > 60 dB DC–1 kHz |
| Loop phase margin, worst corner | 119.1° | 177.8° | **108.9°** | ≥ 45° (this design's own criterion) |
| Loop Nyquist gain margin, worst corner | no critical-axis crossing | −7.0 dB | **no critical-axis crossing** | < 0 dB (added in #42, Section 4.4) |
| Quiescent current, `ff`/125 °C/3.63 V | 77.5 µA | 80.5 µA | 65.71 µA (#55) → **34.01 µA (#61)** | < 50 µA — **passes as of #61**, Section 5 |

The **all allocated terms** row is the honest one, and it is new in #55: the
#10 and #42 entries are those issues' own RSS re-computed with Section 2.6a's
core-mirror line included at the sizing each of them shipped (both left it at
40 µm²). Read that way, the earlier revisions of this document were not
"closing" — they were omitting a term, which Section 2.8's Monte Carlo
cross-check said so at the time and now says quantitatively.

**#147 closes the last one that did not: the *combined* untrimmed-accuracy
verdict.** Every per-bench row passed as of #96, but the ratified
Output-reference row is judged on both legs together (mismatch MC grafted
onto the process corners, `sim/suite/combined.py`), and that verdict read
**FAIL, 42 of 81 corners**. It is an error-budget problem, not a single bad
leg: 20.43 mV of deterministic corner spread plus 2 × 16.13 mV of grafted
mismatch is 52.7 mV against a 48 mV window, with all of the overflow on the
low edge because #96's TC-null leaves `Vref` centred 7.5 mV low.
**Section 5c** derives the two-lever fix (constant-`W/L` area on the
amplifier's input pair and the core mirror, plus an `R1` re-centring paid for
out of temperature-coefficient margin), the stability wall that bounds how
much area the amplifier may take, and the measured result: **PASS, 81/81,
worst margin +0.84 mV**.

| Line | post-#61/#96 | **#147** | Ratified target |
|---|---|---|---|
| Combined untrimmed-accuracy verdict | FAIL, 42/81 corners | **PASS, 81/81** | every corner inside 1.176–1.224 V |
| Untrimmed accuracy, measured 3σ (`mm_all`, −40/27/125 °C) | 15.56 / 15.70 / 16.13 mV | **11.85 / 12.03 / 12.54 mV** | ≤ 24.0 mV |
| Untrimmed accuracy, allocated RSS (random) | 16.26 mV | **12.19 mV** | ≤ 24.0 mV |
| Temperature coefficient, worst of 81 | 29.84 ppm/°C | **46.41 ppm/°C** (margin deliberately spent, Section 5c) | ≤ 50 ppm/°C |
| Loop phase margin / Nyquist margin | 97.3° / no crossing | **160.9° / no crossing** | ≥45° / <0 dB |
| PSRR, worst of 81 | 74.22 dB | **77.61 dB** | > 60 dB |
| Quiescent current, `ff`/125 °C/3.63 V | 34.01 µA | **34.02 µA** | < 50 µA |

**Every ratified row this document is responsible for now passes.** Quiescent
current failed before #42, #42 made it ~3 µA worse, #55's core resize took the
largest single bite any issue had taken out of it without closing it, and
**#61 closes it** by co-scaling `R1`/`R2`/the trim network by `k = 2` rather
than by any further mirror change — Section 5 states the full history and the
closed-form reason why *mirror sizing* could not have closed it on its own.

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
- **`bandgap_core`'s own mirror/cascode mismatch IS allocated here as of
  #55** (Section 2.6a) — it was not, in #10's or #42's version of this
  document, and Section 2.8's Monte Carlo cross-check was the thing that
  said so. Its sensitivity is measured on `bandgap_core`'s own netlist
  (`sim/core-mirror-sensitivity/`) rather than assumed, and the devices are
  sized against the resulting area budget.
- **The untrimmed *mean* is still not this document's subject.** This
  budget allocates the *spread* (3σ) about whatever mean the first-pass
  R1/R2 sizing produces. The mean sitting ~1.7–4 % high of 1.200 V is R1/R2
  sizing plus the 1-point trim's job, not a mismatch term — Section 2.8's
  window-check note, and `design/bandgap_trim_network.md`.
- **The accuracy/trim split is not this document's decision.** This budget
  closes its own allocation untrimmed against the ratified target; it does
  not scope trim range.

## 2. Amplifier offset budget

### 2.1 Topology and sizing decision (#42)

**Topology changed.** #8 entered a 5-transistor single-stage OTA; #10 kept
it and resized it; #42 replaces it with a **telescopic cascode with an
explicit dominant-pole compensation capacitor**
(`design/bandgap_amp.sch`):

| Device | Type | #10 sizing | #42 sizing | Role |
|---|---|---|---|---|
| M1, M2 | `nfet_03v3` | W=100 µm L=4 µm nf=2 | **W=200 µm L=4 µm nf=8** | input pair (in_p = core `sns2`, in_n = core `sns1`) |
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
applies directly with no extrapolation in L. Fingering at W=200 µm is not a
layout preference: gf180mcu's `nfet_03v3`/`pfet_03v3` models are
width-binned with a 100 µm top bin edge per finger, so 200 µm needs ≥2
fingers. #42 originally declared `nf=4` (50 µm/finger); #65 found the
schematic had never been updated to the `nf=8` (25 µm/finger) 8-way
common-centroid array `layout/bandgap_top/plan.py` always drew for this
pair, and corrected it. Either finger count keeps each finger inside the
*same* bin #10's 100 µm/nf=2 device used, so no bin extrapolation is
introduced.

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

**Update (#147) — input pair 800 µm² → 1800 µm², mirror load unchanged.**
`M1`/`M2` go `200 µm/4 µm` → `300 µm/6 µm` (`nf` 8 → 12, 25 µm/finger held),
i.e. `W/L = 50` exactly preserved, so `Vov`, `gm`, `gm3/gm1` and every
saturation margin are unchanged by construction and only the Pelgrom area
term moves:

```
sigma_M1M2 = 4.91 * sqrt(2) / sqrt(1800) = 0.1637 mV   (was 0.2455 mV)
sigma_M3M4_referred                       = 0.1123 mV   (unchanged)
sigma_Vos_random = sqrt(0.1637^2 + 0.1123^2) = 0.1985 mV
3-sigma_Vos_random = 0.5955 mV
=> amplifier line at Vref = 0.5955 * 16.13 = 9.60 mV   (was 13.06 mV)
```

`M3`/`M4` were **deliberately left at 20 µm/16 µm**. Their gate node `nd1`
carries the mirror pole `gm3/(Cgs3+Cgs4)`, and Section 5c shows by
measurement that area there is bought straight out of the servo loop's
stability margin: 1.27× the mirror-load area already takes this design's own
phase-margin criterion from 83.7° to 4.2°. The input pair is bounded the
same way at `300 µm/6 µm`. Both bounds are measured on
`sim/amp-loop-stability/`, not assumed.

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

### 2.6a Core mirror/cascode mismatch (issue #55)

`bandgap_core`'s four PMOS legs (`M1`…`M4`, each with a cascode `MC1`…`MC4`
above it) all share one gate node, `fb` — the amplifier's output. Local
`Vth`/current-factor mismatch on those devices is therefore an
**independent series gate offset per device**, and it is *not* an amplifier
offset: it does not act at the amplifier's input, it acts on four separate
branch currents. This section derives that mechanism in closed form,
measures it on this circuit's own netlist, sizes the devices against the
result, and hands Section 2.7 a number.

#### The mechanism, in closed form

Write `δ1`…`δ4` for the four devices' independent gate-referred offsets and
`g ≡ gm/I` for the mirror PMOS's transconductance efficiency, so a device
whose gate is `δ` more positive carries `I·(1 − g·δ)`. Let `Δfb` be the
shift the loop applies to `fb` in response. The servo constraint is
`VEB(Q1, I1) = I2·R2 + VEB(Q2, I2)`, i.e.

```
VT * ln(A * I1 / I2) = I2 * R2 ,    A = 3.634 (effective PNP area ratio)
```

Linearising about the operating point, with `I0·R2 = ΔVBE0` by definition of
the design point, gives a single ratio

```
rho = VT / (VT + dVBE0)        = 25.85 / (25.85 + 33.374) = 0.4365  (27 degC)
Dfb = (rho*d1 - d2) / (1 - rho)
```

and the output branch is `Vref = VEB(Q3, I3) + I3·R1`, so

```
dVref = -K * g * (Dfb + d3),   K = VT + I0*R1 = 0.0259 + 0.506 = 0.5319 V
```

Substituting `Δfb` gives the four per-device sensitivities:

| device | leg | closed form | predicted (27 °C) | **measured** |
|---|---|---|---|---|
| `M1` | servoed, `sns1` (Q1) | `−K·g·ρ/(1−ρ)` | −2.83 | **−2.875** |
| `M2` | servoed, `sns2` (Q2/R2) | `+K·g/(1−ρ)` | +6.47 | **+6.522** |
| `M3` | unservoed, `vref` | `−K·g` | −3.65 | **−3.647** |
| `M4` | unservoed, `ibias` | `0` | 0 | **−7.6e−5** |
| | | **sum (servo common-mode null)** | **0** | **−2.3e−4** |

with `g = 6.86 V⁻¹` back-solved from the `M3` row (`K·g = 3.647`) and used
unchanged for the other three. Closed form and measurement agree to **1.8 %
or better on every leg**, which is the point of writing both down: the
sensitivities are not a fit.

Reading the table physically, and answering the "servoed vs unservoed legs
contribute differently" question directly:

- The **unservoed `vref` leg (`M3`)** is the simple one: its mismatch
  steers the output branch current straight into `R1` with no loop
  intervention at all, `∂Vref/∂δ3 = −(VT + I·R1)·gm/I`.
- The **servoed legs (`M1`, `M2`) are the *larger* contributors**, not the
  smaller ones, which is the counter-intuitive part. The servo does not
  reject their mismatch — it *cannot*, because forcing `sns1 = sns2` with a
  mismatched pair of legs means settling on a different `fb`, and `fb` is
  the gate of the output leg too. The `1/(1−ρ)` factor is that
  amplification: `ρ` is set by the ratio of the thermal voltage to the
  design ΔVBE, so a Brokaw cell with a small ΔVBE is *more* sensitive to
  its own mirror mismatch, exactly as it is to amplifier offset.
- The **`ibias` leg (`M4`) contributes nothing measurable** (−7.6e−5 V/V,
  five orders below `M3`). `M4`/`MC4` feed only the diode-connected `M5`
  that generates the `ibias` bias rail; they never touch `sns1`, `sns2` or
  `vref`. This is a *measured* result, not an assumption, and it is what
  licenses the quiescent-current lever below.
- The **sum being zero** is the servo's common-mode null: a `δ` common to
  all four gates is electrically identical to shifting `fb` by `−δ`, which
  the loop absorbs. The bench checks it (`dvref_dvos_m_sum`, bounded to
  ±0.05 V/V) so the four coefficients are known to be an orthogonal
  decomposition before they are RSSed — an assumption a budget of this kind
  usually leaves silent.

Cascode devices are two orders of magnitude weaker, for the reason
Section 2.2 gives for the amplifier's own cascodes: `MC1`…`MC4` are
common-gate stages carrying whatever current the device below them sets, so
their `ΔVgs` only perturbs the mirror-drain node, which then acts back
through the mirror device's own (cascoded, hence very large) output
impedance. Measured on the `vref` leg: `∂Vref/∂δ(MC3) = −0.0133 V/V`, i.e.
**274× smaller than `M3`'s**. Bounding all four cascodes at the
*worst-corner* figure (−0.0213 V/V, `res_ss`/−40 °C/2.97 V) their RSS
contribution is **< 0.04 mV (3σ)** at 360 µm² and < 0.11 mV at the old
40 µm² — carried in Section 2.7's table as a line rather than dropped, but
it never matters.

#### Mismatch magnitude and the area budget

Same Pelgrom law, same source, same method as Section 2.2 — the PDK model's
own `p_sqrtarea = sqrt(Leff*Weff)` scaling of both mismatch variances, with
`A_pair(pfet_03v3) = 5.02 mV·µm` from record `20260731-031718-8fb0ea6`. Here
the four devices are *independent* rather than a pair, so the per-device
sigma is `A_pair/√(W·L)` (no `√2`; the `√2` in Section 2.2 is what turns a
per-device sigma into a pair's ΔVgs sigma, and this budget RSSes the four
devices individually instead):

```
sigma(Vref) = A_pair / sqrt(W*L) * sqrt(S1^2 + S2^2 + S3^2 + S4^2)
            = A_pair / sqrt(W*L) * 8.007
```

where `8.007` is the RSS of the four measured coefficients at nominal. That
coefficient is itself checked over the grid rather than assumed constant:
across all 81 PVT points it ranges **7.121** (`res_ff`/125 °C/2.97 V) to
**8.771** (`res_ss`/−40 °C/3.63 V), mean 7.972. The worst-corner column
below uses 8.771, so the budget is a margin budget over the grid, not a
nominal-corner number.

**Extrapolation honesty.** `A_pair` was characterized at a `10/4` geometry
and is applied here at `60/6` — an extrapolation in **both** W and L. The W
half is first-principles (the PDK's own variance scaling is
`1/sqrt(Leff*Weff)` with no W-dependent coefficient, verified from the model
source in Section 2.2). The L half is the same extrapolation Section 2.2
already makes for the amplifier's `20/16` mirror load, and it is the weaker
of the two assumptions in this document — weaker than the sensitivity
numbers, which are measured. It is *checked*, not assumed, by Section 2.8's
circuit-level Monte Carlo, which draws its mismatch from the PDK models
directly at the drawn geometry: if the `A_pair` extrapolation were wrong,
the measured MC spread would not track this allocation. At the old 40 µm²
sizing it tracked to 3 %.

| drawn size | gate area | σ(δ) per device | 3σ(Vref), nominal | **3σ(Vref), worst corner** |
|---|---|---|---|---|
| W=20 µm, L=2 µm (#8's, provisional) | 40 µm² | 0.794 mV | 19.07 mV | **20.89 mV** |
| W=40 µm, L=4 µm | 160 µm² | 0.397 mV | 9.53 mV | 10.44 mV |
| W=60 µm, L=6 µm (#55) | 360 µm² | 0.265 mV | 6.36 mV | 6.96 mV |
| **W=85 µm, L=8.5 µm (#147, adopted)** | **722.5 µm²** | **0.187 mV** | **4.49 mV** | **4.92 mV** |

> **The two right-hand columns are stated at #55's `8.007` coefficient and
> are stale as of #61 — see the correction immediately below.** The
> geometry column is not: `σ(δ)` is a pure Pelgrom-area quantity.

**Coefficient correction (#147): `8.007` is a pre-#61 number.** The RSS
coefficient above was measured at #55's design current. #61 then halved that
current (`R1`/`R2` co-scale, `k = 2`), and `g ≡ gm/I` at the mirror devices'
fixed `W/L` rises as the current falls — the same `gm/Id` effect #61's own
Section 5a flagged and did not re-derive. Re-measured on
`sim/core-mirror-sensitivity/` against the **current** design current, at
both the pre- and post-#147 mirror geometry (81 points each):

| coefficient | #55-era (`8.007` basis) | post-#61, 360 µm² (`origin/main`) | post-#61, **722.5 µm² (#147)** |
|---|---|---|---|
| `∂Vref/∂δ1` (`M1`, servoed) | −2.875 | −3.885 | **−3.870** |
| `∂Vref/∂δ2` (`M2`, servoed) | +6.522 | +8.843 | **+8.808** |
| `∂Vref/∂δ3` (`M3`, output leg) | −3.647 | −4.958 | **−4.939** |
| `∂Vref/∂δ4` (`M4`, bias leg) | −7.6e−5 | −2.1e−4 | **−1.4e−4** |
| **RSS** | **8.007** | **10.857** | **10.816** |

Two things this settles. First, the coefficient is a property of the
*current*, not of the geometry: it is unchanged (0.4 %) across a 2× area
step, which is exactly what the constant-`W/L` resize is supposed to
guarantee and is measured here rather than asserted. Second, the correct
core-mirror line at #61's current is **8.62 mV** at 360 µm²
(`5.02/√360 × 10.857`, 3σ), not 6.36 mV — and **6.06 mV** at #147's
722.5 µm². The 2.56 mV that resize buys is what makes Section 5c's budget
close; #55's own stopping rule ("stop where the mirror is no longer the
largest term") was evaluated against an amplifier line that #147 has since
halved, which is precisely the condition under which the next notch becomes
worth buying.

**The 19.07 mV row is why this section exists.** Section 2.8's #42 run
subtracted the amplifier budget out of the measured Monte Carlo in
quadrature and got "~19.4 mV unallocated"; this closed-form line, derived
independently from the PDK's Pelgrom coefficient and this circuit's own
measured sensitivities, lands on **19.07 mV** for exactly the devices that
were left out. The two agree to 1.7 %. That is the identification, and it is
what makes the sizing decision below a budget rather than a guess.

**Why 360 µm², and not the smallest area that closes.** Two criteria, in
order:

1. *Necessary*: the allocation must close. Section 2.7's other random terms
   RSS to 13.79 mV and the systematic reserve takes 2.00 mV off the 24.0 mV
   target, so the core-mirror line may be at most
   `sqrt(22.0² − 13.79²) = 17.1 mV`, i.e. **W·L ≥ 50 µm²**. Meeting only
   this would be meaningless: 40 µm² already measures 23.6–24.3 mV on the
   real Monte Carlo, so "closing on paper" at 50 µm² leaves no margin
   against the very cross-check that found the problem.
2. *Binding*: size until the core mirror is **no longer the largest term**,
   and stop where further area stops buying anything. Half the amplifier's
   line (13.06 mV) is the criterion — `X ≤ 6.53 mV` ⇒ **W·L ≥ 341 µm²**.
   Rounding up to a drawn geometry that holds `W/L = 10` exactly gives
   **W = 60 µm, L = 6 µm (360 µm²)**, for `X = 6.36 mV` — 49 % of the
   amplifier's line and 27 % of the total RSS.

Doubling again (720 µm² per device, +2160 µm² of gate area) would move the
total RSS from 15.19 mV only to 14.28 mV. That is the diminishing return
that sets the stopping point: past ~360 µm² this design is amplifier-limited
again, and area spent here buys ~0.9 mV.

**Cost.** Gate area goes from `8 × 40 = 320 µm²` to
`6 × 360 + 2 × 45 = 2250 µm²`, i.e. **+1930 µm²**, or ≈ 3.9 % of the
ratified `< 0.05 mm²` area row before layout overhead. `W/L` is held at 10
for `M1`–`M3`/`MC1`–`MC3`, so `Vov` — and therefore every saturation
margin in the stack — is unchanged **by construction**, not by luck:
`Id = ½·k·(W/L)·Vov²` at the same shared `Vgs`. That is verified rather
than asserted, over the full 81-point PVT grid, below.

#### The `ibias` leg is a quiescent-current lever, and is used as one

Because `∂Vref/∂δ4` measures ~0, `M4`/`MC4` are the one part of the mirror
that is free to be sized for current instead of for matching. They are
scaled to **W = 7.5 µm at the same L = 6 µm**, i.e. `W/L = 1.25` against the
other legs' 10, so the leg carries **1/8 of the design current at the same
`Vov`** (same shared `Vgs`; `Id ∝ W/L`) and stays in saturation. `M5`, the
diode-connected NMOS that turns that current into the `ibias` rail, is
rescaled by the same 1/8 (`W = 20 µm → 2.5 µm`, `L = 2 µm` unchanged), which
holds `Vov(M5)` — and therefore the `ibias` node voltage itself — at its
pre-#55 value. Everything mirroring off `ibias` (`MNB`, the amplifier's tail
`M5`, the startup circuit's `MSENSE`) consequently keeps its own current
without being touched. `MCB`/`MNB` are left unresized for the same reason.

That is a design *claim*, so it is measured, not argued:
`sim/core-mirror-sensitivity/` reports `v_ibias_op` and the amplifier's own
tail current at all 81 PVT points alongside the sensitivities, and
Section 4/Section 3's loop and PSRR benches are re-run against the resized
core. See Section 5 for what this lever is and is not worth against the
ratified quiescent-current row.

#### Headroom, over the full grid rather than a spot-check

`design/bandgap_operating_point.md` §4.3's standing complaint about this
stage was that "7 spot-checks are not a margin budget". The same bench
therefore reports `Vds − Vdsat` for `M1`, `MC1`, `M4`, `MC4` and the
wide-swing cascode-bias device `MCB` at every one of the 81 PVT points,
gated at `≥ 0`. Results in Section 2.6b's record citation below.

### 2.6b Core-mirror record (#55)

- **Record**: [`20260801-132317-cfd0146`](../sim/core-mirror-sensitivity/records/20260801-132317-cfd0146.md)
  — 81/81 points, **PASS**, clean tree.
- **Bench**: `sim/core-mirror-sensitivity/testbench/tb_core_mirror_sensitivity.spice`
  (+ `tb.json`), five two-point DC linearisations plus a final unperturbed
  `.op` per point.

| measurement | min (corner) | max (corner) | mean | gate |
|---|---|---|---|---|
| `dvref_dvos_m_sns1` (`M1`, servoed) | −3.159 (`res_ss_-40c_3.63v`) | −2.552 (`res_ff_125c_2.97v`) | −2.861 | envelope |
| `dvref_dvos_m_servo` (`M2`, servoed) | 5.800 (`res_ff_125c_2.97v`) | 7.146 (`res_ss_-40c_3.63v`) | 6.494 | envelope |
| `dvref_dvos_m_vref` (`M3`, output leg) | −3.987 (`res_ss_-40c_3.63v`) | −3.248 (`res_ff_125c_2.97v`) | −3.633 | envelope |
| `dvref_dvos_m_ibias` (`M4`, bias leg) | −1.59e−4 | +1.45e−5 | −7.6e−5 | envelope |
| `dvref_dvos_mc_vref` (`MC3`, cascode) | −0.0213 | −0.00768 | −0.0134 | envelope |
| **`dvref_dvos_m_sum`** (common-mode null) | −1.23e−3 | −1.11e−4 | −3.3e−4 | **±0.05, PASS 81/81** |
| `margin_m1_mv` (`Vds − Vdsat`) | **+122.7** (`res_ss_-40c_2.97v`) | +251.1 | +176.0 | **≥ 0, PASS 81/81** |
| `margin_mc1_mv` | +1510.6 | +2384.8 | +1976.9 | ≥ 0, PASS 81/81 |
| `margin_m4_mv` | **+122.8** (`res_ss_-40c_2.97v`) | +251.0 | +176.0 | **≥ 0, PASS 81/81** |
| `margin_mc4_mv` | +1349.1 | +2447.2 | +1927.4 | ≥ 0, PASS 81/81 |
| `margin_mcb_mv` | +858.9 (`ff_125c_2.97v`) | +1147.5 | +1003.6 | ≥ 0, PASS 81/81 |
| `v_ibias_op` | 0.6154 V (`ff_125c_2.97v`) | 0.8985 V | 0.7554 V | envelope |
| `amp_tail_ua` | 1.414 µA (`ss_125c_2.97v`) | 4.196 µA | 2.613 µA | envelope |

Three things this table settles that were previously open:

1. **Headroom is now a grid result, not a spot-check.** The worst
   saturation margin anywhere on the 81-point grid is **+122.7 mV** on the
   mirror device `M1`, at `res_ss`/−40 °C/2.97 V — the PMOS-headroom worst
   case `design/device-characterization.md` §3 flags. `design/bandgap_operating_point.md`
   §4.3's "7 spot-checks are not a margin budget" objection is answered.
   `MCB`, deliberately left unresized, holds ≥ +858.9 mV.
2. **The `W/L = 10` invariance claim is confirmed empirically.** `M1`'s
   margin at nominal (`tt`/27 °C/3.30 V) is +169.3 mV against the +158 mV
   `design/bandgap_operating_point.md` §2 measured pre-resize at 40 µm² —
   i.e. the 9× area change moved the operating point by ~11 mV, not by the
   ~100s of mV a `W/L` change would have.
3. **The `ibias` rail and the amplifier's bias point survived the 1/8
   rescale.** `v_ibias_op` = 0.758 V at nominal against §3's pre-#55 0.75 V,
   and the amplifier's tail reads 2.775 µA against #42's 2.66 µA — the
   `M4`/`M5` co-scaling preserved both, as intended.

### 2.7 Budget table (RSS, untrimmed, 3σ)

> **Read the `#55` column with Section 2.6a's coefficient correction in
> hand.** It is stated at the `8.007` core-mirror coefficient, which #61's
> current halving invalidated; at #61's own current the same 360 µm² mirror
> is **8.62 mV**, not 6.36 mV, and the RSS is **16.26 mV**, not 15.19 mV —
> which is the number that agrees with the Monte Carlo actually measured
> after #61 (15.56/15.70/16.13 mV, Section 2.8). The `#147` column below is
> stated at the re-measured coefficient throughout.

| Line | 3σ contribution to Vref (#10) | 3σ contribution to Vref (#42) | 3σ contribution to Vref (**#55**) | Source |
|---|---|---|---|---|
| Amplifier offset, random (M1/M2 + M3/M4-referred) | 25.06 mV | **13.06 mV** | 13.06 mV | Sections 2.2, 2.4 — analytic scaling of record `20260731-031718-8fb0ea6`, sensitivity from record `20260801-073817-a7fd16a` |
| **Core mirror, random (`M1`–`M4`, 4 independent devices)** | 19.07 mV | 19.07 mV | **6.36 mV** | **Section 2.6a — sensitivities measured ([`20260801-132317-cfd0146`](../sim/core-mirror-sensitivity/records/20260801-132317-cfd0146.md)), Pelgrom scaling of record `20260731-031718-8fb0ea6`** |
| **Core cascode, random (`MC1`–`MC4`)** | < 0.11 mV | < 0.11 mV | **< 0.04 mV** | **Section 2.6a — `∂Vref/∂δ(MC3)` measured at −0.0133 V/V, bounded across all four** |
| Resistor mismatch (R1, R2, independent) | 3.92 mV | 3.92 mV | 3.92 mV | Section 2.5 — **assumed** coefficient, PDK cannot verify |
| PNP mismatch (Q1/Q2 pair) | 2.06 mV | 2.06 mV | 2.06 mV | Section 2.6 — record `20260731-040850-187a336` |
| **RSS of random terms** | 31.80 mV | 23.53 mV | **15.19 mV** | `sqrt(13.06^2 + 6.36^2 + 3.92^2 + 2.06^2)` |
| Amplifier offset, systematic (reserve, unverified) | +2.00 mV | +2.00 mV | +2.00 mV | Section 2.3 — placeholder pending #16 layout |
| **Total (RSS random + systematic reserve)** | 33.80 mV | 25.53 mV | **17.19 mV** | |
| **Ratified untrimmed target (3σ)** | 24.0 mV (±2 % of 1.20 V) | 24.0 mV | 24.0 mV | `README.md`, DR-0003 |
| **Margin** | −41 % (over) | −6 % (over) | **+40 % (72 % of budget used)** | |

### 2.7a Budget table after #147 (re-measured coefficients)

| Line | post-#61, pre-#147 | **#147** | Source |
|---|---|---|---|
| Amplifier offset, random | 13.06 mV | **9.60 mV** | Section 2.2 — input pair 800 → 1800 µm² at constant `W/L` |
| Core mirror, random (`M1`–`M4`) | 8.62 mV | **6.06 mV** | Section 2.6a — 360 → 722.5 µm² at constant `W/L`, coefficient re-measured (10.86 → 10.82, i.e. unchanged) |
| Core cascode, random (`MC1`–`MC4`) | < 0.06 mV | **< 0.02 mV** | Section 2.6a — `∂Vref/∂δ(MC3)` re-measured at −0.0475 V/V worst corner |
| Resistor mismatch (R1, R2, trim ladder) | 3.92 mV | 3.92 mV | Section 2.5 — **assumed** coefficient, unchanged (no resistor geometry moved) |
| PNP mismatch (Q1/Q2 pair) | 2.06 mV | 2.06 mV | Section 2.6 — unchanged |
| **RSS of random terms** | **16.26 mV** | **12.19 mV** | |
| Amplifier offset, systematic (reserve) | +2.00 mV | +2.00 mV | Section 2.3 — unchanged placeholder pending #16 |
| **Total** | **18.26 mV** | **14.19 mV** | |
| **Measured** (`mm_all` 3σ, −40/27/125 °C) | 15.56 / 15.70 / 16.13 mV | **11.85 / 12.03 / 12.54 mV** | `sim/mc-untrimmed/` records [`20260807-204001-1c8f58d`](../sim/mc-untrimmed/records/20260807-204001-1c8f58d.md) → [`20260816-142716-1ca1c95`](../sim/mc-untrimmed/records/20260816-142716-1ca1c95.md) |
| **Ratified untrimmed target (3σ)** | 24.0 mV | 24.0 mV | `README.md`, DR-0003 |

The allocation's random RSS (12.19 mV) lands 2.9 % under the measured
all-on 3σ at 125 °C (12.54 mV) and 2.8 % over it at −40 °C — the same
few-percent agreement the #55 row achieved, across another 1.29× change in
the quantity being predicted. **No line above was loosened**: the two that
moved are the two whose devices moved, the resistor and PNP lines are
numerically unchanged, and the systematic reserve is untouched.

**This allocation closes, and unlike the previous two revisions of this
table it is complete.** The #10 and #42 columns are those issues' own
numbers with Section 2.6a's core-mirror line added at the 40 µm² sizing they
both shipped — which is why #42's column now reads 25.53 mV rather than the
15.79 mV that revision of this document claimed. **Nothing was measured
differently; a missing row was added.** The 25.53 mV figure is also the one
that agrees with the Monte Carlo #42 actually ran (23.6–24.3 mV, Section
2.8), where 15.79 mV did not — which is the strongest available evidence
that the added row is real and correctly sized.

No allocation above was loosened to make the table sum: the amplifier,
resistor and PNP lines are numerically unchanged from #42's, and the
core-mirror line moved because the core mirror changed.

The amplifier's own random offset is again the largest single term (13.06 of
15.19 mV RSS) — deliberately, per Section 2.6a's stopping criterion.

### 2.8 Circuit-level Monte Carlo cross-check

The RSS above is a deterministic allocation over a chosen list of
contributors. `sim/mc-untrimmed/` (#13's bench, `run_mc_untrimmed.py`)
measures the same output quantity the other way: a live N=300 mismatch
Monte Carlo on the **whole** `bandgap_top` netlist, every device included,
at nominal supply across the CLAUDE.md temperature axis. It takes
`design/netlist/bandgap_top.spice` directly as its DUT, so it re-runs
against a changed schematic with no bench edit — which #42 did, and which
#55 does again.

- **Record (#55, resized core + #42 amp + #14 trim network)**: [`20260801-153308-ab79e4d`](../sim/mc-untrimmed/records/20260801-153308-ab79e4d.md)
- **Superseded record (#42 amp, 40 µm² core, pre-trim snapshot)**:
  [`20260801-080002-a7fd16a`](../sim/mc-untrimmed/records/20260801-080002-a7fd16a.md).
  Per #59 that record's netlist snapshot pre-dates #14's trim network, so
  its numbers are a pre-trim *and* pre-resize baseline; #55's re-run above
  is against the current DUT and settles both questions at once.
- **Earliest record**: `20260801-033856-7c40876`, minted against **#8's**
  unbudgeted 10 µm/4 µm amp.

| Group (N=300, 3.30 V) | 3σ at −40 °C | 3σ at 27 °C | 3σ at 125 °C |
|---|---|---|---|
| all mismatch on, #8 amp, 40 µm² core (record `…-7c40876`) | 66.58 mV | 67.32 mV | 69.67 mV |
| all mismatch on, #42 amp, 40 µm² core (record `…-a7fd16a`) | 23.62 mV | 23.77 mV | 24.27 mV |
| **all mismatch on, #55: #42 amp + 360 µm² core** | **14.89 mV** | **15.12 mV** | **15.82 mV** |
| MOS+BJT mismatch only, #55 | 13.64 mV | 13.64 mV | 13.90 mV |
| resistor mismatch only, #55 | 3.20 mV | 4.17 mV | 5.59 mV |
| deterministic control (`mm_ctrl`), #55 | 0.0000 mV | 0.0000 mV | 0.0000 mV |
| **Ratified target (3σ)** | 24.0 mV | 24.0 mV | 24.0 mV |

**The 3σ spread now passes at every temperature, with 34–38 % of margin** —
a further 1.53–1.59× reduction on top of #42's 2.8×, and 4.6× against the
circuit as #8 entered it. `mm_ctrl` reads exactly zero at all three
temperatures, the deterministic anchor that says the spread above is
mismatch and not solver noise, and no sample in any group hit the
degenerate-state guard.

**#59's question, answered with a number.** The superseded record's DUT
snapshot had no trim network; this one has `XXTRIM` at `trim_code=32`, i.e.
63 extra matched `ppolyf_u` segments in the divider path. Their effect is
visible and small: the resistor-only line moves 2.93/3.82/5.15 →
**3.20/4.17/5.59 mV** (+9 % at every temperature), because the trim
segments are short (1.215 µm) and therefore individually poorly matched, but
they sit in series and average as `1/√63`. It does not change any
conclusion — resistor mismatch is still ~1/3 of the MOS+BJT line — but it
does mean the pre-trim numbers were mildly optimistic on that one row, and
the allocated 3.92 mV in Section 2.5 is now slightly *under* the measured
5.59 mV at 125 °C. That gap (Section 2.5's coefficient is an assumed,
PDK-unverifiable literature value to begin with) is well inside this
budget's remaining margin and is flagged here rather than absorbed.

**Reading the window check.** The bench's own verdict folds the
distribution's *centre* and its *width* into one interval (`mean ± 3σ`
inside 1.176–1.224 V). Those are two different design problems and only one
of them is a mismatch problem:

- The **width** is what this document allocates and what #55 sized the core
  mirror against. It is **14.89 / 15.12 / 15.82 mV (3σ)** at −40/27/125 °C
  against the ratified 24.0 mV — **passing at all three temperatures**,
  from 23.62/23.77/24.27 mV before the resize.
- The **centre** sits high of 1.200 V because R1/R2 are still a first-pass
  hand sizing (`design/bandgap_operating_point.md` §2) evaluated at the trim
  network's mid-code, and removing exactly that offset is what the 1-point
  wafer-probe trim exists for (`design/bandgap_trim_network.md`). It is not
  a mismatch term, no amount of device area moves it, and it is out of #55's
  scope.

So the record's combined verdict still reads FAIL while the quantity this
budget is responsible for passes. Both statements are in the record; neither
threshold was adjusted.

**Allocation vs measurement, across three design revisions.** The reason to
keep both numbers is that they check each other. Now that Section 2.6a has
added the missing row, they agree:

| Revision | Section 2.7 RSS (allocated, random) | `mc-untrimmed` all-on 3σ (measured, −40/27/125 °C) |
|---|---|---|
| #8 amp, 40 µm² core | — | 66.58 / 67.32 / 69.67 mV |
| #42 amp, 40 µm² core | 23.53 mV | 23.62 / 23.77 / 24.27 mV |
| **#55 amp + 360 µm² core** | **15.19 mV** | **14.89 / 15.12 / 15.82 mV** |

The middle row is the calibration point: the allocation and the measurement
land within 3 % of each other *only* once the core-mirror line is included
(without it the allocation read 13.79 mV against a measured 23.8 mV). The
bottom row is what the resize was predicted to produce and what it actually
produced — **15.19 mV predicted, 14.89–15.82 mV measured, agreeing to
2–4 %**, across a 1.6× change in the quantity being predicted. That is the
whole argument that Section 2.6a is a model of this circuit and not a
curve-fit: it was written down before the re-run, and the re-run landed on
it.

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

| | #10 amp (same bench) | #42 amp, 40 µm² core | **#55, 360 µm² core** |
|---|---|---|---|
| Worst of the 81-point PVT grid | 31.87 dB (`sf`/125 °C/3.63 V) | 77.61 dB (`res_ss`/125 °C/3.63 V) | **86.98 dB** (`res_ss`/125 °C/3.63 V) |
| Best of the grid | 87.25 dB (`fs`/−40 °C/2.97 V) | 105.87 dB (`ff`/27 °C/3.30 V) | 105.40 dB (`ff`/−40 °C/3.30 V) |
| Corners meeting the ratified >60 dB | 19 / 81 | **81 / 81** | **81 / 81** |
| Overall | **FAIL** | **PASS**, +17.6 dB margin | **PASS**, +27.0 dB margin |

- #55 record: [`20260801-133427-cfd0146`](../sim/amp-psrr/records/20260801-133427-cfd0146.md)

The #10 baseline column reproduces #10's own record (31.9 dB at the same
`sf`/125 °C/3.63 V corner) to two decimal places, which is what makes the
+45.7 dB worst-corner delta a measurement rather than an assertion: the
testbench was rebuilt in #42 (Section 3.5), and running #10's amp through
the rebuilt bench lands on #10's published number.

**#55 improves PSRR by a further 9.4 dB at the worst corner**, which is a
side effect rather than a goal, and a predictable one: the resized mirror
devices are 3× longer (L = 2 µm → 6 µm), so each mirror leg's own output
impedance rises with them, and Section 3.3's core-only diagnostic already
said the core's output stage — not the amp — sets the ceiling once the
amp's contribution is removed. Nothing in the PSRR bench or its limits
changed.

**The whole-block spec-line PSRR bench agrees.** `sim/psrr-dc/` (#12's
bench, the one the ratified row is judged on, run against the regenerated
`sim/dut/bandgap_top.spice`) reads a worst-corner **87.41 dB at 1 Hz and
87.07 dB at 1 kHz**, 81/81 PASS, against 31.91 dB on the pre-#42 DUT —
record [`20260801-143203-cfd0146`](../sim/psrr-dc/records/20260801-143203-cfd0146.md).
The 1 MHz stretch goal (`> 30 dB`, recorded not gated) also now passes at
every corner, worst 30.39 dB.

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
- **Record (#55, resized core)**: [`20260801-133312-cfd0146`](../sim/amp-loop-stability/records/20260801-133312-cfd0146.md)
- **Record (#42 amp, 40 µm² core)**: [`20260801-073725-a7fd16a`](../sim/amp-loop-stability/records/20260801-073725-a7fd16a.md)
- **Paired baseline (#10's amp, same bench)**: [`20260801-073511-a7fd16a`](../sim/amp-loop-stability/records/20260801-073511-a7fd16a.md)

| | #10 amp (same bench) | #42 amp, 40 µm² core | **#55, 360 µm² core** | Criterion |
|---|---|---|---|---|
| DC loop gain | 37.75–42.94 dB | 89.13–106.06 dB | **90.20–105.89 dB** | ≥10 dB sanity floor |
| Phase margin, worst corner | 119.1° (`res_ss`/−40 °C/3.63 V) | 177.8° (`ff`/125 °C/3.63 V) | **108.9°** (`ff`/−40 °C/3.63 V) | ≥45° |
| Nyquist gain margin, worst corner | −999 dB (no crossing) | −7.007 dB (`ff`/−40 °C/2.97 V) | **−999 dB (no crossing, 81/81)** | <0 dB |
| Overall | PASS | PASS, 81/81 | **PASS, 81/81** | |

**No new violation versus either baseline.** #55's phase margin is lower
than #42's (108.9° vs 177.8° at the worst corner) and that is expected, not
a surprise: the resized mirror devices add roughly an order of magnitude of
gate capacitance on `fb`, which *is* the amplifier's output node, so the
dominant pole moves down and the loop's phase rolls further before crossover.
The worst-corner margin is still **2.4× the 45° criterion**, DC loop gain is
unchanged to within 1 dB, and on the *stronger* of the two criteria the
resize is a strict improvement: `gm_crit_db` goes from −7.0 dB (a real, if
comfortable, positive-real-axis crossing) to the −999 dB sentinel — the
Nyquist locus no longer reaches phase 0 anywhere in the sweep, at any of the
81 corners. Section 4.4 exists because criterion #1 alone can be fooled;
criterion #2 is the one that moved the right way.

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

Re-run against #55's resized core, record
[`20260801-145517-cfd0146`](../sim/startup/records/20260801-145517-cfd0146.md):
still settles at every one of the 81 corners, `startup_time` **9.3–31.1 µs**
(faster, and now ~32× margin at the worst corner), `vref_final`
1.217–1.260 V — bit-identical range to #42's. The transient therefore
confirms what Section 4.5's AC result says: the extra gate capacitance moved
the pole without costing settling behaviour, and the loop is not ringing.

## 5. What still does not close (no spec relaxation)

Per CLAUDE.md's "agents do not relax the ratified spec to make results
pass": as of **#61**, every ratified row this document is responsible for
passes. The section below is kept as a full history rather than trimmed to
the current state — the closed-form reasoning that #55 could not close
quiescent current by mirror sizing, and the quantified `k` that #61 used to
close it instead, are load-bearing for the next issue that touches this
circuit's current or resistor sizing. One out-of-scope item (the untrimmed
mean) remains, stated so it is not mistaken for closed.

**Update (#96).** The temperature-coefficient row and the corner leg of the
output-reference row — both left open by #61 (Section 5a's closing note:
"an unrelated, pre-existing miss that #61 measurably narrows rather than
one it introduces or is responsible for closing") — are now also closed.
Section 5b has the derivation and the measured result; the untrimmed
mismatch-MC **mean** (as distinct from the corner leg) remains the one item
still open, unchanged by #96 and out of its scope (Section 5b's own closing
note).

**Update (#147).** The untrimmed *mean* — the one item the paragraph below
leaves open, and the paragraph below is left as written for history — is now
closed too, together with the combined verdict it was blocking. **Section 5c**
is that work; read it in place of the "not this document's" framing here,
which #147 supersedes: re-centring the mean turned out to be exactly this
document's problem, because it can only be paid for out of another ratified
row's margin.

**Untrimmed accuracy: the mismatch *spread* closes; the untrimmed *mean*
does not, and is not this document's.** Section 2.7's allocation now covers
every device group in the block and closes at 17.19 mV against 24.0 mV, and
Section 2.8's Monte Carlo agrees at **14.89 / 15.12 / 15.82 mV (3σ)**,
passing at all three temperatures. What remains is the distribution's centre
— 1.22–1.25 V against a 1.200 V target, from R1/R2's first-pass hand sizing
evaluated at the trim network's mid-code. That is not a mismatch problem, no
device area moves it, and it is what the 1-point wafer-probe trim exists to
remove (`design/bandgap_trim_network.md`). The `mc-untrimmed` bench's own
verdict folds centre and width together and therefore still reads FAIL; both
quantities are in the record separately, and neither threshold was adjusted.

**Quiescent current** — the miss, until #61 (Section 5a). Ratified `< 50 µA`,
binding at `ff`/125 °C/3.63 V. Measured on `sim/startup/`'s
`iq_total_final_ua` (the same bench and measurement across all three
columns, so these are comparable):

| | before #42 | after #42 | after #55 | **after #61** | ratified |
|---|---|---|---|---|---|
| `tt`/27 °C/3.30 V | 46.78 µA | 48.24 µA | 39.32 µA | **20.72 µA** | — |
| `ff`/125 °C/3.63 V (binding) | 77.5 µA | 80.5 µA | 65.71 µA | **34.41 µA** | < 50 µA |
| overshoot / margin at the binding corner | +55 % | +61 % | +31 % | **−31 % (31 % margin)** | |

- #55 records: [`20260801-145326-cfd0146`](../sim/iq/records/20260801-145326-cfd0146.md)
  (`sim/iq/`, the spec-line bench: 65.473 µA at `ff`/125 °C/3.63 V) and
  [`20260801-145517-cfd0146`](../sim/startup/records/20260801-145517-cfd0146.md)
  (`sim/startup/`, 65.71 µA including the settled startup branch).

**What #55 recovered, and how.** −14.8 µA at the binding corner (−18 %),
−8.9 µA at nominal, from scaling the `ibias` leg (`M4`/`MC4`/`M5`) to 1/8 of
the design current — licensed by Section 2.6a's measurement that this leg's
mismatch does not reach `Vref` at all. It is the largest single Iq reduction
any issue has made on this block, and it is not enough.

**Why *mirror sizing* cannot close the rest — closed form, not opinion.**
Three of the four core branches carry the design current `I`, and `I` is not
a function of any mirror device's geometry:

```
I = dVBE / R2 ,      dVBE = VT * ln(A)        (A = 3.634, the PNP area ratio)
```

The servo drives `fb` to *whatever* gate voltage delivers that current;
widening `M1`/`M2` lowers `Vov` and leaves `I` exactly where it was. Two
apparent escapes, both closed:

- **Skew the mirror ratio** `I1 = r·I2`. Then `I2·R2 = VT·ln(A·r)`, so
  `r < 1` does reduce current — by shrinking `ΔVBE`. At `r = ½`, `ΔVBE`
  falls 33.4 → 15.4 mV, which raises Section 2.6a's `ρ` from 0.437 to 0.627
  and the servoed-leg sensitivity `1/(1−ρ)` from 1.77 to 2.68. That buys
  ~2× on current by spending ~1.5× on the *accuracy* row this issue exists
  to fix. Rejected.
- **Shrink the output leg** `M3` by `1/m`. Then `I3·R1` — the entire PTAT
  term of `Vref` — falls by `m` and must be restored by `R1 → m·R1`. That
  is a resistor change, not a mirror change.

⇒ The one lever that reduces total current while leaving `ΔVBE`, the `R1/R2`
ratio and the untrimmed mean untouched is **co-scaling `R1` and `R2` by a
common factor `k`**: `I → I/k`, `I·R1` unchanged, `R1/R2` unchanged, and
`Vref` shifts only by the `−VT·ln k` of `VEB(Q3)` (for `k = 1.5`, −10.5 mV —
*toward* the 1.200 V target). Every **resistor**-ratio and **PNP**-derived
mismatch coefficient in this document (Sections 2.5, 2.6) is invariant under
`k` by construction — those are geometric or `ln`-of-area-ratio quantities
with no dependence on absolute current. The **MOS** mismatch coefficients of
Section 2.6a are not: they scale with `gm/Id` at the mirror devices' fixed
`W/L`, which moves (mildly) with the operating current, so halving `I` was
not guaranteed in advance to leave them exactly fixed — #61's Section 5a
measures by how much.

**Quantified, so the next issue does not have to re-derive it.** At the
binding corner the startup branch's 2.39 µA does not scale with `I` (it is
the 2 MΩ `XRPU` pull-up); the other 63.3 µA does. So

```
Iq(k) ~= 63.3/k + 2.4  uA        =>  k >= 1.33 to pass at all
                                     k  = 1.5  -> ~44.6 uA (11% margin)
                                     k  = 2.0  -> ~34.1 uA (32% margin)
```

i.e. `R2: 3293 Ω → ~4940 Ω` and `R1` (plus the trim network's segment
resistances, so a trim step keeps its value in volts) by the same 1.5×, for
a design current of ~6.7 µA — still inside the 0.07 nA…28 µA usable emitter
window `design/device-characterization.md` §1 characterizes, though off the
exactly-10 µA point the `VEB`/`ΔVBE`/slope citations were taken at, so the
temperature-coefficient row would need re-verifying with it. **That is a
resistor/trim-network sizing pass, not a mirror sizing pass**, and #55
deliberately did not take it: it moves `design/bandgap_trim.sch` and the
`R1`/`R2` values, which #55 scoped itself out of. **#61 is that pass** —
Section 5a.

### 5a. #61: co-scaling `R1`/`R2`/trim by `k = 2` closes it

**Chosen `k` and why not the bare-pass `k = 1.5`.** Of the two margins
quantified above, #61 takes `k = 2` (32 % margin against the ratified
< 50 µA) rather than `k = 1.5` (11 % margin): the mismatch coefficients this
document allocates against are not perfectly current-invariant (Section 2.6a
is a `gm/Id` effect, not a pure ratio — see the caveat above), so the larger
margin is deliberately not spent down to the bare `k ≥ 1.33` threshold the
closed form requires to pass at all.

```
R2      L=18u       -> 36.341871u   (3293.2  -> 6586.5  ohm)
R1      L=230.180u  -> 460.701871u  (41389.5 -> 82779.0 ohm)
R_unit  L=1.215u    -> 2.771871u    (279.53  -> 559.06  ohm, bandgap_trim.sch, x63)
```

`ppolyf_u` is a compound device (`R = 179.547·L_um + 61.382 Ω` at `W=2 µm`,
`tt`/27 °C — Section 2.5 and `bandgap_trim.sch`'s header), so each length was
*solved* for the target resistance rather than doubled directly; a 2×
length is not a 2× resistance for a compound device. `R1_total/R2 = 15.28425`
before and after, to 5 decimal places.

**Result, measured — every acceptance-criteria bench re-run against the
resized DUT:**

| Bench | Metric | Before #61 | **After #61 (k=2)** | Gate | Verdict |
|---|---|---|---|---|---|
| `sim/iq/` | `iq_ua`, worst (`ff`/125 °C/3.63 V) | 65.473 µA | **34.0144 µA** | < 50 µA | **PASS** (record [`20260801-230754-960f726`](../sim/iq/records/20260801-230754-960f726.md), 81/81) |
| `sim/startup/` | `iq_total_final_ua`, worst | 65.71 µA | **34.4132 µA** | (Iq lives in `sim/iq/`; this cross-checks it including the settled startup branch) | **PASS** (record [`20260801-230933-960f726`](../sim/startup/records/20260801-230933-960f726.md), 81/81, startup time 8.96–28.19 µs, still ≪ 1 ms) |
| `sim/trim-coverage/` | `span_mv`, worst-case min | 134.347 mV | **135.389 mV** | ≥ 120 mV (±5 %) | **PASS**, unchanged within noise (record [`20260801-231346-960f726`](../sim/trim-coverage/records/20260801-231346-960f726.md), 81/81) |
| `sim/trim-coverage/` | `lsb_mv` at `tt`/27 °C (ratified corner) | 2.833 mV | **2.829 mV** | ≤ 3.00 mV (0.25 %/step) | **PASS**, unchanged within noise |
| `sim/trim-coverage/` | `w5_lsb` (binary weighting) | 32.000 | **32.0001** (envelope 31.999–32.0012) | 31.9–32.1 | **PASS**, unchanged |
| `sim/mc-untrimmed/` | `mm_all` 3σ, −40/27/125 °C | 14.89/15.12/15.82 mV | **16.22/16.36/16.81 mV** | ≤ 24.0 mV | **PASS** at all three (record [`20260801-232002-960f726`](../sim/mc-untrimmed/records/20260801-232002-960f726.md)); see below for why this rose rather than held flat |
| `sim/amp-loop-stability/` | phase margin, worst corner | 108.9° | **95.489°** | ≥ 45° | **PASS** (record [`20260801-231150-960f726`](../sim/amp-loop-stability/records/20260801-231150-960f726.md), 81/81) |
| `sim/amp-loop-stability/` | Nyquist gain margin | no critical-axis crossing | **no critical-axis crossing** (`gm_crit_db = -999` at all 81 points) | < 0 dB | **PASS** |
| `sim/amp-psrr/` | `psrr_worst_db`, worst corner | — (Section 3.2's 86.98 dB is the whole-loop bench, not this one's own worst-band figure) | **73.805 dB** | > 60 dB DC–1 kHz | **PASS** (record [`20260801-231234-960f726`](../sim/amp-psrr/records/20260801-231234-960f726.md), 81/81) |
| `sim/output-voltage-tc/` | `tc_ppm`, envelope over 81 corners | 86.32–137.75 ppm/°C | **36.37–90.50 ppm/°C** | ≤ 50 ppm/°C (binds at 27 °C) | **Improved, still fails** (record [`20260801-234837-960f726`](../sim/output-voltage-tc/records/20260801-234837-960f726.md), 81/81); no regression, no re-nulling needed — see below |

**Why quiescent current fell by more than exactly 2×.** The closed-form
estimate `Iq(2) ≈ 34.1 µA` assumed only the 63.3 µA/`k` term scales; the
measured 34.01 µA agrees to 0.3 %, confirming the model. The three signal
branches drop from ~10.1 µA to ~5.05 µA each (`ΔVBE/R2` unchanged, `R2`
doubled); `M4`/`MC4`/`M5`'s 1/8-scaled `ibias` leg (#55) and the
cascode-bias branch scale down proportionally with it; only the startup
branch's `XRPU`-pull-up current (set by a fixed 2 MΩ resistor, not by this
circuit's servo) does not scale with `k`, exactly as predicted.

**Why the mismatch spread rose slightly instead of holding flat.** Section
2.7/2.8's resistor line *improved*, as expected — halving `I` at fixed
`I·R1` means doubling `R`, and Pelgrom-law mismatch falls as `1/√(area)`, so
the per-instance sigma on `R1`/`R2`/every trim unit dropped (`XR2`:
0.2507 % → 0.1764 %; `XR1`: 0.0701 % → 0.0496 %) and the resistor-only
`mm_res` 3σ line fell from 3.20/4.17/5.59 mV to **2.27/2.95/3.95 mV**. But
the MOS+BJT line (`mm_fetbjt`) *rose*, from 13.64/13.64/13.90 mV to
**14.92/14.96/15.19 mV**: `gm/Id` at the mirror devices' fixed `W/L`
increases as the operating current drops (moving toward weaker inversion),
so a fixed `Vth` mismatch produces a slightly larger `ΔVref` at the new,
lower `I`. This is the caveat entered above when `k` was chosen — the MOS
mismatch coefficients of Section 2.6a are a `gm/Id` effect, not a pure
resistor-style ratio, and #61 did not re-derive them (the mirror geometry
itself is unchanged). Net effect on `mm_all`: 14.89/15.12/15.82 mV →
**16.22/16.36/16.81 mV**, a ≈9 % increase that still leaves 30–32 % of margin
against the ratified 24.0 mV at every temperature — the resistor
improvement did not fully offset the MOS/BJT degradation, but neither did it
need to. As before #61, the bench's own combined verdict (mean ± 3σ inside
the window) still reads FAIL on the untrimmed **mean**, unchanged by this
issue and explicitly out of its scope (see the top of this section).

**Temperature coefficient — improved, no re-nulling needed.** The acceptance
criteria required checking `sim/output-voltage-tc/` for a TC regression and
re-nulling `R1`/`R2` if one appeared. It did not: the box-method `tc_ppm`
envelope over all 81 PVT points moved from **86.32–137.75 ppm/°C** (mean
110.97) before #61 to **36.37–90.50 ppm/°C** (mean 62.04) after — every
corner improved, none regressed (record
[`20260801-234837-960f726`](../sim/output-voltage-tc/records/20260801-234837-960f726.md)).
This is consistent with `bandgap_core.sch`'s header note that the `−VT·ln k`
shift makes `VEB(Q3)`'s CTAT slope slightly steeper, which reduces this
first-pass-sized loop's residual PTAT-dominated drift. The row still fails
the ratified `≤ 50 ppm/°C` bound — it did before #61 too, and `R1`/`R2`'s
first-order TC balance is still a first-pass hand calculation, never
corner-swept and re-nulled against a TC target the way #10/#42's amplifier
work was (`design/bandgap_operating_point.md` §2, §6) — so this is an
unrelated, pre-existing miss that #61 measurably narrows rather than one it
introduces or is responsible for closing. The
`vref`-window check on the same bench (corner-only leg of the
output-reference row) also improved: 1.20264–1.23105 V, against
1.22212–1.25612 V before, both consistent with the `−VT·ln k` shift and
neither a claim this issue re-centres the untrimmed mean (see "Not in
scope" in issue #61).

### 5b. #96: re-nulling `R1` alone against a corner-swept TC objective closes it

**Why this was still open after #61.** #55 and #61 both explicitly preserved
the #8 first-pass `R1`/`R2` ratio (`15.28425`) rather than re-deriving it —
#61's own closing note above calls the TC row's residual "an unrelated,
pre-existing miss... that #61 measurably narrows rather than one it
introduces or is responsible for closing." Neither issue's scope was TC; #55
scoped mirror sizing, #61 scoped quiescent current.

**Root cause, closed form.** Section 5 above establishes `I = ΔVBE/R2` —
the design current has no `R1` dependence at all. `Vref(T) = VEB(Q3)(T) +
I(T)·(R1 + R_trim)`, so for a fixed `R2` (and therefore a fixed `I(T)` at
every temperature), `Vref(T)` is **exactly affine in `R1`** at every
temperature: changing `R1` alone cannot move `I(T)` or `ΔVBE(T)` at all. This
makes `R1` — and only `R1` — the correct, isolated lever for re-nulling TC
without touching the #61-closed quiescent-current row (`R2`-set), the
resistor/PNP mismatch *ratios* (Sections 2.5/2.6, which are `R1/R2`-ratio
invariant only under a co-scale — this is a single-lever move, not one), or
the trim step size (`R_unit`-set, unchanged).

**Method: exploit the affine relationship instead of a per-`R1` corner
re-sweep.** Two full `-40..125 °C` internal-sweep runs (the same fine
sweep `sim/output-voltage-tc/` uses) at two different `R1` values, same
`R2` and everything else, reconstruct `Vref(T)` for *any* `R1` at that
corner by exact linear interpolation/extrapolation on the measured pair —
not a curve fit, because the affine relationship above is a circuit fact.
The method was checked against the existing FAIL record before being
trusted for a search: reproduced its `tc_ppm` to 3+ significant figures at
every one of the 9 process corners. Minimizing the worst-of-9-corners box
`tc_ppm` over `R1` this way finds a single global minimum — `bjt_ff` and
`bjt_ss` (the two corners bracketing the ratified row's binding case) cross
at `R1 = 78470.5 Ω`, a Chebyshev-style optimum (both worst corners equal,
confirmed by a wide re-scan `R1 = 20 k…150 k Ω` finding no other local
minimum) — worst-case `tc_ppm ≈ 29.79 ppm/°C` there on the 9-corner/1-supply
search subset, 40 % margin against the ratified 50 ppm/°C bound.

**Sizing.**

```
R1 (fixed, e3->tn0)   L=460.701871u -> 436.705296u  (82779.0 -> 78470.5 ohm)
R2, R_unit, trim ladder structure: UNCHANGED
R1_total/R2 (default trim code 32): 15.28425 -> 14.63021
```

`R2` and the trim ladder are untouched — the affine argument above is
exactly why they don't need to move. `R1_total/R2` is no longer a
hand-picked ratio; it is what the corner-swept minimization landed on.

**Result, measured — full 81-point PVT grid (not the 9-corner/1-supply
search subset above), plus every bench the issue's test plan required as a
regression check, all re-run against the resized DUT:**

| Bench | Metric | Before #96 | **After #96** | Gate | Verdict |
|---|---|---|---|---|---|
| `sim/output-voltage-tc/` | `tc_ppm`, envelope over 81 corners | 36.37–90.50 ppm/°C, 63/81 FAIL (record [`20260802-064729-75ca562`](../sim/output-voltage-tc/records/20260802-064729-75ca562.md)) | **13.56–29.84 ppm/°C** | ≤ 50 ppm/°C | **PASS** 81/81 (record [`20260803-024632-294fb1d`](../sim/output-voltage-tc/records/20260803-024632-294fb1d.md)) |
| `sim/output-voltage-tc/` | `vref` (accuracy-window corner leg) | 6/81 FAIL, all at 125 °C `res_ff`/`bjt_ss` (1.22874–1.23105 V), same record | **1.18142–1.20185 V** | 1.176–1.224 V | **PASS** 81/81, same new record |
| `sim/iq/` | `iq_ua`, worst (`ff`/125 °C/3.63 V) | 34.0144 µA (record [`20260801-230754-960f726`](../sim/iq/records/20260801-230754-960f726.md), #61) | **34.0054 µA** | < 50 µA | **PASS** 81/81 (record [`20260803-031533-294fb1d`](../sim/iq/records/20260803-031533-294fb1d.md)), unchanged within noise — `R1` cannot move `I` (root cause above) |
| `sim/psrr-dc/` | `psrr_1khz_db`, worst corner (`res_ss`/125 °C/3.63 V) | 73.8437 dB (record [`20260802-045149-cf2ab8d`](../sim/psrr-dc/records/20260802-045149-cf2ab8d.md), post-#61) | **74.215 dB** | > 60 dB DC–1 kHz | **PASS** 81/81 (record [`20260803-031631-294fb1d`](../sim/psrr-dc/records/20260803-031631-294fb1d.md)), unchanged within noise |
| `sim/startup/` | `startup_time_s`, worst | 28.19 µs (record [`20260801-230933-960f726`](../sim/startup/records/20260801-230933-960f726.md), #61) | **43.97 µs** (`fs`/−40 °C/2.97 V) | < 1 ms | **PASS** 81/81 (record [`20260803-034153-294fb1d`](../sim/startup/records/20260803-034153-294fb1d.md)) — real increase, explained below, still 4.4 % of budget |
| `sim/startup/` | `iq_total_final_ua`, worst | 34.4132 µA | **33.9447 µA** | (cross-check of `sim/iq/`) | **PASS**, unchanged within noise |
| `sim/line-regulation/` | `linereg_mv_per_v`, worst (`res_ss`/125 °C/3.30 V) | not previously re-run against #61's resize | **0.0399 mV/V** | < 1 mV/V | **PASS** 27/27 (record [`20260803-031951-294fb1d`](../sim/line-regulation/records/20260803-031951-294fb1d.md)) |
| `sim/line-regulation/` | `vref_min`/`vref_max` | — | **1.18142 / 1.20185 V** | 1.176–1.224 V | **PASS**, same record |

**Why `sim/startup/`'s and `sim/startup-slow-ramp/`'s embedded testbenches
needed their own fix first.** Unlike `sim/output-voltage-tc/`, `sim/iq/`,
`sim/psrr-dc/` and `sim/line-regulation/` (which drive the swappable
`sim/dut/bandgap_top.spice` per `sim/README.md`'s convention and therefore
picked up `R1`'s new value automatically), `sim/startup/testbench/` and
`sim/startup-slow-ramp/testbench/`'s `bandgap_startup_ramp.spice` embed
their *own* copy of `bandgap_core`, with `R1` collapsed into a single lumped
device together with the trim ladder's 32 default-code unit segments (a
`sim/startup/`-specific optimization predating the swappable-DUT
convention). A first `sim/startup/` run against the unmodified lumped value
reproduced #61's own numbers exactly — proof the stale embedded value, not
`R1`, was being measured. The lumped device was re-solved the same way
#61's own value was: `R1_new`'s and `R_unit`'s resistances measured directly
on this design's own ngspice model (two-terminal DC op-point check at
50 mV bias, `tt`/27 °C — `design/bandgap_operating_point.md` §2's method),
then a single device's length bisected to match `R1_new + 32·R_unit`
exactly (`96360.76 Ω`, was `100669.29 Ω`) — not interpolated from the
documented approximate fit coefficients, because a lumped device's `L` is
not a simple sum of the real devices' lengths (Section 5a's `ppolyf_u`
compound-device note: one device pays the fit's constant term once, not
33 times). Both embedded testbench files (kept byte-identical by design,
see their own header) were updated together and both `sim/startup/` and
`sim/startup-slow-ramp/` were re-run.

**Why `startup_time_s` genuinely increased (not a regression, not noise).**
`sim/startup/`'s own measurement (`tb.json`) defines `startup_time` as the
time from `vdd` crossing 90 % of its final value to the last time `vref`
exits a **±1 % band around its own final value**. That tolerance band is
1 % of `vref`'s new, `R1`-lowered final value — a narrower absolute-volt
window for the same underlying current-settling transient (which Section 5
established `R1` cannot move) to converge into. A tighter absolute window
around an unchanged-shape settling waveform takes more time constants to
enter, which is exactly what was measured: 28.19 µs → 43.97 µs, still
4.4 % of the 1 ms budget. `iq_total_final_ua` (the actual current-settling
quantity) stayed flat (34.41 → 33.94 µA), confirming the dynamics
themselves did not change — only the derived time-domain threshold that
`vref`'s new absolute level shifted.

**Untrimmed mean, and the other embedded-schematic benches — out of
scope, unchanged.** `sim/mc-untrimmed/` (the mismatch-MC leg of the
output-reference row) was not re-run against `R1`'s new value — a
documented follow-on, not required by this issue (see
`design/bandgap_operating_point.md` §6). `sim/amp-loop-stability/`,
`sim/amp-psrr/`, `sim/amp-offset-sensitivity/`, `sim/core-mirror-sensitivity/`,
`sim/core-psrr-ideal-amp/`, `sim/bandgap-loop-smoke/`,
`sim/startup-disabled-control/` and `sim/startup-state-search/` also embed
their own copy of `bandgap_core` (same pattern as `sim/startup/`, predating
the swappable-DUT convention) and were **not** updated or re-run here: none
of them measure `Vref`'s absolute value or are gated by it (loop gain,
PSRR ratio, offset sensitivity and settle-state proofs are all quantities
Section 5's affine argument shows `R1` cannot move), and none is in this
issue's required regression list. Their embedded `R1` remaining stale is a
pre-existing gap in those testbenches' maintenance, not one this issue
introduces or was scoped to close.

### 5c. #147: the combined untrimmed-accuracy verdict, and what it takes to close it

**What was still open.** Sections 5a/5b closed every *per-bench* row. The
ratified Output-reference row is not a per-bench row: DR-0003 states it as
"1.20 V ±2 % untrimmed (3σ, **mismatch MC N≥300 + process corners**)", and
#97's `sim/suite/combined.py` is what evaluates the two legs together —
grafting `sim/mc-untrimmed/`'s measured mismatch distribution onto each of
`sim/output-voltage-tc/`'s 81 deterministic corners and requiring the whole
3σ interval to fit inside 1.176–1.224 V at every one. Against the
post-#96 design that verdict read **FAIL, 42 of 81 corners**
(`sim/suite/summaries/20260815-020700-40321ca.md`), with every individual
spec-line bench passing 6/6.

**Why both legs can pass and their sum still fail — the arithmetic.**

```
deterministic corner spread   1.20185 - 1.18142  = 20.43 mV
grafted mismatch spread       2 x 16.13          = 32.26 mV
                                                 ----------
total                                              52.69 mV
ratified window               1.224 - 1.176      = 48.00 mV
                                                   -------
                                                    -4.69 mV
```

and **all** of the overflow is on the low edge, because #96 put `R1` at the
TC-null, and at the TC-null this PNP's extrapolated bandgap puts `Vref` at
**1.1925 V** — 7.5 mV below the ratified window's 1.200 V centre. So the row
needs *both* of:

1. **less mismatch spread** — at least `(48 − 20.43)/2 = 13.79 mV` of 3σ is
   the ceiling before *any* centring can work, against 16.13 mV measured; and
2. **a re-centring**, which only `R1` can provide, and which is inherently
   PTAT-shaped (Section 5b: `Vref(T)` is affine in `R1`, and everything `R1`
   adds is `I(T)·ΔR1` — a PTAT term), so it is bought out of the temperature-
   coefficient row's margin.

The deterministic 20.43 mV is not a lever: it is `bjt_ss`/`bjt_ff` and
`res_ss`/`res_ff` process skew acting on `VEB(Q3)` with a gain of 1 (the
`ΔVBE` ratio, and hence the PTAT term, is skew-invariant by construction),
so no in-scope sizing moves it. That leaves mismatch area and `R1`.

**Lever 1: area, and the stability wall it runs into.** The mismatch RSS is
Section 2.7a's: the amplifier's own random offset was the largest term
(13.06 of 16.26 mV), the core mirror second (8.62 mV). Both are pure
Pelgrom-area terms at constant `W/L`. The obvious move — scale both amplifier
pairs hard — **does not survive this design's own stability criteria**, and
that is a measured result, not a caution:

| sizing (all else equal) | `pm_deg` worst of 81 | `gm_crit_db` worst | verdict |
|---|---|---|---|
| `origin/main` (M1/M2 200/4, M3/M4 20/16) | 97.3° | −999 (no crossing) | PASS |
| M1/M2 **300/6**, M3/M4 20/16 | 83.7° | −999 | PASS |
| M1/M2 350/7, M3/M4 20/16 | 21.3° | −999 | **FAIL** |
| M1/M2 200/4, M3/M4 22.5/18 | 4.2° | −17.8 dB | **FAIL** |
| M1/M2 200/4, M3/M4 30/24 | 3.6° | −16.1 dB | **FAIL** |
| M1/M2 350/7, M3/M4 30/24 | 5.7° | (crossings appear) | **FAIL** |

(`sim/amp-loop-stability/`, 81 PVT points each, `--no-write` exploration
runs.) The mirror load is the sensitive one: its gate node `nd1` carries the
mirror pole `gm3/(Cgs3+Cgs4)`, and 1.27× the area there is already enough.
**It is not a compensation problem** — `CC` was scanned at 60/80/100/120/150
µm square and moved `pm_deg` by less than 0.001°, because criterion #1 is
evaluated at the `|T|` notch rather than at a `CC`-set crossover. So the
amplifier contributes **only** the input pair, and only as far as
`300 µm/6 µm`.

The core mirror has the opposite property: its gates sit on `fb`, which *is*
the amplifier's output node, so area there moves the dominant pole down and
is stabilising — measured, with the final sizing in place: `pm_deg`
**160.9–172.4°** (from 97.3–179.8° on `origin/main`) and `gm_crit_db` at the
−999 sentinel at all 81 corners.

**Lever 2: `R1`, and the TC it costs.** `Vref` is affine in `R1` at every
temperature (Section 5b), so the trade is measurable exactly. Measured on
`sim/output-voltage-tc/`'s own 9-corner/1-supply subset:

| `R1` length | `Vref(tt, 27 °C)` | window low edge (`bjt_ff`/125 °C) | window high edge (`bjt_ss`/125 °C) | worst `tc_ppm` |
|---|---|---|---|---|
| 436.705296 µm (#96, TC-null) | 1.19249 V | 1.18142 V | 1.20185 V | 29.79 |
| 442.0 µm | 1.19163 V* | 1.18789 V | 1.20829 V | 42.79 |
| 443.2 µm | 1.19839 V | 1.18935 V | 1.20975 V | 45.89 |
| **443.4 µm (adopted)** | **1.19857 V** | **1.18958 V** | **1.21000 V** | **46.41** |
| 444.4 µm | — | 1.19081 V | 1.21121 V | 48.99 |

(*the 442.0 µm row's 27 °C column is that run's grid minimum, not `tt`.)
`Vref` moves +1.218 mV per µm of `R1` at 125 °C and `tc_ppm` +2.58 ppm/°C
per µm, both linear over this range. The two window edges balance exactly at
**443.57 µm**; **443.4 µm** is adopted a little short of it so the ratified
≤50 ppm/°C row keeps ~7 % margin rather than ~6 %, at the cost of 0.2 mV of
window margin on the low edge. **Both rows are still checked at their
ratified thresholds and both still pass at all 81 corners** — this is a
deliberate reallocation of margin between two ratified rows, not a
relaxation of either.

**Adopted sizing.**

```
bandgap_amp   M1/M2    200u/4u   -> 300u/6u    (nf 8 -> 12)   800  -> 1800   um^2
bandgap_amp   M3/M4    20u/16u   -- unchanged (stability, above)
bandgap_core  M1-M3,
              MC1-MC3  60u/6u    -> 85u/8.5u                  360  -> 722.5  um^2
bandgap_core  M4/MC4   7.5u/6u   -> 10.625u/8.5u  (W/L = 1.25 held, 1/8 leg)
bandgap_core  R1       436.705296u -> 443.400000u  (78470.7 -> 79672.7 ohm)
```

Every geometry above holds its `W/L` exactly, so `Vov`, the branch currents,
the `ibias` rail and every saturation margin are unchanged by construction —
confirmed on `sim/core-mirror-sensitivity/` (81 points, paired against
`origin/main` on the same bench): the four mirror sensitivity coefficients
move by ≤0.4 % across the 2× area step and `margin_m1_mv` reads
+84.7 mV against the baseline's +84.0 mV.

**Drawn-area cost**, against `layout/floorplan.md` §8's schematic-derived
floor (itself stale — it still lists the pre-#42/#55 amplifier and core):

| item | before | after | delta |
|---|---|---|---|
| amp input pair (2 devices) | 1600 µm² | 3600 µm² | +2000 µm² |
| core mirror + cascode (6 devices) | 2160 µm² | 4335 µm² | +2175 µm² |
| core `ibias` leg (2 devices) | 90 µm² | 180.6 µm² | +91 µm² |
| **total** | | | **+4266 µm²** |

That is 8.5 % of the ratified 0.05 mm² area row consumed as drawn body area.
The row is a layout claim, not a simulation claim (`layout/floorplan.md` §8,
§11.1), and re-costing it against real geometry belongs to the layout
follow-up — but it is stated here so the trade is visible: this issue buys
4.06 mV of 3σ mismatch with 4266 µm² of gate area.

**Result, measured — every bench in the spec-line suite plus the two
mismatch benches, re-run against the resized DUT.**

| Bench / verdict | Before #147 | **After #147** | Gate | Verdict |
|---|---|---|---|---|
| **Combined untrimmed accuracy** (`sim/suite/combined.py`) | **FAIL, 42/81 corners** | **PASS, 81/81** (report [`20260816-145925-1ca1c95`](../sim/suite/combined/20260816-145925-1ca1c95.md), suite summary [`20260816-142719-1ca1c95`](../sim/suite/summaries/20260816-142719-1ca1c95.md)) | 3σ interval inside 1.176–1.224 V at every corner | **PASS** |
| `sim/mc-untrimmed/` `mm_all` 3σ, −40/27/125 °C | 15.56 / 15.70 / 16.13 mV | **11.85 / 12.03 / 12.54 mV** | ≤ 24.0 mV | PASS |
| `sim/mc-untrimmed/` `mm_fetbjt` 3σ (MOS+BJT only) | 14.32 / 14.35 / 14.57 mV | **10.90 / 10.94 / 11.21 mV** | — | — |
| `sim/mc-untrimmed/` `mm_res` 3σ (resistors only) | 2.18 / 2.83 / 3.79 mV | 2.20 / 2.87 / 3.84 mV | — | unchanged, as expected (no resistor geometry moved) |
| `sim/output-voltage-tc/` `vref` (record [`20260816-142720-1ca1c95`](../sim/output-voltage-tc/records/20260816-142720-1ca1c95.md)) | 1.18142–1.20185 V | **1.18958–1.21000 V** | 1.176–1.224 V | PASS 81/81 |
| `sim/output-voltage-tc/` `tc_ppm` | 13.56–29.84 ppm/°C | **12.80–46.41 ppm/°C** | ≤ 50 ppm/°C | PASS 81/81 — the deliberate trade above |
| `sim/amp-loop-stability/` `pm_deg` / `gm_crit_db` (record [`20260816-145936-1ca1c95`](../sim/amp-loop-stability/records/20260816-145936-1ca1c95.md)) | 97.3–179.8° / −999 | **160.9–172.4° / −999** | ≥45° / <0 dB | PASS 81/81 |
| `sim/amp-psrr/` `psrr_worst_db` (record [`20260816-145949-1ca1c95`](../sim/amp-psrr/records/20260816-145949-1ca1c95.md)) | 73.81 dB (#61 record) | **77.09 dB** | > 60 dB | PASS 81/81 |
| `sim/amp-offset-sensitivity/` `dvref_dvos` (record [`20260816-150001-1ca1c95`](../sim/amp-offset-sensitivity/records/20260816-150001-1ca1c95.md)) | 16.02–16.21 V/V | **16.05–16.14 V/V** | envelope | unchanged, as the constant-`W/L` argument requires |
| `sim/core-mirror-sensitivity/` RSS coefficient (record [`20260816-150013-1ca1c95`](../sim/core-mirror-sensitivity/records/20260816-150013-1ca1c95.md)) | 10.857 (`origin/main`, re-measured) | **10.816** | envelope | unchanged (0.4 %) |
| `sim/core-mirror-sensitivity/` `margin_m1_mv` (saturation headroom) | +84.0 mV (`origin/main`, same bench) | **+84.7 mV** | ≥ 0 | PASS 81/81, unchanged |
| `sim/psrr-dc/` `psrr_1hz_db` (record [`20260816-145206-1ca1c95`](../sim/psrr-dc/records/20260816-145206-1ca1c95.md)) | 74.30 dB | **77.61 dB** | > 60 dB | PASS 81/81 |
| `sim/line-regulation/` `linereg_mv_per_v` (record [`20260816-145228-1ca1c95`](../sim/line-regulation/records/20260816-145228-1ca1c95.md)) | 0.0399 mV/V | **0.0267 mV/V** | < 1 mV/V | PASS 27/27 |
| `sim/iq/` `iq_ua`, `ff`/125 °C/3.63 V (record [`20260816-145740-1ca1c95`](../sim/iq/records/20260816-145740-1ca1c95.md)) | 34.0054 µA | **34.0193 µA** | < 50 µA | PASS 81/81, unchanged within noise |
| `sim/startup/` `startup_time_s`, worst (record [`20260816-145754-1ca1c95`](../sim/startup/records/20260816-145754-1ca1c95.md)) | 43.97 µs | **46.71 µs** | < 1 ms | PASS 81/81 |

**The margin that remains, stated plainly.** At the binding corners — both at
125 °C, where the grafted 3σ is widest — the combined interval clears the
window by **+0.84 mV on the low edge** (`bjt_ff`/125 °C/3.63 V) and
**+1.66 mV on the high edge** (`bjt_ss`/125 °C). That is a real pass at every
one of the 81 corners, and it is thin: 3.5 % and 6.9 % of the 24 mV
half-window, against a mismatch leg whose own 3σ carries about ±4 %
sampling uncertainty at N=300 (±0.5 mV). It should be read as "closed with
little to spare", not "closed comfortably".

**What is left, if more margin is wanted.** In rough order of value per unit
of risk:

1. **#87.** If it resolves as Option A (schematic adopts the drawn 4×
   unit-PNP array), `ΔVBE` rises 8 %, `R1/R2` falls ~8 %, and *every*
   mismatch term in Section 2.7a scales with it — the single largest
   remaining reduction available, and it is already an open decision rather
   than a new design idea. It also perturbs this verdict, so **this bench
   must be re-run when #87 resolves either way**.
2. **The resistor line (3.92 mV allocated, 3.84 mV measured at 125 °C)** is
   dominated by `R2`'s small area (36.3 µm × 2 µm). Widening `R2` at
   constant resistance is a pure Pelgrom win with no effect on any current —
   but it moves resistor geometry, which the TC null is sensitive to, so it
   needs its own `R1` re-null pass.
3. **A curvature-corrected core** would raise the TC-null `Vref` itself and
   remove the need to spend TC margin on centring at all. That is a topology
   change (DR-0001 scope), not a sizing pass.

**No spec relaxation.** Every threshold used above is the ratified one:
1.176–1.224 V, ≤50 ppm/°C, ≤24.0 mV 3σ, >60 dB, <50 µA, <1 ms. Nothing was
re-defined, and the one row whose *margin* was deliberately spent
(temperature coefficient, 29.79 → 46.41 ppm/°C) is reported at its ratified
threshold, at every corner, with the trade curve that produced it.

## 6. Summary of acceptance criteria

### 6.1 #42 (amplifier)

| Criterion | Status |
|---|---|
| Amp redesigned/recompensated to close both #10 shortfalls simultaneously | **Done** — telescopic cascode + dominant-pole compensation, Section 2.1 |
| Loop stability re-verified full PVT, PM ≥45°, no new violation vs #10 | **PASS** 81/81, Section 4.5 (and a second, stronger Nyquist criterion added, Section 4.4) |
| Offset sensitivity re-verified; updated RSS budget vs ±2 % (3σ) untrimmed | **Allocation PASSES** for the terms #42 allocated — 15.79 mV vs 24.0 mV; **superseded by #55**, which adds the core-mirror row that revision omitted, making #42's complete allocation 25.53 mV (Section 2.7) |
| PSRR re-verified full PVT vs >60 dB DC–1 kHz | **PASS** 81/81, worst corner 77.61 dB, Section 3.2 |
| `design/bandgap_error_budget.md` and `design/bandgap_operating_point.md` updated | Done — this document and `design/bandgap_operating_point.md` §2/§4.1 |
| New `sim/` records appended, not edited | Done — 11 new records (3 amp-* × 2 amps, 4 startup re-runs, 1 circuit-level MC), no existing record touched |
| No spec relaxation; residual gaps reported explicitly | Done — Section 5 as it stood at #42 |
| Accuracy/trim split not decided here | Done |

### 6.2 #55 (core mirror/cascode)

| Criterion | Status |
|---|---|
| `∂Vref/∂(mirror ΔVgs)` derived on `bandgap_core`'s own netlist, servoed legs distinguished from unservoed | **Done** — Section 2.6a: closed form *and* measurement for all four mirror devices plus the cascode mechanism, agreeing to ≤1.8 %; record [`20260801-132317-cfd0146`](../sim/core-mirror-sensitivity/records/20260801-132317-cfd0146.md) |
| Sec 2.7 extended with an explicit core-mirror line, sized against an area budget with Sec 2.2's rigor | **Done** — Sections 2.6a (derivation, area budget, stopping criterion) and 2.7 (table, now three columns) |
| Headroom re-verified across the full PVT grid; amp `tail_bias`/`ibias` operating point re-checked post-resize | **PASS** 81/81 — worst `Vds − Vdsat` **+122.7 mV** (`M1`, `res_ss`/−40 °C/2.97 V); `MCB` ≥ +858.9 mV; `v_ibias_op` 0.615–0.899 V; amp tail 1.41–4.20 µA — Section 2.6b |
| Target residual re-confirmed against a trim-inclusive DUT before finalizing sizing (#59) | **Done** — Section 2.8's #55 record is minted against `design/netlist/bandgap_top.spice` with `XXTRIM`/`trim_code=32` present, and supersedes the pre-trim record explicitly |
| `sim/mc-untrimmed/` re-run, ±2 % window check at −40/27/125 °C | **3σ spread PASSES at all three: 14.89 / 15.12 / 15.82 mV vs 24.0 mV** (record [`20260801-153308-ab79e4d`](../sim/mc-untrimmed/records/20260801-153308-ab79e4d.md), from 23.62/23.77/24.27 mV). The record's combined `mean ± 3σ` verdict still FAILs, on the untrimmed **mean**, which is out of scope — Sections 2.8 and 5 |
| Quiescent current below 50 µA at `ff`/125 °C/3.63 V | **FAIL — 65.71 µA** (from 80.5 µA, −18 %). Section 5 gives the closed-form reason mirror sizing cannot close the rest, and quantifies the resistor co-scaling that would |
| Loop stability / PSRR not regressed by the resize | **PASS** — PM 108.9° worst (≥45°), Nyquist margin *improved* to no critical-axis crossing (Section 4.5); amp PSRR 77.61 → 86.98 dB, whole-block `psrr-dc` 87.07 dB worst, 81/81 (Section 3.2) |
| No `spec/` changes | **Done** — nothing under `spec/` touched; no threshold in any `tb.json` altered |
| Untrimmed mean explicitly out of scope | **Done** — Sections 1, 2.8, 5 |

### 6.3 #61 (co-scale `R1`/`R2`/trim by `k`)

| Criterion | Status |
|---|---|
| `R1`, `R2` and the trim network's segment resistances co-scaled by one factor `k`, chosen against an explicit margin (not the bare `k ≥ 1.33` pass) | **Done** — `k = 2` (32 % margin at the binding corner, vs 11 % at the bare-pass-adjacent `k = 1.5`); each length solved for its target resistance since `ppolyf_u` is a compound device, not scaled directly; `R1_total/R2 = 15.28425` before and after — Section 5a |
| `sim/iq/` (or `sim/startup/`'s `iq_total_final_ua`) below 50 µA at `ff`/125 °C/3.63 V, full PVT grid | **PASS** 81/81 both benches — **34.0144 µA** (`sim/iq/`, record [`20260801-230754-960f726`](../sim/iq/records/20260801-230754-960f726.md)) and **34.4132 µA** (`sim/startup/`, record [`20260801-230933-960f726`](../sim/startup/records/20260801-230933-960f726.md)), 31 % margin — Section 5a |
| `sim/output-voltage-tc/` re-run; TC row must not regress, `R1`/`R2` re-nulled if it does | **Done** — see Section 5a for the measured result and whether re-nulling was needed |
| `sim/trim-coverage/` re-run; range ≥ ±5 %, resolution ≤ 0.25 %/step preserved | **PASS** 81/81, unchanged within simulation noise (`span_mv` 135.4–240.7 mV vs 134.3–243.5 mV before; `lsb_mv` at `tt`/27 °C 2.829 mV vs 2.833 mV before) — record [`20260801-231346-960f726`](../sim/trim-coverage/records/20260801-231346-960f726.md), Section 5a |
| `sim/mc-untrimmed/` re-run; 3σ spread stays inside 24.0 mV | **PASS** at all three temperatures — 16.22/16.36/16.81 mV (was 14.89/15.12/15.82 mV; rose because the MOS/BJT `gm/Id` effect outweighs the resistor-line improvement, still 30–32 % margin) — record [`20260801-232002-960f726`](../sim/mc-untrimmed/records/20260801-232002-960f726.md), Section 5a |
| `sim/amp-loop-stability/`, `sim/amp-psrr/`, `sim/startup/` re-run — pole locations move with branch currents | **PASS** all three, 81/81 each — PM worst 95.489° (≥45°), no Nyquist critical-axis crossing; `psrr_worst_db` 73.805 dB worst (>60 dB); startup 8.96–28.19 µs (≪1 ms) — records [`20260801-231150-960f726`](../sim/amp-loop-stability/records/20260801-231150-960f726.md), [`20260801-231234-960f726`](../sim/amp-psrr/records/20260801-231234-960f726.md), [`20260801-230933-960f726`](../sim/startup/records/20260801-230933-960f726.md) |
| `design/bandgap_error_budget.md` Sec 5 and `design/bandgap_operating_point.md` §4.3 updated; no `spec/` changes | **Done** — this document (Sections 3, 5, 5a, 6.3) and `design/bandgap_operating_point.md` (header, §2, §4.3, §6); nothing under `spec/` touched, no `tb.json` threshold altered |

### 6.4 #96 (re-null `R1` for temperature coefficient)

| Criterion | Status |
|---|---|
| `R1`/`R2` (and/or the trim network) re-derived against an explicit TC target, not just the quiescent-current target #61 solved for | **Done** — `R1` alone re-derived against a corner-swept, Chebyshev-optimum TC objective (`R1 = 78470.5 Ω`, was `82779.0 Ω`); `R2` and the trim network deliberately untouched — Section 5b |
| Fresh `sim/output-voltage-tc/` full-PVT (81-corner) run passes the ratified `≤ 50 ppm/°C` TC row at every corner, or the shortfall is re-scoped through a new decision record | **PASS** 81/81 — **13.56–29.84 ppm/°C** (record [`20260803-024632-294fb1d`](../sim/output-voltage-tc/records/20260803-024632-294fb1d.md)); no `spec/` decision record needed — Section 5b |
| Same run's accuracy-window check (1.176–1.224 V) passes at every corner, or any residual failure is explicitly re-attributed | **PASS** 81/81 — **1.18142–1.20185 V**, same record; closes the 6 corner failures (125 °C `res_ff`/`bjt_ss`) this issue was filed against — Section 5b |
| `design/bandgap_operating_point.md` and `design/bandgap_error_budget.md` updated to reflect the new sizing and the now-closed rows | **Done** — this document (Sections 5, 5b, 6.4) and `design/bandgap_operating_point.md` (header, §2 "Update (#96)", §6) |
| Regression check against every other already-passing bench (`sim/iq/`, `sim/psrr-dc/`, `sim/startup/`, `sim/line-regulation/`), same discipline #61 followed | **PASS**, all four, 81/81 (27/27 for `sim/line-regulation/`) — Section 5b's table; `sim/startup/`'s embedded testbench needed its own lumped-resistor fix first (Section 5b) to be a valid check at all |
| No `spec/` changes | **Done** — nothing under `spec/` touched, no `tb.json` threshold altered |
| Untrimmed mismatch-MC mean (`sim/mc-untrimmed/`) explicitly out of scope | **Done** — Section 5b's closing note; tracked as a documented follow-on, same as #61 left it |
