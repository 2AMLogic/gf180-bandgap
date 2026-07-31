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
and a simple 4-leg current mirror bias/output stage) servoed by
`bandgap_amp` (a provisional real-device 5-transistor OTA), per DR-0001.

```
                      vdd
                       |
        +------+-------+-------+-------+
        |      |       |       |       |
       Mp1    Mp2     Mp3     Mp4      | (all gates tied to "fb",
        |      |       |       |       |  driven by bandgap_amp.out)
      sns1    sns2    vref   ibias
        |      |       |       |
       Q1     R2      R1      Mn5 (diode, gate=drain=ibias)
        |      |       |       |
       (C,B    e2     e3      vss
        =vss)   |       |
                Q2      Q3
                (C,B    (C,B
                 =vss)   =vss)
```

- **Q1** = `pnp_05p00x05p00` (unit, 25 µm² drawn emitter), diode-connected
  (base = collector = `vss`, emitter = `sns1`).
- **Q2** = `pnp_10p00x10p00` (100 µm² drawn emitter, 4:1 drawn ratio vs Q1),
  diode-connected, emitter through **R2** to `sns2`.
- **Q3** = `pnp_05p00x05p00` (same unit device as Q1), diode-connected,
  emitter through **R1** to `vref` — the output-branch "reference" device.
- **Mp1–Mp4** = `pfet_03v3`, identical sizing, gates tied to the common
  node `fb` (the amp's output). The amp forces `sns1 == sns2`; because Mp1
  and Mp2 share the same `Vgs` (same gate, same source) and the amp forces
  the same `Vds` (`sns1 == sns2`), Mp1 and Mp2 carry equal current
  unconditionally. That, combined with `V(sns1) = VEB(Q1)` and
  `V(sns2) = VEB(Q2) + I·R2`, forces the classic PTAT relation
  `ΔVBE(I) = I·R2`.
- **Mp3/R1/Q3** (the output branch) and **Mp4/Mn5** (the tail-bias
  generator, feeding `bandgap_amp.tail_bias`) share the same gate node `fb`
  but are **not** individually servoed by the amp — see the no-cascode
  caveat (§5).
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
| Mp1–Mp4 | `pfet_03v3` | W=20 µm, L=2 µm, m=1 | Core current mirror (bias + output stage) |
| Mn5 | `nfet_03v3` | W=20 µm, L=2 µm | Diode-connected tail-bias generator for the amp |
| M1, M2 (amp input pair) | `nfet_03v3` | W=10 µm, L=4 µm | Sized to match the #4 MOS-mismatch geometry (`20260731-031718-8fb0ea6`) so the amp's own input-referred offset is directly citable, not re-measured |
| M3, M4 (amp mirror load) | `pfet_03v3` | W=10 µm, L=4 µm | — |
| M5 (amp tail) | `nfet_03v3` | W=10 µm, L=4 µm | Gate driven by `bandgap_core.ibias`, not an independent bias — see §4 |

None of these sizes are offset-budgeted or headroom-verified against the
2.97 V / ss / −40 °C worst case that device-characterization.md §3 flags for
PMOS-stack headroom; that is #10's job.

## 3. Smoke-test result

Nominal (27 °C, 3.3 V, `tt`) op-point, via `sim/bandgap-loop-smoke/`, record
[`20260731-232056-d6e10b7`](../sim/bandgap-loop-smoke/records/20260731-232056-d6e10b7.md)
(clean-tree run against this commit's parent). If the smoke test is
re-run, the new record supersedes this one per `sim/README.md`'s
append-only convention — check that experiment's `records/` directory for
the latest ID rather than assuming this citation is current forever.

| Node | Simulated value |
|---|---|
| `vref` | **1.2276 V** |
| `fb` (common mirror gate) | 2.2760 V |
| `sns1` (Q1 branch, VEB(Q1)) | 0.72283 V |
| `sns2` (Q2 branch, top of R2) | 0.72259 V |
| `e2` (Q2 emitter, VEB(Q2)) | 0.68946 V |
| Per-branch current (Q1/Q2/Q3 branches, from V/R) | ≈10.0–10.1 µA each |
| Total supply current | 41.7 µA |

`sns1 ≈ sns2` (0.24 mV residual) confirms the servo is working. `ΔVBE =
sns1 − e2 = 33.38 mV`, matching the #4 citation (33.374 mV at 10 µA, 27 °C)
to within 0.02 mV — confirming the branch current landed almost exactly on
the intended 10 µA design point.

**Expected window and why it is wide:** this smoke test's acceptance bound
is **1.15 V – 1.35 V**, not README.md's ratified ±2% target-spec window
(1.176–1.224 V). The wider bound is deliberate: R1/R2 here are a first-pass
hand calculation (§2), not a trimmed, offset-budgeted, corner-swept
sizing — landing "in the classic ~1.2 V ballpark, right sign, right order of
magnitude" is the actual bar for a schematic-entry existence proof. The
simulated 1.2276 V sits comfortably inside the wide bound and only 0.28%
above the ratified spec's own upper bound, which is a good early sign for
#10 but is **not** a spec-conformance claim (see §6).

**Informal temperature check (not a recorded PVT sweep):** re-running the
same nominal-supply op-point at `tt`/−40 °C and `tt`/125 °C (informal check
only, not entered as `sim/` evidence, since a full PVT/mismatch sweep is
explicitly out of scope for this issue) gives 1.2177 V and 1.2359 V
respectively — a chord slope of about +0.11 mV/°C, i.e. near-flat and
slightly over-compensated, consistent with the §2 hand estimate
(`−1.716 mV/°C + 15.28 × 0.11513 mV/°C ≈ +0.044 mV/°C`; the two-point
chord measurement differs from the hand estimate by second-order effects
this first-pass sizing does not capture). This is presented purely as
sizing-sanity context for #10, not as a TC claim.

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
`bandgap_core.ibias` (see §1's Mp4/Mn5 branch) specifically so that if the
core sits at (or near) zero current, the amp's tail current collapses right
along with it, rather than an idealized/independent bias artificially
keeping the amp alive in a state the real circuit cannot self-start out of.
Per DR-0001, a self-biased loop of this kind has (at least) two DC
solutions: the intended nonzero-current operating point above, and a
low/near-zero-current degenerate one. This smoke test's `.ic` statement
seeds ngspice's DC solver toward the intended state — empirically, this
particular deck also converges to the same state from an all-zero `.ic`
(likely a solver-asymmetry artifact, not evidence of physical
self-starting). **Neither result is evidence that the real circuit
self-starts in silicon** — verifying that, and adding the startup circuit
itself, is **#11**.

### 4.3 No cascode; not all branches are individually servoed

DR-0001 specifies "a cascoded current-mode output/bias stage." This
schematic implements a **simple (non-cascoded) 4-leg current mirror**
instead: Mp1/Mp2 (the two branches the amp actually servos) are forced to
equal current exactly, by construction, regardless of mirror output
impedance. Mp3 (output branch) and Mp4 (tail-bias branch) are **not**
individually servoed — they share the same gate node but their drain
voltages (`vref`, `ibias`) are not forced equal to `sns1`/`sns2`, so their
currents only track Mp1/Mp2's current to the extent an uncascoded mirror's
finite output impedance allows. The smoke test happened to show all three
PNP-branch currents within about 1% of each other at this operating point
(§3), which is encouraging but is a single-corner observation, not a
matching guarantee. Adding the cascode DR-0001 calls for (with its own
cascode-bias generator) is deferred as part of **#10**'s sizing pass; this
is a scope simplification made in this issue, not an oversight, and is
flagged here so #10 does not silently inherit it unstated.

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
nodes (`fb`, `sns1`, `sns2`, `ibias` on `bandgap_core`; `in_p`, `in_n`,
`out`, `tail_bias` on `bandgap_amp`) are deliberately not exposed at the top
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
