#!/usr/bin/env python3
"""Unit tests for ``layout/common/report_id.py`` (gf180-bandgap#138).

No ``git`` binary mocking needed for the ``record_id`` glob behaviour --
those tests work directly against a real temp directory. ``short_sha``/
``_git`` are exercised against this checkout's real ``git`` (always present
in this repo, per ``sim/harness/report.py``'s own precedent) and against a
non-repo directory to cover the "no commit" fallback.

    python3 -m unittest layout.common.test_report_id -v
    # or, from this directory:
    python3 -m unittest test_report_id -v
"""

from __future__ import annotations

import datetime as _dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report_id  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


class ShortShaTests(unittest.TestCase):
    def test_returns_seven_char_sha_in_this_repo(self) -> None:
        sha = report_id.short_sha(REPO_ROOT)
        self.assertEqual(len(sha), 7)
        self.assertNotEqual(sha, "unknown")

    def test_returns_unknown_outside_a_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(report_id.short_sha(Path(tmp)), "unknown")


class RecordIdTests(unittest.TestCase):
    """Append-only id allocation: probes ``<candidate>.*``, not one suffix."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.reports_dir = Path(self._tmp.name)
        self.when = _dt.datetime(2026, 8, 14, 12, 0, 0, tzinfo=_dt.timezone.utc)

    def test_first_call_mints_the_requested_timestamp(self) -> None:
        candidate = report_id.record_id(self.reports_dir, self.when, "abc1234")
        self.assertEqual(candidate, "20260814-120000-abc1234")

    def test_advances_past_a_claimed_id_regardless_of_suffix(self) -> None:
        """A single-suffix caller (run_drc.py/run_extract.py's own usage) is
        still safe: the glob still matches its one file extension."""
        (self.reports_dir / "20260814-120000-abc1234.drc.json").write_text("{}")
        candidate = report_id.record_id(self.reports_dir, self.when, "abc1234")
        self.assertEqual(candidate, "20260814-120001-abc1234")

    def test_advances_past_a_claimed_id_under_a_different_suffix(self) -> None:
        """The multi-suffix case (run_lvs.py --engine netgen, gf180-bandgap#109):
        an id claimed under one suffix must not be reused under another --
        the strict-superset reason the glob form exists at all."""
        (self.reports_dir / "20260814-120000-abc1234.lvs-netgen.json").write_text("{}")
        candidate = report_id.record_id(self.reports_dir, self.when, "abc1234")
        self.assertEqual(candidate, "20260814-120001-abc1234")

    def test_keeps_advancing_until_a_free_id_is_found(self) -> None:
        for offset in range(3):
            stamp = self.when + _dt.timedelta(seconds=offset)
            candidate = f"{stamp.strftime('%Y%m%d-%H%M%S')}-abc1234"
            (self.reports_dir / f"{candidate}.extract.json").write_text("{}")
        candidate = report_id.record_id(self.reports_dir, self.when, "abc1234")
        self.assertEqual(candidate, "20260814-120003-abc1234")

    def test_never_mutates_the_caller_supplied_datetime(self) -> None:
        """``when`` is advanced on a local copy inside the loop, not the
        caller's own object -- a caller that reuses ``when`` after the call
        (e.g. to log the original request time) must see it unchanged."""
        (self.reports_dir / "20260814-120000-abc1234.drc.json").write_text("{}")
        report_id.record_id(self.reports_dir, self.when, "abc1234")
        self.assertEqual(self.when, _dt.datetime(2026, 8, 14, 12, 0, 0, tzinfo=_dt.timezone.utc))


if __name__ == "__main__":
    unittest.main()
