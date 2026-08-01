#!/usr/bin/env python3
"""Reproducible, append-only ``klt extract`` + ``klt lvs`` run for ``layout/``.

The LVS half of the flow ``layout/drc/run_drc.py`` starts. Given a GDS and a
reference netlist it:

1. regenerates the reference netlist (``layout/lvs/make_reference.py``) so a
   stale, hand-edited reference can never quietly pass;
2. runs ``klt extract --deck gf180mcu`` and keeps the extracted netlist;
3. runs ``klt lvs`` against the reference;
4. writes all three artefacts under
   ``layout/lvs/reports/<block>/<record-id>.*``.

``<record-id>`` is ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, the same
convention ``sim/README.md`` documents for ``sim/`` evidence and
``layout/drc/run_drc.py`` uses for DRC reports. **Reports are never
overwritten** — CLAUDE.md: "``sim/`` results are append-only evidence", and
this repo applies the same rule to ``layout/`` reports.

Usage (from the repo root)::

    python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_ROOT = Path(__file__).resolve().parent / "reports"
REFERENCE = Path(__file__).resolve().parent / "bandgap_top.ref.spice"
MAKE_REFERENCE = Path(__file__).resolve().parent / "make_reference.py"


def _short_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = out.stdout.strip()
    return commit[:7] if commit else "unknown"


def _record_id(reports_dir: Path, when: _dt.datetime, short_sha: str) -> str:
    while True:
        record_id = f"{when.strftime('%Y%m%d-%H%M%S')}-{short_sha}"
        if not (reports_dir / f"{record_id}.lvs.json").exists():
            return record_id
        when += _dt.timedelta(seconds=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gds", type=Path, help="path to the GDS/OASIS file")
    parser.add_argument("--block", help="report subdirectory (default: the GDS stem)")
    parser.add_argument("--deck", default="gf180mcu", help="extraction deck")
    parser.add_argument("--top", default=None, help="top cell (default: the GDS stem)")
    parser.add_argument(
        "--reference",
        type=Path,
        default=REFERENCE,
        help="reference netlist (regenerated before the run)",
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

    # 1. Regenerate the reference so it can never be stale relative to the
    #    schematic netlist or the layout plan.
    regen = subprocess.run(
        [sys.executable, str(MAKE_REFERENCE), "-o", str(args.reference)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if regen.returncode != 0:
        print(regen.stdout, regen.stderr, file=sys.stderr)
        print("error: could not regenerate the reference netlist", file=sys.stderr)
        return 1

    record_id = _record_id(reports_dir, _dt.datetime.now(_dt.timezone.utc), _short_sha())
    gds_rel = gds_path.relative_to(REPO_ROOT)
    extracted = reports_dir / f"{record_id}.extracted.spice"

    # 2. Extract.
    extract_proc = subprocess.run(
        [
            klt, "extract", str(gds_rel),
            "--deck", args.deck,
            "--top", top,
            "--format", "json",
            "-o", str(extracted),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if extract_proc.returncode != 0:
        print(extract_proc.stdout, extract_proc.stderr, file=sys.stderr)
        print(f"error: klt extract failed (exit {extract_proc.returncode})", file=sys.stderr)
        return 1
    (reports_dir / f"{record_id}.extract.json").write_text(extract_proc.stdout)

    # 3. Compare.
    #
    # `klt lvs` resolves every relative path inside a request document
    # against the **request file's own directory**, not the process cwd
    # (klayout_tools.lvs.run_lvs -> `request_dir`). The request lives under
    # layout/lvs/reports/<block>/, so repo-root-relative paths would resolve
    # to nonexistent files. Emit paths relative to the request directory
    # instead — machine-independent (unlike absolute paths), so the committed
    # request document stays reproducible on any checkout.
    request_path = reports_dir / f"{record_id}.lvs-request.json"
    request = {
        "layout": {
            "file": os.path.relpath(gds_path, reports_dir),
            "deck": args.deck,
            "top": top,
        },
        "reference": {
            "netlist": os.path.relpath(args.reference.resolve(), reports_dir),
            "top": top,
        },
    }
    request_path.write_text(json.dumps(request, indent=2) + "\n")

    lvs_json = subprocess.run(
        [klt, "lvs", str(request_path.relative_to(REPO_ROOT)), "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # exit 0 (match) and exit 3 (mismatch) are both successful runs.
    if lvs_json.returncode not in (0, 3):
        print(lvs_json.stdout, lvs_json.stderr, file=sys.stderr)
        print(f"error: klt lvs failed (exit {lvs_json.returncode})", file=sys.stderr)
        return 1
    lvs_text = subprocess.run(
        [klt, "lvs", str(request_path.relative_to(REPO_ROOT)), "--format", "text"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    (reports_dir / f"{record_id}.lvs.json").write_text(lvs_json.stdout)
    (reports_dir / f"{record_id}.lvs.txt").write_text(lvs_text.stdout)

    payload = json.loads(lvs_json.stdout)
    extract_payload = json.loads(extract_proc.stdout)
    print(f"record id        : {record_id}")
    print(f"block            : {block}")
    print(f"extracted devices: {extract_payload['device_count']} "
          f"{extract_payload['device_counts']}")
    print(f"lvs status       : {payload['status']}")
    print(f"mismatch_count   : {payload['mismatch_count']}")
    print(f"devices matched  : {payload['counts']['devices']['matched']} / "
          f"{payload['counts']['devices']['reference']}")
    print(f"nets matched     : {payload['counts']['nets']['matched']} / "
          f"{payload['counts']['nets']['reference']}")
    print(f"report (json)    : {(reports_dir / f'{record_id}.lvs.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
