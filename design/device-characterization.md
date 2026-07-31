# gf180mcu device characterization — summary

Device-level evidence base for the Brokaw-core reference selected in
[DR-0001](../spec/decision-records/0001-bandgap-topology-selection.md), at the
3.3 V-only scope of
[DR-0002-supply](../spec/decision-records/0002-supply-voltage-scope.md).

Everything here is a **measured simulation number with a testbench behind it**.
Nothing here is a pass/fail claim: the spec is not ratified (#1), so this
document reports what the devices do, not whether they are good enough.

Every number cites the `sim/` record it comes from. Records are append-only
evidence per [`sim/README.md`](../sim/README.md); if a number here is ever
re-measured, the new record supersedes the old one and this table is updated to
cite the new record ID.

## Source records

| Campaign | Experiment | Record ID | Corner points |
|---|---|---|---|
| Vertical PNP | `sim/device-pnp-vbe/` | `20260731-030932-8fb0ea6` | 3 BJT corners × 6 temperatures |
| Resistors | `sim/device-resistor-tc/` | `20260731-031750-8fb0ea6` | 3 resistor corners × 3 temperatures (+2 well-bias) |
| MOS threshold | `sim/device-mos-vth/` | `20260731-031337-8fb0ea6` | 5 MOS corners × 3 temperatures |
| MOS mismatch | `sim/device-mos-mismatch/` | `20260731-031718-8fb0ea6` | `typical` × 3 temperatures, N = 300 each |
| PNP mismatch | `sim/device-pnp-mismatch/` | `20260731-040850-187a336` | `bjt_typical` × 3 temperatures, N = 300 each |

All five testbenches are two-terminal or source-referred device measurements
with no supply rail, so the ±10 % supply axis of the CLAUDE.md PVT matrix does
not apply; each record states that explicitly, and the resistor record
additionally sweeps the one non-ground node (the p+ resistor's n-well tie) over
±10 % of 3.3 V to demonstrate it.

Reproduce any of them with, e.g.:

```bash
PDK_ROOT=~/.volare PDK=gf180mcuD sim/device-pnp-vbe/run_pnp_vbe.py
```

---

## 1. Vertical PNP — record `20260731-030932-8fb0ea6`

gf180mcu offers four vertical (substrate) PNP geometries. DR-0001's matched
pair uses `pnp_05p00x05p00` / `pnp_10p00x10p00`, whose **drawn** emitter areas
are 25 µm² and 100 µm² (4:1).

| Quantity | Value | Notes |
|---|---|---|
| VBE, 5×5 @ 10 µA, typical, 27 °C | 0.7227 V | 0.8347 V at −40 °C, 0.5516 V at 125 °C |
| VBE, 10×10 @ 10 µA, typical, 27 °C | 0.6893 V | |
| CTAT slope dVBE/dT, 5×5 @ 10 µA | −1.716 mV/°C | −1.916 mV/°C at 1 µA; −1.655 mV/°C at 20 µA |
| CTAT slope dVBE/dT, 10×10 @ 10 µA | −1.831 mV/°C | corner spread on the slope is < 0.03 mV/°C |
| ΔVBE (5×5 − 10×10) @ 10 µA, 27 °C | **33.374 mV** | 25.66 mV at −40 °C, 44.66 mV at 125 °C |
| ΔVBE PTAT slope | **115.13 µV/°C** | typical; 115.01–115.25 µV/°C over BJT corners |
| ΔVBE linearity error | **6.7 µV** max deviation from the best-fit line | 0.035 % of the 19 mV span over −40…125 °C |
| Effective emitter-area ratio | **3.634** (not 4.00) | `exp(ΔVBE / VT)` at equal *emitter* current |
| Ideality factor n @ 1 µA | 1.002 (10×10) – 1.006 (5×0.42) | typical, 27 °C |
| Usable emitter-current window, 5×5 | **≈ 0.07 nA … 28 µA** | worst-case intersection over all nine BJT corner points, `n ≤ 1.05` |
| Forward beta, 5×5 @ 1 µA, typical, 27 °C | **1.62** | 0.90 at ss/−40 °C, 2.79 at ff/125 °C |

Sanity anchors hold: VBE sits in the 0.6–0.7 V band at 27 °C at low-µA bias and
falls at roughly −2 mV/°C; ΔVBE is PTAT and close to `(kT/q)·ln(ratio)`.

### What this changes for the design

- **The area ratio is not 4:1 in ΔVBE terms.** The PDK saturation currents of
  the two geometries are in ratio 3.671, not 4.000, and at equal *emitter*
  current the measured effective ratio is 3.634. Sizing that assumes
  `VT·ln 4 = 35.9 mV` overstates the PTAT term by 7.4 %. Use **33.37 mV at
  27 °C**, or design for an explicit *N*:1 unit-device array whose ratio you
  re-measure.
- **Equal-Ie and equal-Ic cores are not the same circuit.** Forcing equal
  collector currents instead of equal emitter currents moves the effective
  ratio from 3.634 to 3.671, i.e. ΔVBE by +0.26 mV (0.8 %). Which one the
  Brokaw core actually enforces must be settled in #8 and simulated as built.
- **Beta is the dominant surprise.** Forward beta is ≈ 1.6 at 27 °C and drops
  **below 1** at the ss/−40 °C corner, so the base current is 38–53 % of the
  emitter current and swings 3:1 over PVT. Any node that has to absorb PNP base
  current (the amplifier output, a base-ballast resistor, a common base rail)
  sees a large, strongly PVT-dependent load. Base-resistance asymmetry between
  the two devices converts directly into a ΔVBE error.
- **Bias-current headroom is comfortable.** A 1–20 µA core bias sits inside the
  ≈ 0.07 nA … 28 µA window at every corner, so the ±19 % bias shift the
  recommended resistor flavor's process spread produces (§2) does not push the
  devices out of their exponential region.

---

## 2. Resistors — record `20260731-031750-8fb0ea6`

All DUTs drawn as 10 squares (L = 10 × W) at two widths, biased at 50 mV
(low field). `Rsh_eff = R / (L/W)`, so it includes head resistance and
drawn-vs-effective geometry bias — which is why it is not the nominal `rsh_*`
parameter and why it is width-dependent.

Values below are `res_typical`, 27 °C, W = 1 µm; TC is the −40…125 °C chord;
spread is the half-spread between `res_ss` and `res_ff` at 27 °C.

| Flavor | Rsh_eff (Ω/sq) | TC (ppm/°C) | TC curvature, cold vs hot chord | Corner spread | Squares for 100 kΩ |
|---|---|---|---|---|---|
| `ppolyf_u` | 381.4 | **−111** | −180 / −64 | ±19.3 % | 262 |
| `ppolyf_u_1k` | 1045.9 | −947 | −1259 / −733 | ±19.7 % | 96 |
| `ppolyf_u_2k` | 2133.3 | −1550 | −1920 / −1297 | ±19.9 % | 47 |
| `ppolyf_u_3k` | 3196.6 | −1548 | −1917 / −1296 | **±25.0 %** | 31 |
| `pplus_u` (p+ diffusion) | 206.9 | **+1258** | +1161 / +1323 | ±20.5 % | 483 |
| `nplus_u` (n+ diffusion) | 58.1 | **+1352** | +1282 / +1400 | ±23.6 % | 1722 |

At W = 5 µm the same devices land much closer to their nominal sheet
(`ppolyf_u` 356.0 Ω/sq vs 381.4 at W = 1 µm — a **7.1 % width sensitivity**) and
their TC magnitude drops (`ppolyf_u` −75 ppm/°C). Narrow resistors are more
exposed to etch bias, in both absolute value and TC.

Two model limitations that constrain what can be claimed:

- **Local mismatch is not modelled.** The gf180mcu resistor subcircuits
  hard-code `mis_r = 0` (the mismatch expression is present but commented out
  in `sm141064.ngspice`). A Monte Carlo over these devices reports *zero*
  resistor spread. Resistor matching must therefore be argued from area and
  layout technique, and #13's circuit-level Monte Carlo will have a known blind
  spot here that its record must state.
- **Voltage coefficient is not modelled.** `r_vc1 = r_vc2 = 0` for every
  flavor, so the measured VCR is exactly 0 ppm/V — a model artefact, not
  evidence. Real high-sheet poly has a finite VCR.

`ppolyf_u_2k` and `ppolyf_u_3k` share identical `r_tc1` / `r_tc2` in the PDK,
which is why their TCs are indistinguishable despite the 1.5× sheet difference.

### Recommended flavor: `ppolyf_u` for the ratio-critical PTAT/feedback pair

**Recommendation: use `ppolyf_u` for R1 and R2 of the Brokaw core, at
W ≥ 2 µm, built from identical unit segments. Use `ppolyf_u_1k` only for
non-ratio-critical bulk resistance (start-up bleeder, trim ladder rungs).**

Rationale:

1. **TC magnitude, and therefore PTAT-current fidelity.** The core's PTAT
   current is `ΔVBE / R1`. Any resistor TC multiplies that current by an extra
   temperature term, which shifts VBE by `VT · d(ln I)/dT`. At −111 ppm/°C
   (`ppolyf_u`) that perturbation is ≈ 3 µV/°C; at −1550 ppm/°C
   (`ppolyf_u_2k/3k`) it is ≈ 40 µV/°C — about 2.3 % of the −1.72 mV/°C CTAT
   slope, which then has to be absorbed by retuning R2/R1.
2. **TC curvature, and therefore residual output TC.** What cannot be trimmed
   out is the *change* in resistor TC across the range: 116 ppm/°C for
   `ppolyf_u` versus 620 ppm/°C for the 2k/3k flavors. Curvature in R(T) shows
   up directly as curvature in the reference output.
3. **Area is matching budget, not waste.** Resistor mismatch scales as
   1/√(area). `ppolyf_u` needs ~8× the area of `ppolyf_u_3k` for the same
   resistance — which, for a block whose accuracy is limited by matching and
   which the PDK cannot simulate mismatch for, is the right side of the
   trade. A representative core (5 µA PTAT, R1 ≈ 6.6 kΩ, R2 ≈ 52 kΩ) is
   ~155 squares of `ppolyf_u`; at W = 2 µm that is ~620 µm² of poly per branch,
   entirely affordable.
4. **Corner spread is no worse.** At ±19.3 % `ppolyf_u` has the *smallest*
   spread in the set, so nothing is given up on trim range. `ppolyf_u_3k`'s
   ±25 % is the worst.
5. **Diffusion flavors are wrong for the ratio pair.** `pplus_u` / `nplus_u`
   have TCs of +1258 / +1352 ppm/°C — opposite sign and an order of magnitude
   larger than poly — and their bodies sit in a reverse-biased junction. They
   remain interesting as a *deliberate* opposite-sign element for curvature
   correction later, not as the PTAT/feedback pair.

Matching-plan implications for #16:

- R1 and R2 must be the **same flavor and the same unit geometry**; the ratio
  is what the output voltage depends on, and only same-flavor ratios cancel
  process and temperature to first order.
- Build both from identical series/parallel unit segments in a common-centroid
  or interdigitated array with dummy segments at both ends.
- Use W ≥ 2 µm for ratio-critical elements: the measured 7.1 % Rsh difference
  between W = 1 µm and W = 5 µm is width-bias sensitivity, and it is a
  *systematic* error that only cancels if every unit has the same width.
- The absolute ±19 % corner spread does **not** cancel in the bias current, so
  the PNPs see ±19 % current variation from the resistor corners alone —
  comfortably inside their measured usable window (§1).

---

## 3. MOS threshold — record `20260731-031337-8fb0ea6`

`nfet_03v3` / `pfet_03v3`, constant-current threshold at
`Id = 100 nA × (W/L)`, diode-connected (Vds = Vgs), Vsb = 0.

| Quantity | `nfet_03v3` 10/1 | `nfet_03v3` 10/4 | `pfet_03v3` 10/1 | `pfet_03v3` 10/4 |
|---|---|---|---|---|
| \|Vth\| @ typical, 27 °C | 0.6348 V | 0.6097 V | 0.8186 V | 0.8163 V |
| \|Vth\| @ typical, −40 °C | 0.7080 V | 0.6836 V | 0.8902 V | 0.8847 V |
| \|Vth\| @ typical, 125 °C | 0.5299 V | 0.5044 V | 0.7104 V | 0.7126 V |
| d\|Vth\|/dT (−40…125 °C chord) | −1.079 mV/°C | −1.086 mV/°C | −1.090 mV/°C | −1.043 mV/°C |
| Process spread at 27 °C (ff…ss) | 219 mV | 220 mV | 250 mV | 253 mV |
| \|Vgs\| at 10 µA, typical, 27 °C | 0.7654 V | 0.8889 V | 1.0184 V | 1.3156 V |

`fs` / `sf` land at roughly ±80 mV (NMOS) and ∓90 mV (PMOS) from typical, i.e.
the skew corners are ~73 % of the full ff/ss excursion and are the ones that
matter for an NMOS-vs-PMOS mirror stack.

### What this changes for the design

- At 3.3 V nominal and ±10 % (2.97 V worst case), a PMOS cascode stack costs
  ~0.94 V of \|Vth\| at ss/−40 °C before any overdrive. The cascoded
  current-mode output stage from DR-0001 needs its headroom budget checked
  against 2.97 V at the ss/−40 °C corner specifically, not at typical.
- Vth drift (≈ −1.08 mV/°C for both polarities) is over half the PNP CTAT slope
  in magnitude. Any part of the reference path that leans on a MOS threshold —
  a source follower, a start-up trip point — imports that drift directly, which
  is an argument for keeping the reference path purely BJT + resistor and using
  the MOS devices only as current mirrors and gain.

---

## 4. MOS local mismatch — record `20260731-031718-8fb0ea6`

N = 300 Monte Carlo samples per temperature, mismatch-only
(`sw_stat_mismatch = 1`, `sw_stat_global = 0`), reported as 1σ of the
gate-voltage difference of an equally biased, nominally identical pair. That
difference *is* the input-referred offset the pair contributes.

Values at 27 °C, 1 µA per device:

| Pair | σ(ΔVgs) | 3σ | Area-normalised `A_pair` |
|---|---|---|---|
| `nfet_03v3` 10/1 | 2.529 mV | 7.59 mV | 5.66 mV·µm |
| `nfet_03v3` 10/4 | 1.098 mV | 3.29 mV | 4.91 mV·µm |
| `pfet_03v3` 10/1 | 2.339 mV | 7.02 mV | 5.23 mV·µm |
| `pfet_03v3` 10/4 | 1.123 mV | 3.37 mV | 5.02 mV·µm |

`A_pair = σ(ΔVgs) · √(W·L) / √2` (drawn area) lumps threshold and
current-factor mismatch together; it is a Pelgrom-style scaling constant, not a
pure A_VT. Temperature dependence is weak (σ rises ~0.3 % from −40 °C to
125 °C) and mismatch is essentially bias-independent between 1 µA and 10 µA.

### Offset budget input for #10

Required gate area for a target pair offset, from `A_pair ≈ 4.9–5.7 mV·µm`:

| Target 3σ offset | as % of ΔVBE (33.37 mV) | Required W·L per device |
|---|---|---|
| 3.0 mV | 9.0 % | ≈ 48 µm² (e.g. 12/4) |
| 1.0 mV | 3.0 % | ≈ 435 µm² (e.g. 109/4) |
| 0.5 mV | 1.5 % | ≈ 1740 µm² (e.g. 435/4) |

The headline consequence: **a plain 10/4 amplifier input pair contributes a 3σ
offset of ~3.3 mV against a 33.4 mV PTAT signal — about 10 % error on the PTAT
term.** Brute-force area buys 3 % at ~435 µm² per device and 1.5 % at
~1740 µm². Anything tighter than that is an argument for chopping, auto-zero,
or trim rather than for more area — which is exactly the trade #10 has to
settle.

**MOS + PNP side by side** (both contributions now characterized — see §5 for
the PNP campaign): at the representative 10 µA bias, the `pnp_05p00x05p00`
core pair's own dVBE mismatch is 3σ ≈ 0.128 mV (27 °C, `bjt_typical`,
`20260731-040850-187a336`) versus the MOS 10/4 pair's 3σ ≈ 3.37–3.66 mV
(§4 table above). **The PNP pair's own mismatch is roughly 25–30× smaller
than a plain 10/4 MOS pair's** and contributes well under 1 % of the 33.4 mV
PTAT signal on its own — for this offset budget, the MOS mirror/amplifier
pair, not the PNP core pair, is the term worth spending area on. #10 should
carry both sigma figures (MOS from §4, PNP from §5) into the RSS offset
budget rather than treating either as negligible without stating why.

---

## 5. PNP local mismatch — record `20260731-040850-187a336`

N = 300 Monte Carlo samples per temperature, mismatch-only
(`sw_stat_mismatch = 1`, `sw_stat_global = 0`, process fixed at the nominal
`bjt_typical` point — deliberately not stacked on the `bjt_ss`/`bjt_typical`/
`bjt_ff` corner axis §1 already sweeps, to avoid double-counting that spread),
reported as 1σ of dVBE for (a) two identical `pnp_05p00x05p00` devices and
(b) the area-ratioed `pnp_05p00x05p00` / `pnp_10p00x10p00` pair the Brokaw
core actually uses, at equal emitter current.

Values at 27 °C:

| Pair | Id | σ(ΔVBE) | 3σ |
|---|---|---|---|
| `pnp_05p00x05p00` identical pair | 1 µA | 0.0469 mV | 0.141 mV |
| `pnp_05p00x05p00` identical pair | 10 µA | 0.0463 mV | 0.139 mV |
| `pnp_05p00x05p00` / `pnp_10p00x10p00` area-ratioed pair | 1 µA | 0.0424 mV | 0.127 mV |
| `pnp_05p00x05p00` / `pnp_10p00x10p00` area-ratioed pair | 10 µA | 0.0426 mV | 0.128 mV |

Both sigma figures are two to three orders of magnitude smaller than the
33.4 mV PTAT signal (§1) and than the MOS pair sigmas in §4 — expected, since
the PDK's per-instance `mis_is_pnp_*` / `mis_bf_pnp_*` agauss() sigmas
(0.05–0.3 %) are themselves small relative to the `fets_mm` MOS mismatch
parameters. This is a PDK-model artefact, not a claim that PNP devices are
inherently better matched than MOS in silicon; see the record's plausibility
note. Temperature dependence is weak (σ rises ~10–16 % from −40 °C to 125 °C,
same common-random-numbers caveat as §4).

---

## Known gaps

- **Resistor mismatch is not simulatable** in this PDK release (§2), so the
  matching argument for the PTAT/feedback pair is a layout-discipline argument,
  and any Monte Carlo that includes resistors will under-report spread.
- **Resistor voltage coefficient is not modelled** (§2); do not cite the zero
  VCR measurement as evidence of anything.
