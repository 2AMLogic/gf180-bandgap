#!/usr/bin/env python3
"""Ingest a finished fleet `klt sim` output-voltage-tc run into append-only evidence.

Why this exists: `sim/tools/mk_klt_request.py` turns the bench into a `klt sim`
request that goes to the Spot fleet, but the fleet report only carries raw
`.meas` values. This module does what the (absent) post-processor was meant
to: completeness assessment of the expected PVT matrix, box-method TC, and
the ratified-threshold verdicts -- and writes the sim/README.md evidence
(record, frozen self-contained deck, per-corner logs, request/report).

Nothing here relaxes a limit: the thresholds are read from
`sim/output-voltage-tc/testbench/tb.json`. Missing corners, backend errors,
null measurements and an inconsistent temperature sweep are *never* dropped:
they turn the verdict into INCOMPLETE (or FAIL), and the record says so.

    # 1. request (self-contained deck, optional Vref(T) samples for retuning)
    python3 sim/tools/mk_klt_request.py output-voltage-tc WORK --curve
    # 2. dispatch to the fleet (never a local grid on a shared worker)
    klt sim --backend batch -o WORK/out WORK/request.json --format json > WORK/report.json
    # 3. ingest
    python3 sim/tools/tc_ingest.py WORK [--supersedes ID] [--issue N] [--note TEXT]

The pure functions (`collect`, `assess`, `box_tc_ppm`, `reconstruct`) are unit
tested in `sim/tests/test_tc_ingest.py` without a PDK, ngspice or the fleet.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(HERE))

import fleet_common as fc  # noqa: E402
from harness import corners as hc  # noqa: E402

EXPERIMENT = "output-voltage-tc"
TB_JSON = SIM / EXPERIMENT / "testbench" / "tb.json"
TC_SPAN_C = 165.0  # -40..125 C
SWEEP_POINTS = 166
ENDPOINT_NAMES = ("vref_m40", "vref_27", "vref_125")
BOX_NAMES = ("vref_box_max", "vref_box_min")
REQUIRED = ENDPOINT_NAMES + BOX_NAMES
CURVE_RE = re.compile(r"^vref_t(m?)(\d+)$")
# Consistency tolerance between a `.meas ... AT=` point and the same
# temperature sampled again by a second card (identical sweep point -> equal).
SAMPLE_TOL_V = 1e-9


def load_tb() -> dict:
    return json.loads(TB_JSON.read_text())


corner_key = fc.corner_key  # 'tt/2.970V/27C' -> ('tt', 2.97); shared with fleet_ingest.py


def expected_points(tb: dict | None = None) -> list[tuple[str, float]]:
    """Process x supply points the bench's own tb.json demands (temperature is
    the internal 1 C sweep, so the outer axis is a single point)."""
    tb = tb or load_tb()
    names = [c.name for c in hc.resolve_corners(tb["corners"])]
    vdds = hc.supply_points(tb["nominal_supply_v"], tb.get("supply_tolerance", 0.0))
    return [(n, round(v, 4)) for n in names for v in vdds]


def box_tc_ppm(vmax: float, vmin: float, v27: float) -> float:
    """The bench's convention: (Vref_max - Vref_min)/(Vref_27 * 165) * 1e6."""
    return (vmax - vmin) / (v27 * TC_SPAN_C) * 1e6


def curve_of(vals: dict) -> dict[int, float]:
    """{temperature C: Vref} from the optional `vref_t<T>` sample measurements."""
    out = {}
    for k, v in vals.items():
        m = CURVE_RE.match(k)
        if m:
            out[-int(m.group(2)) if m.group(1) else int(m.group(2))] = v
    return dict(sorted(out.items()))


def collect(report: dict, expected: list[tuple[str, float]]):
    """-> (points, missing, failed, problems); see `fleet_common.collect_units`.

    points : {(process, vdd): {measurement: value}} for corners that returned
             every REQUIRED measurement as a finite number.
    missing: expected points absent from the report, or present but lacking a
             finite REQUIRED measurement (reason attached).
    failed : points whose klt status is error (etc.) with the diagnostics the
             backend gave.
    problems: report-level issues (duplicate corners, unexpected corners).
    """
    return fc.collect_units(
        report, expected, REQUIRED,
        lambda cid: (lambda k: (k[0], round(k[1], 4)))(corner_key(cid)),
    )


def sweep_consistency(vals: dict) -> list[str]:
    """Things that must hold if the 166-point -40..125 C, 1 C sweep really ran.

    The fleet report cannot return `length(dc1.v(vref))`, so this is the
    independent evidence the sweep is complete: the box extrema bracket every
    sampled point and the endpoint measurements, and (when sampled) a second
    `.meas` card at the same temperature agrees with the endpoint card.
    """
    errs = []
    hi, lo = vals["vref_box_max"], vals["vref_box_min"]
    ends = [vals[n] for n in ENDPOINT_NAMES]
    curve = curve_of(vals)
    pts = ends + list(curve.values())
    if hi < max(pts) - SAMPLE_TOL_V:
        errs.append(f"vref_box_max {hi:.6f} below a sampled point {max(pts):.6f}")
    if lo > min(pts) + SAMPLE_TOL_V:
        errs.append(f"vref_box_min {lo:.6f} above a sampled point {min(pts):.6f}")
    for name, t in (("vref_m40", -40), ("vref_125", 125)):
        if t in curve and abs(curve[t] - vals[name]) > SAMPLE_TOL_V:
            errs.append(f"{name} disagrees with vref_t{t}")
    if curve and not {-40, 125} <= set(curve):
        errs.append("sampled curve does not span -40..125 C")
    return errs


def assess(points, missing, failed, problems, tb: dict | None = None, expected=None):
    """Per-corner derived values + verdicts + one overall verdict.

    Overall: INCOMPLETE if anything expected is missing/failed (never PASS),
    else FAIL if any ratified check fails, else PASS.
    """
    tb = tb or load_tb()
    lim_v = tb["checks"]["vref"]
    lim_tc = tb["checks"]["tc_ppm"]
    rows = {}
    for key, v in points.items():
        tc = box_tc_ppm(v["vref_box_max"], v["vref_box_min"], v["vref_27"])
        accuracy_vals = [v[n] for n in REQUIRED]
        v_ok = all(lim_v["min"] <= x <= lim_v["max"] for x in accuracy_vals)
        tc_ok = tc <= lim_tc["max"]
        sweep_errs = sweep_consistency(v)
        rows[key] = {
            "tc_ppm": tc,
            "vref_ok": v_ok,
            "tc_ok": tc_ok,
            "sweep_errs": sweep_errs,
            "pass": v_ok and tc_ok and not sweep_errs,
        }
    bad_sweep = [k for k, r in rows.items() if r["sweep_errs"]]
    incomplete = bool(missing or failed or problems or bad_sweep)
    if incomplete:
        overall = "INCOMPLETE"
    elif all(r["pass"] for r in rows.values()):
        overall = "PASS"
    else:
        overall = "FAIL"
    return {"rows": rows, "overall": overall, "bad_sweep": bad_sweep}


def worst(points, rows):
    """Worst-case summary used by the record and by retuning."""
    if not points:
        return {}
    k_tc = max(rows, key=lambda k: rows[k]["tc_ppm"])
    k_hi = max(points, key=lambda k: points[k]["vref_box_max"])
    k_lo = min(points, key=lambda k: points[k]["vref_box_min"])
    return {
        "tc": (rows[k_tc]["tc_ppm"], k_tc),
        "vmax": (points[k_hi]["vref_box_max"], k_hi),
        "vmin": (points[k_lo]["vref_box_min"], k_lo),
    }


def reconstruct(vals_a: dict, vals_b: dict, r1_a: float, r1_b: float, r1: float) -> dict[int, float]:
    """Vref(T) at a new R1 from two runs at R1_a, R1_b.

    Vref(T) = VEB(Q3)(T) + I(T)*(R1 + Rtrim) with I = dVBE/R2 independent of
    R1 (design/bandgap_operating_point.md, #96), so Vref is exactly affine in
    R1 at each temperature. Needs the sampled `vref_t<T>` curves of both runs.
    """
    ca, cb = curve_of(vals_a), curve_of(vals_b)
    out = {}
    for t in sorted(set(ca) & set(cb)):
        slope = (cb[t] - ca[t]) / (r1_b - r1_a)
        out[t] = ca[t] + slope * (r1 - r1_a)
    return out


def curve_tc_ppm(curve: dict[int, float]) -> float:
    """Box TC from a sampled curve (retuning estimate only; verdicts use the
    fleet's 1 C-sweep extrema)."""
    return box_tc_ppm(max(curve.values()), min(curve.values()), curve[27] if 27 in curve else _interp27(curve))


def _interp27(curve):
    lo, hi = max(t for t in curve if t < 27), min(t for t in curve if t > 27)
    return curve[lo] + (curve[hi] - curve[lo]) * (27 - lo) / (hi - lo)


# --------------------------------------------------------------------------
# evidence writing
# --------------------------------------------------------------------------


def _fmt(x, n=6):
    return f"{x:.{n}g}"


def corner_id(process: str, vdd: float) -> str:
    return f"{process}_27c_{vdd:.2f}v"


def build_record(record, stamp, report, req, tb, expected, points, missing, failed, problems,
                 verdict, dut_rel, dut_sha, tb_sha, deck_sha, issue, supersedes, note, git=None) -> str:
    rows = verdict["rows"]
    env = report.get("environment", {})
    remote = env.get("remote", {}) or {}
    prov = report.get("provenance", {}) or {}
    overall = verdict["overall"]
    L = []
    add = L.append
    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add("- **Claim**: " + tb["claim"].split(" Caveat carried")[0]
        + f" Evidence for issue #{issue} (DR-0007 retuning of canonical R2/R1): untrimmed (trim code 32)"
        " deterministic corner result, no Monte Carlo/mismatch claim (later suite child)."
        + ("" if overall != "INCOMPLETE" else " **INCOMPLETE -- see Result: missing/failed points; no verdict is claimed.**"))
    add(f"- **Netlist provenance**: schematic -- DUT `{dut_rel}` (sha256 `{dut_sha}`), "
        f"driven by `sim/output-voltage-tc/testbench/tb_output_voltage_tc.spice` (sha256 `{tb_sha}`); "
        f"frozen self-contained fleet deck sha256 `{deck_sha}` (`netlist-snapshots/{record}.spice`). "
        "The deck is frozen in the snapshot, so the result is reproducible from it regardless of tree state "
        "(git state in Environment).")
    add("- **Corner matrix run**:")
    procs = []
    for p, _ in expected:
        if p not in procs:
            procs.append(p)
    vdds = sorted({v for _, v in expected})
    add(f"  - Process: {', '.join(procs)}")
    add("  - Temperature: -40, 27, 125 C reported; the full -40..125 C range is swept internally "
        "(`dc temp -40 125 1`, 166 points at 1 C) at every process/supply point, so the outer axis is "
        "the single fleet point per process/supply; its one log is stored under each of -40c/27c/125c "
        "(`<process>_<T>c_<V>v.log`, with the sweep's value at that T appended as `m_vref`). Box extrema come from the full 1 C sweep, "
        "not from the three reported temperatures.")
    add("  - Supply: " + ", ".join(f"{v:.2f} V" for v in vdds))
    add(f"  - {len(expected)} process x supply points expected; {len(points)} returned complete; "
        f"{len(missing)} missing, {len(failed)} failed/errored"
        + (f", {len(verdict['bad_sweep'])} with an inconsistent sweep" if verdict["bad_sweep"] else "") + ".")
    add("- **Statistical convention**: N/A (corner-matrix claim, not a distribution claim)")
    add("- **Result**:")
    add("  - Sweep-completeness caveat: the fleet report returns `.meas` values only, so the bench's "
        "`sweep_points == 166` check cannot be counted here. It is replaced by consistency checks on every "
        "point (box max/min bracket the endpoint values and every 5 C `vref_t<T>` sample when present; "
        "-40 and 125 C reached; a failing check makes the point, and the record, INCOMPLETE). A local "
        "harness run still counts the 166 points.")
    if missing or failed or problems:
        add("  - **INCOMPLETE.**")
        for k, why in missing:
            add(f"    - missing `{corner_id(*k)}`: {why}")
        for k, why in failed:
            add(f"    - failed `{corner_id(*k)}`: {why}")
        for p in problems:
            add(f"    - report problem: {p}")
    if note:
        add(f"  - {note}")
    add("")
    add("  | corner-id | vref@-40 | vref@27 | vref@125 | vref_box_min | vref_box_max | tc_ppm | accuracy | tc | sweep | pass/fail |")
    add("  |---|---|---|---|---|---|---|---|---|---|---|")
    for key in expected:
        if key not in points:
            add(f"  | `{corner_id(*key)}` | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | - | - | - | **MISSING** |")
            continue
        v, r = points[key], rows[key]
        add(f"  | `{corner_id(*key)}` | {_fmt(v['vref_m40'])} | {_fmt(v['vref_27'])} | {_fmt(v['vref_125'])} | "
            f"{_fmt(v['vref_box_min'])} | {_fmt(v['vref_box_max'])} | {_fmt(r['tc_ppm'], 5)} | "
            f"{'ok' if r['vref_ok'] else 'FAIL'} | {'ok' if r['tc_ok'] else 'FAIL'} | "
            f"{'ok' if not r['sweep_errs'] else 'BAD: ' + '; '.join(r['sweep_errs'])} | "
            f"{'PASS' if r['pass'] else 'FAIL'} |")
    w = worst(points, rows)
    add("")
    if w:
        lv, tcl = tb["checks"]["vref"], tb["checks"]["tc_ppm"]
        scope = "all returned points" if overall != "INCOMPLETE" else "the returned points ONLY (record incomplete)"
        add(f"  Worst case over {scope}:")
        add("")
        add(f"  - max box TC: **{w['tc'][0]:.4f} ppm/C** at `{corner_id(*w['tc'][1])}` (limit <= {tcl['max']:g})")
        add(f"  - highest Vref over the -40..125 C sweep: **{w['vmax'][0]:.5f} V** at `{corner_id(*w['vmax'][1])}` (limit <= {lv['max']:g})")
        add(f"  - lowest Vref over the -40..125 C sweep: **{w['vmin'][0]:.5f} V** at `{corner_id(*w['vmin'][1])}` (limit >= {lv['min']:g})")
        add("")
    add(f"  - **Overall: {overall}**")
    add("- **Links**:")
    add("  - Testbench: `sim/output-voltage-tc/testbench/tb_output_voltage_tc.spice`, `sim/output-voltage-tc/testbench/tb.json`")
    add(f"  - DUT netlist: `{dut_rel}`")
    add(f"  - Netlist snapshot: `sim/output-voltage-tc/netlist-snapshots/{record}.spice`")
    add(f"  - Raw logs: `sim/output-voltage-tc/corners/{record}/` (also `request.json`, `report.json`, `<corner-id>.cir`)")
    add("  - Request adapter: `sim/tools/mk_klt_request.py`; ingestion: `sim/tools/tc_ingest.py`")
    if remote:
        add(f"  - Fleet execution: {remote.get('provider')} job `{remote.get('job_id')}`, {remote.get('instance_type')} "
            f"({remote.get('lifecycle')}) {remote.get('instance_id')}, state {remote.get('state')}, "
            f"exit {remote.get('exit_code')}, {remote.get('elapsed_seconds')} s")
    else:
        add("  - Fleet execution: NOT RECORDED in the report (`environment.remote` absent)")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #{issue})")
    add(f"- **Supersedes**: {supersedes or '(none)'}")
    add("")
    add("## Environment")
    add("")
    add(f"- klt: client {remote.get('client_klt_version')}, fleet runner {remote.get('runner_klt_version')} "
        f"(compatibility: {remote.get('runner_compatibility')}); report provenance klt {prov.get('klt_version')}")
    add(f"- engine: {env.get('engine')} {env.get('engine_version')}; "
        f"PDK {prov.get('pdk', {}).get('name')} ({prov.get('pdk', {}).get('version')}); "
        f"model deck {prov.get('deck', {}).get('name')} {prov.get('deck', {}).get('content_hash')}")
    if git:
        add(f"- git: `{git.get('commit', git.get('short'))}` on `{git.get('branch')}`"
            f"{' (dirty working tree at ingest; the frozen deck, not the tree, is the evidence)' if git.get('dirty') else ''}")
    add(f"- measurements declared: {', '.join(m['name'] for m in req['measurements'])}")
    add("")
    add("Per-corner model sections used:")
    add("")
    for p in req["corners"]["process"]:
        add(f"- `{p['name']}`: {' '.join(p['sections'])}")
    add("")
    add("---")
    add("")
    add("Written by `sim/tools/tc_ingest.py`. Append-only: never edit or delete this file -- a re-run or "
        "correction mints a new record-id and points back here via **Supersedes** (see `sim/README.md`).")
    add("")
    return "\n".join(L)


OUTER_TEMPS_C = (-40, 27, 125)
INVALID_POINT_MARKER = "*** sim/harness: INVALID POINT"  # mirrors harness.runner / suite.analysis


def corner_id_at(process: str, temp_c: int, vdd: float) -> str:
    return f"{process}_{temp_c}c_{vdd:.2f}v"


def write_corner_logs(cdir: Path, work: Path, report: dict, points: dict, record: str) -> None:
    """Per-PVT-point raw logs in the sim/README.md corner-id grammar.

    One fleet unit (process x supply) holds the whole internal -40..125 C
    sweep, so its single ngspice log is written once per outer temperature
    (-40/27/125) -- the layout every earlier output-voltage-tc record and the
    suite readers (`sim/suite/`) expect. The `m_*` lines appended to a valid
    point are the fleet's own `.meas` values (vref at that temperature from the
    sweep, and the sweep-wide box figures), rewritten in the harness's
    `m_<name> = <value>` shape; a point that did not produce all measurements
    gets the harness's INVALID POINT trailer instead, so readers reject it.
    """
    cdir.mkdir(parents=True, exist_ok=True)
    for c in report.get("corners", []):
        try:
            p, v = corner_key(c["corner_id"])
        except Exception:
            continue
        key = (p, round(v, 4))
        art = c.get("artifacts") or {}
        src = work / (art.get("log") or "")
        raw = src.read_text() if art.get("log") and src.exists() else "(no ngspice.log returned)\n"
        vals = points.get(key)
        for t in OUTER_TEMPS_C:
            head = (f"* record-id : {record}\n* klt corner : {c['corner_id']} (status {c.get('status')}); "
                    f"outer-axis point {t} C of the internal -40..125 C sweep\n")
            tail = ""
            if vals:
                at = {-40: vals["vref_m40"], 27: vals["vref_27"], 125: vals["vref_125"]}[t]
                tc = box_tc_ppm(vals["vref_box_max"], vals["vref_box_min"], vals["vref_27"])
                tail = ("\n* ---- derived by sim/tools/tc_ingest.py from the fleet .meas values in this log ----\n"
                        f"m_vref = {at:.10e}\nm_tc_ppm = {tc:.10e}\n"
                        f"m_vref_box_max = {vals['vref_box_max']:.10e}\nm_vref_box_min = {vals['vref_box_min']:.10e}\n"
                        f"m_vref_m40 = {vals['vref_m40']:.10e}\nm_vref_27 = {vals['vref_27']:.10e}\n"
                        f"m_vref_125 = {vals['vref_125']:.10e}\n")
            else:
                tail = (f"\n{INVALID_POINT_MARKER} -- status={c.get('status')} ***\n"
                        "*** fleet unit returned no complete set of measurements ***\n")
            (cdir / f"{corner_id_at(p, t, v)}.log").write_text(head + raw + tail)
        deck = work / (art.get("deck") or "")
        if art.get("deck") and deck.exists():
            shutil.copyfile(deck, cdir / f"{corner_id_at(p, 27, v)}.cir")


def sha256(p: Path) -> str:
    return fc.sha256_file(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workdir", help="dir with request.json, report.json, body.spice, out/")
    ap.add_argument("--dut", default="sim/dut/bandgap_top.spice", help="DUT the request was built from")
    ap.add_argument("--dut-rev", default=None, help="hash the DUT as committed at this git rev (e.g. a pre-retune baseline)")
    ap.add_argument("--dut-label", default=None, help="DUT description for the record (default: --dut, plus @rev)")
    ap.add_argument("--issue", default="209")
    ap.add_argument("--supersedes", default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the verdict, write nothing")
    a = ap.parse_args()

    from harness import report as hreport

    work = Path(a.workdir).resolve()
    report = json.loads((work / "report.json").read_text())
    req = json.loads((work / "request.json").read_text())
    tb = load_tb()
    expected = expected_points(tb)
    points, missing, failed, problems = collect(report, expected)
    verdict = assess(points, missing, failed, problems, tb)
    w = worst(points, verdict["rows"])
    print(f"overall={verdict['overall']} points={len(points)}/{len(expected)} "
          f"missing={len(missing)} failed={len(failed)} problems={len(problems)}")
    if w:
        print(f"worst tc={w['tc'][0]:.4f} at {w['tc'][1]}; vmax={w['vmax'][0]:.5f}; vmin={w['vmin'][0]:.5f}")
    if a.dry_run:
        return 0 if verdict["overall"] == "PASS" else 2

    exp_dir = SIM / EXPERIMENT
    git = hreport.git_provenance(REPO)
    record = hreport.allocate_record_id(REPO, exp_dir / "records", git=git)
    stamp = datetime.strptime(record[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)

    cdir = exp_dir / "corners" / record
    write_corner_logs(cdir, work, report, points, record)
    for n in ("request.json", "report.json"):
        shutil.copyfile(work / n, cdir / n)
    snap = exp_dir / "netlist-snapshots"
    snap.mkdir(exist_ok=True)
    shutil.copyfile(work / "body.spice", snap / f"{record}.spice")

    if a.dut_rev:
        import hashlib
        import subprocess

        blob = subprocess.run(["git", "show", f"{a.dut_rev}:{a.dut}"], cwd=REPO, check=True, capture_output=True).stdout
        dut_sha = hashlib.sha256(blob).hexdigest()
    else:
        dut_sha = sha256(Path(a.dut) if Path(a.dut).is_absolute() else REPO / a.dut)
    dut_label = a.dut_label or (f"{a.dut} @ {a.dut_rev}" if a.dut_rev else a.dut)
    text = build_record(
        record, stamp, report, req, tb, expected, points, missing, failed, problems, verdict,
        dut_label, dut_sha, sha256(exp_dir / "testbench" / tb["netlist"]), sha256(work / "body.spice"),
        a.issue, a.supersedes, a.note, git,
    )
    path = hreport.device_write_record(exp_dir / "records", record, text)
    print(f"wrote {path}")
    return 0 if verdict["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
