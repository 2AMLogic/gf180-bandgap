#!/usr/bin/env python3
"""Spec-line verification suite for gf180-bandgap.

    python3 sim/run_suite.py            # every bench, full PVT matrix, mint records
    python3 sim/run_suite.py --smoke    # nominal-only debugging run, records nothing
    python3 sim/run_suite.py --list     # the ratified-spec-row -> testbench index

One command, one per-spec-line pass/fail summary: the operational definition
of "simulation-complete". Stdlib only, no virtualenv. See sim/suite/README.md.
"""

import sys
from pathlib import Path

# Load-bearing: sys.path[0] is this file's dir only under `python3 file.py`.
# Under the documented `python3 -m <dotted.module>` form it is the CWD. #479
sys.path.insert(0, str(Path(__file__).resolve().parent))

from suite.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
