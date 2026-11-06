#!/usr/bin/env python3
"""tb.json-driven fleet requests and their ingest to PointResult (issue #424).

No PDK, ngspice, fleet credentials or network: the PDK include is a stub file
and every klt report is synthesized.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import fleet_common as fc  # noqa: E402
import mk_klt_fleet_request as mk  # noqa: E402

REMOTE = {"provider": "aws-batch", "job_id": "job-424", "runner_klt_version": "0.7.0", "client_klt_version": "0.7.0",
          "runner_compatibility": "match"}

#: Every bench with a tb.json and no dedicated builder before #424, and the
#: verdict `classify_bench` must give (the table in sim/harness/README.md).
UNCOVERED = {
    "smoke-bias": True, "device-resistor-tc": True, "device-mos-vth": True, "device-pnp-vbe": True,
    "device-mos-mismatch": True, "device-pnp-mismatch": True,
    "amp-loop-stability": False, "amp-offset-sensitivity": False, "amp-psrr": False, "bandgap-loop-smoke": False,
    "core-mirror-sensitivity": False, "core-psrr-ideal-amp": False, "startup-disabled-control": False,
    "startup-extracted": False, "startup-slow-ramp": False, "startup-state-search": False,
    "startup-state-search-extracted": False, "trim-coverage": False,
}


def load(bench):
    tb = json.loads((SIM / bench / "testbench" / "tb.json").read_text())
    return tb, SIM / bench / "testbench" / tb["netlist"]


class Classify(unittest.TestCase):
    def test_every_uncovered_bench_is_classified(self):
        for bench, want in UNCOVERED.items():
            tb, net = load(bench)
            ok, why = mk.classify_bench(tb, net.read_text())
            self.assertEqual(ok, want, f"{bench}: {why}")
            self.assertTrue(why)
        self.assertEqual(sorted(b for b, w in UNCOVERED.items() if w), sorted(mk.GENERIC_BENCHES))

    def test_unsupported_bench_is_refused_by_build_plan(self):
        with tempfile.TemporaryDirectory() as d:
            inc = Path(d) / "design.ngspice"
            inc.write_text("* stub\n")
            tb, net = load("amp-psrr")
            with self.assertRaises(ValueError):
                mk.build_plan("amp-psrr", tb, design_include=inc, dut=inc, tb_netlist=net, dut_rel="x")


class Request(unittest.TestCase):
    def plan(self, bench, d):
        inc = Path(d) / "design.ngspice"
        inc.write_text("* stub pdk\n")
        tb, net = load(bench)
        plan, files = mk.build_plan(bench, tb, design_include=inc, dut=inc, tb_netlist=net, dut_rel="x",
                                    submitting_klt_version="0.7.0")
        return tb, plan, files

    def test_smoke_bias_request_comes_from_tb_json(self):
        with tempfile.TemporaryDirectory() as d:
            tb, plan, files = self.plan("smoke-bias", d)
            req = json.loads(files["run/request.json"])
            self.assertEqual(req["analysis"], {"kind": "op", "args": ""})
            self.assertEqual({m["name"]: m["expr"] for m in req["measurements"]}, tb["measure"])
            self.assertEqual(req["corners"]["temperature_c"], tb["temperatures_c"])
            self.assertEqual(req["corners"]["supply_v"], {"vsup": [2.97, 3.3, 3.63]})
            self.assertEqual(len(plan["requests"][0]["expected_units"]), 9 * 3 * 3)
            self.assertNotIn("ngspice_init", req["options"])

    def test_supplyless_bench_has_no_supply_axis(self):
        with tempfile.TemporaryDirectory() as d:
            tb, plan, files = self.plan("device-mos-vth", d)
            req = json.loads(files["run/request.json"])
            self.assertNotIn("supply_v", req["corners"])
            self.assertTrue(all(u[1] is None for u in plan["requests"][0]["expected_units"]))
            self.assertEqual([c["name"] for c in req["corners"]["process"]], ["tt", "ff", "ss", "fs", "sf"])

    def test_params_reach_the_deck(self):
        with tempfile.TemporaryDirectory() as d:
            _, _, files = self.plan("device-resistor-tc", d)
            self.assertIn(".param v_nwell=3.3", files["run/body.spice"])


class Ingest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        inc = Path(self._td.name) / "design.ngspice"
        inc.write_text("* stub\n")
        self.tb, net = load("device-mos-vth")
        self.plan, _ = mk.build_plan("device-mos-vth", self.tb, design_include=inc, dut=inc, tb_netlist=net,
                                     dut_rel="x", submitting_klt_version="0.7.0")
        self.names = list(self.tb["measure"])

    def report(self, drop=None, status=None, nan=None):
        corners = []
        for p, _s, t in self.plan["requests"][0]["expected_units"]:
            cid = f"{p}/novdd/{t:g}C"
            if cid == drop:
                continue
            ms = [{"name": n, "value": 0.7} for n in self.names]
            if cid == nan:
                ms[0]["value"] = None
            corners.append({"corner_id": cid, "status": (status or {}).get(cid, "pass"), "measurements": ms,
                            "diagnostics": []})
        return {"corners": corners, "environment": {"remote": REMOTE}, "provenance": {"klt_version": "0.7.0"}}

    def test_complete_report_is_all_ok(self):
        res, problems = fc.generic_point_results(self.tb, self.plan, self.report())
        self.assertEqual(problems, [])
        self.assertEqual(len(res), 15)
        self.assertTrue(all(r.status == "ok" and set(r.measurements) == set(self.names) for r in res))

    def test_missing_corner_is_an_error_point_naming_corner_and_job(self):
        res, _ = fc.generic_point_results(self.tb, self.plan, self.report(drop="ss/novdd/125C"))
        self.assertEqual(len(res), 15)
        bad = [r for r in res if r.status != "ok"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].status, "error")
        self.assertIn("ss/novdd/125C", bad[0].message)
        self.assertIn("job-424", bad[0].message)

    def test_failed_corner_and_missing_measurement(self):
        res, _ = fc.generic_point_results(self.tb, self.plan, self.report(status={"tt/novdd/27C": "error"},
                                                                          nan="ff/novdd/-40C"))
        by = {(r.point.corner.name, r.point.temp_c): r for r in res}
        self.assertEqual(by[("tt", 27.0)].status, "error")
        self.assertEqual(by[("ff", -40.0)].status, "failed")
        self.assertEqual(by[("ff", -40.0)].missing, [self.names[0]])
        self.assertEqual(sum(r.status != "ok" for r in res), 2)

    def test_runner_incompatibility_downgrades_every_point(self):
        rep = self.report()
        rep["environment"]["remote"] = dict(REMOTE, runner_compatibility="mismatch")
        res, problems = fc.generic_point_results(self.tb, self.plan, rep)
        self.assertTrue(problems)
        self.assertTrue(all(r.status == "failed" and "job-424" in r.message for r in res))

    def test_no_report_is_all_error_never_dropped(self):
        res, problems = fc.generic_point_results(self.tb, self.plan, None)
        self.assertEqual(len(res), 15)
        self.assertTrue(all(r.status == "error" for r in res))
        self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
