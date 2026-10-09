#!/usr/bin/env python3
"""Fixture checks for the psrr-dc / line-regulation / startup fleet adapters (#237).

No PDK, ngspice, fleet credentials or network: the PDK include is a stub file,
and every klt report / waveform is synthesized.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
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
import mk_klt_fleet_request as mk  # noqa: E402
import tc_ingest as ti  # noqa: E402
from suite import analysis, completeness, spec  # noqa: E402
from suite.cli import BenchRun, expected_corner_ids  # noqa: E402

DUT = REPO / "sim" / "dut" / "bandgap_top.spice"
REMOTE = {
    "provider": "aws-batch", "job_id": "job-1", "instance_type": "c7a", "lifecycle": "spot", "state": "SUCCEEDED",
    "exit_code": 0, "runner_klt_version": "0.7.0+gtest", "client_klt_version": "0.7.0+gtest", "runner_compatibility": "match",
}
GIT = {"short": "abc1234", "commit": "abc1234", "branch": "test", "dirty": False}


# ---------------------------------------------------------------- waveforms


def write_wave(path: Path, cols: dict) -> str:
    names = list(cols)
    rows = [list(r) for r in zip(*cols.values())]
    path.write_text(json.dumps({"plotname": "x", "variables": [{"index": i, "name": n, "type": "voltage"} for i, n in enumerate(names)], "points": rows}))
    return str(path)


def ac_wave(psrr_db=80.0):
    f = [0.1 * 10 ** (i / 20) for i in range(161)]
    return {"frequency": f, "v(vref)": [10 ** (-psrr_db / 20)] * len(f)}


def op_wave(vref=1.2):
    x = [2.97 + 0.33 * i for i in range(3)]
    return {"v-sweep": x, "v(vref)": [vref] * 3}


def dc_wave(slope=1e-5, n=133):
    x = [2.97 + 0.005 * i for i in range(n)]
    return {"v-sweep": x, "v(vref)": [1.2 + slope * (v - 3.3) for v in x], "v(vdd)": x}


def tran_wave(supply, kind="clean", n=1000):
    """vdd ramps 0->supply in 1 us (or 2 ms for 'negative'); vref settles with
    tau; 'chatter' re-exits the 1 % band late; 'negative' is in band from t=0."""
    t = [3e-3 * i / (n - 1) for i in range(n)]
    ramp = 2e-3 if kind == "negative" else 1e-6
    vdd = [min(supply, supply * x / ramp) for x in t]
    final = 1.2
    if kind == "negative":
        vref = [final] * n
    else:
        vref = [final * (1 - math.exp(-x / 50e-6)) for x in t]
        if kind == "chatter":
            for i, x in enumerate(t):
                if 1.8e-3 <= x <= 1.82e-3:
                    vref[i] = final * 1.03  # leaves the band again long after the first entry
    return {
        "time": t, "v(vdd)": vdd, "v(vref)": vref,
        "i(vsup)": [-30e-6] * n, "i(v.xtop.vsu_sense)": [0.2e-6] * n, "v(xtop.xx3.det)": [0.05] * n,
    }


# ---------------------------------------------------------------- fixtures


class Fixture:
    """A synthetic work dir (plan, decks, reports, waveforms) for one bench."""

    def __init__(self, bench, tmp: Path, *, wave=None, vals=None, include_wave=True):
        self.bench, self.tmp = bench, tmp
        self.tb = fi.load_tb(bench)
        (tmp / "design.ngspice").write_text("* stub pdk include\n")
        self.plan, files = mk.build_plan(
            bench, self.tb, design_include=tmp / "design.ngspice", dut=DUT,
            tb_netlist=SIM / bench / "testbench" / self.tb["netlist"], dut_rel="sim/dut/bandgap_top.spice",
            submitting_klt_version="0.7.0+gtest")
        for rel, text in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.wave = wave
        self.vals = vals
        self.include_wave = include_wave
        self.reports = {r["name"]: self.make_report(r) for r in self.plan["requests"]}

    def corner_id(self, r, p, s, t):
        sup = r["supply_v"] if s is None else s
        label = "novdd" if (s is None and r["supply_v"] is None) else f"{sup:.3f}V"
        return f"{p}/{label}/{t:g}C"

    def unit_vals(self, r, p, s, t):
        if self.vals:
            return self.vals(r, p, s, t)
        if self.bench == "psrr-dc":
            if r["role"] == "ac":
                return {f"vdb_{tag}": -80.0 for tag in fi.PSRR_TAGS}
            return {}
        if self.bench == "line-regulation":
            return {"vref_min": 1.2 - 3.3e-6, "vref_max": 1.2 + 3.3e-6, "v_lo_check": 2.97, "v_hi_check": 3.63}
        return {}

    def unit_wave(self, r, p, s, t):
        if self.wave:
            return self.wave(r, p, s, t)
        if self.bench == "psrr-dc":
            return ac_wave() if r["role"] == "ac" else op_wave()
        if self.bench == "line-regulation":
            return dc_wave()
        return tran_wave(r["supply_v"])

    def make_report(self, r):
        corners = []
        for p, s, t in r["expected_units"]:
            cid = self.corner_id(r, p, s, t)
            art = {}
            w = self.unit_wave(r, p, s, t)
            if w is not None and self.include_wave:
                d = self.tmp / r["name"] / "out"
                d.mkdir(parents=True, exist_ok=True)
                slug = cid.replace("/", "_")
                art["waveform"] = write_wave(d / f"{slug}.json", w)
                (d / f"{slug}.log").write_text(f"ngspice log {cid}\n")
                art["log"] = str(d / f"{slug}.log")
            corners.append({
                "corner_id": cid, "status": "pass", "diagnostics": [],
                "measurements": [{"name": k, "value": v} for k, v in self.unit_vals(r, p, s, t).items()],
                "artifacts": art,
            })
        return {"corners": corners, "environment": {"engine": "ngspice", "engine_version": "46", "remote": dict(REMOTE)},
                "provenance": {"klt_version": "0.7.0+gtest", "pdk": {"name": "gf180mcuD", "version": "x"}}}

    def decks(self):
        return {r["name"]: (self.tmp / r["name"] / "body.spice").read_text() for r in self.plan["requests"]}

    def assess(self, **kw):
        kw.setdefault("dut_sha", fc.sha256_file(DUT))
        kw.setdefault("decks", self.decks())
        return fi.assess_bench(self.bench, self.tb, self.plan, self.reports, self.tmp, **kw)

    def corner(self, name, idx=0):
        return self.reports[name]["corners"][idx]


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def fx(self, bench, **kw):
        return Fixture(bench, self.tmp, **kw)


# ---------------------------------------------------------------- requests


class Requests(TmpCase):
    def test_corner_list_is_the_harness_corner_list(self):
        for bench in mk.BENCHES:
            with self.subTest(bench=bench):
                f = self.fx(bench) if bench != "psrr-dc" else Fixture(bench, self.tmp)
                names = [c.name for c in fi.hc.resolve_corners(f.tb["corners"])]
                for r in f.plan["requests"]:
                    req = json.loads((self.tmp / r["name"] / "request.json").read_text())
                    self.assertEqual([p["name"] for p in req["corners"]["process"]], names)
                    self.assertEqual(req["corners"]["temperature_c"], f.tb["temperatures_c"])
                    self.assertEqual({(p, t) for p, _, t in r["expected_units"]},
                                     {(n, float(t)) for n in names for t in f.tb["temperatures_c"]})
                    self.assertTrue(req["options"]["keep_artifacts"])

    def test_psrr_ac_request_and_companion(self):
        f = self.fx("psrr-dc")
        ac = json.loads((self.tmp / "ac" / "request.json").read_text())
        self.assertEqual(ac["analysis"], {"kind": "ac", "args": "dec 20 0.1 10meg"})
        self.assertEqual(ac["corners"]["supply_v"], {"vsup": [2.97, 3.3, 3.63]})
        self.assertEqual({m["name"] for m in ac["measurements"]}, {f"vdb_{t}" for t in fi.PSRR_TAGS})
        op = json.loads((self.tmp / "op" / "request.json").read_text())
        self.assertEqual(op["analysis"]["kind"], "dc")
        self.assertNotIn("supply_v", op["corners"])
        self.assertEqual(op["measurements"], [])  # values come from the returned waveform
        self.assertTrue(op["options"]["waveforms"])
        self.assertEqual(len(f.plan["requests"]), 2)

    def test_line_regulation_keeps_internal_sweep_and_nominal_only_outer_supply(self):
        self.fx("line-regulation")
        req = json.loads((self.tmp / "sweep" / "request.json").read_text())
        self.assertEqual(req["analysis"], {"kind": "dc", "args": "vsup 2.97 3.63 0.005"})
        self.assertEqual(req["corners"]["supply_v"], {"vsup": [3.3]})  # never the three rails

    def test_startup_one_request_per_supply_no_alter_of_pwl_source(self):
        f = self.fx("startup")
        self.assertEqual(sorted(r["supply_v"] for r in f.plan["requests"]), [2.97, 3.3, 3.63])
        for r in f.plan["requests"]:
            req = json.loads((self.tmp / r["name"] / "request.json").read_text())
            self.assertNotIn("supply_v", req["corners"])  # klt refuses it for a PWL source
            self.assertEqual(req["analysis"], {"kind": "tran", "args": "1u 3m"})
            body = (self.tmp / r["name"] / "body.spice").read_text()
            self.assertIn(f".param vdd_val={r['supply_v']!r}", body)
            self.assertIn(".param tramp=1u", body)

    def test_embedded_core_is_not_duplicated_by_the_canonical_dut(self):
        f = self.fx("startup")
        for deck in f.decks().values():
            self.assertEqual(deck.lower().count(".subckt bandgap_top"), 1)
            self.assertNotIn("begin inlined DUT", deck)
        self.assertTrue(f.plan["embedded_core"])
        self.assertEqual(f.plan["dut"]["sha256"], fc.sha256_file(DUT))
        for deck in self.fx("psrr-dc").decks().values():
            self.assertEqual(deck.lower().count(".subckt bandgap_top"), 1)
            self.assertIn("begin inlined DUT", deck)

    def test_unsupported_bench_is_refused(self):
        with self.assertRaises(ValueError):
            mk.build_plan("output-voltage-tc", fi.load_tb("psrr-dc"), design_include=DUT, dut=DUT, tb_netlist=DUT, dut_rel="x")

    def test_plan_matches_tb_and_corners(self):
        for bench in mk.BENCHES:
            f = self.fx(bench)
            self.assertEqual(fi.plan_problems(bench, f.tb, f.plan), [])
        f = self.fx("psrr-dc")
        f.plan["requests"][0]["expected_units"].pop()
        self.assertTrue(fi.plan_problems("psrr-dc", f.tb, f.plan))


# ---------------------------------------------------------------- PSRR


class Psrr(TmpCase):
    def test_success_sign_and_reference_not_gated(self):
        f = self.fx("psrr-dc")
        res = f.assess()
        self.assertEqual(res["overall"], "PASS", res["problems"] + [str(v) for v in res["invalid"].values()])
        row = res["rows"][res["grid"][0]]
        self.assertAlmostEqual(row["measures"]["psrr_1hz_db"], 80.0)  # PSRR = -vdb
        self.assertAlmostEqual(row["measures"]["f_dc_hz"], 1.0, places=6)
        self.assertAlmostEqual(row["measures"]["f_band_edge_hz"], 1000.0, places=3)
        self.assertEqual(set(row["spec"]), {"psrr_1hz_db", "psrr_1khz_db"})

    def test_reference_columns_never_change_the_verdict(self):
        def vals(r, p, s, t):
            if r["role"] == "ac":
                d = {f"vdb_{tag}": -80.0 for tag in fi.PSRR_TAGS}
                d["vdb_1mhz"] = -5.0  # 5 dB at 1 MHz: stretch goal, recorded not gated
                return d
            return {}
        self.assertEqual(self.fx("psrr-dc", vals=vals).assess()["overall"], "PASS")

    def test_gated_1khz_failure_is_fail(self):
        def vals(r, p, s, t):
            d = {f"vdb_{tag}": -80.0 for tag in fi.PSRR_TAGS}
            if r["role"] != "ac":
                return {}
            d["vdb_1khz"] = -59.0
            return d
        res = self.fx("psrr-dc", vals=vals).assess()
        self.assertEqual(res["overall"], "FAIL")
        self.assertEqual(len(res["spec_fail"]), 81)

    def test_operating_point_outside_window_is_invalid_not_pass(self):
        def vals(r, p, s, t):
            if r["role"] == "ac":
                return {f"vdb_{tag}": -80.0 for tag in fi.PSRR_TAGS}
            return {}
        def wave(r, p, s, t):
            return ac_wave() if r["role"] == "ac" else op_wave(0.2)  # degenerate state
        res = self.fx("psrr-dc", vals=vals, wave=wave).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["invalid"]), 81)

    def test_missing_op_companion_is_incomplete(self):
        f = self.fx("psrr-dc")
        del f.reports["op"]
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["invalid"]), 81)

    def test_coarse_ac_grid_is_caught(self):
        def wave(r, p, s, t):
            if r["role"] != "ac":
                return None
            w = ac_wave()
            return {k: v[::2] for k, v in w.items()}  # 10 pts/dec: 1 Hz is still on grid, but the count is wrong
        res = self.fx("psrr-dc", wave=wave).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_off_grid_frequency_index_is_caught(self):
        def wave(r, p, s, t):
            if r["role"] != "ac":
                return None
            f = [0.1 * 10 ** (i / 20) * 1.5 for i in range(161)]
            return {"frequency": f, "v(vref)": [1e-4] * 161}
        res = self.fx("psrr-dc", wave=wave).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")


# ---------------------------------------------------------------- line regulation


class LineReg(TmpCase):
    def test_success_and_box_figure(self):
        res = self.fx("line-regulation").assess()
        self.assertEqual(res["overall"], "PASS", res["problems"] + list(map(str, res["invalid"].values())))
        m = res["rows"][res["grid"][0]]["measures"]
        self.assertAlmostEqual(m["linereg_mv_per_v"], 6.6e-6 * 1000 / 0.66, places=9)
        self.assertEqual(m["sweep_points"], 133.0)
        self.assertEqual(len(res["grid"]), 27)  # 9 process x 3 temperature, nominal supply only

    def test_box_not_endpoint_chord(self):
        def vals(r, p, s, t):
            return {"vref_min": 1.19, "vref_max": 1.2, "v_lo_check": 2.97, "v_hi_check": 3.63}
        def wave(r, p, s, t):
            w = dc_wave()
            w["v(vref)"] = [1.19 + 0.01 * (i == 60) for i in range(133)]
            return w
        res = self.fx("line-regulation", vals=vals, wave=wave).assess()
        m = res["rows"][res["grid"][0]]["measures"]
        self.assertAlmostEqual(m["linereg_mv_per_v"], 0.01 * 1000 / 0.66)
        self.assertEqual(res["overall"], "FAIL")  # > 1 mV/V although the endpoints are equal

    def test_coarsened_sweep_is_incomplete(self):
        res = self.fx("line-regulation", wave=lambda r, p, s, t: dc_wave(n=67)).assess()  # wrong count
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_meas_vs_waveform_disagreement_is_incomplete(self):
        def vals(r, p, s, t):
            return {"vref_min": 1.2, "vref_max": 1.3, "v_lo_check": 2.97, "v_hi_check": 3.63}
        res = self.fx("line-regulation", vals=vals).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_small_disagreement_beyond_print_precision_is_incomplete(self):
        # 1e-5 V at 1.2 V is ~8e-6 relative: well past 7-digit rounding (<= 5e-7)
        w = dc_wave()
        hi, lo = max(w["v(vref)"]), min(w["v(vref)"])
        def vals(r, p, s, t):
            return {"vref_min": lo, "vref_max": hi + 1e-5, "v_lo_check": 2.97, "v_hi_check": 3.63}
        res = self.fx("line-regulation", vals=vals).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_meas_rounded_like_ngspice_prints_is_valid(self):
        # ngspice prints `.meas` lines with %e (7 significant digits); klt parses
        # that line, while the waveform keeps full rawfile precision.
        def wave(r, p, s, t):
            x = [2.97 + 0.005 * i for i in range(133)]
            return {"v-sweep": x, "v(vref)": [1.200342379 + 6.6e-6 * (v - 2.97) / 0.66 + 1.23456789e-10 * i
                                             for i, v in enumerate(x)], "v(vdd)": x}
        def vals(r, p, s, t):
            v = wave(r, p, s, t)["v(vref)"]
            return {"vref_min": float(f"{min(v):e}"), "vref_max": float(f"{max(v):e}"),
                    "v_lo_check": 2.97, "v_hi_check": 3.63}
        sample = wave(None, None, None, None)["v(vref)"]
        rounded = float(f"{max(sample):e}")
        self.assertNotEqual(rounded, max(sample))
        self.assertGreater(abs(rounded - max(sample)), 1e-9)  # the old 1e-9 tolerance would reject this
        res = self.fx("line-regulation", vals=vals, wave=wave).assess()
        self.assertEqual(res["overall"], "PASS", res["problems"] + list(map(str, res["invalid"].values())))
        m = res["rows"][res["grid"][0]]["measures"]
        # gated values come from the full-precision waveform, not the rounded .meas
        self.assertEqual(m["vref_max"], max(sample))
        self.assertEqual(m["vref_min"], min(sample))
        self.assertEqual(m["linereg_mv_per_v"], (max(sample) - min(sample)) * 1000.0 / 0.66)

    def test_meas_agrees_tolerance_is_print_precision(self):
        for x in (1.200348979, 1.200342379, 2.0726349036795e-3, 3.63, 0.0):
            self.assertTrue(fi.meas_agrees(float(f"{x:e}"), x))
        self.assertFalse(fi.meas_agrees(1.200349, 1.200349 + 3e-6))

    def test_sweep_endpoint_sanity(self):
        def vals(r, p, s, t):
            return {"vref_min": 1.2, "vref_max": 1.2, "v_lo_check": 3.0, "v_hi_check": 3.63}
        res = self.fx("line-regulation", vals=vals, wave=lambda *a: {"x": [2.97 + 0.005 * i for i in range(133)], "v(vref)": [1.2] * 133}).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")


# ---------------------------------------------------------------- startup


class Startup(TmpCase):
    def test_clean_success_matches_the_bench_convention(self):
        res = self.fx("startup").assess()
        self.assertEqual(res["overall"], "PASS", res["problems"] + list(map(str, res["invalid"].values())))
        m = res["rows"][res["grid"][0]]["measures"]
        self.assertGreater(m["startup_time_s"], 0)
        self.assertLess(m["startup_time_s"], 1e-3)
        self.assertAlmostEqual(m["iq_total_final_ua"], 30.0)
        self.assertEqual(len(res["grid"]), 81)

    def test_late_chattering_pushes_settle_later_than_first_crossing(self):
        w = tran_wave(3.3, "chatter")
        m, errs = fi.derive_startup(w, 3.3, fi.load_tb("startup"))
        self.assertEqual(errs, [])
        # first entry into the band (a first-crossing approximation) is early...
        vf = w["v(vref)"][-1]
        first = next(t for t, v in zip(w["time"], w["v(vref)"]) if abs(v - vf) <= 0.01 * vf)
        self.assertLess(first, 1e-3)
        # ...the backward scan lands after the late excursion
        self.assertGreater(m["t_settle_s"], 1.82e-3)
        self.assertGreater(m["startup_time_s"], 1e-3)
        res = self.fx("startup", wave=lambda r, p, s, t: tran_wave(r["supply_v"], "chatter")).assess()
        self.assertEqual(res["overall"], "FAIL")

    def test_negative_startup_time_is_legitimate(self):
        w = tran_wave(3.3, "negative")
        m, errs = fi.derive_startup(w, 3.3, fi.load_tb("startup"))
        self.assertEqual(errs, [])
        self.assertLess(m["startup_time_s"], 0)
        self.assertEqual(m["t_settle_s"], 0.0)
        res = self.fx("startup", wave=lambda r, p, s, t: tran_wave(r["supply_v"], "negative")).assess()
        self.assertEqual(res["overall"], "PASS")  # <= 1 ms: the best possible outcome, not an error

    def test_wrong_rail_is_invalid(self):
        # an `alter` on a PWL source being ignored would leave vdd at the nominal rail
        res = self.fx("startup", wave=lambda r, p, s, t: tran_wave(3.3)).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("rail" in why for why in res["invalid"].values()))

    def test_truncated_run_is_invalid(self):
        def wave(r, p, s, t):
            w = tran_wave(r["supply_v"])
            return {k: v[:500] for k, v in w.items()}
        self.assertEqual(self.fx("startup", wave=wave).assess()["overall"], "INCOMPLETE")

    def test_missing_waveform_never_becomes_a_pass(self):
        res = self.fx("startup", include_wave=False).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_sanity_windows_gate_validity(self):
        def wave(r, p, s, t):
            w = tran_wave(r["supply_v"])
            w["v(xtop.xx3.det)"] = [1.0] * len(w["time"])  # startup branch still conducting
            return w
        res = self.fx("startup", wave=wave).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")


# ---------------------------------------------------------------- completeness (all benches)


class Fails(TmpCase):
    BENCHES = mk.BENCHES

    def each(self):
        for bench in self.BENCHES:
            with self.subTest(bench=bench):
                self.setUp()
                yield self.fx(bench)

    def first_request(self, f):
        return f.plan["requests"][0]["name"]

    def test_missing_corner(self):
        for f in self.each():
            n = self.first_request(f)
            f.reports[n]["corners"].pop(3)
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(res["missing"])

    def test_backend_error(self):
        for f in self.each():
            n = self.first_request(f)
            c = f.corner(n, 2)
            c["status"], c["measurements"] = "error", []
            c["diagnostics"] = [{"code": "batch_job_failed", "message": "boom"}]
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(any("boom" in why for _, why in res["failed"]))

    def test_null_and_nonfinite_measurements(self):
        for f in self.each():
            n = self.first_request(f)
            ms = f.corner(n, 1)["measurements"]
            if not ms:  # startup has no .meas: nothing to null
                continue
            ms[0]["value"] = None
            ms[1]["value"] = float("nan")
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(res["missing"] or res["failed"])

    def test_nan_alone_is_rejected(self):
        f = self.fx("line-regulation")
        f.corner("sweep", 0)["measurements"][0]["value"] = float("inf")
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertIn("non-finite", res["missing"][0][1])
        self.assertEqual(res["failed"], [])

    def test_nonfinite_waveform_value_is_rejected(self):
        def wave(r, p, s, t):
            w = tran_wave(r["supply_v"])
            w["v(vref)"][-1] = float("nan")
            return w
        # json.dumps writes NaN literal; reading it back must not produce a PASS
        res = self.fx("startup", wave=wave).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_duplicate_and_unexpected_corners(self):
        for f in self.each():
            n = self.first_request(f)
            cs = f.reports[n]["corners"]
            cs.append(copy.deepcopy(cs[0]))
            extra = copy.deepcopy(cs[0])
            extra["corner_id"] = extra["corner_id"].replace(cs[0]["corner_id"].split("/")[0], "zz", 1)
            cs.append(extra)
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertGreaterEqual(len([p for p in res["problems"] if "duplicate" in p or "unexpected" in p]), 2)

    def test_mismatched_dut(self):
        for f in self.each():
            res = f.assess(dut_sha="0" * 64)
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(any("DUT sha256" in p for p in res["problems"]))

    def test_edited_deck_or_testbench_after_generation(self):
        for f in self.each():
            n = self.first_request(f)
            decks = f.decks()
            decks[n] += "* tampered\n"
            self.assertTrue(any("deck sha256" in p for p in f.assess(decks=decks)["problems"]))
            self.assertTrue(any("testbench netlist" in p for p in f.assess(tb_sha="1" * 64)["problems"]))
            self.assertTrue(any("tb.json changed" in p for p in f.assess(manifest_sha="1" * 64)["problems"]))

    def test_duplicate_subckt_definition_in_deck(self):
        for f in self.each():
            n = self.first_request(f)
            decks = f.decks()
            decks[n] += "\n.subckt bandgap_top a b c\n.ends\n"
            probs = f.assess(decks=decks)["problems"]
            self.assertTrue(any("defined 2 times" in p for p in probs), probs)

    def test_version_and_provenance_mismatch(self):
        for f in self.each():
            n = self.first_request(f)
            f.reports[n]["environment"]["remote"]["runner_compatibility"] = "mismatch"
            f.reports[n]["environment"]["remote"]["runner_klt_version"] = "0.6.0"
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(any("compatibility" in p for p in res["problems"]))

    def test_unknown_runner_and_missing_remote(self):
        f = self.fx("line-regulation")
        r = f.reports["sweep"]["environment"]["remote"]
        r["runner_compatibility"], r["runner_klt_version"] = "unknown", None
        self.assertEqual(f.assess()["overall"], "INCOMPLETE")
        g = self.fx("line-regulation")
        del g.reports["sweep"]["environment"]["remote"]  # a local run is not fleet evidence
        self.assertTrue(any("not a fleet run" in p for p in g.assess()["problems"]))

    def test_submitting_version_differs_from_plan(self):
        f = self.fx("line-regulation")
        f.plan["submitting_klt_version"] = "0.5.0"
        self.assertTrue(any("differs" in p for p in f.assess()["problems"]))

    def test_unsupported_analysis_never_yields_data(self):
        # a worker that dropped the waveform artifact (capability not delivered)
        for bench in self.BENCHES:
            with self.subTest(bench=bench):
                self.setUp()
                res = self.fx(bench, include_wave=False).assess()
                self.assertEqual(res["overall"], "INCOMPLETE")

    def test_missing_request_report(self):
        f = self.fx("startup")
        del f.reports[f.plan["requests"][0]["name"]]
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["invalid"]), 27)


# ---------------------------------------------------------------- suite integration


def bench_run_from(slug, cdir: Path) -> BenchRun:
    lines = spec.by_slug()[slug]
    expected = expected_corner_ids(slug)
    run = BenchRun(slug=slug, lines=lines, expected_corners=expected)
    run.status = "ok"
    run.logs_dir = cdir
    run.samples = analysis.read_corner_logs(cdir)
    run.outcomes = [analysis.evaluate_line(line, run.samples, expected) for line in lines]
    return run


class SuiteIntegration(TmpCase):
    def ingest(self, bench, fx):
        res = fx.assess()
        exp = self.tmp / "exp" / bench
        rec = fi.write_evidence(exp, self.tmp, bench, fx.tb, fx.plan, res, fx.reports, dut_label="sim/dut/bandgap_top.spice",
                                issue=237, git=GIT)
        return res, exp, rec

    def test_expected_corner_ids_equal_the_log_names(self):
        for bench in mk.BENCHES:
            fx = self.fx(bench)
            self.assertEqual([fi.corner_id(k) for k in fi.expected_grid(fx.tb)], expected_corner_ids(bench))

    def test_ingested_pass_is_read_by_the_suite_as_pass(self):
        for bench in ("psrr-dc", "line-regulation"):
            with self.subTest(bench=bench):
                self.setUp()
                fx = self.fx(bench)
                res, exp, rec = self.ingest(bench, fx)
                self.assertEqual(res["overall"], "PASS")
                (cdir,) = list((exp / "corners").iterdir())
                run = bench_run_from(bench, cdir)
                self.assertEqual([o.status for o in run.outcomes], ["PASS"] * len(run.outcomes))
                done = completeness.assess([run], None, [bench], smoke=True)
                self.assertEqual(done.missing, [])
                self.assertEqual(done.failures, [])
                self.assertEqual(done.n_gated, done.n_pass)
                self.assertIn("Overall: PASS", rec.read_text())

    def test_ingested_incomplete_is_no_data_never_pass(self):
        for bench in ("psrr-dc", "line-regulation"):
            with self.subTest(bench=bench):
                self.setUp()
                fx = self.fx(bench)
                fx.reports[fx.plan["requests"][0]["name"]]["corners"].pop(5)  # one corner never came back
                res, exp, rec = self.ingest(bench, fx)
                self.assertEqual(res["overall"], "INCOMPLETE")
                (cdir,) = list((exp / "corners").iterdir())
                run = bench_run_from(bench, cdir)
                self.assertTrue(all(o.status == "NO DATA" for o in run.outcomes))
                done = completeness.assess([run], None, [bench], smoke=True)
                self.assertTrue(done.blocked)
                self.assertNotEqual(done.exit_code, 0)
                self.assertIn("INCOMPLETE", rec.read_text())

    def test_ingested_spec_fail_is_fail_in_the_suite(self):
        fx = self.fx("line-regulation", vals=lambda r, p, s, t: {
            "vref_min": 1.19, "vref_max": 1.2, "v_lo_check": 2.97, "v_hi_check": 3.63},
            wave=lambda *a: {"x": [2.97 + 0.005 * i for i in range(133)], "v(vref)": [1.19] * 66 + [1.2] * 67})
        res, exp, _ = self.ingest("line-regulation", fx)
        self.assertEqual(res["overall"], "FAIL")  # 10 mV over 0.66 V = 15 mV/V > 1
        (cdir,) = list((exp / "corners").iterdir())
        run = bench_run_from("line-regulation", cdir)
        self.assertEqual(next(o for o in run.outcomes if o.line.key == "line-regulation").status, "FAIL")
        done = completeness.assess([run], None, ["line-regulation"], smoke=True)
        self.assertTrue(done.failures)
        self.assertEqual(done.exit_code, completeness.EXIT_SPEC_FAIL)

    def test_invalid_sanity_corner_is_no_data_in_suite(self):
        fx = self.fx("psrr-dc", vals=lambda r, p, s, t: (
            {f"vdb_{tag}": -80.0 for tag in fi.PSRR_TAGS} if r["role"] == "ac" else {}),
            wave=lambda r, p, s, t: ac_wave() if r["role"] == "ac" else op_wave(0.1))
        res, exp, _ = self.ingest("psrr-dc", fx)
        (cdir,) = list((exp / "corners").iterdir())
        run = bench_run_from("psrr-dc", cdir)
        self.assertTrue(all(o.status == "NO DATA" for o in run.outcomes))
        self.assertTrue(all(not v for v in run.samples.values()))  # INVALID POINT: no numbers reach a verdict

    def test_startup_logs_are_written_and_record_has_both_identities(self):
        fx = self.fx("startup")
        res, exp, rec = self.ingest("startup", fx)
        text = rec.read_text()
        self.assertIn(fc.sha256_file(DUT), text)  # canonical DUT identity
        for r in fx.plan["requests"]:
            self.assertIn(r["deck_sha256"], text)  # frozen embedded deck identity
        self.assertIn("Embedded-core convention", text)
        (cdir,) = list((exp / "corners").iterdir())
        samples = analysis.read_corner_logs(cdir)
        self.assertEqual(len(samples), 81)
        self.assertIn("startup_time_s", next(iter(samples.values())))
        self.assertTrue((cdir / "plan.json").exists())
        self.assertTrue(any((exp / "netlist-snapshots").glob("*.vdd_*.spice")))

    def test_append_only_second_ingest_mints_a_new_record(self):
        fx = self.fx("line-regulation")
        _, exp, r1 = self.ingest("line-regulation", fx)
        res = fx.assess()
        r2 = fi.write_evidence(exp, self.tmp, "line-regulation", fx.tb, fx.plan, res, fx.reports,
                               dut_label="x", issue=237, git=GIT)
        self.assertNotEqual(r1, r2)
        from harness import report as hreport
        with self.assertRaises(RuntimeError):
            hreport.device_write_record(exp / "records", r1.stem, "overwrite")

    def test_suite_index_and_manifests_agree_with_spec_checks(self):
        for bench in mk.BENCHES:
            tb = fi.load_tb(bench)
            for line in spec.by_slug().get(bench, []):
                self.assertEqual(analysis.check_limits_match_manifest(line, tb["checks"]), [])
                for lim in line.limits:
                    self.assertIn(lim.measurement, fi.SPEC_CHECKS[bench])
            self.assertTrue(fi.SPEC_CHECKS[bench] <= set(tb["checks"]))


class SharedHelpers(unittest.TestCase):
    def test_tc_ingest_still_uses_the_shared_helpers(self):
        self.assertIs(ti.sha256.__module__, "tc_ingest")
        rep = {"corners": [{"corner_id": "tt/3.300V/27C", "status": "pass",
                            "measurements": [{"name": n, "value": float("nan")} for n in ti.REQUIRED]}]}
        pts, miss, fail, prob = ti.collect(rep, [("tt", 3.3)])
        self.assertEqual(pts, {})
        self.assertTrue(miss)  # NaN is not a measurement (was silently accepted before #237)

    def test_corner_id_parsing(self):
        self.assertEqual(fc.parse_klt_corner_id("bjt_ff/2.970V/-40C"), ("bjt_ff", 2.97, -40.0))
        self.assertEqual(fc.parse_klt_corner_id("tt/novdd/125C"), ("tt", None, 125.0))
        with self.assertRaises(ValueError):
            fc.parse_klt_corner_id("tt/3.300V/27C/mc3")


if __name__ == "__main__":
    unittest.main()
