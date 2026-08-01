#!/usr/bin/env python3
"""Reproducible, append-only ``klt drc`` invocation for ``layout/``.

Runs ``klt drc <gds> --deck gf180mcu`` (both ``--format json`` and
``--format text``) and writes the output under
``layout/drc/reports/<fixture>/<record-id>.drc.{json,txt}``.

``<record-id>`` is ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, matching the
convention ``sim/README.md`` documents for ``sim/`` evidence
(``sim/harness/report.py``). This script never overwrites an existing
report -- CLAUDE.md: "``sim/`` results are append-only evidence", and this
repo applies the same rule to ``layout/`` DRC reports (see
``layout/README.md``). On a same-second collision it advances the
timestamp by one second rather than clobbering.

Requires ``klt`` on ``PATH`` -- see ``layout/README.md`` for install
instructions (no PyPI release yet; install from the klayout-tools git repo).

Usage (from the repo root):

    python3 layout/drc/run_drc.py layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds

    # explicit fixture name / deck, if ever needed:
    python3 layout/drc/run_drc.py <path/to.gds> --fixture <name> --deck gf180mcu
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
        if not (reports_dir / f"{record_id}.drc.json").exists():
            return record_id
        when += _dt.timedelta(seconds=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gds", type=Path, help="path to the GDS/OASIS file to check")
    parser.add_argument(
        "--fixture",
        help="report subdirectory name (default: the GDS file's stem)",
    )
    parser.add_argument("--deck", default="gf180mcu", help="DRC deck (default: gf180mcu)")
    args = parser.parse_args()

    klt = shutil.which("klt")
    if klt is None:
        print(
            "error: 'klt' not found on PATH. Install with:\n"
            "  uv tool install git+https://github.com/2AMLogic/klayout-tools\n"
            "(no PyPI release yet -- see layout/README.md)",
            file=sys.stderr,
        )
        return 1

    gds_path = args.gds
    if not gds_path.is_absolute():
        gds_path = (Path.cwd() / gds_path).resolve()
    if not gds_path.exists():
        print(f"error: {gds_path} does not exist", file=sys.stderr)
        return 1

    fixture = args.fixture or gds_path.stem
    reports_dir = REPORTS_ROOT / fixture
    reports_dir.mkdir(parents=True, exist_ok=True)

    when = _dt.datetime.now(_dt.timezone.utc)
    record_id = _record_id(reports_dir, when, _short_sha())

    # Relative path from the repo root, so the committed report's "file"
    # field is reproducible regardless of invocation cwd.
    gds_rel = gds_path.relative_to(REPO_ROOT)

    json_proc = subprocess.run(
        [klt, "drc", str(gds_rel), "--deck", args.deck, "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    text_proc = subprocess.run(
        [klt, "drc", str(gds_rel), "--deck", args.deck, "--format", "text"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    # exit 0 (clean) and exit 3 (violations found) are both successful runs
    # per klt drc's documented exit-code contract; only exit 1/2 are errors.
    if json_proc.returncode not in (0, 3):
        print(json_proc.stdout, file=sys.stdout)
        print(json_proc.stderr, file=sys.stderr)
        print(f"error: klt drc failed (exit {json_proc.returncode})", file=sys.stderr)
        return 1

    json_path = reports_dir / f"{record_id}.drc.json"
    text_path = reports_dir / f"{record_id}.drc.txt"
    json_path.write_text(json_proc.stdout)
    text_path.write_text(text_proc.stdout)

    payload = json.loads(json_proc.stdout)
    print(f"record id      : {record_id}")
    print(f"fixture         : {fixture}")
    print(f"status          : {payload['status']}")
    print(f"violation_count : {payload['violation_count']}")
    print(f"report (json)   : {json_path.relative_to(REPO_ROOT)}")
    print(f"report (text)   : {text_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
