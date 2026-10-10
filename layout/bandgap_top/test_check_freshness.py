#!/usr/bin/env python3
"""Tests for ``check_freshness.py`` (gf180-bandgap#308).

Without klayout the module skips (the stdlib-only ``test`` CI job runs every
layout test). With ``REQUIRE_KLAYOUT=1`` -- set by the ``signoff`` job, which
installs klayout via klt -- a missing klayout is an ImportError, never a skip:

    REQUIRE_KLAYOUT=1 python3 -m unittest discover -s layout/bandgap_top \
        -p 'test_check_freshness.py'

Locally without klayout use ``uv run --with klayout ...``.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import klayout.db  # noqa: F401
except ImportError:
    if os.environ.get("REQUIRE_KLAYOUT"):
        raise
    raise unittest.SkipTest("klayout not installed")

import check_freshness as cf  # noqa: E402
import generate  # noqa: E402


def _fresh_bytes() -> bytes:
    b, _ = generate.build()
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "x.gds"
        b.layout.write(str(p), generate.save_options())
        return p.read_bytes()


class FreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fresh = _fresh_bytes()

    def _file(self, data: bytes) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "bandgap_top.gds"
        p.write_bytes(data)
        return p

    def test_generation_is_deterministic(self):
        self.assertEqual(self.fresh, _fresh_bytes())

    def test_match_passes_and_does_not_mutate(self):
        p = self._file(self.fresh)
        before = hashlib.sha256(p.read_bytes()).hexdigest()
        code, msg = cf.check(p)
        self.assertEqual(code, 0, msg)
        self.assertEqual(before, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_one_byte_change_fails_with_remedy(self):
        data = bytearray(self.fresh)
        data[len(data) // 2] ^= 0x01
        p = self._file(bytes(data))
        code, msg = cf.check(p)
        self.assertEqual(code, 1)
        self.assertIn("STALE", msg)
        self.assertIn("generate.py", msg)
        self.assertIn("regenerate.sh", msg)
        self.assertLess(msg.index("generate.py"), msg.index("regenerate.sh"))
        self.assertEqual(p.read_bytes(), bytes(data))  # untouched

    def test_missing_file_fails(self):
        code, msg = cf.check(HERE / "does_not_exist.gds")
        self.assertEqual(code, 2)
        self.assertIn("not found", msg)

    def test_generation_failure_fails(self):
        p = self._file(self.fresh)
        with mock.patch.object(generate, "build", side_effect=RuntimeError("boom")):
            code, msg = cf.check(p)
        self.assertEqual(code, 2)
        self.assertIn("boom", msg)
        self.assertEqual(p.read_bytes(), self.fresh)

    def test_altered_generator_output_detected(self):
        p = self._file(self.fresh)
        real = generate.save_options

        def opts():
            o = real()
            o.dbu = 0.0005  # changes the serialized units
            return o

        with mock.patch.object(generate, "save_options", opts):
            code, _ = cf.check(p)
        self.assertEqual(code, 1)

    def test_temp_output_cleaned(self):
        p = self._file(self.fresh)
        created = []
        orig = tempfile.TemporaryDirectory

        class Spy(orig):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                created.append(self.name)

        with mock.patch.object(cf.tempfile, "TemporaryDirectory", Spy):
            cf.check(p)
        self.assertTrue(created)
        self.assertFalse(any(Path(c).exists() for c in created))

    def test_tracked_gds_not_mutated_by_default_check(self):
        tracked = cf.COMMITTED
        if not tracked.is_file():
            self.fail("committed GDS missing")
        before = tracked.read_bytes()
        cf.check()
        self.assertEqual(before, tracked.read_bytes())


if __name__ == "__main__":
    unittest.main()
