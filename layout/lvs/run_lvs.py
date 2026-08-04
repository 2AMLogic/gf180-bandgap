#!/usr/bin/env python3
"""Reproducible, append-only ``klt extract`` + ``klt lvs`` run for ``layout/``.

The LVS half of the flow ``layout/drc/run_drc.py`` starts. Given a GDS and a
reference netlist it:

1. regenerates the reference netlist (``layout/lvs/make_reference.py``) so a
   stale, hand-edited reference can never quietly pass;
2. runs ``klt extract --deck gf180mcu`` and keeps the extracted netlist;
3. runs ``klt lvs`` against the reference, once per selected engine
   (``--engine``);
4. writes all artefacts under ``layout/lvs/reports/<block>/<record-id>.*``.

``<record-id>`` is ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, the same
convention ``sim/README.md`` documents for ``sim/`` evidence and
``layout/drc/run_drc.py`` uses for DRC reports. **Reports are never
overwritten** — CLAUDE.md: "``sim/`` results are append-only evidence", and
this repo applies the same rule to ``layout/`` reports.

Engines
-------

``klt lvs`` ships two comparators (klayout-tools#343/#360). ``klayout`` (the
default, and the only one this script used before gf180-bandgap#109) is
KLayout's in-process ``NetlistComparer``; ``netgen`` wraps
``RTimothyEdwards/netgen``'s ``netgen -batch lvs`` as a subprocess. Selecting
``--engine both`` runs each in turn and reports whether the two independent
comparators reach the same verdict on the same inputs.

What the second engine buys is **comparator independence, not extraction
independence**: netgen has no layout front-end here, so both engines compare
the *same* ``klt extract`` output. A bug in extraction is invisible to both;
a bug in the graph-matching step is not. The netgen engine also needs the
``netgen`` binary on ``$PATH`` (not bundled, not pip-installable), which is
why it is opt-in rather than always-on — a machine without it must still be
able to run the default flow.

Usage (from the repo root)::

    python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds
    python3 layout/lvs/run_lvs.py layout/bandgap_top/bandgap_top.gds --engine both
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

#: ``klt lvs`` comparators this script knows how to drive, in the order
#: ``--engine both`` runs them. ``klayout`` stays first so its report keeps
#: the historical, unsuffixed file names.
ENGINES = ("klayout", "netgen")

#: The engine whose request document and report files keep the pre-#109 shape:
#: no ``engine`` key in the request, no engine suffix on the report names.
DEFAULT_ENGINE = ENGINES[0]


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
    """Return the first ``<date>-<time>-<sha>`` id no artefact already claims.

    The probe is over ``<record-id>.*`` rather than ``<record-id>.lvs.json``
    specifically: a ``--engine netgen`` run writes ``.lvs-netgen.json`` and no
    ``.lvs.json`` at all, so keying append-only-ness on one engine's file name
    would let a later run of the *other* engine reuse the id and clobber the
    extraction artefacts recorded under it.
    """
    while True:
        record_id = f"{when.strftime('%Y%m%d-%H%M%S')}-{short_sha}"
        if next(reports_dir.glob(f"{record_id}.*"), None) is None:
            return record_id
        when += _dt.timedelta(seconds=1)


def _engine_stem(engine: str) -> str:
    """Report-file stem for ``engine``'s artefacts, minus the record id.

    ``klayout`` keeps the unsuffixed pre-#109 names (``.lvs.json``,
    ``.lvs.txt``, ``.lvs-request.json``) so the existing evidence trail stays
    one continuous series; every other engine gets its own ``.lvs-<engine>*``
    series, so no two engines can ever write the same path.
    """
    return "lvs" if engine == DEFAULT_ENGINE else f"lvs-{engine}"


def _build_request(
    *,
    gds_path: Path,
    reports_dir: Path,
    reference: Path,
    deck: str,
    top: str,
    engine: str,
) -> dict:
    """Build the ``klt lvs`` request document for one engine.

    `klt lvs` resolves every relative path inside a request document against
    the **request file's own directory**, not the process cwd
    (``klayout_tools.lvs.run_lvs`` -> ``request_dir``). The request lives under
    ``layout/lvs/reports/<block>/``, so repo-root-relative paths would resolve
    to nonexistent files. Emit paths relative to the request directory instead
    — machine-independent (unlike absolute paths), so the committed request
    document stays reproducible on any checkout.

    The default engine deliberately emits **no** ``engine`` key: ``klt lvs``
    defaults to ``"klayout"``, and omitting it keeps the committed request
    documents byte-identical to every one recorded before #109.
    """
    request = {
        "layout": {
            "file": os.path.relpath(gds_path, reports_dir),
            "deck": deck,
            "top": top,
        },
        "reference": {
            "netlist": os.path.relpath(reference.resolve(), reports_dir),
            "top": top,
        },
    }
    if engine != DEFAULT_ENGINE:
        request["engine"] = engine
    return request


def _run_engine(
    *,
    klt: str,
    engine: str,
    request: dict,
    reports_dir: Path,
    record_id: str,
) -> tuple[dict | None, str | None]:
    """Run ``klt lvs`` for one engine and record its verdict.

    Returns ``(payload, None)`` on a completed comparison (match *or*
    mismatch), or ``(None, message)`` when ``klt lvs`` itself failed. The
    failure message carries `klt`'s own stdout/stderr verbatim: a missing
    ``netgen`` binary is an actionable `klt lvs` error, and swallowing it in
    favour of a generic "lvs failed" would defeat the point of asking for the
    second engine in the first place.
    """
    stem = _engine_stem(engine)
    request_path = reports_dir / f"{record_id}.{stem}-request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    request_arg = str(request_path.relative_to(REPO_ROOT))

    lvs_json = subprocess.run(
        [klt, "lvs", request_arg, "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # exit 0 (match) and exit 3 (mismatch) are both successful runs.
    if lvs_json.returncode not in (0, 3):
        return None, (
            f"{lvs_json.stdout}{lvs_json.stderr}\n"
            f"error: klt lvs --engine {engine} failed (exit {lvs_json.returncode})"
        )
    lvs_text = subprocess.run(
        [klt, "lvs", request_arg, "--format", "text"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    (reports_dir / f"{record_id}.{stem}.json").write_text(lvs_json.stdout)
    (reports_dir / f"{record_id}.{stem}.txt").write_text(lvs_text.stdout)
    return json.loads(lvs_json.stdout), None


def build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--engine",
        choices=(*ENGINES, "both"),
        default=DEFAULT_ENGINE,
        help=(
            "klt lvs comparator to run (default: %(default)s). 'netgen' is an "
            "independent cross-check of the compare step and needs the netgen "
            "binary on PATH; 'both' runs each in turn and reports whether the "
            "two verdicts agree. Reports are written per engine "
            "(<record-id>.lvs.* for klayout, <record-id>.lvs-netgen.* for "
            "netgen), never overwritten"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    engines = ENGINES if args.engine == "both" else (args.engine,)

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

    # 3. Compare — once per selected engine, each against the same extraction.
    extract_payload = json.loads(extract_proc.stdout)
    print(f"record id        : {record_id}")
    print(f"block            : {block}")
    print(f"extracted devices: {extract_payload['device_count']} "
          f"{extract_payload['device_counts']}")

    verdicts: dict[str, str] = {}
    for engine in engines:
        payload, error = _run_engine(
            klt=klt,
            engine=engine,
            request=_build_request(
                gds_path=gds_path,
                reports_dir=reports_dir,
                reference=args.reference,
                deck=args.deck,
                top=top,
                engine=engine,
            ),
            reports_dir=reports_dir,
            record_id=record_id,
        )
        if error is not None or payload is None:
            print(error, file=sys.stderr)
            return 1
        verdicts[engine] = payload["status"]
        report = reports_dir / f"{record_id}.{_engine_stem(engine)}.json"
        print(f"engine           : {engine}")
        print(f"lvs status       : {payload['status']}")
        print(f"mismatch_count   : {payload['mismatch_count']}")
        print(f"devices matched  : {payload['counts']['devices']['matched']} / "
              f"{payload['counts']['devices']['reference']}")
        print(f"nets matched     : {payload['counts']['nets']['matched']} / "
              f"{payload['counts']['nets']['reference']}")
        print(f"report (json)    : {report.relative_to(REPO_ROOT)}")

    # A cross-engine disagreement is a finding about the *tools*, not about
    # the layout, so it is reported rather than made fatal — same reason a
    # `mismatch` verdict exits 0 here: this script mints evidence, the reader
    # judges it.
    if len(verdicts) > 1:
        agreed = len(set(verdicts.values())) == 1
        detail = " ".join(f"{name}={status}" for name, status in verdicts.items())
        print(f"cross-check      : {'agree' if agreed else 'DISAGREE'} ({detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
