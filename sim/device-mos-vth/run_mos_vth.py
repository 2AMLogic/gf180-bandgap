#!/usr/bin/env python3
"""Run the gf180mcu 3.3 V MOS threshold corner matrix (issue #4).

Executes `testbench/tb_mos_vth.spice` headlessly through ngspice at every
(MOS corner, temperature) point, commits the raw per-corner logs, freezes the
netlist snapshot, and writes one append-only summary record under `records/`
per `sim/README.md`.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-mos-vth/run_mos_vth.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

import devchar as dc  # noqa: E402

# gf180mcu MOS corner sections. `typical`/`ff`/`ss`/`fs`/`sf` are top-level
# `.LIB` wrappers in sm141064.ngspice that pull in the matching nfet_03v3_* and
# pfet_03v3_* bins (fs = fast NMOS / slow PMOS, sf = the reverse).
SECTIONS = ["typical", "ff", "ss", "fs", "sf"]
TEMPS = [-40.0, 27.0, 125.0]

# name -> (ngspice vector, W um, L um, polarity sign)
DUTS = {
    "nfet_03v3 10/1": ("v(gn1)", 10.0, 1.0, +1),
    "nfet_03v3 10/4": ("v(gn4)", 10.0, 4.0, +1),
    "pfet_03v3 10/1": ("v(gp1)", 10.0, 1.0, -1),
    "pfet_03v3 10/4": ("v(gp4)", 10.0, 4.0, -1),
}

# Constant-current threshold criterion for 0.18 um-class devices.
ICRIT_PER_SQUARE = 100e-9  # Id_crit = 100 nA * (W/L)
BIASES_A = [1e-6, 5e-6, 10e-6, 20e-6]


def extract(log: str) -> dict:
    columns, rows = dc.parse_dc_table(log)
    logi = dc.column(columns, rows, "v-sweep")
    out: dict = {"vth": {}, "vgs": {}, "icrit": {}}
    for name, (vec, w, length, sign) in DUTS.items():
        vgs = [sign * v for v in dc.column(columns, rows, vec)]
        icrit = ICRIT_PER_SQUARE * (w / length)
        out["icrit"][name] = icrit
        out["vth"][name] = dc.interp_at(logi, vgs, math.log10(icrit))
        out["vgs"][name] = {
            bias: dc.interp_at(logi, vgs, math.log10(bias)) for bias in BIASES_A
        }
    return out


def build_record(record, stamp, pdk, results) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add(
        "- **Claim**: gf180mcu 3.3 V MOS threshold characterization for the "
        "mirror / cascode / amplifier devices of the Brokaw core selected in "
        "DR-0001 (`spec/decision-records/0001-bandgap-topology-selection.md`) at "
        "the 3.3 V-only supply scope of DR-0002-supply -- |Vth| and Vgs vs "
        "temperature and process corner at microamp-scale bias. **This record "
        "makes no spec pass/fail claim**: no ratified spec exists yet (#1), so "
        "every entry below is a measured device number."
    )
    add(
        "- **Extraction method**: **constant-current threshold** -- each DUT is "
        "diode-connected (Vds = Vgs, saturation) with Vsb = 0, and |Vth| is read "
        "as |Vgs| at Id = 100 nA x (W/L). Max-gm extrapolation was not used; the "
        "constant-current criterion is what a current-mirror bias budget actually "
        "cares about and it is single-valued across all corners without a fitting "
        "window."
    )
    add(
        "- **Netlist provenance**: schematic-level device testbench "
        "(`sim/device-mos-vth/testbench/tb_mos_vth.spice`) -- PDK device models "
        "instantiated directly; no `design/` schematic, no extracted layout."
    )
    add("- **Corner matrix run**:")
    add(
        f"  - Process: {', '.join(SECTIONS)} (the top-level MOS `.LIB` sections in "
        "`sm141064.ngspice`; `fs` = fast NMOS / slow PMOS, `sf` = the reverse. "
        "gf180mcu has no global corner switch, so only the MOS sections apply "
        "to this DUT)"
    )
    add("  - Temperature: " + ", ".join(f"{t:g} C" for t in TEMPS))
    add(
        "  - Supply: **not applicable** -- each DUT is referred to its own source "
        "node at ground and driven by an ideal current source; there is no supply "
        "rail, so the +/-10% supply axis of the CLAUDE.md PVT matrix has nothing "
        "to sweep. This is the explicit subset justification `sim/README.md` "
        "requires; the corner-log filenames carry `nosupply` in the supply field. "
        "Supply sensitivity is a circuit-level property and belongs to the "
        "PSRR/line-regulation testbenches, not to a device threshold extraction."
    )
    add(
        f"  - {len(SECTIONS) * len(TEMPS)} corner points "
        f"({len(SECTIONS)} process x {len(TEMPS)} temperature)"
    )
    add(
        "- **Statistical convention**: N/A here -- this record is the corner "
        "matrix. Local mismatch is a separate distribution claim and lives in the "
        "`sim/device-mos-mismatch/` record."
    )
    add("- **Result**: measured device data (no spec comparison -- see Claim).")
    add("")

    add("### Constant-current |Vth| (V) at Id = 100 nA x (W/L)")
    add("")
    add(
        "| DUT | Id_crit | "
        + " | ".join(f"{s} @ {t:g} C" for s in SECTIONS for t in TEMPS)
        + " |"
    )
    add("|---|---|" + "---|" * (len(SECTIONS) * len(TEMPS)))
    for name in DUTS:
        icrit = results[(SECTIONS[0], TEMPS[0])]["icrit"][name]
        cells = [
            f"{results[(s, t)]['vth'][name]:.4f}" for s in SECTIONS for t in TEMPS
        ]
        add(f"| `{name}` | {icrit * 1e9:.0f} nA | " + " | ".join(cells) + " |")
    add("")

    add("### |Vth| temperature drift (mV/C)")
    add("")
    add(
        "Chord slopes rather than a fit: `full` is -40 -> 125 C, the half chords "
        "expose curvature."
    )
    add("")
    add("| DUT | corner | full -40..125 | cold -40..27 | hot 27..125 |")
    add("|---|---|---|---|---|")
    for name in DUTS:
        for section in SECTIONS:
            cold = results[(section, -40.0)]["vth"][name]
            ref = results[(section, 27.0)]["vth"][name]
            hot = results[(section, 125.0)]["vth"][name]
            add(
                f"| `{name}` | {section} | "
                f"{1e3 * (hot - cold) / 165.0:+.3f} | "
                f"{1e3 * (ref - cold) / 67.0:+.3f} | "
                f"{1e3 * (hot - ref) / 98.0:+.3f} |"
            )
    add("")

    add("### |Vth| process spread at 27 C (mV, relative to `typical`)")
    add("")
    add("| DUT | typical (V) | ff | ss | fs | sf | total spread (mV) |")
    add("|---|---|---|---|---|---|---|")
    for name in DUTS:
        typ = results[("typical", 27.0)]["vth"][name]
        others = {
            s: results[(s, 27.0)]["vth"][name] for s in SECTIONS if s != "typical"
        }
        spread = max(list(others.values()) + [typ]) - min(
            list(others.values()) + [typ]
        )
        add(
            f"| `{name}` | {typ:.4f} | "
            + " | ".join(f"{1e3 * (others[s] - typ):+.1f}" for s in ("ff", "ss", "fs", "sf"))
            + f" | {1e3 * spread:.1f} |"
        )
    add("")

    add("### |Vgs| (V) at candidate core bias currents, `typical` corner")
    add("")
    add(
        "Overdrive at any of these biases is `|Vgs| - |Vth|` using the |Vth| table "
        "above; the raw |Vgs| is given so downstream sizing (#8) does not have to "
        "re-derive it."
    )
    add("")
    add(
        "| DUT | T (C) | "
        + " | ".join(f"{b * 1e6:g} uA" for b in BIASES_A)
        + " |"
    )
    add("|---|---|" + "---|" * len(BIASES_A))
    for name in DUTS:
        for temp in TEMPS:
            cells = [
                f"{results[('typical', temp)]['vgs'][name][b]:.4f}" for b in BIASES_A
            ]
            add(f"| `{name}` | {temp:g} | " + " | ".join(cells) + " |")
    add("")

    add("- **Links**:")
    add("  - Testbench: `sim/device-mos-vth/testbench/tb_mos_vth.spice`")
    add("  - Run script: `sim/device-mos-vth/run_mos_vth.py`")
    add(f"  - Netlist snapshot: `sim/device-mos-vth/netlist-snapshots/{record}.spice`")
    add(f"  - Raw logs: `sim/device-mos-vth/corners/{record}/`")
    add(f"  - PDK: {pdk.label}, ngspice {dc.ngspice_version()}")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #4)")
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


def main() -> int:
    pdk = dc.resolve_pdk()
    root = dc.repo_root(HERE)
    record, stamp = dc.mint_record_id(root)
    deck = HERE / "testbench" / "tb_mos_vth.spice"

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
            results[(section, temp)] = extract(log)
            print(f"  {cid}: ok")

    dc.snapshot_netlist(HERE / "netlist-snapshots", record, deck)
    path = dc.write_record(
        HERE / "records", record, build_record(record, stamp, pdk, results)
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
