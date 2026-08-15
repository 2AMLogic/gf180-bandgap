#!/usr/bin/env python3
"""Run the gf180mcu resistor-flavor characterization corner matrix (issue #4).

Executes `testbench/tb_resistor_tc.spice` headlessly through ngspice at every
(resistor corner, temperature) point plus a well-bias sensitivity check,
commits the raw per-corner logs, freezes the netlist snapshot, and writes one
append-only summary record under `records/` per `sim/README.md`.

This experiment is driven directly against `sim/harness`'s library modules
(`pdk.py`, `runner.py`, `report.py`, `corners.py`) rather than the retired
`sim/tools/devchar.py` (issue #117): PDK discovery, ngspice-version detection,
git provenance / record-id minting and the two-terminal device-testbench
corner-id naming (`sim/README.md`'s `nosupply` grammar) are all harness
functions now. What stays local is genuinely specific to this experiment --
composing/running the per-corner deck for a 12-DUT, no-supply-rail
characterization plus its well-bias and HV-bias sub-sweeps, parsing raw
`print` output, and the sheet-resistance / TC / corner-spread / VCR analysis
-- none of which the current `tb.json` single-grid contract expresses.
`testbench/tb.json` still documents this experiment for harness discovery
(`sim/run_corners.py --list`) and supports a secondary, representative
generic-CLI run (`python3 sim/run_corners.py device-resistor-tc`) that reports
the raw DUT currents; it is not what produces the record below.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-resistor-tc/run_resistor_tc.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import corners as harness_corners  # noqa: E402
from harness import pdk as harness_pdk  # noqa: E402
from harness import report as harness_report  # noqa: E402
from harness.runner import ngspice_version  # noqa: E402

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


# --------------------------------------------------------------------------
# Deck composition / ngspice execution -- this experiment measures 12 DUTs
# per corner via raw `print` (not the single-scalar `let m_<name>` convention
# sim/harness/runner.py's compose_deck() targets) and layers a well-bias
# sub-sweep with an extra `.param` on top of the main grid, so it composes
# its own minimal shim instead of going through compose_deck(). PDK model
# paths still come from sim/harness/pdk.py -- nothing here re-resolves the
# PDK on its own.
# --------------------------------------------------------------------------


def _run_corner(
    deck: Path, pdk: harness_pdk.Pdk, section: str, temp_c: float, extra_shim: str = ""
) -> str:
    """Run `deck` through ngspice at one (model section, temperature) point."""
    with tempfile.TemporaryDirectory(prefix="device-resistor-tc-") as tmp:
        work = Path(tmp)
        local_deck = work / deck.name
        (work / "corner.spice").write_text(
            harness_report.corner_shim(
                pdk, section, temp_c, script_name="run_resistor_tc.py", extra=extra_shim
            ),
            encoding="utf-8",
        )
        (work / "control.spice").write_text(
            ".control\n"
            "op\n"
            "print i(v_pu_w1) i(v_pu_w5)\n"
            "print i(v_p1k_w1) i(v_p1k_w5)\n"
            "print i(v_p2k_w1) i(v_p2k_w5)\n"
            "print i(v_p3k_w1) i(v_p3k_w5)\n"
            "print i(v_pp_w1) i(v_pp_w5)\n"
            "print i(v_np_w1) i(v_np_w5)\n"
            "print i(v_p1k_hv) i(v_p2k_hv) i(v_p3k_hv)\n"
            "quit\n"
            ".endc\n",
            encoding="utf-8",
        )
        local_deck.write_text(
            '.include "corner.spice"\n'
            + deck.read_text(encoding="utf-8")
            + '\n.include "control.spice"\n.end\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["ngspice", "-b", deck.name],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )
    log = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(
            f"ngspice exited {proc.returncode} for {deck.name} "
            f"[{section} @ {temp_c} C]\n{log}"
        )
    if re.search(r"^\s*(Error|ERROR|fatal)", log, re.MULTILINE):
        raise RuntimeError(f"ngspice reported an error for {deck.name}:\n{log}")
    return log


_OP_LINE = re.compile(r"^([a-zA-Z_][\w()\-.,+@#]*)\s*=\s*([-+0-9.eE]+)\s*$")


def _parse_op(log: str) -> dict[str, float]:
    """Parse `print a b c` scalars emitted by an `op` analysis."""
    values: dict[str, float] = {}
    for line in log.splitlines():
        match = _OP_LINE.match(line.strip())
        if match:
            try:
                values[match.group(1).lower()] = float(match.group(2))
            except ValueError:
                continue
    return values


# --------------------------------------------------------------------------
# Device-specific analysis
# --------------------------------------------------------------------------


def resistances(log: str) -> dict[str, float]:
    values = _parse_op(log)
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


def build_record(record, stamp, pdk, ngspice, results, supply_check) -> str:
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
    add(f"  - PDK: {pdk.variant} ({pdk.path}), ngspice {ngspice}")
    add(
        f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder "
        "(issue #4, re-run onto sim/harness by issue #117)"
    )
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


def main() -> int:
    pdk = harness_pdk.find_pdk()
    root = harness_pdk.REPO_ROOT
    ngspice = ngspice_version()
    git = harness_report.git_provenance(root)
    record = harness_report.allocate_record_id(root, HERE / "records", git=git)
    stamp = datetime.strptime(record[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    deck = HERE / "testbench" / "tb_resistor_tc.spice"

    print(f"record {record}: {len(SECTIONS) * len(TEMPS)} corner points + 2 well-bias")
    results: dict[tuple[str, float], dict[str, float]] = {}
    for section in SECTIONS:
        for temp in TEMPS:
            cid = harness_corners.device_corner_id(section, temp)
            log = _run_corner(
                deck, pdk, section, temp, f".param v_nwell = {NOMINAL_NWELL}"
            )
            harness_report.write_device_corner_log(
                HERE / "corners",
                record,
                cid,
                harness_report.device_log_header(
                    pdk, deck, section, temp, record, stamp, ngspice
                ),
                log,
            )
            results[(section, temp)] = resistances(log)
            print(f"  {cid}: ok")

    supply_check: dict[float, dict[str, float]] = {}
    for vnw in (2.97, 3.63):
        tag = f"nwell{vnw:.2f}v".replace(".", "p")
        cid = harness_corners.device_corner_id("res_typical", 27.0, tag)
        log = _run_corner(deck, pdk, "res_typical", 27.0, f".param v_nwell = {vnw}")
        harness_report.write_device_corner_log(
            HERE / "corners",
            record,
            cid,
            harness_report.device_log_header(
                pdk, deck, "res_typical", 27.0, record, stamp, ngspice
            ),
            log,
        )
        supply_check[vnw] = resistances(log)
        print(f"  {cid}: ok")

    harness_report.write_device_netlist_snapshot(
        HERE / "netlist-snapshots", record, deck
    )
    path = harness_report.device_write_record(
        HERE / "records",
        record,
        build_record(record, stamp, pdk, ngspice, results, supply_check),
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
