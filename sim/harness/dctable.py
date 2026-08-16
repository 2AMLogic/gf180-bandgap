"""DC-sweep `print` table parsing and linear interpolation.

Shared by the device-level DC-sweep benches
(`sim/device-mos-vth/run_mos_vth.py`, `sim/device-pnp-vbe/run_pnp_vbe.py`),
which were byte-identical private copies of this logic in each file
(issue #154); this module is the single implementation.
"""

from __future__ import annotations


def parse_dc_table(log: str) -> tuple[list[str], list[list[float]]]:
    """Parse the tabular output of `print v1 v2 ...` after a `dc` analysis.

    Returns (column names excluding the Index column, rows). The leading
    `v-sweep` column is kept as the first data column.
    """
    lines = log.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Index"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("no DC table header ('Index ...') found in ngspice log")
    columns = lines[header_idx].split()[1:]
    rows: list[list[float]] = []
    for line in lines[header_idx + 1 :]:
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        try:
            values = [float(p) for p in parts[1:]]
        except ValueError:
            continue
        if len(values) == len(columns):
            rows.append(values)
    if not rows:
        raise ValueError("DC table header found but no data rows parsed")
    return columns, rows


def column(columns: list[str], rows: list[list[float]], name: str) -> list[float]:
    idx = columns.index(name)
    return [row[idx] for row in rows]


def interp_at(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation of y(x) on a monotonically increasing xs."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if xs[i] >= x:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]
