#!/usr/bin/env python3
"""PVT corner runner for gf180-bandgap.

    python3 sim/run_corners.py --check-env
    python3 sim/run_corners.py --list
    python3 sim/run_corners.py smoke-bias

Stdlib only, no virtualenv required. See sim/README.md.
"""

import sys
from pathlib import Path

# Load-bearing: sys.path[0] is this file's dir only under `python3 file.py`.
# Under the documented `python3 -m <dotted.module>` form it is the CWD. #479
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
