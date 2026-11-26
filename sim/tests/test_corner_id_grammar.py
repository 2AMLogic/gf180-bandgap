#!/usr/bin/env python3
"""Unit tests for the corner-log filename parser both evidence readers share.

    python3 -m unittest discover -s sim/tests -v

``sim/harness/evidence_lint.py`` (the checker) and ``sim/suite/analysis.py``
(the suite's reader) both parse ``<corner-id>.log`` names through
``sim/corner_id_grammar.py``. These tests hold the two readers to that: they
accept and reject the same names, each keeps its own interface, and each still
imports on its own.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

import corner_id_grammar as grammar  # noqa: E402
from harness import evidence_lint  # noqa: E402
from suite import analysis  # noqa: E402

if __package__:  # Dotted unittest invocation imports this module as a package member.
    from .test_evidence_lint import CORPUS_CORNER_IDS
else:  # Discovery from sim/tests imports the test modules as siblings.
    from test_evidence_lint import CORPUS_CORNER_IDS

#: Valid names beyond the corpus shapes the linter's tests enumerate: the
#: bare ``<volts>v`` supply form they pin as accepted.
EXTRA_VALID_CORNER_IDS = ("tt_27c_3v",)

VALID_CORNER_IDS = (*CORPUS_CORNER_IDS, *EXTRA_VALID_CORNER_IDS)

#: The malformed names the readers' own tests use (``test_evidence_lint.py``
#: and ``test_suite.py``), each with the words its diagnostic must carry.
MALFORMED_CORNER_IDS = {
    "tt_27c": "does not parse as",
    "tt": "does not parse as",
    "nonsense": "does not parse as",
    "tt_27_3.30v": "temperature field",
    "tt_hot_3.30v": "temperature field",
    "tt_27c_3.30": "supply field",
    "tt_27c_nominal": "supply field",
    "TT_27c_3.30v": "process field",
    "bjt__ff_27c_3.30v": "process field",
    "bjt_ff\n_27c_3.30v": "process field",
    "tt_27c\n_3.30v": "temperature field",
    "tt_27c_3.30v\n": "supply field",
}


def readme_fields(corner_id: str) -> grammar.CornerKey:
    """The fields sim/README.md's own rule gives: the last two underscores."""
    process, temp, supply = corner_id.rsplit("_", 2)
    return grammar.CornerKey(process=process, temp_c=float(temp[:-1]), supply=supply)


class SharedParserTests(unittest.TestCase):
    def test_valid_names_parse_into_the_fields_the_readme_split_gives(self):
        for corner_id in VALID_CORNER_IDS:
            with self.subTest(corner_id=corner_id):
                key = grammar.parse_corner_id(corner_id)
                self.assertEqual(key, readme_fields(corner_id))
                self.assertIsNone(grammar.corner_id_problem(corner_id))

    def test_malformed_names_are_rejected_naming_the_field_at_fault(self):
        for corner_id, expected in MALFORMED_CORNER_IDS.items():
            with self.subTest(corner_id=corner_id):
                self.assertIsNone(grammar.parse_corner_id(corner_id))
                self.assertIn(expected, grammar.corner_id_problem(corner_id))


class ReaderTests(unittest.TestCase):
    def test_the_checker_keeps_its_field_specific_diagnostics(self):
        for corner_id, expected in MALFORMED_CORNER_IDS.items():
            with self.subTest(corner_id=corner_id):
                self.assertIn(expected, evidence_lint.parse_corner_id(corner_id))
        for corner_id in VALID_CORNER_IDS:
            with self.subTest(corner_id=corner_id):
                self.assertIsNone(evidence_lint.parse_corner_id(corner_id))

    def test_the_suite_reader_keeps_its_parsed_fields(self):
        self.assertIs(analysis.CornerKey, grammar.CornerKey)
        for corner_id in VALID_CORNER_IDS:
            with self.subTest(corner_id=corner_id):
                self.assertEqual(
                    analysis.parse_corner_id(corner_id), readme_fields(corner_id)
                )
        for corner_id in MALFORMED_CORNER_IDS:
            with self.subTest(corner_id=corner_id):
                self.assertIsNone(analysis.parse_corner_id(corner_id))

    def test_both_readers_accept_exactly_the_same_names(self):
        for corner_id in (*VALID_CORNER_IDS, *MALFORMED_CORNER_IDS):
            with self.subTest(corner_id=corner_id):
                accepted = evidence_lint.parse_corner_id(corner_id) is None
                self.assertEqual(analysis.parse_corner_id(corner_id) is not None, accepted)

    def test_every_committed_corner_log_name_keeps_its_parsed_fields(self):
        """The evidence is frozen by the append-only rule; the parser adapts to it."""
        logs = sorted((REPO_ROOT / "sim").glob("*/corners/*/*.log"))
        self.assertGreater(len(logs), 0, "no committed corner logs found")
        for log in logs:
            with self.subTest(corner_id=log.stem):
                self.assertIsNone(evidence_lint.parse_corner_id(log.stem))
                self.assertEqual(analysis.parse_corner_id(log.stem), readme_fields(log.stem))


class StandaloneImportTests(unittest.TestCase):
    """Each reader imports by itself: neither needs the other's package."""

    def python(self, *argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        """Run ``python <argv>`` in a fresh interpreter; it must exit 0."""
        completed = subprocess.run(
            [sys.executable, *argv],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def modules_after(self, statement: str) -> set[str]:
        """``sys.modules`` of a fresh interpreter that ran ``statement``."""
        script = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            f"{statement}\n"
            "print('\\n'.join(sorted(sys.modules)))\n"
        )
        return set(self.python("-I", "-c", script, str(SIM_DIR)).stdout.split())

    def test_the_checker_imports_without_the_suite(self):
        modules = self.modules_after("import harness.evidence_lint")
        self.assertIn("harness.evidence_lint", modules)
        self.assertNotIn("suite", modules)

    def test_the_suite_reader_imports_without_the_harness(self):
        modules = self.modules_after("import suite.analysis")
        self.assertIn("suite.analysis", modules)
        self.assertNotIn("harness", modules)

    def test_each_tool_still_starts_from_its_documented_entry_point(self):
        for script in (
            "sim/check_records.py",
            "sim/run_suite.py",
            "sim/run_combined_accuracy.py",
        ):
            with self.subTest(script=script):
                self.python(str(REPO_ROOT / script), "--help")

    def test_each_reader_still_imports_under_the_dotted_module_form(self):
        """``python3 -m <dotted.module>`` puts the CWD, not the package, on sys.path."""
        for module in ("sim.harness.evidence_lint", "sim.suite.analysis"):
            with self.subTest(module=module):
                self.python("-m", module, "--help", cwd=REPO_ROOT)

    def test_the_checker_module_still_runs_as_a_script(self):
        self.python(str(SIM_DIR / "harness" / "evidence_lint.py"), "--help")

    def test_corpus_imports_under_dotted_unittest_invocation(self):
        self.python(
            "-m", "unittest", "sim.tests.test_corner_id_grammar.SharedParserTests",
            cwd=REPO_ROOT,
        )


if __name__ == "__main__":
    unittest.main()
