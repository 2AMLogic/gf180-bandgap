#!/usr/bin/env python3
"""Validate the public artifact-store manifests under ``manifests/artifacts/``.

New sim evidence keeps its raw outputs in the artifact store; git carries only
the manifest (``sim/harness/evidence_store.py``). This check fails on:

* a manifest that is not valid JSON, or lacks the ``schema_version`` /
  ``entries`` shape ``klt artifact put`` writes;
* an entry missing ``name`` / ``size`` / ``sha256`` / ``uri``, with a
  malformed digest, or whose ``uri`` does not start with ``artifact:``;
* an entry whose bytes are *also* tracked in git (matched by sha256 against
  tracked files of the same size), which would defeat the point of storing
  them;
* a URL, ``s3://`` or ``arn:aws:`` string anywhere in a manifest.

Stdlib + git only. Usage: ``scripts/check_artifact_manifests.py [REPO_ROOT]``.
Exit 0 clean, 1 problems.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST_DIR = Path("manifests") / "artifacts"
URI_PREFIX = "artifact:"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_RE = re.compile(r"s3://|arn:aws:|https?://", re.IGNORECASE)
#: Tracked files above this size are not hashed (layout blobs, not logs).
MAX_HASHED_BYTES = 256 * 1024 * 1024


def _tracked_files(root: Path) -> list[str]:
    done = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False
    )
    if done.returncode != 0:
        return []
    return [p for p in done.stdout.decode("utf-8", "replace").split("\0") if p]


def _tracked_hashes(root: Path, tracked: list[str], sizes: set[int]) -> dict[str, str]:
    """sha256 -> path for tracked files whose size matches a stored object."""
    out: dict[str, str] = {}
    for rel in tracked:
        path = root / rel
        try:
            if not path.is_file() or path.is_symlink():
                continue
            size = path.stat().st_size
            if size not in sizes or size > MAX_HASHED_BYTES:
                continue
            out[hashlib.sha256(path.read_bytes()).hexdigest()] = rel
        except OSError:
            continue
    return out


def check_manifest(path: Path, label: str) -> tuple[list[str], list[dict]]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    if FORBIDDEN_RE.search(text):
        problems.append(f"{label}: contains a URL / s3:// / arn:aws: string")
    try:
        data = json.loads(text)
    except ValueError as exc:
        return problems + [f"{label}: not valid JSON ({exc})"], []
    if not isinstance(data, dict) or not isinstance(data.get("schema_version"), int):
        problems.append(f"{label}: missing integer schema_version")
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return problems + [f"{label}: 'entries' must be a non-empty list"], []
    good: list[dict] = []
    for i, entry in enumerate(entries):
        where = f"{label}: entries[{i}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        ok = True
        for key in ("name", "uri", "sha256", "size"):
            if key not in entry:
                problems.append(f"{where}: missing '{key}'")
                ok = False
        if not ok:
            continue
        if not isinstance(entry["uri"], str) or not entry["uri"].startswith(URI_PREFIX):
            problems.append(f"{where}: uri must start with '{URI_PREFIX}'")
            ok = False
        if not isinstance(entry["sha256"], str) or not SHA_RE.match(entry["sha256"]):
            problems.append(f"{where}: sha256 is not 64 lowercase hex digits")
            ok = False
        size = entry["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            problems.append(f"{where}: size must be a non-negative integer")
            ok = False
        if ok:
            good.append(entry)
    return problems, good


def check(root: Path) -> list[str]:
    manifest_dir = root / MANIFEST_DIR
    if not manifest_dir.is_dir():
        return []
    tracked = _tracked_files(root)
    tracked_set = set(tracked)
    problems: list[str] = []
    entries: list[tuple[str, dict]] = []
    for path in sorted(manifest_dir.glob("*.manifest.json")):
        rel = path.relative_to(root).as_posix()
        if tracked_set and rel not in tracked_set:
            continue  # untracked scratch; only committed manifests are gated
        found, good = check_manifest(path, rel)
        problems += found
        entries += [(rel, e) for e in good]
    if entries:
        hashes = _tracked_hashes(root, tracked, {e["size"] for _, e in entries})
        for rel, e in entries:
            if e["sha256"] in hashes:
                problems.append(
                    f"{rel}: stored object {e['name']} ({e['sha256'][:12]}) is also "
                    f"tracked in git as {hashes[e['sha256']]}"
                )
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parents[1]
    problems = check(root)
    for line in problems:
        print(f"  {line}")
    if problems:
        print(f"FAIL: {len(problems)} artifact-manifest problem(s)")
        return 1
    print("PASS: artifact manifests clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
