#!/usr/bin/env python3
"""Unit tests for the shared DC-table parser/interpolator and `_fmt`.

    python3 -m unittest discover -s sim/tests -v

No PDK, no ngspice.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.dctable import column, interp_at, parse_dc_table  # noqa: E402
from harness.fmt import _fmt  # noqa: E402

LOG = """\
Circuit: x
Some banner
Index   v-sweep         v(a)            v(b)
--------------------------------------------------
0       -1.0e+00        1.0e+00         2.0e+00
1       0.0e+00         3.0e+00         4.0e+00
short   1.0
2       1.0e+00         5.0e+00
3       nan_x           1.0             2.0
4       1.0e+00         5.0e+00         6.0e+00
"""


class ParseTests(unittest.TestCase):
    def test_header_and_rows(self):
        cols, rows = parse_dc_table(LOG)
        self.assertEqual(cols, ["v-sweep", "v(a)", "v(b)"])
        # non-digit index, short row and non-numeric row are skipped
        self.assertEqual(rows, [[-1.0, 1.0, 2.0], [0.0, 3.0, 4.0], [1.0, 5.0, 6.0]])

    def test_no_header(self):
        with self.assertRaisesRegex(ValueError, "no DC table header"):
            parse_dc_table("nothing here\n0 1 2\n")

    def test_no_data_rows(self):
        with self.assertRaisesRegex(ValueError, "no data rows"):
            parse_dc_table("Index a b\n---\nfoo bar\n")

    def test_column(self):
        cols, rows = parse_dc_table(LOG)
        self.assertEqual(column(cols, rows, "v(b)"), [2.0, 4.0, 6.0])
        with self.assertRaises(ValueError):
            column(cols, rows, "missing")


class NonFiniteParseTests(unittest.TestCase):
    def test_non_finite_tokens_raise(self):
        for tok in ("nan", "inf", "-inf", "1e999"):
            log = f"Index v-sweep v(a)\n0 0 1\n1 1 {tok}\n"
            with self.assertRaisesRegex(ValueError, r"non-finite.*row 1.*v\(a\)"):
                parse_dc_table(log)

    def test_malformed_rows_still_skipped(self):
        cols, rows = parse_dc_table("Index a b\n0 1 2\n1 nan_x 3\n2 1\n")
        self.assertEqual(rows, [[1.0, 2.0]])


class InterpTests(unittest.TestCase):
    xs = [0.0, 1.0, 2.0]
    ys = [0.0, 10.0, 30.0]

    def test_midpoint(self):
        self.assertAlmostEqual(interp_at(self.xs, self.ys, 0.5), 5.0)
        self.assertAlmostEqual(interp_at(self.xs, self.ys, 1.5), 20.0)

    def test_exact_node_and_ends(self):
        self.assertEqual(interp_at(self.xs, self.ys, 1.0), 10.0)
        self.assertEqual(interp_at(self.xs, self.ys, 0.0), 0.0)
        self.assertEqual(interp_at(self.xs, self.ys, 2.0), 30.0)

    def test_duplicate_x(self):
        xs = [0.0, 1.0, 1.0, 2.0]
        ys = [0.0, 4.0, 8.0, 12.0]
        self.assertEqual(interp_at(xs, ys, 1.0), 4.0)

    def test_out_of_range_raises_by_default(self):
        with self.assertRaises(ValueError):
            interp_at(self.xs, self.ys, -0.1)
        with self.assertRaises(ValueError):
            interp_at(self.xs, self.ys, 2.1)

    def test_out_of_range_clamp(self):
        self.assertEqual(interp_at(self.xs, self.ys, -5.0, clamp=True), 0.0)
        self.assertEqual(interp_at(self.xs, self.ys, 9.0, clamp=True), 30.0)
        self.assertAlmostEqual(interp_at(self.xs, self.ys, 0.5, clamp=True), 5.0)


class NonFiniteInterpTests(unittest.TestCase):
    xs = [0.0, 1.0, 2.0]
    ys = [0.0, 10.0, 30.0]

    def test_non_finite_query(self):
        for clamp in (False, True):
            for q in (float("nan"), float("inf"), float("-inf")):
                with self.assertRaisesRegex(ValueError, "non-finite"):
                    interp_at(self.xs, self.ys, q, clamp=clamp)

    def test_non_finite_series(self):
        nan = float("nan")
        for clamp in (False, True):
            for xs, ys in (
                ([0.0, nan, 2.0], self.ys),
                ([0.0, 1.0, float("inf")], self.ys),
                (self.xs, [0.0, 10.0, nan]),
                (self.xs, [float("-inf"), 10.0, 30.0]),
            ):
                for q in (0.0, 1.0, 2.0, 5.0):
                    with self.assertRaisesRegex(ValueError, "non-finite"):
                        interp_at(xs, ys, q, clamp=clamp)

    def test_overflow_result_raises(self):
        big = 1.5e308
        with self.assertRaisesRegex(ValueError, "non-finite"):
            interp_at([0.0, 1.0], [-big, big], 0.75)


class FmtTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual(_fmt(None), "n/a")

    def test_zero(self):
        self.assertEqual(_fmt(0.0), "0")

    def test_mid_range_float(self):
        self.assertEqual(_fmt(1.5), "1.5")
        self.assertEqual(_fmt(0.001), "0.001")

    def test_small_large_scientific(self):
        self.assertEqual(_fmt(1e-4), "1.000000e-04")
        self.assertEqual(_fmt(-2.5e5), "-2.500000e+05")

    def test_precision_override(self):
        self.assertEqual(_fmt(1e-4, precision="4e"), "1.0000e-04")
        # precision does not affect mid-range values
        self.assertEqual(_fmt(1.5, precision="4e"), "1.5")

    def test_non_float(self):
        self.assertEqual(_fmt(7), "7")
        self.assertEqual(_fmt("x"), "x")
        self.assertEqual(_fmt(10**9), "1000000000")


if __name__ == "__main__":
    unittest.main()
