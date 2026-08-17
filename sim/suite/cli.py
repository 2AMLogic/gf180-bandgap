"""``python3 sim/run_suite.py`` -- run every bench, judge every spec line.

One command runs the whole spec-line suite over the full PVT matrix and
prints a per-spec-line pass/fail summary. Each bench is executed through the
ordinary corner runner, so each mints its own append-only record; the suite
adds no new evidence format, only a roll-up that cites those records.

Re-running is always safe: every bench mints a fresh ``<record-id>`` and the
runner refuses to overwrite an existing record, so a second run adds
evidence and never edits it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import SUITE_VERSION
from . import combined as combined_verdict
from .analysis import (
    LineOutcome,
    compare_box_to_endpoints,
    cross_check_temperature_axes,
    evaluate_line,
    read_corner_logs,
)
from .spec import COMBINED_ACCURACY, NOT_CLAIMED_HERE, SUITE, SpecLine, by_slug, slugs

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
RUN_CORNERS = SIM_DIR / "run_corners.py"
SUMMARY_DIR = SIM_DIR / "suite" / "summaries"

# Every known caller of this module inserts SIM_DIR onto sys.path before
# importing suite.cli (see suite.combined's identical note, issue #154), so
# this module-level import of a sibling sim/harness/ package is safe here.
sys.path.insert(0, str(SIM_DIR))
from harness.paths import _repo_relative  # noqa: E402  (needs sys.path)
from harness.fmt import _fmt as _harness_fmt  # noqa: E402  (needs sys.path)

EXIT_OK = 0
EXIT_SPEC_FAIL = 1
EXIT_RUN_ERROR = 2

#: Lines the corner runner prints that the suite needs to find its evidence.
_RECORD_RE = re.compile(r"^record\s*:\s*(?P<path>.+)$")
_LOGS_RE = re.compile(r"^raw logs\s*:\s*(?P<path>.+)$")
_WORKDIR_RE = re.compile(r"^work dir\s*:\s*(?P<path>.+)$")
_DUT_RE = re.compile(r"^dut\s*:\s*(?P<path>\S+)\s*\((?P<provenance>[^)]+)\)$")


@dataclass
class BenchRun:
    """One bench's execution and the evidence it produced."""

    slug: str
    lines: list[SpecLine]
    status: str = "PENDING"        # ok | check-failed | error | missing
    returncode: int | None = None
    record: str = ""
    logs_dir: Path | None = None
    dut: str = ""
    dut_provenance: str = ""
    samples: dict = field(default_factory=dict)
    outcomes: list[LineOutcome] = field(default_factory=list)
    message: str = ""

    @property
    def available(self) -> bool:
        return self.status != "missing"


def _bench_manifest(slug: str) -> Path:
    return SIM_DIR / slug / "testbench" / "tb.json"


def _runner_status(returncode: int) -> str:
    return {0: "ok", 1: "check-failed", 2: "error", 3: "error"}.get(returncode, "error")


def run_bench(
    slug: str,
    lines: list[SpecLine],
    extra: list[str],
    quiet: bool = False,
) -> BenchRun:
    """Run one bench through ``sim/run_corners.py`` and read back its evidence."""
    bench = BenchRun(slug=slug, lines=lines)
    if not _bench_manifest(slug).is_file():
        bench.status = "missing"
        bench.message = f"sim/{slug}/testbench/tb.json does not exist yet"
        return bench

    command = [sys.executable, str(RUN_CORNERS), slug, *extra]
    if not quiet:
        print(f"\n$ {' '.join(command)}\n", flush=True)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = completed.stdout + completed.stderr
    if not quiet:
        print(output, end="", flush=True)

    bench.returncode = completed.returncode
    bench.status = _runner_status(completed.returncode)

    logs_dir: Path | None = None
    for raw in output.splitlines():
        line = raw.strip()
        record = _RECORD_RE.match(line)
        if record:
            bench.record = _repo_relative(record.group("path").strip())
        logs = _LOGS_RE.match(line)
        if logs:
            logs_dir = Path(logs.group("path").strip())
        workdir = _WORKDIR_RE.match(line)
        if workdir and logs_dir is None:
            # --no-write: the runner keeps the raw logs next to the decks.
            logs_dir = Path(workdir.group("path").strip())
        dut = _DUT_RE.match(line)
        if dut:
            bench.dut = dut.group("path")
            bench.dut_provenance = dut.group("provenance")

    bench.logs_dir = logs_dir
    if logs_dir is not None:
        bench.samples = read_corner_logs(logs_dir)
    if not bench.samples and bench.status == "ok":
        bench.status = "error"
        bench.message = f"no per-corner logs found under {logs_dir}"

    bench.outcomes = [evaluate_line(line, bench.samples) for line in lines]
    return bench


# --- rendering --------------------------------------------------------------


def _fmt(value) -> str:
    """Like ``harness.fmt._fmt``, but ``.4e`` -- suite summaries are more
    compact than per-record Markdown."""
    return _harness_fmt(value, precision="4e")


def _verdict_rows(benches: list[BenchRun]) -> list[str]:
    rows = [
        "| Spec row | Ratified target | Bench | Worst measured | At corner | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for bench in benches:
        for outcome in bench.outcomes:
            line = outcome.line
            if bench.status == "missing":
                rows.append(
                    f"| {line.row} | {line.target} | `{line.slug}` (owner {line.owner}) "
                    f"| — | — | PENDING — bench not in the tree yet |"
                )
                continue
            if not line.gated:
                verdict = {
                    "ok": "PASS (bench's own verdict)",
                    "check-failed": "FAIL (bench's own verdict)",
                    "error": "ERROR (bench did not complete)",
                }.get(bench.status, bench.status.upper())
                rows.append(
                    f"| {line.row} | {line.target} | `{line.slug}` (owner {line.owner}) "
                    f"| — | — | {verdict} |"
                )
                continue
            worst = outcome.worst
            measured = _fmt(worst.worst_value) + (worst.limit.units if worst else "")
            rows.append(
                f"| {line.row} | {line.target} | `{line.slug}` "
                f"| {measured} (limit {worst.limit.describe()}) "
                f"| `{worst.worst_corner or '—'}` | {outcome.status} |"
            )
    return rows


def _bench_evidence_rows(benches: list[BenchRun]) -> list[str]:
    rows = [
        "| Bench | Corners run | Record | DUT | Runner status |",
        "|---|---|---|---|---|",
    ]
    for bench in benches:
        if bench.status == "missing":
            rows.append(
                f"| `{bench.slug}` | — | — | — | not present ({bench.message}) |"
            )
            continue
        record = f"`{bench.record}`" if bench.record else "not recorded (--no-write)"
        dut = f"`{bench.dut}` ({bench.dut_provenance})" if bench.dut else "—"
        rows.append(
            f"| `{bench.slug}` | {len(bench.samples)} | {record} | {dut} "
            f"| {bench.status} (exit {bench.returncode}) |"
        )
    return rows


def _tc_section(benches: list[BenchRun]) -> list[str]:
    bench = next((b for b in benches if b.slug == "output-voltage-tc" and b.samples), None)
    if bench is None:
        return []
    comparison = compare_box_to_endpoints(bench.samples)
    cross = cross_check_temperature_axes(bench.samples)
    lines = [
        "",
        "### Temperature coefficient: box method vs endpoint-only",
        "",
        "The recorded TC is the box over a 1 degC-step sweep. The same run also",
        "measures Vref at exactly -40/27/125 degC, so the summary can state what an",
        "endpoint-only evaluation *would* have claimed -- the measurement mistake",
        "this bench exists to avoid.",
        "",
        f"- Worst box TC: {_fmt(comparison.worst_box_ppm)} ppm/degC at "
        f"`{comparison.worst_box_corner}`",
        f"- Endpoint-only TC at that same corner: "
        f"{_fmt(comparison.worst_endpoint_ppm)} ppm/degC",
        f"- Largest understatement by endpoint-only evaluation: "
        f"{_fmt(comparison.understated_by_ppm)} ppm/degC"
        + (f" at `{comparison.understated_at}`" if comparison.understated_at else ""),
        f"- Corners whose Vref extremum lies strictly inside the sweep (a curvature "
        f"peak an endpoint-only evaluation steps over): "
        f"{len(comparison.interior_extremum_corners)}"
        + (
            " — " + ", ".join(f"`{c}`" for c in comparison.interior_extremum_corners[:6])
            + ("..." if len(comparison.interior_extremum_corners) > 6 else "")
            if comparison.interior_extremum_corners
            else ""
        ),
        "",
        "Harness-integrity cross-check -- the operating point at the harness's own",
        "`.temp` axis vs the same temperature inside the testbench's `dc temp` sweep",
        "(two independent mechanisms, same physical quantity):",
        "",
        f"- {cross.n_compared} corner(s) compared, worst disagreement "
        f"{_fmt(cross.worst_delta_v)} V"
        + (f" at `{cross.worst_at}`" if cross.worst_at else "")
        + f" — {'consistent' if cross.consistent else 'INCONSISTENT, investigate'}",
    ]
    return lines


def combined_accuracy(benches: list[BenchRun]) -> combined_verdict.CombinedVerdict:
    """Judge the two-legged accuracy row: this run's corners + the MC record.

    The corner leg is taken from *this* run when the suite just ran that bench
    (so the summary judges the evidence it minted, not an older record); the
    mismatch leg always comes from ``sim/mc-untrimmed``'s newest committed
    record, because that bench has its own runner and is not part of the
    corner-runner suite.
    """
    bench = next(
        (b for b in benches if b.slug == combined_verdict.CORNER_SLUG and b.samples),
        None,
    )
    if bench is None:
        return combined_verdict.load()
    reference = combined_verdict.EvidenceRef(
        slug=bench.slug,
        record_id=Path(bench.record).stem if bench.record else "",
        record=bench.record,
        logs=_repo_relative(bench.logs_dir) if bench.logs_dir else "",
        live=True,
    )
    return combined_verdict.load(
        corner_samples=bench.samples, corner_evidence=reference
    )


def _combined_section(combined: combined_verdict.CombinedVerdict | None) -> list[str]:
    """The two-legged accuracy row, summarised; full detail in its own report."""
    if combined is None:
        return []
    row = COMBINED_ACCURACY
    lines = [
        "",
        f"## {row.row}",
        "",
        f"Ratified target: {row.target}. No single bench's verdict is this row's "
        "verdict — it is ratified on two legs, combined here:",
        "",
    ]
    lines += [f"- `{slug}`: {supplies}" for slug, supplies in row.legs]
    lines += [
        "",
        f"**Combined verdict: {combined.status}**"
        + (
            f" — {combined.n_fail} of {len(combined.verdicts)} corners fail."
            if combined.verdicts
            else ""
        ),
        "",
        "| T (degC) | corners | failing | worst corner | combined 3-sigma interval (V) "
        "| margin (mV) | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for rollup in combined.rollups:
        worst = rollup.worst
        if worst is None:
            lines.append(f"| {rollup.temp_c:g} | 0 | — | — | — | — | NO DATA |")
            continue
        lines.append(
            f"| {rollup.temp_c:g} | {len(rollup.verdicts)} | {rollup.n_fail} "
            f"| `{worst.corner_id}` | [{worst.low_v:.5f}, {worst.high_v:.5f}] "
            f"| {worst.margin_v * 1e3:.3f} | {rollup.status} |"
        )
    if combined.problems:
        lines += [""] + [f"- {problem}" for problem in combined.problems]
    lines += [
        "",
        f"Method: {row.note}",
        "",
        "Full per-corner detail, the anchor cross-check and the `par_r` "
        "sensitivity band are in the standalone report: "
        "`python3 sim/run_combined_accuracy.py` "
        "(written to `sim/suite/combined/`).",
    ]
    return lines


def _reference_section(benches: list[BenchRun]) -> list[str]:
    lines: list[str] = []
    for bench in benches:
        references = {
            name: values
            for outcome in bench.outcomes
            for name, values in outcome.reference.items()
        }
        if not references:
            continue
        lines += [
            "",
            f"### `{bench.slug}` reference data (recorded, not claimed)",
            "",
            "| measurement | min over corners | max over corners |",
            "|---|---|---|",
        ]
        for name, (low, high) in references.items():
            lines.append(f"| `{name}` | {_fmt(low)} | {_fmt(high)} |")
    return lines


def render_summary(
    benches: list[BenchRun],
    started: _dt.datetime,
    git: dict,
    mode: str,
    wrote_evidence: bool,
    combined: combined_verdict.CombinedVerdict | None = None,
) -> str:
    gated = [o for b in benches for o in b.outcomes if o.line.gated and b.available]
    passing = [o for o in gated if o.status == "PASS"]
    failing = [o for o in gated if o.status == "FAIL"]
    pending = [o for b in benches for o in b.outcomes if not o.line.gated or not b.available]

    # The untrimmed-accuracy row is ratified on TWO legs, so no per-bench line
    # is that row's verdict: a summary that reads "simulation-complete" while
    # the combined verdict fails would be claiming the row on one leg.
    combined_short = ""
    if combined is not None and combined.status != "PASS":
        combined_short = (
            f" The two-legged untrimmed-accuracy row (mismatch MC + process "
            f"corners) reads **{combined.status}**"
            + (
                f" — {combined.n_fail}/{len(combined.verdicts)} corners."
                if combined.verdicts
                else "."
            )
        )

    if failing or combined_short:
        counted = (
            f"{len(failing)} of {len(gated)} claimed spec lines FAIL against the "
            "ratified table."
            if failing
            else f"every per-bench spec line passes ({len(passing)}/{len(gated)})."
        )
        verdict = f"**NOT simulation-complete**: {counted}{combined_short}"
    elif pending:
        verdict = (
            f"**Not yet simulation-complete**: every claimed spec line passes "
            f"({len(passing)}/{len(gated)}), but {len(pending)} line(s) are still "
            "pending a bench."
        )
    else:
        verdict = (
            f"**Simulation-complete**: all {len(passing)} spec lines in the suite "
            "index pass against the ratified table, and the two-legged "
            "untrimmed-accuracy row passes at every corner."
        )

    lines = [
        f"# Suite summary {started.strftime('%Y%m%d-%H%M%S')}-{git.get('short', 'unknown')}",
        "",
        f"- **Suite**: `sim/run_suite.py` {SUITE_VERSION} ({mode} mode)",
        f"- **Timestamp**: {started.isoformat(timespec='seconds')}",
        f"- **git**: `{git.get('commit', 'unknown')}` on `{git.get('branch', 'unknown')}`"
        + (" (dirty)" if git.get("dirty") else " (clean)"),
        f"- **Evidence**: {'records minted per bench (see table)' if wrote_evidence else 'none — --no-write / smoke mode'}",
        "",
        verdict,
        "",
        "## Per-spec-line verdict",
        "",
    ]
    lines += _verdict_rows(benches)
    lines += ["", "## Benches and their evidence", ""]
    lines += _bench_evidence_rows(benches)
    lines += _combined_section(combined)
    lines += _tc_section(benches)
    lines += _reference_section(benches)

    lines += ["", "## Measurement conventions", ""]
    for line in SUITE:
        if line.note:
            lines.append(f"- **{line.row}** (`{line.slug}`): {line.note}")

    lines += [
        "",
        "## Ratified rows this suite does not claim",
        "",
        "| Row | Why not here |",
        "|---|---|",
    ]
    for row in NOT_CLAIMED_HERE:
        lines.append(f"| {row.row} | {row.reason} |")

    lines += [
        "",
        "---",
        "",
        "Generated by `sim/run_suite.py`. This summary is a roll-up of the records",
        "it cites, not a substitute for them: the per-corner evidence lives under",
        "`sim/<slug>/records/`, `sim/<slug>/corners/` and `sim/<slug>/netlist-snapshots/`",
        "and is append-only (`sim/README.md`).",
        "",
    ]
    return "\n".join(lines)


# --- CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_suite.py",
        description="Run every spec-line testbench and summarise pass/fail per spec line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 sim/run_suite.py                 # full PVT matrix, mint records\n"
            "  python3 sim/run_suite.py --smoke         # nominal-only, records nothing\n"
            "  python3 sim/run_suite.py --only iq       # one bench\n"
            "  python3 sim/run_suite.py --dut layout/netlist/bandgap_top_extracted.spice\n"
            "  python3 sim/run_suite.py --timeout 1200  # ride out shared-host contention\n"
            "  python3 sim/run_suite.py --list          # the spec-line index\n"
        ),
    )
    parser.add_argument("--list", action="store_true", help="print the suite index and exit")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="SLUG",
        help="run only these experiment slugs (default: every bench in the index)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="nominal-only debugging run (tt / 27 degC / nominal supply); implies --no-write",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="run without minting records or a summary file",
    )
    parser.add_argument(
        "--dut",
        metavar="PATH",
        help="DUT netlist for every bench, overriding each manifest (e.g. a frozen "
        "copy, or a post-layout extracted netlist)",
    )
    parser.add_argument("-j", "--jobs", type=int, default=0, help="parallel ngspice runs")
    parser.add_argument(
        "--corner-set",
        help="corner set for every bench (tt / mos / full); default: each manifest's own",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="per-point ngspice timeout in seconds for every bench, overriding "
        "run_corners.py's default (e.g. to ride out shared-host CPU contention "
        "on a compute-heavy bench like output-voltage-tc's internal sweep); "
        "default: each bench's own",
    )
    parser.add_argument("--quiet", action="store_true", help="hide each bench's own output")
    return parser


def cmd_list() -> int:
    print("Spec-line suite index (README.md ratified table -> testbench):\n")
    for line in SUITE:
        target = f"{line.row}: {line.target}"
        print(f"  {target}")
        print(f"    bench   : sim/{line.slug}/  (owner {line.owner})")
        if line.limits:
            print("    gates   : " + "; ".join(limit.describe() for limit in line.limits))
        else:
            print("    gates   : (verdict taken from the bench's own overall status)")
        if line.note:
            print(f"    note    : {line.note}")
        print()
    print("Ratified rows deliberately not claimed by this suite:")
    for row in NOT_CLAIMED_HERE:
        print(f"  {row.row}: {row.reason}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list:
        return cmd_list()

    sys.path.insert(0, str(SIM_DIR))
    from harness import report as harness_report  # noqa: E402  (needs sys.path)

    no_write = args.no_write or args.smoke
    extra: list[str] = []
    if args.smoke:
        extra += ["--corners", "tt", "--temps", "27", "--supply-tol", "0"]
    if args.corner_set:
        extra += ["--corner-set", args.corner_set]
    if args.jobs:
        extra += ["-j", str(args.jobs)]
    if args.timeout:
        extra += ["--timeout", str(args.timeout)]
    if args.dut:
        extra += ["--dut", args.dut]
    if no_write:
        extra.append("--no-write")

    grouped = by_slug()
    targets = args.only or slugs()
    unknown = [slug for slug in targets if slug not in grouped]
    if unknown:
        print(
            f"error: not in the suite index: {', '.join(unknown)}; "
            f"known: {', '.join(slugs())}",
            file=sys.stderr,
        )
        return EXIT_RUN_ERROR

    started = _dt.datetime.now(_dt.timezone.utc)
    git = harness_report.git_provenance(REPO_ROOT)

    benches = [
        run_bench(slug, grouped[slug], extra, quiet=args.quiet)
        for slug in targets
    ]

    combined = (
        combined_accuracy(benches)
        if combined_verdict.CORNER_SLUG in targets
        else None
    )

    summary = render_summary(
        benches,
        started=started,
        git=git,
        mode="smoke" if args.smoke else "full PVT",
        wrote_evidence=not no_write,
        combined=combined,
    )
    print()
    print(summary)

    if not no_write:
        SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{started.strftime('%Y%m%d-%H%M%S')}-{git.get('short', 'unknown')}.md"
        path = SUMMARY_DIR / name
        if path.exists():  # pragma: no cover - same second, same commit
            path = SUMMARY_DIR / f"{path.stem}-1.md"
        path.write_text(summary)
        print(f"summary written to {path.relative_to(REPO_ROOT)}")

    if any(bench.status == "error" for bench in benches):
        return EXIT_RUN_ERROR
    if combined is not None and combined.status in {"NO DATA", "INVALID"}:
        return EXIT_RUN_ERROR
    if combined is not None and combined.status == "FAIL":
        return EXIT_SPEC_FAIL
    if any(
        outcome.status == "FAIL"
        for bench in benches
        for outcome in bench.outcomes
        if outcome.line.gated
    ) or any(bench.status == "check-failed" for bench in benches):
        return EXIT_SPEC_FAIL
    return EXIT_OK
