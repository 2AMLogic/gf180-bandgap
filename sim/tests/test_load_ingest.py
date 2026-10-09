#!/usr/bin/env python3
"""Fixture checks for the output-load-sensitivity characterization (#269).

No PDK, ngspice, fleet credentials or network: the PDK include is a stub
file and every klt report / waveform is synthesized.

    python3 -m unittest discover -s sim/tests -t sim/tests -p test_load_ingest.py -v
"""

from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import fleet_common as fc  # noqa: E402
import fleet_ingest as fi  # noqa: E402
import load_ingest as li  # noqa: E402
import mk_klt_fleet_request as mk  # noqa: E402
from harness import evidence_lint  # noqa: E402
from suite import analysis, spec as suite_spec  # noqa: E402

BENCH = "output-load-sensitivity"
DUT = REPO / "sim" / "dut" / "bandgap_top.spice"
REMOTE = {
    "provider": "aws-batch", "job_id": "job-1", "instance_type": "c7a", "lifecycle": "spot", "state": "SUCCEEDED",
    "exit_code": 0, "runner_klt_version": "0.7.0+gtest", "client_klt_version": "0.7.0+gtest", "runner_compatibility": "match",
}
GIT = {"short": "abc1234", "commit": "abc1234", "branch": "test", "dirty": False}
R_OUT = 103e3  # V/A: a plausible unbuffered-node resistance for the synthetic curves


def grid(lo=-1e-6, hi=2e-6, step=1e-8):
    n = round((hi - lo) / step) + 1
    return [lo + i * step for i in range(n)]


def load_wave(supply=3.3, v0=1.2, r=R_OUT, f=None, x=None, sense=lambda i: i):
    """Synthetic klt waveform: sweep axis first (klt contract), v(vref) =
    f(i) (default linear v0 - r*i), v(vdd) at the corner supply, and the
    ammeter in ngspice's ``#branch`` spelling."""
    x = grid() if x is None else x
    f = f or (lambda i: v0 - r * i)
    return {"i-sweep": x, "v(vref)": [f(i) for i in x], "v(vdd)": [supply] * len(x),
            "vlsense#branch": [sense(i) for i in x]}


def write_wave(path: Path, cols: dict) -> str:
    rows = [list(r) for r in zip(*cols.values())]
    path.write_text(json.dumps({"plotname": "dc", "variables": [{"index": i, "name": n, "type": "x"}
                                                                for i, n in enumerate(cols)], "points": rows}))
    return str(path)


class Fixture:
    """A synthetic work dir (plan, deck, report, waveforms) for the load bench."""

    def __init__(self, tmp: Path, *, wave=None, vals=None, dut=DUT, dut_rel="sim/dut/bandgap_top.spice"):
        self.tmp = tmp
        self.tb = fi.load_tb(BENCH)
        (tmp / "design.ngspice").write_text("* stub pdk include\n")
        self.plan, files = mk.build_plan(
            BENCH, self.tb, design_include=tmp / "design.ngspice", dut=dut,
            tb_netlist=SIM / BENCH / "testbench" / self.tb["netlist"], dut_rel=dut_rel,
            submitting_klt_version="0.7.0+gtest")
        for rel, text in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.wave = wave or (lambda p, s, t: load_wave(supply=s))
        self.vals = vals
        self.reports = {"sweep": self.make_report(self.plan["requests"][0])}

    def make_report(self, r):
        corners = []
        d = self.tmp / r["name"] / "out"
        d.mkdir(parents=True, exist_ok=True)
        for p, s, t in r["expected_units"]:
            cid = f"{p}/{s:.3f}V/{t:g}C"
            w = self.wave(p, s, t)
            art = {}
            if w is not None:
                slug = cid.replace("/", "_")
                art["waveform"] = write_wave(d / f"{slug}.json", w)
                (d / f"{slug}.log").write_text(f"ngspice log {cid}\n")
                art["log"] = str(d / f"{slug}.log")
            if self.vals:
                vals = self.vals(p, s, t)
            elif w is not None:
                vals = {"vref_min": float(f"{min(w['v(vref)']):e}"), "vref_max": float(f"{max(w['v(vref)']):e}")}
            else:
                vals = {"vref_min": 1.0, "vref_max": 1.3}
            corners.append({"corner_id": cid, "status": "pass", "diagnostics": [],
                            "measurements": [{"name": k, "value": v} for k, v in vals.items()], "artifacts": art})
        return {"corners": corners, "environment": {"engine": "ngspice", "engine_version": "46", "remote": dict(REMOTE)},
                "provenance": {"klt_version": "0.7.0+gtest", "pdk": {"name": "gf180mcuD", "version": "x"}}}

    def decks(self):
        return {"sweep": (self.tmp / "sweep" / "body.spice").read_text()}

    def assess(self, **kw):
        kw.setdefault("dut_sha", fc.sha256_file(DUT))
        kw.setdefault("dut_label", self.plan["dut"]["path"])
        kw.setdefault("decks", self.decks())
        return li.assess(self.tb, self.plan, self.reports, self.tmp, **kw)


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.tb = fi.load_tb(BENCH)
        self.spec = mk.load_sweep_spec(self.tb)

    def fx(self, **kw):
        return Fixture(self.tmp, **kw)

    def derive(self, wave, supply=3.3, vals=None):
        return li.derive_load(vals, wave, self.spec, supply)


# ---------------------------------------------------------------- manifest


class Manifest(TmpCase):
    def test_defines_direction_units_range_baseline_and_slope(self):
        ls = self.tb["load_sweep"]
        self.assertIn("SUNK out of vref", ls["direction"])
        self.assertEqual(set(ls["units"]), {"current", "voltage", "slope"})
        self.assertIn("mV/uA", ls["units"]["slope"])
        self.assertIn("not a supported-load rating", ls["exploratory_range"]["label"])
        self.assertIn("exactly 0 A", ls["baseline"])
        self.assertIn("central difference", ls["slope"]["method"])
        self.assertEqual(self.spec["n_points"], 301)
        self.assertEqual(self.spec["baseline_index"], 100)
        self.assertEqual(self.spec["slope_steps"], [1, 2, 4])
        self.assertIn("CHARACTERIZATION ONLY", self.tb["claim"])

    def test_no_spec_threshold_anywhere(self):
        self.assertLessEqual(set(self.tb["checks"]), mk.LOAD_SANITY_CHECKS)
        for name in self.tb["checks"]:
            self.assertIn("Not a spec check", self.tb["checks"][name]["description"])
        # not graded: kept out of the spec-row benches, the ingest spec checks and the suite
        self.assertNotIn(BENCH, mk.BENCHES)
        self.assertNotIn(BENCH, fi.SPEC_CHECKS)
        self.assertNotIn(BENCH, suite_spec.slugs())
        self.assertIn("Load", [u.row for u in suite_spec.NOT_CLAIMED_HERE])

    def test_harness_measure_indices_agree_with_the_grid(self):
        k0, n = self.spec["baseline_index"], self.spec["n_points"]
        self.assertEqual(self.tb["measure"]["vref_unloaded"], f"dc1.v(vref)[{k0}]")
        self.assertEqual(self.tb["checks"]["sweep_points"]["min"], n)
        self.assertIn(f"[{n - 1}]", self.tb["measure"]["shift_mv_sink_2u"])

    def bad(self, mutate):
        tb = copy.deepcopy(self.tb)
        mutate(tb)
        with self.assertRaises(ValueError):
            mk.load_sweep_spec(tb)

    def test_rejects_inconsistent_or_unresolvable_definitions(self):
        self.bad(lambda tb: tb["analyses"].__setitem__(0, "dc iload -1u 2u 20n"))  # card != load_sweep
        self.bad(lambda tb: tb["analyses"].__setitem__(0, "dc vsup -1u 2u 10n"))  # wrong source
        def off_grid(tb):  # 0 A falls between points: no unloaded baseline
            tb["analyses"][0] = "dc iload -1.005u 2u 10n"
            tb["load_sweep"]["exploratory_range"]["lo_a"] = -1.005e-6
        self.bad(off_grid)
        def coarse(tb):  # 2 points below 0 A: insufficient resolution for the step check
            tb["analyses"][0] = "dc iload -1u 2u 0.5u"
            tb["load_sweep"]["exploratory_range"]["step_a"] = 5e-7
            tb["load_sweep"]["report_points_a"] = [-1e-6, 1e-6]
        self.bad(coarse)
        def one_sided(tb):
            tb["analyses"][0] = "dc iload 0 2u 10n"
            tb["load_sweep"]["exploratory_range"]["lo_a"] = 0.0
        self.bad(one_sided)
        self.bad(lambda tb: tb["load_sweep"]["report_points_a"].append(1.234e-7))  # off grid
        self.bad(lambda tb: tb["load_sweep"]["exploratory_range"].__setitem__("label", "supported load range"))
        self.bad(lambda tb: tb["checks"].__setitem__("slope_mv_per_ua", {"max": 0.0}))  # a threshold sneaking in
        self.bad(lambda tb: tb.pop("load_sweep"))


# ---------------------------------------------------------------- requests


class Requests(TmpCase):
    def test_request_covers_process_temperature_and_supply(self):
        f = self.fx()
        req = json.loads((self.tmp / "sweep" / "request.json").read_text())
        self.assertEqual(req["analysis"], {"kind": "dc", "args": "iload -1u 2u 10n"})
        self.assertEqual(req["corners"]["supply_v"], {"vsup": [2.97, 3.3, 3.63]})
        self.assertEqual([p["name"] for p in req["corners"]["process"]],
                         [c.name for c in fi.hc.resolve_corners(self.tb["corners"])])
        self.assertEqual(len(req["corners"]["process"]), 9)
        self.assertEqual(req["corners"]["temperature_c"], [-40, 27, 125])
        self.assertTrue(req["options"]["waveforms"] and req["options"]["keep_artifacts"])
        self.assertEqual(len(f.plan["requests"][0]["expected_units"]), 81)
        self.assertEqual(len(fi.expected_grid(self.tb)), 81)
        self.assertEqual(fi.plan_problems(BENCH, self.tb, f.plan), [])

    def test_plan_records_identity_and_scope(self):
        f = self.fx()
        self.assertEqual(f.plan["dut"], {"path": "sim/dut/bandgap_top.spice", "sha256": fc.sha256_file(DUT),
                                         "provenance_class": "schematic"})
        self.assertTrue(f.plan["scope"].startswith("characterization-only"))
        self.assertIn("not a supported-load rating", f.plan["scope"])
        self.assertEqual(f.plan["requests"][0]["load_sweep"], self.spec)
        deck = f.decks()["sweep"]
        self.assertEqual(deck.lower().count(".subckt bandgap_top"), 1)
        self.assertIn("begin inlined DUT", deck)
        self.assertIn("vlsense vref nl dc 0", deck)
        self.assertEqual(f.plan["requests"][0]["deck_sha256"], fc.sha256_bytes(deck.encode()))

    def test_supplied_extracted_dut_is_labelled_extracted(self):
        f = self.fx(dut=DUT, dut_rel="layout/netlist/bandgap_top_extracted.spice")
        self.assertEqual(f.plan["dut"]["provenance_class"], "extracted")
        self.assertEqual(mk.dut_provenance_class("sim/dut/frozen/x.spice"), "frozen schematic")

    def test_dut_with_include_is_refused(self):
        d = self.tmp / "inc.spice"
        d.write_text(".subckt bandgap_top vdd vss vref\n.include parasitics.spice\n.ends\n")
        with self.assertRaises(ValueError):
            Fixture(self.tmp, dut=d, dut_rel="layout/netlist/inc.spice")

    def test_existing_benches_unchanged(self):
        self.assertEqual(mk.BENCHES, ("psrr-dc", "line-regulation", "startup"))
        self.assertEqual(fi.BENCHES, ("psrr-dc", "line-regulation", "startup"))


# ---------------------------------------------------------------- derivation


class Derive(TmpCase):
    def test_linear_slope_sign_and_units(self):
        m, errs = self.derive(load_wave())
        self.assertEqual(errs, [])
        self.assertAlmostEqual(m["vref_unloaded_v"], 1.2, places=12)
        self.assertAlmostEqual(m["slope_mv_per_ua"], -103.0, places=6)  # -103 kOhm -> -103 mV per uA sunk
        self.assertAlmostEqual(m["zout_kohm"], 103.0, places=6)
        self.assertAlmostEqual(m["shift_mv_sink_1u"], -103.0, places=6)  # sinking lowers vref: negative shift
        self.assertAlmostEqual(m["shift_mv_sink_2u"], -206.0, places=6)
        self.assertAlmostEqual(m["shift_mv_source_1u"], 103.0, places=6)
        self.assertAlmostEqual(m["shift_mv_sink_100n"], -10.3, places=6)
        self.assertAlmostEqual(m["shift_mv_source_500n"], 51.5, places=6)
        self.assertLess(m["slope_step_spread_pct"], 1e-6)
        self.assertLess(m["nonlin_max_mv"], 1e-6)
        self.assertEqual(m["monotonic"], 1.0)
        self.assertEqual(m["sweep_points"], 301.0)
        self.assertAlmostEqual(m["i_lo_ua"], -1.0)
        self.assertAlmostEqual(m["i_hi_ua"], 2.0)

    def test_report_point_names(self):
        self.assertEqual([li.shift_name(i) for i in self.spec["report_points"]],
                         ["shift_mv_source_1u", "shift_mv_source_500n", "shift_mv_source_100n", "shift_mv_sink_100n",
                          "shift_mv_sink_500n", "shift_mv_sink_1u", "shift_mv_sink_2u"])

    def test_positive_slope_is_reported_with_its_sign(self):
        m, errs = self.derive(load_wave(r=-50e3))  # a node that RISES when loaded: sign must survive
        self.assertEqual(errs, [])
        self.assertAlmostEqual(m["slope_mv_per_ua"], 50.0, places=6)
        self.assertAlmostEqual(m["zout_kohm"], -50.0, places=6)
        self.assertGreater(m["shift_mv_sink_1u"], 0)

    def test_nonlinear_curve_tangent_and_one_sided_slopes(self):
        c = 1e10  # V/A^2: 40 mV of curvature at +2 uA
        m, errs = self.derive(load_wave(f=lambda i: 1.2 - R_OUT * i - c * i * i))
        self.assertEqual(errs, [])
        self.assertAlmostEqual(m["slope_mv_per_ua"], -103.0, places=5)  # central difference cancels the quadratic
        self.assertAlmostEqual(m["nonlin_max_mv"], 40.0, places=6)
        self.assertAlmostEqual(m["nonlin_at_ua"], 2.0, places=9)
        self.assertAlmostEqual(m["shift_mv_sink_2u"], -206.0 - 40.0, places=6)
        self.assertAlmostEqual(m["shift_mv_source_1u"], 103.0 - 10.0, places=6)
        self.assertLess(m["slope_sink_side_mv_per_ua"], m["slope_source_side_mv_per_ua"])

    def test_collapse_is_recorded_not_judged(self):
        def f(i):  # flat-then-falling: the node collapses past +1.5 uA
            return 1.2 - R_OUT * i - (5e5 * (i - 1.5e-6) if i > 1.5e-6 else 0.0)
        m, errs = self.derive(load_wave(f=f))
        self.assertEqual(errs, [])
        self.assertGreater(m["nonlin_max_mv"], 200.0)

    def test_feature_finer_than_the_grid_is_insufficient_resolution(self):
        w = 3e-8  # a tanh feature 3 grid steps wide: the slope moves with the step size
        m, errs = self.derive(load_wave(f=lambda i: 1.2 - 3e-3 * math.tanh(i / w)))
        self.assertTrue(any("not resolved" in e and "step-size" in e for e in errs), errs)
        self.assertGreater(m["slope_step_spread_pct"], 1.0)

    def test_coarse_axis_is_insufficient_resolution(self):
        x = grid(step=5e-7)  # -1 .. 2 uA in 0.5 uA steps: 2 points below 0 A
        m, errs = self.derive(load_wave(x=x))
        self.assertTrue(any(e.startswith("insufficient resolution") for e in errs), errs)
        self.assertTrue(any("of the manifest's 301 points" in e for e in errs), errs)

    def test_incomplete_sweep(self):
        w = {k: v[:250] for k, v in load_wave().items()}  # the solver stopped at +1.5 uA
        m, errs = self.derive(w)
        self.assertTrue(any("incomplete sweep: 250 of the manifest's 301" in e for e in errs), errs)
        self.assertTrue(any("spans" in e for e in errs), errs)
        w = {k: v[:2] for k, v in load_wave().items()}
        m, errs = self.derive(w)
        self.assertIsNone(m)

    def test_missing_baseline(self):
        x = [i + 5e-9 for i in grid()]  # half a step off: 0 A is not a grid point
        m, errs = self.derive(load_wave(x=x))
        self.assertIsNone(m)
        self.assertTrue(errs[0].startswith("missing baseline"), errs)

    def test_reversed_or_mis_scaled_sense_current(self):
        m, errs = self.derive(load_wave(sense=lambda i: -i))
        self.assertTrue(any("REVERSED" in e for e in errs), errs)
        m, errs = self.derive(load_wave(sense=lambda i: i * 1e6))  # uA where A was expected
        self.assertTrue(any("disagrees with the sweep" in e and "sign/units" in e for e in errs), errs)

    def test_supply_not_applied(self):
        m, errs = self.derive(load_wave(supply=3.3), supply=2.97)
        self.assertTrue(any("not the corner's 2.9700 V" in e for e in errs), errs)

    def test_non_finite_waveform(self):
        w = load_wave()
        w["v(vref)"][150] = float("nan")
        m, errs = self.derive(w)
        self.assertIsNone(m)
        self.assertIn("non-finite", errs[0])
        w = load_wave()
        w["i-sweep"][3] = float("inf")
        self.assertIsNone(self.derive(w)[0])

    def test_missing_columns_and_no_waveform(self):
        w = load_wave()
        del w["vlsense#branch"]
        self.assertIsNone(self.derive(w)[0])
        self.assertIsNone(self.derive(None)[0])

    def test_meas_cross_check(self):
        w = load_wave()
        ok = {"vref_min": float(f"{min(w['v(vref)']):e}"), "vref_max": float(f"{max(w['v(vref)']):e}")}
        self.assertEqual(self.derive(w, vals=ok)[1], [])
        bad = dict(ok, vref_max=ok["vref_max"] + 1e-3)
        self.assertTrue(any("disagrees" in e for e in self.derive(w, vals=bad)[1]))


# ---------------------------------------------------------------- run assessment


class Assess(TmpCase):
    def test_complete_run(self):
        res = self.fx().assess()
        self.assertEqual(res["overall"], "COMPLETE", res["problems"] + list(map(str, res["invalid"].values())))
        self.assertEqual(len(res["rows"]), 81)
        self.assertNotIn(res["overall"], ("PASS", "FAIL"))

    def test_per_corner_supply_is_checked(self):
        res = self.fx(wave=lambda p, s, t: load_wave(supply=3.3)).assess()  # the alter never took effect
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["invalid"]), 54)

    def test_incomplete_sweep_at_one_corner(self):
        def wave(p, s, t):
            w = load_wave(supply=s)
            return {k: v[:200] for k, v in w.items()} if (p, s, t) == ("ss", 2.97, -40.0) else w
        res = self.fx(wave=wave).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(list(res["invalid"]), [("ss", -40.0, 2.97)])

    def test_missing_baseline_everywhere(self):
        res = self.fx(wave=lambda p, s, t: load_wave(supply=s, x=[i + 5e-9 for i in grid()])).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(res["rows"], {})
        self.assertTrue(all("missing baseline" in why for why in res["invalid"].values()))

    def test_non_finite_measurement(self):
        f = self.fx()
        f.reports["sweep"]["corners"][4]["measurements"][0]["value"] = float("nan")
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertIn("non-finite", res["missing"][0][1])

    def test_missing_corner_backend_error_and_missing_report(self):
        f = self.fx()
        f.reports["sweep"]["corners"].pop(3)
        c = f.reports["sweep"]["corners"][0]
        c["status"], c["measurements"] = "error", []
        c["diagnostics"] = [{"code": "batch_job_failed", "message": "boom"}]
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(res["missing"] and res["failed"])
        del f.reports["sweep"]
        res = f.assess()
        self.assertEqual(len(res["missing"]), 81)
        self.assertEqual(len(res["invalid"]), 81)

    def test_duplicate_and_unexpected_corners(self):
        f = self.fx()
        cs = f.reports["sweep"]["corners"]
        cs.append(copy.deepcopy(cs[0]))
        extra = copy.deepcopy(cs[0])
        extra["corner_id"] = "zz" + extra["corner_id"][2:]
        cs.append(extra)
        probs = f.assess()["problems"]
        self.assertTrue(any("duplicate" in p for p in probs) and any("unexpected" in p for p in probs), probs)

    def test_provenance_mismatches(self):
        cases = {
            "DUT sha256": dict(dut_sha="0" * 64),
            "DUT path": dict(dut_label="layout/netlist/bandgap_top_extracted.spice"),
            "testbench netlist": dict(tb_sha="1" * 64),
            "tb.json changed": dict(manifest_sha="1" * 64),
        }
        for needle, kw in cases.items():
            with self.subTest(needle=needle):
                res = self.fx().assess(**kw)
                self.assertEqual(res["overall"], "INCOMPLETE")
                self.assertTrue(any(needle in p for p in res["problems"]), res["problems"])
        f = self.fx()
        decks = f.decks()
        decks["sweep"] += "* tampered\n"
        self.assertTrue(any("deck sha256" in p for p in f.assess(decks=decks)["problems"]))

    def test_klt_version_and_remote_provenance(self):
        f = self.fx()
        f.reports["sweep"]["environment"]["remote"]["runner_compatibility"] = "mismatch"
        self.assertTrue(any("compatibility" in p for p in f.assess()["problems"]))
        f = self.fx()
        del f.reports["sweep"]["environment"]["remote"]
        self.assertTrue(any("not a fleet run" in p for p in f.assess()["problems"]))
        f = self.fx()
        f.plan["submitting_klt_version"] = "0.5.0"
        self.assertTrue(any("differs" in p for p in f.assess()["problems"]))

    def test_plan_tampering(self):
        f = self.fx()
        f.plan["requests"][0]["load_sweep"]["step"] = 2e-8
        self.assertTrue(any("load_sweep differs" in p for p in f.assess()["problems"]))
        f = self.fx()
        del f.plan["scope"]
        self.assertTrue(any("characterization-only scope" in p for p in f.assess()["problems"]))
        f = self.fx()
        f.plan["dut"]["provenance_class"] = "extracted"
        self.assertTrue(any("provenance class" in p for p in f.assess()["problems"]))
        f = self.fx()
        f.plan["requests"][0]["expected_units"].pop()
        self.assertTrue(f.assess()["problems"])

    def test_manifest_edited_into_a_threshold_is_a_problem(self):
        f = self.fx()
        tb = copy.deepcopy(f.tb)
        tb["checks"]["zout_kohm"] = {"max": 1.0}
        res = li.assess(tb, f.plan, f.reports, self.tmp, decks=f.decks())
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("non-sanity checks" in p for p in res["problems"]))


# ---------------------------------------------------------------- evidence


class Evidence(TmpCase):
    def mint(self, root: Path, fx: Fixture, **kw):
        res = fx.assess()
        exp = root / "sim" / BENCH
        rec = li.write_evidence(exp, self.tmp, fx.tb, fx.plan, res, fx.reports, issue=269, git=GIT, repo=root, **kw)
        return res, exp, rec

    def test_complete_record_identity_scope_and_linter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fx = self.fx()
            res, exp, rec = self.mint(root, fx)
            text = rec.read_text()
            self.assertIn("CHARACTERIZATION ONLY", text)
            self.assertIn("exploratory measurement range, not a supported-load rating", text)
            self.assertIn("No threshold is applied", text)
            self.assertIn("**Overall: COMPLETE**", text)
            self.assertNotIn("Overall: PASS", text)
            self.assertIn(fc.sha256_file(DUT), text)
            self.assertIn(fx.plan["requests"][0]["deck_sha256"], text)
            self.assertIn(fx.plan["requests"][0]["request_sha256"], text)
            self.assertIn("**Netlist provenance**: schematic.", text)
            self.assertIn("job `job-1`", text)
            self.assertIn("2.97 V, 3.30 V, 3.63 V", text)
            (cdir,) = list((exp / "corners").iterdir())
            self.assertTrue((exp / "netlist-snapshots" / f"{rec.stem}.spice").exists())
            samples = analysis.read_corner_logs(cdir)
            self.assertEqual(len(samples), 81)
            one = next(iter(samples.values()))
            self.assertAlmostEqual(one["slope_mv_per_ua"], -103.0, places=6)
            self.assertIn("shift_mv_sink_1u", one)
            self.assertTrue((cdir / "plan.json").exists() and (cdir / "report-sweep.json").exists())
            paths, _ = evidence_lint.list_evidence_paths(root)
            self.assertEqual(evidence_lint.check_experiments(root, evidence_lint.collect_experiments(paths)), [])

    def test_extracted_dut_record_says_extracted(self):
        with tempfile.TemporaryDirectory() as td:
            fx = Fixture(self.tmp, dut_rel="layout/netlist/bandgap_top_extracted.spice")
            res = fx.assess(dut_label="layout/netlist/bandgap_top_extracted.spice")
            self.assertEqual(res["overall"], "COMPLETE", res["problems"])
            rec = li.write_evidence(Path(td) / "sim" / BENCH, self.tmp, fx.tb, fx.plan, res, fx.reports,
                                    issue=269, git=GIT, repo=Path(td))
            self.assertIn("**Netlist provenance**: extracted.", rec.read_text())

    def test_incomplete_run_is_recorded_as_incomplete_with_invalid_logs(self):
        with tempfile.TemporaryDirectory() as td:
            fx = self.fx()
            fx.reports["sweep"]["corners"].pop(5)
            res, exp, rec = self.mint(Path(td), fx)
            text = rec.read_text()
            self.assertIn("**Overall: INCOMPLETE**", text)
            self.assertIn("nothing is characterized by this record", text)
            (cdir,) = list((exp / "corners").iterdir())
            logs = [p.read_text() for p in cdir.glob("*.log")]
            self.assertEqual(len(logs), 81)
            self.assertEqual(sum(fi.INVALID_POINT_MARKER in t for t in logs), 1)

    def test_provenance_mismatch_mints_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            fx = self.fx()
            res = fx.assess(dut_sha="0" * 64)
            exp = Path(td) / "sim" / BENCH
            with self.assertRaises(ValueError):
                li.write_evidence(exp, self.tmp, fx.tb, fx.plan, res, fx.reports, issue=269, git=GIT, repo=Path(td))
            self.assertFalse(exp.exists())

    def test_append_only_second_ingest_mints_a_new_record(self):
        with tempfile.TemporaryDirectory() as td:
            fx = self.fx()
            _, exp, r1 = self.mint(Path(td), fx)
            _, _, r2 = self.mint(Path(td), fx)
            self.assertNotEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
