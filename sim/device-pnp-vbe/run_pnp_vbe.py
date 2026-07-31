#!/usr/bin/env python3
"""Run the gf180mcu vertical-PNP characterization corner matrix (issue #4).

Executes `testbench/tb_pnp_vbe.spice` headlessly through ngspice at every
(BJT corner, temperature) point, commits the raw per-corner logs, freezes the
netlist snapshot, and writes one append-only summary record under `records/`
per the evidence format in `sim/README.md`.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-pnp-vbe/run_pnp_vbe.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

import devchar as dc  # noqa: E402

# --------------------------------------------------------------------------
# Corner matrix
# --------------------------------------------------------------------------

SECTIONS = ["bjt_ss", "bjt_typical", "bjt_ff"]

# -40 / 27 / 125 C are the CLAUDE.md PVT temperatures; the four intermediate
# points exist so the dVBE-vs-T linearity error is a real curvature figure
# rather than a three-point artefact.
TEMPS = [-40.0, -10.0, 27.0, 60.0, 90.0, 125.0]
PVT_TEMPS = [-40.0, 27.0, 125.0]

DEVICES = {
    "5x5": ("pnp_05p00x05p00", "v(e5x5)", "i(vb5x5)", 25.0),
    "10x10": ("pnp_10p00x10p00", "v(e10x10)", "i(vb10x10)", 100.0),
    "5x0.42": ("pnp_05p00x00p42", "v(e5x042)", "i(vb5x042)", 2.1),
    "10x0.42": ("pnp_10p00x00p42", "v(e10x042)", "i(vb10x042)", 4.2),
}

BIASES_A = [1e-6, 5e-6, 10e-6, 20e-6]  # candidate core bias currents
IDEALITY_LIMIT = 1.05  # local n above this = outside the usable window
PAIR = ("5x5", "10x10")  # the 4:1 drawn-area pair the Brokaw core uses
PAIR_BIAS_A = 10e-6


# --------------------------------------------------------------------------
# Per-corner extraction
# --------------------------------------------------------------------------


def extract(log: str, temp_c: float) -> dict:
    columns, rows = dc.parse_dc_table(log)
    logi = dc.column(columns, rows, "v-sweep")
    vt = dc.thermal_voltage(temp_c)

    out: dict = {"vbe": {}, "beta": {}, "ideality": {}, "window": {}}
    for key, (_model, vcol, icol, _area) in DEVICES.items():
        vbe = dc.column(columns, rows, vcol)
        ib = dc.column(columns, rows, icol)

        out["vbe"][key] = {
            bias: dc.interp_at(logi, vbe, math.log10(bias)) for bias in BIASES_A
        }

        beta = [(10.0**x - b) / b if b > 0 else float("nan") for x, b in zip(logi, ib)]
        out["beta"][key] = {
            bias: dc.interp_at(logi, beta, math.log10(bias)) for bias in BIASES_A
        }

        # Local ideality factor from the slope of VBE vs ln(I), midpoint-sampled.
        mid_logi: list[float] = []
        n_local: list[float] = []
        for i in range(len(logi) - 1):
            dv = vbe[i + 1] - vbe[i]
            dx = (logi[i + 1] - logi[i]) * math.log(10.0)
            n_local.append(dv / (vt * dx))
            mid_logi.append(0.5 * (logi[i] + logi[i + 1]))
        out["ideality"][key] = {
            bias: dc.interp_at(mid_logi, n_local, math.log10(bias))
            for bias in BIASES_A
        }
        out["window"][key] = usable_window(mid_logi, n_local)

    lo, hi = PAIR
    out["dvbe"] = {
        bias: out["vbe"][lo][bias] - out["vbe"][hi][bias] for bias in BIASES_A
    }
    out["area_ratio_eff"] = {
        bias: math.exp(out["dvbe"][bias] / vt) for bias in BIASES_A
    }
    return out


def usable_window(mid_logi: list[float], n_local: list[float]) -> tuple[float, float, bool, bool]:
    """Widest contiguous current span around 1 uA with local n <= IDEALITY_LIMIT.

    Returns (I_low, I_high, low_is_sweep_floor, high_is_sweep_ceiling).
    """
    anchor = min(
        range(len(mid_logi)), key=lambda i: abs(mid_logi[i] - math.log10(1e-6))
    )
    if n_local[anchor] > IDEALITY_LIMIT:
        return (float("nan"), float("nan"), False, False)
    lo = anchor
    while lo - 1 >= 0 and n_local[lo - 1] <= IDEALITY_LIMIT:
        lo -= 1
    hi = anchor
    while hi + 1 < len(n_local) and n_local[hi + 1] <= IDEALITY_LIMIT:
        hi += 1
    return (
        10.0 ** mid_logi[lo],
        10.0 ** mid_logi[hi],
        lo == 0,
        hi == len(n_local) - 1,
    )


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def amps(value: float) -> str:
    if math.isnan(value):
        return "n/a"
    if value >= 1e-3:
        return f"{value * 1e3:.3g} mA"
    if value >= 1e-6:
        return f"{value * 1e6:.3g} uA"
    if value >= 1e-9:
        return f"{value * 1e9:.3g} nA"
    if value >= 1e-12:
        return f"{value * 1e12:.3g} pA"
    return f"{value:.3g} A"


def window_str(win: tuple[float, float, bool, bool]) -> str:
    lo, hi, at_floor, at_ceiling = win
    if math.isnan(lo):
        return "none (n > limit at 1 uA)"
    low = f"<= {amps(lo)} (sweep floor)" if at_floor else amps(lo)
    high = f">= {amps(hi)} (sweep ceiling)" if at_ceiling else amps(hi)
    return f"{low} .. {high}"


# --------------------------------------------------------------------------
# Record body
# --------------------------------------------------------------------------


def build_record(
    record: str,
    stamp,
    pdk: dc.Pdk,
    results: dict[tuple[str, float], dict],
) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add(
        "- **Claim**: gf180mcu vertical (substrate) PNP device characterization "
        "for the Brokaw core selected in DR-0001 "
        "(`spec/decision-records/0001-bandgap-topology-selection.md`) -- VBE(I, T), "
        "dVBE/dT, dVBE between the area-ratioed pair, ideality factor, forward "
        "beta, and the usable emitter-current window. **This record makes no "
        "spec pass/fail claim**: no ratified spec exists yet (#1), so every "
        "entry below is a measured device number, not a verdict."
    )
    add(
        "- **Netlist provenance**: schematic-level device testbench "
        "(`sim/device-pnp-vbe/testbench/tb_pnp_vbe.spice`) -- no `design/` "
        "schematic and no extracted layout is involved; the DUTs are PDK "
        "device models instantiated directly."
    )
    add("- **Corner matrix run**:")
    add(f"  - Process: {', '.join(SECTIONS)} (gf180mcu has no global corner")
    add("    switch -- each device family has its own `.lib` section in")
    add("    `sm141064.ngspice`; only the BJT sections apply to this DUT)")
    add(
        "  - Temperature: "
        + ", ".join(f"{t:g} C" for t in TEMPS)
        + " (-40 / 27 / 125 C are the CLAUDE.md PVT points; the intermediate"
    )
    add("    points support the dVBE-vs-T linearity error below)")
    add(
        "  - Supply: **not applicable** -- every DUT here is a two-terminal "
        "diode-connected device driven by an ideal current source with its "
        "collector/base at ground. There is no supply rail, so the +/-10% "
        "supply axis of the CLAUDE.md PVT matrix has nothing to sweep. This is "
        "the explicit subset justification `sim/README.md` requires; the "
        "corner-log filenames carry `nosupply` in the supply field."
    )
    add(
        f"  - {len(SECTIONS) * len(TEMPS)} corner points total "
        f"({len(SECTIONS)} process x {len(TEMPS)} temperature)"
    )
    add(
        "- **Statistical convention**: N/A -- this is a corner-matrix "
        "characterization, not a distribution claim. Device mismatch is not "
        "exercised here (`sw_stat_mismatch` left at the PDK default of 0)."
    )
    add("- **Result**: measured device data (no spec comparison -- see Claim).")
    add("")

    # --- VBE / beta / ideality at the PVT temperatures -----------------
    add("### VBE at candidate bias currents (V)")
    add("")
    add(
        "| Corner | T (C) | "
        + " | ".join(
            f"{key} @ {amps(b)}" for key in ("5x5", "10x10") for b in BIASES_A
        )
        + " |"
    )
    add("|---|---|" + "---|" * (2 * len(BIASES_A)))
    for section in SECTIONS:
        for temp in PVT_TEMPS:
            res = results[(section, temp)]
            cells = [
                f"{res['vbe'][key][b]:.4f}"
                for key in ("5x5", "10x10")
                for b in BIASES_A
            ]
            add(f"| {section} | {temp:g} | " + " | ".join(cells) + " |")
    add("")

    add("### VBE at 10 uA for the small-emitter geometries (V)")
    add("")
    add("| Corner | T (C) | 5x0.42 | 10x0.42 |")
    add("|---|---|---|---|")
    for section in SECTIONS:
        for temp in PVT_TEMPS:
            res = results[(section, temp)]
            add(
                f"| {section} | {temp:g} | "
                f"{res['vbe']['5x0.42'][10e-6]:.4f} | "
                f"{res['vbe']['10x0.42'][10e-6]:.4f} |"
            )
    add("")

    # --- dVBE/dT -------------------------------------------------------
    add("### CTAT slope dVBE/dT (mV/C), least-squares over all six temperatures")
    add("")
    add(
        "| Corner | Device | "
        + " | ".join(f"{amps(b)}" for b in BIASES_A)
        + " | max fit residual (mV) |"
    )
    add("|---|---|" + "---|" * (len(BIASES_A) + 1))
    for section in SECTIONS:
        for key in DEVICES:
            cells = []
            worst = 0.0
            for bias in BIASES_A:
                ys = [results[(section, t)]["vbe"][key][bias] for t in TEMPS]
                slope, intercept = dc.linfit(TEMPS, ys)
                worst = max(worst, dc.max_abs_residual(TEMPS, ys, slope, intercept))
                cells.append(f"{slope * 1e3:.3f}")
            add(
                f"| {section} | {key} | " + " | ".join(cells) + f" | {worst * 1e3:.2f} |"
            )
    add("")

    # --- dVBE pair -----------------------------------------------------
    lo, hi = PAIR
    add(
        f"### PTAT dVBE = VBE({lo}) - VBE({hi}) at equal emitter current "
        f"({amps(PAIR_BIAS_A)})"
    )
    add("")
    add(
        "Drawn emitter-area ratio is 4:1 (25 um^2 vs 100 um^2). The model saturation "
        "currents are not in the same ratio, so the *effective* ratio "
        "`exp(dVBE / VT)` extracted below is the number a Brokaw core actually sees."
    )
    add("")
    add(
        "| Corner | dVBE @ -40 C (mV) | dVBE @ 27 C (mV) | dVBE @ 125 C (mV) | "
        "slope (uV/C) | max deviation from fit (uV) | deviation / span (%) | "
        "effective area ratio @ 27 C |"
    )
    add("|---|---|---|---|---|---|---|---|")
    for section in SECTIONS:
        ys = [results[(section, t)]["dvbe"][PAIR_BIAS_A] for t in TEMPS]
        slope, intercept = dc.linfit(TEMPS, ys)
        resid = dc.max_abs_residual(TEMPS, ys, slope, intercept)
        span = max(ys) - min(ys)
        add(
            f"| {section} | "
            + " | ".join(
                f"{results[(section, t)]['dvbe'][PAIR_BIAS_A] * 1e3:.3f}"
                for t in PVT_TEMPS
            )
            + f" | {slope * 1e6:.2f} | {resid * 1e6:.2f} | "
            f"{100.0 * resid / span:.3f} | "
            f"{results[(section, 27.0)]['area_ratio_eff'][PAIR_BIAS_A]:.3f} |"
        )
    add("")

    # --- ideality + window --------------------------------------------
    add("### Ideality factor and usable emitter-current window")
    add("")
    add(
        "Local ideality `n = (1/VT) dVBE/d(ln I)` from adjacent sweep points over a "
        "1 pA .. 1 mA emitter-current sweep. The usable window is the contiguous "
        f"current span around 1 uA over which `n <= {IDEALITY_LIMIT}`; below it the "
        "recombination/leakage term dominates, above it emitter series resistance "
        "and high-injection do. Both edges are inside the swept range, so the "
        "window bounds are measured rather than clipped by the sweep."
    )
    add("")
    add("| Corner | T (C) | Device | n @ 1 uA | n @ 10 uA | usable window |")
    add("|---|---|---|---|---|---|")
    for section in SECTIONS:
        for temp in PVT_TEMPS:
            res = results[(section, temp)]
            for key in DEVICES:
                add(
                    f"| {section} | {temp:g} | {key} | "
                    f"{res['ideality'][key][1e-6]:.4f} | "
                    f"{res['ideality'][key][10e-6]:.4f} | "
                    f"{window_str(res['window'][key])} |"
                )
    add("")

    # --- beta ----------------------------------------------------------
    add("### Forward beta = (Ie - Ib) / Ib")
    add("")
    add(
        "The gf180mcu vertical PNP is a substrate device with a very low forward "
        "beta (model `bf` ~ 1.7). Base current is therefore a large fraction of "
        "emitter current, which any core using these devices has to budget for."
    )
    add("")
    add(
        "| Corner | T (C) | "
        + " | ".join(f"{key} @ 1 uA | {key} @ 20 uA" for key in ("5x5", "10x10"))
        + " |"
    )
    add("|---|---|---|---|---|---|")
    for section in SECTIONS:
        for temp in PVT_TEMPS:
            res = results[(section, temp)]
            cells = []
            for key in ("5x5", "10x10"):
                cells.append(f"{res['beta'][key][1e-6]:.3f}")
                cells.append(f"{res['beta'][key][20e-6]:.3f}")
            add(f"| {section} | {temp:g} | " + " | ".join(cells) + " |")
    add("")

    add("- **Links**:")
    add("  - Testbench: `sim/device-pnp-vbe/testbench/tb_pnp_vbe.spice`")
    add("  - Run script: `sim/device-pnp-vbe/run_pnp_vbe.py`")
    add(
        f"  - Netlist snapshot: `sim/device-pnp-vbe/netlist-snapshots/{record}.spice`"
    )
    add(f"  - Raw logs: `sim/device-pnp-vbe/corners/{record}/`")
    add(f"  - PDK: {pdk.label}, ngspice {dc.ngspice_version()}")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #4)")
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------


def main() -> int:
    pdk = dc.resolve_pdk()
    root = dc.repo_root(HERE)
    record, stamp = dc.mint_record_id(root)
    deck = HERE / "testbench" / "tb_pnp_vbe.spice"

    print(f"record {record}: {len(SECTIONS) * len(TEMPS)} corner points")
    results: dict[tuple[str, float], dict] = {}
    for section in SECTIONS:
        for temp in TEMPS:
            cid = dc.corner_id(section, temp)
            log = dc.run_corner(deck, pdk, section, temp)
            dc.write_log(
                HERE / "corners",
                record,
                cid,
                dc.log_header(pdk, deck, section, temp, record, stamp),
                log,
            )
            results[(section, temp)] = extract(log, temp)
            print(f"  {cid}: ok")

    dc.snapshot_netlist(HERE / "netlist-snapshots", record, deck)
    path = dc.write_record(
        HERE / "records", record, build_record(record, stamp, pdk, results)
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
