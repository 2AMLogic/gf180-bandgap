"""Evidence-only suite roll-up (#239): no simulation, honest about gaps."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "tools"))

import fleet_suite_summary as fss  # noqa: E402
from suite.spec import by_slug  # noqa: E402


class BenchFromRecord(unittest.TestCase):
    def test_no_record_is_missing_not_substituted(self):
        b = fss.bench_from_record("iq", by_slug()["iq"], None)
        self.assertEqual(b.status, "missing")
        self.assertFalse(b.samples)
        self.assertFalse(b.available)

    def test_unknown_record_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            b = fss.bench_from_record("iq", by_slug()["iq"], "20990101-000000-0000000", Path(d))
        self.assertEqual(b.status, "missing")
        self.assertIn("20990101-000000-0000000", b.message)

    def test_record_without_logs_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "sim"
            (root / "iq" / "records").mkdir(parents=True)
            (root / "iq" / "corners" / "r1").mkdir(parents=True)
            (root / "iq" / "records" / "r1.md").write_text("# Record r1\n")
            b = fss.bench_from_record("iq", by_slug()["iq"], "r1", root)
        self.assertEqual(b.status, "error")


class ParseRecords(unittest.TestCase):
    def test_pairs(self):
        self.assertEqual(fss.parse_records(["psrr-dc=abc"]), {"psrr-dc": "abc"})

    def test_rejects_malformed_duplicate_and_unknown(self):
        for bad in (["psrr-dc"], ["psrr-dc=a", "psrr-dc=b"], ["nope=a"]):
            with self.assertRaises(SystemExit):
                fss.parse_records(bad)


if __name__ == "__main__":
    unittest.main()
