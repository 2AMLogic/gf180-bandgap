#!/usr/bin/env python3
"""Schematic-vs-extracted delta summary, per spec line (#17, Scope item 4).

    python3 sim/postlayout_delta.py \
        --pair output-voltage-tc=<schematic-rid>:<extracted-rid> \
        --pair psrr-dc=<schematic-rid>:<extracted-rid> \
        ... \
        -o sim/postlayout-delta.md

A post-layout re-run that reports only an aggregate pass/fail hides *where*
layout cost margin. This script pairs an existing schematic-provenance record
with an existing extracted-provenance record from the same experiment slug,
aligns them corner for corner, and reports -- per spec line and per corner --
the schematic result, the extracted result, and the delta.

It reads only committed evidence (``sim/<slug>/records/<record-id>.md``); it
runs no simulation and mints no record, so it can be re-run at any time and
always reproduces the same document from the same two records. Limits come
from ``sim/suite/spec.py`` and each side's verdict is what the suite's own
evaluator (``sim/suite/analysis.py:evaluate_line``, the one
``sim/run_suite.py`` rolls up with) returns for the corners present in that
side's record — the same single source a suite summary judges by, so a delta
summary can never disagree with a suite summary about what the limit is, and
a measurement missing at any corner of a side's record reads NO DATA there
instead of passing.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import report as harness_report  # noqa: E402
from harness.paths import _repo_relative  # noqa: E402
from suite import spec as spec_mod  # noqa: E402
from suite.analysis import LimitOutcome, evaluate_line  # noqa: E402
from suite.combined import provenance_of_path  # noqa: E402

RECORD_ROW = re.compile(r"^\s*\|\s*`([^`]+)`\s*\|(.+)\|\s*$")


@dataclass
class Record:
    slug: str
    record_id: str
    provenance: str
    path: Path
    #: corner-id -> measurement -> value
    corners: dict[str, dict[str, float]]
    #: corner-id -> verdict text
    verdicts: dict[str, str]

    @property
    def link(self) -> str:
        return f"`sim/{self.slug}/records/{self.record_id}.md`"


def _float(token: str) -> float | None:
    token = token.strip().strip("`*")
    try:
        return float(token)
    except ValueError:
        return None


def load_record(slug: str, record_id: str) -> Record:
    """Parse a record's per-corner result table.

    The table's shape is fixed by ``sim/harness/report.py``: a header row of
    `corner-id | <measurement>... | pass/fail`, then one row per corner whose
    first cell is the backticked corner-id.
    """
    path = REPO_ROOT / "sim" / slug / "records" / f"{record_id}.md"
    text = path.read_text()

    # Read this field only through the shared reader -- a second, hand-rolled
    # scan here kept the class's trailing period and rejected every
    # fleet-ingested record (#454). The ``read_text()`` above already failed
    # loudly for an unreadable record, so the ``unknown`` fallback inside
    # ``provenance_of_path`` cannot mask a missing one.
    provenance = provenance_of_path(path)

    header: list[str] | None = None
    corners: dict[str, dict[str, float]] = {}
    verdicts: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if header is None and stripped.startswith("| corner-id |"):
            header = [cell.strip() for cell in stripped.strip("|").split("|")]
            continue
        if header is None:
            continue
        hit = RECORD_ROW.match(line)
        if not hit:
            continue
        corner = hit.group(1)
        cells = [cell.strip() for cell in hit.group(2).split("|")]
        if len(cells) != len(header) - 1:
            continue
        values: dict[str, float] = {}
        for name, cell in zip(header[1:-1], cells[:-1]):
            value = _float(cell)
            if value is not None:
                values[name.strip("`")] = value
        corners[corner] = values
        verdicts[corner] = cells[-1]
    if not corners:
        raise SystemExit(f"{path}: no per-corner result table found")
    return Record(slug, record_id, provenance, path, corners, verdicts)


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _delta(new: float, old: float) -> str:
    diff = new - old
    if old == 0:
        return f"{diff:+.6g}"
    return f"{diff:+.6g} ({diff / abs(old) * 100:+.2f}%)"


def _worst_cell(outcome: LimitOutcome) -> str:
    """One side's ``worst`` cell: the worst sample and its corner, or a dash.

    A dash marks a side whose record carries no sample of the measurement
    at any corner -- the row stays visible so the gap itself is reportable.
    """
    if outcome.worst_value is None:
        return "—"
    return f"{_fmt(outcome.worst_value)} (`{outcome.worst_corner}`)"


def spec_lines_for(slug: str) -> list[spec_mod.SpecLine]:
    return [line for line in spec_mod.SUITE if line.slug == slug and line.gated]


def render(pairs: dict[str, tuple[Record, Record]], extra: str) -> str:
    out: list[str] = []
    out.append("# Schematic-vs-extracted delta summary (#17)")
    out.append("")
    out.append(
        "Per ratified spec line: the schematic-level result, the "
        "parasitic-extracted post-layout result, and the delta between them — so "
        "a layout-induced regression is visible **per line**, not just in an "
        "aggregate pass/fail."
    )
    out.append("")
    out.append(
        "GENERATED by `sim/postlayout_delta.py` from committed evidence only "
        "(`sim/<slug>/records/`). It runs no simulation and mints no record; "
        "re-running it against the same two record-ids reproduces this file. "
        "Limits come from `sim/suite/spec.py`; each side's verdict is what the "
        "suite evaluator (`sim/suite/analysis.py:evaluate_line`, the one "
        "`sim/run_suite.py` rolls up with) returns for the corners present in "
        "that side's record, so a measurement missing at any corner reads NO "
        "DATA, never PASS."
    )
    out.append("")
    out.append(
        f"- **git**: `{harness_report._git('rev-parse', 'HEAD', cwd=REPO_ROOT)}` on "
        f"`{harness_report._git('rev-parse', '--abbrev-ref', 'HEAD', cwd=REPO_ROOT)}`"
    )
    out.append("")

    out.append("## Records paired")
    out.append("")
    out.append("| Bench | Schematic record | Extracted record | Corners aligned |")
    out.append("|---|---|---|---|")
    for slug, (schematic, extracted) in pairs.items():
        common = sorted(set(schematic.corners) & set(extracted.corners))
        out.append(
            f"| `{slug}` | {schematic.link} | {extracted.link} | "
            f"{len(common)} of {len(schematic.corners)} / {len(extracted.corners)} |"
        )
    out.append("")

    out.append("## Per-spec-line delta")
    out.append("")
    out.append(
        "*Worst* is the corner at which that limit is furthest into violation "
        "(or, when passing, closest to it) — evaluated independently on each "
        "side, so the two columns may name different corners. A side missing "
        "the measurement at every corner shows `—` for its worst and the "
        "delta; missing it at only some corners still names the worst of the "
        "measured ones, but that side's verdict reads NO DATA — a missing "
        "measurement cannot pass."
    )
    out.append("")
    out.append(
        "| Spec row | Ratified limit | Schematic worst | Extracted worst | Delta | "
        "Schematic | Extracted |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for slug, (schematic, extracted) in pairs.items():
        for line in spec_lines_for(slug):
            # One evaluation per side, by the same evaluator the suite
            # summary rolls up with: verdicts are judged over the corners
            # present in each record, so a measurement missing anywhere in
            # a side reads NO DATA there, never PASS (#535).
            sch = evaluate_line(line, schematic.corners)
            ext = evaluate_line(line, extracted.corners)
            for sch_o, ext_o in zip(sch.outcomes, ext.outcomes):
                delta = (
                    _delta(ext_o.worst_value, sch_o.worst_value)
                    if sch_o.worst_value is not None and ext_o.worst_value is not None
                    else "—"
                )
                out.append(
                    f"| {line.row} | `{sch_o.limit.describe()}` | "
                    f"{_worst_cell(sch_o)} | {_worst_cell(ext_o)} | {delta} | "
                    f"{sch.status} | "
                    f"{'**' + ext.status + '**' if ext.status != sch.status else ext.status} |"
                )
    out.append("")

    out.append("## Per-corner delta, gated measurements")
    out.append("")
    for slug, (schematic, extracted) in pairs.items():
        gated = []
        for line in spec_lines_for(slug):
            for limit in line.limits:
                if limit.measurement not in gated:
                    gated.append(limit.measurement)
        common = sorted(set(schematic.corners) & set(extracted.corners))
        out.append(f"### `{slug}`")
        out.append("")
        head = ["corner-id"]
        for name in gated:
            head += [f"{name} (sch)", f"{name} (ext)", f"{name} delta"]
        out.append("| " + " | ".join(head) + " |")
        out.append("|" + "---|" * len(head))
        for corner in common:
            cells = [f"`{corner}`"]
            for name in gated:
                sch = schematic.corners[corner].get(name)
                ext = extracted.corners[corner].get(name)
                if sch is None or ext is None:
                    cells += ["—", "—", "—"]
                else:
                    cells += [_fmt(sch), _fmt(ext), _delta(ext, sch)]
            out.append("| " + " | ".join(cells) + " |")
        out.append("")

    if extra:
        out.append(Path(extra).read_text().rstrip())
        out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pair",
        action="append",
        required=True,
        metavar="SLUG=SCHEMATIC_RID:EXTRACTED_RID",
        help="one experiment slug and the two record-ids to diff",
    )
    ap.add_argument(
        "--append",
        default="",
        help="path to a markdown fragment appended verbatim (the narrative "
        "analysis this mechanical diff cannot derive)",
    )
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    pairs: dict[str, tuple[Record, Record]] = {}
    for item in args.pair:
        slug, _, rids = item.partition("=")
        schematic_rid, _, extracted_rid = rids.partition(":")
        schematic = load_record(slug, schematic_rid)
        extracted = load_record(slug, extracted_rid)
        if schematic.provenance != "schematic":
            raise SystemExit(f"{schematic.path}: expected schematic provenance")
        if extracted.provenance != "extracted":
            raise SystemExit(f"{extracted.path}: expected extracted provenance")
        pairs[slug] = (schematic, extracted)

    output = args.output.resolve()
    output.write_text(render(pairs, args.append))
    print(f"wrote {_repo_relative(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
