#!/usr/bin/env python3
"""Unit checks for the pure helpers in sim/mc-untrimmed/run_mc_untrimmed.py.

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
REPO = SIM.parent
sys.path.insert(0, str(SIM))

_spec = importlib.util.spec_from_file_location(
    "run_mc_untrimmed", SIM / "mc-untrimmed" / "run_mc_untrimmed.py"
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

NETLIST = (REPO / "design" / "netlist" / "bandgap_top.spice").read_text()
# `ppolyf_u_1k` etc. are different models and must not be matched.
PPOLYF_LINE = re.compile(r"^X\S+(?:\s+\S+){3}\s+ppolyf_u\b", re.MULTILINE)


def fake_log(n, isup=1e-5):
    blocks = []
    for i in range(n):
        blocks.append(f"vref_val = {1.2 + 0.001 * i:.6e}\nisup_val = {isup:.6e}\n")
    return "\n".join(blocks)


class ResistorMismatchSigma(unittest.TestCase):
    def test_known_value(self):
        w, l = 2.0, 10.0
        r_w = 2e-6 - 2 * 2.55e-8
        r_l = 10e-6 - 2 * 2e-11
        expected = 0.7071 * 0.021e-6 / math.sqrt(r_w * r_l)
        self.assertAlmostEqual(
            run.resistor_mismatch_sigma(w, l) / expected, 1.0, places=12
        )

    def test_decreases_with_area(self):
        small = run.resistor_mismatch_sigma(2.0, 10.0)
        self.assertLess(run.resistor_mismatch_sigma(2.0, 40.0), small)
        self.assertLess(run.resistor_mismatch_sigma(8.0, 10.0), small)

    def test_non_physical_geometry(self):
        with self.assertRaises(ValueError):
            run.resistor_mismatch_sigma(0.0, 10.0)
        with self.assertRaises(ValueError):
            run.resistor_mismatch_sigma(2.0, 0.0)
        with self.assertRaises(ValueError):
            run.resistor_mismatch_sigma(-1.0, 10.0)


class StripTrailingEnd(unittest.TestCase):
    def test_removes_end_case_insensitive(self):
        for end in (".end", ".END", "  .End  "):
            out = run.strip_trailing_end(f"R1 a b 1k\n{end}\n")
            self.assertEqual(out, "R1 a b 1k\n")

    def test_keeps_ends(self):
        text = ".subckt foo a b\nR1 a b 1k\n.ends foo\n.ends\n.end\n"
        out = run.strip_trailing_end(text)
        self.assertIn(".ends foo", out)
        self.assertIn(".ends\n", out)
        self.assertNotIn("\n.end\n", "\n" + out)

    def test_ends_with_newline(self):
        self.assertTrue(run.strip_trailing_end("R1 a b 1k").endswith("\n"))
        self.assertTrue(run.strip_trailing_end("R1 a b 1k\n.end").endswith("\n"))

    def test_real_netlist(self):
        out = run.strip_trailing_end(NETLIST)
        self.assertNotIn(
            ".end", [ln.strip().lower() for ln in out.splitlines()]
        )


class InjectResistorMismatch(unittest.TestCase):
    def test_real_netlist(self):
        expected = len(PPOLYF_LINE.findall(NETLIST))
        self.assertGreater(expected, 0)
        new, injected = run.inject_resistor_mismatch(NETLIST)
        self.assertEqual(len(injected), expected)
        for info in injected:
            self.assertGreater(info["sigma"], 0)
            self.assertIn(f"{info['instance']} ", new)
        # Every rewritten line carries an agauss draw; others are untouched.
        old_lines, new_lines = NETLIST.splitlines(), new.splitlines()
        self.assertEqual(len(old_lines), len(new_lines))
        changed = 0
        for old, cur in zip(old_lines, new_lines):
            if PPOLYF_LINE.match(old):
                changed += 1
                self.assertIn("agauss(0,", cur)
                self.assertNotEqual(old, cur)
            else:
                self.assertEqual(old, cur)
        self.assertEqual(changed, expected)

    def test_single_line_values(self):
        text = "XR1 a b vss ppolyf_u r_width=2u r_length=10u m=1\n"
        new, injected = run.inject_resistor_mismatch(text)
        sigma = run.resistor_mismatch_sigma(2.0, 10.0)
        self.assertEqual(injected[0]["instance"], "XR1")
        self.assertEqual(injected[0]["width_um"], 2.0)
        self.assertEqual(injected[0]["length_um"], 10.0)
        self.assertAlmostEqual(injected[0]["sigma"], sigma)
        self.assertIn("r_width=2u", new)
        self.assertIn("r_length={10u*(1+agauss(0,", new)
        self.assertTrue(new.rstrip().endswith("m=1"))

    def test_no_ppolyf_u_raises(self):
        with self.assertRaises(RuntimeError):
            run.inject_resistor_mismatch("R1 a b 1k\nXR a b c d ppolyf_u_1k r_width=2u r_length=4u\n")

    def test_missing_geometry_raises(self):
        with self.assertRaises(RuntimeError):
            run.inject_resistor_mismatch("XR1 a b vss ppolyf_u r_width=2u m=1\n")
        with self.assertRaises(RuntimeError):
            run.inject_resistor_mismatch("XR1 a b vss ppolyf_u r_length=2u m=1\n")


class Extract(unittest.TestCase):
    def test_parses_n_samples(self):
        res = run.extract(fake_log(run.N_SAMPLES))
        self.assertEqual(res["n"], run.N_SAMPLES)
        self.assertAlmostEqual(res["min"], 1.2)
        self.assertAlmostEqual(res["max"], 1.2 + 0.001 * (run.N_SAMPLES - 1))
        self.assertAlmostEqual(
            res["mean"], 1.2 + 0.001 * (run.N_SAMPLES - 1) / 2, places=9
        )
        self.assertGreater(res["sigma"], 0)
        self.assertEqual(res["degenerate_count"], 0)

    def test_short_or_long_log_raises(self):
        with self.assertRaises(RuntimeError):
            run.extract(fake_log(run.N_SAMPLES - 1))
        with self.assertRaises(RuntimeError):
            run.extract(fake_log(run.N_SAMPLES + 1))
        with self.assertRaises(RuntimeError):
            run.extract("")

    def test_degenerate_isup_flagged(self):
        res = run.extract(fake_log(run.N_SAMPLES, isup=0.0))
        self.assertEqual(res["degenerate_count"], run.N_SAMPLES)
        self.assertEqual(res["degenerate_indices"], list(range(run.N_SAMPLES)))


class ProvenanceClass(unittest.TestCase):
    def test_classes(self):
        P = Path
        self.assertEqual(run.provenance_class(P("layout/netlist/x.spice")), "extracted")
        self.assertEqual(
            run.provenance_class(P("sim/dut/frozen/x.spice")), "frozen schematic"
        )
        self.assertEqual(
            run.provenance_class(P("design/netlist/bandgap_top.spice")), "schematic"
        )


if __name__ == "__main__":
    unittest.main()
