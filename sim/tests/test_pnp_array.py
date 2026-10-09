#!/usr/bin/env python3
"""Small-fixture checks for the equal-Ie Q2 array bench (issue #208).

No PDK, ngspice or fleet required:

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import mk_klt_device_request as req  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "run_pnp_array", SIM / "device-pnp-array" / "run_pnp_array.py"
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

BENCH = (req.BENCH_DIR / req.BENCH).read_text()


def fake_report(skip=(), fail=()):
    vt_scale = {}
    corners = []
    for sec, t in req.expected_points():
        if (sec, t) in skip:
            continue
        vt = run.thermal_voltage(t)
        vals = {}
        for ua in req.CURRENTS_UA:
            vals[req.meas_name("u", ua)] = 0.70
            vals[req.meas_name("a", ua)] = 0.70 - vt * math.log(4.02)
            vals[req.meas_name("m", ua)] = 0.70 - vt * math.log(3.63)
        tl = f"{t:g}C"
        corners.append(
            {
                "corner_id": f"{sec}/novdd/{tl}",
                "status": "fail" if (sec, t) in fail else "pass",
                "measurements": [{"name": k, "value": v} for k, v in vals.items()],
            }
        )
    return {"corners": corners}


class Request(unittest.TestCase):
    def test_axes(self):
        r = req.build_request()
        self.assertEqual([p["name"] for p in r["corners"]["process"]], list(req.BJT_SECTIONS))
        self.assertEqual(r["corners"]["temperature_c"], [-40.0, 27.0, 125.0])  # degrees C
        self.assertNotIn("supply_v", r["corners"])  # device-only: no rail
        self.assertEqual(r["analysis"]["kind"], "dc")

    def test_design_current_is_a_sweep_point(self):
        # sweep 4.00..7.00 step 0.01: 5.07 and 6.5 land exactly on it
        _, lo, hi, step = req.SWEEP.split()
        for ua in req.CURRENTS_UA:
            self.assertAlmostEqual((ua - float(lo)) / float(step), round((ua - float(lo)) / float(step)), 6)
            self.assertTrue(float(lo) <= ua <= float(hi))
        self.assertEqual(req.DESIGN_UA, 5.07)

    def test_measurements_are_raw_meas_cards(self):
        for m in req.build_request()["measurements"]:
            self.assertIn("spice", m)
            self.assertNotIn("expr", m)
            self.assertTrue(m["spice"].startswith(f".meas dc {m['name']} FIND v("))
        names = [m["name"] for m in req.measurements()]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 3 * len(req.CURRENTS_UA))

    def _pairs(self, r):
        return [(p["name"], t) for p in r["corners"]["process"] for t in r["corners"]["temperature_c"]]

    def test_request_matches_expected_points(self):
        import json

        cases = [
            {},
            {"sections": ("bjt_ff", "bjt_ss"), "temps_c": (125.0, -40.0)},  # reordered subset
            {"sections": ("bjt_typical",), "temps_c": (27.0,)},
            {"sections": ("bjt_ff", "bjt_ss", "bjt_ff"), "temps_c": (125.0, 125.0, 27.0)},  # multiplicity
        ]
        for kw in cases:
            with self.subTest(**kw):
                r = req.build_request(**kw)
                self.assertEqual(self._pairs(r), req.expected_points(**kw))
                self.assertEqual(json.loads(json.dumps(r)), r)
                for p in r["corners"]["process"]:
                    self.assertEqual(p["sections"], [p["name"]])

    def test_meas_names_map_uniquely_to_branch_current(self):
        seen = {}
        for ua in req.CURRENTS_UA:
            for branch, node in req.BRANCHES.items():
                seen.setdefault(req.meas_name(branch, ua), (branch, ua, node))
        self.assertEqual(len(seen), len(req.BRANCHES) * len(req.CURRENTS_UA))
        for m in req.build_request()["measurements"]:
            branch, ua, node = seen[m["name"]]
            self.assertIn(f"FIND v({node}) AT={ua:g}", m["spice"])

    def test_empty_axis_rejected(self):
        with self.assertRaises(ValueError):
            req.build_request(sections=())
        with self.assertRaises(ValueError):
            req.build_request(temps_c=())


class Wiring(unittest.TestCase):
    def test_equal_total_ie_per_branch(self):
        srcs = re.findall(r"^(B\w+)\s+0\s+(\w+)\s+I\s*=\s*(.+)$", BENCH, re.M)
        self.assertEqual(len(srcs), 3)  # one source per branch, not per unit
        self.assertEqual({e for _, _, e in srcs}, {"v(ctrl) * 1e-6"})  # identical Ie
        self.assertEqual({n for _, n, _ in srcs}, {"eu", "ea", "em"})

    def test_unit_counts(self):
        cell = lambda node, model: len(  # noqa: E731
            re.findall(rf"^XQ\w+\s+0\s+\w+\s+{node}\s+{model}\b", BENCH, re.M)
        )
        self.assertEqual(cell("eu", "pnp_05p00x05p00"), 1)
        self.assertEqual(cell("ea", "pnp_05p00x05p00"), 4)
        self.assertEqual(cell("em", "pnp_10p00x10p00"), 1)

    def test_meas_nodes_match_branches(self):
        cards = {m["name"]: m["spice"] for m in req.measurements()}
        self.assertIn("v(ea)", cards["vbe_a_5p07"])
        self.assertIn("v(eu)", cards["vbe_u_5p07"])
        self.assertIn("AT=5.07", cards["vbe_u_5p07"])

    def test_fragment_has_no_control_cards(self):
        for card in (".include", ".lib", ".temp", ".control", ".end"):
            self.assertFalse(re.search(rf"^\s*{re.escape(card)}\b", BENCH, re.M | re.I), card)


class Extraction(unittest.TestCase):
    def test_a_eff_inverts_dvbe(self):
        for t in (-40.0, 27.0, 125.0):
            vt = run.thermal_voltage(t)
            self.assertAlmostEqual(run.a_eff(0.70, 0.70 - vt * math.log(4.0), t), 4.0, 9)

    def test_temperature_is_celsius(self):
        self.assertAlmostEqual(run.thermal_voltage(27.0), 0.025865, 5)
        self.assertAlmostEqual(run.thermal_voltage(-40.0), 0.020091, 5)

    def test_corner_id_parse(self):
        self.assertEqual(run.parse_corner_id("bjt_typical/novdd/-40C"), ("bjt_typical", -40.0))
        self.assertEqual(run.parse_corner_id("bjt_ss/novdd/125C"), ("bjt_ss", 125.0))

    def test_complete_report(self):
        pts, missing, failed = run.collect(fake_report(), req.expected_points())
        self.assertEqual((len(pts), missing, failed), (9, [], []))
        r = run.ratios(pts[("bjt_ff", 125.0)], 125.0)[req.DESIGN_UA]
        self.assertAlmostEqual(r["array"], 4.02, 6)
        self.assertAlmostEqual(r["mono"], 3.63, 6)

    def test_missing_corner_rejected(self):
        pts, missing, failed = run.collect(
            fake_report(skip={("bjt_ss", -40.0)}), req.expected_points()
        )
        self.assertEqual(missing, [("bjt_ss", -40.0)])
        self.assertEqual(len(pts), 8)

    def test_failed_corner_surfaced(self):
        pts, missing, failed = run.collect(
            fake_report(fail={("bjt_ff", 27.0)}), req.expected_points()
        )
        self.assertEqual(failed, [(("bjt_ff", 27.0), "fail")])
        self.assertEqual(missing, [])
        self.assertNotIn(("bjt_ff", 27.0), pts)

    def test_missing_measurement_is_missing(self):
        rep = fake_report()
        rep["corners"][0]["measurements"].pop()
        _, missing, _ = run.collect(rep, req.expected_points())
        self.assertEqual(len(missing), 1)

    def test_local_backend_refused(self):
        import os
        old = os.environ.get("KLT_SIM_BACKEND")
        os.environ["KLT_SIM_BACKEND"] = "local"
        try:
            with self.assertRaises(SystemExit):
                run.dispatch(Path("/nonexistent"))
        finally:
            if old is None:
                del os.environ["KLT_SIM_BACKEND"]
            else:
                os.environ["KLT_SIM_BACKEND"] = old


if __name__ == "__main__":
    unittest.main()
