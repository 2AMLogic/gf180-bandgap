#!/usr/bin/env python3
"""Unit tests for ``layout/common/klt_runner.py`` (gf180-bandgap#548).

The contracts under test:

* ``find_klt`` prints the single install hint and returns ``None`` when klt
  is absent, and resolves ``shutil.which`` at *call time* -- the property
  that lets the runner tests keep patching the module-global ``shutil.which``
  (``layout/lvs/test_run_lvs.py``).
* ``run_dual_format`` fails closed: an unaccepted ``--format json`` exit code
  short-circuits before the text pass is ever launched, an unaccepted
  ``--format text`` exit code returns ``None`` so no caller can file a
  report pair from a half-finished run, and accepted non-zero exit codes
  (``3`` for drc/lvs, ``4`` for erc) complete like ``0``.

No ``klt`` binary required: ``subprocess.run`` is replaced by a recording
stand-in.

    python3 -m unittest layout.common.test_klt_runner -v
    # or, from this directory:
    python3 -m unittest test_klt_runner -v
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

# Load-bearing: sys.path[0] is this file's dir only under `python3 file.py`.
# Under the documented `python3 -m <dotted.module>` form it is the CWD. #479
sys.path.insert(0, str(Path(__file__).resolve().parent))

import klt_runner  # noqa: E402


class RecordingRun:
    """A ``subprocess.run`` stand-in that records invocations and answers
    from a per-format exit-code map."""

    def __init__(self, *, json_rc: int = 0, text_rc: int = 0,
                 json_out: str = '{"status": "ok"}',
                 json_err: str = "", text_out: str = "text report",
                 text_err: str = "") -> None:
        self.json_rc = json_rc
        self.text_rc = text_rc
        self.json_out = json_out
        self.json_err = json_err
        self.text_out = text_out
        self.text_err = text_err
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []

    def __call__(self, argv, **kwargs):  # noqa: ANN001 - subprocess.run signature
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        self.kwargs.append(kwargs)
        fmt = argv[-1]
        if fmt == "json":
            return subprocess.CompletedProcess(argv, self.json_rc, self.json_out, self.json_err)
        if fmt == "text":
            return subprocess.CompletedProcess(argv, self.text_rc, self.text_out, self.text_err)
        raise AssertionError(f"unexpected format: {argv}")


class FindKltTests(unittest.TestCase):
    def test_returns_the_resolved_path_quietly(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(
                klt_runner.find_klt(lambda _name: "/usr/bin/klt"), "/usr/bin/klt"
            )
        self.assertEqual(err.getvalue(), "")

    def test_missing_klt_prints_the_install_hint_and_returns_none(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIsNone(klt_runner.find_klt(lambda _name: None))
        self.assertIn("'klt' not found on PATH", err.getvalue())
        self.assertIn("uv tool install klayout-tools", err.getvalue())
        self.assertIn("layout/README.md", err.getvalue())

    def test_resolves_shutil_which_at_call_time(self) -> None:
        """The runner tests patch the module-global ``shutil.which``; the
        lookup must go through that same attribute when the caller passes no
        resolver, not a def-time default binding."""
        with mock.patch("shutil.which", return_value="/usr/bin/klt") as which:
            self.assertEqual(klt_runner.find_klt(), "/usr/bin/klt")
        which.assert_called_once_with("klt")


class RunDualFormatTests(unittest.TestCase):
    def _run(self, fake: RecordingRun, ok: tuple[int, ...] = (0, 3)):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = klt_runner.run_dual_format(
                ["klt", "drc", "a.gds", "--deck", "gf180mcu"],
                cwd=Path("/repo"),
                ok_exit_codes=ok,
                label="klt drc",
                run=fake,
            )
        return result, out.getvalue(), err.getvalue()

    def test_success_returns_both_procs_json_first(self) -> None:
        fake = RecordingRun(json_rc=0, text_rc=0)
        result, _, err = self._run(fake)
        json_proc, text_proc = result
        self.assertEqual(json_proc.returncode, 0)
        self.assertEqual(json_proc.stdout, '{"status": "ok"}')
        self.assertEqual(text_proc.returncode, 0)
        self.assertEqual(text_proc.stdout, "text report")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[0][-2:], ["--format", "json"])
        self.assertEqual(fake.calls[1][-2:], ["--format", "text"])
        self.assertEqual(err, "")

    def test_runs_through_subprocess_run_with_capture_kwargs(self) -> None:
        """The real (unstubbed) path delegates to ``subprocess.run`` with
        the same invocation contract the runners used inline -- resolved at
        call time so test patches keep working."""
        fake = RecordingRun()
        with mock.patch("subprocess.run", fake):
            klt_runner.run_dual_format(
                ["klt", "drc", "a.gds"],
                cwd=Path("/repo"),
                ok_exit_codes=(0,),
                label="klt drc",
            )
        self.assertEqual(
            fake.kwargs[0],
            {"cwd": Path("/repo"), "capture_output": True, "text": True, "check": False},
        )

    def test_accepts_nonzero_exit_codes_in_the_accepted_set(self) -> None:
        """``klt drc``/``klt lvs`` accept 3 and ``klt erc`` accepts 4 -- an
        accepted non-zero exit is a completed run whose report is evidence,
        not an error (each runner's docstring states its contract)."""
        for rc in (3, 4):
            with self.subTest(rc=rc):
                fake = RecordingRun(json_rc=rc, text_rc=rc)
                result, _, err = self._run(fake, ok=(0, 3, 4))
                self.assertIsNotNone(result)
                self.assertEqual(result[0].returncode, rc)
                self.assertEqual(result[1].returncode, rc)
                self.assertEqual(err, "")

    def test_json_failure_short_circuits_before_the_text_pass(self) -> None:
        """Pre-#548, run_drc.py/run_erc.py still launched the text pass
        before checking the json exit code; the helper must not."""
        fake = RecordingRun(json_rc=1, text_rc=0)
        result, _, err = self._run(fake)
        self.assertIsNone(result)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0][-2:], ["--format", "json"])
        self.assertIn("klt drc failed (exit 1)", err)

    def test_text_failure_fails_closed(self) -> None:
        """The fail-closed contract (#548): a text pass failure returns
        ``None``, so the caller writes neither report file."""
        fake = RecordingRun(json_rc=0, text_rc=1)
        result, _, err = self._run(fake)
        self.assertIsNone(result)
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("klt drc --format text failed (exit 1)", err)

    def test_failure_echoes_the_failing_pass_streams(self) -> None:
        """The failing pass's own stdout/stderr stay verbatim in the run's
        output -- an actionable ``klt`` error must not be swallowed."""
        fake = RecordingRun(json_rc=1, json_out="partial\n", json_err="boom\n")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertIsNone(
                klt_runner.run_dual_format(
                    ["klt", "erc", "a.gds", "spec.json"],
                    cwd=Path("/repo"),
                    ok_exit_codes=(0, 3, 4),
                    label="klt erc",
                    run=fake,
                )
            )
        self.assertIn("partial", out.getvalue())
        self.assertIn("boom", err.getvalue())
        self.assertIn("klt erc failed (exit 1)", err.getvalue())


if __name__ == "__main__":
    unittest.main()
