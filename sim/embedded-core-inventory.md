# Embedded bandgap_core copies: inventory and equivalence (#227)

Part of DR-0007 propagation (#210 / #203). Six active diagnostic benches embed
their own copy of `bandgap_core` instead of including the DUT. After DR-0007
(#209, merged as PR #222, `a919849553b4c6cc05db6be676bbdb522caa3c75`) those
copies still carried the pre-DR-0007 R2 and Q2. This note records what the
canonical core is, what each copy now carries, how the lumped R1 was derived
and verified, and what is deliberately *not* claimed.

**This is a synchronization of diagnostic inputs. It is not a signoff or PVT
result. The full-suite PVT evidence run is downstream (#211).** No spec text,
frozen DUT, record, log or netlist snapshot was changed.

## Canonical reference

`sim/dut/bandgap_top.spice` (sha256
`9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`, last
touched by commit `aeaca90e962ece5307ba279e6ecfbb896836eaa3`; build base
`744a1cb8`). Values re-read from that file before editing:

| Device | Canonical |
|---|---|
| XR2 | `ppolyf_u r_width=2u r_length=39.195501u m=1` |
| XQ2 | `pnp_05p00x05p00 m=4` |
| XR1 (base) | `ppolyf_u r_width=2u r_length=446.000000u m=1`, node `tn0` |
| trim ladder | `bandgap_trim`, 63 x `ppolyf_u` 2u / 2.771871u, `trim_code=32` default |
| XQ1, XQ3 | `pnp_05p00x05p00 m=1` |

Pre-sync values in the six copies: R2 36.341871u, Q2 `pnp_10p00x10p00 m=1`,
lumped R1 560.341647u (five benches), explicit base R1 460.701871u (mirror
bench).

## Inventory

| Bench | R1 realization | R2 | Q2 | R1 length | Diagnostic content preserved |
|---|---|---|---|---|---|
| `sim/amp-loop-stability` | lumped | 39.195501u | `pnp_05p00x05p00 m=4` | 545.639857u | single-injection loop-gain probe at the fb break, PM / Nyquist-GM measurements and thresholds |
| `sim/amp-offset-sensitivity` | lumped | 39.195501u | `pnp_05p00x05p00 m=4` | 545.639857u | series offset source `vos` at the amp input, sensitivity measurement |
| `sim/amp-psrr` | lumped | 39.195501u | `pnp_05p00x05p00 m=4` | 545.639857u | AC supply stimulus, PSRR measurement and threshold |
| `sim/bandgap-loop-smoke` | lumped | 39.195501u | `pnp_05p00x05p00 m=4` | 545.639857u | self-biased servo smoke test (bandgap_top with provisional amp) |
| `sim/core-mirror-sensitivity` | **explicit** (base R1 + `XXTRIM`) | 39.195501u | `pnp_05p00x05p00 m=4` | 446.000000u (base) | four mirror-gate and one cascode-gate perturbation sources, headroom margins |
| `sim/core-psrr-ideal-amp` | lumped | 39.195501u | `pnp_05p00x05p00 m=4` | 545.639857u | 1e6-gain ideal `Efb` servo replacing the amp, AC supply stimulus, `>= 60 dB` check |

The `amp-*` and `core-mirror-sensitivity` manifests default to the *active*
`sim/dut/bandgap_amp.spice` (not a frozen amp snapshot), so they are live
diagnostics and were synchronized rather than left frozen.

The mirror bench keeps its explicit realization: base R1 was changed
460.701871u -> 446.000000u and the 63-segment ladder is byte-identical to the
canonical one (checked automatically).

Explicit, intentional deviations from the canonical core (unchanged by this
issue; they are the experiments):

- `core-mirror-sensitivity`: flattened into the top deck; per-device `vos_m_*`
  and `vos_mc_vref` series sources between `fb`/`casc` and the individual
  mirror/cascode gates.
- `core-psrr-ideal-amp`: `Efb fb 0 sns2 sns1 1e6` replaces the amp.
- `amp-loop-stability`: fb break with a loop-gain injection node.
- `amp-offset-sensitivity`: offset source at the amp input.
- `bandgap-loop-smoke`: its core copy generates `casc` internally (MCB/MNB
  inside the subckt) rather than exposing a `casc` pin; the pin list differs
  from the canonical 8-pin core.

Known pre-existing drift **outside this issue's R2/Q2/R1 scope** (reported, not
changed here): the cores embedded in `bandgap-loop-smoke` and
`core-psrr-ideal-amp` still use the earlier mirror/cascode sizing
(`XM1..XM3`, `XMC1..XMC3` L=6u W=60u nf=4; `XM4`, `XMC4` L=6u W=7.5u) where
the canonical core has L=8.5u W=85u nf=4 / L=8.5u W=10.625u. The W/L ratios are
equal (10 and 1.25 in both), so the mirror ratios match, but the
copies are not geometrically identical to the DUT.

## Lumped R1 derivation

`ppolyf_u` is a compound model: R = a*L + b, with a per-device overhead b.
One lumped device standing in for base R1 plus the 32 trim units that are
in-circuit at the default `trim_code=32` pays b once; the real stack pays it 33
times, so the lumped length is not `446 + 32*2.771871 = 534.699872u`.

`sim/tools/measure_lumped_r1.py` measures the real model directly, using the
reference stack built exactly as in `sim/dut/bandgap_top.spice` (R1 base plus
the `bandgap_trim` subcircuit extracted verbatim from that file at its
default code), then solves and verifies the lumped length. Provenance of the
run recorded here: ngspice-42, gf180mcuD, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, model section `res_typical`, one
ngspice process per invocation.

Fit at tt / 27 C (W = 2u): R(L) = 179.545971 ohm/um * L + 62.167 ohm.
Reference R1 + 32 units = 98029.605 ohm. Solved lumped length
**545.639857u**.

Verification of that length against the real stack:

| T (C) | R_stack (ohm) | R_lumped (ohm) | error | error if lengths were simply summed (534.699872u) |
|---|---|---|---|---|
| -40 | 99099.385 | 98916.273 | -1848 ppm | -21847 ppm |
| 27 | 98029.605 | 98029.605 | 0.00 ppm | -20037 ppm |
| 125 | 97578.492 | 97842.571 | +2706 ppm | -17385 ppm |

The same figures were obtained at 50 mV (substrate-referred 0 V) and at a
0.5 V drop biased about 0.7 V above the substrate: the DC model shows no
voltage dependence at this resolution.

Reproduce: `python3 sim/tools/measure_lumped_r1.py` (solve and verify) or
`--check-length 545.639857` (verify only).

### Limitations of the equivalence

- Exact at tt / 27 C by construction. Away from 27 C the single lumped device
  and the 33-device stack differ by -0.18 % / +0.27 % because the overhead b
  and the length term a*L have different temperature dependence. That
  residual is the price of lumping; the same limitation applied to the
  previous lumped values (their headers solve at tt/27 C the same way). Where
  it matters, use the explicit realization.
- Only `res_typical` was exercised. `res_ff` / `res_ss` and Monte Carlo
  statistical variation were not run (a corner grid is not appropriate on the
  shared dispatch host, and none of that is needed to synchronize inputs).
  Whether the corner residual is larger than the temperature residual is
  unmeasured here.
- The 1 mohm / 1 Tohm switch resistors of the code-32 trim ladder are part of
  the reference stack and were included.
- If the base R1, the trim unit, `trim_code` default, or the PDK resistor
  model changes, re-run the tool and update `LUMPED_R1_LENGTH_U` in
  `sim/tools/check_embedded_cores.py`.

## Automated check

`python3 sim/tools/check_embedded_cores.py` compares each bench's XR2, XQ1,
XQ2, XQ3 and XR1 against `sim/dut/bandgap_top.spice`, treating the two R1
realizations separately:

- explicit: base length equals the canonical base and the trim ladder (unit
  length and count) equals the canonical ladder;
- lumped: length equals the PDK-solved `LUMPED_R1_LENGTH_U`; pasting 446u is
  flagged.

`sim/tests/test_embedded_cores.py` (picked up by the CI `sim/tests` run) pins
the canonical values and proves the check fails on a deliberately stale Q2, a
stale R2, a pasted base R1 in a lumped bench, a stale explicit base R1, a
modified trim unit and a flipped realization. Running the checker against the
pre-change tree (before this edit) reports all six benches stale.

## Smoke and parse coverage (not evidence)

Single-point runs with `sim/run_corners.py <bench> --corner-set tt --no-write`
(nothing was recorded; `sim/*/records` untouched):

- `bandgap-loop-smoke`: tt, -40 / 27 / 125 C, 3.3 V: runs, vref 1.19956 V at
  27 C (1.20027 V at -40 C, 1.19245 V at 125 C).
- `core-psrr-ideal-amp`: tt, -40 / 27 / 125 C, 3.3 V: runs on the physical
  branch, PSRR 99.2 / 101.5 / 109.7 dB. Required a convergence aid (see
  below). Before the edit this bench measured 98.2 / 100.1 / 106.6 dB with the
  old core.
- `amp-loop-stability`, `amp-offset-sensitivity`, `amp-psrr`,
  `core-mirror-sensitivity`: **could not be run on this host, before or after
  this change.** ngspice stops with `could not find a valid modelname` for the
  amp's `nfet_03v3` (L=6u W=300u nf=12) with the installed PDK; the same
  failure occurs for `line-regulation` against `sim/dut/bandgap_top.spice`
  and for an unmodified `main`. For these four only the static parameter check
  above applies. This is an environment/PDK-version issue independent of
  this change.

### Convergence aid in `core-psrr-ideal-amp`

With Q2 `pnp_05p00x05p00 m=4` the DC operating point of the 1e6-gain ideal
servo, seeded only by the existing `.ic`, converged to a non-physical branch
(fb in the MV range, PSRR about 0 dB). The bench now also carries a
`.nodeset` of the physical tt / 27 C operating point and
`.options itl1=1000 itl2=1000 itl6=1000`. These change only where Newton
starts; the ideal servo, stimulus, measurement and `>= 60 dB` threshold are
unchanged. A seed alone failed at -40 C and the raised limits alone failed at
125 C, so both are needed; this was verified at tt corner only (no supply
excursion, no process corners).

## Not done / downstream

- No PVT, supply-tolerance or process-corner results are produced or claimed.
  The suite PVT evidence run is #211.
- No record under `sim/*/records`, no corner log, no
  `sim/*/netlist-snapshots` entry, no `sim/dut/frozen` file and nothing under
  `spec/` was modified.
