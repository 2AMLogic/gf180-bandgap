#!/usr/bin/env python3
"""Fixture checks for the fleet Monte Carlo mismatch adapter (#238).

No PDK, ngspice, fleet credentials or network: the PDK include is a stub, and
every klt report is synthesized from the plan the real request builder wrote.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import copy
import json
import math
import random
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import fleet_common as fc  # noqa: E402
import mc_fleet_ingest as mi  # noqa: E402
import mk_klt_mc_request as mk  # noqa: E402
from harness import corners as hc  # noqa: E402
from harness import evidence_lint  # noqa: E402
from suite import combined  # noqa: E402

RUN = mk.load_run_module()
DUT = REPO / "sim" / "dut" / "bandgap_top.spice"
DESIGN_STUB = "* design.ngspice stub\n.param\n+ sw_stat_global = 0\n+ sw_stat_mismatch = 0\n"
REMOTE = {
    "provider": "aws-batch", "job_id": "job-1", "instance_type": "c7a", "lifecycle": "spot", "state": "SUCCEEDED",
    "exit_code": 0, "runner_klt_version": "0.7.0+gtest", "client_klt_version": "0.7.0+gtest",
    "runner_compatibility": "match",
}
GIT = {"short": "abc1234", "commit": "abc1234", "branch": "test", "dirty": False}
KLT = "0.7.0+gtest"

#: Per-group sigma (V) of the synthesized Vref, and the nominal Vref per temperature.
SIGMA = {"mm_ctrl": 0.0, "mm_res": 0.0009, "mm_fetbjt": 0.0033, "mm_all": 0.0035}
NOMINAL = {-40.0: 1.1951, 27.0: 1.2020, 125.0: 1.1980}


def fake_report(entry: dict, *, sigma: float, nominal: float, isup: float = 2.0e-5, remote=REMOTE,
                seed_offset: int = 0) -> dict:
    """What `klt sim` returns for one monte_carlo request (6-digit .meas values)."""
    rng = random.Random(zlib.crc32(entry["group"].encode()))
    corners = []
    for i in range(entry["n"]):
        v = float(f"{nominal + (rng.gauss(0, sigma) if sigma else 0.0):.6g}")
        i_a = float(f"{-isup:.6g}")
        corners.append({
            "corner_id": f"tt/3.300V/{entry['temp_c']:g}C/mc{i}",
            "status": "pass",
            "measurements": [
                {"name": "vref_lo", "value": v}, {"name": "vref_hi", "value": v},
                {"name": "isup_lo", "value": i_a}, {"name": "isup_hi", "value": i_a},
            ],
            "diagnostics": [],
            "monte_carlo": {"sample_index": i, "seed": 1000 + i + seed_offset, "process_seed": 7,
                            "mismatch_seed": 5000 + i},
        })
    return {
        "status": "pass", "corners": corners,
        "environment": {"engine": "ngspice", "engine_version": "46",
                        "monte_carlo": {"n": entry["n"], "seed": entry["seed"], "vary": entry["vary"]},
                        **({"remote": dict(remote)} if remote else {})},
        "provenance": {"klt_version": KLT, "pdk": {"name": "gf180mcuD", "version": "x"}},
    }


class Fixture:
    def __init__(self):
        self.plan, self.files = mk.build_plan(dut=DUT, dut_rel="sim/dut/bandgap_top.spice", design_text=DESIGN_STUB,
                                              submitting_klt_version=KLT)
        self.decks = {n.split("/")[0]: t for n, t in self.files.items() if n.endswith("body.spice")}
        self.requests = {n.split("/")[0]: t for n, t in self.files.items() if n.endswith("request.json")}
        self.reports = {
            e["name"]: fake_report(e, sigma=SIGMA[e["group"]], nominal=NOMINAL[e["temp_c"]])
            for e in self.plan["requests"]
        }
        self.dut_sha = fc.sha256_file(DUT)
        self.tb_sha = fc.sha256_file(mk.TB_PATH)

    def assess(self, plan=None, **kw):
        args = dict(dut_sha=self.dut_sha, tb_sha=self.tb_sha, decks=self.decks, requests=self.requests)
        args.update(kw)
        return mi.assess(RUN, plan or self.plan, self.reports, **args)

    def entry(self, group, temp):
        return next(e for e in self.plan["requests"] if e["group"] == group and e["temp_c"] == temp)


class RequestBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture()

    def test_the_grid_is_the_run_scripts_groups_times_temperatures(self):
        plan = self.fx.plan
        self.assertEqual(len(plan["requests"]), len(RUN.GROUPS) * len(RUN.TEMPS))
        self.assertEqual([(e["group"], e["temp_c"]) for e in plan["requests"]],
                         [(g, float(t)) for g in RUN.GROUPS for t in RUN.TEMPS])

    def test_monte_carlo_block_n_seed_vary_and_one_temperature_each(self):
        for name, text in self.fx.requests.items():
            req = json.loads(text)
            self.assertEqual(req["monte_carlo"], {"n": 300, "seed": RUN.SEED, "vary": "mismatch"})
            self.assertGreaterEqual(req["monte_carlo"]["n"], 300)
            self.assertEqual(len(req["corners"]["temperature_c"]), 1, name)
            self.assertEqual(req["corners"]["supply_v"], {"vsup": [RUN.SUPPLY_V]})
            self.assertEqual(req["corners"]["process"], [{"name": "tt", "sections": list(RUN.SECTIONS)}])
            self.assertEqual(req["analysis"], {"kind": "dc", "args": "vsup 3.3 3.3 1"})
            self.assertFalse(any("expr" in m for m in req["measurements"]))
            self.assertEqual(req["options"]["ngspice_init"], ["set measureprec=10"])

    def test_sections_are_the_harness_tt_bundle(self):
        self.assertEqual(tuple(hc.CORNERS["tt"].sections), tuple(RUN.SECTIONS))

    def test_group_switches_and_dut_variants_come_from_GROUPS(self):
        for e in self.fx.plan["requests"]:
            deck = self.fx.decks[e["name"]]
            cfg = RUN.GROUPS[e["group"]]
            self.assertIn(f".param sw_stat_mismatch = {cfg['sw_stat_mismatch']}\n", deck)
            self.assertEqual("agauss(" in deck, cfg["dut"] == "mm", e["name"])
            self.assertFalse([l for l in deck.splitlines() if l.lower().startswith((".control", ".endc"))], e["name"])

    def test_the_resistor_override_is_the_run_scripts_injection(self):
        variants, injected = RUN.prepare_dut_variants(DUT.read_text())
        self.assertEqual(self.fx.plan["injected"], injected)
        self.assertTrue(injected)
        self.assertIn(variants["mm"].rstrip(), self.fx.decks["mm_all_27c"])
        self.assertIn(variants["baseline"].rstrip(), self.fx.decks["mm_ctrl_27c"])
        # the PDK's own mis_r is NOT used: it rides the same switch as MOS/BJT.
        self.assertNotIn("mis_r", self.fx.decks["mm_res_27c"].split("end inlined design.ngspice")[1])

    def test_the_bench_circuit_is_the_testbenchs_not_a_copy(self):
        deck = self.fx.decks["mm_all_27c"]
        tb = mk.TB_PATH.read_text()
        for line in ("vsup vdd 0 dc 3.30", "vssref vss 0 dc 0"):
            self.assertIn(line, tb)
            self.assertIn(line, deck)
        self.assertIn("xdut vdd vss vref bandgap_top", deck)
        self.assertIn("v(xdut.fb)=1.0", deck)        # internal node gains the instance prefix
        self.assertIn("v(vref)=1.2", deck)           # a port does not
        self.assertNotIn("xdut.vref", deck)

    def test_run_constants_agree_with_the_committed_testbench(self):
        consts = RUN.testbench_constants(mk.TB_PATH.read_text())
        self.assertEqual(consts, {"mc_runs": RUN.N_SAMPLES, "seed": RUN.SEED, "supply_v": RUN.SUPPLY_V})

    def test_n_below_the_ratified_floor_is_refused(self):
        for n in (1, 299):
            with self.subTest(n=n), self.assertRaisesRegex(ValueError, "N>=300"):
                mk.build_plan(dut=DUT, dut_rel="x", design_text=DESIGN_STUB, n=n)

    def test_the_flattened_export_is_refused_not_misread(self):
        with self.assertRaisesRegex(ValueError, "no `.subckt bandgap_top`"):
            mk.build_plan(dut=REPO / "design" / "netlist" / "bandgap_top.spice", dut_rel="x", design_text=DESIGN_STUB)

    def test_a_testbench_that_disagrees_with_the_constants_is_refused(self):
        tb = mk.TB_PATH.read_text().replace("let mc_runs = 300", "let mc_runs = 200")
        with self.assertRaisesRegex(ValueError, "disagree"):
            mk.build_plan(dut=DUT, dut_rel="x", design_text=DESIGN_STUB, tb_text=tb)

    def test_plan_freezes_hashes(self):
        plan = self.fx.plan
        self.assertEqual(plan["dut"]["sha256"], fc.sha256_file(DUT))
        for e in plan["requests"]:
            self.assertEqual(e["deck_sha256"], fc.sha256_bytes(self.fx.decks[e["name"]].encode()))
            self.assertEqual(e["request_sha256"], fc.sha256_bytes(self.fx.requests[e["name"]].encode()))


class CornerIdGrammar(unittest.TestCase):
    def test_mc_ids_parse(self):
        self.assertEqual(fc.parse_klt_mc_corner_id("tt/3.300V/27C/mc17"), ("tt", 3.3, 27.0, 17))
        self.assertEqual(fc.parse_klt_mc_corner_id("tt/3.300V/-40C/mc0"), ("tt", 3.3, -40.0, 0))

    def test_malformed_mc_ids_raise(self):
        for bad in ("tt/3.300V/27C", "tt/3.300V/27C/mc", "tt/3.300V/27C/mcx", "tt/3.300V/27C/3", "tt/27C/mc1", "mc1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fc.parse_klt_mc_corner_id(bad)

    def test_deterministic_parser_still_rejects_mc_ids(self):
        with self.assertRaises(ValueError):
            fc.parse_klt_corner_id("tt/3.300V/27C/mc3")


class Ingest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture()

    def setUp(self):
        self.fx = copy.deepcopy(self.__class__.fx)

    def test_complete_consistent_grid_passes_with_statistics(self):
        res = self.fx.assess()
        self.assertEqual(res["problems"], [])
        self.assertEqual(res["overall"], "PASS")
        for g in RUN.GROUPS:
            for t in RUN.TEMPS:
                st = res["stats"][g][t]
                self.assertEqual(st["n"], 300)
                self.assertEqual(st["degenerate_count"], 0)
        self.assertEqual(res["stats"]["mm_ctrl"][27.0]["sigma"], 0.0)
        self.assertAlmostEqual(res["stats"]["mm_all"][27.0]["mean"], NOMINAL[27.0], delta=1e-3)
        self.assertAlmostEqual(res["stats"]["mm_all"][27.0]["sigma"], SIGMA["mm_all"], delta=5e-4)
        self.assertAlmostEqual(res["stats"]["mm_all"][27.0]["isup_mean"], 2.0e-5, places=9)

    def test_statistics_use_the_n_minus_1_sigma(self):
        entry = self.fx.entry("mm_all", 27.0)
        rep = self.fx.reports[entry["name"]]
        vals = [m["value"] for c in rep["corners"] for m in c["measurements"] if m["name"] == "vref_lo"]
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
        self.assertAlmostEqual(self.fx.assess()["stats"]["mm_all"][27.0]["sigma"], sd, places=12)

    def test_window_miss_is_FAIL_not_incomplete(self):
        e = self.fx.entry("mm_all", 125.0)
        self.fx.reports[e["name"]] = fake_report(e, sigma=0.02, nominal=1.198)
        res = self.fx.assess()
        self.assertEqual(res["problems"], [])
        self.assertEqual(res["overall"], "FAIL")

    def test_degenerate_sample_is_FAIL(self):
        e = self.fx.entry("mm_fetbjt", 27.0)
        c = self.fx.reports[e["name"]]["corners"][5]
        for m in c["measurements"]:
            if m["name"].startswith("isup"):
                m["value"] = -1e-12
        res = self.fx.assess()
        self.assertEqual(res["stats"]["mm_fetbjt"][27.0]["degenerate_count"], 1)
        self.assertEqual(res["overall"], "FAIL")

    # ---- N < 300 -------------------------------------------------------

    def test_plan_with_n_below_300_is_incomplete(self):
        plan = copy.deepcopy(self.fx.plan)
        plan["n"] = 299
        for e in plan["requests"]:
            e["n"] = 299
        res = mi.assess(RUN, plan, self.fx.reports, dut_sha=self.fx.dut_sha, tb_sha=self.fx.tb_sha, decks=self.fx.decks)
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("below the ratified floor" in p for p in res["problems"]))

    def test_report_with_fewer_samples_than_requested_is_incomplete_and_listed(self):
        e = self.fx.entry("mm_all", 27.0)
        del self.fx.reports[e["name"]]["corners"][-10:]
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len([m for m in res["missing"] if m[0][0] == e["name"]]), 10)
        self.assertNotIn(27.0, res["stats"]["mm_all"])  # no statistics from a short sample set

    # ---- missing temperature / group ----------------------------------

    def test_missing_temperature_request_is_incomplete(self):
        plan = copy.deepcopy(self.fx.plan)
        plan["requests"] = [e for e in plan["requests"] if e["temp_c"] != -40.0]
        res = mi.assess(RUN, plan, self.fx.reports, dut_sha=self.fx.dut_sha, tb_sha=self.fx.tb_sha, decks=self.fx.decks)
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("-40 C" in p and "no request" in p for p in res["problems"]))

    def test_missing_group_request_is_incomplete(self):
        plan = copy.deepcopy(self.fx.plan)
        plan["requests"] = [e for e in plan["requests"] if e["group"] != "mm_ctrl"]
        res = mi.assess(RUN, plan, self.fx.reports, dut_sha=self.fx.dut_sha, tb_sha=self.fx.tb_sha, decks=self.fx.decks)
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("'mm_ctrl'" in p for p in res["problems"]))

    def test_missing_report_for_a_request_is_incomplete(self):
        name = self.fx.entry("mm_res", 125.0)["name"]
        del self.fx.reports[name]
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(res["missing"][0][0], (name,))

    def test_changed_group_definition_invalidates_the_plan(self):
        plan = copy.deepcopy(self.fx.plan)
        plan["definition"]["groups"]["mm_all"]["sw_stat_mismatch"] = 0
        res = mi.assess(RUN, plan, self.fx.reports, dut_sha=self.fx.dut_sha, tb_sha=self.fx.tb_sha, decks=self.fx.decks)
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("definition" in p for p in res["problems"]))

    # ---- backend error --------------------------------------------------

    def test_errored_samples_are_failed_never_dropped(self):
        e = self.fx.entry("mm_fetbjt", -40.0)
        c = self.fx.reports[e["name"]]["corners"][3]
        c["status"] = "error"
        c["diagnostics"] = [{"code": "ngspice", "message": "singular matrix"}]
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["failed"]), 1)
        self.assertIn("singular matrix", res["failed"][0][1])

    def test_finite_values_with_invalid_execution_are_never_measured(self):
        e = self.fx.entry("mm_fetbjt", -40.0)
        c = self.fx.reports[e["name"]]["corners"][3]
        c["diagnostics"] = [{"severity": "error", "code": "simulation_failed", "message": "kaboom"}]
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertNotEqual(res["overall"], "MEASURED")
        self.assertEqual(len(res["failed"]), 1)
        self.assertIn("kaboom", res["failed"][0][1])
        c["diagnostics"] = []
        del c["status"]
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["failed"]), 1)

    def test_duplicate_measurement_names_are_rejected_and_mint_nothing(self):
        for first, second in ((None, 1.0), (1.0, None), (2.0, 2.0)):
            fx = copy.deepcopy(self.fx)
            e = fx.entry("mm_fetbjt", -40.0)
            ms = fx.reports[e["name"]]["corners"][3]["measurements"]
            name = ms[0]["name"]
            ms[0:1] = [{"name": name, "value": first}, {"name": name, "value": second}]
            res = fx.assess()
            self.assertEqual(res["overall"], "INCOMPLETE", (first, second))
            self.assertEqual(len(res["failed"]), 1)
            self.assertIn("duplicate measurement", res["failed"][0][1])
            with tempfile.TemporaryDirectory() as tmp:
                exp = Path(tmp) / "mc-dup"
                with self.assertRaises(ValueError):
                    mi.write_evidence(RUN, exp, Path(tmp), fx.plan, res, fx.reports, fx.decks, dut_label="x",
                                      dut_path=DUT, issue=290, git=GIT)
                self.assertFalse(exp.exists())

    def test_a_whole_request_that_errored_out_is_incomplete(self):
        e = self.fx.entry("mm_all", 27.0)
        self.fx.reports[e["name"]]["corners"] = []
        self.fx.reports[e["name"]]["status"] = "error"
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertEqual(len(res["missing"]), 300)

    def test_report_that_was_not_a_fleet_run_is_a_problem(self):
        e = self.fx.entry("mm_all", 27.0)
        self.fx.reports[e["name"]]["environment"].pop("remote")
        res = self.fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("not a fleet run" in p for p in res["problems"]))
        # ... but allowed explicitly (local debug ingest)
        self.assertEqual(self.fx.assess(require_remote=False)["overall"], "PASS")

    def test_runner_version_skew_is_a_problem(self):
        e = self.fx.entry("mm_all", 27.0)
        self.fx.reports[e["name"]]["environment"]["remote"]["runner_compatibility"] = "mismatch"
        self.assertTrue(any("compatibility" in p for p in self.fx.assess()["problems"]))

    # ---- DUT mismatch ---------------------------------------------------

    def test_dut_hash_differing_from_the_plan_is_a_problem(self):
        res = self.fx.assess(dut_sha="0" * 64)
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(any("DUT sha256" in p for p in res["problems"]))

    def test_edited_deck_or_request_after_generation_is_a_problem(self):
        decks = dict(self.fx.decks)
        decks["mm_all_27c"] += "* edited\n"
        res = self.fx.assess(decks=decks)
        self.assertTrue(any("mm_all_27c" in p and "deck sha256" in p for p in res["problems"]))
        reqs = dict(self.fx.requests)
        reqs["mm_all_27c"] = reqs["mm_all_27c"].replace("300", "299")
        self.assertTrue(any("request.json sha256" in p for p in self.fx.assess(requests=reqs)["problems"]))

    def test_testbench_change_is_a_problem(self):
        self.assertTrue(any("testbench" in p for p in self.fx.assess(tb_sha="f" * 64)["problems"]))

    # ---- malformed samples ---------------------------------------------

    def _first(self, group="mm_all", temp=27.0):
        e = self.fx.entry(group, temp)
        return e, self.fx.reports[e["name"]]["corners"]

    def test_null_nan_and_inf_measurements_are_missing_not_zero(self):
        for bad in (None, float("nan"), float("inf")):
            with self.subTest(bad=bad):
                self.setUp()
                _e, corners = self._first()
                corners[2]["measurements"][0]["value"] = bad
                res = self.fx.assess()
                self.assertEqual(res["overall"], "INCOMPLETE")
                self.assertEqual(len(res["missing"]), 1)

    def test_non_mc_and_unparseable_ids_are_problems(self):
        for bad in ("tt/3.300V/27C", "garbage"):
            with self.subTest(bad=bad):
                self.setUp()
                _e, corners = self._first()
                corners[0]["corner_id"] = bad
                res = self.fx.assess()
                self.assertEqual(res["overall"], "INCOMPLETE")
                self.assertTrue(any("unparseable" in p for p in res["problems"]))

    def test_duplicate_and_unexpected_samples_are_problems(self):
        _e, corners = self._first()
        corners.append(copy.deepcopy(corners[4]))
        corners.append({**copy.deepcopy(corners[0]), "corner_id": "tt/3.300V/27C/mc300"})
        res = self.fx.assess()
        self.assertTrue(any("duplicate corner" in p for p in res["problems"]))
        self.assertTrue(any("unexpected corner" in p for p in res["problems"]))
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_wrong_temperature_in_a_report_is_unexpected(self):
        _e, corners = self._first()
        corners[0]["corner_id"] = "tt/3.300V/125C/mc0"
        self.assertEqual(self.fx.assess()["overall"], "INCOMPLETE")

    def test_sample_index_must_match_its_id(self):
        _e, corners = self._first()
        corners[7]["monte_carlo"]["sample_index"] = 8
        self.assertTrue(any("sample_index" in p for p in self.fx.assess()["problems"]))

    def test_repeated_sample_seeds_mean_the_sampler_did_not_vary(self):
        _e, corners = self._first()
        corners[9]["monte_carlo"]["seed"] = corners[8]["monte_carlo"]["seed"]
        self.assertTrue(any("not distinct" in p for p in self.fx.assess()["problems"]))

    def test_seeds_must_be_common_across_requests(self):
        e = self.fx.entry("mm_res", 27.0)
        self.fx.reports[e["name"]] = fake_report(e, sigma=SIGMA["mm_res"], nominal=NOMINAL[27.0], seed_offset=1)
        self.assertTrue(any("common random numbers" in p for p in self.fx.assess()["problems"]))

    def test_report_without_or_with_wrong_monte_carlo_echo_is_a_problem(self):
        e = self.fx.entry("mm_all", 27.0)
        rep = self.fx.reports[e["name"]]
        rep["environment"]["monte_carlo"]["seed"] = 1
        self.assertTrue(any("monte_carlo.seed" in p for p in self.fx.assess()["problems"]))
        rep["environment"].pop("monte_carlo")
        self.assertTrue(any("not a Monte Carlo run" in p for p in self.fx.assess()["problems"]))

    def test_min_max_disagreement_means_more_than_one_sweep_point(self):
        _e, corners = self._first()
        corners[1]["measurements"][1]["value"] += 0.01
        res = self.fx.assess()
        self.assertTrue(any("one-point sweep" in p for p in res["problems"]))
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_control_group_must_be_exactly_deterministic(self):
        e = self.fx.entry("mm_ctrl", 27.0)
        self.fx.reports[e["name"]] = fake_report(e, sigma=0.001, nominal=NOMINAL[27.0])
        res = self.fx.assess()
        self.assertTrue(any("control sigma" in p for p in res["problems"]))
        self.assertEqual(res["overall"], "INCOMPLETE")

    def test_a_mismatch_group_with_zero_spread_means_mismatch_was_not_sampled(self):
        e = self.fx.entry("mm_res", 27.0)
        self.fx.reports[e["name"]] = fake_report(e, sigma=0.0, nominal=NOMINAL[27.0])
        res = self.fx.assess()
        self.assertTrue(any("mismatch was not sampled" in p for p in res["problems"]))
        self.assertEqual(res["overall"], "INCOMPLETE")


class Evidence(unittest.TestCase):
    """The minted record is read by check_records and combined like any other."""

    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture()

    def mint(self, root: Path):
        fx = self.fx
        res = fx.assess()
        self.assertEqual(res["overall"], "PASS")
        work = root / "work"
        for rel, text in fx.files.items():
            p = work / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        exp = root / "sim" / "mc-untrimmed"
        rec = mi.write_evidence(RUN, exp, work, fx.plan, res, fx.reports, fx.decks, dut_label="sim/dut/bandgap_top.spice",
                                dut_path=DUT, issue=238, git=GIT)
        return res, exp, rec

    def test_logs_round_trip_through_combined_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            res, exp, rec = self.mint(Path(tmp))
            (cdir,) = list((exp / "corners").iterdir())
            groups = combined.read_mc_groups(cdir)
        self.assertEqual(len(groups), 12)
        for (g, t), gs in groups.items():
            st = res["stats"][g][t]
            self.assertEqual(gs.n, 300)
            # logs store 10 significant digits of values that are 6-digit already
            self.assertAlmostEqual(gs.mean_v, st["mean"], places=9)
            self.assertAlmostEqual(gs.sigma_v, st["sigma"], places=9)

    def test_record_states_dut_identity_and_n_and_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            _res, _exp, rec = self.mint(Path(tmp))
            text = rec.read_text()
            self.assertEqual(combined.dut_sha_of_path(rec), fc.sha256_file(DUT))
            self.assertEqual(combined.provenance_of_path(rec), "schematic")
        self.assertIn("**DUT identity**", text)
        self.assertIn("**N = 300**", text)
        self.assertIn("monte_carlo", text)
        self.assertIn("| `mm_all` | 27 |", text)
        self.assertIn("mean +/- 3 sigma", text)
        self.assertIn("Overall (mismatch-MC leg): PASS", text)
        self.assertNotIn("Provisional-amp caveat", text)

    def test_record_passes_the_evidence_linter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.mint(root)
            paths, _source = evidence_lint.list_evidence_paths(root)
            problems = evidence_lint.check_experiments(root, evidence_lint.collect_experiments(paths))
        self.assertEqual(problems, [])

    def test_incomplete_grid_mints_nothing(self):
        fx = copy.deepcopy(self.fx)
        del fx.reports[fx.plan["requests"][0]["name"]]
        res = fx.assess()
        with tempfile.TemporaryDirectory() as tmp:
            exp = Path(tmp) / "mc-untrimmed"
            with self.assertRaises(ValueError):
                mi.write_evidence(RUN, exp, Path(tmp), fx.plan, res, fx.reports, fx.decks, dut_label="x",
                                  dut_path=DUT, issue=238, git=GIT)
            self.assertFalse(exp.exists())

    def test_fleet_mc_leg_pairs_with_a_matching_corner_record_and_anchors_on_the_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res, exp, rec = self.mint(root)
            sim_dir = root / "sim"
            cid = "20260802-010000-abcdef0"
            ctrl27 = res["stats"]["mm_ctrl"][27.0]["mean"]
            corner = sim_dir / combined.CORNER_SLUG
            (corner / "corners" / cid).mkdir(parents=True)
            (corner / "records").mkdir()
            sha = fc.sha256_file(DUT)
            (corner / "records" / f"{cid}.md").write_text(
                f"- **Netlist provenance**: schematic -- DUT `sim/dut/bandgap_top.spice` (sha256 `{sha}`)\n")
            for t in (-40, 27, 125):
                (corner / "corners" / cid / f"tt_{t}c_3.30v.log").write_text(
                    f"m_vref = {res['stats']['mm_ctrl'][float(t)]['mean']:.10e}\n")
            v = combined.load(sim_dir=sim_dir)
            self.assertEqual(v.problems, [])
            self.assertEqual(v.status, "PASS")
            self.assertTrue(v.anchors_agree)
            self.assertEqual(v.anchors_evaluated, 3)
            # a corner leg of a different DUT is refused
            (corner / "records" / f"{cid}.md").write_text(
                f"- **Netlist provenance**: schematic -- DUT `x` (sha256 `{'e' * 64}`)\n")
            self.assertTrue(any("different DUTs" in p for p in combined.load(sim_dir=sim_dir).problems))
            # a corner leg whose tt point disagrees with the control is INVALID
            (corner / "records" / f"{cid}.md").write_text(
                f"- **Netlist provenance**: schematic -- DUT `x` (sha256 `{sha}`)\n")
            (corner / "corners" / cid / "tt_27c_3.30v.log").write_text(f"m_vref = {ctrl27 + 0.01:.10e}\n")
            self.assertEqual(combined.load(sim_dir=sim_dir).status, "INVALID")


class CommandLine(unittest.TestCase):
    def test_ingest_dry_run_on_a_written_workdir_reports_without_writing(self):
        fx = Fixture()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for rel, text in fx.files.items():
                p = work / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
            for name, rep in fx.reports.items():
                (work / name / "report.json").write_text(json.dumps(rep))
            plan, reports, decks, requests = mi.load_work(work)
            self.assertEqual(set(reports), set(fx.reports))
            res = mi.assess(RUN, plan, reports, dut_sha=fx.dut_sha, tb_sha=fx.tb_sha, decks=decks, requests=requests)
        self.assertEqual(res["overall"], "PASS")


if __name__ == "__main__":
    unittest.main()
