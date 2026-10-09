#!/usr/bin/env python3
"""Unit tests for the spec-line suite. No PDK and no ngspice required.

    python3 -m unittest discover -s sim/tests -v

These cover the two things the suite can get wrong on its own (independent of
whether a simulation converged): reading raw evidence back correctly, and
judging it against the ratified numbers.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from suite import analysis, completeness, spec  # noqa: E402
from suite.cli import BenchRun, render_summary  # noqa: E402


class SuiteIndexTests(unittest.TestCase):
    def test_every_spec_line_names_an_experiment_slug(self):
        for line in spec.SUITE:
            with self.subTest(line=line.key):
                self.assertTrue(line.slug)
                self.assertTrue(line.row)
                self.assertTrue(line.target)

    def test_the_startup_row_is_delegated_not_reimplemented(self):
        """#11 owns the startup bench; #12 only wires the slug in."""
        startup = next(line for line in spec.SUITE if line.key == "startup")
        self.assertEqual(startup.slug, "startup")
        self.assertEqual(startup.owner, "#11")
        self.assertFalse(startup.gated, "the suite must not invent #11's limits")
        self.assertFalse(
            (SIM_DIR / "startup" / "testbench").exists()
            and any(line.slug == "startup" and line.limits for line in spec.SUITE),
            "if #11's bench lands, its own checks stay authoritative",
        )

    def test_every_bench_this_issue_owns_exists(self):
        for line in spec.SUITE:
            if line.owner != "#12":
                continue
            with self.subTest(slug=line.slug):
                self.assertTrue(
                    (SIM_DIR / line.slug / "testbench" / "tb.json").is_file(),
                    f"sim/{line.slug}/testbench/tb.json is missing",
                )

    def test_ratified_limits_agree_with_each_manifest(self):
        """The suite index and tb.json must not drift apart (both are ratified)."""
        problems: list[str] = []
        for line in spec.SUITE:
            manifest_path = SIM_DIR / line.slug / "testbench" / "tb.json"
            if not manifest_path.is_file():
                continue
            checks = json.loads(manifest_path.read_text()).get("checks", {})
            problems += analysis.check_limits_match_manifest(line, checks)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_ratified_numbers_match_the_readme_table(self):
        """A spot check against README.md so a relaxed limit cannot hide here."""
        readme = (SIM_DIR.parent / "README.md").read_text()
        self.assertIn("1.20 V ±2% untrimmed", readme)
        self.assertIn("< 50 ppm/°C", readme)
        self.assertIn("> 60 dB DC–1 kHz", readme)
        self.assertIn("< 1 mV/V", readme)
        self.assertIn("< 50 µA", readme)
        limits = {
            (line.key, limit.measurement, limit.kind): limit.value
            for line in spec.SUITE
            for limit in line.limits
        }
        self.assertEqual(limits[("output-reference", "vref", "min")], 1.176)
        self.assertEqual(limits[("output-reference", "vref", "max")], 1.224)
        self.assertEqual(limits[("temp-coefficient", "tc_ppm", "max")], 50.0)
        self.assertEqual(limits[("psrr", "psrr_1hz_db", "min")], 60.0)
        self.assertEqual(limits[("line-regulation", "linereg_mv_per_v", "max")], 1.0)
        self.assertEqual(limits[("quiescent-current", "iq_ua", "max")], 50.0)


class LogReadingTests(unittest.TestCase):
    def test_parses_scalar_measurements_only(self):
        text = "\n".join(
            [
                "Circuit: * iq @ tt_27c_3.30v",
                "m_iq_ua = 4.4277512345e+01",
                "m_vref = 1.2291153728e+00",
                "m_f_check = 1.0000000000e+00,0.0000000000e+00",
                "v(vref) = 1.23",
            ]
        )
        self.assertEqual(
            analysis.parse_log(text), {"iq_ua": 44.277512345, "vref": 1.2291153728}
        )

    def test_overflowing_scalars_are_not_measurements(self):
        text = "m_iq_ua = 1e999\nm_vref = -1e999\nm_ok = 1.5\n"
        self.assertEqual(analysis.parse_log(text), {"ok": 1.5})

    def test_overflowing_raw_log_is_no_data_never_pass(self):
        line = next(l for l in spec.SUITE if l.key == "quiescent-current")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tt_27c_3.30v.log").write_text("m_iq_ua = -1e999\n")
            samples = analysis.read_corner_logs(Path(tmp))
        self.assertEqual(analysis.evaluate_line(line, samples).status, "NO DATA")
        # mixed: a finite corner alongside an overflowed one still cannot pass
        # for the overflowed corner when coverage is expected.
        mixed = {"tt_27c_3.30v": {}, "ss_-40c_2.97v": {"iq_ua": 30.0}}
        status = analysis.evaluate_line(
            line, mixed, expected_corners=list(mixed)
        ).status
        self.assertNotEqual(status, "PASS")

    def test_reads_one_directory_of_corner_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            corners = Path(tmp)
            (corners / "tt_27c_3.30v.log").write_text("m_iq_ua = 4.0e+01\n")
            (corners / "ff_125c_3.63v.log").write_text("m_iq_ua = 7.3e+01\n")
            (corners / "notes.txt").write_text("ignored\n")
            samples = analysis.read_corner_logs(corners)
        self.assertEqual(sorted(samples), ["ff_125c_3.63v", "tt_27c_3.30v"])
        self.assertEqual(samples["ff_125c_3.63v"]["iq_ua"], 73.0)

    def test_missing_directory_reads_as_no_evidence(self):
        self.assertEqual(analysis.read_corner_logs(Path("/nope/nowhere")), {})

    def test_corner_id_grammar_keeps_device_family_prefixes(self):
        key = analysis.parse_corner_id("bjt_ss_-40c_2.97v")
        self.assertIsNotNone(key)
        self.assertEqual(key.process, "bjt_ss")
        self.assertEqual(key.temp_c, -40.0)
        self.assertEqual(key.supply, "2.97v")
        self.assertEqual(key.corner_id, "bjt_ss_-40c_2.97v")
        self.assertIsNone(analysis.parse_corner_id("nonsense"))


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.iq_line = next(line for line in spec.SUITE if line.key == "quiescent-current")

    def test_worst_corner_governs_a_max_limit(self):
        samples = {
            "tt_27c_3.30v": {"iq_ua": 44.0, "vref": 1.2},
            "ff_125c_3.63v": {"iq_ua": 73.5, "vref": 1.2},
            "ss_-40c_2.97v": {"iq_ua": 21.0, "vref": 1.2},
        }
        outcome = analysis.evaluate_line(self.iq_line, samples)
        self.assertEqual(outcome.status, "FAIL")
        self.assertEqual(outcome.worst.worst_corner, "ff_125c_3.63v")
        self.assertEqual(outcome.worst.worst_value, 73.5)
        self.assertEqual(outcome.worst.n_violations, 1)

    def test_all_corners_inside_the_limit_pass(self):
        samples = {f"tt_{t}c_3.30v": {"iq_ua": 30.0 + t / 100} for t in (-40, 27, 125)}
        outcome = analysis.evaluate_line(self.iq_line, samples)
        self.assertEqual(outcome.status, "PASS")

    def test_a_missing_measurement_is_no_data_not_a_pass(self):
        outcome = analysis.evaluate_line(self.iq_line, {"tt_27c_3.30v": {"vref": 1.2}})
        self.assertEqual(outcome.status, "NO DATA")

    def test_worst_corner_governs_a_min_limit(self):
        psrr = next(line for line in spec.SUITE if line.key == "psrr")
        samples = {
            "tt_27c_3.30v": {"psrr_1hz_db": 72.0, "psrr_1khz_db": 71.0},
            "ss_-40c_2.97v": {"psrr_1hz_db": 61.0, "psrr_1khz_db": 59.0},
        }
        outcome = analysis.evaluate_line(psrr, samples)
        self.assertEqual(outcome.status, "FAIL")
        failing = outcome.worst
        self.assertEqual(failing.limit.measurement, "psrr_1khz_db")
        self.assertEqual(failing.worst_corner, "ss_-40c_2.97v")

    def test_an_ungated_line_is_pending_not_passing(self):
        startup = next(line for line in spec.SUITE if line.key == "startup")
        self.assertEqual(analysis.evaluate_line(startup, {}).status, "PENDING")


class BoxMethodTests(unittest.TestCase):
    """The measurement-convention trap this suite exists to avoid."""

    @staticmethod
    def _parabola(peak_c: float, curvature: float, nominal: float = 1.2) -> dict:
        """Vref(T) = nominal - curvature*(T - peak)^2, sampled the way the bench does."""
        def vref(temp: float) -> float:
            return nominal - curvature * (temp - peak_c) ** 2

        fine = [vref(-40 + step) for step in range(166)]
        return {
            "tc_ppm": (max(fine) - min(fine)) / (vref(27.0) * 165.0) * 1e6,
            "vref_box_max": max(fine),
            "vref_box_min": min(fine),
            "vref_m40": vref(-40.0),
            "vref_27": vref(27.0),
            "vref_125": vref(125.0),
        }

    def test_endpoint_only_understates_tc_when_the_peak_is_interior(self):
        """A peak at 60 degC falls between -40/27/125: 3 points miss it."""
        samples = {"tt_27c_3.30v": self._parabola(peak_c=60.0, curvature=2e-6)}
        comparison = analysis.compare_box_to_endpoints(samples)
        endpoint = analysis.endpoint_tc_ppm(samples["tt_27c_3.30v"])
        self.assertGreater(comparison.worst_box_ppm, endpoint)
        self.assertGreater(comparison.understated_by_ppm, 0.05)
        self.assertEqual(comparison.interior_extremum_corners, ["tt_27c_3.30v"])
        self.assertTrue(comparison.endpoint_only_would_mislead)

    def test_a_monotonic_curve_makes_both_methods_agree(self):
        """No interior extremum -> box == endpoint; the box is never *worse*."""
        slope = 1.19e-4  # V/degC, the near-flat positive ramp #8's sizing shows
        fine = [1.2187 + slope * step for step in range(166)]
        samples = {
            "tt_27c_3.30v": {
                "tc_ppm": (max(fine) - min(fine)) / (fine[67] * 165.0) * 1e6,
                "vref_box_min": min(fine),
                "vref_box_max": max(fine),
                "vref_m40": fine[0],
                "vref_27": fine[67],
                "vref_125": fine[165],
            }
        }
        comparison = analysis.compare_box_to_endpoints(samples)
        self.assertEqual(comparison.interior_extremum_corners, [])
        self.assertAlmostEqual(
            analysis.endpoint_tc_ppm(samples["tt_27c_3.30v"]),
            samples["tt_27c_3.30v"]["tc_ppm"],
            places=6,
        )
        self.assertFalse(comparison.endpoint_only_would_mislead)

    def test_endpoint_tc_needs_all_three_endpoints(self):
        self.assertIsNone(analysis.endpoint_tc_ppm({"vref_m40": 1.2, "vref_27": 1.2}))


class CrossCheckTests(unittest.TestCase):
    def test_the_two_temperature_mechanisms_must_agree(self):
        samples = {
            "tt_-40c_3.30v": {"vref": 1.2187, "vref_m40": 1.2187, "vref_27": 1.2291,
                              "vref_125": 1.2383},
            "tt_125c_3.30v": {"vref": 1.2383, "vref_m40": 1.2187, "vref_27": 1.2291,
                              "vref_125": 1.2383},
        }
        check = analysis.cross_check_temperature_axes(samples)
        self.assertEqual(check.n_compared, 2)
        self.assertTrue(check.consistent)

    def test_a_pinned_temperature_axis_is_caught(self):
        """If .temp never took effect, the outer axis reads room temperature."""
        samples = {
            "tt_-40c_3.30v": {"vref": 1.2291, "vref_m40": 1.2187, "vref_27": 1.2291,
                              "vref_125": 1.2383},
        }
        check = analysis.cross_check_temperature_axes(samples)
        self.assertFalse(check.consistent)
        self.assertEqual(check.worst_at, "tt_-40c_3.30v")


class SummaryTests(unittest.TestCase):
    def _bench(self, slug: str, samples: dict, status: str = "ok") -> BenchRun:
        lines = spec.by_slug()[slug]
        bench = BenchRun(slug=slug, lines=lines, status=status, returncode=0, samples=samples)
        bench.outcomes = [analysis.evaluate_line(line, samples) for line in lines]
        return bench

    def _summary(self, benches) -> str:
        import datetime as dt

        return render_summary(
            benches,
            started=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            git={"commit": "f" * 40, "short": "fffffff", "branch": "main", "dirty": False},
            mode="full PVT",
            wrote_evidence=True,
        )

    def test_a_missing_bench_is_pending_not_a_silent_pass(self):
        """#11 has not landed: the suite must say so, not skip the row."""
        missing = BenchRun(
            slug="startup",
            lines=spec.by_slug()["startup"],
            status="missing",
            message="sim/startup/testbench/tb.json does not exist yet",
        )
        missing.outcomes = [analysis.evaluate_line(line, {}) for line in missing.lines]
        text = self._summary([self._bench("iq", {"tt_27c_3.30v": {"iq_ua": 44.0}}), missing])
        self.assertIn("PENDING", text)
        self.assertIn("Startup", text)
        self.assertIn("not present", text)
        self.assertNotIn("Simulation-complete**: all", text)

    def test_a_failing_line_is_reported_as_not_simulation_complete(self):
        bench = self._bench("iq", {"ff_125c_3.63v": {"iq_ua": 73.5}}, status="check-failed")
        text = self._summary([bench])
        self.assertIn("NOT simulation-complete", text)
        self.assertIn("FAIL", text)
        self.assertIn("ff_125c_3.63v", text)

    def test_rows_outside_the_suite_are_listed_in_every_summary(self):
        text = self._summary([self._bench("iq", {"tt_27c_3.30v": {"iq_ua": 44.0}})])
        self.assertIn("Ratified rows this suite does not claim", text)
        self.assertIn("mc-untrimmed", text)
        self.assertIn("Area", text)

    def test_the_mismatch_leg_is_no_longer_listed_as_unclaimed(self):
        """It is claimed now -- by the combined verdict, not by one bench."""
        unclaimed = " ".join(row.row for row in spec.NOT_CLAIMED_HERE)
        self.assertNotIn("mismatch", unclaimed.lower())
        self.assertIn("mc-untrimmed", [slug for slug, _ in spec.COMBINED_ACCURACY.legs])
        self.assertIn(
            "output-voltage-tc", [slug for slug, _ in spec.COMBINED_ACCURACY.legs]
        )

    def test_a_failing_combined_row_is_reported_even_when_every_bench_passes(self):
        """The accuracy row is ratified on two legs; one leg passing is not it."""
        import datetime as dt

        from suite import combined as combined_module

        mc = {
            ("mm_all", 27.0): combined_module.GroupStats(
                "mm_all", 27.0, 300, 1.2140, 0.0050
            )
        }
        verdict = combined_module.evaluate({"tt_27c_3.30v": {"vref": 1.2142}}, mc)
        text = render_summary(
            [self._bench("iq", {"tt_27c_3.30v": {"iq_ua": 44.0}})],
            started=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            git={"commit": "f" * 40, "short": "fffffff", "branch": "main", "dirty": False},
            mode="full PVT",
            wrote_evidence=True,
            combined=verdict,
        )
        self.assertEqual(verdict.status, "FAIL")
        self.assertIn("Output reference (untrimmed accuracy, both legs)", text)
        self.assertIn("Combined verdict: FAIL", text)
        self.assertNotIn("Simulation-complete**: all", text)


class CompletenessTests(unittest.TestCase):
    """Missing evidence must block the acceptance claim and the exit code."""

    TT = "tt_27c_3.30v"
    FF = "ff_125c_3.63v"

    def _bench(self, slug, samples, status="ok", expected=None):
        lines = spec.by_slug()[slug]
        bench = BenchRun(
            slug=slug, lines=lines, status=status, returncode=0 if status == "ok" else 2,
            samples=samples, expected_corners=expected,
        )
        bench.outcomes = [analysis.evaluate_line(l, samples, expected) for l in lines]
        return bench

    def _good_samples(self, slug, corners):
        names = {m.measurement for l in spec.by_slug()[slug] for m in l.limits}
        good = {"iq_ua": 40.0, "vref": 1.2, "tc_ppm": 20.0, "psrr_1hz_db": 70.0,
                "psrr_1khz_db": 70.0, "linereg_mv_per_v": 0.5, "vref_min": 1.19,
                "vref_max": 1.21}
        return {c: {n: good[n] for n in names} for c in corners}

    def _combined(self, corners):
        from suite import combined as cm

        mc = {("mm_all", t): cm.GroupStats("mm_all", t, 300, 1.2, 0.001)
              for t in (-40.0, 27.0, 125.0)}
        return cm.evaluate({c: {"vref": 1.2} for c in corners}, mc)

    def _all_corners(self):
        return ["tt_-40c_2.97v", "tt_27c_3.30v", "ff_125c_3.63v"]

    def _full(self):
        corners = self._all_corners()
        benches = []
        for slug in spec.slugs():
            if not any(l.limits for l in spec.by_slug()[slug]):
                b = BenchRun(slug=slug, lines=spec.by_slug()[slug], status="ok", returncode=0)
                b.outcomes = [analysis.evaluate_line(l, {}) for l in b.lines]
                benches.append(b)
                continue
            benches.append(self._bench(slug, self._good_samples(slug, corners), expected=corners))
        return benches, self._combined(corners)

    def _text(self, benches, combined, mode="full PVT"):
        import datetime as dt

        return render_summary(
            benches,
            started=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            git={"commit": "f" * 40, "short": "fffffff", "branch": "main", "dirty": False},
            mode=mode, wrote_evidence=False, combined=combined,
        )

    def test_fully_complete_passing_fixture_claims_completion(self):
        benches, combined = self._full()
        self.assertEqual(combined.status, "PASS")
        done = completeness.assess(benches, combined, spec.slugs())
        self.assertTrue(done.complete, done.missing + done.failures)
        self.assertEqual(done.exit_code, 0)
        self.assertIn("**Simulation-complete**", self._text(benches, combined))

    def test_iq_only_run_passes_but_makes_no_completeness_claim(self):
        bench = self._bench("iq", self._good_samples("iq", [self.TT]), expected=[self.TT])
        done = completeness.assess([bench], None, spec.slugs())
        self.assertEqual(done.state, "subset")
        self.assertEqual(done.exit_code, 0)
        text = self._text([bench], None)
        self.assertIn("Subset run", text)
        self.assertNotIn("Simulation-complete**", text)
        self.assertNotIn("two-legged untrimmed-accuracy row passes", text)

    def test_smoke_run_passes_but_makes_no_completeness_claim(self):
        benches, combined = self._full()
        done = completeness.assess(benches, combined, spec.slugs(), smoke=True)
        self.assertEqual(done.state, "subset")
        self.assertEqual(done.exit_code, 0)
        self.assertNotIn("Simulation-complete**", self._text(benches, combined, mode="smoke"))

    def test_a_requested_bench_missing_from_the_tree_blocks(self):
        benches, combined = self._full()
        startup = next(b for b in benches if b.slug == "startup")
        startup.status, startup.message = "missing", "no tb.json"
        done = completeness.assess(benches, combined, spec.slugs())
        self.assertTrue(done.blocked)
        self.assertNotEqual(done.exit_code, 0)
        self.assertIn("NOT simulation-complete", self._text(benches, combined))

    def test_gated_no_data_blocks(self):
        bench = self._bench("iq", {self.TT: {"vref": 1.2}}, expected=[self.TT])
        done = completeness.assess([bench], None, spec.slugs())
        self.assertTrue(done.blocked)
        self.assertEqual(done.exit_code, 2)
        text = self._text([bench], None)
        self.assertIn("NO DATA", text)
        self.assertNotIn("Subset run", text)

    def test_measurement_missing_at_one_present_corner_is_not_a_pass(self):
        samples = {self.TT: {"iq_ua": 40.0}, self.FF: {"vref": 1.2}}
        outcome = analysis.evaluate_line(spec.by_slug()["iq"][0], samples)
        self.assertEqual(outcome.status, "NO DATA")
        self.assertEqual(outcome.worst.missing_corners, (self.FF,))
        bench = self._bench("iq", samples)
        done = completeness.assess([bench], None, spec.slugs())
        self.assertEqual(done.exit_code, 2)
        self.assertIn(self.FF, " ".join(done.missing))

    def test_a_corner_with_no_log_is_caught_via_the_expected_grid(self):
        samples = {self.TT: {"iq_ua": 40.0, "vref": 1.2}}
        bench = self._bench("iq", samples, expected=[self.TT, self.FF])
        self.assertEqual(completeness.assess([bench], None, spec.slugs()).exit_code, 2)

    def test_a_real_violation_still_fails_even_with_gaps(self):
        outcome = analysis.evaluate_line(
            spec.by_slug()["iq"][0],
            {self.TT: {"iq_ua": 73.0}, self.FF: {"vref": 1.2}},
        )
        self.assertEqual(outcome.status, "FAIL")

    def test_runner_failure_with_partial_passing_logs_blocks(self):
        bench = self._bench("iq", self._good_samples("iq", [self.TT]),
                            status="error", expected=[self.TT])
        done = completeness.assess([bench], None, spec.slugs())
        self.assertTrue(done.blocked)
        self.assertEqual(done.exit_code, 2)
        self.assertNotIn("Subset run", self._text([bench], None))

    def test_expected_corner_ids_follow_the_manifest_and_overrides(self):
        from suite.cli import expected_corner_ids

        self.assertEqual(len(expected_corner_ids("iq")), 81)
        self.assertEqual(expected_corner_ids("iq", smoke=True), [self.TT])
        self.assertEqual(len(expected_corner_ids("iq", corner_set="tt")), 9)
        self.assertIsNone(expected_corner_ids("no-such-bench"))

    def test_main_exit_codes_follow_the_assessment(self):
        from unittest import mock

        from suite import cli

        no_data = False

        def fake_run(slug, lines, extra, quiet=False, expected_corners=None):
            samples = {self.TT: {"vref": 1.2}} if no_data else self._good_samples(slug, [self.TT])
            return self._bench(slug, samples, expected=[self.TT])

        import contextlib
        import io

        for no_data, code in ((False, 0), (True, 2)):
            with mock.patch.object(cli, "run_bench", fake_run), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["--only", "iq", "--no-write", "--quiet"]), code)


if __name__ == "__main__":
    unittest.main()
