#!/usr/bin/env python3
"""Fail when the committed ``bandgap_top.gds`` is not what ``generate.py`` makes.

``generate.py`` is documented as byte-for-byte deterministic (GDS timestamps
are disabled in :func:`generate.save_options`), and signoff pins plus the
DRC/LVS/area reports are graded against the committed GDS. This check
regenerates the layout into a temporary directory with the generator's own
``build()`` / ``save_options()`` and compares the bytes strictly with the
committed file. The tracked file is never written.

    python3 layout/bandgap_top/check_freshness.py

Exit status: 0 fresh; 1 stale (bytes differ); 2 cannot check (committed file
missing, klayout missing, or generation raised). Nothing is ever a skip.
Requires ``klayout`` (``pip install klayout``; installed with klt in CI).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMITTED = HERE / "bandgap_top.gds"

REMEDY = (
    "To fix: re-run `python3 layout/bandgap_top/generate.py` and commit the "
    "regenerated layout/bandgap_top/bandgap_top.gds, then refresh the signoff "
    "pins (signoff/pinned-inputs.json) and re-run `signoff/regenerate.sh` and "
    "`python3 signoff/check_signoff.py --run-klt`. Do not overwrite historical "
    "reports/evidence."
)


def _first_diff(a: bytes, b: bytes) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def check(committed: Path = COMMITTED) -> tuple[int, str]:
    """Return ``(exit_code, message)``. Never modifies ``committed``."""
    committed = Path(committed)
    if not committed.is_file():
        return 2, f"ERROR: committed GDS not found: {committed}\n{REMEDY}"
    try:
        sys.path.insert(0, str(HERE))
        import generate  # noqa: PLC0415 (needs klayout; failure is an error)

        builder, _stats = generate.build()
        with tempfile.TemporaryDirectory(prefix="bandgap_fresh_") as tmp:
            out = Path(tmp) / "bandgap_top.gds"
            builder.layout.write(str(out), generate.save_options())
            fresh = out.read_bytes()
    except Exception as exc:  # noqa: BLE001 - every failure must be loud
        return 2, f"ERROR: could not regenerate the layout: {type(exc).__name__}: {exc}"
    have = committed.read_bytes()
    if fresh == have:
        return 0, f"OK: {committed.name} matches generate.py output ({len(have)} bytes)."
    return 1, (
        f"STALE: {committed} differs from generate.py output "
        f"(committed {len(have)} bytes, generated {len(fresh)} bytes, "
        f"first differing byte offset {_first_diff(have, fresh)}).\n{REMEDY}"
    )


def main() -> int:
    code, msg = check()
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
