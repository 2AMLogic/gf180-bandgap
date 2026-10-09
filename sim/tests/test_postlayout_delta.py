#!/usr/bin/env python3
"""Unit tests for the schematic-vs-extracted delta summary. No PDK, no ngspice.

    python3 -m unittest discover -s sim/tests -v

``postlayout_delta`` pairs two committed evidence records and reports where
layout cost margin, so a mis-parsed record or mis-aligned corner would
silently misreport a verdict. These cover record parsing, corner alignment
(through the ``Corners aligned`` coverage value ``render()`` emits), delta
sign/magnitude, PASS/FAIL taken from ``sim/suite/spec.py`` limits, and
byte-identical rendering once the git metadata is pinned. Records are
synthetic and live under a temporary repo root; ``sim/*/records/`` is never
read.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

import postlayout_delta as pld  # noqa: E402
from suite import spec as spec_mod  # noqa: E402

SLUG = "output-voltage-tc"


def record_md(provenance: str | None, rows: list[tuple[str, str, str, str]]) -> str:
    """A record stub with the per-corner table shape sim/harness/report.py emits."""
    lines = ["# stub", ""]
    if provenance is not None:
        lines.append(f"- **Netlist provenance**: {provenance} — DUT `x.spice`")
        lines.append("")
    lines.append("| corner-id | `vref` | `tc_ppm` | pass/fail |")
    lines.append("|---|---|---|---|")
    for corner, vref, tc, status in rows:
        lines.append(f"| `{corner}` | {vref} | {tc} | {status} |")
    return "\n".join(lines) + "\n"


def write_record(root: Path, record_id: str, text: str) -> None:
    path = root / "sim" / SLUG / "records" / f"{record_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_record(corners: dict[str, dict[str, float]], provenance: str) -> pld.Record:
    return pld.Record(SLUG, "rid", provenance, Path("rid.md"), corners, {})


def spec_line(row: str) -> spec_mod.SpecLine:
    return next(l for l in spec_mod.SUITE if l.slug == SLUG and l.row == row)


class LoadRecordTests(unittest.TestCase):
    def load(self, text: str) -> pld.Record:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_record(root, "r1", text)
            with mock.patch.object(pld, "REPO_ROOT", root):
                return pld.load_record(SLUG, "r1")

    def test_provenance_numbers_and_verdicts(self) -> None:
        rec = self.load(
            record_md(
                "extracted",
                [("tt_27", "1.2", "`12.5`", "PASS"), ("ss_125", "**1.19**", "30", "FAIL")],
            )
        )
        self.assertEqual(rec.provenance, "extracted")
        self.assertEqual(rec.slug, SLUG)
        self.assertEqual(rec.corners["tt_27"], {"vref": 1.2, "tc_ppm": 12.5})
        self.assertEqual(rec.corners["ss_125"], {"vref": 1.19, "tc_ppm": 30.0})
        self.assertEqual(rec.verdicts, {"tt_27": "PASS", "ss_125": "FAIL"})
        self.assertEqual(rec.link, f"`sim/{SLUG}/records/r1.md`")

    def test_missing_provenance_is_unknown(self) -> None:
        rec = self.load(record_md(None, [("tt_27", "1.2", "10", "PASS")]))
        self.assertEqual(rec.provenance, "unknown")

    def test_non_numeric_cell_is_omitted_not_zero(self) -> None:
        rec = self.load(record_md("schematic", [("tt_27", "n/a", "10", "PASS")]))
        self.assertEqual(rec.corners["tt_27"], {"tc_ppm": 10.0})

    def test_wrong_cell_count_row_is_skipped(self) -> None:
        text = record_md("schematic", [("tt_27", "1.2", "10", "PASS")])
        text += "| `bad` | 1.2 | PASS |\n"
        rec = self.load(text)
        self.assertEqual(list(rec.corners), ["tt_27"])

    def test_no_table_exits(self) -> None:
        with self.assertRaises(SystemExit):
            self.load("# stub\n\nno table here\n")


class DeltaTests(unittest.TestCase):
    def test_sign_and_magnitude(self) -> None:
        self.assertEqual(pld._delta(1.1, 1.0), "+0.1 (+10.00%)")
        self.assertEqual(pld._delta(0.9, 1.0), "-0.1 (-10.00%)")
        self.assertEqual(pld._delta(5.0, 5.0), "+0 (+0.00%)")

    def test_percent_uses_absolute_baseline(self) -> None:
        self.assertEqual(pld._delta(-1.5, -1.0), "-0.5 (-50.00%)")

    def test_zero_baseline_has_no_percent(self) -> None:
        self.assertEqual(pld._delta(2.5, 0.0), "+2.5")


class VerdictTests(unittest.TestCase):
    def test_pass_then_fail_transition(self) -> None:
        line = spec_line("Output reference")
        good = make_record({"a": {"vref": 1.2}, "b": {"vref": 1.19}}, "schematic")
        bad = make_record({"a": {"vref": 1.2}, "b": {"vref": 1.17}}, "extracted")
        self.assertEqual(pld.verdict(good, line), "PASS")
        self.assertEqual(pld.verdict(bad, line), "FAIL")

    def test_max_limit_failure(self) -> None:
        line = spec_line("Temp coefficient (-40..125 degC)")
        self.assertEqual(pld.verdict(make_record({"a": {"tc_ppm": 50.0}}, "s"), line), "PASS")
        self.assertEqual(pld.verdict(make_record({"a": {"tc_ppm": 50.1}}, "s"), line), "FAIL")

    def test_worst_picks_furthest_into_violation(self) -> None:
        rec = make_record({"a": {"vref": 1.2}, "b": {"vref": 1.19}}, "s")
        lo, hi = spec_line("Output reference").limits
        self.assertEqual(pld.worst(rec, lo), ("b", 1.19))
        self.assertEqual(pld.worst(rec, hi), ("a", 1.2))
        self.assertIsNone(pld.worst(make_record({"a": {}}, "s"), lo))


class RenderTests(unittest.TestCase):
    def pair(self) -> dict[str, tuple[pld.Record, pld.Record]]:
        schematic = make_record(
            {
                "tt_27": {"vref": 1.200, "tc_ppm": 10.0},
                "ss_125": {"vref": 1.190, "tc_ppm": 20.0},
                "only_sch": {"vref": 1.210, "tc_ppm": 5.0},
            },
            "schematic",
        )
        extracted = make_record(
            {
                "tt_27": {"vref": 1.176, "tc_ppm": 12.0},
                "ss_125": {"vref": 1.170, "tc_ppm": 25.0},
            },
            "extracted",
        )
        return {SLUG: (schematic, extracted)}

    def render(self, extra: str = "") -> str:
        with mock.patch.object(
            pld.harness_report, "_git", side_effect=lambda *a, **k: "fixed-" + a[-1]
        ):
            return pld.render(self.pair(), extra)

    def test_coverage_count_and_only_common_corners_get_rows(self) -> None:
        text = self.render()
        self.assertIn("| 2 of 3 / 2 |", text)
        per_corner = text.split("## Per-corner delta, gated measurements")[1]
        self.assertIn("| `tt_27` |", per_corner)
        self.assertIn("| `ss_125` |", per_corner)
        self.assertNotIn("only_sch", per_corner)

    def test_per_corner_delta_values(self) -> None:
        text = self.render()
        self.assertIn("| `tt_27` | 1.2 | 1.176 | -0.024 (-2.00%) |", text)
        self.assertIn("| 10 | 12 | +2 (+20.00%) |", text)

    def test_spec_row_verdict_transition_is_bolded(self) -> None:
        text = self.render()
        row = next(
            l for l in text.splitlines()
            if l.startswith("| Output reference |") and "vref >= 1.176 V" in l
        )
        self.assertTrue(row.endswith("| PASS | **FAIL** |"), row)
        self.assertIn("-0.02 (-1.68%)", row)
        tc_row = next(l for l in text.splitlines() if "tc_ppm <= 50 ppm/degC" in l)
        self.assertTrue(tc_row.endswith("| PASS | PASS |"), tc_row)

    def test_byte_identical_with_fixed_git_metadata(self) -> None:
        first, second = self.render(), self.render()
        self.assertEqual(first.encode(), second.encode())
        self.assertIn("`fixed-HEAD` on `fixed-HEAD`", first)

    def test_extra_fragment_appended(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            frag = Path(tmp) / "frag.md"
            frag.write_text("## Narrative\n\nhello\n\n")
            text = self.render(str(frag))
        self.assertTrue(text.endswith("## Narrative\n\nhello\n\n"))


if __name__ == "__main__":
    unittest.main()
