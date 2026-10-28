"""Manifest-forward evidence: raw run output goes to the artifact store.

New runs no longer commit their raw per-corner logs. They are written to a
git-ignored stage directory, ``klt artifact put`` uploads them, and the repo
keeps only the public manifest at

    manifests/artifacts/<experiment>-<record-id>.manifest.json

(``artifact:`` URIs and sha256 digests -- never bytes, never a broker URL).
Records committed before this change keep their in-tree ``corners/`` logs.

The store is fail-closed: :meth:`EvidenceRun.start` runs a preflight before
anything is simulated, and every failure raises :class:`StoreUnavailable`.
There is deliberately no flag or fallback that commits the bytes instead.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .pdk import REPO_ROOT

BROKER_ENV = "KLT_ARTIFACT_BROKER"
MANIFEST_DIR = Path("manifests") / "artifacts"
#: Git-ignored (``sim/.work/``) scratch the raw outputs are staged in.
STAGE_ROOT = Path("sim") / ".work" / ".stage"
ARTIFACT_URI_PREFIX = "artifact:"
PREFLIGHT_TIMEOUT_S = 10
PUT_TIMEOUT_S = 600


class StoreUnavailable(RuntimeError):
    """The artifact store cannot be used; the run must not proceed."""


@dataclass(frozen=True)
class StoredFile:
    name: str
    size: int
    sha256: str
    uri: str


def _broker_reachable(url: str) -> bool:
    """Any HTTP answer counts as reachable; only a transport failure does not."""
    try:
        urllib.request.urlopen(url, timeout=PREFLIGHT_TIMEOUT_S).close()
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return True


class KltArtifactStore:
    """The real store: shells out to ``klt artifact put``."""

    def __init__(self, klt: str = "klt", reachable=_broker_reachable):
        self.klt = klt
        self._reachable = reachable

    def preflight(self) -> None:
        broker = os.environ.get(BROKER_ENV, "")
        if not broker:
            raise StoreUnavailable(
                f"${BROKER_ENV} is not set; new evidence is stored in the "
                "artifact store and there is no fallback that commits it"
            )
        try:
            probe = subprocess.run(
                [self.klt, "artifact", "put", "--help"],
                capture_output=True,
                text=True,
                timeout=PREFLIGHT_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StoreUnavailable(f"cannot run `{self.klt} artifact put`: {exc}") from exc
        if probe.returncode != 0:
            raise StoreUnavailable(
                f"`{self.klt} artifact put` is not available in this klt"
            )
        # Deliberately not echoing the broker URL: it must not leak into logs.
        if not self._reachable(broker):
            raise StoreUnavailable(f"the artifact broker (${BROKER_ENV}) is unreachable")

    def put(self, path: Path, name: str, manifest: Path) -> None:
        try:
            done = subprocess.run(
                [self.klt, "artifact", "put", "--manifest", str(manifest),
                 "--name", name, str(path)],
                capture_output=True,
                text=True,
                timeout=PUT_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StoreUnavailable(f"`klt artifact put` failed for {name}: {exc}") from exc
        if done.returncode != 0:
            raise StoreUnavailable(
                f"`klt artifact put` failed for {name} (exit {done.returncode})"
            )


def read_manifest(path: Path) -> list[StoredFile]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        StoredFile(
            name=e["name"],
            size=int(e["size"]),
            sha256=e["sha256"],
            uri=e["uri"],
        )
        for e in data["entries"]
    ]


def stored_evidence_lines(entries: list[StoredFile], manifest_rel: str) -> list[str]:
    """The record's "Stored evidence" section, as markdown lines."""
    lines = [
        "",
        "## Stored evidence",
        "",
        "Raw outputs for this record live in the artifact store, not in git.",
        f"Manifest: `{manifest_rel}` (fetch/verify with `klt artifact get|verify`).",
        "",
        "| name | size (bytes) | sha256 |",
        "| --- | ---: | --- |",
    ]
    for e in sorted(entries, key=lambda e: e.name):
        lines.append(f"| `{e.name}` | {e.size} | `{e.sha256}` |")
    lines.append("")
    return lines


class EvidenceRun:
    """Stage -> put -> manifest for one record.

    Typical use::

        run = EvidenceRun(bench, record_id)
        run.start()                       # preflight; raises StoreUnavailable
        ... write logs under run.log_dir ...
        entries = run.finalize()          # uploads, builds the manifest
        ... write the record (it embeds run.stored_lines()) ...
        run.commit()                      # manifest lands in manifests/artifacts/
    """

    def __init__(self, bench: str, record_id: str, *, store=None, repo_root: Path | None = None):
        self.bench = bench
        self.record_id = record_id
        self.store = store if store is not None else KltArtifactStore()
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self.stage = self.repo_root / STAGE_ROOT / f"{bench}-{record_id}"
        #: Parent of ``<record-id>/``; pass to ``write_device_corner_log``.
        self.corners_root = self.stage / "corners"
        #: Where per-corner logs for this record are written.
        self.log_dir = self.corners_root / record_id
        self._staged_manifest = self.stage / "manifest.json"
        self.manifest_path = (
            self.repo_root / MANIFEST_DIR / f"{bench}-{record_id}.manifest.json"
        )
        self.entries: list[StoredFile] = []

    @property
    def manifest_rel(self) -> str:
        return self.manifest_path.relative_to(self.repo_root).as_posix()

    def start(self) -> "EvidenceRun":
        self.store.preflight()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self

    def finalize(self) -> list[StoredFile]:
        files = sorted(p for p in self.log_dir.glob("*") if p.is_file())
        if not files:
            raise StoreUnavailable(f"no raw output was staged under {self.log_dir}")
        self._staged_manifest.unlink(missing_ok=True)
        for path in files:
            name = f"sim/{self.bench}/{CORNERS_NAME}/{self.record_id}/{path.name}"
            self.store.put(path, name, self._staged_manifest)
        self.entries = read_manifest(self._staged_manifest)
        return self.entries

    def stored_lines(self) -> list[str]:
        return stored_evidence_lines(self.entries, self.manifest_rel)

    def commit(self) -> Path:
        """Move the finished manifest into ``manifests/artifacts/`` (append-only)."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            raise FileExistsError(
                f"{self.manifest_path} already exists; manifests are append-only"
            )
        shutil.move(str(self._staged_manifest), str(self.manifest_path))
        return self.manifest_path


CORNERS_NAME = "corners"
