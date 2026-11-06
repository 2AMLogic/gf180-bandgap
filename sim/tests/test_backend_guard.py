"""Checks for sim/harness/backend.py (issue #219). No PDK/ngspice needed."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from harness import backend  # noqa: E402


def _env(value):
    env = {k: v for k, v in os.environ.items() if k != "KLT_SIM_BACKEND"}
    if value is not None:
        env["KLT_SIM_BACKEND"] = value
    return mock.patch.dict(os.environ, env, clear=True)


class GuardTests(unittest.TestCase):
    def test_allowed(self):
        for val, n in [(None, 81), ("local", 81), ("", 81), ("batch", 1), ("remote", 1)]:
            with self.subTest(val=val, n=n), _env(val):
                backend.guard_local_grid(n)

    def test_refused(self):
        for val in ("batch", "remote"):
            with self.subTest(val=val), _env(val):
                with self.assertRaises(SystemExit) as cm:
                    backend.guard_local_grid(81)
                self.assertIn("refusing", str(cm.exception))

    def test_override_to_local(self):
        with _env("batch"):
            with self.assertRaises(SystemExit):
                backend.guard_local_grid(81)
            os.environ["KLT_SIM_BACKEND"] = "local"
            backend.guard_local_grid(81)


class CliWiringTests(unittest.TestCase):
    def test_refusal_starts_no_ngspice(self):
        from harness import cli, runner
        args = cli.build_parser().parse_args(["smoke-bias", "--corner-set", "full", "--no-write"])
        with _env("batch"), \
                mock.patch.object(runner, "run_grid") as grid, \
                mock.patch("subprocess.run") as sp, \
                mock.patch.object(cli, "find_pdk", return_value=mock.MagicMock(variant="v", version="1", path="p")), \
                mock.patch.object(runner, "ngspice_version", return_value="ng"):
            with self.assertRaises(SystemExit) as cm:
                cli.run(args)
            self.assertIn("refusing", str(cm.exception))
            grid.assert_not_called()
            sp.assert_not_called()


class JobsDefaultTests(unittest.TestCase):
    def test_default_jobs(self):
        for cpus, want in [(1, 1), (2, 2), (16, 2), (None, 1)]:
            with self.subTest(cpus=cpus), mock.patch("os.cpu_count", return_value=cpus):
                self.assertEqual(backend.default_jobs(), want)


if __name__ == "__main__":
    unittest.main()
