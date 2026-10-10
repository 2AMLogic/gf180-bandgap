#!/usr/bin/env python3
"""Fixture checks for the output-voltage-tc fleet ingestion (issue #209).

No PDK, ngspice or fleet required:

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import mk_klt_request as mk  # noqa: E402
import tc_ingest as ti  # noqa: E402

TB = ti.load_tb()
EXPECTED = ti.expected_points(TB)


def curve_fn(t, vmid=1.2, bow=-2e-6, lin=0.0):
    return vmid + lin * (t - 27) + bow * (t - 27) ** 2 / 100


def good_vals(vmid=1.2, bow=-2e-6, lin=0.0, curve=True):
    ts = range(-40, 126)
    vs = [curve_fn(t, vmid, bow, lin) for t in ts]
    vals = {
        "vref_m40": curve_fn(-40, vmid, bow, lin),
        "vref_27": curve_fn(27, vmid, bow, lin),
        "vref_125": curve_fn(125, vmid, bow, lin),
        "vref_box_max": max(vs),
        "vref_box_min": min(vs),
    }
    if curve:
        for t in range(-40, 126, 5):
            vals["vref_t" + str(t).replace("-", "m")] = curve_fn(t, vmid, bow, lin)
    return vals


def corner(key, vals, status="pass", diag=None):
    p, v = key
    return {
        "corner_id": f"{p}/{v:.3f}V/27C",
        "status": status,
        "measurements": [{"name": k, "value": x} for k, x in vals.items()],
        "diagnostics": diag or [],
    }


def report(vals_by_key=None, skip=(), override=None):
    cs = []
    for key in EXPECTED:
        if key in skip:
            continue
        if override and key in override:
            cs.append(override[key])
            continue
        cs.append(corner(key, (vals_by_key or {}).get(key, good_vals())))
    return {"corners": cs}


def run(rep):
    pts, miss, fail, prob = ti.collect(rep, EXPECTED)
    return pts, miss, fail, prob, ti.assess(pts, miss, fail, prob, TB)


class Matrix(unittest.TestCase):
    def test_expected_is_full_process_supply_matrix(self):
        self.assertEqual(len(EXPECTED), 27)
        self.assertEqual({v for _, v in EXPECTED}, {2.97, 3.3, 3.63})
        self.assertEqual(
            {p for p, _ in EXPECTED},
            {"tt", "ff", "ss", "fs", "sf", "res_ff", "res_ss", "bjt_ff", "bjt_ss"},
        )

    def test_request_covers_same_matrix(self):
        # the request helper and the ingestion read the same tb.json
        names = [c.name for c in mk.hc.resolve_corners(TB["corners"])]
        self.assertEqual(sorted(set(p for p, _ in EXPECTED)), sorted(names))


class Tc(unittest.TestCase):
    def test_box_tc_formula(self):
        # (1.2010 - 1.1990)/(1.2 * 165) * 1e6
        self.assertAlmostEqual(ti.box_tc_ppm(1.2010, 1.1990, 1.2), 0.002 / (1.2 * 165) * 1e6, places=9)
        self.assertAlmostEqual(ti.box_tc_ppm(1.2010, 1.1990, 1.2), 10.101010, places=5)

    def test_tc_uses_full_box_not_three_points(self):
        v = good_vals()
        v["vref_box_max"] += 0.01  # a peak the three endpoints miss
        pts, miss, fail, prob, res = run(report({EXPECTED[0]: v}))
        row = res["rows"][EXPECTED[0]]
        self.assertAlmostEqual(row["tc_ppm"], ti.box_tc_ppm(v["vref_box_max"], v["vref_box_min"], v["vref_27"]))
        self.assertGreater(row["tc_ppm"], 50)  # failed on the box, though endpoints are flat
        self.assertFalse(row["tc_ok"])

    def test_curve_helpers(self):
        c = ti.curve_of(good_vals())
        self.assertEqual(min(c), -40)
        self.assertEqual(max(c), 125)
        self.assertIn(-5, c)
        self.assertGreater(ti.curve_tc_ppm(c), 0)


class Verdicts(unittest.TestCase):
    def test_all_good_passes(self):
        *_, res = run(report())
        self.assertEqual(res["overall"], "PASS")

    def test_vref_window_edges(self):
        for vmid, ok in ((1.176, True), (1.1755, False), (1.224, True), (1.2245, False)):
            v = good_vals(vmid=vmid, bow=0.0)
            *_, res = run(report({EXPECTED[3]: v}))
            self.assertEqual(res["rows"][EXPECTED[3]]["vref_ok"], ok, vmid)
            self.assertEqual(res["overall"], "PASS" if ok else "FAIL")

    def test_accuracy_checked_on_box_extrema_not_just_endpoints(self):
        v = good_vals()
        v["vref_box_max"] = 1.23  # beyond the window mid-sweep only
        *_, res = run(report({EXPECTED[0]: v}))
        self.assertFalse(res["rows"][EXPECTED[0]]["vref_ok"])
        self.assertEqual(res["overall"], "FAIL")

    def test_tc_threshold_edge(self):
        span = 49.999 * 1.2 * 165 / 1e6
        v = good_vals(bow=0.0)
        v["vref_box_max"], v["vref_box_min"] = 1.2 + span / 2, 1.2 - span / 2
        *_, res = run(report({EXPECTED[0]: v}))
        self.assertTrue(res["rows"][EXPECTED[0]]["tc_ok"])  # just under the <= 50 limit passes
        v["vref_box_max"] += 1e-5  # now ~50.05 ppm/C
        *_, res = run(report({EXPECTED[0]: v}))
        self.assertFalse(res["rows"][EXPECTED[0]]["tc_ok"])
        self.assertEqual(res["overall"], "FAIL")


class Completeness(unittest.TestCase):
    def test_missing_corner_is_incomplete_never_pass(self):
        pts, miss, fail, prob, res = run(report(skip=[EXPECTED[5]]))
        self.assertEqual([k for k, _ in miss], [EXPECTED[5]])
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_backend_error_is_visible(self):
        bad = corner(EXPECTED[1], {k: None for k in good_vals()}, status="error",
                     diag=[{"code": "batch_job_failed", "message": "boom"}])
        pts, miss, fail, prob, res = run(report(override={EXPECTED[1]: bad}))
        self.assertEqual([k for k, _ in fail], [EXPECTED[1]])
        self.assertIn("boom", fail[0][1])
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_finite_values_with_invalid_execution_give_no_verdict(self):
        for kw in ({"status": "weird"}, {"status": "inconclusive"},
                   {"diag": [{"severity": "error", "code": "simulation_failed", "message": "boom"}]}):
            bad = corner(EXPECTED[1], good_vals(), **kw)
            pts, miss, fail, prob, res = run(report(override={EXPECTED[1]: bad}))
            self.assertEqual([k for k, _ in fail], [EXPECTED[1]])
            self.assertNotIn(EXPECTED[1], pts)
            self.assertEqual(res["overall"], "INCOMPLETE")

    def test_null_measurement_is_missing(self):
        v = good_vals()
        v["vref_box_min"] = None
        pts, miss, fail, prob, res = run(report({EXPECTED[2]: v}))
        self.assertTrue(miss or fail)
        self.assertNotIn(EXPECTED[2], pts)
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_all_error_report_is_incomplete(self):
        cs = [corner(k, {n: None for n in good_vals()}, status="error") for k in EXPECTED]
        pts, miss, fail, prob, res = run({"corners": cs})
        self.assertEqual(len(fail), 27)
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_duplicate_and_unexpected_corners(self):
        rep = report()
        rep["corners"].append(corner(EXPECTED[0], good_vals()))
        rep["corners"].append(corner(("zz", 3.3), good_vals()))
        *_, prob, res = run(rep)
        self.assertEqual(len(prob), 2)
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_failure_does_not_mask_missing(self):
        v = good_vals(vmid=1.3, bow=0.0)
        *_, res = run(report({EXPECTED[0]: v}, skip=[EXPECTED[1]]))
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_truncated_sweep_is_detected(self):
        # box extrema that do not bracket the sampled temperature points:
        # a sweep that stopped early / a stale measurement
        v = good_vals(bow=-2e-6)
        v["vref_box_max"] = v["vref_27"] - 1e-3
        *_, res = run(report({EXPECTED[0]: v}))
        self.assertTrue(res["rows"][EXPECTED[0]]["sweep_errs"])
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_sample_must_span_endpoints(self):
        v = good_vals()
        del v["vref_t125"]
        errs = ti.sweep_consistency(v)
        self.assertTrue(any("span" in e for e in errs))


class Reconstruct(unittest.TestCase):
    def test_affine_in_r1(self):
        # Vref(T) = a(T) + b(T) * R1, exactly affine
        def vals(r1):
            return {f"vref_t{str(t).replace('-', 'm')}": 0.7 - 1.7e-3 * (t - 27) + (1e-5 + 1e-8 * t) * r1
                    for t in range(-40, 126, 5)}
        va, vb = vals(70000.0), vals(80000.0)
        got = ti.reconstruct(va, vb, 70000.0, 80000.0, 75500.0)
        want = ti.curve_of(vals(75500.0))
        for t in want:
            self.assertAlmostEqual(got[t], want[t], places=9)


if __name__ == "__main__":
    unittest.main()
