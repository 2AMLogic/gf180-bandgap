#!/usr/bin/env python3
"""Ingest finished fleet `klt sim` runs of psrr-dc / line-regulation / startup (#237) and output-noise (#268).

Sibling of `sim/tools/tc_ingest.py` and following its conventions:

* completeness against the expected PVT matrix (from the bench's own tb.json +
  `sim/harness/corners.py`): a missing corner, a backend error, a null /
  non-finite measurement, an inconsistent sweep, a hash or version mismatch is
  INCOMPLETE -- never silently dropped, never an invented PASS;
* thresholds are read from tb.json unchanged (`tb["checks"]`);
* append-only evidence: record, frozen deck(s), per-corner logs in the
  `<process>_<T>c_<V>v.log` / `m_<name> = <value>` shape that `sim/suite/`
  reads, request/report copies, the series the verdict was computed from;
* recorded provenance: canonical DUT hash, the frozen deck hash(es), the
  submitting and worker klt versions.

    python3 sim/tools/mk_klt_fleet_request.py psrr-dc WORK        # 1. requests
    klt sim --backend batch -o WORK/ac/out WORK/ac/request.json --format json > WORK/ac/report.json
    klt sim --backend batch -o WORK/op/out WORK/op/request.json --format json > WORK/op/report.json
    python3 sim/tools/fleet_ingest.py psrr-dc WORK [--dry-run]    # 3. ingest

The pure functions (`assess_bench`, `derive_*`, `write_evidence`) are unit
tested in `sim/tests/test_fleet_ingest.py` with no PDK, ngspice, fleet or
network.

Verdict semantics (same as the harness, nothing relaxed): a tb.json check that
is a ratified spec limit (SPEC_CHECKS) and fails is FAIL; a tb.json *sanity*
check that fails (operating point, frequency index, sweep endpoints/points,
vdd reaching the requested rail) means the number is uninterpretable, so the
corner is INVALID and the bench INCOMPLETE -- the per-corner log then carries
the harness' INVALID POINT trailer so `sim/suite/` reads it as NO DATA.

output-noise (MEASUREMENT_BENCHES) has no ratified threshold (A6 open): its
overall verdict is ``MEASURED`` (every corner of every request came back
valid, unit-checked and identity-checked) or ``INCOMPLETE`` -- never PASS or
FAIL. Conversions are tb.json's own (#252: scale only, no square root), read
through ``plan["noise"]`` (``mk_klt_fleet_request.noise_spec``): the fleet
returns raw SI values and this module multiplies by tb.json's scale. A corner
is INVALID when a noise request reports ``sqrnoise`` set, the wrong sweep
point count, an integrated-noise artifact that is not amplitude-mode
(``Integrated Noise`` / type ``voltage``), a reported unit other than the
plan's, or a waveform/expr disagreement beyond print precision.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
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

BENCHES = ("psrr-dc", "line-regulation", "startup")
NOISE_BENCH = "output-noise"
#: No ratified threshold: verdict is MEASURED / INCOMPLETE, never PASS / FAIL.
MEASUREMENT_BENCHES = (NOISE_BENCH,)
MEASURED = "MEASURED"
INVALID_POINT_MARKER = "*** sim/harness: INVALID POINT"  # mirrors harness.runner / suite.analysis

#: tb.json checks that are ratified-spec limits. Every other tb.json check is
#: a sanity check on the measurement itself. (A test pins these to the suite's
#: gated limits so the two cannot drift apart.)
SPEC_CHECKS = {
    "psrr-dc": {"psrr_1hz_db", "psrr_1khz_db"},
    "line-regulation": {"linereg_mv_per_v", "vref_min", "vref_max"},
    "startup": {"startup_time_s"},
    NOISE_BENCH: frozenset(),  # A6 threshold open: every tb.json check is a sanity check
}

PSRR_TAGS = ("1hz", "10hz", "100hz", "1khz", "10khz", "100khz", "1mhz")
LINEREG_REQUIRED = ("vref_min", "vref_max", "v_lo_check", "v_hi_check")
#: .meas vs waveform cross-check tolerance. klt reads `.meas` results from
#: ngspice's stdout line, which ngspice prints with `%e` (7 significant
#: digits), while the waveform comes from the rawfile at ~16 digits. A
#: correctly rounded 7-digit print is within 0.5 ulp of the 7th digit, i.e.
#: <= 5e-7 relative; MEAS_REL_TOL = 1e-6 (one unit in the 7th digit) covers
#: that with a factor-2 margin and nothing more. MEAS_ABS_TOL only guards
#: values at/near zero. Gated values never come from `.meas` when a waveform
#: is available; this is a consistency check only.
MEAS_REL_TOL = 1e-6
MEAS_ABS_TOL = 1e-12


def meas_agrees(meas: float, full: float) -> bool:
    """True when a printed `.meas` value is the full-precision ``full`` up to
    ngspice's 7-significant-digit print rounding."""
    return abs(meas - full) <= MEAS_REL_TOL * max(abs(meas), abs(full)) + MEAS_ABS_TOL
STARTUP_REACH_TOL = 1e-3  # relative: vdd_final must be the requested rail


def load_tb(bench: str) -> dict:
    return json.loads((SIM / bench / "testbench" / "tb.json").read_text())


def harness_key(process: str, temp: float, supply: float) -> tuple[str, float, float]:
    return (process, float(temp), round(float(supply), 4))


def corner_id(key) -> str:
    p, t, v = key
    return f"{p}_{t:g}c_{v:.2f}v"


def expected_grid(tb: dict) -> list[tuple[str, float, float]]:
    """The harness' own P x V x T grid for this bench (corner ids as the suite expects)."""
    grid = hc.build_grid(
        hc.resolve_corners(tb["corners"]),
        tb["temperatures_c"],
        hc.supply_points(tb["nominal_supply_v"], tb.get("supply_tolerance", 0.0)),
    )
    return [harness_key(p.corner.name, p.temp_c, p.vdd) for p in grid]


def check_ok(spec: dict, value: float) -> bool:
    return ("min" not in spec or value >= spec["min"]) and ("max" not in spec or value <= spec["max"])


# --------------------------------------------------------------------------
# waveforms (klt `options.waveforms` -> artifacts.waveform JSON)
# --------------------------------------------------------------------------


def read_waveform(path: Path) -> dict[str, list[float]]:
    """{variable name: [values]} from klt's waveform JSON (``variables`` +
    row-major ``points``). Raises ValueError on a malformed file; non-finite
    values are rejected by the callers for the columns they use."""
    doc = json.loads(Path(path).read_text())
    names = [v["name"] for v in doc["variables"]]
    pts = doc["points"]
    if not pts or any(len(r) != len(names) for r in pts):
        raise ValueError("waveform has no points or ragged rows")
    return {n: [r[i] for r in pts] for i, n in enumerate(names)}


def column(wave: dict, *candidates: str) -> list[float]:
    """First matching column among ``candidates`` (names are case-insensitive;
    ``i(x)`` also matches ngspice's ``x#branch`` spelling)."""
    low = {k.lower(): k for k in wave}
    for cand in candidates:
        for form in (cand, cand.replace("i(", "").rstrip(")") + "#branch" if cand.startswith("i(") else cand):
            k = low.get(form.lower())
            if k is not None:
                col = wave[k]
                if not all(fc.is_finite_number(x) for x in col):
                    raise ValueError(f"non-finite values in waveform column {k!r}")
                return col
    raise ValueError("waveform lacks column " + " / ".join(candidates))


# --------------------------------------------------------------------------
# per-bench derivation: klt measurements (+ waveform) -> the bench's measures
# --------------------------------------------------------------------------


def derive_psrr(ac_vals: dict, wave: dict | None, op_vals: dict | None, supply_index: int, tb: dict):
    """-> (measures, errs). PSRR(f) = -vdb(v(vref)) for the 1 V supply perturbation."""
    errs: list[str] = []
    m: dict[str, float] = {}
    for tag in PSRR_TAGS:
        m[f"psrr_{tag}_db"] = -ac_vals[f"vdb_{tag}"]
    # frequency-grid sanity: the grid point nearest the spot must BE the spot
    # (the .meas AT= interpolates, so a coarsened grid would otherwise hide).
    if wave is None:
        errs.append("no ac waveform returned: frequency grid not verifiable")
    else:
        try:
            freq = column(wave, "frequency")
            for name, target in (("f_dc_hz", 1.0), ("f_band_edge_hz", 1e3)):
                m[name] = min(freq, key=lambda f: abs(math.log10(f) - math.log10(target)))
            args = next(c for c in tb["analyses"] if c.startswith("ac ")).split()
            per_dec, f0, f1 = int(args[2]), float(args[3].replace("meg", "e6")), float(args[4].replace("meg", "e6"))
            want = round(per_dec * math.log10(f1 / f0)) + 1
            if len(freq) != want:
                errs.append(f"ac grid has {len(freq)} points, the bench's `ac` card implies {want}")
        except (ValueError, StopIteration) as exc:
            errs.append(f"ac waveform unusable: {exc}")
    if op_vals is None or f"vref_op_s{supply_index}" not in op_vals:
        errs.append("no operating-point measurement (vref_op companion request missing for this corner)")
    else:
        m["vref_op"] = op_vals[f"vref_op_s{supply_index}"]
    return m, errs


def op_values(wave: dict | None, supplies: list[float]) -> dict:
    """{vref_op_s<i>: v(vref) at supply i} from the companion `dc` sweep waveform."""
    if wave is None:
        raise ValueError("no dc waveform returned")
    x = list(next(iter(wave.values())))  # klt waveform contract: variables[0] is always the sweep variable
    vref = column(wave, "v(vref)", "vref")
    out = {}
    for i, v in enumerate(supplies):
        j = min(range(len(x)), key=lambda q: abs(x[q] - v))
        if abs(x[j] - v) > 1e-6:
            raise ValueError(f"sweep has no point at {v} V")
        out[f"vref_op_s{i}"] = vref[j]
    return out


def _linereg_span(tb: dict) -> float:
    mt = re.search(r"/\s*([0-9.]+)\s*$", tb["measure"]["linereg_mv_per_v"])
    if not mt:
        raise ValueError("cannot read the span divisor from tb.json measure.linereg_mv_per_v")
    return float(mt.group(1))


def derive_linereg(vals: dict, wave: dict | None, tb: dict, sweep: dict):
    """-> (measures, errs). vref_min / vref_max / linereg_mv_per_v, the sweep
    count and the endpoints all come from the full-precision waveform (as the
    harness computes them from full-precision vectors in `.control`); the
    fleet's printed `.meas` vref_min / vref_max are only a cross-check at
    ngspice's print precision (see MEAS_REL_TOL). Without a usable waveform
    the corner is invalid (errs non-empty), so `.meas`-derived values are
    never gated."""
    errs: list[str] = []
    span = _linereg_span(tb)
    m = {k: vals[k] for k in LINEREG_REQUIRED}
    m["linereg_mv_per_v"] = (vals["vref_max"] - vals["vref_min"]) * 1000.0 / span
    if wave is None:
        errs.append("no dc waveform returned: sweep point count / extrema not verifiable")
        return m, errs
    try:
        # klt waveform contract: variables[0] is always the sweep variable.
        x = list(next(iter(wave.values())))
        if not all(fc.is_finite_number(v) for v in x):
            raise ValueError("non-finite sweep axis")
        vref = column(wave, "v(vref)", "vref")
        if len(vref) != len(x):
            raise ValueError("sweep axis and v(vref) lengths differ")
    except (ValueError, StopIteration) as exc:
        errs.append(f"dc waveform unusable: {exc}")
        return m, errs
    m["sweep_points"] = float(len(x))
    m["vref_lo"], m["vref_hi"] = vref[0], vref[-1]  # dc1.v(vref)[0] / [132]
    step = sweep["step"]
    if any(abs((b - a) - step) > 1e-6 for a, b in zip(x, x[1:])):
        errs.append("sweep axis is not uniform at the bench's step")
    if abs(x[0] - sweep["lo"]) > 1e-6 or abs(x[-1] - sweep["hi"]) > 1e-6:
        errs.append(f"sweep axis spans {x[0]:.4f}..{x[-1]:.4f} V, not {sweep['lo']}..{sweep['hi']}")
    m["vref_max"], m["vref_min"] = max(vref), min(vref)
    m["linereg_mv_per_v"] = (m["vref_max"] - m["vref_min"]) * 1000.0 / span
    for name in ("vref_max", "vref_min"):
        if not meas_agrees(vals[name], m[name]):
            errs.append(f"{name} {vals[name]:.9f} (.meas) disagrees with the waveform's {m[name]:.9f} "
                        f"beyond ngspice's 7-digit print precision")
    return m, errs


def derive_startup(wave: dict | None, supply: float, tb: dict):
    """-> (measures, errs). Exactly the bench's own convention:

    t0 = first time v(vdd) >= 90 % of its final value; t_settle = start of the
    final unbroken stretch inside +/-1 % of v(vref)'s OWN final value, found
    by a backward scan from the end (late re-entry/chatter pushes it later);
    startup_time = t_settle - t0 (negative when the loop was already in band
    before vdd reached 90 %).
    """
    errs: list[str] = []
    if wave is None:
        return {}, ["no transient waveform returned: startup time not computable"]
    try:
        t = column(wave, "time")
        vdd = column(wave, "v(vdd)", "vdd")
        vref = column(wave, "v(vref)", "vref")
        isup = column(wave, "i(vsup)")
        isu = column(wave, "i(v.xtop.vsu_sense)")
        det = column(wave, "v(xtop.xx3.det)")
    except ValueError as exc:
        return {}, [f"transient waveform unusable: {exc}"]
    n = len(t)
    if not (len(vdd) == len(vref) == len(isup) == len(isu) == len(det) == n) or n < 3:
        return {}, ["transient waveform columns are ragged or too short"]
    if any(b <= a for a, b in zip(t, t[1:])):
        return {}, ["transient time axis is not strictly increasing"]
    stop = _tran_stop(tb)
    if t[-1] < stop * (1 - 1e-6):
        errs.append(f"transient stopped at {t[-1]:.6g} s, before the bench's {stop:.6g} s")
    vf = vref[n - 1]
    tol = 0.01 * abs(vf)
    lo, hi = vf - tol, vf + tol
    idx = n - 1
    while idx > 0 and not (vref[idx - 1] < lo or vref[idx - 1] > hi):
        idx -= 1
    t_settle = t[idx]
    vdd_final = vdd[n - 1]
    thresh = 0.9 * vdd_final
    j = 0
    while j < n - 1 and not vdd[j] >= thresh:
        j += 1
    if not vdd[j] >= thresh:
        errs.append("v(vdd) never reached 90 % of its final value")
    if abs(vdd_final - supply) > STARTUP_REACH_TOL * supply:
        errs.append(f"v(vdd) ended at {vdd_final:.4f} V, not the requested {supply:.4f} V rail")
    t0 = t[j]
    m = {
        "startup_time_s": t_settle - t0,
        "vref_final_v": vf,
        "iq_total_final_ua": -isup[n - 1] * 1e6,
        "iq_startup_branch_final_ua": isu[n - 1] * 1e6,
        "det_final_v": det[n - 1],
        "t0_s": t0,
        "t_settle_s": t_settle,
        "vdd_final_v": vdd_final,
    }
    return m, errs


def _tran_stop(tb: dict) -> float:
    args = next(c for c in tb["analyses"] if c.startswith("tran ")).split()
    return _spice_number(args[2])


_SUFFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9}


def _spice_number(tok: str) -> float:
    mt = re.fullmatch(r"([-+0-9.eE]+?)(meg|[fpnumkg])?", tok.lower())
    if not mt:
        raise ValueError(f"unparseable SPICE number {tok!r}")
    return float(mt.group(1)) * _SUFFIX.get(mt.group(2), 1.0)


# --------------------------------------------------------------------------
# output-noise (#268): unit-checked, conversion from tb.json via the plan
# --------------------------------------------------------------------------

#: ngspice's integrated-noise plot name in amplitude mode (``sqrnoise`` unset);
#: squared mode names it "Integrated Noise - V^2 or A^2" and types its
#: vectors ``voltage^2`` (verified with klt 0.7.0 / ngspice 46, see
#: sim/output-noise/fleet-capability/README.md).
NOISE_TOTAL_PLOT = "Integrated Noise"
NOISE_TOTAL_TYPE = "voltage"


def wave_columns(doc: dict) -> dict[str, list]:
    """{variable name: [values]} from an already-parsed klt waveform document."""
    names = [v["name"] for v in doc["variables"]]
    pts = doc["points"]
    if not pts or any(len(r) != len(names) for r in pts):
        raise ValueError("waveform has no points or ragged rows")
    return {n: [r[i] for r in pts] for i, n in enumerate(names)}


def read_waveform_doc_for(c: dict, work: Path) -> dict | None:
    """The raw klt waveform document (plot name and variable types kept), or None."""
    p = ((c or {}).get("artifacts") or {}).get("waveform")
    if not p or not (work / p).exists():
        return None
    try:
        doc = json.loads((work / p).read_text())
        wave_columns(doc)
        return doc
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def reported_units(c: dict | None) -> dict:
    return {m.get("name"): m.get("unit") for m in (c or {}).get("measurements", []) or []}


def noise_unit_problems(doc: dict | None) -> list[str]:
    """Why an integrated-noise waveform artifact does not show amplitude mode."""
    if doc is None:
        return ["no integrated-noise waveform returned: amplitude vs squared representation not verifiable"]
    errs = []
    if doc.get("plotname") != NOISE_TOTAL_PLOT:
        errs.append(f"integrated-noise plot is {doc.get('plotname')!r}, not amplitude-mode {NOISE_TOTAL_PLOT!r} (#252)")
    types = {str(v.get("name")).lower(): v.get("type") for v in doc.get("variables", [])}
    t = types.get("v(onoise_total)", types.get("onoise_total"))
    if t != NOISE_TOTAL_TYPE:
        errs.append(f"onoise_total has type {t!r}, not {NOISE_TOTAL_TYPE!r} (amplitude mode, #252)")
    return errs


def _full_precision(doc: dict | None, vector: str) -> float:
    """The single-point value of ``vector`` (``v(x)`` or ``onoise_total``) from an op / integrated-noise waveform."""
    if doc is None:
        raise ValueError("no waveform returned")
    wave = wave_columns(doc)
    bare = vector[2:-1] if vector.startswith("v(") else vector
    col = column(wave, f"v({bare})", bare)
    if len(col) != 1:
        raise ValueError(f"{vector} has {len(col)} points, a single-point plot was expected")
    return col[0]


def noise_request_units(nspec: dict, rname: str) -> dict:
    """measurement name -> the SI unit the plan asked klt to label it with."""
    out = {f"raw_{m}": s["si_unit"] for m, s in nspec["measures"].items() if s["request"] == rname}
    if nspec["requests"][rname]["analysis"]["kind"] == "noise":
        out.update({"n_points": "1", "sqrnoise_set": "1"})
    return out


def derive_noise(nspec: dict, vals: dict, docs: dict, units: dict):
    """-> (measures, errs) for one PVT corner.

    ``vals`` / ``docs`` / ``units``: request name -> that corner's finite klt
    values / waveform document / reported measurement units. Every measure
    is tb.json's own expression evaluated by ngspice on the worker (plot
    renumbered, scale stripped) times tb.json's scale. Single-point vectors
    (the integrated total, the operating point) come from the full-precision
    waveform and the printed expr is only a cross-check (MEAS_REL_TOL);
    spectrum points and frequencies only exist as printed expr values (the
    artifact holds the integrated plot only, klt #2893), 7 significant
    digits."""
    errs: list[str] = []
    for rname, rq in nspec["requests"].items():
        v = vals[rname]
        for mname, want in noise_request_units(nspec, rname).items():
            got = units.get(rname, {}).get(mname)
            if got != want:
                errs.append(f"{rname}: {mname} reported in {got!r}, the plan requested {want!r}")
        if rq["analysis"]["kind"] != "noise":
            continue
        if v.get("sqrnoise_set") != nspec["sqrnoise_set_expected"]:
            errs.append(f"{rname}: sqrnoise is set on the worker (squared V^2/Hz mode), #252 requires it unset")
        if v.get("n_points") != rq["n_points"]:
            errs.append(f"{rname}: noise sweep has {v.get('n_points')} points, `{rq['analysis']['args']}` "
                        f"implies {rq['n_points']}")
        errs += [f"{rname}: {e}" for e in noise_unit_problems(docs.get(rname))]
    m: dict[str, float] = {}
    for name, s in nspec["measures"].items():
        raw = vals[s["request"]][f"raw_{name}"]
        if s["kind"] in ("total", "op"):
            try:
                full = _full_precision(docs.get(s["request"]), s["vector"])
            except ValueError as exc:
                errs.append(f"{name}: full-precision {s['vector']} unavailable ({exc})")
            else:
                if not meas_agrees(raw, full):
                    errs.append(f"{name}: printed {raw!r} disagrees with the waveform's {full!r} beyond print precision")
                raw = full
        m[name] = raw * s["scale"]
    return m, errs


def spread_pct(values: list[float]) -> float | None:
    """(max - min) / |mean| in %, as `harness.report.summarize` computes it."""
    if not values:
        return None
    mean = sum(values) / len(values)
    if not mean:
        return None
    out = (max(values) - min(values)) / abs(mean) * 100.0
    return out if math.isfinite(out) else None


# --------------------------------------------------------------------------
# bench assessment
# --------------------------------------------------------------------------

_SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)", re.I | re.M)


def deck_problems(bench: str, plan: dict, body_text: str, name: str) -> list[str]:
    """Duplicate `.subckt` names in a fleet deck (a canonical DUT concatenated
    with the startup bench's embedded core would define bandgap_top twice,
    and ngspice would silently take one)."""
    seen: dict[str, int] = {}
    for n in _SUBCKT_RE.findall(body_text):
        seen[n.lower()] = seen.get(n.lower(), 0) + 1
    probs = [f"request {name!r}: .subckt {n} defined {c} times" for n, c in seen.items() if c > 1]
    if "bandgap_top" not in seen:
        probs.append(f"request {name!r}: no bandgap_top definition in the deck")
    if bool(plan.get("embedded_core")) != (bench == "startup"):
        probs.append("plan embedded_core flag does not match the bench's convention")
    return probs


def plan_problems(bench: str, tb: dict, plan: dict) -> list[str]:
    probs = []
    if plan.get("schema") != "gf180-bandgap/fleet-plan/1" or plan.get("bench") != bench:
        probs.append("plan is not a fleet plan for this bench")
        return probs
    from mk_klt_fleet_request import expected_units

    vdds = hc.supply_points(tb["nominal_supply_v"], tb.get("supply_tolerance", 0.0))
    if plan.get("supplies_v") != vdds:
        probs.append("plan supply points differ from tb.json / corners.py")
    if bench == NOISE_BENCH:
        from mk_klt_fleet_request import noise_spec

        try:
            nspec = noise_spec(tb)
        except ValueError as exc:
            return probs + [f"tb.json leaves the fleet noise contract: {exc}"]
        if plan.get("noise") != json.loads(json.dumps(nspec)):
            probs.append("plan noise contract (requests / measures / conversions) differs from tb.json's")
        want = {name: expected_units(tb, vdds) for name in nspec["requests"]}
    else:
        want = {
            "psrr-dc": {"ac": expected_units(tb, vdds), "op": expected_units(tb, [None])},
            "line-regulation": {"sweep": expected_units(tb, vdds)},
            "output-load-sensitivity": {"sweep": expected_units(tb, vdds)},  # characterization: sim/tools/load_ingest.py
            "startup": {r["name"]: expected_units(tb, [None]) for r in plan.get("requests", [])},
        }[bench]
    got = {r["name"]: r["expected_units"] for r in plan.get("requests", [])}
    if set(got) != set(want):
        probs.append(f"plan requests {sorted(got)} differ from the bench's {sorted(want)}")
    else:
        for name in want:
            if got[name] != want[name]:
                probs.append(f"request {name!r}: plan corner list differs from tb.json / corners.py")
    if bench == "startup" and sorted(r["supply_v"] for r in plan.get("requests", [])) != sorted(vdds):
        probs.append("startup requests do not cover the supply points exactly once each")
    return probs


def _unit_key(r: dict):
    sup = r.get("supply_v")

    def key_of(cid: str):
        p, s, t = fc.parse_klt_corner_id(cid)
        s = sup if s is None else s
        return (p, None if s is None else round(s, 4), t)

    return key_of


def _expected_keys(r: dict) -> list[tuple]:
    sup = r.get("supply_v")
    return [(p, None if (s is None and sup is None) else round(sup if s is None else s, 4), t) for p, s, t in r["expected_units"]]


def read_waveform_for(c: dict, work: Path):
    art = (c or {}).get("artifacts") or {}
    p = art.get("waveform")
    if not p:
        return None
    path = work / p
    if not path.exists():
        return None
    try:
        return read_waveform(path)
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def assess_bench(bench: str, tb: dict, plan: dict, reports: dict, work: Path, *, dut_sha: str | None = None,
                 decks: dict | None = None, manifest_sha: str | None = None, tb_sha: str | None = None,
                 require_remote: bool = True, requests: dict | None = None) -> dict:
    """Judge one bench from its plan and the klt reports (``{request name: report}``).

    Never raises on bad evidence: every defect lands in ``problems`` /
    ``missing`` / ``failed`` / ``invalid`` and keeps the verdict out of PASS.
    """
    grid = expected_grid(tb)
    problems = plan_problems(bench, tb, plan)
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
        problems += deck_problems(bench, plan, text, n)

    missing: list = []
    failed: list = []
    pts: dict[str, dict] = {}
    waves: dict[tuple, dict] = {}  # (request, unit key) -> waveform
    docs: dict[tuple, dict | None] = {}  # (request, unit key) -> raw waveform document (output-noise)
    corners_of: dict[tuple, dict] = {}
    for r in plan.get("requests", []):
        rep = reports.get(r["name"])
        if rep is None:
            for k in _expected_keys(r):
                missing.append(((r["name"],) + k, "no report.json for this request"))
            pts[r["name"]] = {}
            continue
        problems += [f"{r['name']}: {p}" for p in fc.provenance_problems(rep, plan, require_remote=require_remote)]
        required = r["measurements"]
        p, mi, fa, pr = fc.collect_units(rep, _expected_keys(r), required, _unit_key(r))
        pts[r["name"]] = p
        missing += [((r["name"],) + k, why) for k, why in mi]
        failed += [((r["name"],) + k, why) for k, why in fa]
        problems += [f"{r['name']}: {x}" for x in pr]
        for c in rep.get("corners", []):
            try:
                corners_of[(r["name"], _unit_key(r)(c["corner_id"]))] = c
            except Exception:
                pass
        for k in list(p):
            w = read_waveform_for(corners_of.get((r["name"], k)), work)
            if r["role"] in ("ac", "sweep", "tran"):
                waves[(r["name"], k)] = w
            elif r["role"] in ("noise", "op_point"):
                docs[(r["name"], k)] = read_waveform_doc_for(corners_of.get((r["name"], k)), work)
            elif r["role"] == "op":
                try:
                    p[k] = op_values(w, plan["supplies_v"])
                except ValueError as exc:
                    del p[k]
                    missing.append(((r["name"],) + k, f"operating-point companion unusable: {exc}"))

    req = {r["name"]: r for r in plan.get("requests", [])}
    supplies = plan.get("supplies_v", [])
    rows: dict = {}
    invalid: dict = {}
    series: dict = {}
    for key in grid:
        proc, temp, sup = key
        derived = None
        errs: list[str] = []
        try:
            if bench == "psrr-dc":
                ac = pts.get("ac", {}).get((proc, sup, temp))
                op = pts.get("op", {}).get((proc, None, temp))
                if ac is None:
                    errs.append("ac unit unavailable")
                else:
                    w = waves.get(("ac", (proc, sup, temp)))
                    derived, e = derive_psrr(ac, w, op, supplies.index(sup) if sup in supplies else supplies.index(round(sup, 6)), tb)
                    errs += e
                    if w is not None:
                        try:
                            series[key] = {"frequency": column(w, "frequency"), "v(vref)": column(w, "v(vref)", "vref")}
                        except ValueError:
                            pass
            elif bench == "line-regulation":
                u = pts.get("sweep", {}).get((proc, sup, temp))
                if u is None:
                    errs.append("sweep unit unavailable")
                else:
                    w = waves.get(("sweep", (proc, sup, temp)))
                    derived, e = derive_linereg(u, w, tb, req["sweep"]["sweep"])
                    errs += e
                    if w is not None:
                        try:
                            x = list(next(iter(w.values())))
                            series[key] = {"sweep": x, "v(vref)": column(w, "v(vref)", "vref")}
                        except ValueError:
                            pass
            elif bench == NOISE_BENCH:
                nspec = plan.get("noise") or {}
                ukey = (proc, sup, temp)
                vals = {n: pts.get(n, {}).get(ukey) for n in nspec.get("requests", {})}
                absent = sorted(n for n, v in vals.items() if v is None)
                if absent or not vals:
                    errs.append("unit unavailable in request(s) " + (", ".join(absent) or "(plan has no noise contract)"))
                else:
                    derived, e = derive_noise(nspec, vals, {n: docs.get((n, ukey)) for n in vals},
                                              {n: reported_units(corners_of.get((n, ukey))) for n in vals})
                    errs += e
            else:
                rname = next((n for n, r in req.items() if r["supply_v"] is not None and abs(r["supply_v"] - sup) < 1e-6), None)
                u = pts.get(rname, {}).get((proc, round(sup, 4), temp)) if rname else None
                if u is None:
                    errs.append("transient unit unavailable")
                else:
                    w = waves.get((rname, (proc, round(sup, 4), temp)))
                    derived, e = derive_startup(w, sup, tb)
                    errs += e
                    if w is not None:
                        try:
                            series[key] = {n: column(w, n) for n in ("time", "v(vdd)", "v(vref)")}
                        except ValueError:
                            pass
        except Exception as exc:  # fail closed: a derivation bug is INVALID, not a crash
            errs.append(f"derivation error: {type(exc).__name__}: {exc}")
        if derived is None:
            invalid[key] = "; ".join(errs) or "no data"
            continue
        row = {"measures": derived, "spec": {}, "sanity": {}, "errs": errs}
        for name, spec in tb["checks"].items():
            bucket = "spec" if name in SPEC_CHECKS[bench] else "sanity"
            if name not in derived:
                row["errs"].append(f"check measurement {name!r} unavailable")
            else:
                row[bucket][name] = check_ok(spec, derived[name])
        rows[key] = row
        if row["errs"] or not all(row["sanity"].values()):
            bad = [f"sanity {n} out of window ({derived[n]:.6g})" for n, ok in row["sanity"].items() if not ok]
            invalid[key] = "; ".join(row["errs"] + bad)

    spreads: dict = {}
    if bench in MEASUREMENT_BENCHES:
        # grid-level spread floor (harness.report semantics): a figure that should
        # move with PVT but comes back flat means .temp / .lib never took effect.
        for name, chk in tb["checks"].items():
            if "min_spread_pct" not in chk:
                continue
            got = spread_pct([r["measures"][name] for k, r in rows.items() if k not in invalid and name in r["measures"]])
            spreads[name] = (got, chk["min_spread_pct"])
            if got is None or got < chk["min_spread_pct"]:
                problems.append(f"{name}: spread over the valid corners is {_f(got, 4)} %, below the "
                                f"{chk['min_spread_pct']:g} % floor (the PVT sweep may not have taken effect)")
    spec_fail = [k for k, r in rows.items() if k not in invalid and not all(r["spec"].values())]
    incomplete = bool(problems or missing or failed or invalid)
    if bench in MEASUREMENT_BENCHES:
        overall = "INCOMPLETE" if incomplete else MEASURED  # measurement completion, never a spec pass
    else:
        overall = "INCOMPLETE" if incomplete else ("FAIL" if spec_fail else "PASS")
    return {
        "bench": bench, "overall": overall, "grid": grid, "rows": rows, "invalid": invalid, "spec_fail": spec_fail,
        "missing": missing, "failed": failed, "problems": problems, "series": series, "spreads": spreads,
        "corners_of": {f"{a}|{b}": c for (a, b), c in corners_of.items()},
    }


def worst(result: dict, tb: dict) -> dict:
    """Worst valid value of every spec check (the number a claim stands on)."""
    out = {}
    for name in SPEC_CHECKS[result["bench"]]:
        spec = tb["checks"][name]
        vals = [(r["measures"][name], k) for k, r in result["rows"].items() if k not in result["invalid"]]
        if vals:
            out[name] = (min(vals) if "min" in spec else max(vals))
    return out


# --------------------------------------------------------------------------
# evidence writing (sim/README.md conventions)
# --------------------------------------------------------------------------


def _unit_logs(result: dict, plan: dict, work: Path, key) -> str:
    raw = []
    for r in plan.get("requests", []):
        proc, temp, sup = key
        candidates = [(proc, round(sup, 4), temp), (proc, None, temp)]
        if r.get("supply_v") is not None:
            if abs(r["supply_v"] - sup) > 1e-6:
                continue
            candidates = [(proc, round(sup, 4), temp)]
        for cand in candidates:
            c = result["corners_of"].get(f"{r['name']}|{cand}")
            if c is None:
                continue
            art = c.get("artifacts") or {}
            src = work / (art.get("log") or "")
            raw.append(f"* ---- ngspice log of request {r['name']!r} ({c['corner_id']}, status {c.get('status')}) ----\n"
                       + (src.read_text() if art.get("log") and src.exists() else "(no ngspice.log returned)\n"))
            break
    return "\n".join(raw) or "(no unit returned for this corner)\n"


def write_corner_logs(cdir: Path, work: Path, plan: dict, result: dict, record: str) -> None:
    """One log per expected harness corner, in the suite-readable shape. A
    corner without valid data gets the INVALID POINT trailer (suite: NO DATA);
    a corner absent from the report still gets a visible invalid log."""
    cdir.mkdir(parents=True, exist_ok=True)
    for key in result["grid"]:
        head = f"* record-id : {record}\n* bench : {result['bench']}\n* corner : {corner_id(key)}\n"
        body = _unit_logs(result, plan, work, key)
        row = result["rows"].get(key)
        if row is not None and key not in result["invalid"]:
            tail = "\n* ---- derived by sim/tools/fleet_ingest.py from the fleet measurements/waveform ----\n" + "".join(
                f"m_{n} = {v:.10e}\n" for n, v in row["measures"].items())
        else:
            tail = (f"\n{INVALID_POINT_MARKER} -- {result['invalid'].get(key, 'no data')} ***\n"
                    "*** no valid measurement set for this corner ***\n")
        (cdir / f"{corner_id(key)}.log").write_text(head + body + tail)
    sdir = cdir / "series"
    for key, cols in result["series"].items():
        sdir.mkdir(exist_ok=True)
        with gzip.open(sdir / f"{corner_id(key)}.json.gz", "wt") as fh:
            json.dump(cols, fh)


def _f(x, n=6):
    return "-" if x is None else f"{x:.{n}g}"


def build_record(record: str, stamp: datetime, bench: str, tb: dict, plan: dict, result: dict, reports: dict,
                 dut_label: str, issue, supersedes, note, git=None) -> str:
    overall = result["overall"]
    L: list[str] = []
    add = L.append
    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add("- **Claim**: " + tb["claim"].split(" Caveat")[0].split(" Load condition")[0]
        + f" Fleet (`klt sim`) evidence for issue #{issue}."
        + ("" if overall != "INCOMPLETE" else " **INCOMPLETE -- see Result: no verdict is claimed.**"))
    emb = plan.get("embedded_core")
    add(f"- **Netlist provenance**: {plan['dut'].get('provenance_class', 'schematic')}. "
        f"{'Canonical' if 'provenance_class' not in plan['dut'] else 'Supplied'} DUT `{dut_label}` sha256 `{plan['dut']['sha256']}`; "
        f"testbench sha256 `{plan['tb_netlist_sha256']}`; tb.json sha256 `{plan['manifest_sha256']}`.")
    if emb:
        add("  - **Embedded-core convention** (`sim/startup-embedded-core-sync.md`): this bench simulates its OWN "
            "embedded, synchronized `bandgap_top` core -- the canonical DUT is NOT in the fleet deck. Two identities "
            "are therefore recorded separately: the canonical DUT hash above, and the frozen embedded deck hashes below. "
            "Equivalence caveat: the embedded core lumps R1 + 32 trim units into one resistor "
            "(exact at tt/27 C only; -0.18 % / +0.27 % at -40 / 125 C; res_ff/res_ss not exercised), so this is not a "
            "simulation of the canonical netlist itself.")
    for r in plan["requests"]:
        add(f"  - frozen fleet deck `{r['name']}` sha256 `{r['deck_sha256']}` (`netlist-snapshots/{record}.{r['name']}.spice`)")
    add("- **Corner matrix run**:")
    procs = sorted({k[0] for k in result["grid"]}, key=[k[0] for k in result["grid"]].index)
    add(f"  - Process: {', '.join(procs)}")
    add(f"  - Temperature: {', '.join(f'{t:g}' for t in tb['temperatures_c'])} C")
    add("  - Supply: " + ", ".join(f"{v:.2f} V" for v in plan["supplies_v"])
        + (" (outer axis; the continuous sweep is inside the testbench)" if bench == "line-regulation" else ""))
    nvalid = len(result["rows"]) - len(result["invalid"].keys() & result["rows"].keys())
    add(f"  - {len(result['grid'])} corners expected; {nvalid} valid; {len(result['invalid'])} invalid/unavailable; "
        f"{len(result['missing'])} unit(s) missing, {len(result['failed'])} failed/errored.")
    add("- **Statistical convention**: N/A (corner-matrix claim, not a distribution claim)")
    add("- **Result**:")
    if bench == "psrr-dc":
        add("  - Operating-point sanity (`vref_op`) comes from a companion `dc` sweep request, not from the ac analysis' "
            "own operating point (an ac-kind klt request cannot return it); it is a surrogate, stated rather than implied. "
            "Reference columns (10 Hz ... 1 MHz) are recorded, not gated.")
    if bench == "line-regulation":
        add("  - vref_min / vref_max / linereg_mv_per_v, the sweep point count and the endpoints are computed from the "
            "full-precision returned waveform; the fleet `.meas` vref_min / vref_max (printed by ngspice at 7 "
            "significant digits) are only a cross-check at that precision and are not gated.")
    if bench == "startup":
        add("  - t0 = first time vdd reaches 90 % of its final value; settled = start of the last unbroken stretch inside "
            "+/-1 % of vref's final value (backward scan over the returned waveform; a first-crossing approximation is "
            "not equivalent); a negative value means the loop was in band before vdd reached 90 %.")
    if bench == NOISE_BENCH:
        nspec = plan.get("noise") or {}
        add(f"  - **Measurement only.** {plan.get('scope', '')}. `{MEASURED}` means every corner of every request came "
            "back valid; it is not a spec verdict, and the Output-noise row stays unclaimed (sim/suite NOT_CLAIMED_HERE).")
        add("  - Unit contract (#252, `sim/output-noise/unit-probe/`): ngspice amplitude mode, forced by "
            f"`options.ngspice_init` {nspec.get('control')}; each noise request returned `$?sqrnoise` = 0 and an "
            f"integrated-noise artifact `{NOISE_TOTAL_PLOT}` typed `{NOISE_TOTAL_TYPE}`. Conversions are tb.json's own "
            "(scale only, no square root): the fleet returned raw SI values, multiplied here by:")
        for name, s in nspec.get("measures", {}).items():
            add(f"    - `{name}` = `{s['manifest_expr']}` -> request `{s['request']}` `{s['expr']}` [{s['si_unit']}] "
                f"x {s['scale']:g} [{s['unit']}]")
        add("  - Requests (one analysis per corner each): " + "; ".join(
            f"`{n}` = `{(q['analysis']['kind'] + ' ' + q['analysis']['args']).strip()}`"
            for n, q in nspec.get("requests", {}).items())
            + ". `vref_op` is the companion `op` request's solve of the same deck and corner (the point ngspice's "
            "`noise` linearizes around), not read from inside the noise request.")
        add("  - Integrated total and `vref_op` come from the full-precision waveform artifact (the printed expr is a "
            "cross-check); spot densities and frequency indices are printed expr values (7 significant digits).")
        for name, (got, lim) in result.get("spreads", {}).items():
            add(f"  - Grid spread of `{name}` over valid corners: {_f(got, 4)} % (floor {lim:g} %).")
    if overall == "INCOMPLETE":
        add("  - **INCOMPLETE.**")
        for k, why in result["missing"]:
            add(f"    - missing {k}: {why}")
        for k, why in result["failed"]:
            add(f"    - failed {k}: {why}")
        for k, why in result["invalid"].items():
            add(f"    - invalid `{corner_id(k)}`: {why}")
        for p in result["problems"]:
            add(f"    - problem: {p}")
    if note:
        add(f"  - {note}")
    add("")
    cols = list(tb["measure"].keys()) + (["vdd_final_v"] if bench == "startup" else [])
    spec = sorted(SPEC_CHECKS[bench])
    add("  | corner-id | " + " | ".join(cols) + " | spec | state |")
    add("  |---|" + "---|" * (len(cols) + 2))
    for key in result["grid"]:
        row = result["rows"].get(key)
        if row is None or key in result["invalid"]:
            add(f"  | `{corner_id(key)}` | " + " | ".join("-" for _ in cols) + " | - | **INVALID** |")
            continue
        okspec = all(row["spec"].values())
        if bench in MEASUREMENT_BENCHES:
            add(f"  | `{corner_id(key)}` | " + " | ".join(_f(row["measures"].get(c)) for c in cols)
                + f" | n/a | {MEASURED} |")
            continue
        add(f"  | `{corner_id(key)}` | " + " | ".join(_f(row["measures"].get(c)) for c in cols)
            + f" | {'ok' if okspec else 'FAIL'} | {'PASS' if okspec else 'FAIL'} |")
    add("")
    w = worst(result, tb)
    if w:
        scope = "all corners" if overall != "INCOMPLETE" else "the valid corners ONLY (record incomplete)"
        add(f"  Worst case over {scope}:")
        add("")
        for name in spec:
            if name in w:
                lim = tb["checks"][name]
                add(f"  - `{name}`: **{w[name][0]:.6g}** at `{corner_id(w[name][1])}` (limit {', '.join(f'{k} {v:g}' for k, v in lim.items() if k in ('min', 'max'))})")
        add("")
    add(f"  - **Overall: {overall}**")
    add("- **Links**:")
    add(f"  - Testbench: `sim/{bench}/testbench/{tb['netlist']}`, `sim/{bench}/testbench/tb.json`")
    add(f"  - Raw logs: `sim/{bench}/corners/{record}/` (also `plan.json`, `request-<name>.json`, `report-<name>.json`, `series/`)")
    add("  - Request adapter: `sim/tools/mk_klt_fleet_request.py`; ingestion: `sim/tools/fleet_ingest.py`")
    for name, rep in reports.items():
        remote = (rep.get("environment") or {}).get("remote") or {}
        if remote:
            add(f"  - Fleet execution `{name}`: {remote.get('provider')} job `{remote.get('job_id')}`, "
                f"{remote.get('instance_type')} ({remote.get('lifecycle')}), state {remote.get('state')}, exit {remote.get('exit_code')}")
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
            f"{' (dirty working tree at ingest; the frozen decks, not the tree, are the evidence)' if git.get('dirty') else ''}")
    add("")
    add("---")
    add("")
    add("Written by `sim/tools/fleet_ingest.py`. Append-only: never edit or delete this file -- a re-run or "
        "correction mints a new record-id and points back here via **Supersedes** (see `sim/README.md`).")
    add("")
    return "\n".join(L)


def write_evidence(exp_dir: Path, work: Path, bench: str, tb: dict, plan: dict, result: dict, reports: dict, *,
                   dut_label: str, issue, supersedes=None, note=None, git=None, repo: Path = REPO,
                   stamp: datetime | None = None) -> Path:
    """Write record + logs + frozen decks + request/report copies under ``exp_dir``
    (``sim/<bench>``; a temp dir in tests). Refuses to overwrite (append-only)."""
    from harness import report as hreport

    git = git or hreport.git_provenance(repo)
    record = hreport.allocate_record_id(repo, exp_dir / "records", when=stamp, git=git)
    st = datetime.strptime(record[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    cdir = exp_dir / "corners" / record
    write_corner_logs(cdir, work, plan, result, record)
    shutil.copyfile(work / "plan.json", cdir / "plan.json")
    snap = exp_dir / "netlist-snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    for r in plan["requests"]:
        shutil.copyfile(work / r["name"] / "request.json", cdir / f"request-{r['name']}.json")
        if r["name"] in reports:
            (cdir / f"report-{r['name']}.json").write_text(json.dumps(reports[r["name"]], indent=2) + "\n")
        shutil.copyfile(work / r["name"] / "body.spice", snap / f"{record}.{r['name']}.spice")
    text = build_record(record, st, bench, tb, plan, result, reports, dut_label, issue, supersedes, note, git)
    return hreport.device_write_record(exp_dir / "records", record, text)


# --------------------------------------------------------------------------


def load_work(work: Path) -> tuple[dict, dict, dict, dict]:
    plan = json.loads((work / "plan.json").read_text())
    reports, decks, requests = {}, {}, {}
    for r in plan.get("requests", []):
        rp = work / r["name"] / "report.json"
        if rp.exists():
            reports[r["name"]] = json.loads(rp.read_text())
        bp = work / r["name"] / "body.spice"
        if bp.exists():
            decks[r["name"]] = bp.read_text()
        qp = work / r["name"] / "request.json"
        if qp.exists():
            requests[r["name"]] = qp.read_text()
    return plan, reports, decks, requests


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bench", choices=BENCHES + MEASUREMENT_BENCHES)
    ap.add_argument("workdir", help="dir written by mk_klt_fleet_request.py, with <request>/report.json added")
    ap.add_argument("--dut", default="sim/dut/bandgap_top.spice", help="canonical DUT the requests were built from")
    ap.add_argument("--issue", default="239")
    ap.add_argument("--supersedes", default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the verdict, write nothing")
    a = ap.parse_args()

    work = Path(a.workdir).resolve()
    tb = load_tb(a.bench)
    plan, reports, decks, requests = load_work(work)
    dut = Path(a.dut) if Path(a.dut).is_absolute() else REPO / a.dut
    result = assess_bench(
        a.bench, tb, plan, reports, work, dut_sha=fc.sha256_file(dut), decks=decks, requests=requests,
        manifest_sha=fc.sha256_file(SIM / a.bench / "testbench" / "tb.json"),
        tb_sha=fc.sha256_file(SIM / a.bench / "testbench" / tb["netlist"]),
    )
    print(f"overall={result['overall']} valid={len(result['rows']) - len(result['invalid'])}/{len(result['grid'])} "
          f"missing={len(result['missing'])} failed={len(result['failed'])} invalid={len(result['invalid'])} "
          f"problems={len(result['problems'])}")
    for p in result["problems"][:10]:
        print("  problem:", p)
    if a.dry_run:
        return 0 if result["overall"] in ("PASS", MEASURED) else 2
    path = write_evidence(SIM / a.bench, work, a.bench, tb, plan, result, reports, dut_label=a.dut,
                          issue=a.issue, supersedes=a.supersedes, note=a.note)
    print(f"wrote {path}")
    return 0 if result["overall"] in ("PASS", MEASURED) else 2


if __name__ == "__main__":
    raise SystemExit(main())
