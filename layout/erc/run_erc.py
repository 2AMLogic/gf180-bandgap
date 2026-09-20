#!/usr/bin/env python3
"""Reproducible, append-only ``klt erc`` invocation for ``layout/``.

Runs ``klt erc <gds> <spec>`` (both ``--format json`` and ``--format text``)
and writes the output under
``layout/erc/reports/<fixture>/<record-id>.<suffix>.{json,txt}``.

``<record-id>`` is ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, the same
convention ``layout/drc/run_drc.py``, ``layout/lvs/run_lvs.py`` and
``sim/harness/report.py`` already use, minted by ``layout/common/report_id``.
This script never overwrites an existing report -- CLAUDE.md: "``sim/``
results are append-only evidence", and this repo applies the same rule to
``layout/`` reports (see ``layout/README.md``).

Beyond filing the report, this script **asserts the item-11 verdict** rather
than leaving it to a reader (see ``layout/erc/README.md``). Two gates, both
on by default:

1. ``provenance.input.content_hash`` equals the sha256 of the GDS file on
   disk -- the report is evidence about the *committed* layout, not about
   some other stream that happened to be at that path.
2. Under ``--expect supply-clean`` (the default): every ``nets[]`` entry
   declared ``"kind": "supply"`` is named by **zero** ``erc.unconnected_net``
   findings and **zero** ``erc.supply_short`` findings.

   Under ``--expect findings``: at least one ERC finding was reported. This
   is what the negative control (``erc-supply-spec.negative-control.json``)
   and the known-gap reproduction (``erc-tie-spec.known-gap.json``) run with
   -- for them, a *clean* result is the regression.

   Under ``--expect any``: no verdict gate; file the report and report the
   numbers.

**Deliberately not gated on the report's own top-level ``status``.** T1 item
11 grades the supply-net finding rules above, explicitly *not* the overall
status (klayout-tools ``docs/design-evidence-tiers.md``, item 11: "Those are
the rules this item grades, not the report's overall ``status``"). On
gf180mcu that status is always ``"not_checked"`` (exit 4), because ``klt
erc --pdk`` ships an antenna-ratio limit table for sky130 only -- so no
antenna level is ever graded and the coverage contract refuses to call the
run a pass. That is an antenna-coverage fact, not a power-delivery one.
``klt erc``'s exit 4 is therefore accepted here exactly like exit 0 and 3.

Requires ``klt`` on ``PATH`` -- see ``layout/README.md`` for install
instructions (no PyPI release yet; install from the klayout-tools git repo).

Usage (from the repo root):

    # the item-11 signoff read (defaults: bandgap_top + the supply spec)
    python3 layout/erc/run_erc.py

    # the negative control -- a clean result here is the regression
    python3 layout/erc/run_erc.py \\
        --spec layout/erc/erc-supply-spec.negative-control.json \\
        --suffix erc-negative-control --expect findings

    # the klayout-tools#2169 reproduction -- NOT signoff evidence
    python3 layout/erc/run_erc.py \\
        --spec layout/erc/erc-tie-spec.known-gap.json \\
        --suffix erc-tie-known-gap --expect findings
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "common"))

import report_id  # noqa: E402

REPORTS_ROOT = Path(__file__).resolve().parent / "reports"
DEFAULT_GDS = Path("layout/bandgap_top/bandgap_top.gds")
DEFAULT_SPEC = Path("layout/erc/erc-supply-spec.json")

#: ``klt erc`` exit codes that mean "the run completed and the report is
#: real", per klayout-tools ``docs/cli/erc.md``'s exit-code contract:
#: 0 = graded and clean, 3 = findings, 4 = nothing antenna-graded
#: (``status: "not_checked"``). 1/2 are genuine failures.
OK_EXIT_CODES = (0, 3, 4)

#: The two finding rules T1 item 11 grades a declared supply on.
SUPPLY_RULES = ("erc.unconnected_net", "erc.supply_short")


def sha256_of(path: Path) -> str:
    """``sha256:<hex>`` over ``path``, matching klt's provenance format."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def declared_supplies(spec: dict) -> list[str]:
    """Every ``nets[]`` name declared ``"kind": "supply"``, in spec order."""
    return [
        net["name"]
        for net in spec.get("nets", [])
        if net.get("kind", "signal") == "supply"
    ]


def supply_findings(payload: dict, supplies: list[str]) -> list[dict]:
    """Findings from :data:`SUPPLY_RULES` that name a declared supply.

    A finding names a supply through either of its two net fields:
    ``erc.unconnected_net`` populates ``net`` alone, ``erc.supply_short``
    populates ``net`` and ``other_net`` (the shorted pair).
    """
    named = set(supplies)
    hits = []
    for finding in payload.get("erc_findings", []):
        if finding.get("rule") not in SUPPLY_RULES:
            continue
        if {finding.get("net"), finding.get("other_net")} & named:
            hits.append(finding)
    return hits


def verdict_lines(payload: dict, supplies: list[str], gds_hash: str) -> tuple[list[str], list[str]]:
    """``(report_lines, failure_lines)`` for the two always-on checks."""
    lines: list[str] = []
    failures: list[str] = []

    provenance = payload.get("provenance") or {}
    reported = ((provenance.get("input") or {}).get("content_hash")) or "<absent>"
    if reported == gds_hash:
        lines.append(f"input hash    : {reported} (matches the GDS on disk)")
    else:
        failures.append(
            "provenance.input.content_hash does not match the GDS on disk:\n"
            f"  report : {reported}\n"
            f"  on disk: {gds_hash}\n"
            "This report is not evidence about the committed layout. If klt "
            "is too old to emit a provenance block at all, upgrade it "
            "(layout/README.md, 'Install klt')."
        )

    hits = supply_findings(payload, supplies)
    lines.append(f"supplies      : {', '.join(supplies) if supplies else '<none declared>'}")
    lines.append(f"supply finding: {len(hits)}")
    for finding in hits:
        lines.append(
            f"  {finding.get('rule')} net={finding.get('net')} "
            f"other_net={finding.get('other_net')}"
        )
    return lines, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "gds", type=Path, nargs="?", default=DEFAULT_GDS, help=f"GDS/OASIS to read (default: {DEFAULT_GDS})"
    )
    parser.add_argument(
        "--spec", type=Path, default=DEFAULT_SPEC, help=f"klt erc spec file (default: {DEFAULT_SPEC})"
    )
    parser.add_argument("--fixture", help="report subdirectory name (default: the GDS file's stem)")
    parser.add_argument(
        "--suffix",
        default="erc",
        help="report filename suffix, before .json/.txt (default: erc)",
    )
    parser.add_argument(
        "--expect",
        choices=("supply-clean", "findings", "any"),
        default="supply-clean",
        help=(
            "verdict gate: 'supply-clean' (default) requires zero "
            "erc.unconnected_net/erc.supply_short naming a declared supply; "
            "'findings' requires at least one finding (the controls); "
            "'any' gates on nothing"
        ),
    )
    parser.add_argument("--top", help="top cell, when the stream has more than one")
    args = parser.parse_args(argv)

    klt = shutil.which("klt")
    if klt is None:
        print(
            "error: 'klt' not found on PATH. Install with:\n"
            "  uv tool install git+https://github.com/2AMLogic/klayout-tools\n"
            "(no PyPI release yet -- see layout/README.md)",
            file=sys.stderr,
        )
        return 1

    def resolve(path: Path) -> Path:
        return path if path.is_absolute() else (Path.cwd() / path).resolve()

    gds_path, spec_path = resolve(args.gds), resolve(args.spec)
    for label, path in (("gds", gds_path), ("spec", spec_path)):
        if not path.exists():
            print(f"error: {label} {path} does not exist", file=sys.stderr)
            return 1

    # Repo-relative paths, so the committed report's own "file"/"spec" fields
    # are reproducible regardless of invocation cwd (run_drc.py's convention).
    gds_rel = gds_path.relative_to(REPO_ROOT)
    spec_rel = spec_path.relative_to(REPO_ROOT)

    fixture = args.fixture or gds_path.stem
    reports_dir = REPORTS_ROOT / fixture
    reports_dir.mkdir(parents=True, exist_ok=True)

    when = _dt.datetime.now(_dt.timezone.utc)
    record_id = report_id.record_id(reports_dir, when, report_id.short_sha(REPO_ROOT))

    base_cmd = [klt, "erc", str(gds_rel), str(spec_rel)]
    if args.top:
        base_cmd += ["--top", args.top]

    procs = {
        fmt: subprocess.run(
            [*base_cmd, "--format", fmt],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        for fmt in ("json", "text")
    }

    if procs["json"].returncode not in OK_EXIT_CODES:
        print(procs["json"].stdout)
        print(procs["json"].stderr, file=sys.stderr)
        print(f"error: klt erc failed (exit {procs['json'].returncode})", file=sys.stderr)
        return 1

    json_path = reports_dir / f"{record_id}.{args.suffix}.json"
    text_path = reports_dir / f"{record_id}.{args.suffix}.txt"
    json_path.write_text(procs["json"].stdout)
    text_path.write_text(procs["text"].stdout)

    payload = json.loads(procs["json"].stdout)
    spec = json.loads(spec_path.read_text())
    supplies = declared_supplies(spec)

    lines, failures = verdict_lines(payload, supplies, sha256_of(gds_path))

    print(f"record id     : {record_id}")
    print(f"fixture       : {fixture}")
    print(f"spec          : {spec_rel}")
    print(f"klt exit      : {procs['json'].returncode}")
    print(f"status        : {payload.get('status')}")
    print(f"gate_count    : {payload.get('gate_count')}")
    print(f"findings      : {payload.get('erc_finding_count')}")
    for line in lines:
        print(line)
    print(f"report (json) : {json_path.relative_to(REPO_ROOT)}")
    print(f"report (text) : {text_path.relative_to(REPO_ROOT)}")

    total = payload.get("erc_finding_count") or 0
    if args.expect == "supply-clean" and supply_findings(payload, supplies):
        failures.append(
            "--expect supply-clean: a declared supply is named by an "
            "erc.unconnected_net or erc.supply_short finding (listed above). "
            "Per gf180-bandgap#192 this is a REAL FINDING about the layout -- "
            "file it as its own issue; do not tune the spec until it passes."
        )
    if args.expect == "findings" and total == 0:
        failures.append(
            "--expect findings: this control reported ZERO findings. It exists "
            "to demonstrate that the ERC finding rules actually fire, so a "
            "clean result here means the signoff report's own zero has stopped "
            "meaning anything. See this spec's own _comment block."
        )

    if failures:
        print()
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
