#!/usr/bin/env python3
"""Tests for scripts/check_artifact_manifests.py. stdlib + git only."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_artifact_manifests", REPO / "scripts" / "check_artifact_manifests.py"
)
cam = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cam)


def entry(data: bytes = b"log", **over) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    e = {"name": "sim/b/corners/r/c.log", "size": len(data), "sha256": digest,
         "uri": f"artifact:evidence/x/{digest[:2]}/{digest}"}
    e.update(over)
    return e


class Checker(unittest.TestCase):
    def _repo(self, tmp: str, manifest, tracked: dict[str, bytes] | None = None) -> Path:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        mdir = root / "manifests" / "artifacts"
        mdir.mkdir(parents=True)
        text = manifest if isinstance(manifest, str) else json.dumps(manifest)
        (mdir / "b-r.manifest.json").write_text(text)
        for rel, data in (tracked or {}).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        return root

    def run_check(self, manifest, tracked=None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            return cam.check(self._repo(tmp, manifest, tracked))

    def test_clean(self):
        self.assertEqual(self.run_check({"schema_version": 1, "entries": [entry()]}), [])

    def test_no_manifests_dir_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cam.check(Path(tmp)), [])

    def test_bad_json(self):
        self.assertTrue(any("not valid JSON" in p for p in self.run_check("{nope")))

    def test_bad_schema(self):
        self.assertTrue(self.run_check({"entries": [entry()]}))  # no schema_version
        self.assertTrue(self.run_check({"schema_version": 1, "entries": []}))
        self.assertTrue(self.run_check({"schema_version": 1, "entries": [{"name": "x"}]}))

    def test_non_artifact_uri(self):
        for uri in ("s3://bucket/key", "https://x/y", "file:///etc/passwd"):
            problems = self.run_check({"schema_version": 1, "entries": [entry(uri=uri)]})
            self.assertTrue(problems, uri)

    def test_bad_digest_and_size(self):
        self.assertTrue(self.run_check({"schema_version": 1, "entries": [entry(sha256="abc")]}))
        self.assertTrue(self.run_check({"schema_version": 1, "entries": [entry(size=-1)]}))

    def test_stored_bytes_also_tracked(self):
        problems = self.run_check(
            {"schema_version": 1, "entries": [entry(b"dup")]},
            tracked={"sim/b/corners/r/c.log": b"dup"},
        )
        self.assertTrue(any("also tracked" in p for p in problems))

    def test_same_size_different_bytes_ok(self):
        self.assertEqual(
            self.run_check(
                {"schema_version": 1, "entries": [entry(b"aaa")]},
                tracked={"other.txt": b"bbb"},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
