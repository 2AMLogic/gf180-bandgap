# manifests/artifacts

Public manifests for sim evidence whose raw bytes live in the artifact store,
not in git. One file per run: `<experiment>-<record-id>.manifest.json`, written
by `sim/harness/evidence_store.py` through `klt artifact put`.

- Only `artifact:` URIs, sizes and sha256 digests are committed. No bucket
  names, ARNs, or broker URLs appear here, and none may be added.
- The bytes are private; the manifest is public. Fetch or verify with
  `klt artifact get <manifest>#<name> -o <file>` / `klt artifact verify
  <manifest>` (needs `$KLT_ARTIFACT_BROKER`).
- Manifests are append-only evidence, like `sim/*/records/`.
- `scripts/check_artifact_manifests.py` (lint step 10) validates the schema
  and the URI form and fails if a stored object's bytes are also tracked.
