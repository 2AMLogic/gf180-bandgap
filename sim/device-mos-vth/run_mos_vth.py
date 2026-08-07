#!/usr/bin/env python3
"""Run the gf180mcu 3.3 V MOS threshold corner matrix (issue #4).

Executes `testbench/tb_mos_vth.spice` headlessly through ngspice at every
(MOS corner, temperature) point, commits the raw per-corner logs, freezes the
netlist snapshot, and writes one append-only summary record under `records/`
per `sim/README.md`.

This experiment is driven directly against `sim/harness`'s library modules
(`pdk.py`, `runner.py`, `report.py`, `corners.py`) rather than the retired
`sim/tools/devchar.py` (issue #117): PDK discovery, ngspice-version detection,
git provenance / record-id minting and the two-terminal device-testbench
corner-id naming (`sim/README.md`'s `nosupply` grammar) are all harness
functions now. What stays local is genuinely specific to this experiment --
composing/running the per-corner DC-sweep deck, parsing the resulting table,
and the constant-current |Vth| / temperature-drift / process-spread
extraction -- none of which the current `tb.json` single-grid contract
expresses (it targets one scalar `op` measurement per PVT point, not a DC
sweep interpolated at a current criterion). `testbench/tb.json` still
documents this experiment for harness discovery (`sim/run_corners.py --list`)
and supports a secondary, representative generic-CLI run
(`python3 sim/run_corners.py device-mos-vth`) that reports Vgs at the
fragment's fixed 1 uA bias; it is not what produces the record below.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-mos-vth/run_mos_vth.py
"""

from __future__ import annotations

import math
import re
import shutil
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


# --------------------------------------------------------------------------
# Deck composition / ngspice execution -- this experiment sweeps a DC table
# (not the single-scalar `let m_<name>` convention sim/harness/runner.py's
# compose_deck() targets) so it composes its own minimal shim instead of
# going through compose_deck(). PDK model paths still come from
# sim/harness/pdk.py -- nothing here re-resolves the PDK on its own.
# --------------------------------------------------------------------------


def _corner_shim(pdk: harness_pdk.Pdk, section: str, temp_c: float) -> str:
    return (
        "* Generated per corner point by run_mos_vth.py from\n"
        "* $PDK_ROOT/$PDK (via sim/harness/pdk.py) -- do not edit by hand, "
        "and do not commit.\n"
        f'.include "{pdk.design_include}"\n'
        f'.lib "{pdk.model_lib}" {section}\n'
        f".temp {temp_c:g}\n"
    )


def _run_corner(deck: Path, pdk: harness_pdk.Pdk, section: str, temp_c: float) -> str:
    """Run `deck` through ngspice at one (model section, temperature) point."""
    with tempfile.TemporaryDirectory(prefix="device-mos-vth-") as tmp:
        work = Path(tmp)
        local_deck = work / deck.name
        (work / "corner.spice").write_text(
            _corner_shim(pdk, section, temp_c), encoding="utf-8"
        )
        (work / "control.spice").write_text(
            ".control\n"
            "set width  = 512\n"
            "set height = 100000\n"
            "dc Vctrl -8 -3 0.05\n"
            "print v(gn1) v(gn4) v(gp1) v(gp4)\n"
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


def _log_header(
    pdk: harness_pdk.Pdk,
    deck: Path,
    section: str,
    temp_c: float,
    record: str,
    stamp: datetime,
    ngspice: str,
) -> str:
    return (
        "* ====================================================================\n"
        f"* record-id : {record}\n"
        f"* testbench : {deck.name}\n"
        f"* corner    : {section}\n"
        f"* temp      : {temp_c:g} C\n"
        "* supply    : n/a (no supply rail in this device-level testbench)\n"
        f"* pdk       : {pdk.variant} ({pdk.path})\n"
        f"* ngspice   : {ngspice}\n"
        f"* run (UTC) : {stamp:%Y-%m-%dT%H:%M:%SZ}\n"
        "* ====================================================================\n"
    )


def _write_log(corners_dir: Path, record: str, cid: str, header: str, log: str) -> Path:
    out_dir = corners_dir / record
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cid}.log"
    path.write_text(header + log, encoding="utf-8")
    return path


def _snapshot_netlist(snapshot_dir: Path, record: str, deck: Path) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{record}.spice"
    shutil.copyfile(deck, path)
    return path


def _write_record(records_dir: Path, record: str, body: str) -> Path:
    """Write `records/<record-id>.md`, refusing to overwrite (append-only)."""
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / f"{record}.md"
    if path.exists():
        raise RuntimeError(
            f"refusing to overwrite existing record {path} -- sim/ is append-only; "
            "a re-run must mint a new record ID"
        )
    path.write_text(body, encoding="utf-8")
    return path


def _parse_dc_table(log: str) -> tuple[list[str], list[list[float]]]:
    """Parse the tabular output of `print v1 v2 ...` after a `dc` analysis.

    Returns (column names excluding the Index column, rows). The leading
    `v-sweep` column is kept as the first data column.
    """
    lines = log.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Index"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("no DC table header ('Index ...') found in ngspice log")
    columns = lines[header_idx].split()[1:]
    rows: list[list[float]] = []
    for line in lines[header_idx + 1 :]:
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        try:
            values = [float(p) for p in parts[1:]]
        except ValueError:
            continue
        if len(values) == len(columns):
            rows.append(values)
    if not rows:
        raise ValueError("DC table header found but no data rows parsed")
    return columns, rows


def _column(columns: list[str], rows: list[list[float]], name: str) -> list[float]:
    idx = columns.index(name)
    return [row[idx] for row in rows]


def _interp_at(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation of y(x) on a monotonically increasing xs."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if xs[i] >= x:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


# --------------------------------------------------------------------------
# Device-specific analysis
# --------------------------------------------------------------------------


def extract(log: str) -> dict:
    columns, rows = _parse_dc_table(log)
    logi = _column(columns, rows, "v-sweep")
    out: dict = {"vth": {}, "vgs": {}, "icrit": {}}
    for name, (vec, w, length, sign) in DUTS.items():
        vgs = [sign * v for v in _column(columns, rows, vec)]
        icrit = ICRIT_PER_SQUARE * (w / length)
        out["icrit"][name] = icrit
        out["vth"][name] = _interp_at(logi, vgs, math.log10(icrit))
        out["vgs"][name] = {
            bias: _interp_at(logi, vgs, math.log10(bias)) for bias in BIASES_A
        }
    return out


def build_record(record, stamp, pdk, ngspice, results) -> str:
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
    deck = HERE / "testbench" / "tb_mos_vth.spice"

    print(f"record {record}: {len(SECTIONS) * len(TEMPS)} corner points")
    results: dict[tuple[str, float], dict] = {}
    for section in SECTIONS:
        for temp in TEMPS:
            cid = harness_corners.device_corner_id(section, temp)
            log = _run_corner(deck, pdk, section, temp)
            _write_log(
                HERE / "corners",
                record,
                cid,
                _log_header(pdk, deck, section, temp, record, stamp, ngspice),
                log,
            )
            results[(section, temp)] = extract(log)
            print(f"  {cid}: ok")

    _snapshot_netlist(HERE / "netlist-snapshots", record, deck)
    path = _write_record(
        HERE / "records", record, build_record(record, stamp, pdk, ngspice, results)
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
