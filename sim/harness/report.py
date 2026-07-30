"""Summaries, spec checks, and append-only result files.

CLAUDE.md: "sim/ results are append-only evidence." This module never
overwrites an existing result file -- if a name collides it takes the next
free suffix. Deleting evidence is a human decision, not a script's.
"""

from __future__ import annotations

import csv
import datetime as _dt
import getpass
import json
import platform
import socket
import subprocess
import sys
from pathlib import Path

from . import HARNESS_VERSION
from .corners import PvtPoint
from .pdk import Pdk
from .runner import PointResult
from .testbench import Testbench

SCHEMA = "gf180-bandgap/sim-result/1"


def _git(*args: str, cwd: Path) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
        return out.stdout.strip()
    except OSError:  # pragma: no cover - git always present in this repo
        return ""


def git_provenance(repo_root: Path) -> dict:
    commit = _git("rev-parse", "HEAD", cwd=repo_root)
    dirty = bool(_git("status", "--porcelain", cwd=repo_root))
    return {
        "commit": commit or "unknown",
        "short": (commit[:7] if commit else "unknown"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_root) or "unknown",
        "dirty": dirty,
    }


def make_run_id(repo_root: Path, when: _dt.datetime | None = None) -> str:
    when = when or _dt.datetime.now(_dt.timezone.utc)
    git = git_provenance(repo_root)
    suffix = git["short"] + ("-dirty" if git["dirty"] else "")
    return f"{when.strftime('%Y%m%dT%H%M%SZ')}-{suffix}"


def summarize(results: list[PointResult], measure_names: list[str]) -> dict:
    """Min / max / mean / spread of each measurement across the PVT grid."""
    summary: dict[str, dict] = {}
    ok = [r for r in results if r.status == "ok"]
    for name in measure_names:
        samples = [(r.measurements[name], r.point.label) for r in ok if name in r.measurements]
        if not samples:
            summary[name] = {"n": 0}
            continue
        values = [v for v, _ in samples]
        lo_value, lo_at = min(samples, key=lambda s: s[0])
        hi_value, hi_at = max(samples, key=lambda s: s[0])
        mean = sum(values) / len(values)
        spread_pct = (hi_value - lo_value) / abs(mean) * 100.0 if mean else None
        summary[name] = {
            "n": len(values),
            "min": lo_value,
            "min_at": lo_at,
            "max": hi_value,
            "max_at": hi_at,
            "mean": mean,
            "spread_pct": spread_pct,
        }
    return summary


def evaluate_checks(
    checks: dict[str, dict],
    results: list[PointResult],
    summary: dict,
) -> list[dict]:
    """Return a list of check failures (empty list == everything passed)."""
    failures: list[dict] = []
    for name, spec in checks.items():
        low = spec.get("min")
        high = spec.get("max")
        if low is not None or high is not None:
            for result in results:
                if result.status != "ok" or name not in result.measurements:
                    continue
                value = result.measurements[name]
                if low is not None and value < low:
                    failures.append(
                        {
                            "measurement": name,
                            "kind": "min",
                            "limit": low,
                            "value": value,
                            "at": result.point.label,
                        }
                    )
                if high is not None and value > high:
                    failures.append(
                        {
                            "measurement": name,
                            "kind": "max",
                            "limit": high,
                            "value": value,
                            "at": result.point.label,
                        }
                    )
        # Grid-level spread checks. max_spread_pct is the usual "this must be
        # stable over PVT" assertion; min_spread_pct is its inverse and exists
        # to prove the harness is actually *moving* the corner -- a measurement
        # that is supposed to be strongly PVT-sensitive but comes back flat
        # means .temp / .lib never took effect.
        for kind, limit in (
            ("max_spread_pct", spec.get("max_spread_pct")),
            ("min_spread_pct", spec.get("min_spread_pct")),
        ):
            if limit is None:
                continue
            observed = (summary.get(name) or {}).get("spread_pct")
            violated = (
                observed is None
                or (kind == "max_spread_pct" and observed > limit)
                or (kind == "min_spread_pct" and observed < limit)
            )
            if violated:
                failures.append(
                    {
                        "measurement": name,
                        "kind": kind,
                        "limit": limit,
                        "value": observed,
                        "at": "grid",
                    }
                )
    return failures


def environment(pdk: Pdk, ngspice: str, repo_root: Path) -> dict:
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - unusual environments
        user = "unknown"
    return {
        "harness_version": HARNESS_VERSION,
        "ngspice": ngspice,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "host": socket.gethostname(),
        "user": user,
        "pdk": pdk.provenance(),
        "git": git_provenance(repo_root),
    }


def build_record(
    tb: Testbench,
    pdk: Pdk,
    points: list[PvtPoint],
    results: list[PointResult],
    ngspice: str,
    repo_root: Path,
    run_id: str,
    started_utc: str,
    wall_seconds: float,
) -> dict:
    measure_names = list(tb.measure)
    summary = summarize(results, measure_names)
    failures = evaluate_checks(tb.checks, results, summary)
    n_ok = sum(1 for r in results if r.status == "ok")

    if n_ok != len(results):
        status = "error"
    elif failures:
        status = "fail"
    else:
        status = "pass"

    corners = []
    seen = set()
    for point in points:
        if point.corner.name not in seen:
            seen.add(point.corner.name)
            corners.append(
                {
                    "name": point.corner.name,
                    "sections": list(point.corner.sections),
                    "description": point.corner.description,
                }
            )

    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "status": status,
        "started_utc": started_utc,
        "wall_seconds": round(wall_seconds, 2),
        "testbench": tb.provenance(),
        "environment": environment(pdk, ngspice, repo_root),
        "grid": {
            "corners": corners,
            "temperatures_c": sorted({p.temp_c for p in points}),
            "supplies_v": sorted({p.vdd for p in points}),
            "points": len(points),
            "points_ok": n_ok,
        },
        "measure": dict(tb.measure),
        "checks": {
            "spec": tb.checks,
            "passed": not failures,
            "failures": failures,
        },
        "summary": summary,
        "points": [r.as_dict() for r in results],
    }


def _next_free(path: Path) -> Path:
    """Append-only: never clobber an existing evidence file."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}.{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def write_results(record: dict, results_dir: Path, tb_name: str, run_id: str) -> dict[str, Path]:
    out_dir = results_dir / tb_name
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = _next_free(out_dir / f"{run_id}.json")
    json_path.write_text(json.dumps(record, indent=2, sort_keys=False) + "\n")

    csv_path = _next_free(out_dir / f"{run_id}.csv")
    measure_names = list(record["measure"])
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_id", "corner", "temp_c", "vdd", "status", *measure_names])
        for point in record["points"]:
            writer.writerow(
                [
                    record["run_id"],
                    point["corner"],
                    point["temp_c"],
                    point["vdd"],
                    point["status"],
                    *[point["measurements"].get(name, "") for name in measure_names],
                ]
            )
    return {"json": json_path, "csv": csv_path}
