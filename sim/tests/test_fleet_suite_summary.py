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


def _frozen_datetime():
    """A stand-in for the ``datetime`` module whose ``now`` never advances, so
    every writer in a test mints the same ``<timestamp>-<sha>`` base name."""
    import datetime as dt

    class _FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return dt.datetime(2026, 11, 20, 12, 0, 0, tzinfo=tz)

    class _Frozen:
        datetime = _FrozenDateTime
        timezone = dt.timezone

    return _Frozen


class MainWriteTests(unittest.TestCase):
    """The fleet summary shares ``sim/suite/summaries`` with the local suite
    (#533): same-second reruns and a simultaneous local run all keep their
    payloads, and --no-write leaves nothing behind."""

    def _run_main(self, payload: str, out_dir: Path, argv: list[str]) -> int:
        import contextlib
        import io
        from types import SimpleNamespace
        from unittest import mock

        from harness import report as harness_report

        done = SimpleNamespace(exit_code=0)
        with mock.patch.object(fss, "bench_from_record", mock.Mock(return_value=object())), \
                mock.patch.object(fss.combined_verdict, "load",
                                  mock.Mock(return_value=SimpleNamespace(status="PASS"))), \
                mock.patch.object(fss, "assess", mock.Mock(return_value=done)), \
                mock.patch.object(fss, "render_summary", mock.Mock(return_value=payload)), \
                mock.patch.object(fss, "SUMMARY_DIR", out_dir), \
                mock.patch.object(fss, "REPO", out_dir), \
                mock.patch.object(fss, "dt", _frozen_datetime()), \
                mock.patch.object(harness_report, "git_provenance",
                                  mock.Mock(return_value={"short": "deadbee"})), \
                contextlib.redirect_stdout(io.StringIO()):
            return fss.main(["--corner-record", "c1", "--mc-record", "m1", *argv])

    def test_three_same_second_reruns_keep_every_summary(self):
        with tempfile.TemporaryDirectory() as d:
            for payload in ("FLEET-A", "FLEET-B", "FLEET-C"):
                self.assertEqual(self._run_main(payload, Path(d), []), 0)
            files = {p.name: p.read_text() for p in Path(d).iterdir()}
        self.assertEqual(
            set(files),
            {"20261120-120000-deadbee.md", "20261120-120000-deadbee-1.md",
             "20261120-120000-deadbee-2.md"},
        )
        self.assertEqual(set(files.values()), {"FLEET-A", "FLEET-B", "FLEET-C"})

    def test_no_write_leaves_no_summary_behind(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run_main("FLEET-A", Path(d), ["--no-write"]), 0)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_simultaneous_local_and_fleet_writers_keep_both_summaries(self):
        import contextlib
        import io
        import threading
        from types import SimpleNamespace
        from unittest import mock

        from harness import report as harness_report
        from suite import analysis
        from suite.cli import BenchRun

        tt = "tt_27c_3.30v"

        def fake_run(slug, lines, extra, quiet=False, expected_corners=None):
            samples = {tt: {"iq_ua": 40.0, "vref": 1.2}}
            bench = BenchRun(slug=slug, lines=lines, status="ok", returncode=0,
                             samples=samples, expected_corners=[tt])
            bench.outcomes = [analysis.evaluate_line(l, samples, [tt]) for l in lines]
            return bench

        def local(out_dir, errors):
            from suite import cli
            try:
                with mock.patch.object(cli, "run_bench", fake_run), \
                        mock.patch.object(cli, "render_summary",
                                          mock.Mock(return_value="LOCAL PAYLOAD")), \
                        mock.patch.object(cli, "SUMMARY_DIR", out_dir), \
                        mock.patch.object(cli, "REPO_ROOT", out_dir), \
                        mock.patch.object(cli, "_dt", _frozen_datetime()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    cli.main(["--only", "iq", "--quiet"])
            except Exception as exc:  # pragma: no cover - surfaced via assert below
                errors.append(exc)

        def fleet(out_dir, errors):
            try:
                with mock.patch.object(fss, "bench_from_record",
                                       mock.Mock(return_value=object())), \
                        mock.patch.object(fss.combined_verdict, "load",
                                          mock.Mock(return_value=SimpleNamespace(status="PASS"))), \
                        mock.patch.object(fss, "assess",
                                          mock.Mock(return_value=SimpleNamespace(exit_code=0))), \
                        mock.patch.object(fss, "render_summary",
                                          mock.Mock(return_value="FLEET PAYLOAD")), \
                        mock.patch.object(fss, "SUMMARY_DIR", out_dir), \
                        mock.patch.object(fss, "REPO", out_dir), \
                        mock.patch.object(fss, "dt", _frozen_datetime()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    fss.main(["--corner-record", "c1", "--mc-record", "m1"])
            except Exception as exc:  # pragma: no cover - surfaced via assert below
                errors.append(exc)

        with tempfile.TemporaryDirectory() as d:
            errors: list[Exception] = []
            with mock.patch.object(harness_report, "git_provenance",
                                   mock.Mock(return_value={"short": "deadbee"})):
                threads = [
                    threading.Thread(target=local, args=(Path(d), errors)),
                    threading.Thread(target=fleet, args=(Path(d), errors)),
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
            self.assertEqual(errors, [])
            files = {p.name: p.read_text() for p in Path(d).iterdir()}
        self.assertEqual(len(files), 2)
        self.assertEqual(set(files.values()), {"LOCAL PAYLOAD", "FLEET PAYLOAD"})


if __name__ == "__main__":
    unittest.main()
