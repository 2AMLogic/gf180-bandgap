# bandgap_top operating point (issues #8, #10, startup circuit issue #11)

Schematic entry for the ratified Brokaw-cell bandgap
([DR-0001](../spec/decision-records/0001-bandgap-topology-selection.md)):
`design/bandgap_core.sch`, `design/bandgap_amp.sch`, `design/bandgap_top.sch`,
`design/bandgap_startup.sch` (+ matching `.sym` symbols). This document
records the operating-point assumptions, cites the `sim/` evidence they are
grounded in, and states every caveat that applies before the numbers here can
be treated as final.

**Scope**: schematic entry (#8); the amplifier offset/mismatch budget, final
amplifier sizing, loop-stability and PSRR verification (#10, see
[`design/bandgap_error_budget.md`](bandgap_error_budget.md) for the full
derivation); and a current-sensing, self-disabling startup circuit verified
across the full PVT matrix (#11). No per-spec-line testbenches (#12), no
Monte Carlo (#13), no trim network (#14).

Two ratified target-spec rows are now directly evaluated here, and nothing
else is:

- **Startup time** (README.md's Startup row) — issue #11 verifies it
  directly and it **passes**; see §3a and §4.2.
- **Untrimmed accuracy and PSRR** — #10's budget work found both **fall
  short** of the ratified target at this amplifier's sizing (see
  `bandgap_error_budget.md` Sec 5 and §4.1 below). Recorded as a shortfall,
  not relaxed.

Every other row remains un-claimed: no trim (#14), no per-spec-line
testbench suite or whole-circuit PVT/mismatch sweep (#12/#13). See §6.


## 1. Topology

`bandgap_top` = `bandgap_core` (matched vertical-PNP pair, PTAT/CTAT summing,
and the **cascoded** 4-leg current-mode bias/output stage DR-0001 calls for)
servoed by `bandgap_amp` (a provisional real-device 5-transistor OTA), per
DR-0001.

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

### Mirror (core) and amp devices

Core mirror/cascode-bias sizing (rows 1–5) is still **provisional** — see
§4.3, unchanged by #10. Amp sizing (rows 6–8) is **final**, this issue's
own offset-budgeted result — see
[`design/bandgap_error_budget.md`](bandgap_error_budget.md) Sec 2 for the
full derivation, sensitivity measurement, and why sizing was not pushed
further. Device names `M1`–`M5` are reused independently inside
`bandgap_core` and `bandgap_amp` (each subcircuit's own local numbering);
the `(core)`/`(amp)` qualifiers below disambiguate.

| Device | Type | Size | Role |
|---|---|---|---|
| M1–M4 (core) | `pfet_03v3` | W=20 µm, L=2 µm, m=1 | Core current mirror (lower devices) — provisional, §4.3 |
| MC1–MC4 (core) | `pfet_03v3` | W=20 µm, L=2 µm, m=1 | Cascode devices, one per mirror leg — deliberately identical to M1–M4 so the whole stage is one matching group for #16's common-centroid layout — provisional, §4.3 |
| MCB (core) | `pfet_03v3` | W=4 µm, L=12 µm | Diode-connected cascode-bias device (see sizing derivation below) — provisional, §4.3 |
| MNB (core) | `nfet_03v3` | W=5 µm, L=2 µm | Cascode-bias current sink; 1/4 of Mn5's W/L, so it draws ≈ I/4 (measured 2.533 µA, §3) — provisional, §4.3 |
| Mn5 (core) | `nfet_03v3` | W=20 µm, L=2 µm | Diode-connected tail-bias generator for the amp — provisional, §4.3 |
| M1, M2 (amp input pair) | `nfet_03v3` | W=100 µm, L=4 µm, nf=2 | **Final (#10).** 10x the #8 provisional 10 µm/4 µm area; L unchanged from the #4 MOS-mismatch characterization geometry (`20260731-031718-8fb0ea6`) so `A_pair` applies with no L-extrapolation; `nf=2` because a single finger tops out at 100 µm in this PDK. Dominant term in the offset budget even after this resize — see `bandgap_error_budget.md` Sec 2.2, 2.7 |
| M3, M4 (amp mirror load) | `pfet_03v3` | W=40 µm, L=4 µm | **Final (#10).** 4x the #8 provisional area; smaller increase than the input pair because mirror-load mismatch is attenuated at the input by the measured `gm3/gm1 ≈ 0.69` — see `bandgap_error_budget.md` Sec 2.2 |
| M5 (amp tail) | `nfet_03v3` | W=10 µm, L=4 µm | Unchanged from #8. Gate driven by `bandgap_core.ibias`, not an independent bias — see §4. Sizing here sets the amp/core current-mirror ratio (Iq), not the offset-budget's limiting term, so #10 left it as-is |

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
sizing choice made by simulation, not a budgeted one.

None of these sizes are offset-budgeted or headroom-verified as a *design
margin* against the 2.97 V / ss / −40 °C worst case that
device-characterization.md §3 flags for PMOS-stack headroom — the §3
spot-check confirms saturation is maintained there, but a spot-check is not
a margin budget over mismatch and model spread; that is #10's job.

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
re-derived against a mismatch/margin budget the way #10's final pass will
need to for the rest of the loop.

## 3. Smoke-test result

Nominal (27 °C, 3.3 V, `tt`) op-point, via `sim/bandgap-loop-smoke/`, record
[`20260801-013804-259a8e0`](../sim/bandgap-loop-smoke/records/20260801-013804-259a8e0.md)
(clean-tree run against the commit that added the cascode; supersedes
`20260731-232056-d6e10b7`, the pre-cascode run — that record is retained
unedited per `sim/README.md`'s append-only convention). If the smoke test is
re-run, the new record supersedes this one — check that experiment's
`records/` directory for the latest ID rather than assuming this citation is
current forever.

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

- **`sim/startup/`** (fast ramp, 1 µs 0→final) — record
  [`20260801-032901-fbfa3f1`](../sim/startup/records/20260801-032901-fbfa3f1.md).
  `startup_time_s` ranges 0 (`ff_27c_3.63v`) to **3.784 µs**
  (`ss_125c_3.63v`), all ≪ the ratified 1 ms bound. Note the worst corner is
  `ss`/125 °C/3.63 V, **not** the `ss`/−40 °C/2.97 V corner the original
  issue text expected — the Implementation guidance's "verify rather than
  assume" call was correct to make: `ss`/−40 °C/2.97 V itself settles in
  520 ns (`iq_startup_branch_final_ua` = 1.134 µA, the itemized-Iq minimum
  across the whole grid — see §4.2).
- **`sim/startup-slow-ramp/`** (slow ramp, 1 ms 0→final — the Implementation
  guidance's "classic trap" case) — record
  [`20260801-033024-fbfa3f1`](../sim/startup-slow-ramp/records/20260801-033024-fbfa3f1.md).
  `startup_time_s` is **negative at every corner** (−320 µs to −510 µs): the
  loop is already settled to within ±1% of its final value *before* `vdd`
  even reaches 90% of final, which is the best possible outcome for a slow
  ramp and rules out the ramp-tracking stall the guidance warns about.
- **`sim/startup-state-search/`** (adversarial `.ic`/`uic` seed at the exact
  degenerate operating point — `fb`, `casc`, `d1`…`d4` pinned to 3.63 V,
  everything else 0 — `vdd` already valid DC, startup circuit **enabled**) —
  record
  [`20260801-033147-fbfa3f1`](../sim/startup-state-search/records/20260801-033147-fbfa3f1.md).
  `recovery_time_s` ranges 466 ns–3.914 µs; `iq_total_final_ua` gated
  `min=5` (must clear a genuine nonzero operating current, not degenerate
  leakage) and clears it everywhere (28.9–76.0 µA). The kick recovers from
  this adversarial seed at every one of the 81 points.
- **`sim/startup-disabled-control/`** (identical adversarial seed,
  `bandgap_startup` **not instantiated** — `bandgap_top`/`bandgap_core`
  wired the same way #8 originally shipped it) — record
  [`20260801-033326-fbfa3f1`](../sim/startup-disabled-control/records/20260801-033326-fbfa3f1.md).
  This is the "(c) control run" leg of the required multi-pronged evidence:
  it observes where the degenerate state persists vs. self-starts from
  leakage alone, rather than gating a pass/fail outcome. Result: at 78 of 81
  points the block sits at `vref` in the 0.05–0.53 V range with
  `iq_total_final_ua` in the **9 pA – 160 pA** range — the degenerate state
  is physical, not a solver artifact, including at the `ss`/−40 °C/2.97 V
  corner the Implementation guidance calls out (`vref` = 0.525 V,
  `iq_total` = 14.1 pA). At exactly the 3 `ff`/125 °C points (`ff_125c_*`,
  all three supplies — **not** the partial skews `res_ff_125c_*` or
  `bjt_ff_125c_*`, which stay degenerate), leakage alone self-starts the
  loop to the intended operating point (`vref` ≈ 1.234–1.240 V,
  `iq_total_final_ua` ≈ 73.5–73.9 µA) with **no startup circuit present at
  all** — exactly the masking effect the Implementation guidance flagged
  ("ff/125 °C leakage may self-start the core — a pass there proves
  little"), now confirmed rather than assumed, and narrowed to the specific
  sub-corner where it actually happens. Contrasting this record against
  `sim/startup-state-search/`'s (same seed, same corners, startup circuit
  present) shows the kick doing genuine work at the other 78/81 points, not
  riding on leakage that was going to self-start anyway.

**Startup-branch residual current, itemized against the Iq budget.** Every
record above reports `iq_startup_branch_final_ua` — the startup branch's own
current draw after disengagement, isolated via a zero-volt ammeter tap
between the shared `vdd` rail and `bandgap_startup`'s own `vdd` pin (so it
does not include the rest of the block's current). Across the full 81-point
grid this ranges **1.134 µA** (`ss_-40c_2.97v`) to **2.391 µA**
(`ff_125c_3.63v`) — comfortably inside both the ratified < 50 µA budget and
its < 20 µA stretch target on its own. `det_final_v` (the internal sense
node) sits at 8.0–14.5 mV at every corner, three orders of magnitude below
`nfet_03v3`'s 0.53–0.89 V threshold range
(device-characterization.md §3) — the kick devices are firmly off, not
partially conducting, and each record's raw per-corner logs (single steady
end-of-run value, not an oscillating one) show no chattering around the
detect threshold.

**What this does *not* itemize**: the block's *total* Iq
(`iq_total_final_ua`, 28.9–76.0 µA across the grid) already exceeds the
ratified < 50 µA budget at the `ff`/125 °C corners — this is the same
pre-existing, provisional-amp/cascode-sizing issue §4.3 already documents
(73.5–76.0 µA total, of which the startup branch itself is only
≈1.6–2.4 µA), not a regression introduced by this issue. Final Iq-budget
closure across the whole loop is #10's job.

## 4. Caveats (read before reusing these values)

### 4.1 Amp offset budget, stability and PSRR (#10 — closed, with a recorded shortfall)

`bandgap_amp` is a plain 5-transistor OTA (differential pair + mirror load +
tail), using real devices rather than a behavioral source (see §4.2 for
why). Sizing is now **final** (#10, replacing #8's provisional 10 µm/4 µm
placeholder) — see
[`design/bandgap_error_budget.md`](bandgap_error_budget.md) for the full
derivation. Loop stability is verified and passes with wide margin across
the full PVT grid (132.5° minimum phase margin against a 45° criterion,
`bandgap_error_budget.md` Sec 4). **Two things do not close**, per
CLAUDE.md's "no spec relaxation" rule and this issue's explicit escalation
requirement rather than being silently declared passing:

- The untrimmed accuracy budget (amp offset + resistor + PNP mismatch, RSS)
  comes in at ~106–115 % of the ratified ±2 % (3σ) target — the amp's own
  random offset alone, even after a 10x/4x area increase, is the dominant
  term (`bandgap_error_budget.md` Sec 2.7).
- PSRR falls 5–28 dB short of the ratified >60 dB DC–1 kHz target across
  the PVT grid, traced to the amp (not `bandgap_core`'s cascode) as the
  limiter (`bandgap_error_budget.md` Sec 3).

Both are escalated (`bandgap_error_budget.md` Sec 5) rather than fixed by
further sizing changes, because further area growth on this amp topology
measurably erodes loop stability at this circuit's specific corners
(`bandgap_error_budget.md` Sec 2.1) — closing either gap needs a
topology/compensation change that is out of this issue's scope.

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

### 4.3 Provisional cascode sizing

The cascoded current-mode bias/output stage DR-0001 specifies **is
implemented** (MC1–MC4 + the MCB/MNB wide-swing bias generator, §1), and its
effect is measured in §3. What is *not* final is its **sizing**, in exactly
the same sense the amp's is not (§4.1):

- MCB's `W/L` was picked by simulation to place the mirror devices
  comfortably in saturation at nominal (§2), not by a headroom budget over
  mismatch, model spread, and the full corner grid. The §3 spot-check shows
  ≥ +102 mV of `Vds − Vdsat` on the mirror devices at the worst of 7
  corner points, but 7 spot-checks are not a margin budget.
- MC1–MC4 are drawn identical to M1–M4 for matching-group simplicity. A
  sizing pass may well want different cascode geometry (e.g. shorter
  cascodes to recover headroom, or wider ones to lower `Vdsat`).
- **PSRR has now been measured against the sized amp (#10)** —
  `design/bandgap_error_budget.md` Sec 3 runs a full-PVT PSRR sweep against
  the final amp and a diagnostic isolating `bandgap_core`'s own
  contribution (an idealized-amp variant, majority of the PVT grid reading
  80–99 dB). That diagnostic result is consistent with the cascoded stage's
  own PSRR being adequate — **the amp, not the cascode, is where the
  ratified >60 dB target's shortfall traces to.** The cascode's own
  headroom-margin budget (as opposed to its PSRR contribution) is still
  unbudgeted — this bullet's first point (MCB sizing, no margin budget)
  remains open, unaddressed by #10.
- The cascode adds one bias branch (≈2.5 µA) to the Iq budget; that is
  inside the ratified < 50 µA line at nominal today (44.3 µA total) but has
  not been budgeted across corners — at `ff`/125 °C/3.63 V the informal
  spot-check already reads 73.5 µA. #10 did not change the core/cascode
  sizing (only the amp — see §2's table), so this Iq-across-corners gap is
  unchanged and still open; the amp's own resize did not add materially to
  Iq (§2's Mirror/amp devices table).

Final sizing of the cascode stack and its headroom budget remain open
(unaddressed by #10, which was scoped to the amp — see Section 4.1); its
PSRR contribution has now been measured, per above.

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

## 6. Why this is not a spec-conformance claim (except startup)

Per CLAUDE.md ("no claim without a testbench") and this issue's explicit
scope: the spec (`README.md`) is ratified, and three of its rows — and only
three — are now directly evaluated here.

**Passing (#11): the Startup row.** Issue #11's `sim/startup/`,
`sim/startup-slow-ramp/`, `sim/startup-state-search/` and
`sim/startup-disabled-control/` records (§3a) are full-PVT-matrix,
spec-referenced (`README.md#target-specification`, Startup row), pass/fail
records against the ratified < 1 ms bound — a genuine spec-conformance
claim, not a sanity-window smoke test, because the startup-time measurement
does not depend on R1/R2's trim state the way an output-voltage claim
would; it only needs the loop to *converge* to *something* near the
intended point quickly. These records are taken against the **final (#10)
amp sizing**: the provisional-amp records minted before #10 landed were
superseded on integration rather than left standing, per issue #11's own
ordering caveat — see §3a's supersession note.

**Falling short (#10): untrimmed accuracy and PSRR.** Section 4.1 records
both as honest shortfalls, not passes:

- **Untrimmed accuracy**: `design/bandgap_error_budget.md` Sec 2 finds the
  RSS'd offset/mismatch budget at ~106–115 % of the ratified ±2 % (3σ)
  target, dominated by the amp's own random offset.
- **PSRR**: `bandgap_error_budget.md` Sec 3 finds the amp's own
  contribution falls 5–28 dB short of the ratified >60 dB DC–1 kHz target
  across the PVT grid.

Beyond these three rows, a pass/fail claim against the remaining ratified
rows (TC, line regulation, Iq across the full corner grid, etc.) is still
premature: (a) no per-spec-line testbench suite or whole-circuit
PVT/mismatch sweep has been run against every row (#12/#13), and (b) R1/R2
are still a first-pass hand calculation (Section 2 of this doc), not a
trimmed design (#14). The smoke-test acceptance bound in §3 (1.15–1.35 V)
remains intentionally wider than and independent of the ratified spec
window for exactly this reason — it predates both #10 and #11 and was never
meant to stand in for the accuracy budget now recorded in
`bandgap_error_budget.md`.
