#!/usr/bin/env python3
"""Unit tests for the T1 signoff validator. No klt, no network, no PDK.

    python3 -m unittest discover -s signoff/tests -v

Every test builds a throwaway repo layout in a temp dir and points the
checker's module-level path constants at it, so the committed manifest, pins
and reports are never read or modified. ``subprocess.run`` is mocked for the
klt re-grade.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIGNOFF_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIGNOFF_DIR))

import check_signoff as cs  # noqa: E402

ENVELOPE = "evidence/env.json"
RECORD = "20260101-000000-abcdef0.signoff.json"


def build_report(manifest_evidence: dict, count: int = 11) -> dict:
    items = []
    for item_id in range(1, count + 1):
        entry = manifest_evidence.get(str(item_id))
        if entry:
            items.append({
                "tier": "T1", "id": item_id, "status": "met", "reason": "ok",
                "citation": {
                    "file": entry["file"],
                    "command": "cmd",
                    "kind": "sim",
                    "check_status": "pass",
                    "content_hash": entry["content_hash"],
                    "coverage": {"corners": 3},
                    "body_bias": {"vbs": 0},
                },
            })
        else:
            items.append({"tier": "T1", "id": item_id,
                          "status": "no_evidence", "reason": "none"})
    met = sum(1 for i in items if i["status"] == "met")
    return {"block": "bg", "kind": "analog", "tier": None,
            "t1_item_count": count, "t1_met_count": met, "items": items}


class FixtureCase(unittest.TestCase):
    """A valid mini-repo in a temp dir with the checker's paths patched."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.signoff = self.root / "signoff"
        self.reports = self.signoff / "reports"
        self.reports.mkdir(parents=True)
        (self.root / "evidence").mkdir()
        self.artifact = self.root / "evidence" / "layout.gds"
        self.artifact.write_bytes(b"layout-bytes")
        (self.root / ENVELOPE).write_text("{}", encoding="utf-8")
        self.pin = cs.sha256_file(self.artifact)

        self.manifest = {
            "block": "bg", "kind": "analog",
            "evidence": {"1": {"file": ENVELOPE, "content_hash": self.pin}},
        }
        self.inputs = {"inputs": {"1": "evidence/layout.gds"}}
        self.report = build_report(self.manifest["evidence"])
        self.write_all()

        for name, value in {
            "REPO_ROOT": self.root,
            "SIGNOFF_DIR": self.signoff,
            "MANIFEST": self.signoff / "block-manifest.json",
            "PINNED_INPUTS": self.signoff / "pinned-inputs.json",
            "KLT_PIN": self.signoff / "klt-pin.txt",
            "REPORTS_DIR": self.reports,
        }.items():
            patcher = mock.patch.object(cs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_all(self) -> None:
        (self.signoff / "block-manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8")
        (self.signoff / "pinned-inputs.json").write_text(
            json.dumps(self.inputs), encoding="utf-8")
        (self.reports / RECORD).write_text(
            json.dumps(self.report), encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cs.main(list(args))
        return code, out.getvalue()

    def assertFails(self, failures: cs.Failures, *needles: str) -> None:
        self.assertTrue(failures, "expected the check to fail")
        text = "\n".join(failures.messages)
        for needle in needles:
            self.assertIn(needle, text)


class QuietCase(FixtureCase):
    def run(self, result=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)


class ManifestTests(QuietCase):
    def check(self) -> cs.Failures:
        failures = cs.Failures()
        cs.check_manifest(self.manifest, failures)
        return failures

    def test_valid_passes(self):
        self.assertFalse(self.check())
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_unrecognized_evidence_keys(self):
        for key in ("0", "12", "foo", "1.digital", "3.mixed"):
            with self.subTest(key=key):
                self.manifest["evidence"] = {
                    key: {"file": ENVELOPE, "content_hash": self.pin}}
                self.assertFails(self.check(), repr(key))

    def test_partition_key_allowed_only_for_mixed_signal(self):
        self.manifest["evidence"] = {
            "1.analog": {"file": ENVELOPE, "content_hash": self.pin}}
        self.assertFails(self.check(), "per-partition")
        self.manifest["kind"] = "mixed-signal"
        self.assertFalse(self.check())

    def test_bad_block_and_kind(self):
        self.manifest["block"] = "  "
        self.manifest["kind"] = "quantum"
        self.assertFails(self.check(), "`block` must be", "`kind` must be")

    def test_missing_citations(self):
        cases = {
            "bare path": ("evidence/env.json", "must be an object"),
            "no hash": ({"file": ENVELOPE}, "pins no `content_hash`"),
            "missing file": ({"file": "evidence/gone.json",
                              "content_hash": self.pin}, "missing file"),
            "no file or command": ({"content_hash": self.pin},
                                   "neither a `file` nor a `command`"),
        }
        for name, (entry, needle) in cases.items():
            with self.subTest(name):
                self.manifest["evidence"] = {"1": entry}
                self.assertFails(self.check(), needle)

    def test_cited_file_not_json(self):
        (self.root / ENVELOPE).write_text("{nope", encoding="utf-8")
        self.assertFails(self.check(), "not valid JSON")

    def test_non_object_manifest_and_evidence(self):
        failures = cs.Failures()
        self.assertEqual(cs.check_manifest([], failures), {})
        self.assertFails(failures, "not a JSON object")
        self.manifest["evidence"] = []
        self.assertFails(self.check(), "`evidence` must be an object")


class PinTests(QuietCase):
    def check(self) -> cs.Failures:
        failures = cs.Failures()
        cs.check_pins(self.manifest["evidence"], failures)
        return failures

    def test_matching_pin_passes(self):
        self.assertFalse(self.check())

    def test_changed_artifact_fails(self):
        self.artifact.write_bytes(b"regenerated")
        self.assertFails(self.check(), "has changed since", self.pin)

    def test_orphan_pin_fails(self):
        self.inputs["inputs"]["7"] = "evidence/layout.gds"
        self.write_all()
        self.assertFails(self.check(), "inputs['7']", "does not cite")

    def test_unrecorded_artifact_fails(self):
        self.inputs["inputs"] = {}
        self.write_all()
        self.assertFails(self.check(), "no artifact recorded")

    def test_missing_artifact_fails(self):
        self.artifact.unlink()
        self.assertFails(self.check(), "does not exist")

    def test_missing_or_malformed_pinned_inputs(self):
        (self.signoff / "pinned-inputs.json").unlink()
        self.assertFails(self.check(), "cannot read")
        (self.signoff / "pinned-inputs.json").write_text("[", encoding="utf-8")
        self.assertFails(self.check(), "not valid JSON")
        self.inputs = {"inputs": []}
        self.write_all()
        self.assertFails(self.check(), "`inputs` must be an object")

    def test_non_object_pinned_inputs_document(self):
        (self.signoff / "pinned-inputs.json").write_text("[]", encoding="utf-8")
        self.assertFails(self.check(), "pinned-inputs")


class LatestReportTests(QuietCase):
    def test_selects_lexically_latest(self):
        newer = "20260202-000000-abcdef0.signoff.json"
        (self.reports / newer).write_text("{}", encoding="utf-8")
        failures = cs.Failures()
        self.assertEqual(cs.latest_report(failures).name, newer)
        self.assertFalse(failures)

    def test_missing_directory(self):
        for p in self.reports.iterdir():
            p.unlink()
        self.reports.rmdir()
        failures = cs.Failures()
        self.assertIsNone(cs.latest_report(failures))
        self.assertFails(failures, "no report directory")

    def test_empty_directory(self):
        (self.reports / RECORD).unlink()
        failures = cs.Failures()
        self.assertIsNone(cs.latest_report(failures))
        self.assertFails(failures, "holds no *.signoff.json")

    def test_bad_record_id_is_flagged(self):
        (self.reports / "latest.signoff.json").write_text("{}", encoding="utf-8")
        failures = cs.Failures()
        cs.latest_report(failures)
        self.assertFails(failures, "latest.signoff.json", "record id")

    def test_main_fails_on_malformed_and_missing_reports(self):
        (self.reports / RECORD).write_text("{broken", encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", out)
        (self.reports / RECORD).unlink()
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("holds no *.signoff.json", out)


class ReportConsistencyTests(QuietCase):
    def check(self) -> cs.Failures:
        failures = cs.Failures()
        cs.check_report(self.report, self.manifest,
                        self.manifest["evidence"], failures)
        return failures

    def test_consistent_report_passes(self):
        self.assertFalse(self.check())

    def test_non_object_report(self):
        self.report = []
        self.assertFails(self.check(), "not a JSON object")

    def test_block_and_kind_mismatch(self):
        self.report["block"] = "other"
        self.report["kind"] = "digital"
        self.assertFails(self.check(), "block 'other'", "kind 'digital'")

    def test_empty_items(self):
        self.report["items"] = []
        self.assertFails(self.check(), "`items` is missing or empty")

    def test_inconsistent_item_count(self):
        self.report["t1_item_count"] = 12
        self.assertFails(self.check(), "t1_item_count 12 != the 11")

    def test_inconsistent_met_count(self):
        self.report["t1_met_count"] = 5
        self.assertFails(self.check(), "t1_met_count 5 != the 1")

    def test_old_checklist_rejected(self):
        self.report = build_report(self.manifest["evidence"], count=10)
        self.assertFails(self.check(), "only 10 T1 items", "klt pin is behind")

    def test_cited_item_not_rendered(self):
        self.report["items"] = [i for i in self.report["items"] if i["id"] != 1]
        self.report["t1_item_count"] = 10
        self.assertFails(self.check(), "cites item 1, which the report")

    def test_unsupported_met_citations(self):
        # met row with no manifest citation
        self.report["items"][1]["status"] = "met"
        self.report["items"][1]["citation"] = {}
        self.report["t1_met_count"] = 2
        self.assertFails(self.check(), "item 2 is `met` but the manifest cites nothing")

    def test_met_citation_file_and_hash_mismatch(self):
        cite = self.report["items"][0]["citation"]
        cite["file"] = "evidence/other.json"
        cite["content_hash"] = "sha256:dead"
        self.assertFails(self.check(), "cites 'evidence/other.json'",
                         "citation hash 'sha256:dead'")

    def test_main_reports_inconsistent_record(self):
        self.report["t1_met_count"] = 0
        self.write_all()
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("t1_met_count 0", out)


class KltCommandTests(QuietCase):
    def test_env_override(self):
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": "foo  bar"}):
            self.assertEqual(cs.klt_command(), ["foo", "bar"])

    def test_default_uses_pin_even_with_path_klt(self):
        (self.signoff / "klt-pin.txt").write_text("abc123\n", encoding="utf-8")
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": ""}), \
                mock.patch.object(cs, "KLT_PIN", self.signoff / "klt-pin.txt"), \
                mock.patch.object(cs, "_which", side_effect=lambda b: f"/bin/{b}"):
            command = cs.klt_command()
        self.assertEqual(command[0], "uvx")
        self.assertIn("git+https://github.com/2AMLogic/klayout-tools@abc123", command)
        self.assertEqual(command[-1], "klt")

    def test_missing_uvx_fails_clearly_without_path_fallback(self):
        (self.signoff / "klt-pin.txt").write_text("abc123\n", encoding="utf-8")
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": ""}), \
                mock.patch.object(cs, "KLT_PIN", self.signoff / "klt-pin.txt"), \
                mock.patch.object(
                    cs, "_which", side_effect=lambda b: "/bin/klt" if b == "klt" else None
                ):
            with self.assertRaisesRegex(cs.KltUnavailable, "uvx not found"):
                cs.klt_command()

    def test_missing_pin_fails_clearly(self):
        (self.signoff / "klt-pin.txt").write_text("# only comments\n", encoding="utf-8")
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": ""}), \
                mock.patch.object(cs, "KLT_PIN", self.signoff / "klt-pin.txt"):
            with self.assertRaisesRegex(cs.KltUnavailable, "names no revision"):
                cs.klt_command()

    def test_regrade_reports_unavailable_as_failure(self):
        failures = cs.Failures()
        with mock.patch.object(cs, "klt_command", side_effect=cs.KltUnavailable("nope")):
            cs.run_klt({}, failures)
        self.assertTrue(failures)

    def test_pin_parsing_skips_comments(self):
        (self.signoff / "klt-pin.txt").write_text("# c\n\nabc123\n", encoding="utf-8")
        self.assertEqual(cs.klt_pin(), "abc123")


class RegradeTests(QuietCase):
    def completed(self, stdout="", returncode=0, stderr=""):
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def regrade(self, result=None, side_effect=None, fresh=None):
        if fresh is not None:
            result = self.completed(json.dumps(fresh))
        failures = cs.Failures()
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": "klt"}), \
                mock.patch.object(cs.subprocess, "run", return_value=result,
                                  side_effect=side_effect) as run:
            cs.run_klt(self.report, failures)
        self.run_mock = run
        return failures

    def fresh(self):
        return copy.deepcopy(self.report)

    def test_identical_grade_passes_and_command_shape(self):
        self.assertFalse(self.regrade(fresh=self.fresh()))
        args, kwargs = self.run_mock.call_args
        self.assertEqual(args[0], ["klt", "signoff", "--manifest",
                                   "signoff/block-manifest.json",
                                   "--format", "json"])
        self.assertEqual(kwargs["cwd"], str(self.root))

    def test_exit_codes_0_and_3_accepted(self):
        for code in (0, 3):
            with self.subTest(code=code):
                result = self.completed(json.dumps(self.fresh()), returncode=code)
                self.assertFalse(self.regrade(result))

    def test_other_exit_codes_rejected(self):
        for code in (1, 2, 127):
            with self.subTest(code=code):
                result = self.completed("", returncode=code, stderr="boom")
                self.assertFails(self.regrade(result), f"exited {code}", "boom")

    def test_invalid_json_rejected(self):
        self.assertFails(self.regrade(self.completed("not json")),
                         "stdout is not valid JSON")

    def test_timeout_rejected(self):
        failures = self.regrade(side_effect=subprocess.TimeoutExpired("klt", 900))
        self.assertFails(failures, "timed out")

    def test_missing_binary_rejected(self):
        failures = self.regrade(side_effect=FileNotFoundError("klt"))
        self.assertFails(failures, "could not run klt")

    def test_top_level_field_differences(self):
        fresh = self.fresh()
        fresh["tier"] = "T1"
        fresh["t1_met_count"] = 9
        self.assertFails(self.regrade(fresh=fresh),
                         "tier is now 'T1'", "t1_met_count is now 9")

    def test_status_difference(self):
        fresh = self.fresh()
        fresh["items"][0]["status"] = "unmet"
        self.assertFails(self.regrade(fresh=fresh),
                         "item 1 status is now 'unmet'")

    def test_reason_difference(self):
        fresh = self.fresh()
        fresh["items"][1]["reason"] = "changed"
        self.assertFails(self.regrade(fresh=fresh),
                         "item 2 reason is now 'changed'")

    def test_citation_hash_difference(self):
        fresh = self.fresh()
        fresh["items"][0]["citation"]["content_hash"] = "sha256:new"
        self.assertFails(self.regrade(fresh=fresh), "citation.content_hash")

    def test_coverage_difference(self):
        fresh = self.fresh()
        fresh["items"][0]["citation"]["coverage"] = {"corners": 1}
        failures = self.regrade(fresh=fresh)
        self.assertFails(failures, "citation.coverage changed")
        self.assertNotIn("body_bias", "\n".join(failures.messages))

    def test_body_bias_difference(self):
        fresh = self.fresh()
        fresh["items"][0]["citation"]["body_bias"] = {"vbs": -1}
        failures = self.regrade(fresh=fresh)
        self.assertFails(failures, "citation.body_bias changed")
        self.assertNotIn("citation.coverage", "\n".join(failures.messages))

    def test_item_present_in_only_one_report(self):
        fresh = self.fresh()
        fresh["items"].pop()
        self.assertFails(self.regrade(fresh=fresh), "only one of the two")

    def test_main_run_klt_without_report(self):
        (self.reports / RECORD).unlink()
        code, out = self.run_main("--run-klt")
        self.assertEqual(code, 1)
        self.assertIn("no committed report to compare", out)


class MalformedShapeTests(QuietCase):
    """Garbage shapes must produce a failed verdict, never a traceback."""

    def test_report_items_not_objects(self):
        self.report["items"] = ["x", 3]
        failures = cs.Failures()
        cs.check_report(self.report, self.manifest, self.manifest["evidence"], failures)
        self.assertTrue(failures)

    def test_regrade_non_object_json(self):
        failures = cs.Failures()
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": "klt"}), \
                mock.patch.object(cs.subprocess, "run", return_value=
                                  subprocess.CompletedProcess([], 0, "[]", "")):
            cs.run_klt(self.report, failures)
        self.assertFails(failures, "not a JSON object")

    def test_main_with_non_object_pinned_inputs(self):
        (self.signoff / "pinned-inputs.json").write_text("[]", encoding="utf-8")
        code, _ = self.run_main()
        self.assertEqual(code, 1)


class AttestationTests(QuietCase):
    """`klt signoff --attest` envelopes: offline drift gate and `--check`."""

    def setUp(self) -> None:
        super().setUp()
        (self.root / "docs").mkdir()
        self.hygiene = self.root / "docs" / "README.md"
        self.hygiene.write_bytes(b"readme-bytes")
        self.envelope = {
            "kind": "generic", "status": "pass", "t1_item": 10,
            "attestation": {"checks": [
                {"check": "present", "role": "hygiene", "path": "docs/README.md",
                 "passed": True, "content_hash": cs.sha256_file(self.hygiene)},
            ]},
            "provenance": {"input": {
                "path": {"path": "signoff/inventories/item10.json", "scope": "repo"},
                "content_hash": "sha256:00"}},
        }
        self.cited = "signoff/attestations/item10.json"
        (self.signoff / "attestations").mkdir()
        self.evidence = {"10": {"file": self.cited, "content_hash": "sha256:00"}}
        self.write_envelope()

    def write_envelope(self) -> None:
        (self.root / self.cited).write_text(json.dumps(self.envelope), encoding="utf-8")

    def offline(self) -> cs.Failures:
        failures = cs.Failures()
        with mock.patch.object(cs, "_tracked_testbench_files", return_value=None):
            cs.check_attestations(self.evidence, failures)
        return failures

    def test_unchanged_files_pass(self):
        self.assertFalse(self.offline())

    def test_changed_inventoried_file_fails(self):
        self.hygiene.write_bytes(b"edited")
        self.assertFails(self.offline(), "docs/README.md has changed")

    def test_skipped_while_attesting(self):
        self.hygiene.write_bytes(b"edited")
        with mock.patch.dict("os.environ", {"SIGNOFF_ATTESTING": "1"}):
            self.assertFalse(self.offline())

    def test_deleted_inventoried_file_fails(self):
        self.hygiene.unlink()
        self.assertFails(self.offline(), "no longer exists")

    def test_failing_envelope_fails(self):
        self.envelope["status"] = "fail"
        self.write_envelope()
        self.assertFails(self.offline(), "not 'pass'")

    def test_envelope_cited_for_wrong_item_fails(self):
        self.evidence = {"9": self.evidence["10"]}
        self.assertFails(self.offline(), "attests item 10, cited for item 9")

    def test_untracked_testbench_in_item9_inventory_fails(self):
        self.envelope["t1_item"] = 9
        self.write_envelope()
        self.evidence = {"9": self.evidence["10"]}
        failures = cs.Failures()
        with mock.patch.object(cs, "_tracked_testbench_files",
                               return_value={"docs/README.md", "sim/new/testbench/tb.json"}):
            cs.check_attestations(self.evidence, failures)
        self.assertFails(failures, "sim/new/testbench/tb.json is not in")

    def check_run(self, returncode: int, stdout: str = "") -> cs.Failures:
        failures = cs.Failures()
        result = subprocess.CompletedProcess([], returncode, stdout, "")
        with mock.patch.dict("os.environ", {"KLT_SIGNOFF_CMD": "klt"}), \
                mock.patch.object(cs.subprocess, "run", return_value=result) as run:
            cs.run_attestations(self.evidence, failures)
        self.run_mock = run
        return failures

    def test_check_command_shape_and_match(self):
        self.assertFalse(self.check_run(0, json.dumps({"status": "match"})))
        self.assertEqual(self.run_mock.call_args[0][0], [
            "klt", "signoff", "--attest", "10", "--inventory",
            "signoff/inventories/item10.json", "--check", self.cited,
            "--format", "json"])

    def test_check_reports_unavailable_klt_as_failure(self):
        failures = cs.Failures()
        with mock.patch.object(cs, "klt_command", side_effect=cs.KltUnavailable("nope")), \
                mock.patch.object(cs.subprocess, "run") as run:
            cs.run_attestations(self.evidence, failures)
        run.assert_not_called()
        self.assertFails(failures, "nope")

    def test_flipped_check_outcome_fails(self):
        drifted = {"status": "drifted", "fresh_status": "fail",
                   "drift": [{"path": "attestation.checks[3].passed"}]}
        self.assertFails(self.check_run(3, json.dumps(drifted)),
                         "exited 3", "attestation.checks[3].passed")

    def test_unreadable_check_output_still_fails(self):
        self.assertFails(self.check_run(1, "not json"), "exited 1")


if __name__ == "__main__":
    unittest.main()
