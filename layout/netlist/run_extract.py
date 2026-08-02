#!/usr/bin/env python3
"""Reproducible, append-only ``klt extract --parasitics`` invocation for
``bandgap_top`` (#17's item 1: post-layout parasitic extraction).

Runs ``klt extract <gds> --deck gf180mcu --parasitics --pdk <variant>`` and
writes the extracted SPICE netlist plus its JSON summary under
``layout/netlist/reports/<block>/<record-id>.*``. ``--pdk`` (resolved via
the same resolver every other PDK-aware ``klt`` verb uses) is passed so MOS
devices bind to the real gf180mcu ``nfet_03v3``/``pfet_03v3`` models
instead of the deck's generic ``nfet``/``pfet`` class tokens -- see
``docs/cli/extract.md`` in klayout-tools ("PDK-bound MOS device models").

``<record-id>`` is ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, the same
convention ``sim/README.md`` documents for ``sim/`` evidence and
``layout/drc/run_drc.py`` / ``layout/lvs/run_lvs.py`` use for their own
reports. **Reports are never overwritten** -- CLAUDE.md: "``sim/`` results
are append-only evidence", and this repo applies the same rule to
``layout/`` reports.

Requires ``klt`` on ``PATH`` -- see ``layout/README.md`` for install
instructions.

Usage (from the repo root)::

    python3 layout/netlist/run_extract.py layout/bandgap_top/bandgap_top.gds
    python3 layout/netlist/run_extract.py layout/bandgap_top/bandgap_top.gds --pdk gf180mcuD

**Read ``layout/netlist/README.md`` before treating this netlist as
simulation-ready.** As of this script's introduction (#17), the resistor
and MIM-capacitor device classes klayout-tools' gf180mcu deck can now
recognise (klayout-tools #222/#225) do **not** fire on this repo's drawn
``bandgap_top`` layout -- every discrete ``ppolyf_u`` resistor (``R1``,
``R2``, all 63 trim-ladder segments) and the compensation MIM capacitor
collapse to plain interconnect (an unintended short / an absent device) in
the netlist this script writes, because ``layout/bandgap_top/generate.py``
does not yet draw the marker layers (``RES_MK``/``SAB``/``CAP_MK``) the
deck's recognisers require. See the README for the full finding and the
tracking issue.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_ROOT = Path(__file__).resolve().parent / "reports"


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def _short_sha() -> str:
    commit = _git("rev-parse", "HEAD")
    return commit[:7] if commit else "unknown"


def _record_id(reports_dir: Path, when: _dt.datetime, short_sha: str) -> str:
    while True:
        record_id = f"{when.strftime('%Y%m%d-%H%M%S')}-{short_sha}"
        if not (reports_dir / f"{record_id}.extract.json").exists():
            return record_id
        when += _dt.timedelta(seconds=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gds", type=Path, help="path to the GDS/OASIS file to extract")
    parser.add_argument("--block", help="report subdirectory (default: the GDS stem)")
    parser.add_argument("--deck", default="gf180mcu", help="extraction deck")
    parser.add_argument("--top", default=None, help="top cell (default: the GDS stem)")
    parser.add_argument(
        "--pdk",
        default="gf180mcuD",
        help="PDK variant to resolve for real MOS model binding (default: gf180mcuD, "
        "the 3.3V-flavor variant CLAUDE.md names as primary); pass '' to skip PDK "
        "resolution and keep the deck's generic nfet/pfet class tokens",
    )
    args = parser.parse_args()

    klt = shutil.which("klt")
    if klt is None:
        print(
            "error: 'klt' not found on PATH. Install with:\n"
            "  uv tool install git+https://github.com/2AMLogic/klayout-tools\n"
            "(see layout/README.md)",
            file=sys.stderr,
        )
        return 1

    gds_path = args.gds if args.gds.is_absolute() else (Path.cwd() / args.gds).resolve()
    if not gds_path.exists():
        print(f"error: {gds_path} does not exist", file=sys.stderr)
        return 1

    block = args.block or gds_path.stem
    top = args.top or gds_path.stem
    reports_dir = REPORTS_ROOT / block
    reports_dir.mkdir(parents=True, exist_ok=True)

    record_id = _record_id(reports_dir, _dt.datetime.now(_dt.timezone.utc), _short_sha())
    gds_rel = gds_path.relative_to(REPO_ROOT)
    netlist_path = reports_dir / f"{record_id}.extracted.spice"

    cmd = [
        klt, "extract", str(gds_rel),
        "--deck", args.deck,
        "--top", top,
        "--parasitics",
        "--format", "json",
        "-o", str(netlist_path),
    ]
    if args.pdk:
        cmd += ["--pdk", args.pdk]

    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(proc.stdout, proc.stderr, file=sys.stderr)
        print(f"error: klt extract failed (exit {proc.returncode})", file=sys.stderr)
        return 1

    json_path = reports_dir / f"{record_id}.extract.json"
    json_path.write_text(proc.stdout)

    payload = json.loads(proc.stdout)
    print(f"record id        : {record_id}")
    print(f"block            : {block}")
    print(f"pdk              : {payload.get('pdk')}")
    print(f"extracted devices: {payload['device_count']} {payload['device_counts']}")
    print(f"net_count        : {payload['net_count']}")
    for warning in payload.get("warnings", []):
        print(f"warning          : {warning}")
    print(f"netlist          : {netlist_path.relative_to(REPO_ROOT)}")
    print(f"report (json)    : {json_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
