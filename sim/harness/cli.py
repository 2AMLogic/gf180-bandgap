"""Command line front end: ``python3 sim/run_corners.py <testbench> [...]``."""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import time
from pathlib import Path

from . import HARNESS_VERSION, corners as corners_mod, report, runner, testbench as tb_mod
from .pdk import PdkNotFound, find_pdk
from .runner import NgspiceMissing

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
TB_DIR = SIM_DIR / "tb"
RESULTS_DIR = SIM_DIR / "results"
WORK_DIR = SIM_DIR / ".work"

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_SIM_ERROR = 2
EXIT_ENVIRONMENT = 3


def _resolve_tb_path(argument: str) -> Path:
    candidates = [Path(argument), TB_DIR / argument, SIM_DIR / argument]
    for candidate in candidates:
        if (candidate / tb_mod.MANIFEST_NAME).is_file() or (
            candidate.is_file() and candidate.name == tb_mod.MANIFEST_NAME
        ):
            return candidate
    raise FileNotFoundError(
        f"no testbench {argument!r}; tried: "
        + ", ".join(str(c) for c in candidates)
        + ".\nAvailable: "
        + ", ".join(p.name for p in tb_mod.discover(TB_DIR))
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_corners.py",
        description="Run a testbench across the gf180mcu PVT corner grid.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 sim/run_corners.py smoke_bias\n"
            "  python3 sim/run_corners.py smoke_bias --corners tt --temps 27\n"
            "  python3 sim/run_corners.py smoke_bias --corner-set full -j 8\n"
            "  python3 sim/run_corners.py --list\n"
            "  python3 sim/run_corners.py --check-env\n"
        ),
    )
    parser.add_argument("testbench", nargs="?", help="testbench dir or name under sim/tb/")
    parser.add_argument("--list", action="store_true", help="list testbenches and corners")
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="report ngspice / PDK availability and exit",
    )
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="print shell exports for the resolved PDK (used by sim/env.sh)",
    )
    parser.add_argument(
        "--corners",
        nargs="+",
        metavar="NAME",
        help="explicit corner or corner-set names (overrides the manifest)",
    )
    parser.add_argument(
        "--corner-set",
        choices=sorted(corners_mod.CORNER_SETS),
        help="shorthand for --corners <set>",
    )
    parser.add_argument(
        "--temps",
        nargs="+",
        type=float,
        metavar="C",
        help="temperatures in degrees C (overrides the manifest)",
    )
    parser.add_argument(
        "--supply",
        type=float,
        metavar="V",
        help="nominal supply in volts (overrides the manifest)",
    )
    parser.add_argument(
        "--supply-tol",
        type=float,
        metavar="FRAC",
        help="supply tolerance as a fraction, e.g. 0.10 (0 disables the V axis)",
    )
    parser.add_argument("-j", "--jobs", type=int, default=0, help="parallel ngspice runs")
    parser.add_argument(
        "--timeout",
        type=int,
        default=runner.DEFAULT_TIMEOUT_S,
        help="per-point ngspice timeout in seconds",
    )
    parser.add_argument(
        "--results-dir",
        default=str(RESULTS_DIR),
        help="where to write the append-only result files",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="run but do not record evidence (debugging only)",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    parser.add_argument("--version", action="version", version=f"gf180-bandgap harness {HARNESS_VERSION}")
    return parser


def cmd_list() -> int:
    print("Testbenches (sim/tb):")
    for directory in tb_mod.discover(TB_DIR):
        try:
            tb = tb_mod.load(directory)
            print(f"  {directory.name:<20} {tb.description or tb.name}")
        except Exception as exc:  # noqa: BLE001 - surface bad manifests, keep listing
            print(f"  {directory.name:<20} !! {exc}")
    print("\nCorner sets:")
    for name, members in sorted(corners_mod.CORNER_SETS.items()):
        print(f"  {name:<20} {', '.join(members)}")
    print("\nCorners:")
    for name, corner in corners_mod.CORNERS.items():
        print(f"  {name:<20} {corner.description}")
        print(f"  {'':<20} sections: {' '.join(corner.sections)}")
    return EXIT_OK


def cmd_check_env() -> int:
    status = EXIT_OK
    try:
        version = runner.ngspice_version()
        print(f"ngspice : OK   {version}")
    except NgspiceMissing as exc:
        print(f"ngspice : MISSING\n{exc}")
        status = EXIT_ENVIRONMENT
    try:
        pdk = find_pdk()
        print(f"PDK     : OK   {pdk.path} (open_pdks {pdk.version}, via {pdk.source})")
        print(f"  models: {pdk.model_lib}")
        print(f"  xschem: {pdk.xschem_dir}")
    except PdkNotFound as exc:
        print(f"PDK     : MISSING\n{exc}")
        status = EXIT_ENVIRONMENT
    return status


def cmd_print_env() -> int:
    """Emit shell exports so xschem/ngspice see the same PDK the harness picked."""
    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(f"# gf180mcu PDK not found\n# {exc.args[0].splitlines()[0]}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    library_path = ":".join(
        str(p) for p in (REPO_ROOT / "design", REPO_ROOT / "sim" / "tb")
    )
    print(f'export PDK_ROOT="{pdk.path.parent}"')
    print(f'export PDK="{pdk.variant}"')
    print(f'export GF180_PDK_PATH="{pdk.path}"')
    print(f'export GF180_MODELS="{pdk.ngspice_dir}"')
    print(f'export XSCHEM_USER_LIBRARY_PATH="{library_path}"')
    return EXIT_OK


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value != 0 and (abs(value) < 1e-3 or abs(value) >= 1e5):
            return f"{value:.6e}"
        return f"{value:.6g}"
    return str(value)


def run(args: argparse.Namespace) -> int:
    tb_path = _resolve_tb_path(args.testbench)
    tb = tb_mod.load(tb_path)

    try:
        pdk = find_pdk()
        ngspice = runner.ngspice_version()
    except (PdkNotFound, NgspiceMissing) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    corner_names = args.corners or ([args.corner_set] if args.corner_set else list(tb.corners))
    corner_list = corners_mod.resolve_corners(corner_names)
    temperatures = args.temps if args.temps is not None else list(tb.temperatures_c)
    nominal = args.supply if args.supply is not None else tb.nominal_supply_v
    tolerance = args.supply_tol if args.supply_tol is not None else tb.supply_tolerance
    supplies = corners_mod.supply_points(nominal, tolerance)
    points = corners_mod.build_grid(corner_list, temperatures, supplies)

    jobs = args.jobs or min(8, (os.cpu_count() or 2))
    run_id = report.make_run_id(REPO_ROOT)
    started = _dt.datetime.now(_dt.timezone.utc)
    workdir = WORK_DIR / tb.name / run_id

    if not args.quiet:
        print(f"testbench : {tb.name}  ({tb.description})" if tb.description else f"testbench : {tb.name}")
        print(f"pdk       : {pdk.variant} @ {pdk.version}  ({pdk.path})")
        print(f"ngspice   : {ngspice}")
        print(f"corners   : {', '.join(c.name for c in corner_list)}")
        print(f"temps (C) : {', '.join(_fmt(t) for t in temperatures)}")
        print(f"supply (V): {', '.join(_fmt(v) for v in supplies)} "
              f"(nominal {_fmt(nominal)} +/-{tolerance * 100:g}%)")
        print(f"points    : {len(points)}  (jobs={jobs})")
        print(f"run_id    : {run_id}")
        print()

    completed = 0

    def progress(result):
        nonlocal completed
        completed += 1
        if args.quiet:
            return
        flag = {"ok": "ok  ", "failed": "FAIL", "error": "ERR "}[result.status]
        detail = ""
        if result.status == "ok":
            detail = "  ".join(
                f"{name}={_fmt(result.measurements[name])}" for name in tb.measure
                if name in result.measurements
            )
        else:
            detail = result.message
        print(f"[{completed:>3}/{len(points)}] {flag} {result.point.label:<26} {detail}")

    wall_start = time.monotonic()
    try:
        results = runner.run_grid(
            tb, pdk, points, workdir, jobs=jobs, timeout_s=args.timeout, on_result=progress
        )
    except NgspiceMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
    wall = time.monotonic() - wall_start

    record = report.build_record(
        tb=tb,
        pdk=pdk,
        points=points,
        results=results,
        ngspice=ngspice,
        repo_root=REPO_ROOT,
        run_id=run_id,
        started_utc=started.isoformat(timespec="seconds"),
        wall_seconds=wall,
    )

    print()
    print(f"summary ({record['grid']['points_ok']}/{len(points)} points ok, {wall:.1f}s):")
    header = f"  {'measurement':<16}{'min':>16}{'max':>16}{'mean':>16}{'spread %':>12}"
    print(header)
    for name, stats in record["summary"].items():
        if not stats.get("n"):
            print(f"  {name:<16}{'no data':>16}")
            continue
        print(
            f"  {name:<16}{_fmt(stats['min']):>16}{_fmt(stats['max']):>16}"
            f"{_fmt(stats['mean']):>16}{_fmt(stats['spread_pct']):>12}"
        )

    for failure in record["checks"]["failures"]:
        print(
            f"  CHECK FAIL {failure['measurement']} {failure['kind']}={_fmt(failure['limit'])} "
            f"got {_fmt(failure['value'])} at {failure['at']}"
        )

    if not args.no_write:
        paths = report.write_results(record, Path(args.results_dir), tb.name, run_id)
        print()
        print(f"evidence  : {paths['json']}")
        print(f"            {paths['csv']}")
    print(f"work dir  : {workdir}")
    print(f"status    : {record['status'].upper()}")

    if record["status"] == "error":
        return EXIT_SIM_ERROR
    if record["status"] == "fail":
        return EXIT_CHECK_FAILED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return cmd_list()
    if args.check_env:
        return cmd_check_env()
    if args.print_env:
        return cmd_print_env()
    if not args.testbench:
        parser.print_help()
        return EXIT_ENVIRONMENT
    try:
        return run(args)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ENVIRONMENT
