#!/usr/bin/env python3
"""Unit tests for the evidence-record format checker. No PDK required.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence_lint  # noqa: E402

RECORD_ID = "20260731-112754-861c7a8"
OLDER_ID = "20260731-030932-8fb0ea6"

#: Every corner-id shape the committed corpus actually uses. These filenames
#: are frozen by the append-only rule, so the grammar has to accept them --
#: the checker is the thing that adapts, never the evidence (sim/README.md).
CORPUS_CORNER_IDS = (
    "tt_27c_3.30v",              # sim/README.md's worked example
    "ss_-40c_2.97v",
    "ff_125c_3.63v",
    "fs_27c_2.97v",
    "sf_-40c_3.63v",
    "bjt_ff_-40c_2.97v",         # device-family prefix in the process field
    "res_ss_125c_3.63v",
    "typical_-40c_nosupply",     # device testbench: no supply rail to sweep
    "bjt_typical_125c_nosupply",
    "res_typical_27c_nosupply",
    "bjt_ff_-10c_nosupply",      # non-CLAUDE.md temperature point
    "bjt_typical_90c_nosupply",
    "res_typical_27c_nwell2p97v",  # node-qualified rail, 'p' decimal point
    "res_typical_27c_nwell3p63v",
)


def valid_record(record_id: str = RECORD_ID, **overrides: str) -> str:
    """A minimal record carrying all nine fields from sim/README.md."""
    fields = {
        "Record ID": record_id,
        "Claim": "`spec/bandgap.md#anchor` -- placeholder claim",
        "Netlist provenance": "schematic (`design/bandgap.sch`)",
        "Corner matrix run": "tt/27C/3.30V only; see Statistical convention",
        "Statistical convention": "N/A (corner-matrix claim)",
        "Result": "**Overall: PASS** (placeholder)",
        "Links": "Raw logs: `sim/x/corners/%s/`" % record_id,
        "Timestamp / author": "2026-07-31T11:27:54Z, agent-builder",
        "Supersedes": "(none -- first record for this claim)",
    }
    fields.update(overrides)
    lines = [f"# Record {record_id}", ""]
    for name, value in fields.items():
        if value is None:
            continue
        lines.append(f"- **{name}**: {value}".rstrip())
    lines += ["", "## Environment", "", "- ngspice: ngspice-46", ""]
    return "\n".join(lines)


def write_experiment(
    root: Path,
    slug: str = "output-voltage-tc",
    record_id: str = RECORD_ID,
    text: str | None = None,
    logs: tuple = ("tt_27c_3.30v.log",),
    snapshot: bool = True,
) -> list:
    """Materialise one experiment on disk; return its repo-relative paths."""
    paths = []
    record = root / "sim" / slug / "records" / f"{record_id}.md"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(text if text is not None else valid_record(record_id))
    paths.append(f"sim/{slug}/records/{record_id}.md")
    if snapshot:
        spice = root / "sim" / slug / "netlist-snapshots" / f"{record_id}.spice"
        spice.parent.mkdir(parents=True, exist_ok=True)
        spice.write_text("* netlist\n")
        paths.append(f"sim/{slug}/netlist-snapshots/{record_id}.spice")
    for name in logs:
        log = root / "sim" / slug / "corners" / record_id / name
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("* log\n")
        paths.append(f"sim/{slug}/corners/{record_id}/{name}")
    return paths


class CornerIdGrammarTests(unittest.TestCase):
    def test_every_corner_id_in_the_committed_corpus_parses(self):
        for corner_id in CORPUS_CORNER_IDS:
            with self.subTest(corner_id=corner_id):
                self.assertIsNone(evidence_lint.parse_corner_id(corner_id))

    def test_the_real_corner_log_names_on_disk_parse(self):
        """Guards against the grammar drifting away from the actual evidence."""
        logs = sorted((REPO_ROOT / "sim").glob("*/corners/*/*.log"))
        self.assertGreater(len(logs), 0, "no committed corner logs found")
        for log in logs:
            with self.subTest(log=log.name):
                self.assertIsNone(evidence_lint.parse_corner_id(log.stem))

    def test_missing_fields_are_rejected(self):
        self.assertIsNotNone(evidence_lint.parse_corner_id("tt_27c"))
        self.assertIsNotNone(evidence_lint.parse_corner_id("tt"))

    def test_temperature_field_must_carry_its_c_suffix(self):
        self.assertIsNotNone(evidence_lint.parse_corner_id("tt_27_3.30v"))
        self.assertIsNotNone(evidence_lint.parse_corner_id("tt_hot_3.30v"))

    def test_supply_field_must_be_a_voltage_or_nosupply(self):
        self.assertIsNotNone(evidence_lint.parse_corner_id("tt_27c_3.30"))
        self.assertIsNotNone(evidence_lint.parse_corner_id("tt_27c_nominal"))
        self.assertIsNone(evidence_lint.parse_corner_id("tt_27c_3v"))

    def test_process_field_must_be_lowercase_tokens(self):
        self.assertIsNotNone(evidence_lint.parse_corner_id("TT_27c_3.30v"))
        self.assertIsNotNone(evidence_lint.parse_corner_id("bjt__ff_27c_3.30v"))


class RecordIdTests(unittest.TestCase):
    def test_the_ratified_shape_is_accepted(self):
        self.assertIsNone(evidence_lint.validate_record_id(RECORD_ID))

    def test_a_malformed_id_is_rejected(self):
        for bad in ("2026731-112754-861c7a8", "20260731-112754", "20260731-112754-ZZZ"):
            with self.subTest(record_id=bad):
                self.assertIsNotNone(evidence_lint.validate_record_id(bad))

    def test_an_impossible_timestamp_is_rejected(self):
        self.assertIsNotNone(evidence_lint.validate_record_id("20261340-112754-861c7a8"))


class FieldParsingTests(unittest.TestCase):
    def test_indented_lines_continue_the_field_above(self):
        text = "\n".join([
            "- **Corner matrix run**:",
            "  - Process: tt, ss, ff",
            "  - Temperature: -40 C, 27 C, 125 C",
            "",
            "## Environment",
            "",
            "- ngspice: ngspice-46",
        ])
        fields, duplicates = evidence_lint.parse_fields(text)
        self.assertEqual(duplicates, [])
        self.assertIn("Process: tt, ss, ff", fields["Corner matrix run"].value)
        self.assertNotIn("ngspice", fields["Corner matrix run"].value)

    def test_a_field_with_only_a_colon_and_no_body_is_empty(self):
        fields, _ = evidence_lint.parse_fields("- **Claim**:\n\n## Environment\n")
        self.assertEqual(fields["Claim"].value, "")

    def test_nested_bold_bullets_are_not_top_level_fields(self):
        fields, _ = evidence_lint.parse_fields(
            "- **Result**: see table\n  - **Overall: PASS**\n"
        )
        self.assertEqual(list(fields), ["Result"])


class RecordCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def check(self, paths) -> list:
        experiments = evidence_lint.collect_experiments(paths)
        return [str(p) for p in evidence_lint.check_experiments(self.root, experiments)]

    def test_a_well_formed_record_passes(self):
        paths = write_experiment(self.root)
        self.assertEqual(self.check(paths), [])

    def test_every_required_field_is_enforced(self):
        for name in evidence_lint.REQUIRED_FIELDS:
            with self.subTest(field=name):
                root = Path(tempfile.mkdtemp(dir=self.tmp.name))
                paths = write_experiment(root, text=valid_record(**{name: None}))
                experiments = evidence_lint.collect_experiments(paths)
                problems = [
                    str(p) for p in evidence_lint.check_experiments(root, experiments)
                ]
                self.assertTrue(
                    any(f"missing required field **{name}**" in p for p in problems),
                    problems,
                )

    def test_an_empty_field_is_as_bad_as_a_missing_one(self):
        paths = write_experiment(self.root, text=valid_record(Claim=""))
        self.assertTrue(
            any("**Claim** is empty" in p for p in self.check(paths)), self.check(paths)
        )

    def test_record_id_must_match_the_filename(self):
        paths = write_experiment(self.root, text=valid_record(**{"Record ID": OLDER_ID}))
        problems = self.check(paths)
        self.assertTrue(any("but the filename says" in p for p in problems), problems)

    def test_a_malformed_filename_is_reported(self):
        paths = write_experiment(self.root, record_id="not-a-record-id")
        problems = self.check(paths)
        self.assertTrue(any("record id" in p for p in problems), problems)

    def test_a_missing_netlist_snapshot_is_reported(self):
        paths = write_experiment(self.root, snapshot=False)
        problems = self.check(paths)
        self.assertTrue(any("no frozen netlist" in p for p in problems), problems)

    def test_a_missing_corners_directory_is_reported(self):
        paths = write_experiment(self.root, logs=())
        problems = self.check(paths)
        self.assertTrue(any("no raw per-corner logs" in p for p in problems), problems)

    def test_an_unparseable_corner_log_is_reported(self):
        paths = write_experiment(self.root, logs=("tt_27c_3.30v.log", "run2.log"))
        problems = self.check(paths)
        self.assertTrue(any("does not parse" in p for p in problems), problems)
        self.assertTrue(any("run2" in p for p in problems), problems)

    def test_supersedes_must_name_an_existing_record(self):
        paths = write_experiment(self.root, text=valid_record(Supersedes=OLDER_ID))
        problems = self.check(paths)
        self.assertTrue(any("which has no record" in p for p in problems), problems)

    def test_supersedes_accepts_a_record_in_the_same_experiment(self):
        paths = write_experiment(self.root, text=valid_record(Supersedes=OLDER_ID))
        paths += write_experiment(self.root, record_id=OLDER_ID)
        self.assertEqual(self.check(paths), [])

    def test_supersedes_none_forms_are_accepted(self):
        for value in ("(none)", "(none -- first record for this claim)", "N/A", "none"):
            with self.subTest(value=value):
                root = Path(tempfile.mkdtemp(dir=self.tmp.name))
                paths = write_experiment(root, text=valid_record(Supersedes=value))
                experiments = evidence_lint.collect_experiments(paths)
                self.assertEqual(evidence_lint.check_experiments(root, experiments), [])

    def test_supersedes_prose_with_no_record_id_is_rejected(self):
        paths = write_experiment(self.root, text=valid_record(Supersedes="the earlier run"))
        problems = self.check(paths)
        self.assertTrue(any("names no <record-id>" in p for p in problems), problems)

    def test_an_orphaned_snapshot_has_no_record_to_cite(self):
        paths = write_experiment(self.root)
        paths.append(f"sim/output-voltage-tc/netlist-snapshots/{OLDER_ID}.spice")
        problems = self.check(paths)
        self.assertTrue(any("orphan" in p for p in problems), problems)

    def test_an_orphaned_corner_directory_is_reported(self):
        paths = write_experiment(self.root)
        paths.append(f"sim/output-voltage-tc/corners/{OLDER_ID}/tt_27c_3.30v.log")
        problems = self.check(paths)
        self.assertTrue(any("orphan" in p for p in problems), problems)

    def test_a_head_record_with_a_partial_corner_set_is_rejected(self):
        """Regression for #98: a record whose own Result table (implicitly,
        its predecessor's full corner set) names more points than its
        `corners/<record-id>/` directory actually carries -- e.g. 4 of the
        12 logs a 4-groups-x-3-temperatures record like `mc-untrimmed`
        commits -- must fail, not merely "directory is non-empty"."""
        predecessor_logs = tuple(f"pt{i}_27c_3.30v.log" for i in range(12))
        partial_logs = predecessor_logs[:4]
        paths = write_experiment(self.root, record_id=OLDER_ID, logs=predecessor_logs)
        paths += write_experiment(
            self.root, text=valid_record(Supersedes=OLDER_ID), logs=partial_logs
        )
        problems = self.check(paths)
        self.assertTrue(
            any(
                "holds 4 log(s), fewer than its Supersedes predecessor" in p
                for p in problems
            ),
            problems,
        )

    def test_a_head_record_with_at_least_as_many_logs_as_its_predecessor_passes(self):
        predecessor_logs = tuple(f"pt{i}_27c_3.30v.log" for i in range(12))
        paths = write_experiment(self.root, record_id=OLDER_ID, logs=predecessor_logs)
        paths += write_experiment(
            self.root, text=valid_record(Supersedes=OLDER_ID), logs=predecessor_logs
        )
        self.assertEqual(self.check(paths), [])

    def test_a_superseded_records_partial_corner_set_is_not_rechecked(self):
        """Once a later record supersedes a partial-corner-set record, that
        record is no longer the current head -- readers follow the chain to
        the new head for self-supporting evidence, and the older record's
        already-committed shortfall cannot be fixed in place (append-only).
        The full-corner-set head must still pass on its own."""
        newer_id = "20260801-120000-abc1234"
        oldest_logs = tuple(f"pt{i}_27c_3.30v.log" for i in range(12))
        partial_logs = oldest_logs[:4]
        paths = write_experiment(self.root, record_id="20260731-000000-0000000", logs=oldest_logs)
        paths += write_experiment(
            self.root,
            record_id=OLDER_ID,
            text=valid_record(OLDER_ID, Supersedes="20260731-000000-0000000"),
            logs=partial_logs,
        )
        paths += write_experiment(
            self.root,
            record_id=newer_id,
            text=valid_record(newer_id, Supersedes=OLDER_ID),
            logs=oldest_logs,
        )
        problems = self.check(paths)
        self.assertFalse(
            any("fewer than its Supersedes predecessor" in p for p in problems), problems
        )

    def test_non_evidence_paths_are_ignored(self):
        paths = write_experiment(self.root)
        paths += ["sim/harness/report.py", "sim/README.md", "README.md"]
        self.assertEqual(self.check(paths), [])


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class AppendOnlyTests(unittest.TestCase):
    """The half of the checker that git, not the filesystem, can answer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.git("init", "--quiet")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        write_experiment(self.root)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "seed evidence")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *args: str):
        return subprocess.run(
            ("git", *args),
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def check(self):
        problems, skipped = evidence_lint.check_append_only(self.root, self.base)
        self.assertIsNone(skipped)
        return [str(p) for p in problems]

    def test_an_unchanged_tree_passes(self):
        self.assertEqual(self.check(), [])

    def test_adding_a_new_record_is_allowed(self):
        write_experiment(self.root, record_id=OLDER_ID)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "add a second record")
        self.assertEqual(self.check(), [])

    def test_editing_a_committed_record_is_rejected(self):
        record = self.root / "sim/output-voltage-tc/records" / f"{RECORD_ID}.md"
        record.write_text(record.read_text() + "\n- **Note**: typo fix\n")
        problems = self.check()
        self.assertTrue(any("modified since" in p for p in problems), problems)

    def test_deleting_a_corner_log_is_rejected(self):
        log = self.root / "sim/output-voltage-tc/corners" / RECORD_ID / "tt_27c_3.30v.log"
        log.unlink()
        problems = self.check()
        self.assertTrue(any("deleted since" in p for p in problems), problems)

    def test_deleting_a_netlist_snapshot_is_rejected(self):
        snapshot = self.root / "sim/output-voltage-tc/netlist-snapshots" / f"{RECORD_ID}.spice"
        snapshot.unlink()
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "drop a snapshot")
        problems = self.check()
        self.assertTrue(any("deleted since" in p for p in problems), problems)

    def test_renaming_a_record_is_rejected(self):
        records = self.root / "sim/output-voltage-tc/records"
        (records / f"{RECORD_ID}.md").rename(records / f"{OLDER_ID}.md")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "rename a record")
        problems = self.check()
        self.assertTrue(any("deleted since" in p for p in problems), problems)

    def test_non_evidence_files_under_sim_may_change_freely(self):
        harness = self.root / "sim" / "harness"
        harness.mkdir(parents=True, exist_ok=True)
        (harness / "report.py").write_text("# v1\n")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "add a harness module")
        (harness / "report.py").write_text("# v2\n")
        self.assertEqual(self.check(), [])

    def test_an_unresolvable_base_ref_skips_rather_than_failing(self):
        problems, skipped = evidence_lint.check_append_only(self.root, "origin/nope")
        self.assertEqual(problems, [])
        self.assertIsNotNone(skipped)

    def test_a_directory_outside_git_skips(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        problems, skipped = evidence_lint.check_append_only(outside, "origin/main")
        self.assertEqual(problems, [])
        self.assertIn("not a git checkout", skipped)


class CliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = evidence_lint.main(list(argv))
        return code, buffer.getvalue()

    def test_the_committed_corpus_passes_end_to_end(self):
        """The acceptance bar from the issue: zero failures on the real tree."""
        code, out = self.run_cli("--root", str(REPO_ROOT))
        self.assertEqual(code, 0, out)
        self.assertIn("sim/smoke-bias/records/", out)

    def test_a_broken_tree_exits_non_zero(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_experiment(root, text=valid_record(Result=""), logs=("oops.log",))
        code, out = self.run_cli("--root", str(root), "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("**Result** is empty", out)
        self.assertIn("does not parse", out)

    def test_require_append_only_turns_a_skip_into_a_failure(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_experiment(root)
        code, out = self.run_cli("--root", str(root), "--quiet")
        self.assertEqual(code, 0, out)
        self.assertIn("SKIP: append-only check", out)
        code, out = self.run_cli("--root", str(root), "--quiet", "--require-append-only")
        self.assertEqual(code, 1)
        self.assertIn("could not run", out)


if __name__ == "__main__":
    unittest.main()
