"""Shared plumbing for the gf180mcu device-characterization testbenches (issue #4).

This is deliberately small and dependency-free (stdlib only). It exists because
the four `sim/device-*/` experiments all need the same four things:

  1. Resolve the installed gf180mcu ngspice models from $PDK_ROOT / $PDK.
  2. Generate the per-corner "corner shim" (`.lib <section>` + `.temp <T>`) so the
     committed testbench deck itself carries no machine-specific path and no
     hardcoded corner -- the same pattern `sim/smoke_test/run_smoke_test.sh`
     already uses for its `pdk_include.spice`.
  3. Run ngspice headlessly on the deck and capture the raw log per corner point.
  4. Parse ngspice's `print` output (DC-sweep tables and `op` scalars) back into
     Python floats so the summary record can be generated from the same run that
     produced the logs.

Interim status: issue #2 (PR #23) is standing up a general PVT harness around
`sim/run_corners.py` + `sim/<experiment-slug>/testbench/tb.json` manifests. That
harness had not merged to
`origin/main` when these testbenches were written, so per the guidance on issue #4
they are standalone decks conforming to the `sim/README.md` evidence format as it
exists on main. When the harness lands, this module's job (corner shim + run +
parse) is exactly what it subsumes; these experiments should be re-expressed as
harness manifests and this file deleted rather than grown.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# PDK resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Pdk:
    """Paths to the installed gf180mcu ngspice model files."""

    root: Path
    name: str
    design: Path
    models: Path

    @property
    def label(self) -> str:
        return f"{self.name} ({self.root})"


def resolve_pdk() -> Pdk:
    """Locate the gf180mcu ngspice models via $PDK_ROOT / $PDK.

    Mirrors the check in `sim/smoke_test/run_smoke_test.sh` -- see
    `docs/environment-setup.md` for how these are provisioned (volare).
    """
    root = os.environ.get("PDK_ROOT")
    name = os.environ.get("PDK")
    if not root or not name:
        sys.exit(
            "ERROR: PDK_ROOT and PDK must be set in the environment.\n"
            "       See docs/environment-setup.md for the bootstrap steps."
        )
    model_dir = Path(root) / name / "libs.tech" / "ngspice"
    design = model_dir / "design.ngspice"
    models = model_dir / "sm141064.ngspice"
    for path in (design, models):
        if not path.is_file():
            sys.exit(
                f"ERROR: gf180mcu ngspice models not found at {path}\n"
                "       Did you run 'volare fetch'/'volare enable'? "
                "See docs/environment-setup.md."
            )
    return Pdk(root=Path(root), name=name, design=design, models=models)


def ngspice_version() -> str:
    try:
        out = subprocess.run(
            ["ngspice", "-v"], capture_output=True, text=True, check=False
        ).stdout
    except FileNotFoundError:
        sys.exit("ERROR: ngspice not found on PATH. See docs/environment-setup.md.")
    match = re.search(r"(ngspice-[\w.]+)", out)
    return match.group(1) if match else "unknown"


# --------------------------------------------------------------------------
# Record identity
# --------------------------------------------------------------------------


def repo_root(start: Path) -> Path:
    out = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def short_sha(root: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def mint_record_id(root: Path, now: datetime | None = None) -> tuple[str, datetime]:
    """`<YYYYMMDD>-<HHMMSS>-<short-git-sha>` per `sim/README.md`."""
    stamp = now or datetime.now(timezone.utc)
    return f"{stamp:%Y%m%d-%H%M%S}-{short_sha(root)}", stamp


# --------------------------------------------------------------------------
# Corner naming
# --------------------------------------------------------------------------


def corner_id(section: str, temp_c: float, supply: str = "nosupply") -> str:
    """`<process-corner>_<temp>c_<supply>` per `sim/README.md`.

    Two-terminal device sweeps (diode-connected PNP, resistor) and
    source-referred MOS extractions have no supply rail, so the `<supply>v`
    field carries the literal `nosupply` instead of a voltage. Every record that
    uses it states why the +/-10% supply axis of the PVT matrix does not apply.
    """
    temp = f"{temp_c:g}".replace(".", "p")
    return f"{section}_{temp}c_{supply}"


# --------------------------------------------------------------------------
# Running ngspice
# --------------------------------------------------------------------------

CORNER_SHIM_NAME = "corner.spice"


def corner_shim(pdk: Pdk, section: str, temp_c: float, extra: str = "") -> str:
    return (
        "* Generated per corner point by the experiment's run script from\n"
        "* $PDK_ROOT/$PDK -- do not edit by hand, and do not commit.\n"
        f".include {pdk.design}\n"
        f".lib {pdk.models} {section}\n"
        f".temp {temp_c:g}\n" + (extra + "\n" if extra else "")
    )


def run_corner(
    deck: Path,
    pdk: Pdk,
    section: str,
    temp_c: float,
    extra_shim: str = "",
) -> str:
    """Run `deck` through ngspice at one (corner section, temperature) point.

    Returns the combined stdout+stderr text, which is what gets committed as the
    raw per-corner log.
    """
    with tempfile.TemporaryDirectory(prefix="devchar-") as tmp:
        work = Path(tmp)
        local_deck = work / deck.name
        shutil.copyfile(deck, local_deck)
        (work / CORNER_SHIM_NAME).write_text(
            corner_shim(pdk, section, temp_c, extra_shim), encoding="utf-8"
        )
        proc = subprocess.run(
            ["ngspice", "-b", deck.name],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )
    log = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(
            f"ngspice exited {proc.returncode} for {deck.name} "
            f"[{section} @ {temp_c} C]\n{log}"
        )
    if re.search(r"^\s*(Error|ERROR|fatal)", log, re.MULTILINE):
        raise RuntimeError(f"ngspice reported an error for {deck.name}:\n{log}")
    return log


def write_log(
    corners_dir: Path, record: str, cid: str, header: str, log: str
) -> Path:
    out_dir = corners_dir / record
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cid}.log"
    path.write_text(header + log, encoding="utf-8")
    return path


def log_header(
    pdk: Pdk, deck: Path, section: str, temp_c: float, record: str, stamp: datetime
) -> str:
    return (
        "* ====================================================================\n"
        f"* record-id : {record}\n"
        f"* testbench : {deck.name}\n"
        f"* corner    : {section}\n"
        f"* temp      : {temp_c:g} C\n"
        "* supply    : n/a (no supply rail in this device-level testbench)\n"
        f"* pdk       : {pdk.label}\n"
        f"* ngspice   : {ngspice_version()}\n"
        f"* run (UTC) : {stamp:%Y-%m-%dT%H:%M:%SZ}\n"
        "* ====================================================================\n"
    )


# --------------------------------------------------------------------------
# Parsing ngspice output
# --------------------------------------------------------------------------

_OP_LINE = re.compile(r"^([a-zA-Z_][\w()\-.,+@#]*)\s*=\s*([-+0-9.eE]+)\s*$")


def parse_op(log: str) -> dict[str, float]:
    """Parse `print a b c` scalars emitted by an `op` analysis."""
    values: dict[str, float] = {}
    for line in log.splitlines():
        match = _OP_LINE.match(line.strip())
        if match:
            try:
                values[match.group(1).lower()] = float(match.group(2))
            except ValueError:
                continue
    return values


def parse_op_series(log: str) -> list[dict[str, float]]:
    """Parse repeated `op`+`print` blocks (the Monte Carlo loop) into samples.

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


def column(
    columns: list[str], rows: list[list[float]], name: str
) -> list[float]:
    idx = columns.index(name)
    return [row[idx] for row in rows]


# --------------------------------------------------------------------------
# Small numeric helpers (stdlib only -- no numpy dependency for the runners)
# --------------------------------------------------------------------------


def linfit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Ordinary least-squares fit; returns (slope, intercept)."""
    n = len(xs)
    if n < 2:
        raise ValueError("linfit needs at least two points")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, mean_y - slope * mean_x


def max_abs_residual(
    xs: list[float], ys: list[float], slope: float, intercept: float
) -> float:
    return max(abs(y - (slope * x + intercept)) for x, y in zip(xs, ys))


def stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


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


VT_Q_OVER_K = 1.602176634e-19 / 1.380649e-23  # q/k, K/V


def thermal_voltage(temp_c: float) -> float:
    """kT/q in volts at `temp_c` degrees Celsius."""
    return (temp_c + 273.15) / VT_Q_OVER_K


# --------------------------------------------------------------------------
# Record writing
# --------------------------------------------------------------------------


def write_record(records_dir: Path, record: str, body: str) -> Path:
    """Write `records/<record-id>.md`, refusing to overwrite (append-only)."""
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / f"{record}.md"
    if path.exists():
        raise RuntimeError(
            f"refusing to overwrite existing record {path} -- sim/ is append-only; "
            "a re-run must mint a new record ID"
        )
    path.write_text(body, encoding="utf-8")
    return path


def snapshot_netlist(snapshot_dir: Path, record: str, deck: Path) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{record}.spice"
    shutil.copyfile(deck, path)
    return path
