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
        return {"corners": corners, "environment": {"engine": "ngspice", "engine_version": "46", "remote": dict(REMOTE),
                                "netlist_sha256": r["deck_sha256"]},
                "provenance": {"klt_version": "0.7.0+gtest", "pdk": {"name": "gf180mcuD", "version": "x"},
                               "input": {"content_hash": "sha256:" + r["deck_sha256"], "role": "netlist"}}}

    def decks(self):
        return {r["name"]: (self.tmp / r["name"] / "body.spice").read_text() for r in self.plan["requests"]}

    def requests(self):
        return {r["name"]: (self.tmp / r["name"] / "request.json").read_text()
                for r in self.plan["requests"] if (self.tmp / r["name"] / "request.json").exists()}

    def assess(self, **kw):
        kw.setdefault("dut_sha", fc.sha256_file(DUT))
        kw.setdefault("decks", self.decks())
        kw.setdefault("requests", self.requests())
        return fi.assess_bench(self.bench, self.tb, self.plan, self.reports, self.tmp, **kw)

    def corner(self, name, idx=0):
        return self.reports[name]["corners"][idx]


def printed(x: float) -> float:
    """A value as klt reads it from ngspice's `print` line: 7 significant digits."""
    return float(f"{x:e}")


#: Known-resistor references from sim/output-noise/unit-probe/README.md (#252):
#: amplitude-mode ngspice output for Req = 5 kohm at 27 C.
PROBE_TOTAL_V = 2.8644637779e-08      # onoise_total over 0.1-10 Hz, V rms
PROBE_DENSITY_V_RTHZ = 9.1038635016e-09  # onoise_spectrum, V/sqrt(Hz)


class NoiseFixture(Fixture):
    """Synthetic output-noise work dir: the three requests (op, noise_1 band,
    noise_2 spot), klt expr measurements with their reported units, and the
    waveform artifacts klt returns (operating-point plot / integrated-noise
    plot with ngspice's variable types)."""

    def __init__(self, bench, tmp, *, raw=None, docs=None, units=None, include_wave=True, dut=DUT,
                 dut_rel="sim/dut/bandgap_top.spice"):
        self.raw_override, self.docs_override, self.units_override = raw, docs, units
        self.bench, self.tmp, self.include_wave = bench, tmp, include_wave
        self.tb = fi.load_tb(bench)
        self.dut = dut
        (tmp / "design.ngspice").write_text("* stub pdk include\n")
        self.plan, files = mk.build_plan(
            bench, self.tb, design_include=tmp / "design.ngspice", dut=dut,
            tb_netlist=SIM / bench / "testbench" / self.tb["netlist"], dut_rel=dut_rel,
            submitting_klt_version="0.7.0+gtest")
        self.files = files
        for rel, text in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.wave, self.vals = None, None
        self.reports = {r["name"]: self.make_report(r) for r in self.plan["requests"]}

    # full-precision "true" values of one corner (index i over the report)
    def truth(self, r, i):
        total = PROBE_TOTAL_V * (600.0 + 7.0 * i)  # ~17 uVrms, moves with the corner (spread floor)
        dens = PROBE_DENSITY_V_RTHZ * 97.0 * (1.0 + 0.01 * i)
        vals = {"vref_op": 1.2019834567 + 1e-5 * i, "onoise_int_0p1_10hz_uvrms": total,
                "onoise_1khz_nv_rthz": dens, "onoise_10khz_nv_rthz": dens * 0.97, "onoise_100khz_nv_rthz": dens * 1.1}
        for name, s in self.plan["noise"]["measures"].items():
            if s["vector"] == "frequency":
                idx = int(s["expr"].split("[")[1].rstrip("])"))
                rq = self.plan["noise"]["requests"][s["request"]]
                vals[name] = rq["f_lo"] * 10 ** (idx / rq["per_dec"])
        return vals

    def corner_raw(self, r, i):
        nspec = self.plan["noise"]
        t = self.truth(r, i)
        out = {f"raw_{m}": printed(t[m]) for m, s in nspec["measures"].items() if s["request"] == r["name"]}
        if r["role"] == "noise":
            out.update({"n_points": float(r["n_points"]), "sqrnoise_set": 0.0})
        if self.raw_override:
            out = self.raw_override(r, i, out)
        return out

    def corner_doc(self, r, i):
        t = self.truth(r, i)
        if r["role"] == "op_point":
            doc = {"plotname": "Operating Point",
                   "variables": [{"index": 0, "name": "v(vdd)", "type": "voltage"},
                                 {"index": 1, "name": "v(vref)", "type": "voltage"}],
                   "points": [[3.3, t["vref_op"]]]}
        else:
            total = t["onoise_int_0p1_10hz_uvrms"] if r["name"] == "noise_1" else t["onoise_int_0p1_10hz_uvrms"] * 3
            doc = {"plotname": "Integrated Noise",
                   "variables": [{"index": 0, "name": "v(onoise_total)", "type": "voltage"},
                                 {"index": 1, "name": "v(inoise_total)", "type": "voltage"}],
                   "points": [[total, total * 2]]}
        if self.docs_override:
            doc = self.docs_override(r, i, doc)
        return doc

    def make_report(self, r):
        mk_units = {m["name"]: m["unit"] for m in json.loads(self.files[f"{r['name']}/request.json"])["measurements"]}
        corners = []
        for i, (p, s, t) in enumerate(r["expected_units"]):
            cid = self.corner_id(r, p, s, t)
            slug = cid.replace("/", "_")
            d = self.tmp / r["name"] / "out"
            d.mkdir(parents=True, exist_ok=True)
            art = {}
            doc = self.corner_doc(r, i)
            if doc is not None and self.include_wave:
                (d / f"{slug}.json").write_text(json.dumps(doc))
                art["waveform"] = str(d / f"{slug}.json")
            (d / f"{slug}.log").write_text(f"ngspice log {cid}\n")
            art["log"] = str(d / f"{slug}.log")
            u = dict(mk_units)
            if self.units_override:
                u = self.units_override(r, i, u)
            corners.append({
                "corner_id": cid, "status": "pass", "diagnostics": [],
                "measurements": [{"name": k, "value": v, "unit": u.get(k)} for k, v in self.corner_raw(r, i).items()],
                "artifacts": art,
            })
        return {"corners": corners, "environment": {"engine": "ngspice", "engine_version": "46", "remote": dict(REMOTE),
                                "netlist_sha256": r["deck_sha256"]},
                "provenance": {"klt_version": "0.7.0+gtest", "pdk": {"name": "gf180mcuD", "version": "x"},
                               "input": {"content_hash": "sha256:" + r["deck_sha256"], "role": "netlist"}}}

    def assess(self, **kw):
        kw.setdefault("dut_sha", fc.sha256_file(self.dut))
        kw.setdefault("decks", self.decks())
        kw.setdefault("requests", self.requests())
        return fi.assess_bench(self.bench, self.tb, self.plan, self.reports, self.tmp, **kw)


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def fx(self, bench, **kw):
        return (NoiseFixture if bench == mk.NOISE_BENCH else Fixture)(bench, self.tmp, **kw)


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

    def _bad_axis(self, mutate):
        def wave(r, p, s, t):
            if r["role"] != "ac":
                return None
            w = ac_wave()
            w["frequency"] = mutate(list(w["frequency"]))
            return w
        res = self.fx("psrr-dc", wave=wave).assess()
        self.assertNotEqual(res["overall"], "PASS")
        self.assertEqual(len(res["invalid"]), 81)
        self.assertFalse(any("fails" in str(p) for p in res["problems"]))
        return res

    def test_full_valid_grid_still_passes(self):
        res = self.fx("psrr-dc").assess()
        self.assertEqual(res["overall"], "PASS")

    def test_repro_two_distinct_frequencies(self):
        self._bad_axis(lambda f: [1.0] * 80 + [1000.0] * 81)

    def test_duplicated_points(self):
        def m(f):
            f[70] = f[69]
            return f
        self._bad_axis(m)

    def test_reordered_points(self):
        def m(f):
            f[70], f[71] = f[71], f[70]
            return f
        self._bad_axis(m)

    def test_endpoint_substitutions(self):
        def lo(f):
            f[0] = 0.05
            return f
        def hi(f):
            f[-1] = 2e7
            return f
        self._bad_axis(lo)
        self._bad_axis(hi)

    def test_interior_perturbation_keeps_count_and_spot_frequencies(self):
        def m(f):
            f[100] *= 1.01  # still increasing; f[20]=1 Hz and f[80]=1 kHz untouched
            return f
        self._bad_axis(m)

    def test_nonpositive_or_nonfinite_axis(self):
        def neg(f):
            f[5] = -1.0
            return f
        def nan(f):
            f[5] = float("nan")
            return f
        self._bad_axis(neg)
        self._bad_axis(nan)


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

    def test_missing_status_is_failed_closed(self):
        for f in self.each():
            c = f.corner(self.first_request(f), 2)
            del c["status"]
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(any("unknown corner status" in why for _, why in res["failed"]))

    def test_unknown_or_untrusted_status_is_failed_closed(self):
        for st in ("weird", "pass_partial", "inconclusive", None, 1):
            for f in self.each():
                f.corner(self.first_request(f), 2)["status"] = st
                res = f.assess()
                self.assertEqual(res["overall"], "INCOMPLETE", st)
                self.assertEqual(len(res["failed"]), 1, st)

    def test_complete_values_with_error_diagnostic_is_not_pass(self):
        for sev in ("error", "ERROR", "fatal", None):
            for f in self.each():
                c = f.corner(self.first_request(f), 2)
                d = {"code": "simulation_failed", "message": "kaboom"}
                if sev is not None:
                    d["severity"] = sev  # None: severity absent, treated as error
                c["diagnostics"] = [d]
                res = f.assess()
                self.assertEqual(res["overall"], "INCOMPLETE", sev)
                self.assertTrue(any("kaboom" in why for _, why in res["failed"]), sev)

    def test_warning_only_diagnostic_is_retained_not_fatal(self):
        for f in self.each():
            before = f.assess()["overall"]
            f.corner(self.first_request(f), 2)["diagnostics"] = [
                {"severity": "warning", "code": "recovered_stepping", "message": "gmin stepping"}]
            res = f.assess()
            self.assertEqual(res["failed"], [])
            self.assertEqual(res["overall"], before)

    def test_legitimate_fail_status_is_graded_not_missing(self):
        for f in self.each():
            before = f.assess()["overall"]
            f.corner(self.first_request(f), 2)["status"] = "fail"
            res = f.assess()
            self.assertEqual(res["failed"], [])
            self.assertEqual(res["missing"], [])
            self.assertEqual(res["overall"], before)

    def test_duplicate_measurement_names_are_rejected(self):
        # ambiguity is rejected whichever value comes first, and when identical (#290)
        for first, second in ((None, 1.0), (1.0, None), (1e9, 1.0), (1.0, 1e9), (2.0, 2.0)):
            for f in self.each():
                n = self.first_request(f)
                ms = f.corner(n, 2)["measurements"]
                if not ms:
                    continue  # waveform-derived bench: no scalar measurements to duplicate
                name = ms[0]["name"]
                ms[0:1] = [{"name": name, "value": first}, {"name": name, "value": second}]
                res = f.assess()
                self.assertEqual(res["overall"], "INCOMPLETE", (first, second))
                self.assertEqual(len(res["failed"]), 1, (first, second))
                self.assertIn("duplicate measurement", res["failed"][0][1])
                self.assertIn(name, res["failed"][0][1])
                # nothing graded is minted for the ambiguous unit: its log is an INVALID POINT
                cdir = self.tmp / "logs"
                fi.write_corner_logs(cdir, self.tmp, f.plan, res, "rec")
                logs = [p.read_text() for p in sorted(cdir.glob("*.log"))]
                bad = [t for t in logs if fi.INVALID_POINT_MARKER in t]
                self.assertGreaterEqual(len(bad), 1)
                self.assertEqual(len(bad), len(res["invalid"]))
                self.assertTrue(all("derived by" not in t for t in bad))

    def test_uniquely_named_measurements_are_unaffected(self):
        for f in self.each():
            res = f.assess()
            self.assertFalse(any("duplicate measurement" in w for _, w in res["failed"]))

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

    def test_frozen_request_bytes_verified(self):
        for f in self.each():
            n = self.first_request(f)
            base = f.assess()
            self.assertFalse([p for p in base["problems"] if "request" in p and "sha256" in p], base["problems"])
            rp = f.tmp / n / "request.json"
            orig = rp.read_text()
            doc = json.loads(orig)
            edits = {
                "analysis": lambda d: d.__setitem__("analysis", {"kind": "dc", "args": ["vsup", "3.0", "3.6", "0.005"]}),
                "options": lambda d: d.__setitem__("options", {"reltol": 1e-1}),
                "model": lambda d: d.__setitem__("model_selection", "tampered"),
            }
            for what, edit in edits.items():
                with self.subTest(bench=f.bench, edit=what):
                    d = copy.deepcopy(doc)
                    edit(d)
                    rp.write_text(json.dumps(d, indent=2) + "\n")
                    res = f.assess()
                    self.assertEqual(res["overall"], "INCOMPLETE")
                    self.assertTrue(any("request.json sha256 differs" in p for p in res["problems"]), res["problems"])
            rp.write_text(orig + " ")  # whitespace-only change is still a different frozen byte stream
            self.assertTrue(any("request.json sha256 differs" in p for p in f.assess()["problems"]))
            rp.write_text(orig)
            rp.unlink()
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(any("request.json missing" in p for p in res["problems"]), res["problems"])
            rp.write_text(orig)
            f.plan["requests"][[r["name"] for r in f.plan["requests"]].index(n)].pop("request_sha256")
            res = f.assess()
            self.assertEqual(res["overall"], "INCOMPLETE")
            self.assertTrue(any("no request_sha256" in p for p in res["problems"]), res["problems"])

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


# ---------------------------------------------------------------- output-noise (#268)


def noise_tb(**changes) -> dict:
    tb = copy.deepcopy(fi.load_tb("output-noise"))
    for k, v in changes.items():
        tb[k] = v
    return tb


class NoiseRequests(TmpCase):
    """Phase A: the request/plan contract, derived from tb.json, PDK-free."""

    def test_three_requests_both_bands_and_operating_point(self):
        f = self.fx("output-noise")
        self.assertEqual([(r["name"], r["role"]) for r in f.plan["requests"]],
                         [("op", "op_point"), ("noise_1", "noise"), ("noise_2", "noise")])
        reqs = {r["name"]: json.loads((self.tmp / r["name"] / "request.json").read_text()) for r in f.plan["requests"]}
        self.assertEqual(reqs["op"]["analysis"], {"kind": "op", "args": ""})
        self.assertEqual(reqs["noise_1"]["analysis"], {"kind": "noise", "args": "v(vref) vsup dec 20 0.1 10"})
        self.assertEqual(reqs["noise_2"]["analysis"], {"kind": "noise", "args": "v(vref) vsup dec 20 0.1 100k"})
        for name, req in reqs.items():
            self.assertEqual(req["corners"]["supply_v"], {"vsup": [2.97, 3.3, 3.63]})  # vsup is DC + ac 1: alter-able
            self.assertEqual(req["corners"]["temperature_c"], [-40, 27, 125])
            self.assertEqual(req["options"]["ngspice_init"], ["unset sqrnoise"])  # #252: forced amplitude mode
            self.assertTrue(req["options"]["waveforms"])  # the unit metadata the ingestor checks
            self.assertTrue(all("expr" in m and "spice" not in m for m in req["measurements"]))  # no .meas noise type
        self.assertEqual(len(f.plan["requests"][0]["expected_units"]), 81)
        self.assertEqual(fi.plan_problems("output-noise", f.tb, f.plan), [])

    def test_frequency_endpoints_and_point_counts(self):
        nspec = self.fx("output-noise").plan["noise"]
        self.assertEqual(nspec["requests"]["noise_1"]["n_points"], 41)
        self.assertEqual(nspec["requests"]["noise_2"]["n_points"], 121)
        m = nspec["measures"]
        self.assertEqual((m["f_band_lo_hz"]["request"], m["f_band_lo_hz"]["expr"]), ("noise_1", "real(noise1.frequency[0])"))
        self.assertEqual((m["f_band_hi_hz"]["request"], m["f_band_hi_hz"]["expr"]), ("noise_1", "real(noise1.frequency[40])"))
        for name, idx in (("f_spot_1khz_hz", 80), ("f_spot_10khz_hz", 100), ("f_spot_100khz_hz", 120)):
            self.assertEqual((m[name]["request"], m[name]["expr"]), ("noise_2", f"real(noise1.frequency[{idx}])"))

    def test_plot_renumbering_and_scale_stripped_conversions_from_tb_json(self):
        m = self.fx("output-noise").plan["noise"]["measures"]
        # band total: harness noise2 -> request noise_1's own noise2; tb.json scale only, no sqrt (#252)
        self.assertEqual(m["onoise_int_0p1_10hz_uvrms"], {
            "request": "noise_1", "expr": "noise2.onoise_total", "manifest_expr": "noise2.onoise_total * 1e6",
            "kind": "total", "vector": "onoise_total", "scale": 1e6, "si_unit": "V", "unit": "uVrms"})
        # spot density: harness noise3 is the second card's spectrum -> its own request's noise1
        self.assertEqual((m["onoise_1khz_nv_rthz"]["request"], m["onoise_1khz_nv_rthz"]["expr"],
                          m["onoise_1khz_nv_rthz"]["scale"], m["onoise_1khz_nv_rthz"]["si_unit"]),
                         ("noise_2", "noise1.onoise_spectrum[80]", 1e9, "V/sqrt(Hz)"))
        self.assertEqual((m["vref_op"]["request"], m["vref_op"]["expr"]), ("op", "op1.v(vref)"))
        for name, s in m.items():
            self.assertNotIn("sqrt", s["expr"])
            self.assertEqual(s["manifest_expr"], fi.load_tb("output-noise")["measure"][name])

    def test_noise_requests_carry_mode_and_point_count_probes(self):
        self.fx("output-noise")
        for name in ("noise_1", "noise_2"):
            meas = {x["name"]: x for x in json.loads((self.tmp / name / "request.json").read_text())["measurements"]}
            self.assertEqual(meas["sqrnoise_set"]["expr"], "$?sqrnoise")
            self.assertEqual(meas["n_points"]["expr"], "length(noise1.frequency)")
        op = json.loads((self.tmp / "op" / "request.json").read_text())["measurements"]
        self.assertEqual(op, [{"name": "raw_vref_op", "expr": "op1.v(vref)", "unit": "V"}])

    def test_deterministic_serialization_and_identities(self):
        f = self.fx("output-noise")
        plan2, files2 = mk.build_plan("output-noise", f.tb, design_include=self.tmp / "design.ngspice", dut=DUT,
                                      tb_netlist=SIM / "output-noise" / "testbench" / f.tb["netlist"],
                                      dut_rel="sim/dut/bandgap_top.spice", submitting_klt_version="0.7.0+gtest")
        self.assertEqual(files2, f.files)
        self.assertEqual(f.plan["dut"], {"path": "sim/dut/bandgap_top.spice", "sha256": fc.sha256_file(DUT),
                                         "provenance_class": "schematic"})
        self.assertEqual(f.plan["manifest_sha256"], fc.sha256_file(SIM / "output-noise" / "testbench" / "tb.json"))
        self.assertEqual(f.plan["tb_netlist_sha256"], fc.sha256_file(SIM / "output-noise" / "testbench" / f.tb["netlist"]))
        for r in f.plan["requests"]:
            self.assertEqual(r["deck_sha256"], fc.sha256_bytes(f.files[f"{r['name']}/body.spice"].encode()))
            self.assertEqual(r["request_sha256"], fc.sha256_bytes(f.files[f"{r['name']}/request.json"].encode()))
            self.assertIn("begin inlined DUT", f.files[f"{r['name']}/body.spice"])
        self.assertIn("never a spec pass", f.plan["scope"])

    def test_supplied_extracted_dut(self):
        dut = self.tmp / "layout" / "extracted.spice"
        dut.parent.mkdir()
        dut.write_text(DUT.read_text())
        f = self.fx("output-noise", dut=dut, dut_rel="layout/extracted.spice")
        self.assertEqual(f.plan["dut"]["provenance_class"], "extracted")
        self.assertEqual(f.assess()["overall"], fi.MEASURED)
        dut.write_text(".include other.spice\n" + DUT.read_text())  # the fleet stages only the deck
        with self.assertRaises(ValueError):
            self.fx("output-noise", dut=dut, dut_rel="layout/extracted.spice")

    def test_off_contract_manifests_are_refused(self):
        base = fi.load_tb("output-noise")
        bad = {
            "double square root (pre-#252)": {"measure": {**base["measure"],
                                              "onoise_int_0p1_10hz_uvrms": "sqrt(noise2.onoise_total) * 1e6"}},
            "scale disagrees with the name": {"measure": {**base["measure"], "onoise_1khz_nv_rthz": "noise3.onoise_spectrum[80] * 1e6"}},
            "squared vector": {"measure": {**base["measure"], "vref_op": "noise2.onoise_total"}},
            "index past the sweep": {"measure": {**base["measure"], "f_band_hi_hz": "real(noise1.frequency[41])"}},
            "plot not produced": {"measure": {**base["measure"], "f_spot_1khz_hz": "real(noise5.frequency[80])"}},
            "sqrnoise not forced": {"analyses": base["analyses"][1:]},
            "squared mode": {"analyses": ["set sqrnoise"] + base["analyses"][1:]},
            "unmapped analysis": {"analyses": base["analyses"] + ["ac dec 20 0.1 10"]},
            "off-grid band edge": {"analyses": base["analyses"][:2] + ["noise v(vref) vsup dec 20 0.1 15"] + base["analyses"][3:]},
            "threshold-shaped check": {"checks": {**base["checks"], "onoise_int_0p1_10hz_uvrms": {"max_spread_pct": 1}}},
        }
        for why, change in bad.items():
            with self.subTest(why=why), self.assertRaises(ValueError):
                mk.noise_spec(noise_tb(**change))

    def test_plan_drift_from_tb_json_is_a_problem(self):
        f = self.fx("output-noise")
        f.plan["noise"]["measures"]["onoise_int_0p1_10hz_uvrms"]["scale"] = 1e3
        self.assertTrue(any("noise contract" in p for p in fi.plan_problems("output-noise", f.tb, f.plan)))
        g = self.fx("output-noise")
        g.plan["requests"] = g.plan["requests"][:2]  # a band dropped from the plan
        self.assertTrue(fi.plan_problems("output-noise", g.tb, g.plan))

    def test_existing_benches_keep_their_contract(self):
        self.assertEqual(mk.BENCHES, ("psrr-dc", "line-regulation", "startup"))
        self.assertEqual(fi.BENCHES, mk.BENCHES)
        self.assertNotIn("output-noise", mk.BENCHES)
        self.assertIn("output-noise", mk.SUPPORTED)


class NoiseIngest(TmpCase):
    """Phase B: conversion-aware, unit-checked ingestion (#252 contract)."""

    def test_complete_run_is_measured_never_pass(self):
        f = self.fx("output-noise")
        res = f.assess()
        self.assertEqual(res["overall"], fi.MEASURED, res["problems"] + list(map(str, res["invalid"].values())))
        self.assertNotIn(res["overall"], ("PASS", "FAIL"))
        self.assertEqual(len(res["grid"]), 81)
        self.assertEqual(res["spec_fail"], [])
        row = res["rows"][res["grid"][0]]
        self.assertEqual(row["spec"], {})  # no ratified threshold: nothing is graded as spec
        self.assertTrue(all(row["sanity"].values()))

    def test_corrected_conversions_scale_only(self):
        # Known-resistor values from the #252 unit probe: amplitude mode, so
        # uVrms = V * 1e6 and nV/sqrt(Hz) = V/sqrt(Hz) * 1e9 -- no square root.
        def raw(r, i, out):
            if "raw_onoise_1khz_nv_rthz" in out:
                out["raw_onoise_1khz_nv_rthz"] = printed(PROBE_DENSITY_V_RTHZ)
            if "raw_onoise_int_0p1_10hz_uvrms" in out:
                out["raw_onoise_int_0p1_10hz_uvrms"] = printed(PROBE_TOTAL_V * (1 + 0.01 * i))
            return out

        def docs(r, i, doc):
            if r["name"] == "noise_1":
                doc["points"] = [[PROBE_TOTAL_V * (1 + 0.01 * i), 0.0]]
            return doc
        res = self.fx("output-noise", raw=raw, docs=docs).assess()
        self.assertEqual(res["overall"], fi.MEASURED, res["problems"] + list(map(str, res["invalid"].values())))
        m = res["rows"][res["grid"][0]]["measures"]
        self.assertEqual(m["onoise_int_0p1_10hz_uvrms"], PROBE_TOTAL_V * 1e6)  # full precision from the waveform
        self.assertAlmostEqual(m["onoise_int_0p1_10hz_uvrms"], 0.028644637779, places=12)
        self.assertAlmostEqual(m["onoise_1khz_nv_rthz"], 9.103864, places=6)
        self.assertNotAlmostEqual(m["onoise_int_0p1_10hz_uvrms"], math.sqrt(PROBE_TOTAL_V) * 1e6, places=3)

    def test_frequency_endpoints_and_operating_point(self):
        res = self.fx("output-noise").assess()
        m = res["rows"][res["grid"][0]]["measures"]
        self.assertAlmostEqual(m["f_band_lo_hz"], 0.1)
        self.assertAlmostEqual(m["f_band_hi_hz"], 10.0, places=5)
        self.assertAlmostEqual(m["f_spot_1khz_hz"], 1e3, places=2)
        self.assertAlmostEqual(m["f_spot_100khz_hz"], 1e5, places=0)
        self.assertEqual(m["vref_op"], 1.2019834567)  # full precision from the op waveform

    def test_band_edge_off_index_is_invalid(self):
        def raw(r, i, out):
            if "raw_f_band_hi_hz" in out:
                out["raw_f_band_hi_hz"] = 9.0
            return out
        res = self.fx("output-noise", raw=raw).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["invalid"]), 81)
        self.assertTrue(all("f_band_hi_hz" in why for why in res["invalid"].values()))

    def test_operating_point_outside_window_is_invalid(self):
        res = self.fx("output-noise", docs=lambda r, i, d: (
            {**d, "points": [[3.3, 0.2]]} if r["name"] == "op" else d),
            raw=lambda r, i, out: {**out, "raw_vref_op": 0.2} if "raw_vref_op" in out else out).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(all("vref_op" in why for why in res["invalid"].values()))

    def test_squared_mode_is_rejected(self):
        res = self.fx("output-noise", raw=lambda r, i, out: {**out, "sqrnoise_set": 1.0} if "sqrnoise_set" in out else out).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(all("sqrnoise" in why for why in res["invalid"].values()))

        def docs(r, i, d):
            if r["role"] != "noise":
                return d
            return {**d, "plotname": "Integrated Noise - V^2 or A^2",
                    "variables": [{"index": 0, "name": "onoise_total", "type": "voltage^2"},
                                  {"index": 1, "name": "inoise_total", "type": "voltage^2"}]}
        res = self.fx("output-noise", docs=docs).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(all("voltage^2" in why for why in res["invalid"].values()))

    def test_unit_mismatch_is_rejected(self):
        def units(r, i, u):
            if "raw_onoise_1khz_nv_rthz" in u:
                u["raw_onoise_1khz_nv_rthz"] = "V^2/Hz"
            return u
        res = self.fx("output-noise", units=units).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(all("V^2/Hz" in why for why in res["invalid"].values()))
        res = self.fx("output-noise", units=lambda r, i, u: {}).assess()  # a report with no unit metadata at all
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_wrong_point_count_is_rejected(self):
        res = self.fx("output-noise", raw=lambda r, i, out: {**out, "n_points": 21.0} if "n_points" in out else out).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(all("points" in why for why in res["invalid"].values()))

    def test_printed_total_disagreeing_with_waveform_is_rejected(self):
        res = self.fx("output-noise", raw=lambda r, i, out: (
            {**out, "raw_onoise_int_0p1_10hz_uvrms": out["raw_onoise_int_0p1_10hz_uvrms"] * 1.001}
            if "raw_onoise_int_0p1_10hz_uvrms" in out else out)).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_missing_artifacts_and_companion(self):
        res = self.fx("output-noise", docs=lambda r, i, d: None if r["name"] == "noise_2" else d).assess()
        self.assertEqual(res["overall"], "INCOMPLETE")  # spot request without unit metadata
        self.assertEqual(len(res["invalid"]), 81)
        f = self.fx("output-noise")
        del f.reports["op"]
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(all("op" in why for why in res["invalid"].values()))
        g = self.fx("output-noise")
        g.reports["noise_1"]["corners"].pop(0)  # one band corner never came back
        res = g.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["invalid"]), 1)

    def test_flat_grid_fails_the_spread_floor(self):
        f = self.fx("output-noise", docs=lambda r, i, d: (
            {**d, "points": [[PROBE_TOTAL_V * 600, 0.0]]} if r["name"] == "noise_1" else d),
            raw=lambda r, i, out: ({**out, "raw_onoise_int_0p1_10hz_uvrms": printed(PROBE_TOTAL_V * 600)}
                                   if "raw_onoise_int_0p1_10hz_uvrms" in out else out))
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(res["invalid"], {})
        self.assertTrue(any("spread" in p for p in res["problems"]))

    def test_worker_identity_mismatch(self):
        f = self.fx("output-noise")
        f.reports["noise_2"]["environment"]["remote"]["runner_compatibility"] = "mismatch"
        f.reports["noise_2"]["environment"]["remote"]["runner_klt_version"] = "0.5.0"  # predates measurements[].expr
        res = f.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("compatibility" in p for p in res["problems"]))

    def test_record_says_measured_and_writes_suite_logs(self):
        f = self.fx("output-noise")
        res = f.assess()
        exp = self.tmp / "exp" / "output-noise"
        rec = fi.write_evidence(exp, self.tmp, "output-noise", f.tb, f.plan, res, f.reports,
                                dut_label="sim/dut/bandgap_top.spice", issue=268, git=GIT)
        text = rec.read_text()
        self.assertIn("Overall: MEASURED", text)
        self.assertNotIn("Overall: PASS", text)
        self.assertNotIn("| PASS |", text)
        self.assertIn("noise2.onoise_total * 1e6", text)  # the conversion is tb.json's, stated
        self.assertIn("unset sqrnoise", text)
        (cdir,) = list((exp / "corners").iterdir())
        samples = analysis.read_corner_logs(cdir)
        self.assertEqual(len(samples), 81)
        self.assertIn("onoise_int_0p1_10hz_uvrms", next(iter(samples.values())))
        self.assertEqual(len(list((exp / "netlist-snapshots").glob("*.spice"))), 3)


class NoiseFails(Fails):
    """The shared completeness / provenance fixtures, run on output-noise."""
    BENCHES = (mk.NOISE_BENCH,)

    def first_request(self, f):
        return "noise_1"


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

    # ---- run-level rejection must not become suite-valid evidence (#284)

    def _tree(self, root: Path) -> list:
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

    def _assert_rejected(self, bench, fx, res):
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(res["problems"])
        exp = self.tmp / "exp" / bench
        before = self._tree(self.tmp)
        with self.assertRaises(ValueError) as cm:
            fi.write_evidence(exp, self.tmp, bench, fx.tb, fx.plan, res, fx.reports,
                              dut_label="sim/dut/bandgap_top.spice", issue=284, git=GIT)
        self.assertIn("run-level problems", str(cm.exception))
        self.assertFalse(exp.exists())  # no record, corner or snapshot files
        self.assertEqual(self._tree(self.tmp), before)  # diagnostics in the work dir untouched
        # direct log export fails closed too: nothing a suite could grade
        cdir = self.tmp / "direct"
        with self.assertRaises(ValueError):
            fi.write_corner_logs(cdir, self.tmp, fx.plan, res, "rec")
        self.assertFalse(cdir.exists())
        if cdir.exists():
            run = bench_run_from(bench, cdir)
            self.assertNotIn("PASS", [o.status for o in run.outcomes])

    def test_run_level_rejections_write_nothing_and_cannot_pass(self):
        def runner(fx):
            fx.reports["sweep"]["environment"]["remote"]["runner_compatibility"] = "mismatch"
            return fx.assess()

        def dut(fx):
            return fx.assess(dut_sha="0" * 64)

        def deck(fx):
            d = fx.decks()
            d["sweep"] += "* tampered\n"
            return fx.assess(decks=d)

        def manifest(fx):
            return fx.assess(manifest_sha="1" * 64)

        def dup(fx):
            cs = fx.reports["sweep"]["corners"]
            cs.append(copy.deepcopy(cs[0]))
            extra = copy.deepcopy(cs[0])
            extra["corner_id"] = extra["corner_id"].replace(cs[0]["corner_id"].split("/")[0], "zz", 1)
            cs.append(extra)
            return fx.assess()

        for name, mut in [("runner", runner), ("dut", dut), ("deck", deck), ("manifest", manifest), ("dup", dup)]:
            with self.subTest(case=name):
                self.setUp()
                fx = self.fx("line-regulation")
                self._assert_rejected("line-regulation", fx, mut(fx))

    def test_valid_spec_failure_is_still_recorded_as_fail(self):
        fx = self.fx("line-regulation", vals=lambda r, p, s, t: {
            "vref_min": 1.19, "vref_max": 1.2, "v_lo_check": 2.97, "v_hi_check": 3.63},
            wave=lambda *a: {"x": [2.97 + 0.005 * i for i in range(133)], "v(vref)": [1.19] * 66 + [1.2] * 67})
        res, exp, rec = self.ingest("line-regulation", fx)
        self.assertEqual(res["problems"], [])
        self.assertEqual(res["overall"], "FAIL")
        self.assertIn("FAIL", rec.read_text())
        self.assertTrue(list((exp / "netlist-snapshots").glob("*.spice")))


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

    def test_collect_units_execution_policy(self):
        def rep(**kw):
            c = {"corner_id": "tt/3.300V/27C", "status": "pass", "diagnostics": [],
                 "measurements": [{"name": "a", "value": 1.0}]}
            c.update(kw)
            return {"corners": [c]}
        def run(r):
            return fc.collect_units(r, [("tt", 3.3)], ["a"], lambda cid: fc.parse_klt_corner_id(cid)[:2])
        pts, miss, fail, _ = run(rep())
        self.assertTrue(pts and not miss and not fail)
        pts, miss, fail, _ = run(rep(status="fail"))
        self.assertTrue(pts and not fail)
        warn = [{"severity": "warning", "code": "w", "message": "m"}]
        self.assertTrue(run(rep(diagnostics=warn))[0])
        for bad in (rep(status="inconclusive"), rep(status="weird"), rep(status=None),
                    rep(diagnostics=[{"severity": "error", "code": "e", "message": "m"}]),
                    rep(diagnostics=[{"code": "e", "message": "no severity"}]),
                    rep(diagnostics=["junk"])):
            pts, miss, fail, _ = run(bad)
            self.assertEqual(pts, {})
            self.assertEqual(len(fail), 1)
        r = rep(); del r["corners"][0]["status"]
        self.assertEqual(len(run(r)[2]), 1)

    def test_collect_units_rejects_duplicate_measurement_names(self):
        def run(ms):
            r = {"corners": [{"corner_id": "tt/3.300V/27C", "status": "pass", "diagnostics": [], "measurements": ms}]}
            return fc.collect_units(r, [("tt", 3.3)], ["a"], lambda cid: fc.parse_klt_corner_id(cid)[:2])
        a = lambda v: {"name": "a", "value": v}
        pts, miss, fail, _ = run([a(1.0), {"name": "b", "value": 2.0}])
        self.assertEqual(pts, {("tt", 3.3): {"a": 1.0, "b": 2.0}})
        for ms in ([a(None), a(1.2)], [a(1.2), a(None)], [a(1.0), a(1.0)], [a(9e9), a(1.0)], [a(1.0), a(9e9)]):
            pts, miss, fail, _ = run(ms)
            self.assertEqual(pts, {})
            self.assertEqual(len(fail), 1)
            self.assertIn("'a'", fail[0][1])

    def test_corner_id_parsing(self):
        self.assertEqual(fc.parse_klt_corner_id("bjt_ff/2.970V/-40C"), ("bjt_ff", 2.97, -40.0))
        self.assertEqual(fc.parse_klt_corner_id("tt/novdd/125C"), ("tt", None, 125.0))
        with self.assertRaises(ValueError):
            fc.parse_klt_corner_id("tt/3.300V/27C/mc3")


if __name__ == "__main__":
    unittest.main()
