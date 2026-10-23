#!/usr/bin/env python3
"""Unit tests for the manifest-forward evidence store. No klt/broker needed.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_store import FakeStore  # noqa: E402
from harness import evidence_store as es  # noqa: E402

RID = "20261023-120000-abc1234"


class EvidenceRunTests(unittest.TestCase):
    def test_stage_put_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FakeStore()
            run = es.EvidenceRun("bench", RID, store=store, repo_root=root).start()
            (run.log_dir / "tt_27c_3.30v.log").write_text("hello\n")
            (run.log_dir / "ss_-40c_2.97v.log").write_text("")  # empty file
            entries = run.finalize()
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(e.uri.startswith("artifact:") for e in entries))
            self.assertFalse(run.manifest_path.exists())  # not until commit()
            run.commit()
            doc = json.loads(run.manifest_path.read_text())
            self.assertEqual(
                sorted(e["name"] for e in doc["entries"]),
                [f"sim/bench/corners/{RID}/ss_-40c_2.97v.log",
                 f"sim/bench/corners/{RID}/tt_27c_3.30v.log"],
            )
            self.assertIn("## Stored evidence", "\n".join(run.stored_lines()))

    def test_rerun_identical_object_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = es.EvidenceRun("bench", RID, store=FakeStore(), repo_root=Path(tmp)).start()
            (run.log_dir / "a.log").write_text("x")
            run.finalize()
            self.assertEqual(len(run.finalize()), 1)

    def test_nothing_staged_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = es.EvidenceRun("bench", RID, store=FakeStore(), repo_root=Path(tmp)).start()
            with self.assertRaises(es.StoreUnavailable):
                run.finalize()

    def test_preflight_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = es.EvidenceRun("bench", RID, store=FakeStore(fail_preflight="x"), repo_root=root)
            with self.assertRaises(es.StoreUnavailable):
                run.start()
            self.assertEqual(list(root.iterdir()), [])

    def test_commit_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = es.EvidenceRun("bench", RID, store=FakeStore(), repo_root=Path(tmp)).start()
            (run.log_dir / "a.log").write_text("x")
            run.finalize()
            run.manifest_path.parent.mkdir(parents=True)
            run.manifest_path.write_text("{}")
            with self.assertRaises(FileExistsError):
                run.commit()


class KltPreflightTests(unittest.TestCase):
    def _fake_klt(self, tmp: Path, code: int) -> str:
        path = tmp / "klt"
        path.write_text(f"#!/bin/sh\nexit {code}\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def test_broker_unset(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(es.BROKER_ENV, None)
            with self.assertRaises(es.StoreUnavailable) as cm:
                es.KltArtifactStore(self._fake_klt(Path(tmp), 0)).preflight()
            self.assertIn(es.BROKER_ENV, str(cm.exception))

    def test_put_verb_missing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {es.BROKER_ENV: "https://broker.invalid"}
        ):
            with self.assertRaises(es.StoreUnavailable):
                es.KltArtifactStore(self._fake_klt(Path(tmp), 2), reachable=lambda u: True).preflight()

    def test_klt_not_installed(self):
        with mock.patch.dict(os.environ, {es.BROKER_ENV: "https://broker.invalid"}):
            with self.assertRaises(es.StoreUnavailable):
                es.KltArtifactStore("/nonexistent/klt", reachable=lambda u: True).preflight()

    def test_broker_unreachable_does_not_leak_url(self):
        url = "https://secret-broker.invalid/x"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {es.BROKER_ENV: url}):
            with self.assertRaises(es.StoreUnavailable) as cm:
                es.KltArtifactStore(self._fake_klt(Path(tmp), 0), reachable=lambda u: False).preflight()
            self.assertNotIn("secret-broker", str(cm.exception))

    def test_ok(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {es.BROKER_ENV: "https://broker.invalid"}
        ):
            es.KltArtifactStore(self._fake_klt(Path(tmp), 0), reachable=lambda u: True).preflight()


if __name__ == "__main__":
    unittest.main()
