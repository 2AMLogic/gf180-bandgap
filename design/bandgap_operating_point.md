# bandgap_top operating point (issues #8, #10, #11, #42, #55, #61)

Schematic entry for the ratified Brokaw-cell bandgap
([DR-0001](../spec/decision-records/0001-bandgap-topology-selection.md)):
`design/bandgap_core.sch`, `design/bandgap_amp.sch`, `design/bandgap_top.sch`,
`design/bandgap_startup.sch` (+ matching `.sym` symbols). This document
records the operating-point assumptions, cites the `sim/` evidence they are
grounded in, and states every caveat that applies before the numbers here can
be treated as final.

**Scope**: schematic entry (#8); the amplifier offset/mismatch budget and
loop-stability/PSRR verification (#10, then **#42**); the **core
mirror/cascode mismatch budget and sizing (#55)** — both in
[`design/bandgap_error_budget.md`](bandgap_error_budget.md); a
current-sensing, self-disabling startup circuit verified across the full PVT
matrix (#11); and **co-scaling `R1`/`R2`/the trim network by `k = 2` to close
the ratified quiescent-current row (#61)**, which #55 proved mirror sizing
alone could not do — `bandgap_error_budget.md` Sec 5/5a.

Four ratified target-spec rows are now directly evaluated here, and nothing
else is:

- **Startup time** (README.md's Startup row) — verified by #11's benches,
  re-verified in #42 against the redesigned amplifier, again in #55 against
  the resized core, and again in #61 against the co-scaled `R1`/`R2`/trim
  network; **passes** (8.96–28.19 µs against 1 ms, #61), see §3a and §4.2.
- **PSRR** — **passes** as of #42 and improves again in #55 (86.98 dB worst
  of 81 PVT points on the amp-loop bench, 87.07 dB on the whole-block
  `sim/psrr-dc/` bench, against the ratified >60 dB DC–1 kHz row); #10's
  recorded shortfall is closed and #61's re-run confirms it holds (worst
  73.805 dB on `sim/amp-psrr/`'s own per-band figure) at the halved current.
  See §4.1, §4.3 and `bandgap_error_budget.md` Sec 3.
- **Quiescent current** — **passes as of #61**: co-scaling `R1`/`R2`/the
  trim network by `k = 2` halves the design current and closes the row at
  **34.01 µA** worst-corner against < 50 µA (was 65.71 µA after #55, a known
  miss). §4.3 and `bandgap_error_budget.md` Sec 5/5a give the closed-form
  reason mirror sizing alone could not do this, and the resistor-based lever
  that did.
- **Untrimmed accuracy** — the *mismatch spread* allocation now covers
  every device group in the block and closed at 17.19 mV against the
  ratified 24.0 mV (3σ) as of #55; the circuit-level mismatch Monte Carlo
  over *all* devices measured 14.89 / 15.12 / 15.82 mV (3σ) at
  −40/27/125 °C there, and **#61's re-run measures 16.22 / 16.36 / 16.81 mV
  (3σ)**, still passing at every temperature with 30–32 % margin — the small
  rise is the MOS/BJT mismatch line's `gm/Id` effect at the lower operating
  current, only partly offset by the resistor line's Pelgrom-law
  improvement; `bandgap_error_budget.md` Sec 5a has the full breakdown. What
  still misses is the distribution's **centre**: the mean moved from
  1.222–1.244 V (pre-#61) to **1.207–1.219 V** untrimmed against 1.200 V —
  closer, from the `−VT·ln k` shift of `VEB(Q3)`, but still a trim/resistor
  question rather than a mismatch one, and #61 deliberately did not
  re-centre it (see "Not in scope" in issue #61). See
  `bandgap_error_budget.md` Sec 2.6a, 2.7, 2.8, 5, 5a.


## 1. Topology

`bandgap_top` = `bandgap_core` (matched vertical-PNP pair, PTAT/CTAT summing,
and the **cascoded** 4-leg current-mode bias/output stage DR-0001 calls for)
servoed by `bandgap_amp` (a real-device **telescopic-cascode OTA with
explicit dominant-pole compensation**, #42 — §2, §4.1; #8 entered and #10
resized a 5-transistor single-stage OTA, which #42 replaced) and kicked out
of the degenerate state by `bandgap_startup` (§1a), per DR-0001.

```
                      vdd
                       |
        +------+-------+-------+-------+--------+
        |      |       |       |       |        |
       M1     M2      M3      M4       |       MCB (diode, gate=drain=casc,
        |      |       |       |       |        |     W/L scaled for
       d1     d2      d3      d4       |        |     Vsg ~ Vth + 2*Vov)
        |      |       |       |       |        |
      MC1    MC2     MC3     MC4       |      casc ----+---------+
        |      |       |       |       |        |      |         |
      sns1    sns2    vref   ibias     |       MNB (gate=ibias)   | (casc also
        |      |       |       |       |        |                 |  gates
       Q1     R2      R1      Mn5      |       vss           MC1..MC4)
        |      |       |    (diode,    |
       (C,B    e2     e3    gate=drain |
        =vss)   |       |    =ibias)   |
                Q2      Q3      |      |
                (C,B    (C,B   vss     |
                 =vss)   =vss)         |

   M1..M4  gates all tied to "fb"  (driven by bandgap_amp.out)
   MC1..MC4 gates all tied to "casc" (from the MCB/MNB bias generator)
```

- **Q1** = `pnp_05p00x05p00` (unit, 25 µm² drawn emitter), diode-connected
  (base = collector = `vss`, emitter = `sns1`).
- **Q2** = `pnp_10p00x10p00` (100 µm² drawn emitter, 4:1 drawn ratio vs Q1),
  diode-connected, emitter through **R2** to `sns2`.
- **Q3** = `pnp_05p00x05p00` (same unit device as Q1), diode-connected,
  emitter through **R1** to `vref` — the output-branch "reference" device.
- **M1–M4** = `pfet_03v3`, identical sizing, gates tied to the common
  node `fb` (the amp's output). The amp forces `sns1 == sns2`; because M1
  and M2 share the same `Vgs` (same gate, same source) and the amp forces
  the same drain-side condition, M1 and M2 carry equal current
  unconditionally. That, combined with `V(sns1) = VEB(Q1)` and
  `V(sns2) = VEB(Q2) + I·R2`, forces the classic PTAT relation
  `ΔVBE(I) = I·R2`.
- **MC1–MC4** = `pfet_03v3` cascode devices, same sizing as M1–M4, gates
  tied to the common node `casc`. Each mirror leg is `M<n>` in series with
  `MC<n>`, so every branch node (`sns1`, `sns2`, `vref`, `ibias`) is driven
  from a cascode drain rather than directly from a mirror drain. This is
  DR-0001's "cascoded current-mode output/bias stage": the cascodes hold
  all four mirror drains (`d1`…`d4`) at essentially the same potential
  (measured spread 0.33 mV at nominal, §3) regardless of where the branch
  node itself sits, so the legs the amp does *not* servo track the ones it
  does far more closely than an uncascoded mirror's finite output impedance
  allows — see §3's leg-matching measurement and §4.3's remaining caveat.
- **MCB/MNB** = the wide-swing cascode-bias generator. MCB is a
  diode-connected `pfet_03v3` from `vdd` (gate = drain = `casc`); MNB is an
  `nfet_03v3` sinking a 1/4-scaled copy of the core's own bias current from
  `casc` to `vss` (gate = `ibias`, so it mirrors Mn5). `casc = vdd −
  Vsg(MCB)`, and MCB's `W/L` is scaled so that `Vsg(MCB) ≈ Vth + 2·Vov` —
  the classic wide-swing cascode bias point, which leaves each mirror
  device roughly one `Vov` of `Vsd` (measured margins in §3). The generator
  is deliberately self-biased off `ibias` rather than from an independent
  reference, for the same reason the amp's tail is: in the degenerate
  zero-current state the cascode bias must collapse along with the rest of
  the loop rather than artificially propping it up (§4.2).
- **M3/R1/Q3** (the output branch) and **M4/Mn5** (the tail-bias
  generator, feeding `bandgap_amp.tail_bias`) share the gate nodes `fb` and
  `casc` but are **not** individually servoed by the amp — the cascode is
  what makes them track (§3), not the servo loop.
- **Why the PNP collector is grounded**: gf180mcu's vertical PNP collector
  is the p-substrate; every instance on the die shares one substrate node,
  which must sit at (or below) the lowest potential in use — the same
  diode-connected (`base = collector = vss`) convention
  `sim/device-pnp-vbe/testbench/tb_pnp_vbe.spice` uses to characterize these
  devices. A floating-base "classic textbook" Brokaw cell (collector pulled
  up through a resistor) is not physically realizable with this device; the
  emitter is therefore the "high" terminal driven by the mirror, and the
  amp servos the two emitter-side mirror-drain nodes (`sns1`, `sns2`)
  instead of two collector nodes.

### 1a. Startup circuit (issue #11)

`bandgap_startup` (`design/bandgap_startup.sch`/`.sym`) is instantiated in
`bandgap_top` alongside `bandgap_core` and `bandgap_amp`, per DR-0001's
current-sensing, self-disabling design. Four devices:

- **XMSENSE** (`nfet_03v3`, W=20 µm/L=2 µm) — gate tied to `ibias`,
  deliberately sized to replicate `bandgap_core`'s own Mn5, so it turns on at
  essentially the same `ibias` that Mn5 itself needs to carry the core's
  design current. Drain drives the internal `det` node.
- **XRPU** (`ppolyf_u_1k`, W=2 µm/L=4000 µm, ≈2 MΩ) — an always-on pull-up
  from `vdd` to `det`, per device-characterization.md §2's explicit
  recommendation to use `ppolyf_u_1k` for "non-ratio-critical bulk
  resistance (start-up bleeder, …)". This is the startup circuit's *entire*
  static Iq contribution once disengaged (§4.2) — it is local to the detect
  node, never injecting current into the core's own bias nodes, so it is not
  the "continuously-conducting bleeder into the core" DR-0001 rejects.
- **XMKFB** / **XMKCASC** (`nfet_03v3`, W=2 µm/L=2 µm each) — gates tied to
  `det`, drains tied to `bandgap_core.fb` and `bandgap_core.casc`
  respectively. While `det` is high (degenerate state), both kick devices
  pull their target node to `vss`, forcing the PMOS mirror (`fb`) and
  cascode stack (`casc`) on. **Both** nodes must be kicked, not just `fb`:
  the core's self-biased topology collapses `fb` *and* `casc` together in
  the degenerate state (see `bandgap_core.sch`'s comment), so a kick that
  only pulls `fb` low leaves MC1–MC4 off (`Vsg(MCn) = d<n> − casc = 0`) and
  no current ever reaches `sns1`/`sns2`/`vref`/`ibias`.

`bandgap_core` exposes a new `casc` pin (an internal-wiring addition, not a
`bandgap_top` pin — see §5) specifically so the startup circuit can drive it.
Self-starting fail-safe default: at power-up (`ibias = 0`, MSENSE off), XRPU
pulls `det` toward `vdd`, so the kick is "on" unless proven unnecessary.
Self-disabling: once `ibias` rises past MSENSE's own threshold, MSENSE
overpowers XRPU and clamps `det` low, turning the kick devices off. See §3a
for the full-PVT verification of this behavior and §4.2 for the
degenerate-state existence/removal evidence.

## 2. Device values and citations

All bias-point numbers below cite
[`design/device-characterization.md`](device-characterization.md) (issue #4)
by record ID.

| Quantity | Value | Source |
|---|---|---|
| PNP pair | `pnp_05p00x05p00` / `pnp_10p00x10p00`, 4:1 drawn | DR-0001; §1 of device-characterization.md |
| Effective area ratio (not 4.00) | 3.634 | record `20260731-030932-8fb0ea6` |
| ΔVBE at 10 µA, 27 °C | 33.374 mV | record `20260731-030932-8fb0ea6` |
| ΔVBE PTAT slope | 115.13 µV/°C | record `20260731-030932-8fb0ea6` |
| VEB(5×5) at 10 µA, 27 °C | 0.7227 V | record `20260731-030932-8fb0ea6` |
| CTAT slope dVEB/dT at 10 µA | −1.716 mV/°C | record `20260731-030932-8fb0ea6` |
| Usable emitter-current window (5×5) | ≈0.07 nA … 28 µA | record `20260731-030932-8fb0ea6` — 10 µA sits well inside |
| Resistor flavor | `ppolyf_u` | recommendation in device-characterization.md §2, record `20260731-031750-8fb0ea6` |
| MOS input-pair mismatch (10/4) | σ(ΔVgs) 1.098 mV (3σ 3.29 mV) | record `20260731-031718-8fb0ea6` — cited for `bandgap_amp`'s input pair, sized 10/4 to match |
| PNP-pair mismatch (5×5/10×10, 10 µA) | σ(ΔVBE) 0.0426 mV (3σ 0.128 mV) | record `20260731-040850-187a336` |

Chosen design point: **I ≈ 10 µA per core branch**, matching the 10 µA row
of the #4 PNP-VBE campaign directly (no interpolation needed for VEB/ΔVBE/
slope citations). This current is not an independent free parameter — it
falls out of solving `ΔVBE(I) = I·R2` for the fixed R2 below; R2 was picked
so that the resulting equilibrium current lands on the characterized 10 µA
point.

**Update (#61).** The design current is no longer 10 µA. `bandgap_error_budget.md`
Sec 5 shows in closed form that no mirror-sizing lever can close the ratified
quiescent-current row, because `I = ΔVBE/R2` has no mirror-geometry
dependence — the only lever is `R1`/`R2` (and the trim network) themselves.
`R1`, `R2` and `bandgap_trim.sch`'s 63 unit segments are co-scaled by
`k = 2`, halving the per-branch current to **≈ 5 µA** at `tt`/27 °C (measured
5.05 µA, `sim/iq/` and `sim/startup/` per-branch figures agree with the
`ΔVBE/R2` prediction to within 0.3 %). This moves the design current off the
exactly-10 µA point the citations above were taken at, but not off the
characterized *window*: 5 µA remains deep inside the ≈0.07 nA…28 µA usable
emitter range the same record (`20260731-030932-8fb0ea6`) reports, more than
three decades from either edge. `ΔVBE` and `VEB`'s CTAT slope are otherwise
unaffected in this document's first-order model — they are the PNP pair's
own diode-law behaviour at whatever current a Brokaw cell servos to — and
`sim/output-voltage-tc/`'s re-run (§6, `bandgap_error_budget.md` Sec 5a) is
the actual check that the block's TC did not regress off that assumption
rather than take it on faith.

### Resistors

`ppolyf_u`, `W = 2 µm` (≥ 2 µm per device-characterization.md §2's matching
recommendation), built up as a single series length here (unit-segment
decomposition for common-centroid layout is #16's job):

| Resistor | Drawn geometry | Simulated value (this design's own netlist, `tt`, 27 °C) | Role |
|---|---|---|---|
| R2 | `r_width=2u r_length=18u` (9 squares) | 3293.2 Ω | PTAT: sets `I = ΔVBE(I)/R2` |
| R1 | `r_width=2u r_length=280u` (140 squares) | 50334.7 Ω | Output-branch CTAT/PTAT summing resistor |

R1/R2 ratio = 15.28. These are **measured directly from this design's own
ngspice netlist** (a two-terminal DC op-point check at 50 mV bias, same
method as `sim/device-resistor-tc/`), not interpolated from the
device-characterization table's W=1 µm/W=5 µm data points — a W=2 µm point
was not characterized there, and re-deriving the value from a first-principles
simulation of the actual drawn geometry removes that interpolation error.
Final sizing/trim (#10/#14) should re-derive from the full corner/mismatch
sweep rather than this single nominal measurement.

**Update (#61).** This table is #8's pre-trim baseline and is retained
unedited; the drawn geometry above is no longer what is on the schematic.
`R2` is now `L=36.341871 µm` (6586.5 Ω) and `R1` is `L=460.701871 µm`
(82779.0 Ω) — each length *solved* for the target resistance rather than
doubled directly, because `ppolyf_u` is a compound device
(`R = 179.547·L_um + 61.382 Ω` at `W=2 µm`, `tt`/27 °C) and a 2× length is
not a 2× resistance for one. `R1_total/R2 = 15.28425` to 5 decimal places,
unchanged from the ratio above. `bandgap_trim.sch`'s 63 unit segments are
co-scaled the same way (`L=1.215 µm → 2.771871 µm`, 279.53 Ω → 559.06 Ω) so
a trim step keeps its value in volts. Full derivation, measured results and
the closed-form reason mirror sizing could not have done this instead:
`bandgap_error_budget.md` Sec 5/5a.

### Mirror (core) and amp devices

Core mirror/cascode sizing (`M1`–`M4`/`MC1`–`MC4`/`M5`) is **budgeted and
final as of #55** — `design/bandgap_error_budget.md` Sec 2.6a derives the
`∂Vref/∂ΔVgs` sensitivity on this circuit's own netlist, sizes the devices
against an explicit area budget, and Sec 2.6b records the full-PVT headroom
verification §4.3 asked for. `MCB`/`MNB` remain simulation-picked rather
than budgeted, but are now verified over the whole grid rather than 7 spot
points — see §4.3 for exactly what is and is not closed. Amp sizing (the amp
rows) is **final** as of #42's topology change — see
[`design/bandgap_error_budget.md`](bandgap_error_budget.md) Sec 2 for the
full derivation, sensitivity measurement, and why sizing was not pushed
further. Device names `M1`–`M5` are reused independently inside
`bandgap_core` and `bandgap_amp` (each subcircuit's own local numbering);
the `(core)`/`(amp)` qualifiers below disambiguate.

| Device | Type | Size | Role |
|---|---|---|---|
| M1–M3 (core) | `pfet_03v3` | **W=60 µm, L=6 µm, m=1** (was 20/2) | Core current mirror, the three signal legs (`sns1`, `sns2`, `vref`) — **budgeted (#55)**: 360 µm² of gate area each, chosen so this line's 3σ contribution to `Vref` (6.36 mV) is under half the amplifier's, `W/L = 10` held so `Vov` is unchanged. `bandgap_error_budget.md` Sec 2.6a |
| MC1–MC3 (core) | `pfet_03v3` | **W=60 µm, L=6 µm, m=1** (was 20/2) | Cascodes on those three legs. Kept identical to `M1`–`M3` — still one matching group for #16's common-centroid layout, but now because the measured cascode-only sensitivity (−0.0133 V/V, 274× below the mirror's) says nothing is bought by sizing them differently, not for want of a number |
| M4, MC4 (core) | `pfet_03v3` | **W=7.5 µm, L=6 µm, m=1** (was 20/2) | The `ibias`-only leg. Sized *down* deliberately: `W/L = 1.25` against the signal legs' 10, so it carries 1/8 of the design current at the same `Vov`. Licensed by the measured `∂Vref/∂δ(M4) ≈ −8e−5 V/V` — this leg's mismatch does not reach `Vref` — and taken as the quiescent-current lever `bandgap_error_budget.md` Sec 5 quantifies |
| MCB (core) | `pfet_03v3` | W=4 µm, L=12 µm (unchanged) | Diode-connected cascode-bias device (see sizing derivation below). Still **simulation-picked, not budgeted**, but now verified in saturation with ≥ +858.9 mV of margin at all 81 PVT points, not 7 — §4.3 |
| MNB (core) | `nfet_03v3` | W=5 µm, L=2 µm (unchanged) | Cascode-bias current sink; 2× Mn5's W/L after #55's rescale, so it still draws ≈2.5 µA at nominal — its bias is set by the `ibias` node voltage, which #55 deliberately preserved |
| Mn5 / `M5` (core) | `nfet_03v3` | **W=2.5 µm, L=2 µm** (was 20/2) | Diode-connected `ibias` generator for the amp tail, MNB and the startup sense device. Rescaled by the same 1/8 as `M4` so `Vov(M5)` — and therefore the `ibias` node voltage every one of those consumers mirrors off — is unchanged. Verified: `v_ibias_op` = 0.758 V at nominal (§3's pre-#55 value: 0.75 V), amp tail 2.775 µA (#42: 2.66 µA) |
| M1, M2 (amp input pair) | `nfet_03v3` | W=200 µm, L=4 µm, nf=4 | **Final (#42).** 2x #10's gate area (20x #8's). L unchanged from the #4 MOS-mismatch characterization geometry (`20260731-031718-8fb0ea6`) so `A_pair` applies with no L-extrapolation; `nf=4` keeps each 50 µm finger inside the *same* width bin #10's 100 µm/nf=2 device used. Still the largest single term in the offset budget — `bandgap_error_budget.md` Sec 2.2, 2.7 |
| MC1, MC2 (amp NMOS cascodes) | `nfet_03v3` | W=20 µm, L=16 µm | **New (#42).** Cascodes on the input-pair drains, gate = `ncasc`. This is the device that fixes PSRR: the amp's supply-referred input error is `1/(gm1·Ro,nmos)` and depends on *only* the NMOS branch's output impedance — `bandgap_error_budget.md` Sec 2.1, Sec 3.4 |
| M3, M4 (amp mirror load) | `pfet_03v3` | W=20 µm, L=16 µm | **Final (#42).** 2x #10's gate area at 1/8 the W/L: the mirror's input-referred mismatch contribution scales as 1/L₃, and measured `gm3/gm1` falls 0.689 → 0.283 — `bandgap_error_budget.md` Sec 2.1, 2.2 |
| MC3, MC4 (amp PMOS cascodes) | `pfet_03v3` | W=40 µm, L=16 µm | **New (#42).** Wide-swing cascodes on the mirror load, gate = `pbias`. Buys back the `Vsd` headroom the low-gm mirror needs (measured 191 mV of saturation margin at nominal) and equalizes the two mirror drains to within 4 µV, removing a systematic mirror-ratio error the plain mirror had |
| M5 (amp tail) | `nfet_03v3` | W=10 µm, L=4 µm | Unchanged from #8. Gate driven by `bandgap_core.ibias`, not an independent bias — see §4.2 |
| MBN2 / MBP1 (amp bias rail) | `nfet_03v3` W=2 µm L=16 µm / `pfet_03v3` W=1 µm L=50 µm | | **New (#42).** Ground-referenced sink off `tail_bias` into a PMOS diode, generating the vdd-referenced cascode-bias rail `pbias`; 0.139 µA at nominal |
| MB1 + MBD1/MBD2 (amp `ncasc` generator) | `pfet_03v3` W=5 µm L=50 µm + 2 × `nfet_03v3` W=1 µm L=4 µm | | **New (#42).** MB1 mirrors MBP1 into two stacked NMOS diodes, giving the **ground-referenced** `ncasc` the NMOS cascodes require. 0.725 µA at nominal — the largest single Iq addition, see §4.3 |
| CC (amp compensation cap) | `cap_mim_2f0_m4m5_noshield` | 60 µm × 60 µm (≈7.2 pF) | **New (#42).** Dominant-pole compensation from `out` to **vdd** (not vss: `out` must track vdd for supply rejection). Without it the cascoded loop encircles its Nyquist critical point and oscillates — `bandgap_error_budget.md` Sec 4.3–4.5. The 5LM MIM model name is used explicitly; the xschem symbol's own `cap_mim_2f0fF` default lives in a `.LIB` section the corner runner does not load |

**MCB sizing derivation.** Wide-swing cascode bias wants
`Vsg(MCB) ≈ Vth + 2·Vov`, i.e. `Vov(MCB) ≈ 2·Vov(M1)` at MCB's own current.
Since `Vov ∝ √(I / (W/L))`, running MCB at `I/4` (set by MNB) and asking for
twice the overdrive means `(W/L)_MCB = (1/16)·(W/L)_mirror` under square-law
— 10 → 0.625. These devices are not squarely square-law at 10 µA, so the
final value was picked by simulation rather than by the hand formula: at
`W/L = 0.625` the mirror devices landed marginally *inside* triode
(`Vds − Vdsat = −2 mV` at nominal), so MCB was narrowed to
`W = 4 µm / L = 12 µm` (`W/L = 0.333`), which puts `Vds − Vdsat = +158 mV`
on M1 at nominal and keeps every mirror and cascode device in saturation at
all 7 corner/temperature/supply spot-checks in §3. This is a provisional
sizing choice made by simulation, not a budgeted one. (**#55**: MCB itself
is unchanged and this derivation still stands; what changed is that its
consequence is now verified over all 81 PVT points instead of 7 — M1's
`Vds − Vdsat` reads +169.3 mV at nominal and never falls below +122.7 mV
anywhere on the grid, MCB's own margin never below +858.9 mV. §4.3.)

**Update (#55).** That last paragraph used to read "none of these sizes are
offset-budgeted or headroom-verified as a *design margin*". For the mirror
and cascode devices it no longer holds: `M1`–`M4`/`MC1`–`MC4`/`M5` are
offset-budgeted in `bandgap_error_budget.md` Sec 2.6a, and headroom is
verified over the **full 81-point PVT grid** — worst case **+122.7 mV** of
`Vds − Vdsat` on `M1` at `res_ss`/−40 °C/2.97 V, the exact PMOS-stack corner
`design/device-characterization.md` §3 flags, with `MCB` at ≥ +858.9 mV
(record
[`20260801-132317-cfd0146`](../sim/core-mirror-sensitivity/records/20260801-132317-cfd0146.md)).
`MCB`'s own `W/L` is still a simulation-picked value rather than a derived
one — see §4.3 for that remaining item, and for the startup devices, which
are unchanged and still verified-but-unbudgeted.

### Startup devices (issue #11)

| Device | Type | Size | Role |
|---|---|---|---|
| XMSENSE | `nfet_03v3` | W=20 µm, L=2 µm, m=1 | Current-sense device, replicates `bandgap_core.Mn5` so it activates at the same `ibias` Mn5 needs to carry the design current |
| XRPU | `ppolyf_u_1k` | W=2 µm, L=4000 µm (≈2 MΩ) | Always-on pull-up, `vdd → det`; sized so its own steady-state current (once MSENSE clamps `det` low) is the startup branch's entire itemized residual Iq (§3a) |
| XMKFB | `nfet_03v3` | W=2 µm, L=2 µm, m=1 | Kick device, `det → bandgap_core.fb` |
| XMKCASC | `nfet_03v3` | W=2 µm, L=2 µm, m=1 | Kick device, `det → bandgap_core.casc` |

These sizes were picked by simulation against the full PVT matrix (§3a), not
by a first-principles headroom/offset budget — in the same "provisional but
verified" sense as the cascode-bias generator (§4.3), the startup circuit's
*function* is proven across all 81 corners, but its sizing has not been
re-derived against a mismatch/margin budget the way #10 did for the
amplifier (`design/bandgap_error_budget.md`). #10's scope was the amp only,
so the startup branch is still verified-but-unbudgeted. (The core
mirror/cascode used to be listed alongside it here; as of #55 it is
budgeted — §4.3.)

## 3. Smoke-test result

Nominal (27 °C, 3.3 V, `tt`) op-point, via `sim/bandgap-loop-smoke/`, record
[`20260801-013804-259a8e0`](../sim/bandgap-loop-smoke/records/20260801-013804-259a8e0.md)
(clean-tree run against the commit that added the cascode; supersedes
`20260731-232056-d6e10b7`, the pre-cascode run — that record is retained
unedited per `sim/README.md`'s append-only convention). If the smoke test is
re-run, the new record supersedes this one — check that experiment's
`records/` directory for the latest ID rather than assuming this citation is
current forever.

**Note (#55):** the bench was re-run against the resized core, record
[`20260801-150433-cfd0146`](../sim/bandgap-loop-smoke/records/20260801-150433-cfd0146.md)
(clean tree; nominal-corner subset, with the reason recorded in the record's
own **Corner matrix run** field — the PVT-matrix claims are carried by
`sim/core-mirror-sensitivity/`, `sim/iq/`, `sim/startup/` and `sim/psrr-dc/`,
not by this bench). Against the table below it reads `vref` **1.22904 V**
(was 1.2291), `fb` **2.26833 V** (was 2.2727), `sns1`/`sns2`
**0.722825 / 0.722568 V** (was 0.72283 / 0.72258), total supply current
**35.62 µA** (was 44.3). The **operating point did not move** — `vref` by
60 µV, the servo residual by 3 µV — which is the `W/L = 10`-invariance claim
in `bandgap_error_budget.md` Sec 2.6a holding on the real circuit; the
supply-current drop is the `ibias` leg's deliberate 1/8 rescale.

**Note (#10):** the table below predates #10's amplifier resize (Section 2)
and reflects #8's provisional 10 µm/4 µm amp, not the final sizing —
`sim/bandgap-loop-smoke/` is #8's own experiment and re-running it against
the resized amp is out of #10's scope. For a nominal op-point against the
*current* (final) amp, see `sim/amp-offset-sensitivity/records/20260801-034212-c26da47.md`'s
`vref_at_zero_ish` column (≈1.227 V at `tt`/27 °C/3.30 V, within ~0.15 % of
the number below — the resize did not materially move the nominal
operating point) or `design/bandgap_error_budget.md` Sec 2.5's directly
cited `R1·I = 0.506 V` nominal figure.

| Node | Simulated value |
|---|---|
| `vref` | **1.2291 V** |
| `fb` (common mirror gate) | 2.2727 V |
| `casc` (common cascode gate) | 1.7485 V |
| `d1` … `d4` (mirror drains / cascode sources) | 2.93420 / 2.93420 / 2.93452 / 2.93422 V |
| `sns1` (Q1 branch, VEB(Q1)) | 0.72283 V |
| `sns2` (Q2 branch, top of R2) | 0.72258 V |
| `e2` (Q2 emitter, VEB(Q2)) | 0.68945 V |
| Per-branch current (M1/M2/M3/M4 legs) | 10.0586 / 10.0586 / 10.0584 / 10.0586 µA |
| Cascode-bias branch current (MCB/MNB) | 2.533 µA |
| Total supply current | 44.3 µA |

`sns1 ≈ sns2` (0.25 mV residual) confirms the servo is working. `ΔVBE =
sns1 − e2 = 33.378 mV`, matching the #4 citation (33.374 mV at 10 µA, 27 °C)
to within 0.004 mV — confirming the branch current landed almost exactly on
the intended 10 µA design point.

**What the cascode bought (informal spot-check, not recorded evidence).**
Re-running the same nominal op-point against this branch's pre-cascode
netlist (commit `9fb51c3`) and comparing the systematic current error
between the servoed leg (M1) and the *un*servoed output leg (M3):

| Corner / temp / supply | (I(M3) − I(M1)) / I(M1), uncascoded | …cascoded | M1 `Vds − Vdsat` (cascoded) |
|---|---|---|---|
| `tt` 27 °C 3.30 V | −0.294 % | −0.0018 % | +158 mV |
| `tt` −40 °C 3.30 V | −0.254 % | −0.0021 % | +114 mV |
| `tt` 125 °C 3.30 V | −0.349 % | −0.0016 % | +226 mV |
| `ss` −40 °C 2.97 V | −0.286 % | −0.0028 % | +102 mV |
| `ss` 125 °C 2.97 V | −0.397 % | −0.0021 % | +205 mV |
| `ff` −40 °C 3.63 V | −0.232 % | −0.0016 % | +130 mV |
| `ff` 125 °C 3.63 V | −0.322 % | −0.0014 % | +255 mV |

That is a ~130× reduction in the systematic leg-matching error, and every
mirror and cascode device stays in saturation (positive `Vds − Vdsat`) at
every point spot-checked, including the `ss` / −40 °C / 2.97 V worst case
for PMOS headroom that device-characterization.md §3 flags. Cost: one extra
bias branch, ≈2.5 µA (total 41.7 → 44.3 µA at nominal).

**What it did *not* buy, at this provisional sizing.** DC line sensitivity
`dVref/dVdd` measured over 2.97 → 3.63 V at `tt`/27 °C is 2.61 mV/V
uncascoded and 2.88 mV/V cascoded (≈52 dB vs ≈51 dB) — i.e. essentially
unchanged. At this sizing the supply sensitivity of the loop is dominated by
the *provisional amp's* own supply rejection and offset drift, not by the
mirror's output impedance, so the cascode's PSRR benefit does not show up
yet. **Neither number is a PSRR claim**: there is no PSRR testbench (#12),
this is a two-point DC line-sensitivity spot-check at one corner, and the
amp is unsized (#10). It is recorded here only so that #10 knows where the
supply-sensitivity bottleneck currently sits.

**Expected window and why it is wide:** this smoke test's acceptance bound
is **1.15 V – 1.35 V**, not README.md's ratified ±2% target-spec window
(1.176–1.224 V). The wider bound is deliberate: R1/R2 here are a first-pass
hand calculation (§2), not a trimmed, offset-budgeted, corner-swept
sizing — landing "in the classic ~1.2 V ballpark, right sign, right order of
magnitude" is the actual bar for a schematic-entry existence proof. The
simulated 1.2291 V sits comfortably inside the wide bound and 0.42%
above the ratified spec's own upper bound, which is a good early sign for
#10 but is **not** a spec-conformance claim (see §6).

**Informal temperature check (not a recorded PVT sweep):** re-running the
same nominal-supply op-point at `tt`/−40 °C and `tt`/125 °C (informal check
only, not entered as `sim/` evidence, since a full PVT/mismatch sweep is
explicitly out of scope for this issue) gives 1.2187 V and 1.2383 V
respectively — a chord slope of about +0.12 mV/°C, i.e. near-flat and
slightly over-compensated, consistent with the §2 hand estimate
(`−1.716 mV/°C + 15.28 × 0.11513 mV/°C ≈ +0.044 mV/°C`; the two-point
chord measurement differs from the hand estimate by second-order effects
this first-pass sizing does not capture). This is presented purely as
sizing-sanity context for #10, not as a TC claim.

**Informal convergence check (not a recorded PVT sweep):** the same deck was
also swept over the harness's full 81-point grid (9 corners × 3 temperatures
× 3 supplies) with `--no-write`, purely to confirm the added cascode stack
does not break DC convergence anywhere; all 81 points converged, with `vref`
spanning 1.2142–1.2523 V. That is **not** entered as evidence and is **not**
a TC/line-regulation claim — an untrimmed, unsized loop (regardless of
startup-circuit status, which #11 later resolved separately, see §3a/§4.2)
has no business making one (§6). It is here only to document that the
cascode was checked for convergence/headroom robustness, not just at
nominal.

## 3a. Startup verification (issue #11)

Four full-PVT (81-point: 9 process corners × 3 temperatures × 3 supplies)
experiments verify the startup circuit. Measurement convention, stated once
and used consistently: **t=0** is the time `vdd` crosses 90% of its final
(per-corner) value; **settled** is the last time `v(vref)` exits ±1% of its
own final simulated value, computed as a genuine backward scan from the end
of the run (so a late re-entry — chattering — after an apparent early settle
pushes the reported time later rather than being missed). All four are
**Overall: PASS**, 81/81 points each.

> **Superseding note (#42 integration).** The records cited below are the
> **third** run of all four experiments, taken against **#42's
> telescopic-cascode amp** (§2). They supersede the #10-amp records
> (`…-5ac97dc`), which superseded the #8-amp records (`…-fbfa3f1`); both
> earlier generations are retained unedited per `sim/README.md`'s
> append-only rule and must not be cited as current evidence. The amp
> change moves the numbers again — worst-case fast-ramp startup 25.5 µs →
> **37.0 µs** (still ~27× inside the ratified 1 ms bound), and the
> no-startup-circuit control now finds the block degenerate at **all 81**
> points rather than 78/81, i.e. this amp does not leakage-self-start even
> at `ff`/125 °C. The re-run also serves as #42's physical cross-check on
> loop stability (`bandgap_error_budget.md` Sec 4.6): an encircling loop
> shows up here as ringing or a wrong settled value, and did, for an
> intermediate uncompensated revision.
>
> **Superseding note (#10 integration), retained for history.** The
> `…-5ac97dc` records were the
> **second** run of all four experiments, taken against the **final (#10)
> amp sizing** (input pair W=100 µm/nf=2, mirror load W=40 µm — §2). The
> first run (record-ids `…-fbfa3f1`, 2026-08-01) was minted against #8's
> provisional 10 µm/4 µm amp, before #10 landed. Issue #11's own ordering
> note called this out in advance — "if #10 lands after this issue's
> records are minted, the amp change invalidates the recorded startup
> claims" — and it was right to: the resize moved the fast-ramp worst-case
> startup time from 3.78 µs to **25.5 µs**, a ~6.7× change, and moved which
> corner is worst. The provisional-amp records are retained unedited per
> `sim/README.md`'s append-only rule and are pointed at by each new
> record's **Supersedes** field; they must not be cited as current
> evidence.

- **`sim/startup/`** (fast ramp, 1 µs 0→final) — record
  [`20260801-073947-a7fd16a`](../sim/startup/records/20260801-073947-a7fd16a.md)
  (supersedes `20260801-040646-5ac97dc`, which superseded
  `20260801-032901-fbfa3f1`).
  `startup_time_s` ranges 17.17 µs (`sf_-40c_3.63v`) to **37.03 µs**
  (`ff_27c_2.97v`), all ≪ the ratified 1 ms bound — **~27× of margin** at
  the worst corner; `vref_final_v` is 1.217–1.260 V at every point with no
  ringing, which is the transient half of #42's stability evidence. The
  #10-amp figures the rest of this bullet quotes (1.256–25.51 µs) belong to
  the superseded record. Note the worst corner is `res_ss`/−40 °C/3.30 V,
  **not** the `ss`/−40 °C/2.97 V corner the original issue text expected —
  the Implementation guidance's "verify rather than assume" call was
  correct to make: `ss`/−40 °C/2.97 V itself settles in 6.01 µs
  (`iq_startup_branch_final_ua` = 1.134 µA, the itemized-Iq minimum across
  the whole grid — see §4.2). It is also not the same worst corner the
  provisional-amp run found (`ss`/125 °C/3.63 V), which is the concrete
  reason the re-run was necessary rather than cosmetic.
- **`sim/startup-slow-ramp/`** (slow ramp, 1 ms 0→final — the Implementation
  guidance's "classic trap" case) — record
  [`20260801-074839-a7fd16a`](../sim/startup-slow-ramp/records/20260801-074839-a7fd16a.md)
  (supersedes `20260801-040919-5ac97dc`).
  `startup_time_s` is **negative at every corner** (−111 µs to −459 µs;
  the superseded #10-amp run read −320 µs to −508 µs): the
  loop is already settled to within ±1% of its final value *before* `vdd`
  even reaches 90% of final, which is the best possible outcome for a slow
  ramp and rules out the ramp-tracking stall the guidance warns about. This
  conclusion is unchanged by the amp resize.
- **`sim/startup-state-search/`** (adversarial `.ic`/`uic` seed at the exact
  degenerate operating point — `fb`, `casc`, `d1`…`d4` pinned to 3.63 V,
  everything else 0 — `vdd` already valid DC, startup circuit **enabled**) —
  record
  [`20260801-074416-a7fd16a`](../sim/startup-state-search/records/20260801-074416-a7fd16a.md)
  (supersedes `20260801-041217-5ac97dc`).
  `recovery_time_s` ranges 2.499 µs–18.86 µs (superseded #10-amp run:
  1.254–12.87 µs); `iq_total_final_ua` gated
  `min=5` (must clear a genuine nonzero operating current, not degenerate
  leakage) and clears it everywhere (29.7–77.5 µA). The kick recovers from
  this adversarial seed at every one of the 81 points.
- **`sim/startup-disabled-control/`** (identical adversarial seed,
  `bandgap_startup` **not instantiated** — `bandgap_top`/`bandgap_core`
  wired the same way #8 originally shipped it) — record
  [`20260801-075309-a7fd16a`](../sim/startup-disabled-control/records/20260801-075309-a7fd16a.md)
  (supersedes `20260801-041607-5ac97dc`). **With #42's amp the degenerate
  state persists at all 81 points** (`vref_final_v` 0.046–0.531 V,
  `iq_total_final_ua` −0.017 to +0.103 µA): the three `ff`/125 °C
  self-starting corners the #10-amp run found are gone, so the startup
  circuit is now doing genuine work at every corner, with no
  leakage-masked pass anywhere. The rest of this bullet describes the
  superseded #10-amp run.
  This is the "(c) control run" leg of the required multi-pronged evidence:
  it observes where the degenerate state persists vs. self-starts from
  leakage alone, rather than gating a pass/fail outcome. Result: at 78 of 81
  points the block sits at `vref` in the 0.046–0.531 V range with
  `iq_total_final_ua` in the **13 pA – 177 pA** range — the degenerate state
  is physical, not a solver artifact, including at the `ss`/−40 °C/2.97 V
  corner the Implementation guidance calls out (`vref` = 0.525 V,
  `iq_total` = 16.1 pA). At exactly the 3 `ff`/125 °C points (`ff_125c_*`,
  all three supplies — **not** the partial skews `res_ff_125c_*` or
  `bjt_ff_125c_*`, which stay degenerate), leakage alone self-starts the
  loop to the intended operating point (`vref` ≈ 1.231–1.237 V,
  `iq_total_final_ua` ≈ 75.0–75.5 µA) with **no startup circuit present at
  all** — exactly the masking effect the Implementation guidance flagged
  ("ff/125 °C leakage may self-start the core — a pass there proves
  little"), now confirmed rather than assumed, and narrowed to the specific
  sub-corner where it actually happens. The 78/81-vs-3/81 split is
  identical to the provisional-amp run's: the amp resize moved the startup
  *dynamics*, not which corners are degenerate traps. Contrasting this
  record against `sim/startup-state-search/`'s (same seed, same corners,
  startup circuit present) shows the kick doing genuine work at the other
  78/81 points, not riding on leakage that was going to self-start anyway.

**Startup-branch residual current, itemized against the Iq budget.** Every
record above reports `iq_startup_branch_final_ua` — the startup branch's own
current draw after disengagement, isolated via a zero-volt ammeter tap
between the shared `vdd` rail and `bandgap_startup`'s own `vdd` pin (so it
does not include the rest of the block's current). Across the full 81-point
grid this ranges **1.134 µA** (`ss_-40c_2.97v`) to **2.391 µA**
(`ff_125c_3.63v`) — comfortably inside both the ratified < 50 µA budget and
its < 20 µA stretch target on its own. These figures are set by XRPU and
XMSENSE alone and are numerically unchanged by #10's amp resize (the amp
sits on a different branch), which is itself a small consistency check that
the re-run is measuring the same startup branch.
`det_final_v` (the internal sense
node) sits at 8.0–14.5 mV at every corner, three orders of magnitude below
`nfet_03v3`'s 0.53–0.89 V threshold range
(device-characterization.md §3) — the kick devices are firmly off, not
partially conducting, and each record's raw per-corner logs (single steady
end-of-run value, not an oscillating one) show no chattering around the
detect threshold.

**What this does *not* itemize**: the block's *total* Iq
(`iq_total_final_ua`, 29.0–77.5 µA across the grid) already exceeds the
ratified < 50 µA budget at the `ff`/125 °C corners — this is the same
pre-existing core/cascode-sizing issue §4.3 already documents (74.9–77.5 µA
total, of which the startup branch itself is only ≈1.6–2.4 µA), not a
regression introduced by this issue. #10 explicitly did **not** close it
(it was scoped to the amp, and left the core/cascode sizing alone — §4.3),
so whole-loop Iq-budget closure across corners remains open.

## 4. Caveats (read before reusing these values)

### 4.1 Amp offset budget, stability and PSRR (#10's shortfalls, closed by #42)

`bandgap_amp` is a telescopic-cascode OTA with explicit dominant-pole
compensation (#42), using real devices rather than a behavioral source (see
§4.2 for why). Sizing and topology are **final** as of #42 — see
[`design/bandgap_error_budget.md`](bandgap_error_budget.md) for the full
derivation. **#10 recorded two ratified-spec shortfalls here and escalated
them rather than relaxing anything; #42 closes both**, and every number
below is a same-testbench measurement against #10's own amp, not an
assertion (`bandgap_error_budget.md` Sec 3.5 explains the paired-record
mechanism):

- **Untrimmed accuracy, amplifier allocation**: the RSS budget goes
  25.45 mV → **13.79 mV** of random terms, 27.5 mV → **15.79 mV** including
  the systematic reserve, against a ratified 24.0 mV (3σ) — 66 % of budget
  used, was 115 % (`bandgap_error_budget.md` Sec 2.7). The amp's own random
  offset falls 25.06 → 13.06 mV.
- **Untrimmed accuracy, whole circuit**: the circuit-level mismatch Monte
  Carlo (`sim/mc-untrimmed/`, record `20260801-080002-a7fd16a`) goes
  **66.6–69.7 mV → 23.6–24.3 mV (3σ)**, a 2.8× reduction, but its window
  check still **FAILS** at all three temperatures. It is no longer
  amplifier-limited: the remaining spread is dominated by the core mirror's
  40 µm² devices (§4.3) and the intervals are pushed out of the window by
  the untrimmed *mean* (1.221–1.248 V), not by their width.
  `bandgap_error_budget.md` Sec 2.8 and Sec 5 decompose this; it is the
  explicit residual #42 reports rather than closes.
- **PSRR**: worst of the 81-point PVT grid goes 31.87 dB → **77.61 dB**
  against the ratified >60 dB DC–1 kHz row; corners passing goes 19/81 →
  **81/81** (`bandgap_error_budget.md` Sec 3.2).
- **Loop stability**: phase margin 119.1° → 177.8° worst-corner against the
  same 45° criterion, plus a **second, strictly stronger** Nyquist
  gain-margin criterion added in #42 (the phase-margin criterion alone
  passed an intermediate revision at 179.8° on all 81 corners that in fact
  encircled its critical point and oscillated) — `bandgap_error_budget.md`
  Sec 4.3–4.5.

What that cost: two small bias branches, ≈0.86 µA at nominal, on a
quiescent-current row that was **already failing** at the hot corner before
this issue — see §4.3 and `bandgap_error_budget.md` Sec 5.

**Superseded in part by #55.** The bullets above are #42's own results and
are left as recorded, but two of them have moved since, because #55 resized
`bandgap_core` and the amplifier's benches are closed-loop measurements of
the whole circuit:

- *Untrimmed accuracy* — the "13.79 / 15.79 mV" figures were an allocation
  over the amplifier, R1/R2 and the PNP pair only. With #55's core-mirror
  row added the complete allocation is **17.19 mV** against 24.0 mV
  (`bandgap_error_budget.md` Sec 2.7's three-column table restates #10's
  and #42's numbers on the same complete basis).
- *PSRR* 77.61 → **86.98 dB** and *phase margin* 177.8° → **108.9°** worst
  corner (still 2.4× the 45° criterion, and the stronger Nyquist criterion
  improves to no critical-axis crossing at all) — `bandgap_error_budget.md`
  Sec 3.2 and Sec 4.5.

### 4.2 Degenerate (near-zero-current) state — resolved by the startup circuit (issue #11)

This is a self-biased loop: there is no independent bias reference forcing
a nonzero current. `bandgap_amp`'s own tail current is itself mirrored from
`bandgap_core.ibias` (see §1's M4/Mn5 branch) specifically so that if the
core sits at (or near) zero current, the amp's tail current collapses right
along with it, rather than an idealized/independent bias artificially
keeping the amp alive in a state the real circuit cannot self-start out of.
The cascode-bias generator (MCB/MNB) is self-biased off `ibias` for the same
reason: at zero core current MNB sinks nothing, `casc` relaxes toward `vdd`,
and the cascode devices turn off — the degenerate state stays degenerate
rather than being propped up by an independent cascode reference that the
real circuit would not have. This deliberately makes the startup problem
**no easier** than it physically is.

Per DR-0001, a self-biased loop of this kind has (at least) two DC
solutions: the intended nonzero-current operating point above, and a
low/near-zero-current degenerate one. **This is no longer a caveat carried
forward from #8 — it is now directly verified, in both directions:**

- **The degenerate state is physical**, not a solver artifact: the #11
  control run (`sim/startup-disabled-control/`, §3a) seeds `bandgap_core` +
  `bandgap_amp` alone (no startup circuit) at the exact degenerate point via
  `.ic`/`uic` (which bypasses the DC solver's own gmin-stepping bias toward
  the nonzero solution — a solver artifact this smoke test's original `.op`
  convergence could not distinguish from genuine self-starting) and the
  block sits there, undisturbed, for the whole transient at 78 of 81 PVT
  points — including the `ss`/−40 °C/2.97 V corner this section used to
  flag as unverified.
- **`bandgap_startup`'s kick removes it**, everywhere it needs to: the
  companion `sim/startup-state-search/` run (identical adversarial seed,
  circuit enabled) recovers to the intended operating point at all 81
  points, and the from-zero ramp records (`sim/startup/`,
  `sim/startup-slow-ramp/`) confirm the same recovery from the actual
  physical power-up condition (`vdd` ramping from 0 V, no `.ic`/`.nodeset`
  seed at all) at every corner, both a fast and a slow ramp rate. **The
  smoke-test operating point in §3 is now reachable without `.ic`/`.nodeset`
  once `bandgap_startup` is in the loop** — closing the gap this section
  used to document.
- **The one corner where leakage alone (no startup circuit) also reaches the
  intended state** is the pure `ff`/125 °C corner (all three supplies) —
  see §3a for the exact numbers and why the partial-skew `res_ff_125c_*` /
  `bjt_ff_125c_*` corners do *not* show this effect. This does not weaken
  the evidence above: the degenerate-state existence check is deliberately
  read at the low-leakage corners (`ss`/−40 °C in particular) where a
  leakage-driven false pass cannot happen, exactly as the Implementation
  guidance for #11 directs.

Full corner-by-corner data, the measurement convention, and links to all four
records are in §3a.

### 4.3 Cascode sizing — closed by #55, except for MCB's own `W/L`

The cascoded current-mode bias/output stage DR-0001 specifies **is
implemented** (MC1–MC4 + the MCB/MNB wide-swing bias generator, §1), and its
effect is measured in §3. Its **sizing** was left provisional by #8, #10,
#11 and #42 — all of which were scoped to the amplifier or the startup
branch. **#55 is the sizing pass this section was asking for.** Item by
item, against how this section previously read:

- ~~"MCB's `W/L` was picked by simulation … 7 spot-checks are not a margin
  budget."~~ **Half closed.** The margin budget now exists: every mirror,
  cascode, and the MCB bias device is checked for `Vds − Vdsat ≥ 0` at all
  **81** PVT points, not 7 — worst case **+122.7 mV** on `M1` at
  `res_ss`/−40 °C/2.97 V, `MCB` at ≥ +858.9 mV (record
  [`20260801-132317-cfd0146`](../sim/core-mirror-sensitivity/records/20260801-132317-cfd0146.md)).
  **Still open**: MCB's `W/L = 0.333` remains a value *picked* by simulation
  rather than *derived*, and #55 deliberately did not move it — MCB's
  current is set by MNB mirroring `M5`'s `Vgs`, which #55's `M4`/`M5`
  co-scaling was chosen to preserve, so re-deriving it is an independent
  question with ~858 mV of measured margin behind it.
- ~~"MC1–MC4 are drawn identical to M1–M4 for matching-group simplicity. A
  sizing pass may well want different cascode geometry."~~ **Closed, and
  the answer is no.** The sizing pass measured the cascode-only mechanism
  directly: `∂Vref/∂δ(MC3) = −0.0133 V/V`, **274× smaller** than the mirror
  device's own −3.647 V/V, because a cascode is a common-gate stage whose
  `ΔVgs` only perturbs the mirror drain and is then divided by the mirror's
  (cascoded, hence very large) output impedance. Different cascode geometry
  would buy nothing measurable on accuracy, so MC1–MC4 stay identical to
  M1–M4 — now as a budgeted conclusion rather than a placeholder.
  `design/bandgap_error_budget.md` Sec 2.6a.
- **PSRR** — unchanged conclusion, better number. Sec 3 of the error budget
  runs the full-PVT sweep; #55's larger `L` raises each mirror leg's output
  impedance and the amp-loop PSRR bench moves 77.61 → **86.98 dB** worst
  corner, with the whole-block `sim/psrr-dc/` spec bench at **87.07 dB**
  (1 kHz), 81/81 PASS.
- **Iq**: the cascode adds one bias branch (≈2.5 µA at the #55 current). The
  block read **39.32 µA at `tt`/27 °C/3.30 V and 65.71 µA at the binding
  `ff`/125 °C/3.63 V corner** after #55 (`sim/startup/` record
  [`20260801-145517-cfd0146`](../sim/startup/records/20260801-145517-cfd0146.md),
  `iq_total_final_ua`), from 48.24 / 80.5 µA before #55 — an 18 % cut at the
  binding corner, from scaling the `ibias` leg to 1/8 of the design current.
  **That row still failed** (< 50 µA ratified), and `bandgap_error_budget.md`
  Sec 5 showed in closed form *why* no further mirror sizing could close
  it — the three signal branches each carry `I = ΔVBE/R2`, which is not a
  function of mirror geometry — leaving the resistor co-scaling that would.
  **#61 took that pass**: `R1`/`R2`/the trim network co-scaled by `k = 2`
  halves every branch current, and the row now **passes** at
  **20.72 µA / 34.01 µA** (same bench, same two columns, record
  [`20260801-230933-960f726`](../sim/startup/records/20260801-230933-960f726.md)) —
  31 % of margin against < 50 µA at the binding corner. Full derivation and
  the full set of re-verified benches: `bandgap_error_budget.md` Sec 5/5a.

**What remains open in this section**: MCB's derived-vs-picked `W/L` (with
a measured ≥858 mV margin), and the startup devices' own budget (§2's
"Startup devices" note) — both explicitly out of #55's scope.

### 4.4 Base-current loading

Per device-characterization.md §1, forward beta for these PNPs is
1.62 typical at 27 °C and drops **below 1** at `ss`/−40 °C — base current is
comparable to (and at some corners exceeds) collector current. Because
every PNP here is diode-connected (base = collector = `vss`), the emitter
node sees the *sum* of collector and base current, so this does not break
the diode I–V relationship the sizing above relies on — but it does mean
the substrate/`vss` node locally sinks a large, strongly PVT-dependent
current from every branch. That is a layout (substrate-tie sizing/IR-drop)
concern for a later stage, not a schematic-topology one, and is noted here
only so it is not lost.

### 4.5 No trim, no per-spec-line verification

No trim pins or trim-resistor segments exist in this schematic (deferred to
**#14**'s scoping decision, per the issue's explicit instruction not to add
them here). No PVT/mismatch sweep against the ratified target spec has been
run (deferred to **#12**/**#13**).

## 5. Pins (for #12's testbench suite)

`bandgap_top` exposes the minimum pin set: `vdd`, `vss`, `vref`. Internal
nodes (`fb`, `sns1`, `sns2`, `ibias`, plus the cascode nodes `casc` and
`d1`…`d4` on `bandgap_core`; `in_p`, `in_n`, `out`, `tail_bias` on
`bandgap_amp`) are deliberately not exposed at the top
level — if a future testbench needs to probe one, add a pin to
`bandgap_top.sch`/`.sym` rather than routing around this file, so the
wrapper's pin list stays the single source of truth for what is
testable from outside.

## 6. Which ratified rows are, and are not, claimed here

Per CLAUDE.md ("no claim without a testbench"): the spec (`README.md`) is
ratified, and four of its rows — and only four — are directly evaluated in
this document.

**Passing — the Startup row (#11, re-verified in #42).** `sim/startup/`,
`sim/startup-slow-ramp/`, `sim/startup-state-search/` and
`sim/startup-disabled-control/` (§3a) are full-PVT-matrix, spec-referenced
(`README.md#target-specification`, Startup row) pass/fail records against
the ratified < 1 ms bound — a genuine spec-conformance claim, not a
sanity-window smoke test, because the startup-time measurement does not
depend on R1/R2's trim state the way an output-voltage claim would; it only
needs the loop to *converge* to *something* near the intended point
quickly. The cited records are taken against **#42's amp**; the #10-amp and
#8-amp generations were superseded on integration rather than left
standing — see §3a's supersession notes.

**Passing — the PSRR row (#42, improved in #55).** `sim/amp-psrr/` record
[`20260801-133427-cfd0146`](../sim/amp-psrr/records/20260801-133427-cfd0146.md)
is a full 81-point PVT sweep of the closed-loop supply-to-`vref` transfer
over 0.01 Hz – 1 kHz, reporting the worst point of the whole band at every
corner: **86.98 dB** minimum against the ratified > 60 dB DC–1 kHz row
(77.61 dB before #55's core resize), 81/81 corners passing. Like the startup
row, this is claimable now because it does not depend on R1/R2's trim state.
The whole-block spec bench `sim/psrr-dc/` agrees at
[`20260801-143203-cfd0146`](../sim/psrr-dc/records/20260801-143203-cfd0146.md)
— 87.07 dB worst at 1 kHz — and additionally reports the ratified
> 30 dB @ 1 MHz *stretch* target passing at every corner (worst 30.39 dB),
recorded and not gated. The PSRR row's load condition is still the ratified
table's own open item A4.

**Passing as of #61 — the Quiescent-current row.** Failing since before #10,
cut −18 % at the binding corner by #55's `ibias`-leg rescale (80.5 →
65.71 µA), and **closed by #61**: co-scaling `R1`/`R2`/the trim network by
`k = 2` halves every branch current and the row now reads **20.72 µA at
nominal and 34.01 µA at the binding `ff`/125 °C/3.63 V corner**, against
< 50 µA (records
[`20260801-230754-960f726`](../sim/iq/records/20260801-230754-960f726.md),
[`20260801-230933-960f726`](../sim/startup/records/20260801-230933-960f726.md)) —
31 % of margin at the binding corner. §4.3 and `bandgap_error_budget.md`
Sec 5/5a give the closed-form reason no further *mirror* sizing could have
closed it, and the resistor/trim co-scaling that did.

**Output-reference (untrimmed accuracy) row — the mismatch *spread* still
closes; the *centre* still does not.** The ratified basis is "3σ, mismatch MC
N≥300 **+** process corners, −40…125 °C". `bandgap_error_budget.md` Sec 2.7
allocates every device group in the block, not just the amplifier's, and
closed at 17.19 mV against 24.0 mV as of #55; Sec 2.8's `sim/mc-untrimmed/`
re-run against the trim-inclusive, resized DUT measured 14.89/15.12/15.82 mV
(3σ) there, and **#61's re-run measures 16.22/16.36/16.81 mV (3σ)**
(record [`20260801-232002-960f726`](../sim/mc-untrimmed/records/20260801-232002-960f726.md)) —
still passing at every temperature with 30–32 % margin. The rise (rather
than a flat hold) is real and explained in Sec 5a: the resistor mismatch
line *improved* (Pelgrom law, halved current at doubled `R`) but the
MOS/BJT line *rose slightly* (`gm/Id` at the mirror devices' fixed `W/L`
increases as current drops), and the latter effect is not fully offset by
the former. What remains outside the ±2 % window is the distribution's
centre — 1.207–1.219 V untrimmed against 1.200 V (was 1.222–1.244 V before
#61, moved closer by the `−VT·ln k` shift of `VEB(Q3)`), from R1/R2's
first-pass hand sizing at the trim network's mid-code, which is what the
1-point wafer-probe trim exists to remove — see
`design/bandgap_trim_network.md`. The bench's own verdict folds centre and
width together and therefore still reads FAIL. The process-corner leg is
#12's, and combining the two legs into a single verdict is a follow-on step
this document does not attempt.

Beyond those, a pass/fail claim against the remaining ratified rows (line
regulation, output noise, area, load) is still premature: R1/R2 remain a
first-pass hand calculation (Section 2) and the untrimmed mean is not
re-centred. `output-voltage-tc` (TC row) was re-run against the current,
#61-resized DUT as one of #61's required regression checks: the `tc_ppm`
envelope over all 81 PVT points **improved**, from 86.32–137.75 ppm/°C to
**36.37–90.50 ppm/°C** (record
[`20260801-234837-960f726`](../sim/output-voltage-tc/records/20260801-234837-960f726.md)) —
still failing the ratified `≤ 50 ppm/°C` bound, as it did before #61, since
`R1`/`R2` have never been corner-swept and re-nulled against a TC target.
That re-verification is a "did this regress" check, not a claim that this
narrative section now tracks TC as a fifth row; `bandgap_error_budget.md`
Sec 5a has the full result. The smoke-test acceptance bound in §3
(1.15–1.35 V) remains intentionally wider than and independent of the
ratified spec window for exactly that reason.
