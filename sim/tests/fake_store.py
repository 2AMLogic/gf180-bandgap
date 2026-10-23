"""In-memory stand-in for the artifact store, for tests (no klt, no broker)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harness.evidence_store import StoreUnavailable


class FakeStore:
    def __init__(self, fail_preflight: str = "", fail_put: bool = False):
        self.fail_preflight = fail_preflight
        self.fail_put = fail_put
        self.puts: list[str] = []

    def preflight(self) -> None:
        if self.fail_preflight:
            raise StoreUnavailable(self.fail_preflight)

    def put(self, path: Path, name: str, manifest: Path) -> None:
        if self.fail_put:
            raise StoreUnavailable("put failed")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        doc = (
            json.loads(manifest.read_text())
            if manifest.exists()
            else {"schema_version": 1, "entries": []}
        )
        doc["entries"] = [e for e in doc["entries"] if e["name"] != name]
        doc["entries"].append(
            {
                "name": name,
                "size": len(data),
                "sha256": digest,
                "kind": "evidence",
                "uri": f"artifact:evidence/test/{digest[:2]}/{digest}",
            }
        )
        manifest.write_text(json.dumps(doc, indent=2))
        self.puts.append(name)
