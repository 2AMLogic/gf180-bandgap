#!/usr/bin/env python3
"""Unit tests for the README-vs-spec.py limit check. No PDK required.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SIM_DIR))

import check_spec_limits as csl  # noqa: E402
from sim.suite import spec  # noqa: E402

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _mutate_limit(key: str, measurement: str, value: float):
    out = []
    for line in spec.SUITE:
        if line.key == key:
            line = dataclasses.replace(line, limits=tuple(
                dataclasses.replace(lim, value=value)
                if lim.measurement == measurement else lim
                for lim in line.limits))
        out.append(line)
    return tuple(out)


class SpecLimitsTest(unittest.TestCase):
    def test_repo_is_in_agreement(self):
        self.assertEqual(csl.check(README, spec.SUITE), [])

    def test_mutated_readme_fails(self):
        for old, new, row in (
            ("< 50 ppm/", "< 60 ppm/", "Temp coefficient"),
            ("> 60 dB DC", "> 50 dB DC", "PSRR"),
            ("< 1 mV/V", "< 2 mV/V", "Line regulation"),
            ("< 50 µA", "< 80 µA", "Quiescent current"),
            ("±2% untrimmed", "±3% untrimmed", "Output reference"),
        ):
            with self.subTest(row=row):
                self.assertIn(old, README)
                problems = csl.check(README.replace(old, new, 1), spec.SUITE)
                self.assertTrue(any(row in p for p in problems), problems)

    def test_mutated_limit_fails_with_both_values(self):
        for key, meas, value, readme_val in (
            ("temp-coefficient", "tc_ppm", 80.0, "50"),
            ("psrr", "psrr_1khz_db", 40.0, "60"),
            ("line-regulation", "linereg_mv_per_v", 5.0, "1"),
            ("quiescent-current", "iq_ua", 100.0, "50"),
            ("output-reference", "vref", 1.1, "1.176"),
        ):
            with self.subTest(key=key):
                problems = csl.check(README, _mutate_limit(key, meas, value))
                self.assertTrue(problems)
                msg = "\n".join(problems)
                self.assertIn("README", msg)
                self.assertIn("spec.py", msg)
                self.assertIn(readme_val, msg)
                self.assertIn(f"{value:g}", msg)

    def test_tbd_rows_are_skipped(self):
        problems = csl.check(README, spec.SUITE)
        self.assertFalse(any("noise" in p or "Load" in p for p in problems))

    def test_missing_row_and_unparseable_cell_fail(self):
        no_psrr = "\n".join(l for l in README.splitlines() if not l.startswith("| PSRR"))
        self.assertTrue(any("PSRR" in p for p in csl.check(no_psrr, spec.SUITE)))
        tbd = README.replace("< 1 mV/V", "TBD", 1)
        self.assertTrue(any("Line regulation" in p for p in csl.check(tbd, spec.SUITE)))

    def test_extra_gated_limit_fails(self):
        extra = []
        for line in spec.SUITE:
            if line.key == "quiescent-current":
                line = dataclasses.replace(line, limits=line.limits + (
                    spec.Limit("iq_extra", "max", 50.0),))
            extra.append(line)
        self.assertTrue(csl.check(README, tuple(extra)))


if __name__ == "__main__":
    unittest.main()
