#!/usr/bin/env python3
"""Evidence-record format checker for gf180-bandgap.

    python3 sim/check_records.py
    python3 sim/check_records.py --require-append-only

Checks every sim/<slug>/records/<record-id>.md against the ratified format in
sim/README.md, and enforces the append-only rule against the merge base.
Stdlib only, no virtualenv required. See sim/harness/evidence_lint.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.evidence_lint import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
