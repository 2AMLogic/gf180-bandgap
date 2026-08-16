"""Monte Carlo `op`-series parsing and summary statistics.

Shared by the device-level mismatch Monte Carlo benches
(`sim/device-mos-mismatch/run_mos_mismatch.py`,
`sim/device-pnp-mismatch/run_pnp_mismatch.py`) and the circuit-level
mismatch bench (`sim/mc-untrimmed/run_mc_untrimmed.py`), plus
`sim/suite/combined.py`'s own summary stats over that bench's raw logs.
These were byte-identical/near-identical private copies in each file
(issue #154); this module is the single implementation.
"""

from __future__ import annotations

import math
import re

#: ``<name> = <scalar>`` as ngspice's ``print`` writes it inside a Monte Carlo
#: ``dowhile``/``reset``/``op`` loop (e.g. ``"dn1 = -1.234567e-03"``).
_OP_LINE = re.compile(r"^([a-zA-Z_][\w()\-.,+@#]*)\s*=\s*([-+0-9.eE]+)\s*$")


def parse_op_series(log: str) -> list[dict[str, float]]:
    """Parse repeated `op`+`print` blocks (a Monte Carlo loop) into samples.

    A new sample starts whenever a name that has already been seen repeats.
    """
    samples: list[dict[str, float]] = []
    current: dict[str, float] = {}
    for line in log.splitlines():
        match = _OP_LINE.match(line.strip())
        if not match:
            continue
        name = match.group(1).lower()
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if name in current:
            samples.append(current)
            current = {}
        current[name] = value
    if current:
        samples.append(current)
    return samples


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def stdev(values: list[float]) -> float:
    """Sample standard deviation (N-1 normalisation)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_v = mean(values)
    return math.sqrt(sum((v - mean_v) ** 2 for v in values) / (n - 1))
