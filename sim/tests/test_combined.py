#!/usr/bin/env python3
"""Unit tests for the combined untrimmed-accuracy verdict. No PDK, no ngspice.

    python3 -m unittest discover -s sim/tests -v

The combined verdict is the only place in the suite where two benches' results
are multiplied together into one claim, so these cover the things that
combination can get wrong independently of whether either simulation
converged: reading the Monte Carlo logs back, grafting the distribution onto
the right corner, refusing to graft when the two benches disagree, and
attributing a failure to the leg that actually caused it.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from suite import combined  # noqa: E402


def mc_log(values: list[float], supply_a: float = 2.0e-5) -> str:
    """One Monte Carlo log's worth of ``op``/``print`` blocks."""
    blocks = []
    for value in values:
        blocks.append(f"vref_val = {value:.6e}\nisup_val = {supply_a:.6e}")
    return "* header line = not a sample\n" + "\n".join(blocks) + "\n"


def record_body(provenance: str | None) -> str:
    """A record stub, optionally carrying sim/README.md's provenance field."""
    if provenance is None:
        return "# stub\n"
    return (
        "# stub\n\n"
        f"- **Netlist provenance**: {provenance} — DUT `sim/dut/bandgap_top.spice`\n"
    )


def write_mc_record(
    root: Path,
    record_id: str,
    groups: dict[str, dict[float, list[float]]],
    provenance: str | None = None,
):
    """Materialise a mismatch record's raw logs under ``root``."""
    corners = root / combined.MC_SLUG / "corners" / record_id
    corners.mkdir(parents=True, exist_ok=True)
    (root / combined.MC_SLUG / "records").mkdir(parents=True, exist_ok=True)
    (root / combined.MC_SLUG / "records" / f"{record_id}.md").write_text(
        record_body(provenance)
    )
    for group, by_temp in groups.items():
        for temp, values in by_temp.items():
            (corners / f"{group}_{temp:g}c_3.30v.log").write_text(mc_log(values))
    return corners


def write_corner_record(
    root: Path,
    record_id: str,
    samples: dict[str, float],
    provenance: str | None = None,
):
    """Materialise a corner record's raw logs under ``root``."""
    corners = root / combined.CORNER_SLUG / "corners" / record_id
    corners.mkdir(parents=True, exist_ok=True)
    (root / combined.CORNER_SLUG / "records").mkdir(parents=True, exist_ok=True)
    (root / combined.CORNER_SLUG / "records" / f"{record_id}.md").write_text(
        record_body(provenance)
    )
    for corner_id, vref in samples.items():
        (corners / f"{corner_id}.log").write_text(f"m_vref = {vref:.10e}\n")
    return corners


#: A symmetric five-sample set: mean exactly ``centre``, sample sigma (N-1)
#: exactly ``spread``.
def spread_about(centre: float, spread: float) -> list[float]:
    return [centre - spread, centre - spread, centre, centre + spread, centre + spread]


class LogReadingTests(unittest.TestCase):
    def test_repeated_names_start_a_new_sample(self):
        samples = combined.parse_mc_samples(mc_log([1.2, 1.21, 1.22]))
        self.assertEqual(len(samples), 3)
        self.assertAlmostEqual(samples[1]["vref_val"], 1.21)
        self.assertIn("isup_val", samples[0])

    def test_group_and_temperature_come_from_the_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            corners = write_mc_record(
                Path(tmp),
                "20260802-000000-abcdef0",
                {"mm_all": {27.0: spread_about(1.214, 0.005)}},
            )
            stats = combined.read_mc_groups(corners)
        self.assertIn(("mm_all", 27.0), stats)
        group = stats[("mm_all", 27.0)]
        self.assertEqual(group.n, 5)
        self.assertAlmostEqual(group.mean_v, 1.214, places=9)
        self.assertAlmostEqual(group.sigma_v, 0.005, places=9)

    def test_sigma_uses_the_n_minus_1_convention_the_record_states(self):
        stats = combined._stdev([1.0, 2.0, 3.0])  # population sigma would be 0.8165
        self.assertAlmostEqual(stats, 1.0, places=9)


class GraftTests(unittest.TestCase):
    """The combination rule itself."""

    def setUp(self):
        self.mc = {
            ("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2140, 0.0050),
            ("mm_ctrl", 27.0): combined.GroupStats("mm_ctrl", 27.0, 300, 1.2142, 0.0),
        }

    def test_at_the_shared_corner_the_interval_is_the_mc_records_own_window(self):
        """tt/3.30 V must reproduce mean +/- 3 sigma exactly, or the graft lies."""
        verdict = combined.evaluate({"tt_27c_3.30v": {"vref": 1.2142}}, self.mc)
        corner = verdict.verdicts[0]
        self.assertAlmostEqual(corner.centre_v, 1.2140, places=9)
        self.assertAlmostEqual(corner.low_v, 1.2140 - 3 * 0.0050, places=9)
        self.assertAlmostEqual(corner.high_v, 1.2140 + 3 * 0.0050, places=9)

    def test_the_offset_is_applied_to_every_other_corner(self):
        samples = {"tt_27c_3.30v": {"vref": 1.2142}, "ss_27c_2.97v": {"vref": 1.2200}}
        verdict = combined.evaluate(samples, self.mc)
        other = next(v for v in verdict.verdicts if v.corner_id == "ss_27c_2.97v")
        self.assertAlmostEqual(other.centre_v, 1.2200 - 0.0002, places=9)

    def test_a_corner_inside_the_window_can_still_fail_on_its_mismatch_skirt(self):
        """The whole point of combining: the corner leg alone under-reports."""
        samples = {"tt_27c_3.30v": {"vref": 1.2142}, "ss_27c_2.97v": {"vref": 1.2200}}
        verdict = combined.evaluate(samples, self.mc)
        binding = next(v for v in verdict.verdicts if v.corner_id == "ss_27c_2.97v")
        self.assertEqual(binding.corner_only_status, "PASS")
        self.assertEqual(binding.status, "FAIL")
        self.assertEqual(binding.binding_edge, "upper")
        self.assertLess(binding.margin_v, 0)

    def test_a_centred_narrow_distribution_passes_at_every_corner(self):
        mc = {
            ("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2000, 0.0010),
            ("mm_ctrl", 27.0): combined.GroupStats("mm_ctrl", 27.0, 300, 1.2000, 0.0),
        }
        samples = {
            "tt_27c_3.30v": {"vref": 1.2000},
            "ss_27c_2.97v": {"vref": 1.2050},
            "ff_27c_3.63v": {"vref": 1.1950},
        }
        verdict = combined.evaluate(samples, mc)
        self.assertEqual(verdict.status, "PASS")
        self.assertEqual(verdict.n_fail, 0)


class AnchorTests(unittest.TestCase):
    def test_disagreeing_benches_are_invalid_not_a_verdict(self):
        """A control group that does not match the corner leg breaks the graft."""
        mc = {
            ("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2000, 0.0010),
            # 5 mV away from the corner leg's tt point: two different circuits.
            ("mm_ctrl", 27.0): combined.GroupStats("mm_ctrl", 27.0, 300, 1.2050, 0.0),
        }
        verdict = combined.evaluate({"tt_27c_3.30v": {"vref": 1.2000}}, mc)
        self.assertEqual(verdict.status, "INVALID")
        self.assertFalse(verdict.anchors_agree)

    def test_a_missing_control_group_is_reported_not_fatal(self):
        mc = {("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2000, 0.0010)}
        verdict = combined.evaluate({"tt_27c_3.30v": {"vref": 1.2000}}, mc)
        self.assertEqual(verdict.status, "PASS")
        self.assertEqual(verdict.anchors_evaluated, 0)
        self.assertEqual(verdict.anchors[0].status, "not evaluable")
        self.assertIn("not evaluable", combined.render(verdict))

    def test_an_agreeing_control_group_splits_the_offset(self):
        mc = {
            ("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2140, 0.0050),
            ("mm_ctrl", 27.0): combined.GroupStats("mm_ctrl", 27.0, 300, 1.2142, 0.0),
        }
        verdict = combined.evaluate({"tt_27c_3.30v": {"vref": 1.2142}}, mc)
        leg = verdict.legs[27.0]
        self.assertAlmostEqual(leg.mismatch_shift_v, -0.0002, places=9)
        self.assertTrue(verdict.anchors_agree)


class CoverageTests(unittest.TestCase):
    def test_a_temperature_the_corner_leg_never_ran_is_a_note_not_a_silent_drop(self):
        mc = {("mm_all", -40.0): combined.GroupStats("mm_all", -40.0, 300, 1.2, 0.001)}
        verdict = combined.evaluate({"tt_27c_3.30v": {"vref": 1.2}}, mc)
        self.assertEqual(verdict.verdicts, [])
        self.assertTrue(any("-40" in note for note in verdict.notes))
        self.assertEqual(verdict.status, "NO DATA")

    def test_a_corner_with_no_mismatch_distribution_is_skipped_out_loud(self):
        mc = {("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2, 0.001)}
        samples = {"tt_27c_3.30v": {"vref": 1.2}, "tt_125c_3.30v": {"vref": 1.21}}
        verdict = combined.evaluate(samples, mc)
        self.assertEqual(len(verdict.verdicts), 1)
        self.assertTrue(any("tt_125c_3.30v" in item for item in verdict.skipped))

    def test_the_rollup_is_governed_by_the_worst_margin_corner(self):
        mc = {("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2000, 0.0010)}
        samples = {
            "tt_27c_3.30v": {"vref": 1.2000},
            "ss_27c_2.97v": {"vref": 1.2215},   # 3 sigma skirt outside the window
        }
        verdict = combined.evaluate(samples, mc)
        rollup = verdict.rollups[0]
        self.assertEqual(rollup.status, "FAIL")
        self.assertEqual(rollup.n_fail, 1)
        self.assertEqual(rollup.worst.corner_id, "ss_27c_2.97v")


class ParRSensitivityTests(unittest.TestCase):
    def _verdict(self):
        mc = {
            ("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2000, 0.0050),
            ("mm_res", 27.0): combined.GroupStats("mm_res", 27.0, 300, 1.2000, 0.0030),
        }
        return combined.evaluate({"tt_27c_3.30v": {"vref": 1.2000}}, mc)

    def test_scaling_par_r_moves_only_the_resistor_share_of_the_variance(self):
        verdict = self._verdict()
        doubled = next(s for s in verdict.sensitivity if s.factor == 2.0)
        expected = math.sqrt(0.005**2 + (2.0**2 - 1) * 0.003**2)
        self.assertAlmostEqual(doubled.halfwidth_v, 3 * expected, places=9)
        self.assertGreater(doubled.halfwidth_v, 3 * 0.005)

    def test_halving_par_r_narrows_the_window(self):
        verdict = self._verdict()
        halved = next(s for s in verdict.sensitivity if s.factor == 0.5)
        baseline = verdict.legs[27.0].halfwidth_v
        self.assertLess(halved.halfwidth_v, baseline)

    def test_no_resistor_group_means_the_risk_is_reported_unquantified(self):
        mc = {("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2, 0.005)}
        verdict = combined.evaluate({"tt_27c_3.30v": {"vref": 1.2}}, mc)
        self.assertEqual(verdict.sensitivity, [])
        self.assertIn("Not evaluable from this record", combined.render(verdict))


class ReportTests(unittest.TestCase):
    def test_the_report_cites_both_legs_by_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_mc_record(
                root,
                "20260802-000000-abcdef0",
                {
                    "mm_all": {27.0: spread_about(1.2140, 0.0050)},
                    "mm_ctrl": {27.0: [1.2142] * 5},
                },
            )
            write_corner_record(root, "20260802-010000-abcdef0", {"tt_27c_3.30v": 1.2142})
            verdict = combined.load(sim_dir=root)
        text = combined.render(verdict)
        self.assertIn("20260802-000000-abcdef0", text)
        self.assertIn("20260802-010000-abcdef0", text)
        self.assertIn("mc-untrimmed", text)
        self.assertIn("output-voltage-tc", text)

    def test_the_newest_record_of_each_leg_is_used_by_default(self):
        """Re-runnability: a newer record must be picked up with no arguments."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_mc_record(
                root, "20260801-000000-aaaaaaa",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}},
            )
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2000, 0.0010)}},
            )
            write_corner_record(root, "20260802-010000-bbbbbbb", {"tt_27c_3.30v": 1.2000})
            verdict = combined.load(sim_dir=root)
        self.assertEqual(verdict.mc_evidence.record_id, "20260802-000000-bbbbbbb")
        self.assertAlmostEqual(verdict.legs[27.0].sigma_v, 0.0010, places=9)

    def test_a_pinned_record_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_mc_record(
                root, "20260801-000000-aaaaaaa",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}},
            )
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2000, 0.0010)}},
            )
            write_corner_record(root, "20260802-010000-bbbbbbb", {"tt_27c_3.30v": 1.2000})
            verdict = combined.load(mc_record="20260801-000000-aaaaaaa", sim_dir=root)
        self.assertEqual(verdict.mc_evidence.record_id, "20260801-000000-aaaaaaa")

    def test_a_missing_leg_is_a_problem_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(root, "20260802-010000-bbbbbbb", {"tt_27c_3.30v": 1.2000})
            verdict = combined.load(sim_dir=root)
        self.assertEqual(verdict.status, "NO DATA")
        self.assertTrue(any("mc-untrimmed" in problem for problem in verdict.problems))

    def test_the_methodology_and_its_approximation_are_always_stated(self):
        mc = {("mm_all", 27.0): combined.GroupStats("mm_all", 27.0, 300, 1.2, 0.001)}
        text = combined.render(combined.evaluate({"tt_27c_3.30v": {"vref": 1.2}}, mc))
        self.assertIn("Granularity: per corner", text)
        self.assertIn("separable", text)
        self.assertIn("1.176", text)


class ProvenancePairingTests(unittest.TestCase):
    """Which two records get paired: the legs must describe the same circuit.

    A schematic-netlist corner leg grafted with an extracted-netlist mismatch
    leg is not a bench disagreement, it is a category error -- and it reaches
    the reader as a bare ``INVALID`` anchor mismatch that reads as one. These
    cover the pairing rule that prevents that, and the diagnostic that
    replaces it when no same-provenance pair exists.
    """

    def test_the_provenance_field_is_read_off_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2}, "schematic"
            )
            write_corner_record(
                root, "20260802-000000-bbbbbbb", {"tt_27c_3.30v": 1.2}, "extracted"
            )
            write_corner_record(root, "20260803-000000-ccccccc", {"tt_27c_3.30v": 1.2})

            def read(record_id: str) -> str:
                return combined.record_provenance(combined.CORNER_SLUG, record_id, root)

            self.assertEqual(read("20260801-000000-aaaaaaa"), "schematic")
            self.assertEqual(read("20260802-000000-bbbbbbb"), "extracted")
            self.assertEqual(read("20260803-000000-ccccccc"), combined.UNKNOWN_PROVENANCE)

    def test_a_same_provenance_pair_beats_a_newer_cross_provenance_record(self):
        """The defect this guards: newest-of-each silently cross-mixed the legs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "schematic"
            )
            write_corner_record(
                root, "20260804-000000-ddddddd", {"tt_27c_3.30v": 1.1000}, "extracted"
            )
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            verdict = combined.load(sim_dir=root)
        self.assertEqual(verdict.corner_evidence.record_id, "20260801-000000-aaaaaaa")
        self.assertEqual(verdict.mc_evidence.record_id, "20260802-000000-bbbbbbb")
        self.assertEqual(verdict.matched_provenance, "schematic")
        self.assertFalse(verdict.cross_provenance)
        self.assertEqual(verdict.problems, [])

    def test_the_newest_evidence_names_the_class_when_both_legs_have_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "schematic"
            )
            write_corner_record(
                root, "20260802-000000-bbbbbbb", {"tt_27c_3.30v": 1.2000}, "extracted"
            )
            write_mc_record(
                root, "20260803-000000-ccccccc",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            write_mc_record(
                root, "20260804-000000-ddddddd",
                {"mm_all": {27.0: spread_about(1.2140, 0.0010)}}, "extracted",
            )
            verdict = combined.load(sim_dir=root)
        self.assertEqual(verdict.matched_provenance, "extracted")
        self.assertEqual(verdict.corner_evidence.record_id, "20260802-000000-bbbbbbb")
        self.assertEqual(verdict.mc_evidence.record_id, "20260804-000000-ddddddd")

    def test_no_same_provenance_pair_is_a_stated_problem_not_a_bare_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260802-000000-bbbbbbb", {"tt_27c_3.30v": 1.2000}, "extracted"
            )
            write_mc_record(
                root, "20260801-000000-aaaaaaa",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            verdict = combined.load(sim_dir=root)
            text = combined.render(verdict)
        self.assertEqual(verdict.status, "NO DATA")
        self.assertNotEqual(verdict.status, "INVALID")
        self.assertTrue(verdict.problems)
        problem = verdict.problems[0]
        for expected in ("schematic", "extracted", "--corner-record", "--mc-record"):
            self.assertIn(expected, problem)
        self.assertIn("CROSS-PROVENANCE", text)

    def test_a_pinned_leg_makes_the_other_leg_match_its_provenance(self):
        """Pinning the corner leg must not be paired with a newer, other-class MC."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "schematic"
            )
            write_corner_record(
                root, "20260802-000000-bbbbbbb", {"tt_27c_3.30v": 1.2000}, "extracted"
            )
            write_mc_record(
                root, "20260803-000000-ccccccc",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            write_mc_record(
                root, "20260804-000000-ddddddd",
                {"mm_all": {27.0: spread_about(1.2140, 0.0010)}}, "extracted",
            )
            verdict = combined.load(
                corner_record="20260801-000000-aaaaaaa", sim_dir=root
            )
        self.assertEqual(verdict.corner_evidence.record_id, "20260801-000000-aaaaaaa")
        self.assertEqual(verdict.mc_evidence.record_id, "20260803-000000-ccccccc")
        self.assertEqual(verdict.matched_provenance, "schematic")

    def test_a_pinned_leg_whose_class_the_other_bench_lacks_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "extracted"
            )
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            verdict = combined.load(
                corner_record="20260801-000000-aaaaaaa", sim_dir=root
            )
        self.assertEqual(verdict.status, "NO DATA")
        self.assertIn("extracted", verdict.problems[0])
        self.assertIn("--mc-record", verdict.problems[0])

    def test_pinning_both_legs_is_never_overridden_even_across_classes(self):
        """An explicit cross-provenance pair is allowed -- and labelled as one."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "schematic"
            )
            write_corner_record(
                root, "20260802-000000-bbbbbbb", {"tt_27c_3.30v": 1.2000}, "extracted"
            )
            write_mc_record(
                root, "20260803-000000-ccccccc",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            write_mc_record(
                root, "20260804-000000-ddddddd",
                {"mm_all": {27.0: spread_about(1.2140, 0.0010)}}, "extracted",
            )
            verdict = combined.load(
                corner_record="20260802-000000-bbbbbbb",
                mc_record="20260803-000000-ccccccc",
                sim_dir=root,
            )
            text = combined.render(verdict)
        self.assertEqual(verdict.corner_evidence.record_id, "20260802-000000-bbbbbbb")
        self.assertEqual(verdict.mc_evidence.record_id, "20260803-000000-ccccccc")
        self.assertEqual(verdict.problems, [])  # deliberate: honoured, not refused
        self.assertTrue(verdict.cross_provenance)
        self.assertIsNone(verdict.matched_provenance)
        self.assertIn("CROSS-PROVENANCE", text)

    def test_the_report_states_which_class_the_legs_were_paired_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "extracted"
            )
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "extracted",
            )
            text = combined.render(combined.load(sim_dir=root))
        self.assertIn("Provenance pairing: extracted", text)
        self.assertIn("| **extracted** |", text)

    def test_records_without_the_field_still_pair_and_say_so(self):
        """Back-compat: records predating the field are 'unknown', not 'different'."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000})
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}},
            )
            verdict = combined.load(sim_dir=root)
            text = combined.render(verdict)
        self.assertEqual(verdict.problems, [])
        self.assertFalse(verdict.cross_provenance)
        self.assertEqual(verdict.matched_provenance, combined.UNKNOWN_PROVENANCE)
        self.assertIn("Provenance pairing: not stated", text)

    def test_a_live_corner_leg_pairs_the_mc_leg_on_its_own_provenance(self):
        """The suite hands its own run over live -- it still constrains the pair."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_corner_record(
                root, "20260801-000000-aaaaaaa", {"tt_27c_3.30v": 1.2000}, "schematic"
            )
            write_mc_record(
                root, "20260802-000000-bbbbbbb",
                {"mm_all": {27.0: spread_about(1.2140, 0.0050)}}, "schematic",
            )
            write_mc_record(
                root, "20260803-000000-ccccccc",
                {"mm_all": {27.0: spread_about(1.2140, 0.0010)}}, "extracted",
            )
            live = combined.EvidenceRef(
                slug=combined.CORNER_SLUG,
                record_id="20260801-000000-aaaaaaa",
                record=str(
                    root
                    / combined.CORNER_SLUG
                    / "records"
                    / "20260801-000000-aaaaaaa.md"
                ),
                logs=str(root / combined.CORNER_SLUG / "corners" / "20260801-000000-aaaaaaa"),
                live=True,
            )
            verdict = combined.load(
                sim_dir=root,
                corner_samples={"tt_27c_3.30v": {"vref": 1.2000}},
                corner_evidence=live,
            )
        self.assertEqual(verdict.mc_evidence.record_id, "20260802-000000-bbbbbbb")
        self.assertEqual(verdict.matched_provenance, "schematic")


class CommittedEvidenceTests(unittest.TestCase):
    """The tool against this repo's own committed evidence.

    Deliberately asserts *structure*, never the current pass/fail: the verdict
    is expected to change when either leg is re-run, and a test that pins
    today's result would have to be edited to let that happen.
    """

    def setUp(self):
        self.verdict = combined.load()
        if self.verdict.corner_evidence is None or self.verdict.mc_evidence is None:
            self.skipTest("no committed records for one of the two legs")

    def test_both_legs_resolve_to_a_committed_record_and_its_logs(self):
        for reference in (self.verdict.corner_evidence, self.verdict.mc_evidence):
            self.assertTrue((combined.REPO_ROOT / reference.record).is_file())
            self.assertTrue((combined.REPO_ROOT / reference.logs).is_dir())

    def test_every_readable_corner_gets_exactly_one_verdict(self):
        corner_ids = [v.corner_id for v in self.verdict.verdicts]
        self.assertEqual(len(corner_ids), len(set(corner_ids)))
        self.assertTrue(corner_ids)

    def test_the_claim_axis_is_covered_at_every_claimed_temperature(self):
        temps = sorted(r.temp_c for r in self.verdict.rollups)
        self.assertEqual(temps, [-40.0, 27.0, 125.0])

    def test_the_shared_corner_matches_the_mismatch_records_own_window(self):
        for temp, leg in self.verdict.legs.items():
            corner = next(
                v
                for v in self.verdict.verdicts
                if v.corner_id == combined.anchor_corner_id(temp)
            )
            self.assertAlmostEqual(corner.centre_v, leg.mean_v, places=9)
            self.assertAlmostEqual(corner.high_v - corner.low_v, 6 * leg.sigma_v, places=9)


if __name__ == "__main__":
    unittest.main()
