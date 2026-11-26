"""Monte Carlo `op`-series parsing and summary statistics.

Shared by the device-level mismatch Monte Carlo benches
(`sim/device-mos-mismatch/run_mos_mismatch.py`,
`sim/device-pnp-mismatch/run_pnp_mismatch.py`) and the circuit-level
mismatch bench (`sim/mc-untrimmed/run_mc_untrimmed.py`), plus
`sim/suite/combined.py`'s own summary stats over that bench's raw logs.
These were byte-identical/near-identical private copies in each file
(issue #154); this module is the single implementation. `pair_stats` is
likewise the one per-pair extraction loop shared by the two device mismatch
benches (issue #578).
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable

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
    # fsum, not sum: builtin sum() gained compensated float summation in 3.12,
    # so a plain sum differs in the last bits between 3.9 and 3.12 and turns
    # a zero-spread sample into ~1e-15 sigma on the documented 3.9 floor.
    return math.fsum(values) / len(values)


def stdev(values: list[float]) -> float:
    """Sample standard deviation (N-1 normalisation)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_v = mean(values)
    return math.sqrt(math.fsum((v - mean_v) ** 2 for v in values) / (n - 1))


def pair_stats(
    log: str,
    pairs: Iterable[str],
    *,
    n_samples: int,
    sigma_floor_v: float,
    mean_k: float,
    zero_mean_pairs: Collection[str],
) -> dict[str, dict[str, float]]:
    """Summarise a Monte Carlo `op` log per pair, rejecting a suspect draw.

    Requires exactly `n_samples` samples, then returns one `{"mean", "sigma",
    "max_abs"}` entry per name in `pairs`, in that order. Two guards reject
    the whole log with `RuntimeError`: a pair whose sigma is at or below
    `sigma_floor_v` is not re-randomizing, and a pair in `zero_mean_pairs`
    whose |mean| exceeds `mean_k * sigma / sqrt(n_samples)` is not centered
    at zero. A pair outside `zero_mean_pairs` may carry a physical offset.
    """
    samples = parse_op_series(log)
    if len(samples) != n_samples:
        raise RuntimeError(
            f"expected {n_samples} Monte Carlo samples in the log, parsed "
            f"{len(samples)} -- testbench control loop and N_SAMPLES disagree?"
        )
    out: dict[str, dict[str, float]] = {}
    for key in pairs:
        values = [s[key] for s in samples]
        mean_v = mean(values)
        sigma = stdev(values)
        if sigma <= sigma_floor_v:
            raise RuntimeError(
                f"pair {key!r}: sigma={sigma * 1e3:.6f} mV is at or below the "
                f"{sigma_floor_v * 1e3:g} mV floor -- the Monte Carlo draw does "
                "not appear to be re-randomizing (sw_stat_mismatch ignored?)"
            )
        if key in zero_mean_pairs:
            bound = mean_k * sigma / math.sqrt(n_samples)
            if abs(mean_v) > bound:
                raise RuntimeError(
                    f"pair {key!r}: mean={mean_v * 1e3:+.6f} mV exceeds {mean_k}x "
                    f"its expected standard error ({bound * 1e3:.6f} mV) -- the "
                    "draw may not be centered at zero / re-randomizing correctly"
                )
        out[key] = {
            "mean": mean_v,
            "sigma": sigma,
            "max_abs": max(abs(v) for v in values),
        }
    return out
