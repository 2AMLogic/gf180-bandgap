#!/usr/bin/env python3
"""Combined untrimmed-accuracy verdict for gf180-bandgap.

    python3 sim/run_combined_accuracy.py            # newest record of each leg
    python3 sim/run_combined_accuracy.py --no-write # print, write nothing

README.md's ratified Output-reference row is substantiated by two benches --
`sim/mc-untrimmed/` (mismatch MC, N>=300) and `sim/output-voltage-tc/`
(process x temperature x supply corners). This command combines them into ONE
pass/fail per corner (rolled up per temperature), citing both records by path.

It simulates nothing and writes nothing under any bench's `records/`,
`corners/` or `netlist-snapshots/`; its own report lands in
`sim/suite/combined/`. Stdlib only, no PDK required. See sim/suite/README.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from suite.combined import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
