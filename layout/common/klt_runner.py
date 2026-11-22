#!/usr/bin/env python3
"""Shared ``klt`` lookup and dual-format invocation for ``layout/`` runners.

Every ``layout/*/run_*.py`` entry point starts the same way: resolve ``klt``
on ``PATH`` (printing the one install hint from ``layout/README.md`` when it
is absent), then run the verb twice -- ``--format json`` for the report this
repo commits as evidence, ``--format text`` for the human-readable twin filed
beside it. That plumbing was duplicated across ``layout/drc/run_drc.py``,
``layout/erc/run_erc.py``, ``layout/lvs/run_lvs.py`` and
``layout/netlist/run_extract.py`` (the lookup) and the first three of those
(the dual-format invocation), and the copies had drifted apart (#548): a
``--format json`` failure still launched the ``--format text`` pass in two of
the three dual-format callers, and a ``--format text`` failure was silently
ignored in all three -- a failed text pass exited ``0`` and filed its report
beside a json report the failing run never truly produced. This module gives
both one implementation, with the fail-closed contract the evidence rules
demand:

* :func:`find_klt` resolves the binary and prints the install hint;
* :func:`run_dual_format` runs the json pass first and fails immediately
  (never launching the text pass) on an exit code outside the accepted set,
  then runs the text pass and fails closed on an unaccepted exit code,
  returning both ``CompletedProcess`` results only when both passes
  completed -- a caller can never file a report pair from a half-finished
  run.

Accepted exit codes stay per-verb facts owned by the callers (``klt drc`` and
``klt lvs`` accept ``(0, 3)``; ``klt erc`` accepts ``(0, 3, 4)`` -- each
runner's own docstring says why), because they are part of each tool's
documented exit-code contract, not plumbing.

``shutil.which`` and ``subprocess.run`` are resolved at call time, not bound
at import time, so the module-global patches the runner tests apply (see
``layout/lvs/test_run_lvs.py``) keep intercepting these calls.

Usage from a ``run_*.py`` entry point::

    REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO_ROOT / "layout" / "common"))

    import klt_runner  # noqa: E402

    ...
    klt = klt_runner.find_klt()
    if klt is None:
        return 1
    procs = klt_runner.run_dual_format(
        [klt, "drc", str(gds_rel), "--deck", deck],
        cwd=REPO_ROOT, ok_exit_codes=(0, 3), label="klt drc",
    )
    if procs is None:
        return 1
    json_proc, text_proc = procs
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Container, Sequence
from pathlib import Path


def find_klt(which: Callable[[str], str | None] | None = None) -> str | None:
    """Resolve ``klt`` on ``PATH``, or print the install hint and return ``None``.

    The hint is the single pointer ``layout/README.md`` owns; printing it
    here is what let the four identical lookup blocks collapse into one
    place. Callers treat ``None`` as a hard stop (exit 1), which is what
    every runner already did inline.
    """
    resolver = which if which is not None else shutil.which
    klt = resolver("klt")
    if klt is None:
        print(
            "error: 'klt' not found on PATH. Install with:\n"
            "  uv tool install klayout-tools==<pin in signoff/klt-pin.txt>\n"
            "(see layout/README.md)",
            file=sys.stderr,
        )
    return klt


def run_dual_format(
    base_cmd: Sequence[str],
    *,
    cwd: Path,
    ok_exit_codes: Container[int],
    label: str,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[subprocess.CompletedProcess, subprocess.CompletedProcess] | None:
    """Run ``[*base_cmd, "--format", fmt]`` for json then text, failing closed.

    Returns ``(json_proc, text_proc)`` when **both** passes exited with a
    code in ``ok_exit_codes``, or ``None`` after printing the failing pass's
    captured output and an ``error: <label> ...`` line to the appropriate
    streams -- in which case the caller must write no report file at all.
    A json failure returns before the text pass is ever launched; a text
    failure means no caller-visible report exists for the run.

    ``label`` names the invocation in the error line (e.g. ``"klt drc"``,
    ``"klt lvs --engine netgen"``); the text pass names itself too, since
    it is the pass whose failure used to be silent.
    """
    runner = run if run is not None else subprocess.run
    json_proc = runner(
        [*base_cmd, "--format", "json"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if json_proc.returncode not in ok_exit_codes:
        _report_failure(f"error: {label} failed (exit {json_proc.returncode})", json_proc)
        return None
    text_proc = runner(
        [*base_cmd, "--format", "text"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if text_proc.returncode not in ok_exit_codes:
        _report_failure(
            f"error: {label} --format text failed (exit {text_proc.returncode})",
            text_proc,
        )
        return None
    return json_proc, text_proc


def _report_failure(message: str, proc: subprocess.CompletedProcess) -> None:
    """Echo the failing pass's own output before the error line, so the run's
    diagnostics stay verbatim (a missing netgen binary is an actionable ``klt
    lvs`` error; swallowing it behind a generic "failed" defeats the run)."""
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    print(message, file=sys.stderr)
