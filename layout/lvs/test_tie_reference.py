#!/usr/bin/env python3
"""Unit tests for ``tie_reference.py`` (gf180-bandgap#378)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tie_reference  # noqa: E402

OLD = """* c
.SUBCKT bandgap_top vdd vss vref vsubs
Mamp_M1_0 a b c vsubs nfet L=6U W=25U
Mpmos a b vdd nwl pfet L=1U W=2U
Qcore_Q1 vsubs nw_core_Q1 sns1 bjt AE=1
.ENDS bandgap_top
"""


class TieTest(unittest.TestCase):
    def test_aliases_applied(self):
        out = tie_reference.tie(OLD)
        self.assertIn(".SUBCKT bandgap_top vdd vss vref\n", out)
        self.assertIn("Mamp_M1_0 a b c vss nfet", out)
        self.assertIn("Mpmos a b vdd vdd pfet", out)
        self.assertIn("Qcore_Q1 vss vss sns1 bjt", out)
        for gone in ("vsubs", "nwl", "nw_"):
            self.assertNotIn(gone, out.split("\n", 3)[3])

    def test_rejects_already_tied(self):
        with self.assertRaises(ValueError):
            tie_reference.tie(tie_reference.tie(OLD))

    def test_committed_reference_ties(self):
        out = tie_reference.tie(tie_reference.SOURCE.read_text())
        body = "\n".join(l for l in out.splitlines() if not l.startswith("*"))
        for gone in ("vsubs", "nwl", "nw_"):
            self.assertNotIn(gone, body)


if __name__ == "__main__":
    unittest.main()
