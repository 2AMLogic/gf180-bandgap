#!/usr/bin/env python3
"""Returned fleet reports must be bound to the frozen generated deck (#293).

No PDK, ngspice or fleet required:

    python3 -m unittest discover -s sim/tests -t sim/tests -p test_report_identity.py -v
"""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import fleet_common as fc  # noqa: E402
import tc_ingest as ti  # noqa: E402
import test_fleet_ingest as tfi  # noqa: E402
import test_load_ingest as tli  # noqa: E402
import test_mc_fleet as tmc  # noqa: E402
import test_tc_ingest as ttc  # noqa: E402

GOOD = "ab" * 32
OTHER = "cd" * 32


def rep(env=None, inp=None, model=None):
    r = {"environment": {}, "provenance": {}}
    if env is not None:
        r["environment"]["netlist_sha256"] = env
    if inp is not None:
        r["provenance"]["input"] = {"content_hash": inp, "role": "netlist"}
    if model is not None:
        r["provenance"]["deck"] = {"name": "sm141064.ngspice", "content_hash": model}
    return r


def has(problems, text):
    return any(text in p for p in problems)


class Helper(unittest.TestCase):
    def test_valid_forms(self):
        self.assertEqual(fc.report_identity_problems(rep(env=GOOD), GOOD), [])
        self.assertEqual(fc.report_identity_problems(rep(inp="sha256:" + GOOD), GOOD), [])
        self.assertEqual(fc.report_identity_problems(rep(env=GOOD, inp="sha256:" + GOOD), GOOD), [])
        self.assertEqual(fc.report_identity_problems(rep(env=GOOD.upper(), inp="sha256:" + GOOD), GOOD), [])
        self.assertEqual(fc.report_identity_problems(rep(env=GOOD), GOOD.upper()), [])

    def test_mismatch(self):
        self.assertTrue(has(fc.report_identity_problems(rep(env=OTHER, inp="sha256:" + OTHER), GOOD), "different deck"))

    def test_missing(self):
        self.assertTrue(has(fc.report_identity_problems(rep(), GOOD), "no root-input identity"))
        self.assertTrue(has(fc.report_identity_problems({}, GOOD), "no root-input identity"))

    def test_model_deck_hash_is_not_identity(self):
        self.assertTrue(has(fc.report_identity_problems(rep(model="sha256:" + GOOD), GOOD), "no root-input identity"))

    def test_malformed(self):
        for bad in (123, None, "", GOOD[:-1], GOOD + "a", "g" * 64, "md5:" + GOOD, "sha512:" + GOOD,
                    " " + GOOD, "SHA256:" + GOOD, "sha256:sha256:" + GOOD):
            probs = fc.report_identity_problems(rep(env=bad), GOOD)
            self.assertEqual(len(probs), 1, (bad, probs))
            self.assertIn("environment.netlist_sha256", probs[0])
        self.assertTrue(has(fc.report_identity_problems(rep(inp=GOOD[:10]), GOOD), "provenance.input.content_hash"))
        # malformed container shapes never raise
        for r in ({"environment": 3, "provenance": "x"}, {"provenance": {"input": []}}, None, []):
            self.assertTrue(fc.report_identity_problems(r, GOOD))

    def test_contradictory(self):
        probs = fc.report_identity_problems(rep(env=GOOD, inp="sha256:" + OTHER), GOOD)
        self.assertTrue(has(probs, "disagree"), probs)

    def test_bare_prefixed_equivalence_is_not_a_mismatch(self):
        self.assertEqual(fc.report_identity_problems(rep(env=GOOD, inp=GOOD), GOOD), [])


def _tamper_cases():
    """(label, mutator(report, deck_sha), expected substring)."""
    def setid(env, inp):
        def f(r, sha):
            for k in ("netlist_sha256",):
                r["environment"].pop(k, None)
            r["provenance"].pop("input", None)
            if env is not None:
                r["environment"]["netlist_sha256"] = env
            if inp is not None:
                r["provenance"]["input"] = {"content_hash": inp, "role": "netlist"}
        return f
    return [
        ("mismatch", setid(OTHER, "sha256:" + OTHER), "different deck"),
        ("missing", setid(None, None), "no root-input identity"),
        ("malformed", setid("zz", "sha256:" + GOOD), "not a SHA-256"),
        ("contradictory", setid(GOOD, "sha256:" + OTHER), "disagree"),
    ]


class FleetIngest(unittest.TestCase):
    def test_each_bench(self):
        for bench in ("psrr-dc", "line-regulation", "startup"):
            with tempfile.TemporaryDirectory() as d:
                f = tfi.Fixture(bench, Path(d))
                res = f.assess()
                self.assertNotEqual(res["overall"], "INCOMPLETE", (bench, res["problems"]))
                self.assertFalse(has(res["problems"], "root-input"), res["problems"])
            for label, mut, want in _tamper_cases():
                with tempfile.TemporaryDirectory() as d:
                    f = tfi.Fixture(bench, Path(d))
                    r = f.plan["requests"][0]
                    mut(f.reports[r["name"]], r["deck_sha256"])
                    res = f.assess()
                    self.assertEqual(res["overall"], "INCOMPLETE", (bench, label))
                    self.assertTrue(has(res["problems"], want), (bench, label, res["problems"]))


class LoadIngest(unittest.TestCase):
    def test_valid_and_tampered(self):
        with tempfile.TemporaryDirectory() as d:
            res = tli.Fixture(Path(d)).assess()
            self.assertEqual(res["overall"], "COMPLETE", res["problems"])
        for label, mut, want in _tamper_cases():
            with tempfile.TemporaryDirectory() as d:
                f = tli.Fixture(Path(d))
                mut(f.reports["sweep"], f.plan["requests"][0]["deck_sha256"])
                res = f.assess()
                self.assertEqual(res["overall"], "INCOMPLETE", label)
                self.assertTrue(has(res["problems"], want), (label, res["problems"]))


class McIngest(unittest.TestCase):
    def test_valid_and_tampered(self):
        fx = tmc.Fixture()
        res = fx.assess()
        self.assertEqual(res["overall"], "PASS", res["problems"])
        for label, mut, want in _tamper_cases():
            fx = tmc.Fixture()
            e = fx.entry("mm_all", 27.0)
            mut(fx.reports[e["name"]], e["deck_sha256"])
            res = fx.assess()
            self.assertEqual(res["overall"], "INCOMPLETE", label)
            self.assertTrue(has(res["problems"], want), (label, res["problems"]))

    def test_report_from_another_requests_deck(self):
        fx = tmc.Fixture()
        a, b = fx.entry("mm_all", 27.0), fx.entry("mm_res", 27.0)
        fx.reports[a["name"]] = copy.deepcopy(fx.reports[b["name"]])
        res = fx.assess()
        self.assertEqual(res["overall"], "INCOMPLETE")
        self.assertTrue(has(res["problems"], "different deck"), res["problems"])


class TcIngest(unittest.TestCase):
    def test_valid_and_tampered(self):
        base = ttc.report()
        ok = copy.deepcopy(base)
        ok["environment"] = {"netlist_sha256": GOOD}
        ok["provenance"] = {"input": {"content_hash": "sha256:" + GOOD}}
        _, _, _, probs = ti.collect(ok, ttc.EXPECTED, deck_sha256=GOOD)
        self.assertEqual(probs, [])
        _, _, _, probs = ti.collect(ok, ttc.EXPECTED, deck_sha256=OTHER)
        self.assertTrue(has(probs, "different deck"))
        for label, mut, want in _tamper_cases():
            r = copy.deepcopy(ok)
            mut(r, GOOD)
            pts, miss, fail, probs = ti.collect(r, ttc.EXPECTED, deck_sha256=GOOD)
            self.assertTrue(has(probs, want), (label, probs))
            self.assertEqual(ti.assess(pts, miss, fail, probs, ttc.TB)["overall"], "INCOMPLETE", label)

    def test_no_report_identity_is_not_checked_without_a_deck(self):
        # library callers that pass no deck keep the old signature behaviour
        _, _, _, probs = ti.collect(ttc.report(), ttc.EXPECTED)
        self.assertEqual(probs, [])
        # ... the CLI always passes the frozen body.spice hash, so missing identity is rejected there
        _, _, _, probs = ti.collect(ttc.report(), ttc.EXPECTED, deck_sha256=GOOD)
        self.assertTrue(has(probs, "no root-input identity"))


if __name__ == "__main__":
    unittest.main()
