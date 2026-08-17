"""Repo-relative path formatting for records, logs and console output.

Resolves a path and makes it relative to the repo root, falling back to the
original (unresolved) string when the path isn't under the repo -- so a
record or log line reads the same regardless of where it was generated, and
degrades gracefully for paths outside the tree. This was a near-identical
private copy in each caller (issue #171); this module is the single
implementation.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_relative(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
