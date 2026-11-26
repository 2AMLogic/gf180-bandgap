#!/usr/bin/env python3
"""Equal-Ie effective area ratio of the four-unit Q2 array (issue #208).

DR-0007 Decision item 1 requires the array's effective ratio
`A_eff = exp(dVBE / VT)` to be measured at equal TOTAL emitter current at the
design current (~5.07 uA), over the BJT process corners x -40/27/125 C, before
the R2 rescale locks to it. This script

  1. builds the `klt sim` request (sim/tools/mk_klt_device_request.py),
  2. submits it with `klt sim` -- the grid goes to the Spot fleet through
     KLT_SIM_BACKEND=batch; it REFUSES to run a multi-point grid on the local
     backend (shared dispatch worker; no hand-rolled ngspice loops),
  3. checks every expected (corner, temperature) point came back and passed,
  4. writes the append-only evidence (request, report, raw logs, frozen
     netlist, record) under sim/device-pnp-array/.

Points that failed or are missing are listed in the record; the record is then
headed INCOMPLETE and carries no ratio range.

    python3 sim/device-pnp-array/run_pnp_array.py [--from-report DIR]

`--from-report DIR` skips dispatch and re-ingests a finished `klt sim` output
directory (DIR/request.json, DIR/report.json, DIR/out/).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import mk_klt_device_request as req  # noqa: E402
import fleet_common as fc  # noqa: E402
from harness import corners as hcorners  # noqa: E402
from harness import report as hreport  # noqa: E402

K_OVER_Q = 1.380649e-23 / 1.602176634e-19  # V/K


def thermal_voltage(temp_c: float) -> float:
    """kT/q in volts; `temp_c` is degrees Celsius (klt's unit)."""
    return (temp_c + 273.15) * K_OVER_Q


def a_eff(vbe_unit: float, vbe_other: float, temp_c: float) -> float:
    """exp((VBE_unit - VBE_other)/VT): effective ratio of `other` to one unit."""
    return math.exp((vbe_unit - vbe_other) / thermal_voltage(temp_c))


def parse_corner_id(cid: str) -> tuple[str, float]:
    """'bjt_typical/novdd/-40C' -> ('bjt_typical', -40.0).

    Parses with the fleet corner-id grammar (`fc.parse_klt_corner_id`) and
    rejects a corner id that carries a supply axis: every branch of this
    bench is current-source driven with no supply rail, so a supply in the
    id is a wrong report, not a point to ingest.
    """
    section, supply, temp = fc.parse_klt_corner_id(cid)
    if supply is not None:
        raise ValueError(f"corner id {cid!r} carries supply {supply:g}V; this bench has no supply rail")
    return section, temp


def collect(report: dict, expected: list[tuple[str, float]]):
    """-> (points, missing, failed, problems, keyed_rows); see `fleet_common.collect_units`.

    points: {(section, temp): {measurement name: value}} for passing corners
    carrying every declared measurement; missing: expected points absent from
    the report or lacking a measurement; failed: points whose execution the
    fleet collector rejects, plus this bench's pass-only rule; problems:
    report-level issues (duplicate / unexpected / rejected corner ids).
    keyed_rows: (parsed key, original row) pairs in report order for logging,
    including identifiable rows whose measurements or execution failed.

    Device-bench additions over the shared collector:

    * every corner id must be a no-supply id (`parse_corner_id` raises
      otherwise); a rejected id is a report-level problem and its expected
      point counts as missing, so the verdict is incomplete;
    * pass-only: a `fail` verdict is a legitimate fleet result but not an
      accepted measurement for this characterization (pinned by
      `sim/tests/test_pnp_array.py`) -- demoted from points to failed.
    """
    required = [m["name"] for m in req.measurements()]
    bad_ids, keyed_rows = [], []
    key_by_id = {}
    for c in report.get("corners", []):
        try:
            cid = c["corner_id"]
            key = parse_corner_id(cid)
        except Exception as e:
            bad_ids.append(f"rejected corner identity: {e}")
            continue
        key_by_id[cid] = key
        keyed_rows.append((key, c))
    points, missing, failed, problems = fc.collect_units(
        {"corners": [c for _, c in keyed_rows]}, expected, required, key_by_id.__getitem__
    )
    status_of = {key: c.get("status") for key, c in keyed_rows}
    for k in list(points):
        if status_of.get(k) != "pass":
            failed.append((k, status_of.get(k)))
            del points[k]
    return points, missing, failed, bad_ids + problems, keyed_rows


def ratios(vals: dict, temp_c: float) -> dict:
    """Per-current array and monolithic effective ratios at one point."""
    out = {}
    for ua in req.CURRENTS_UA:
        u = vals[req.meas_name("u", ua)]
        out[ua] = {
            "array": a_eff(u, vals[req.meas_name("a", ua)], temp_c),
            "mono": a_eff(u, vals[req.meas_name("m", ua)], temp_c),
        }
    return out


def dispatch(workdir: Path) -> None:
    backend = os.environ.get("KLT_SIM_BACKEND", "")
    if backend not in ("batch", "remote"):
        raise SystemExit(
            f"KLT_SIM_BACKEND={backend!r}: refusing to run the 9-point grid on a "
            "local backend. Export KLT_SIM_BACKEND=batch (the Spot fleet)."
        )
    rc = subprocess.run(
        ["klt", "sim", "-o", str(workdir / "out"), str(workdir / "request.json"),
         "--format", "json"],
        stdout=(workdir / "report.json").open("w"),
        stderr=(workdir / "stderr.txt").open("w"),
    ).returncode
    if rc != 0 or not (workdir / "report.json").read_text().strip():
        raise SystemExit(
            f"klt sim failed (rc={rc}); stderr:\n{(workdir / 'stderr.txt').read_text()}"
        )


def pct(x: float) -> str:
    return f"{x:.4f}"


def build_record(record, stamp, report, points, missing, failed, problems, cids) -> str:
    L = []
    add = L.append
    complete = not missing and not failed and not problems
    env = report.get("environment", {})
    remote = env.get("remote", {})
    prov = report.get("provenance", {})
    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add(
        "- **Claim**: equal-total-emitter-current effective ratio "
        "`A_eff = exp(dVBE/VT)` of the four-parallel-`pnp_05p00x05p00` Q2 "
        "realisation versus one unit, at the design current ~5.07 uA, per "
        "`spec/decision-records/0007-q2-array-dvbe-ratio.md` Decision item 1 "
        "(issue #208, part of #203). **No spec pass/fail claim**: this is a "
        "measured device input for the next retuning step; no ratified `README.md` "
        "row is touched. It does not replace the historical 4.027 "
        "(single corner, 6.5 uA) or the monolithic 3.634 in "
        "`sim/device-pnp-vbe/`, which stay as recorded."
        + ("" if complete else " **INCOMPLETE -- see Result: failed/missing points.**")
    )
    add(
        "- **Netlist provenance**: schematic-level device testbench "
        "(`sim/device-pnp-array/testbench/tb_pnp_array.spice`); PDK device "
        "models instantiated directly, no `design/` schematic or extracted layout."
    )
    add("- **Corner matrix run**:")
    add(f"  - Process: {', '.join(req.BJT_SECTIONS)} (model `.lib` sections of `sm141064.ngspice`; "
        "only the BJT family is exercised by this DUT, so MOS/resistor/cap skews are not applicable)")
    add("  - Temperature: " + ", ".join(f"{t:g} C" for t in req.TEMPS_C) + " (CLAUDE.md axis; `.temp` in degrees Celsius)")
    add(
        "  - Supply: **not applicable** -- every branch is a grounded-base/collector "
        "diode-connected PNP driven by an ideal current source; there is no supply "
        "rail, so the +/-10% axis has nothing to sweep (device-only subset "
        "justification per `sim/README.md`; corner logs carry `nosupply`)."
    )
    add(f"  - {len(cids)} points expected ({len(req.BJT_SECTIONS)} process x {len(req.TEMPS_C)} temperature); "
        f"{len(points)} returned and parsed. Emitter current swept 4.00..7.00 uA in 0.01 uA steps; "
        f"reported at {', '.join(f'{u:g}' for u in req.CURRENTS_UA)} uA total per branch.")
    add("- **Statistical convention**: N/A -- corner-matrix characterization; mismatch not exercised.")
    add("")
    add("- **Result**:")
    if complete:
        add(f"  - All {len(points)} of {len(cids)} points executed on the fleet and passed; all measurements present.")
    else:
        add("  - **INCOMPLETE.** Failed: " + (", ".join(f"{k} ({s})" for k, s in failed) or "none")
            + ". Missing: " + (", ".join(f"{k} ({why})" for k, why in missing) or "none")
            + ". Problems: " + ("; ".join(problems) or "none") + ".")
    add("")
    d = req.DESIGN_UA
    if points:
        add(f"### A_eff of the 4-unit array at equal total Ie = {d} uA (design current)")
        add("")
        add("| Corner | T (C) | VBE 1x5x5 (V) | VBE 4x5x5 (V) | dVBE (mV) | A_eff array | A_eff monolithic 10x10 | lambda = ln(A_arr)/ln(A_mono) |")
        add("|---|---|---|---|---|---|---|---|")
        arr_vals = []
        for sec in req.BJT_SECTIONS:
            for t in req.TEMPS_C:
                v = points.get((sec, t))
                if not v:
                    add(f"| {sec} | {t:g} | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |")
                    continue
                r = ratios(v, t)[d]
                u, a = v[req.meas_name("u", d)], v[req.meas_name("a", d)]
                arr_vals.append(r["array"])
                add(f"| {sec} | {t:g} | {u:.6f} | {a:.6f} | {(u - a) * 1e3:.3f} | {r['array']:.4f} | "
                    f"{r['mono']:.4f} | {math.log(r['array']) / math.log(r['mono']):.4f} |")
        add("")
        add("### A_eff of the array versus emitter current")
        add("")
        add("| Corner | T (C) | " + " | ".join(f"{u:g} uA" for u in req.CURRENTS_UA) + " |")
        add("|---|---|" + "---|" * len(req.CURRENTS_UA))
        for sec in req.BJT_SECTIONS:
            for t in req.TEMPS_C:
                v = points.get((sec, t))
                if v:
                    r = ratios(v, t)
                    add(f"| {sec} | {t:g} | " + " | ".join(pct(r[u]['array']) for u in req.CURRENTS_UA) + " |")
        add("")
        lo, hi = min(arr_vals), max(arr_vals)
        nom = ratios(points[("bjt_typical", 27.0)], 27.0)[d] if ("bjt_typical", 27.0) in points else None
        add("### Summary for the retuning step")
        add("")
        scope = "over all returned points" if complete else f"over the {len(arr_vals)} returned points ONLY (record incomplete)"
        add(f"- Measured A_eff range at {d} uA {scope}: **{lo:.4f} .. {hi:.4f}** "
            f"(excess over the 4.000 unit-count ratio: {100 * (lo / 4 - 1):+.2f} % .. {100 * (hi / 4 - 1):+.2f} %).")
        if nom:
            add(f"- **Nominal rescaling input** (bjt_typical, 27 C, {d} uA): "
                f"A_array = **{nom['array']:.4f}**; same-bench monolithic A_old = {nom['mono']:.4f}; "
                f"`lambda = ln A_array / ln A_old` = {math.log(nom['array']) / math.log(nom['mono']):.4f} "
                f"(`lambda` against an exact 4.000 would be {math.log(4.0) / math.log(nom['mono']):.4f}).")
            add(f"- dVBE shift of using measured {nom['array']:.4f} instead of 4.000 at 27 C: "
                f"{thermal_voltage(27.0) * math.log(nom['array'] / 4.0) * 1e3:+.3f} mV.")
        add("- Temperature behaviour: see the per-corner table; the array ratio is a "
            "unit-count identity plus an equal-Ie base-current term, so it is nearly flat in T "
            "(DR-0007's argument), unlike the monolithic ratio.")
        add("")
    add("- **Links**:")
    add("  - Testbench: `sim/device-pnp-array/testbench/tb_pnp_array.spice`")
    add("  - Request adapter: `sim/tools/mk_klt_device_request.py`; run script: `sim/device-pnp-array/run_pnp_array.py`")
    add(f"  - Request / report / decks: `sim/device-pnp-array/corners/{record}/request.json`, `report.json`, `<corner-id>.cir`")
    add(f"  - Netlist snapshot: `sim/device-pnp-array/netlist-snapshots/{record}.spice`")
    add(f"  - Raw logs: `sim/device-pnp-array/corners/{record}/`")
    add(f"  - Provenance: klt {prov.get('klt_version')}; engine {env.get('engine')} {env.get('engine_version')}; "
        f"PDK {prov.get('pdk', {}).get('name')} ({prov.get('pdk', {}).get('version')}); "
        f"model deck {prov.get('deck', {}).get('name')} {prov.get('deck', {}).get('content_hash')}; "
        f"netlist sha256 {env.get('netlist_sha256')}")
    if remote:
        add(f"  - Fleet execution: {remote.get('provider')} job `{remote.get('job_id')}`, "
            f"{remote.get('instance_type')} ({remote.get('lifecycle')}) {remote.get('instance_id')}, "
            f"state {remote.get('state')}, exit {remote.get('exit_code')}, {remote.get('elapsed_seconds')} s")
    else:
        add("  - Fleet execution: NOT RECORDED in report (`environment.remote` absent)")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #208)")
    add("- **Supersedes**: (none -- first record for this claim; does not supersede `sim/device-pnp-vbe/` records)")
    add("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-report", metavar="DIR")
    a = ap.parse_args()

    if a.from_report:
        work = Path(a.from_report).resolve()
    else:
        work = Path(tempfile.mkdtemp(prefix="pnp-array-"))
        subprocess.run([sys.executable, str(SIM / "tools" / "mk_klt_device_request.py"), str(work)], check=True)
        dispatch(work)
    report = json.loads((work / "report.json").read_text())
    expected = req.expected_points()
    points, missing, failed, problems, keyed_rows = collect(report, expected)

    git = hreport.git_provenance(hreport.REPO_ROOT) if hasattr(hreport, "REPO_ROOT") else hreport.git_provenance(SIM.parent)
    record = hreport.allocate_record_id(SIM.parent, HERE / "records", git=git)
    stamp = hreport.record_stamp(record)
    cids = [hcorners.device_corner_id(s, t) for s, t in expected]

    cdir = HERE / "corners" / record
    cdir.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for (sec, t), c in keyed_rows:
        cid = hcorners.device_corner_id(sec, t)
        if cid in written:
            continue  # duplicate id: the first entry owns the log (problem already recorded)
        written.add(cid)
        src_dir = work / "out" / f"{sec}_novdd_{('n' + format(abs(t), 'g') if t < 0 else format(t, 'g'))}C"
        header = (f"* record-id : {record}\n* klt corner : {c['corner_id']} (status {c.get('status')})\n"
                  f"* supply    : n/a (no supply rail)\n")
        log = src_dir / "ngspice.log"
        (cdir / f"{cid}.log").write_text(header + (log.read_text() if log.exists() else "(no ngspice.log returned)\n"))
        if (src_dir / "corner.cir").exists():
            shutil.copyfile(src_dir / "corner.cir", cdir / f"{cid}.cir")
    for name in ("request.json", "report.json"):
        shutil.copyfile(work / name, cdir / name)

    body = (work / "body.spice").read_text().replace(
        f'.include "{req.BENCH_DIR / req.BENCH}"',
        (req.BENCH_DIR / req.BENCH).read_text(),
    )
    hreport.write_snapshot_text(HERE / "netlist-snapshots", record, body)

    path = hreport.device_write_record(
        HERE / "records", record,
        build_record(record, stamp, report, points, missing, failed, problems, cids)
    )
    print(f"wrote {path} ({len(points)}/{len(cids)} points; missing={missing} failed={failed} problems={problems})")
    return 0 if not (missing or failed or problems) else 2


if __name__ == "__main__":
    raise SystemExit(main())
