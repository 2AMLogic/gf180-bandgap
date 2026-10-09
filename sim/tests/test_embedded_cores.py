#!/usr/bin/env python3
"""Checks for the embedded-core sync check (#227). No PDK or ngspice needed.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM / "tools"))

import check_embedded_cores as chk  # noqa: E402

REPO = SIM.parent
CANON = chk.parse_core(chk.CANONICAL.read_text())


def bench(rel: str) -> str:
    return (REPO / rel).read_text()


class EmbeddedCores(unittest.TestCase):
    def test_all_six_in_sync(self):
        for rel, real in chk.BENCHES.items():
            with self.subTest(rel):
                self.assertEqual(chk.check_core(bench(rel), CANON, real), [])

    def test_canonical_values(self):
        d = CANON["devices"]
        self.assertEqual((d["XR2"]["length"], d["XR2"]["width"], d["XR2"]["model"]),
                         ("39.195501", "2", "ppolyf_u"))
        self.assertEqual((d["XQ2"]["model"], d["XQ2"]["m"]), ("pnp_05p00x05p00", 4))
        self.assertEqual(d["XR1"]["length"], "446.000000")
        self.assertEqual(len(CANON["trim_units"]), 63)

    def _stale(self, rel, old, new):
        text = bench(rel)
        self.assertIn(old, text)
        return chk.check_core(text.replace(old, new), CANON, chk.BENCHES[rel])

    def test_startup_benches_covered_and_topology(self):
        for rel, want in chk.STARTUP_INSTANCE.items():
            with self.subTest(rel):
                self.assertIn(rel, chk.BENCHES)
                self.assertEqual(chk.has_startup_instance(bench(rel)), want)

    def test_stale_startup_core_detected(self):
        for rel in chk.STARTUP_INSTANCE:
            with self.subTest(rel):
                errs = self._stale(rel, "pnp_05p00x05p00 m=4", "pnp_10p00x10p00 m=1")
                self.assertTrue(any("XQ2.model" in e for e in errs))
                errs = self._stale(rel, "r_length=39.195501u", "r_length=36.341871u")
                self.assertTrue(any("XR2.length" in e for e in errs))
                errs = self._stale(rel, "r_length=545.639857u", "r_length=446.000000u")
                self.assertTrue(any("lumped" in e for e in errs))

    def test_stale_q2_detected(self):
        rel = "sim/amp-psrr/testbench/tb_psrr.spice"
        errs = self._stale(rel, "pnp_05p00x05p00 m=4", "pnp_10p00x10p00 m=1")
        self.assertTrue(any("XQ2.model" in e for e in errs))
        self.assertTrue(any("XQ2.m" in e for e in errs))

    def test_stale_r2_detected(self):
        rel = "sim/core-mirror-sensitivity/testbench/tb_core_mirror_sensitivity.spice"
        errs = self._stale(rel, "r_length=39.195501u", "r_length=36.341871u")
        self.assertTrue(any("XR2.length" in e for e in errs))

    def test_lumped_r1_not_canonical_base(self):
        # pasting the base 446u into a lumped bench must be flagged
        rel = "sim/bandgap-loop-smoke/testbench/bandgap_loop_smoke.spice"
        errs = self._stale(rel, "r_length=545.639857u", "r_length=446.000000u")
        self.assertTrue(any("lumped" in e for e in errs))

    def test_explicit_stale_base_r1_and_trim_detected(self):
        rel = "sim/core-mirror-sensitivity/testbench/tb_core_mirror_sensitivity.spice"
        errs = self._stale(rel, "r_length=446.000000u", "r_length=460.701871u")
        self.assertTrue(any("base" in e for e in errs))
        text = bench(rel).replace("XRU5 u2_1 u2_2 sub ppolyf_u r_width=2u r_length=2.771871u",
                                  "XRU5 u2_1 u2_2 sub ppolyf_u r_width=2u r_length=5.543742u")
        errs = chk.check_core(text, CANON, "explicit")
        self.assertTrue(any("trim ladder" in e for e in errs))

    def test_realization_flip_detected(self):
        rel = "sim/amp-psrr/testbench/tb_psrr.spice"
        errs = chk.check_core(bench(rel), CANON, "explicit")
        self.assertTrue(any("realization" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
