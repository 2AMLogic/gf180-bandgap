#!/usr/bin/env python3
"""Evidence-only suite roll-up over pinned, already-minted records (#239).

`sim/run_suite.py` runs every bench through `run_bench` -> `run_corners.py`,
i.e. local ngspice jobs. Evidence that came from the batch fleet and was
ingested by `tc_ingest.py` / `fleet_ingest.py` / `mc_fleet_ingest.py` is
already on disk, so this script judges *that* with the suite's own parsers and
rules and starts no simulation:

* corner logs are read with `suite.analysis.read_corner_logs`;
* each spec line is judged by `suite.analysis.evaluate_line`;
* completeness and the exit code come from `suite.completeness.assess`;
* the two-legged accuracy row is `suite.combined.load` with explicit pins;
* the text is `suite.cli.render_summary`.

A bench with no `--record SLUG=ID` is reported as missing evidence (never
substituted with an older record), so the summary cannot claim completeness.

    python3 sim/tools/fleet_suite_summary.py \\
        --record output-voltage-tc=ID --record psrr-dc=ID ... \\
        --corner-record ID --mc-record ID [--no-write]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(REPO / "sim"))
sys.path.insert(0, str(REPO))

from suite import combined as combined_verdict  # noqa: E402
from suite.analysis import evaluate_line, read_corner_logs  # noqa: E402
from suite.cli import SUMMARY_DIR, BenchRun, expected_corner_ids, render_summary  # noqa: E402
from suite.completeness import assess  # noqa: E402
from suite.spec import by_slug, slugs  # noqa: E402


def bench_from_record(slug: str, lines, record_id: str | None, sim_dir: Path = SIM) -> BenchRun:
    """A :class:`BenchRun` read back from ``sim/<slug>/corners/<record_id>/``.

    No record, or a record without logs, is ``missing`` -- the same status the
    suite gives an absent bench -- so it blocks the completeness claim.
    """
    bench = BenchRun(slug=slug, lines=lines, expected_corners=expected_corner_ids(slug))
    bench.acceptance_corners = expected_corner_ids(slug)
    if not record_id:
        bench.status = "missing"
        bench.message = "no fleet record supplied for this bench"
    else:
        logs = sim_dir / slug / "corners" / record_id
        record = sim_dir / slug / "records" / f"{record_id}.md"
        if not record.is_file() or not logs.is_dir():
            bench.status = "missing"
            bench.message = f"no record/logs for {slug} {record_id}"
        else:
            bench.status = "ok"
            bench.record = str(record.relative_to(sim_dir.parent))
            bench.logs_dir = logs
            bench.samples = read_corner_logs(logs)
            bench.dut = "sim/dut/bandgap_top.spice"
            bench.dut_provenance = combined_verdict.record_provenance(slug, record_id, sim_dir)
            if not bench.samples:
                bench.status = "error"
                bench.message = f"no per-corner logs found under {logs}"
    bench.outcomes = [evaluate_line(line, bench.samples, bench.expected_corners) for line in lines]
    return bench


def parse_records(items) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        slug, sep, rid = item.partition("=")
        if not sep or not slug or not rid:
            raise SystemExit(f"--record expects SLUG=RECORD-ID, got {item!r}")
        if slug in out:
            raise SystemExit(f"--record given twice for {slug}")
        out[slug] = rid
    unknown = sorted(set(out) - set(slugs()))
    if unknown:
        raise SystemExit(f"not in the suite index: {', '.join(unknown)}; known: {', '.join(slugs())}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--record", action="append", metavar="SLUG=RECORD-ID",
                    help="pin one bench to an ingested record (repeatable)")
    ap.add_argument("--corner-record", required=True, help="output-voltage-tc record for the combined verdict")
    ap.add_argument("--mc-record", required=True, help="mc-untrimmed record for the combined verdict")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)

    records = parse_records(a.record)
    grouped = by_slug()
    benches = [bench_from_record(slug, grouped[slug], records.get(slug)) for slug in slugs()]
    combined = combined_verdict.load(corner_record=a.corner_record, mc_record=a.mc_record)
    done = assess(benches, combined, slugs())
    from harness import report as harness_report  # noqa: E402

    started = dt.datetime.now(dt.timezone.utc)
    git = harness_report.git_provenance(REPO)
    summary = render_summary(benches, started=started, git=git, mode="fleet evidence (pinned records)",
                             wrote_evidence=False, combined=combined, completeness=done)
    print(summary)
    if not a.no_write:
        SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        path = SUMMARY_DIR / f"{started.strftime('%Y%m%d-%H%M%S')}-{git.get('short', 'unknown')}.md"
        path.write_text(summary)
        print(f"summary written to {path.relative_to(REPO)}")
    return done.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
