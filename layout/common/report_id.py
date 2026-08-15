#!/usr/bin/env python3
"""Shared evidence-id helpers for the ``layout/{drc,lvs,netlist}`` run scripts.

Every ``layout/*/run_*.py`` entry point (``layout/drc/run_drc.py``,
``layout/lvs/run_lvs.py``, ``layout/netlist/run_extract.py``) mints its own
append-only ``<record-id>``, per the convention ``sim/README.md`` documents
for ``sim/`` evidence: ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``, advancing by
one second on a same-second collision rather than ever overwriting an
existing report. That plumbing -- shelling out to git for the current short
commit sha, and probing a reports directory for whether a candidate id is
already claimed -- used to be duplicated byte-for-byte across all three
scripts (the same shape ``sim/harness/report.py`` already consolidated for
``sim/`` in #124/#128/#130/#132/#134). This module gives it one
implementation.

Usage from a ``run_*.py`` entry point::

    REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO_ROOT / "layout" / "common"))

    import report_id  # noqa: E402

    ...
    record_id = report_id.record_id(
        reports_dir, _dt.datetime.now(_dt.timezone.utc), report_id.short_sha(REPO_ROOT)
    )
"""

from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path


def _git(repo_root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def short_sha(repo_root: Path) -> str:
    """The current commit's short (7-char) sha, or ``"unknown"`` if git fails."""
    commit = _git(repo_root, "rev-parse", "HEAD")
    return commit[:7] if commit else "unknown"


def record_id(reports_dir: Path, when: _dt.datetime, short_sha: str) -> str:
    """Return the first ``<date>-<time>-<sha>`` id no artefact already claims.

    The probe is over ``<record-id>.*`` rather than one hardcoded suffix, so
    this is correct for every caller regardless of how many file extensions
    it writes per record. A caller that only ever writes one suffix per
    record (``run_drc.py``'s ``.drc.json``, ``run_extract.py``'s
    ``.extract.json``) is unaffected -- the glob still matches its own single
    file. A caller that can write more than one suffix under different runs
    (``run_lvs.py --engine netgen`` writes ``.lvs-netgen.json`` and no
    ``.lvs.json`` at all) needs the glob form: keying append-only-ness on one
    suffix would let a later run of a *different* suffix reuse the id and
    clobber the artefacts already filed under it.
    """
    while True:
        candidate = f"{when.strftime('%Y%m%d-%H%M%S')}-{short_sha}"
        if next(reports_dir.glob(f"{candidate}.*"), None) is None:
            return candidate
        when += _dt.timedelta(seconds=1)
