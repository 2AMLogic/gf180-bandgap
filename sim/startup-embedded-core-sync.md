# Startup experiments: embedded core sync (#228)

Part of #210 (tracks #203). Companion to `sim/embedded-core-inventory.md`
(#227), which covers the six non-startup benches and holds the lumped-R1
derivation this note reuses. **This is a synchronization of diagnostic inputs,
not a signoff or PVT result.** Full -40/27/125 C, supply and process coverage
with startup verdicts is #211. No spec text, record, log, netlist snapshot or
frozen DUT was changed.

## Canonical reference (re-verified before editing)

`sim/dut/bandgap_top.spice`, sha256
`9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`, last
touched by `aeaca90e962ece5307ba279e6ecfbb896836eaa3` (DR-0007, merged via
#222 `a919849553b4c6cc05db6be676bbdb522caa3c75`); build base `6624f072`.
XR2 `ppolyf_u` 2u / 39.195501u, XQ2 `pnp_05p00x05p00 m=4`, XQ1/XQ3
`pnp_05p00x05p00 m=1`, base XR1 446.000000u, 63-segment ladder of
2.771871u units, default `trim_code=32`.

## Inventory

| Bench | Role | Startup instance | R2 (was) | Q2 (was) | lumped R1 (was) |
|---|---|---|---|---|---|
| `sim/startup` | supply ramp, enabled | yes (`Xx3`) | 39.195501u (36.341871u) | `pnp_05p00x05p00 m=4` (`pnp_10p00x10p00 m=1`) | 545.639857u (543.040000u) |
| `sim/startup-slow-ramp` | slower ramp, enabled | yes | same | same | 545.639857u (543.040000u) |
| `sim/startup-state-search` | DC supply, degenerate `.ic`, uic | yes | same | same | 545.639857u (560.341647u) |
| `sim/startup-disabled-control` | same seed, startup omitted | **no** | same | same | 545.639857u (560.341647u) |

All four now carry the identical core. Only the header comment (new
"RE-SYNCED IN #228" block) and the three device lines (XR2, XQ2, XR1) changed
in each testbench; ramp shape/rate, `.ic`, loads, stimulus, thresholds,
`bandgap_amp`/`bandgap_startup` subcircuits and topology are untouched
(`git diff` of each bench is those lines plus comments). The disabled control
still has no `bandgap_startup` instance; this is checked automatically.

## Lumped R1 equivalence

Same derivation and length as #227: `ppolyf_u` is R = a*L + b, so base R1 plus
32 trim units is not `446 + 32*2.771871 = 534.699872u` and 446u is not
assigned. Solved length **545.639857u** against the real PDK model
(`sim/tools/measure_lumped_r1.py`). Re-run for this issue
(ngspice-42, gf180mcuD, open_pdks
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, `res_typical`):

| T (C) | R_stack (ohm) | R_lumped (ohm) | error | error of naive length sum |
|---|---|---|---|---|
| -40 | 99099.385 | 98916.273 | -1848 ppm | -21847 ppm |
| 27 | 98029.605 | 98029.605 | 0.00 ppm | -20037 ppm |
| 125 | 97578.492 | 97842.571 | +2706 ppm | -17385 ppm |

Same at 50 mV and 0.5 V bias. Reproduce:
`python3 sim/tools/measure_lumped_r1.py --check-length 545.639857`.

Limitations: exact only at tt/27 C; -0.18 % / +0.27 % residual at -40 / 125 C
(lumping cannot track the different temperature dependence of b and a*L).
Only `res_typical` was exercised; `res_ff`/`res_ss` and Monte Carlo were not
(a corner grid belongs on the batch fleet via `klt sim`, and is #211's scope).
Trim-ladder switch resistors are included in the reference stack.

## Automated check

`python3 sim/tools/check_embedded_cores.py` now covers 10 benches (the six
from #227 plus these four) and additionally asserts the startup-instance
presence per bench (enabled: present; disabled control: absent).
`sim/tests/test_embedded_cores.py` proves it fails on a deliberately stale Q2,
stale R2 and a pasted 446u R1 in each of the four startup benches, and that
the topology flag matches. Result: 10/10 in sync; unit tests pass.

## Smoke / parse coverage (not evidence)

Attempted one point per bench (`sim/run_corners.py <bench> --corners tt
--temps 27 --supply-tol 0 -j 1 --no-write`; nothing recorded). **All four fail
at netlist parse in ngspice**: `could not find a valid modelname` for the
amp's `nfet_03v3` (input pair `W=200u L=4u nf=8`, i.e. the installed PDK has
no bin for it). The identical failure occurs for `startup-disabled-control`
on the unmodified tree (verified with the change stashed), and was already
reported in #227 for `line-regulation` and the amp-based benches. It is an
environment/PDK-version issue independent of this change, so **no
transient/startup behavior of the synced cores was simulated**; coverage here
is the static parameter/topology check plus the resistor-model equivalence
above. Startup verdicts remain for #211.

## Not done / downstream

No PVT, supply or process-corner results, no startup verdict, and no signoff
claim. No file under `sim/*/records`, `sim/*/corners`,
`sim/*/netlist-snapshots`, `sim/dut/frozen` or `spec/` was modified.
