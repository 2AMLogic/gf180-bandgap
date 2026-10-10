#!/usr/bin/env python3
"""Ingest a finished fleet `klt sim` run of output-load-sensitivity (#269).

CHARACTERIZATION ONLY. This bench answers "how far does v(vref) of the
current, unbuffered DUT move when DC current is drawn from it", to inform the
operator's open A7 (Load row: buffered vs explicitly high-Z) and A4 (PSRR
load condition) decisions -- `spec/tbd-row-evidence.md` Row 3. It carries no
spec threshold, rates no load and selects no output stage, so its verdict
is never PASS/FAIL: a run is **COMPLETE** (every expected corner returned a
valid, resolved sweep) or **INCOMPLETE** (it did not; nothing is claimed).
The sweep span is an *exploratory measurement range*, never a supported-load
range.

Conventions shared with `sim/tools/fleet_ingest.py` (and reused from it):

* completeness against the expected P x V x T grid (tb.json + corners.py):
  a missing corner, backend error, null / non-finite value, hash or version
  mismatch is a defect, never silently dropped;
* append-only evidence: record, frozen deck, per-corner logs in the
  `<process>_<T>c_<V>v.log` / `m_<name> = <value>` shape, request/report
  copies, the sweep series;
* recorded identity: DUT path + provenance class + sha256, testbench and
  tb.json hashes, the frozen deck / request hashes, submitting and worker klt
  versions.

Per-corner validity (any failure -> the corner is INVALID, its numbers are
not used, and the run is INCOMPLETE):

* the waveform has the sweep axis, v(vref), v(vdd) and i(<sense>) columns,
  all finite and of equal length;
* the axis is the manifest's grid exactly -- point count (a short sweep is an
  *incomplete sweep*), uniform step, endpoints;
* an unloaded baseline point at exactly 0 A exists (never interpolated);
* enough points either side of 0 A for the step-refinement slope check
  (*insufficient resolution* otherwise);
* the measured load current i(<sense>) equals the sweep value at every point
  -- the sign/units check of the "positive = sunk out of vref" convention;
* v(vdd) is the corner's supply (the `alter vsup` took effect);
* the central-difference slope at 0 A is stable under step refinement;
* the fleet `.meas` min/max of v(vref) agree with the waveform at ngspice's
  print precision.

    python3 sim/tools/mk_klt_fleet_request.py output-load-sensitivity WORK [--dut PATH]
    klt sim --backend batch -o WORK/sweep/out WORK/sweep/request.json --format json > WORK/sweep/report.json
    python3 sim/tools/load_ingest.py WORK [--dut PATH] [--dry-run]

The pure functions (`derive_load`, `assess`, `build_record`, `write_evidence`)
are unit tested in `sim/tests/test_load_ingest.py` with no PDK, ngspice,
fleet or network.
"""

from __future__ import annotations

import argparse
import gzip
import json
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
import fleet_ingest as fi  # noqa: E402
import mk_klt_fleet_request as mk  # noqa: E402

BENCH = mk.LOAD_BENCH
REQUEST = "sweep"
COMPLETE, INCOMPLETE = "COMPLETE", "INCOMPLETE"
#: Per-corner columns of the record table, in order (all from `derive_load`).
TABLE = ("vref_unloaded_v", "slope_mv_per_ua", "zout_kohm", "slope_step_spread_pct", "nonlin_max_mv")


def current_tag(i: float) -> str:
    """-1e-6 -> 'source_1u', 5e-7 -> 'sink_500n' (measurement-name safe)."""
    side = "sink" if i > 0 else "source"
    a = abs(i)
    mag = f"{a * 1e6:g}u" if a >= 1e-6 * (1 - 1e-9) else f"{a * 1e9:g}n"
    return f"{side}_{mag.replace('.', 'p')}"


def shift_name(i: float) -> str:
    return f"shift_mv_{current_tag(i)}"


def _close(a: float, b: float, rel: float, abs_: float) -> bool:
    return abs(a - b) <= rel * max(abs(a), abs(b)) + abs_


# --------------------------------------------------------------------------
# per-corner derivation
# --------------------------------------------------------------------------


def derive_load(vals: dict | None, wave: dict | None, spec: dict, supply: float):
    """-> (measures, errs). ``spec`` is :func:`mk.load_sweep_spec`; ``vals``
    the unit's fleet `.meas` values (cross-check only). Any ``errs`` entry
    makes the corner INVALID; ``measures`` is ``None`` when nothing could be
    derived at all."""
    errs: list[str] = []
    if wave is None:
        return None, ["no dc waveform returned: load sweep not evaluable"]
    try:
        x = list(next(iter(wave.values())))  # klt waveform contract: variables[0] is the sweep variable
        if not all(fc.is_finite_number(v) for v in x):
            raise ValueError("non-finite sweep axis")
        vref = fi.column(wave, "v(vref)", "vref")
        vdd = fi.column(wave, "v(vdd)", "vdd")
        isense = fi.column(wave, f"i({spec['sense']})")
    except (ValueError, StopIteration) as exc:
        return None, [f"dc waveform unusable: {exc}"]
    n = len(x)
    if not (len(vref) == len(vdd) == len(isense) == n):
        return None, ["waveform columns are ragged (sweep axis, v(vref), v(vdd), sense current differ in length)"]
    if n < 3:
        return None, [f"incomplete sweep: {n} point(s)"]
    if any(b <= a for a, b in zip(x, x[1:])):
        return None, ["sweep axis is not strictly increasing"]

    step = spec["step"]
    tol = mk.GRID_TOL * step
    # -- the unloaded baseline: a grid point at exactly 0 A, never interpolated
    k0 = min(range(n), key=lambda i: abs(x[i]))
    if abs(x[k0]) > tol:
        return None, [f"missing baseline: no sweep point at 0 A (nearest {x[k0]:.4g} A); the unloaded vref "
                      "is never interpolated"]
    # -- resolution around the baseline (from the axis actually returned)
    below, above = k0, n - 1 - k0
    need = max(spec["min_points_each_side"], max(spec["slope_steps"]))
    if below < need or above < need:
        errs.append(f"insufficient resolution: {below} / {above} point(s) below / above 0 A, the slope "
                    f"step-refinement check needs >= {need} each side")
    # -- the grid is the manifest's grid
    if n != spec["n_points"]:
        kind = "incomplete sweep" if n < spec["n_points"] else "unexpected sweep"
        errs.append(f"{kind}: {n} of the manifest's {spec['n_points']} points returned")
    if any(abs((b - a) - step) > tol for a, b in zip(x, x[1:])):
        errs.append(f"sweep axis is not uniform at the manifest's {step:g} A step (insufficient resolution if coarser)")
    if abs(x[0] - spec["lo"]) > tol or abs(x[-1] - spec["hi"]) > tol:
        errs.append(f"sweep axis spans {x[0]:.4g}..{x[-1]:.4g} A, not {spec['lo']:g}..{spec['hi']:g} A")
    # -- sign / units: the measured load current is the swept value
    bad = [i for i in range(n) if not _close(isense[i], x[i], spec["sense_rel_tol"], spec["sense_abs_tol"])]
    if bad:
        reversed_ = all(_close(isense[i], -x[i], spec["sense_rel_tol"], spec["sense_abs_tol"]) for i in range(n))
        errs.append(("load current direction is REVERSED: i(sense) = -iload" if reversed_ else
                     f"measured load current disagrees with the sweep at {len(bad)} point(s) "
                     f"(first: i={isense[bad[0]]:.6g} A at iload={x[bad[0]]:.6g} A)") + " -- sign/units check")
    # -- the corner's supply really applied
    if any(not _close(v, supply, spec["supply_rel_tol"], 0.0) for v in vdd):
        errs.append(f"v(vdd) is {min(vdd):.6g}..{max(vdd):.6g} V, not the corner's {supply:.4f} V supply")

    v0 = vref[k0]
    m: dict[str, float] = {
        "vref_unloaded_v": v0,
        "sweep_points": float(n),
        "i_lo_ua": x[0] * 1e6,
        "i_hi_ua": x[-1] * 1e6,
        "vdd_v": vdd[k0],
        "vref_min_v": min(vref),
        "vref_max_v": max(vref),
    }
    # -- slope at zero load: central differences, step refinement
    slopes = {}
    for mstep in spec["slope_steps"]:
        if k0 - mstep >= 0 and k0 + mstep < n:
            slopes[mstep] = (vref[k0 + mstep] - vref[k0 - mstep]) / (x[k0 + mstep] - x[k0 - mstep])
    if 1 not in slopes:
        errs.append("slope at 0 A not computable: no grid point on one side of the baseline")
    else:
        s1 = slopes[1]
        m["slope_mv_per_ua"] = s1 * 1e-3  # V/A -> mV/uA
        m["zout_kohm"] = -s1 * 1e-3
        for mstep, s in slopes.items():
            if mstep != 1:
                m[f"slope_x{mstep}_mv_per_ua"] = s * 1e-3
        denom = max(abs(s1), spec["slope_abs_floor"])
        spread = max((abs(s - s1) / denom for s in slopes.values()), default=0.0)
        m["slope_step_spread_pct"] = spread * 100.0
        if len(slopes) < len(spec["slope_steps"]):
            errs.append("slope step-refinement check incomplete: too few points around 0 A (insufficient resolution)")
        elif spread > spec["slope_rel_tol"]:
            errs.append(f"slope at 0 A not resolved: central differences over {sorted(slopes)} grid steps spread "
                        f"{spread * 100:.3g} % > {spec['slope_rel_tol'] * 100:g} % (step-size check)")
        if k0 + 1 < n:
            m["slope_sink_side_mv_per_ua"] = (vref[k0 + 1] - v0) / (x[k0 + 1] - x[k0]) * 1e-3
        if k0 >= 1:
            m["slope_source_side_mv_per_ua"] = (v0 - vref[k0 - 1]) / (x[k0] - x[k0 - 1]) * 1e-3
        dev = [abs(vref[i] - v0 - s1 * x[i]) for i in range(n)]
        j = max(range(n), key=dev.__getitem__)
        m["nonlin_max_mv"] = dev[j] * 1e3
        m["nonlin_at_ua"] = x[j] * 1e6
    m["monotonic"] = 1.0 if (all(b < a for a, b in zip(vref, vref[1:])) or all(b > a for a, b in zip(vref, vref[1:]))) else 0.0
    # -- signed shifts at the report points (on-grid only)
    for i in spec["report_points"]:
        j = min(range(n), key=lambda q: abs(x[q] - i))
        if abs(x[j] - i) > tol:
            errs.append(f"report point {i:g} A is not on the returned sweep")
            continue
        m[shift_name(i)] = (vref[j] - v0) * 1e3
    # -- `.meas` cross-check at print precision
    for name, full in (("vref_min", m["vref_min_v"]), ("vref_max", m["vref_max_v"])):
        if vals is not None and name in vals and not fi.meas_agrees(vals[name], full):
            errs.append(f"{name} {vals[name]:.9f} (.meas) disagrees with the waveform's {full:.9f} "
                        "beyond ngspice's 7-digit print precision")
    return m, errs


# --------------------------------------------------------------------------
# run assessment
# --------------------------------------------------------------------------


def assess(tb: dict, plan: dict, reports: dict, work: Path, *, dut_sha: str | None = None,
           dut_label: str | None = None, decks: dict | None = None, manifest_sha: str | None = None,
           tb_sha: str | None = None, require_remote: bool = True, requests: dict | None = None) -> dict:
    """Judge one fleet run from its plan and klt reports (``{request: report}``).

    Never raises on bad evidence: every defect lands in ``problems`` (run-level:
    manifest, plan, provenance, hashes), ``missing`` / ``failed`` (units) or
    ``invalid`` (corners), and keeps the run INCOMPLETE."""
    grid = fi.expected_grid(tb)
    problems: list[str] = []
    try:
        spec = mk.load_sweep_spec(tb)
    except (ValueError, KeyError, TypeError) as exc:
        spec = None
        problems.append(f"tb.json load_sweep unusable: {exc}")
    problems += fi.plan_problems(BENCH, tb, plan)
    if not plan.get("scope", "").startswith("characterization-only"):
        problems.append("plan does not declare the characterization-only scope")
    req = next((r for r in plan.get("requests", []) if r.get("name") == REQUEST), None)
    if spec is not None and req is not None and req.get("load_sweep") != spec:
        problems.append("plan load_sweep differs from tb.json (manifest edited after the request was generated?)")
    pdut = plan.get("dut", {})
    if dut_label is not None and pdut.get("path") != dut_label:
        problems.append(f"DUT path {dut_label!r} differs from the plan's {pdut.get('path')!r}")
    if pdut.get("provenance_class") != mk.dut_provenance_class(str(pdut.get("path", ""))):
        problems.append("plan DUT provenance class does not match its path")
    decks = decks or {}
    if dut_sha is not None or manifest_sha or tb_sha:
        problems += fc.hash_problems(
            plan, dut_sha=dut_sha, tb_sha=tb_sha or plan.get("tb_netlist_sha256"),
            manifest_sha=manifest_sha or plan.get("manifest_sha256"),
            deck_sha={n: fc.sha256_bytes(t.encode()) for n, t in decks.items()} or
                     {r["name"]: r["deck_sha256"] for r in plan.get("requests", [])},
            requests=requests,
        )
    for n, text in decks.items():
        problems += fi.deck_problems(BENCH, plan, text, n)

    missing: list = []
    failed: list = []
    pts: dict = {}
    corners_of: dict = {}
    if req is not None:
        rep = reports.get(REQUEST)
        if rep is None:
            missing += [((REQUEST,) + k, "no report.json for this request") for k in fi._expected_keys(req)]
        else:
            problems += [f"{REQUEST}: {p}" for p in fc.provenance_problems(rep, plan, require_remote=require_remote)]
            pts, mi, fa, pr = fc.collect_units(rep, fi._expected_keys(req), req["measurements"], fi._unit_key(req))
            missing += [((REQUEST,) + k, why) for k, why in mi]
            failed += [((REQUEST,) + k, why) for k, why in fa]
            problems += [f"{REQUEST}: {x}" for x in pr]
            for c in rep.get("corners", []):
                try:
                    corners_of[(REQUEST, fi._unit_key(req)(c["corner_id"]))] = c
                except Exception:
                    pass

    rows: dict = {}
    invalid: dict = {}
    series: dict = {}
    for key in grid:
        proc, temp, sup = key
        ukey = (proc, round(sup, 4), temp)
        u = pts.get(ukey)
        if spec is None:
            invalid[key] = "no usable load_sweep definition"
            continue
        if u is None:
            invalid[key] = "sweep unit unavailable (missing, failed or non-finite)"
            continue
        w = fi.read_waveform_for(corners_of.get((REQUEST, ukey)), work)
        try:
            derived, errs = derive_load(u, w, spec, sup)
        except Exception as exc:  # fail closed: a derivation bug is INVALID, not a crash
            derived, errs = None, [f"derivation error: {type(exc).__name__}: {exc}"]
        if w is not None:
            try:
                series[key] = {"iload_a": list(next(iter(w.values()))), "v(vref)": fi.column(w, "v(vref)", "vref")}
            except (ValueError, StopIteration):
                pass
        if derived is None:
            invalid[key] = "; ".join(errs) or "no data"
            continue
        rows[key] = {"measures": derived, "errs": errs}
        if errs:
            invalid[key] = "; ".join(errs)

    incomplete = bool(problems or missing or failed or invalid)
    return {
        "bench": BENCH, "overall": INCOMPLETE if incomplete else COMPLETE, "grid": grid, "rows": rows,
        "invalid": invalid, "missing": missing, "failed": failed, "problems": problems, "series": series,
        "spec": spec, "corners_of": {f"{a}|{b}": c for (a, b), c in corners_of.items()},
    }


def extremes(result: dict) -> dict:
    """{measure: ((min, key), (max, key))} over the VALID corners only --
    descriptive range of the characterization, not a worst case against any
    limit (there is none)."""
    out = {}
    valid = {k: r for k, r in result["rows"].items() if k not in result["invalid"]}
    names = list(TABLE) + [shift_name(i) for i in (result.get("spec") or {}).get("report_points", [])]
    for name in names:
        vals = [(r["measures"][name], k) for k, r in valid.items() if name in r["measures"]]
        if vals:
            out[name] = (min(vals), max(vals))
    return out


# --------------------------------------------------------------------------
# evidence writing (sim/README.md conventions)
# --------------------------------------------------------------------------


def _f(x, n=6):
    return "-" if x is None else f"{x:.{n}g}"


def build_record(record: str, stamp: datetime, tb: dict, plan: dict, result: dict, reports: dict,
                 issue, supersedes, note, git=None) -> str:
    overall = result["overall"]
    spec = result.get("spec") or {}
    pdut = plan["dut"]
    req = next(r for r in plan["requests"] if r["name"] == REQUEST)
    L: list[str] = []
    add = L.append
    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add("- **Claim**: CHARACTERIZATION ONLY -- no ratified spec row is claimed and no pass/fail is stated. "
        "Output-load sensitivity of the DUT named below: unloaded v(vref), signed shifts and the slope at zero "
        "load for a DC current drawn from vref, as diagnostic input to the operator's open Load-row (A7) and "
        "PSRR-load-condition (A4) decisions (`spec/tbd-row-evidence.md` Row 3). The sweep span is an "
        "**exploratory measurement range, not a supported-load rating**; nothing here sets a limit, rates a load "
        f"or selects an output stage. Fleet (`klt sim`) evidence for issue #{issue}."
        + ("" if overall != INCOMPLETE else " **INCOMPLETE -- see Result: nothing is characterized by this record.**"))
    add(f"- **Netlist provenance**: {pdut.get('provenance_class', mk.dut_provenance_class(pdut['path']))}. "
        f"DUT `{pdut['path']}` sha256 `{pdut['sha256']}`; testbench sha256 `{plan['tb_netlist_sha256']}`; "
        f"tb.json sha256 `{plan['manifest_sha256']}`.")
    add(f"  - frozen fleet deck `{REQUEST}` sha256 `{req['deck_sha256']}` (`netlist-snapshots/{record}.spice`); "
        f"request sha256 `{req['request_sha256']}`")
    add(f"  - Scope: {plan.get('scope')}. The record describes this DUT only; it says nothing about any other "
        "netlist (schematic vs extracted are separate records).")
    add("- **Corner matrix run**:")
    procs = sorted({k[0] for k in result["grid"]}, key=[k[0] for k in result["grid"]].index)
    add(f"  - Process: {', '.join(procs)}")
    add(f"  - Temperature: {', '.join(f'{t:g}' for t in tb['temperatures_c'])} C")
    add("  - Supply: " + ", ".join(f"{v:.2f} V" for v in plan["supplies_v"]) + " (`alter vsup`)")
    if spec:
        add(f"  - Load current (internal `dc {spec['source']}` sweep, every corner): {spec['lo'] * 1e6:g} .. "
            f"{spec['hi'] * 1e6:g} uA in {spec['step'] * 1e9:g} nA steps ({spec['n_points']} points) -- "
            "EXPLORATORY MEASUREMENT RANGE, not a supported-load rating")
    nvalid = len(result["rows"]) - len(result["invalid"].keys() & result["rows"].keys())
    add(f"  - {len(result['grid'])} corners expected; {nvalid} valid; {len(result['invalid'])} invalid/unavailable; "
        f"{len(result['missing'])} unit(s) missing, {len(result['failed'])} failed/errored.")
    add("- **Statistical convention**: N/A (corner-matrix characterization, not a distribution claim)")
    add("- **Result**:")
    add("  - Convention (tb.json `load_sweep`): positive load current = current SUNK out of vref into vss; "
        "shifts are signed, `shift_mv(I) = (v(vref)(I) - v(vref)(0 A)) * 1000` (negative = vref fell); "
        "`slope_mv_per_ua` = central-difference dV/dI_sink at exactly 0 A over one grid step (numerically kOhm), "
        "`zout_kohm` = -slope; `slope_step_spread_pct` = its spread over "
        f"{spec.get('slope_steps', '?')} grid steps; `nonlin_max_mv` = largest departure from the zero-load "
        "tangent over the sweep. All figures come from the full-precision returned waveform; the measured "
        "load current was checked equal to the swept value at every point (sign/units).")
    add("  - **No threshold is applied to any of these numbers.** They are not compared with the accuracy "
        "window or any load budget; that comparison is the operator's, in the A7/A4 decision records.")
    if overall == INCOMPLETE:
        add("  - **INCOMPLETE.**")
        for k, why in result["missing"]:
            add(f"    - missing {k}: {why}")
        for k, why in result["failed"]:
            add(f"    - failed {k}: {why}")
        for k, why in result["invalid"].items():
            add(f"    - invalid `{fi.corner_id(k)}`: {why}")
        for p in result["problems"]:
            add(f"    - problem: {p}")
    if note:
        add(f"  - {note}")
    add("")
    shifts = [shift_name(i) for i in spec.get("report_points", [])]
    cols = list(TABLE) + shifts
    add("  | corner-id | " + " | ".join(cols) + " | state |")
    add("  |---|" + "---|" * (len(cols) + 1))
    for key in result["grid"]:
        row = result["rows"].get(key)
        if row is None or key in result["invalid"]:
            add(f"  | `{fi.corner_id(key)}` | " + " | ".join("-" for _ in cols) + " | **INVALID** |")
            continue
        add(f"  | `{fi.corner_id(key)}` | " + " | ".join(_f(row["measures"].get(c)) for c in cols) + " | valid |")
    add("")
    ex = extremes(result)
    if ex:
        scope = "all corners" if overall != INCOMPLETE else "the valid corners ONLY (record incomplete)"
        add(f"  Observed range over {scope} (descriptive; not a worst case against any limit -- none exists):")
        add("")
        for name, ((lo, klo), (hi, khi)) in ex.items():
            add(f"  - `{name}`: {lo:.6g} (`{fi.corner_id(klo)}`) .. {hi:.6g} (`{fi.corner_id(khi)}`)")
        add("")
    add(f"  - **Overall: {overall}** (characterization: COMPLETE / INCOMPLETE only, never PASS / FAIL)")
    add("- **Links**:")
    add(f"  - Testbench: `sim/{BENCH}/testbench/{tb['netlist']}`, `sim/{BENCH}/testbench/tb.json`; "
        f"how to read it: `sim/{BENCH}/README.md`")
    add(f"  - Raw logs: `sim/{BENCH}/corners/{record}/` (also `plan.json`, `request-{REQUEST}.json`, "
        f"`report-{REQUEST}.json`, `<corner-id>.series.json.gz`)")
    add("  - Request adapter: `sim/tools/mk_klt_fleet_request.py`; ingestion: `sim/tools/load_ingest.py`")
    add("  - Decision context: `spec/tbd-row-evidence.md` Row 3 (A7) and Row 1 (A4)")
    for name, rep in reports.items():
        remote = (rep.get("environment") or {}).get("remote") or {}
        if remote:
            add(f"  - Fleet execution `{name}`: {remote.get('provider')} job `{remote.get('job_id')}`, "
                f"{remote.get('instance_type')} ({remote.get('lifecycle')}), state {remote.get('state')}, "
                f"exit {remote.get('exit_code')}")
        else:
            add(f"  - Fleet execution `{name}`: NOT RECORDED in the report (`environment.remote` absent)")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #{issue})")
    add(f"- **Supersedes**: {supersedes or '(none)'}")
    add("")
    add("## Environment")
    add("")
    for name, rep in reports.items():
        remote = (rep.get("environment") or {}).get("remote") or {}
        prov = rep.get("provenance") or {}
        env = rep.get("environment") or {}
        add(f"- `{name}`: submitting klt {remote.get('client_klt_version')}, worker klt {remote.get('runner_klt_version')} "
            f"(compatibility: {remote.get('runner_compatibility')}); report provenance klt {prov.get('klt_version')}; "
            f"engine {env.get('engine')} {env.get('engine_version')}; PDK {(prov.get('pdk') or {}).get('name')} "
            f"({(prov.get('pdk') or {}).get('version')})")
    add(f"- plan submitting klt: {plan.get('submitting_klt_version')}")
    if git:
        add(f"- git: `{git.get('commit', git.get('short'))}` on `{git.get('branch')}`"
            f"{' (dirty working tree at ingest; the frozen deck, not the tree, is the evidence)' if git.get('dirty') else ''}")
    add("")
    add("---")
    add("")
    add("Written by `sim/tools/load_ingest.py`. Append-only: never edit or delete this file -- a re-run or "
        "correction mints a new record-id and points back here via **Supersedes** (see `sim/README.md`).")
    add("")
    return "\n".join(L)


def write_evidence(exp_dir: Path, work: Path, tb: dict, plan: dict, result: dict, reports: dict, *, issue,
                   supersedes=None, note=None, git=None, repo: Path = REPO, stamp: datetime | None = None) -> Path:
    """Write record + logs + frozen deck + request/report copies under
    ``exp_dir`` (``sim/output-load-sensitivity``; a temp dir in tests).

    Refuses (ValueError, nothing written) when the run has a run-level
    problem -- a provenance, hash, plan or manifest mismatch -- because such a
    record could not identify the exact DUT and scope it describes. Missing or
    invalid corners alone are recorded, as INCOMPLETE, so a failed attempt
    stays visible. Refuses to overwrite (append-only)."""
    if result["problems"]:
        raise ValueError("refusing to mint evidence with run-level problems: " + "; ".join(result["problems"][:5]))
    from harness import report as hreport

    git = git or hreport.git_provenance(repo)
    record = hreport.allocate_record_id(repo, exp_dir / "records", when=stamp, git=git)
    st = datetime.strptime(record[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    cdir = exp_dir / "corners" / record
    # Per-corner logs in the suite-readable shape. The sweep series go FLAT in
    # corners/<record-id>/ (`<corner-id>.series.json.gz`): the evidence linter
    # (sim/harness/evidence_lint.py) allows one directory level under corners/.
    fi.write_corner_logs(cdir, work, plan, dict(result, series={}), record)
    for key, cols in result["series"].items():
        with gzip.open(cdir / f"{fi.corner_id(key)}.series.json.gz", "wt") as fh:
            json.dump(cols, fh)
    shutil.copyfile(work / "plan.json", cdir / "plan.json")
    shutil.copyfile(work / REQUEST / "request.json", cdir / f"request-{REQUEST}.json")
    if REQUEST in reports:
        (cdir / f"report-{REQUEST}.json").write_text(json.dumps(reports[REQUEST], indent=2) + "\n")
    snap = exp_dir / "netlist-snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    target = snap / f"{record}.spice"
    if target.exists():
        raise RuntimeError(f"{target} exists (append-only)")
    shutil.copyfile(work / REQUEST / "body.spice", target)
    text = build_record(record, st, tb, plan, result, reports, issue, supersedes, note, git)
    return hreport.device_write_record(exp_dir / "records", record, text)


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workdir", help="dir written by mk_klt_fleet_request.py output-load-sensitivity, "
                                    "with sweep/report.json added")
    ap.add_argument("--dut", default="sim/dut/bandgap_top.spice", help="DUT the request was built from (repo-relative)")
    ap.add_argument("--issue", default="269")
    ap.add_argument("--supersedes", default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the outcome, write nothing")
    a = ap.parse_args()

    work = Path(a.workdir).resolve()
    tb = fi.load_tb(BENCH)
    plan, reports, decks, requests = fi.load_work(work)
    dut = (Path(a.dut) if Path(a.dut).is_absolute() else REPO / a.dut).resolve()
    try:
        label = str(dut.relative_to(REPO))  # the form mk_klt_fleet_request.py froze into the plan
    except ValueError:
        label = str(dut)
    result = assess(
        tb, plan, reports, work, dut_sha=fc.sha256_file(dut), dut_label=label, decks=decks, requests=requests,
        manifest_sha=fc.sha256_file(SIM / BENCH / "testbench" / "tb.json"),
        tb_sha=fc.sha256_file(SIM / BENCH / "testbench" / tb["netlist"]),
    )
    print(f"overall={result['overall']} valid={len(result['rows']) - len(result['invalid'].keys() & result['rows'].keys())}"
          f"/{len(result['grid'])} missing={len(result['missing'])} failed={len(result['failed'])} "
          f"invalid={len(result['invalid'])} problems={len(result['problems'])}")
    for p in result["problems"][:10]:
        print("  problem:", p)
    if a.dry_run:
        return 0 if result["overall"] == COMPLETE else 2
    try:
        path = write_evidence(SIM / BENCH, work, tb, plan, result, reports, issue=a.issue,
                              supersedes=a.supersedes, note=a.note)
    except ValueError as exc:
        print(f"NOT written: {exc}")
        return 2
    print(f"wrote {path}")
    return 0 if result["overall"] == COMPLETE else 2


if __name__ == "__main__":
    raise SystemExit(main())
