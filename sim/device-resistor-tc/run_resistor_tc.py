#!/usr/bin/env python3
"""Run the gf180mcu resistor-flavor characterization corner matrix (issue #4).

Executes `testbench/tb_resistor_tc.spice` headlessly through ngspice at every
(resistor corner, temperature) point plus a well-bias sensitivity check,
commits the raw per-corner logs, freezes the netlist snapshot, and writes one
append-only summary record under `records/` per `sim/README.md`.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-resistor-tc/run_resistor_tc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

import devchar as dc  # noqa: E402

SECTIONS = ["res_ss", "res_typical", "res_ff"]
TEMPS = [-40.0, 27.0, 125.0]
NOMINAL_NWELL = 3.3
BIAS_V = 0.050
HV_BIAS_V = 0.500

# name -> (label, ngspice current vector, drawn W um, drawn L um, applied V)
DUTS = {
    "ppolyf_u/W1": ("ppolyf_u", "i(v_pu_w1)", 1.0, 10.0, BIAS_V),
    "ppolyf_u/W5": ("ppolyf_u", "i(v_pu_w5)", 5.0, 50.0, BIAS_V),
    "ppolyf_u_1k/W1": ("ppolyf_u_1k", "i(v_p1k_w1)", 1.0, 10.0, BIAS_V),
    "ppolyf_u_1k/W5": ("ppolyf_u_1k", "i(v_p1k_w5)", 5.0, 50.0, BIAS_V),
    "ppolyf_u_2k/W1": ("ppolyf_u_2k", "i(v_p2k_w1)", 1.0, 10.0, BIAS_V),
    "ppolyf_u_2k/W5": ("ppolyf_u_2k", "i(v_p2k_w5)", 5.0, 50.0, BIAS_V),
    "ppolyf_u_3k/W1": ("ppolyf_u_3k", "i(v_p3k_w1)", 1.0, 10.0, BIAS_V),
    "ppolyf_u_3k/W5": ("ppolyf_u_3k", "i(v_p3k_w5)", 5.0, 50.0, BIAS_V),
    "pplus_u/W1": ("pplus_u", "i(v_pp_w1)", 1.0, 10.0, BIAS_V),
    "pplus_u/W5": ("pplus_u", "i(v_pp_w5)", 5.0, 50.0, BIAS_V),
    "nplus_u/W1": ("nplus_u", "i(v_np_w1)", 1.0, 10.0, BIAS_V),
    "nplus_u/W5": ("nplus_u", "i(v_np_w5)", 5.0, 50.0, BIAS_V),
}

HV_DUTS = {
    "ppolyf_u_1k/W1": "i(v_p1k_hv)",
    "ppolyf_u_2k/W1": "i(v_p2k_hv)",
    "ppolyf_u_3k/W1": "i(v_p3k_hv)",
}


def resistances(log: str) -> dict[str, float]:
    values = dc.parse_op(log)
    out: dict[str, float] = {}
    for name, (_flavor, vec, _w, _l, bias) in DUTS.items():
        out[name] = bias / abs(values[vec])
    for name, vec in HV_DUTS.items():
        out[name + "/HV"] = HV_BIAS_V / abs(values[vec])
    return out


def sheet(name: str, r_ohm: float) -> float:
    _flavor, _vec, w, length, _bias = DUTS[name]
    return r_ohm / (length / w)


def ppm_per_c(r_hot: float, r_cold: float, r_ref: float, dt: float) -> float:
    return 1e6 * (r_hot - r_cold) / (r_ref * dt)


def build_record(record, stamp, pdk, results, supply_check) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add(
        "- **Claim**: gf180mcu resistor-flavor characterization for the PTAT / trim "
        "network of the Brokaw core selected in DR-0001 "
        "(`spec/decision-records/0001-bandgap-topology-selection.md`) -- effective "
        "sheet resistance, temperature coefficient and process-corner spread for "
        "the unsalicided p-poly family (`ppolyf_u`, `ppolyf_u_1k`, `ppolyf_u_2k`, "
        "`ppolyf_u_3k`) and two diffusion flavors (`pplus_u`, `nplus_u`). "
        "**This record makes no spec pass/fail claim**: no ratified spec exists "
        "yet (#1), so every entry below is a measured device number."
    )
    add(
        "- **Netlist provenance**: schematic-level device testbench "
        "(`sim/device-resistor-tc/testbench/tb_resistor_tc.spice`) -- PDK device "
        "models instantiated directly; no `design/` schematic, no extracted layout."
    )
    add("- **Corner matrix run**:")
    add(
        f"  - Process: {', '.join(SECTIONS)} (gf180mcu has no global corner switch; "
        "the resistor sections in `sm141064.ngspice` are the only ones that apply "
        "to this DUT)"
    )
    add("  - Temperature: " + ", ".join(f"{t:g} C" for t in TEMPS))
    add(
        "  - Supply: **not applicable** -- the DUTs are two-terminal resistors "
        "driven from a 50 mV low-field source; there is no supply rail, so the "
        "+/-10% supply axis of the CLAUDE.md PVT matrix has nothing to sweep. "
        "This is the explicit subset justification `sim/README.md` requires; "
        "those corner-log filenames carry `nosupply` in the supply field. The one "
        "node above ground is the n-well tie that reverse-biases the `pplus_u` "
        "well junction; the two extra corner points named `nwell2p97v` / "
        "`nwell3p63v` sweep that tie over +/-10% of 3.3 V to show it does not "
        "move any extracted resistance (table at the end)."
    )
    add(
        f"  - {len(SECTIONS) * len(TEMPS)} corner points "
        f"({len(SECTIONS)} process x {len(TEMPS)} temperature) "
        f"+ {len(supply_check)} well-bias sensitivity points"
    )
    add(
        "- **Statistical convention**: N/A -- corner-matrix characterization, not a "
        "distribution claim. Note that the gf180mcu resistor subcircuits hard-code "
        "`mis_r = 0` (the local-mismatch expression is present but commented out in "
        "`sm141064.ngspice`), so **resistor local mismatch is not simulatable in "
        "this PDK release**; a Monte Carlo run on these devices would report zero "
        "spread and would be misleading. Resistor matching has to be argued from "
        "area and layout technique, not from simulation."
    )
    add("- **Result**: measured device data (no spec comparison -- see Claim).")
    add("")

    # --- resistance + sheet ---
    add("### Resistance and effective sheet resistance at res_typical")
    add("")
    add(
        "All DUTs are drawn as 10 squares (L = 10 x W). `Rsh_eff = R / (L/W)` "
        "therefore folds in the terminal (head) resistance and the drawn-vs-effective "
        "geometry bias, which is why it differs from the nominal `rsh_*` parameter "
        "and differs between the two widths."
    )
    add("")
    add(
        "| DUT | drawn W (um) | R @ -40 C (kohm) | R @ 27 C (kohm) | R @ 125 C (kohm) "
        "| Rsh_eff @ 27 C (ohm/sq) | nominal rsh (ohm/sq) | squares for 100 kohm |"
    )
    add("|---|---|---|---|---|---|---|---|")
    nominal = {
        "ppolyf_u": 350,
        "ppolyf_u_1k": 1000,
        "ppolyf_u_2k": 2000,
        "ppolyf_u_3k": 3000,
        "pplus_u": 185,
        "nplus_u": 60,
    }
    for name, (flavor, _vec, w, _l, _b) in DUTS.items():
        r27 = results[("res_typical", 27.0)][name]
        rsh = sheet(name, r27)
        add(
            f"| `{name}` | {w:g} | "
            + " | ".join(
                f"{results[('res_typical', t)][name] / 1e3:.3f}" for t in TEMPS
            )
            + f" | {rsh:.1f} | {nominal[flavor]} | {100e3 / rsh:.1f} |"
        )
    add("")

    # --- TC ---
    add("### Temperature coefficient (ppm/C), referenced to R(27 C)")
    add("")
    add(
        "`TC_full` is the -40 -> 125 C chord; the two half-range chords expose the "
        "curvature of the PDK's quadratic `r_temp` model, which matters because a "
        "bandgap's residual TC is set by how well the resistor TC cancels over the "
        "whole range, not at one point."
    )
    add("")
    add(
        "| DUT | corner | TC_full -40..125 | TC_cold -40..27 | TC_hot 27..125 |"
    )
    add("|---|---|---|---|---|")
    for name in DUTS:
        for section in SECTIONS:
            r_cold = results[(section, -40.0)][name]
            r_ref = results[(section, 27.0)][name]
            r_hot = results[(section, 125.0)][name]
            add(
                f"| `{name}` | {section} | "
                f"{ppm_per_c(r_hot, r_cold, r_ref, 165.0):+.1f} | "
                f"{ppm_per_c(r_ref, r_cold, r_ref, 67.0):+.1f} | "
                f"{ppm_per_c(r_hot, r_ref, r_ref, 98.0):+.1f} |"
            )
    add("")

    # --- corner spread ---
    add("### Process-corner spread at 27 C, relative to res_typical")
    add("")
    add("| DUT | res_ss (%) | res_ff (%) | total spread (%) | +/- half-spread (%) |")
    add("|---|---|---|---|---|")
    for name in DUTS:
        typ = results[("res_typical", 27.0)][name]
        ss = results[("res_ss", 27.0)][name]
        ff = results[("res_ff", 27.0)][name]
        add(
            f"| `{name}` | {100 * (ss - typ) / typ:+.2f} | "
            f"{100 * (ff - typ) / typ:+.2f} | "
            f"{100 * (ss - ff) / typ:.2f} | "
            f"+/-{100 * (ss - ff) / (2 * typ):.2f} |"
        )
    add("")

    # --- VCR ---
    add("### Voltage coefficient of the high-sheet flavors (W = 1 um, res_typical, 27 C)")
    add("")
    add("| DUT | R @ 50 mV (kohm) | R @ 500 mV (kohm) | implied VCR (ppm/V) |")
    add("|---|---|---|---|")
    for name in HV_DUTS:
        lo = results[("res_typical", 27.0)][name]
        hi = results[("res_typical", 27.0)][name + "/HV"]
        vcr = 1e6 * (hi - lo) / (lo * (HV_BIAS_V - BIAS_V))
        add(f"| `{name}` | {lo / 1e3:.4f} | {hi / 1e3:.4f} | {vcr:+.1f} |")
    add("")
    add(
        "A VCR of exactly zero is a **model limitation, not a measurement**: the "
        "gf180mcu resistor subcircuits set `r_vc1 = r_vc2 = 0`, so voltage "
        "coefficient is not modelled in this PDK release. Silicon high-sheet poly "
        "does have a finite VCR; a design that relies on VCR being negligible "
        "cannot cite this simulation as evidence."
    )
    add("")

    # --- well bias sensitivity ---
    add("### n-well tie sensitivity (res_typical, 27 C)")
    add("")
    add(
        "`pplus_u` is the only DUT whose bulk terminal is not at ground. Sweeping "
        "its n-well tie over +/-10% of 3.3 V confirms the +/-10% supply axis of the "
        "PVT matrix is genuinely inapplicable to this testbench."
    )
    add("")
    add("| DUT | R @ 2.97 V (kohm) | R @ 3.30 V (kohm) | R @ 3.63 V (kohm) | delta (ppm) |")
    add("|---|---|---|---|---|")
    for name in ("pplus_u/W1", "pplus_u/W5"):
        nom = results[("res_typical", 27.0)][name]
        lo = supply_check[2.97][name]
        hi = supply_check[3.63][name]
        add(
            f"| `{name}` | {lo / 1e3:.5f} | {nom / 1e3:.5f} | {hi / 1e3:.5f} | "
            f"{1e6 * (hi - lo) / nom:.3f} |"
        )
    add("")

    add("- **Links**:")
    add("  - Testbench: `sim/device-resistor-tc/testbench/tb_resistor_tc.spice`")
    add("  - Run script: `sim/device-resistor-tc/run_resistor_tc.py`")
    add(
        f"  - Netlist snapshot: `sim/device-resistor-tc/netlist-snapshots/{record}.spice`"
    )
    add(f"  - Raw logs: `sim/device-resistor-tc/corners/{record}/`")
    add(f"  - PDK: {pdk.label}, ngspice {dc.ngspice_version()}")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #4)")
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


def main() -> int:
    pdk = dc.resolve_pdk()
    root = dc.repo_root(HERE)
    record, stamp = dc.mint_record_id(root)
    deck = HERE / "testbench" / "tb_resistor_tc.spice"

    print(f"record {record}: {len(SECTIONS) * len(TEMPS)} corner points + 2 well-bias")
    results: dict[tuple[str, float], dict[str, float]] = {}
    for section in SECTIONS:
        for temp in TEMPS:
            cid = dc.corner_id(section, temp)
            log = dc.run_corner(
                deck, pdk, section, temp, f".param v_nwell = {NOMINAL_NWELL}"
            )
            dc.write_log(
                HERE / "corners",
                record,
                cid,
                dc.log_header(pdk, deck, section, temp, record, stamp),
                log,
            )
            results[(section, temp)] = resistances(log)
            print(f"  {cid}: ok")

    supply_check: dict[float, dict[str, float]] = {}
    for vnw in (2.97, 3.63):
        tag = f"nwell{vnw:.2f}v".replace(".", "p")
        cid = dc.corner_id("res_typical", 27.0, tag)
        log = dc.run_corner(deck, pdk, "res_typical", 27.0, f".param v_nwell = {vnw}")
        dc.write_log(
            HERE / "corners",
            record,
            cid,
            dc.log_header(pdk, deck, "res_typical", 27.0, record, stamp),
            log,
        )
        supply_check[vnw] = resistances(log)
        print(f"  {cid}: ok")

    dc.snapshot_netlist(HERE / "netlist-snapshots", record, deck)
    path = dc.write_record(
        HERE / "records",
        record,
        build_record(record, stamp, pdk, results, supply_check),
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
