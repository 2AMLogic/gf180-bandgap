#!/usr/bin/env python3
"""Emit `klt sim` requests for the psrr-dc, line-regulation, startup and output-load-sensitivity benches.

Sibling of `sim/tools/mk_klt_request.py` (output-voltage-tc / iq; issue #237).
Shared dispatch workers must not run SPICE grids themselves, so each bench is
expressed as `klt sim` request(s) that `KLT_SIM_BACKEND=batch` sends to the
Spot fleet. The corner list, supply points, analysis and checks come from the
bench's own `tb.json` and `sim/harness/corners.py` -- there is no second
hand-kept corner list. This script only WRITES requests (and a plan the
ingestor reads); it never dispatches anything.

What the pinned `klt sim` request contract can and cannot express, and how
each bench is mapped (verified from the klt source, see the PR for #237):

* ``analysis`` is one ``{kind, args}`` card -> one ngspice command per corner.
  ``ac``, ``dc`` and ``tran`` are all accepted verbatim.
* ``.meas`` cards cover ``dc``/``ac``/``tran``/``sp`` only; there is no
  ``.meas op``. Waveform-wide reductions (a backward scan, a point count)
  are not ``.meas``-expressible.
* ``options.waveforms`` returns each corner's vectors (``artifacts.waveform``,
  JSON); the ingestor does the waveform processing in Python.
* ``corners.supply_v`` is ``alter <source>=<v>``; klt REFUSES it for a source
  declared with a PWL/PULSE/SIN waveform (it would be silently ignored).

Mapping:

``psrr-dc``          request ``ac``: ``ac dec 20 0.1 10meg`` x process x supply x
                     temperature; `.meas ac ... FIND vdb(vref) AT=<f>` for the
                     spot frequencies (PSRR = -vdb), waveform for the frequency
                     grid sanity. Request ``op``: a companion ``dc vsup lo hi
                     step`` sweep whose v(vref) at the supply points,
                     read from the returned waveform, is the operating-point sanity value, because an
                     ac-kind request cannot return the operating point it
                     linearized around (no `.meas op`). Caveat recorded by the
                     ingestor: a dc continuation sweep is a surrogate for, not
                     the identical solve as, the ac analysis' own operating point.
``line-regulation``  one request, the bench's internal ``dc vsup 2.97 3.63
                     0.005`` x process x temperature with the manifest's
                     nominal-only outer supply (never three rails instead of
                     the continuous sweep); `.meas dc` min/max of v(vref) and v(vdd);
                     waveform for the 133-point count, endpoint values and
                     cross-checks (`.meas FIND AT=` fails at a sweep's ends).
``startup``          the supply is a PWL ramp, so klt refuses ``supply_v``. One
                     request PER SUPPLY POINT instead, with the supply in the
                     bench's own ``vdd_val`` parameter; process x temperature
                     inside each. ``tran 1u 3m``; the backward settling scan and
                     the 90 % supply crossing are computed from the waveform
                     (a first-crossing `.meas` is NOT equivalent). The bench
                     embeds its own synchronized bandgap_top core
                     (`sim/startup-embedded-core-sync.md`), so the canonical DUT
                     is deliberately NOT inlined (that would redefine
                     `bandgap_top`); the plan records both identities.

``output-load-sensitivity``  CHARACTERIZATION ONLY (#269; no spec threshold, no
                     load rating). One request: the bench's internal ``dc iload
                     -1u 2u 10n`` load-current sweep x process x supply (``alter
                     vsup``, the full +/-10 % axis) x temperature; `.meas dc` min/max
                     of v(vref) as a print-precision cross-check, waveform for the
                     baseline, signed shifts, slope at zero load and the
                     sign/units check (``sim/tools/load_ingest.py``). The sweep's
                     definition is tb.json ``load_sweep``, validated here by
                     :func:`load_sweep_spec` before anything is written. A
                     supplied extracted DUT (``--dut layout/...``) is inlined like
                     the schematic one and labelled ``extracted`` in the plan;
                     a DUT that ``.include``s other files is refused (the fleet
                     stages only the deck).

Tool-gap references (2AMLogic/klayout-tools): #2482 (one analysis per corner: the
ac operating-point companion) and #2964 (no param/ramp supply axis; `.meas AT=`
at sweep end points).

    python3 sim/tools/mk_klt_fleet_request.py psrr-dc WORK [--dut PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(HERE))

import fleet_common as fc  # noqa: E402
from harness import corners as hc  # noqa: E402

GENERATOR = "sim/tools/mk_klt_fleet_request.py"
SUPPLY_SOURCE = "vsup"
PLAN_SCHEMA = "gf180-bandgap/fleet-plan/1"
BENCHES = ("psrr-dc", "line-regulation", "startup")
#: Benches that characterize rather than verify: no ratified row, no spec
#: check, never PASS/FAIL. Kept apart from BENCHES so nothing that grades
#: spec rows (fleet_ingest.SPEC_CHECKS, the suite) can pick them up.
CHARACTERIZATION_BENCHES = ("output-load-sensitivity",)
SUPPORTED = BENCHES + CHARACTERIZATION_BENCHES
LOAD_BENCH = "output-load-sensitivity"
#: The only tb.json checks the load bench may carry: measurement sanity
#: (grid, baseline index, sense current), never a threshold on a load figure.
LOAD_SANITY_CHECKS = frozenset({"sweep_points", "i_zero_check", "i_lo_check", "i_hi_check"})
#: How far a grid value may sit from its nominal and still be "that point"
#: (relative to the sweep step): float noise only, never interpolation.
GRID_TOL = 1e-6

#: PSRR spot frequencies: measurement tag -> Hz. (tb.json indexes them on the
#: `ac dec 20 0.1 10meg` grid; here the frequency is explicit and the grid is
#: checked from the returned waveform.)
PSRR_SPOTS = {"1hz": 1.0, "10hz": 10.0, "100hz": 100.0, "1khz": 1e3, "10khz": 1e4, "100khz": 1e5, "1mhz": 1e6}

#: The pinned fleet model arguments, as in mk_klt_request.py.
MODELS = {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"}


def split_analysis(card: str) -> dict:
    kind, _, args = card.strip().partition(" ")
    return {"kind": kind, "args": args.strip()}


def pick_analysis(tb: dict, kind: str) -> dict:
    """The tb.json ``analyses`` card of the given kind (the bench's own)."""
    for card in tb["analyses"]:
        if card.startswith(kind + " "):
            return split_analysis(card.split("\n")[0])
    raise ValueError(f"tb.json of {tb['name']!r} has no {kind!r} analysis card")


def supply_tag(v: float) -> str:
    return f"{v:.3f}".replace(".", "p")


def head_lines(tb: dict, vdd: float, extra_params: dict | None = None) -> list[str]:
    lines = [
        f".param vdd_nom={tb['nominal_supply_v']!r}",
        f".param vdd_val={vdd!r}",
        ".param temp_c=27.0",
    ]
    for k, v in (extra_params or {}).items():
        lines.append(f".param {k}={v}")
    # gf180mcu BSIM4 bins are per finger; see mk_klt_request.py for why.
    lines.append(".options wnflag=1")
    return lines


def process_axis(tb: dict) -> list[dict]:
    return [{"name": c.name, "sections": list(c.sections)} for c in hc.resolve_corners(tb["corners"])]


def expected_units(tb: dict, supplies: list[float | None]) -> list[list]:
    """[[process, supply|None, temp], ...] -- harness grid order."""
    names = [c.name for c in hc.resolve_corners(tb["corners"])]
    return [[n, s, float(t)] for n in names for t in tb["temperatures_c"] for s in supplies]


def dut_provenance_class(dut_rel: str) -> str:
    """``schematic`` / ``frozen schematic`` / ``extracted`` from the DUT path
    (the rule `harness.testbench.Testbench.dut_provenance_class` applies)."""
    if dut_rel.startswith("layout/"):
        return "extracted"
    if "/frozen/" in dut_rel:
        return "frozen schematic"
    return "schematic"


def load_sweep_spec(tb: dict) -> dict:
    """The validated load-sweep definition of the output-load-sensitivity
    manifest -> plain numbers the request and the ingestor share.

    Raises ValueError when the manifest cannot define the measurement
    unambiguously: the ``dc`` card disagreeing with ``load_sweep``, no grid
    point at exactly 0 A (no unloaded baseline), a report point off the grid,
    too few points either side of zero for the step-refinement slope check,
    or a tb.json check on anything but measurement sanity (this bench carries
    no spec threshold)."""
    from fleet_ingest import _spice_number

    ls = tb.get("load_sweep")
    if not isinstance(ls, dict):
        raise ValueError("tb.json has no load_sweep definition")
    rng = ls["exploratory_range"]
    if "not a supported-load rating" not in rng.get("label", ""):
        raise ValueError("exploratory_range.label must say it is not a supported-load rating")
    lo, hi, step = float(rng["lo_a"]), float(rng["hi_a"]), float(rng["step_a"])
    card = pick_analysis(tb, "dc")["args"].split()
    if len(card) != 4:
        raise ValueError(f"dc card {card!r} is not `<source> <lo> <hi> <step>`")
    if card[0].lower() != ls["source"].lower():
        raise ValueError(f"dc card sweeps {card[0]!r}, load_sweep.source is {ls['source']!r}")
    c_lo, c_hi, c_step = (_spice_number(x) for x in card[1:])
    for name, a, b in (("lo", c_lo, lo), ("hi", c_hi, hi), ("step", c_step, step)):
        if abs(a - b) > GRID_TOL * step:
            raise ValueError(f"dc card {name} {a:g} A differs from load_sweep {b:g} A")
    if not (step > 0 and lo < 0 < hi):
        raise ValueError("the sweep must step upwards and straddle 0 A (baseline interior, slope central)")
    n = round((hi - lo) / step) + 1
    k0 = round(-lo / step)
    if abs(lo + k0 * step) > GRID_TOL * step or abs(lo + (n - 1) * step - hi) > GRID_TOL * step:
        raise ValueError("0 A and the sweep end are not exactly on the step grid: no unloaded baseline point")
    slope = ls["slope"]
    steps = [int(m) for m in slope["steps"]]
    if not steps or steps[0] != 1 or any(m < 1 for m in steps):
        raise ValueError("slope.steps must start at 1 grid step")
    need = max(int(ls["min_points_each_side"]), max(steps))
    if k0 < need or (n - 1 - k0) < need:
        raise ValueError(f"insufficient resolution: {k0} / {n - 1 - k0} points below / above 0 A, need >= {need}")
    points = []
    for i in ls["report_points_a"]:
        i = float(i)
        j = round((i - lo) / step)
        if i == 0 or not (0 <= j < n) or abs(lo + j * step - i) > GRID_TOL * step:
            raise ValueError(f"report point {i:g} A is zero, outside the sweep or off the grid")
        points.append(i)
    extra = set(tb.get("checks", {})) - LOAD_SANITY_CHECKS
    if extra:
        raise ValueError(f"characterization bench carries non-sanity checks {sorted(extra)}: no spec threshold here")
    return {
        "source": ls["source"], "sense": ls["sense"], "lo": lo, "hi": hi, "step": step, "n_points": n,
        "baseline_index": k0, "report_points": points, "slope_steps": steps,
        "slope_rel_tol": float(slope["step_refinement_rel_tol"]), "slope_abs_floor": float(slope["abs_floor_v_per_a"]),
        "min_points_each_side": int(ls["min_points_each_side"]),
        "sense_rel_tol": float(ls["sense_rel_tol"]), "sense_abs_tol": float(ls["sense_abs_tol_a"]),
        "supply_rel_tol": float(ls["supply_rel_tol"]),
    }


def _req_common(tb: dict, analysis: dict, measurements, supply_v, *, timeout_s: int) -> dict:
    corners = {"process": process_axis(tb), "temperature_c": list(tb["temperatures_c"])}
    if supply_v is not None:
        corners["supply_v"] = {SUPPLY_SOURCE: supply_v}
    return {
        "netlist": "body.spice",
        "engine": "ngspice",
        "models": dict(MODELS),
        "corners": corners,
        "analysis": analysis,
        "measurements": [{"name": n, "spice": card, "unit": u} for n, card, u in measurements],
        "options": {"timeout_s": timeout_s, "keep_artifacts": True, "waveforms": True},
    }


def _entry(name, role, supply, request, deck_text, units, meas_names, **extra) -> dict:
    return {
        "name": name,
        "role": role,
        "supply_v": supply,
        "analysis": request["analysis"],
        "measurements": meas_names,
        "expected_units": units,
        "deck_sha256": fc.sha256_bytes(deck_text.encode()),
        "request_sha256": fc.sha256_bytes((json.dumps(request, indent=2) + "\n").encode()),
        **extra,
    }


def build_plan(bench: str, tb: dict, *, design_include: Path, dut: Path, tb_netlist: Path,
               dut_rel: str, submitting_klt_version: str | None = None) -> tuple[dict, dict[str, str]]:
    """Pure builder -> (plan, files) where files maps ``<request>/request.json``
    and ``<request>/body.spice`` (and ``plan.json``) to their text."""
    if bench not in SUPPORTED:
        raise ValueError(f"unsupported bench {bench!r}; supported: {', '.join(SUPPORTED)}")
    load_spec = load_sweep_spec(tb) if bench == LOAD_BENCH else None
    if load_spec is not None and any(
            ln.strip().lower().startswith(".include") for ln in Path(dut).read_text().splitlines()):
        raise ValueError(f"DUT {dut_rel} .includes other files; the fleet stages only the deck -- flatten it first")
    nominal = tb["nominal_supply_v"]
    vdds = hc.supply_points(nominal, tb.get("supply_tolerance", 0.0))
    files: dict[str, str] = {}
    requests: list[dict] = []
    embedded = bench == "startup"

    if embedded:
        parts = (("design.ngspice (PDK)", design_include), ("testbench (embeds its own bandgap_top core)", tb_netlist))
    else:
        parts = (("design.ngspice (PDK)", design_include), ("DUT", dut), ("testbench", tb_netlist))

    def deck(name: str, vdd: float, extra=None) -> str:
        from mk_klt_request import inline_parts

        body = inline_parts(f"{bench}/{name}", parts, GENERATOR)
        return "\n".join([body[0]] + head_lines(tb, vdd, extra) + body[1:] + [""])

    if bench == "psrr-dc":
        text = deck("ac", nominal)
        ac = pick_analysis(tb, "ac")
        meas = [(f"vdb_{tag}", f".meas ac vdb_{tag} FIND vdb(vref) AT={f:g}", "dB") for tag, f in PSRR_SPOTS.items()]
        req = _req_common(tb, ac, meas, vdds, timeout_s=300)
        files["ac/body.spice"], files["ac/request.json"] = text, json.dumps(req, indent=2) + "\n"
        requests.append(_entry("ac", "ac", None, req, text, expected_units(tb, vdds), [m[0] for m in meas]))
        # operating-point companion
        step = (vdds[-1] - vdds[0]) / (len(vdds) - 1) if len(vdds) > 1 else 1.0
        dc_args = f"{SUPPLY_SOURCE} {vdds[0]:g} {vdds[-1]:g} {step:g}"
        opmeas = []  # values come from the returned waveform: ngspice's `.meas ... AT=` fails at a sweep's end points
        otext = deck("op", nominal)
        oreq = _req_common(tb, {"kind": "dc", "args": dc_args}, opmeas, None, timeout_s=300)
        files["op/body.spice"], files["op/request.json"] = otext, json.dumps(oreq, indent=2) + "\n"
        requests.append(_entry("op", "op", None, oreq, otext, expected_units(tb, [None]), [], supplies=vdds))
    elif bench == "line-regulation":
        dc = pick_analysis(tb, "dc")
        lo, hi, step = (float(x) for x in dc["args"].split()[1:4])
        meas = [
            ("vref_min", ".meas dc vref_min MIN v(vref)", "V"),
            ("vref_max", ".meas dc vref_max MAX v(vref)", "V"),
            ("v_lo_check", ".meas dc v_lo_check MIN v(vdd)", "V"),
            ("v_hi_check", ".meas dc v_hi_check MAX v(vdd)", "V"),
        ]
        text = deck("sweep", nominal)
        req = _req_common(tb, dc, meas, vdds, timeout_s=300)
        files["sweep/body.spice"], files["sweep/request.json"] = text, json.dumps(req, indent=2) + "\n"
        requests.append(_entry("sweep", "sweep", None, req, text, expected_units(tb, vdds), [m[0] for m in meas],
                               sweep={"lo": lo, "hi": hi, "step": step}))
    elif bench == LOAD_BENCH:
        dc = pick_analysis(tb, "dc")
        meas = [  # print-precision cross-check only; every reported figure comes from the waveform
            ("vref_min", ".meas dc vref_min MIN v(vref)", "V"),
            ("vref_max", ".meas dc vref_max MAX v(vref)", "V"),
        ]
        text = deck("sweep", nominal)
        req = _req_common(tb, dc, meas, vdds, timeout_s=300)
        files["sweep/body.spice"], files["sweep/request.json"] = text, json.dumps(req, indent=2) + "\n"
        requests.append(_entry("sweep", "sweep", None, req, text, expected_units(tb, vdds), [m[0] for m in meas],
                               load_sweep=load_spec))
    else:  # startup
        tran = pick_analysis(tb, "tran")
        params = dict(tb.get("params", {}))
        for v in vdds:
            name = f"vdd_{supply_tag(v)}"
            text = deck(name, v, params)
            req = _req_common(tb, tran, [], None, timeout_s=900)
            files[f"{name}/body.spice"], files[f"{name}/request.json"] = text, json.dumps(req, indent=2) + "\n"
            requests.append(_entry(name, "tran", v, req, text, expected_units(tb, [None]), []))

    plan = {
        "schema": PLAN_SCHEMA,
        "bench": bench,
        "submitting_klt_version": submitting_klt_version,
        "dut": {"path": dut_rel, "sha256": fc.sha256_file(dut)},
        "embedded_core": embedded,
        "tb_netlist_sha256": fc.sha256_file(tb_netlist),
        "manifest_sha256": fc.sha256_bytes((SIM / bench / "testbench" / "tb.json").read_bytes()),
        "nominal_supply_v": nominal,
        "supplies_v": vdds,
        "requests": requests,
    }
    if load_spec is not None:
        plan["dut"]["provenance_class"] = dut_provenance_class(dut_rel)
        plan["scope"] = ("characterization-only: output-load sensitivity of the DUT named above; exploratory "
                         "measurement range, not a supported-load rating; no spec threshold")
    files["plan.json"] = json.dumps(plan, indent=2) + "\n"
    return plan, files


def klt_version() -> str | None:
    import subprocess

    try:
        out = subprocess.run(["klt", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.split()[-1] if out else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bench", choices=SUPPORTED)
    ap.add_argument("outdir")
    ap.add_argument("--dut", default="sim/dut/bandgap_top.spice",
                    help="DUT to inline (repo-relative), e.g. a regenerated extracted netlist under layout/")
    a = ap.parse_args()

    from mk_klt_request import hc_pdk

    tb = json.loads((SIM / a.bench / "testbench" / "tb.json").read_text())
    dut = (REPO / a.dut).resolve()
    plan, files = build_plan(
        a.bench, tb,
        design_include=hc_pdk().design_include, dut=dut,
        tb_netlist=SIM / a.bench / "testbench" / tb["netlist"],
        dut_rel=str(dut.relative_to(REPO)), submitting_klt_version=klt_version(),
    )
    out = Path(a.outdir).resolve()
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    print(f"wrote {out}/plan.json ({len(plan['requests'])} request(s)); NOT dispatched.")
    if a.bench in CHARACTERIZATION_BENCHES:
        print(f"  characterization only -- ingest with: python3 sim/tools/load_ingest.py {out} --dut {plan['dut']['path']}")
    for r in plan["requests"]:
        n = len(r["expected_units"])
        print(f"  {r['name']}: {n} corner unit(s) -> klt sim --backend batch -o {out}/{r['name']}/out "
              f"{out}/{r['name']}/request.json --format json > {out}/{r['name']}/report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
