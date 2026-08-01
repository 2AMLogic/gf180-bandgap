# bandgap_top operating point (issue #8)

Schematic entry for the ratified Brokaw-cell bandgap
([DR-0001](../spec/decision-records/0001-bandgap-topology-selection.md)):
`design/bandgap_core.sch`, `design/bandgap_amp.sch`, `design/bandgap_top.sch`
(+ matching `.sym` symbols). This document records the operating-point
assumptions, cites the `sim/` evidence they are grounded in, and states every
caveat that applies before the numbers here can be treated as final.

**Scope**: schematic entry and a nominal smoke test only. No final amp
sizing/offset budget (#10), no startup circuit (#11), no per-spec-line
testbenches (#12), no Monte Carlo (#13), no trim network (#14). Nothing here
is a claim against the ratified target spec (`README.md`, "Target
specification") — see the caveats below for why.

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

### Mirror and amp devices (provisional)

| Device | Type | Size | Role |
|---|---|---|---|
| M1–M4 | `pfet_03v3` | W=20 µm, L=2 µm, m=1 | Core current mirror (lower devices) |
| MC1–MC4 | `pfet_03v3` | W=20 µm, L=2 µm, m=1 | Cascode devices, one per mirror leg — deliberately identical to M1–M4 so the whole stage is one matching group for #16's common-centroid layout |
| MCB | `pfet_03v3` | W=4 µm, L=12 µm | Diode-connected cascode-bias device (see sizing derivation below) |
| MNB | `nfet_03v3` | W=5 µm, L=2 µm | Cascode-bias current sink; 1/4 of Mn5's W/L, so it draws ≈ I/4 (measured 2.533 µA, §3) |
| Mn5 | `nfet_03v3` | W=20 µm, L=2 µm | Diode-connected tail-bias generator for the amp |
| M1, M2 (amp input pair) | `nfet_03v3` | W=10 µm, L=4 µm | Sized to match the #4 MOS-mismatch geometry (`20260731-031718-8fb0ea6`) so the amp's own input-referred offset is directly citable, not re-measured |
| M3, M4 (amp mirror load) | `pfet_03v3` | W=10 µm, L=4 µm | — |
| M5 (amp tail) | `nfet_03v3` | W=10 µm, L=4 µm | Gate driven by `bandgap_core.ibias`, not an independent bias — see §4 |

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

## 3. Smoke-test result

Nominal (27 °C, 3.3 V, `tt`) op-point, via `sim/bandgap-loop-smoke/`, record
[`20260801-013804-259a8e0`](../sim/bandgap-loop-smoke/records/20260801-013804-259a8e0.md)
(clean-tree run against the commit that added the cascode; supersedes
`20260731-232056-d6e10b7`, the pre-cascode run — that record is retained
unedited per `sim/README.md`'s append-only convention). If the smoke test is
re-run, the new record supersedes this one — check that experiment's
`records/` directory for the latest ID rather than assuming this citation is
current forever.

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
a TC/line-regulation claim — an untrimmed, unsized loop with no startup
circuit has no business making one (§6). It is here only to document that
the cascode was checked for convergence/headroom robustness, not just at
nominal.

## 4. Caveats (read before reusing these values)

### 4.1 Provisional amp

`bandgap_amp` is a plain 5-transistor OTA (differential pair + mirror load +
tail), sized only for loop closure, using real devices rather than a
behavioral source (see §4.2 for why). No offset budget, no PSRR/headroom
analysis, no compensation/stability analysis has been done. Final sizing is
**#10**.

### 4.2 Degenerate (near-zero-current) state — no startup circuit yet

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
**no easier** than it physically is; solving it is #11's job, and #11 should
note that its kick branch now has to bring up the cascode bias too, not just
the mirror gate.
Per DR-0001, a self-biased loop of this kind has (at least) two DC
solutions: the intended nonzero-current operating point above, and a
low/near-zero-current degenerate one. This smoke test's `.ic` statement
seeds ngspice's DC solver toward the intended state — empirically, this
particular deck also converges to the same state from an all-zero `.ic`
(likely a solver-asymmetry artifact, not evidence of physical
self-starting). **Neither result is evidence that the real circuit
self-starts in silicon** — verifying that, and adding the startup circuit
itself, is **#11**.

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
- No PSRR analysis has been run on the cascoded stage — the DC
  line-sensitivity spot-check in §3 shows the benefit is currently masked by
  the provisional amp, and the real evaluation needs a PSRR testbench
  (**#12**) against a sized amp (**#10**).
- The cascode adds one bias branch (≈2.5 µA) to the Iq budget; that is
  inside the ratified < 50 µA line at nominal today (44.3 µA total) but has
  not been budgeted across corners — at `ff`/125 °C/3.63 V the informal
  spot-check already reads 73.5 µA, which is a sizing problem for **#10**
  (it was 69.2 µA pre-cascode, so this is not a cascode-introduced
  regression so much as a pre-existing untrimmed-sizing issue).

Final sizing of the cascode stack, its headroom budget, and its PSRR
verification are **#10**/**#12**'s scope, consistent with how the amp itself
is handled.

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

## 6. Why this is not a spec-conformance claim

Per CLAUDE.md ("no claim without a testbench") and this issue's explicit
scope: the spec (`README.md`) is ratified, but (a) the amp here is
provisional/unsized, (b) no startup circuit exists, (c) no PVT or mismatch
sweep has been performed, and (d) R1/R2 are a first-pass hand calculation,
not a trimmed/budgeted design. A pass/fail claim against the ratified
±2%/50 ppm/°C/etc. target-spec rows would therefore be premature. The
smoke-test acceptance bound in §3 (1.15–1.35 V) is intentionally wider than
and independent of the ratified spec window for exactly this reason.
