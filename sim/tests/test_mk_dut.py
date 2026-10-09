#!/usr/bin/env python3
"""Checks for ``sim/tools/mk_dut.py`` convert/validate (#231). No PDK or ngspice needed.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM / "tools"))

import mk_dut  # noqa: E402

REPO = SIM.parent
EXPORT = REPO / "design" / "netlist" / "bandgap_top.spice"

GOOD = ".subckt cell a b\nR1 a b 1k\n.ends\n"


class Convert(unittest.TestCase):
    def test_wrapper_uncommented(self):
        frag, notes = mk_dut.convert("**.subckt top a b\nR1 a b 1k\n**.ends\n")
        self.assertEqual(frag, ".subckt top a b\nR1 a b 1k\n.ends\n")
        self.assertEqual(len(notes), 2)
        self.assertTrue(all("uncommented" in n for n in notes))

    def test_wrapper_case_insensitive(self):
        frag, _ = mk_dut.convert("**.SUBCKT top a\n**.ENDS\n")
        self.assertEqual(frag, ".SUBCKT top a\n.ENDS\n")

    def test_directives_dropped_with_notes(self):
        text = GOOD + ".temp 27\n.lib x.lib tt\n.END\n"
        frag, notes = mk_dut.convert(text)
        self.assertEqual(frag, GOOD)
        self.assertEqual(len(notes), 3)
        for word in (".temp", ".lib", ".END"):
            self.assertTrue(any(n.startswith("dropped deck-level") and word in n
                                for n in notes), word)

    def test_control_block_dropped_whole(self):
        text = GOOD + ".control\nrun\nprint v(a)\n.temp 5\n.endc\n.end\n"
        frag, notes = mk_dut.convert(text)
        self.assertEqual(frag, GOOD)
        self.assertEqual(sum("dropped a .control block" in n for n in notes), 1)
        # the .temp inside the block is swallowed by the block, not noted separately
        self.assertFalse(any(".temp" in n for n in notes))

    def test_control_case_insensitive(self):
        frag, notes = mk_dut.convert(GOOD + ".CONTROL\nquit\n.ENDC\n")
        self.assertEqual(frag, GOOD)
        self.assertEqual(len(notes), 1)

    def test_clean_input_no_notes(self):
        frag, notes = mk_dut.convert(GOOD)
        self.assertEqual((frag, notes), (GOOD, []))


class Validate(unittest.TestCase):
    def test_well_formed(self):
        self.assertEqual(mk_dut.validate(GOOD), [])

    def test_nested_subckt_ok(self):
        text = ".subckt o a\n.subckt i b\nR1 b 0 1\n.ends\nXi a i\n.ends\n"
        self.assertEqual(mk_dut.validate(text), [])

    def test_unclosed_subckt(self):
        problems = mk_dut.validate(".subckt cell a b\nR1 a b 1k\n")
        self.assertEqual(problems, ["1 unclosed .subckt block(s)"])

    def test_stray_ends(self):
        problems = mk_dut.validate(GOOD + ".ends\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("line 4: .ends with no matching .subckt", problems[0])

    def test_top_level_device(self):
        problems = mk_dut.validate("R9 a b 1k\n" + GOOD)
        self.assertEqual(len(problems), 1)
        self.assertIn("device instances outside any .subckt", problems[0])
        self.assertIn("line 1: R9 a b 1k", problems[0])

    def test_no_subckts(self):
        problems = mk_dut.validate("* only a comment\n.model x d\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("no .subckt definitions", problems[0])

    def test_comments_blanks_continuations_ignored(self):
        text = "* c\n\n" + ".subckt c a\nR1 a 0\n+ 1k\n.ends\n"
        self.assertEqual(mk_dut.validate(text), [])


class RoundTrip(unittest.TestCase):
    def test_committed_export_converts_valid(self):
        frag, notes = mk_dut.convert(EXPORT.read_text())
        self.assertEqual(mk_dut.validate(frag), [])
        self.assertIn("bandgap_top", mk_dut.subckt_names(frag))
        self.assertNotIn("\n.end\n", "\n" + frag)
        self.assertTrue(any("uncommented" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
