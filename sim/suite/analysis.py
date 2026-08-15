"""Roll raw per-corner ngspice logs up into per-spec-line verdicts.

The suite deliberately reads the **raw logs** a run wrote
(``sim/<slug>/corners/<record-id>/<corner-id>.log``) rather than the
Markdown record or any in-process value handed over from the runner. Two
reasons:

- the log is the evidence a human would hand-check, so the summary and a
  hand-check are reading the same bytes;
- it keeps the suite honest about what actually landed on disk: a summary
  that cannot be reproduced from the committed evidence is not evidence.

Nothing here mutates anything under ``records/``, ``netlist-snapshots/`` or
``corners/`` -- the suite is a reader of the append-only tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .spec import Limit, SpecLine

#: ``<process>_<temp>c_<supply>`` -- the corner-id grammar ratified in
#: sim/README.md. Split on the last two underscores: the process field may
#: itself contain one (``bjt_ff``, ``res_typical``).
CORNER_ID_RE = re.compile(r"^(?P<process>.+)_(?P<temp>-?\d+(?:\.\d+)?)c_(?P<supply>.+)$")

#: ``print`` output for a length-1 vector: "m_vref = 1.2291153728e+00".
MEASUREMENT_RE = re.compile(r"^\s*m_(\w+)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)\s*$")

#: Ratified box-method temperature span, -40..125 degC.
BOX_SPAN_C = 165.0


@dataclass(frozen=True)
class CornerKey:
    """A parsed ``<corner-id>``."""

    process: str
    temp_c: float
    supply: str

    @property
    def corner_id(self) -> str:
        return f"{self.process}_{self.temp_c:g}c_{self.supply}"


def parse_corner_id(corner_id: str) -> CornerKey | None:
    match = CORNER_ID_RE.match(corner_id)
    if not match:
        return None
    return CornerKey(
        process=match.group("process"),
        temp_c=float(match.group("temp")),
        supply=match.group("supply"),
    )


def parse_log(text: str) -> dict[str, float]:
    """Every ``m_<name> = <scalar>`` line of one raw ngspice log."""
    found: dict[str, float] = {}
    for line in text.splitlines():
        match = MEASUREMENT_RE.match(line)
        if match:
            try:
                found[match.group(1)] = float(match.group(2))
            except ValueError:  # pragma: no cover - the regex constrains this
                continue
    return found


def read_corner_logs(corners_dir: Path) -> dict[str, dict[str, float]]:
    """``{corner-id: {measurement: value}}`` for one record's raw logs."""
    samples: dict[str, dict[str, float]] = {}
    if not corners_dir.is_dir():
        return samples
    for log in sorted(corners_dir.glob("*.log")):
        samples[log.stem] = parse_log(log.read_text(errors="replace"))
    return samples


# --- per-spec-line verdicts -------------------------------------------------


@dataclass
class LimitOutcome:
    """How one limit fared across every corner of one run."""

    limit: Limit
    worst_value: float | None = None
    worst_corner: str = ""
    n_samples: int = 0
    n_violations: int = 0
    missing: bool = False

    @property
    def status(self) -> str:
        if self.missing or not self.n_samples:
            return "NO DATA"
        return "FAIL" if self.n_violations else "PASS"


@dataclass
class LineOutcome:
    """How one spec line fared: the roll-up of its limits."""

    line: SpecLine
    status: str = "PENDING"
    outcomes: list[LimitOutcome] = field(default_factory=list)
    reference: dict[str, tuple[float, float]] = field(default_factory=dict)
    detail: str = ""
    n_corners: int = 0

    @property
    def worst(self) -> LimitOutcome | None:
        """The limit that decides the verdict (a failing one, if any)."""
        failing = [o for o in self.outcomes if o.status == "FAIL"]
        pool = failing or self.outcomes
        return pool[0] if pool else None


def _worst(limit: Limit, samples: dict[str, dict[str, float]]) -> LimitOutcome:
    outcome = LimitOutcome(limit=limit)
    values = [
        (corner_id, values[limit.measurement])
        for corner_id, values in sorted(samples.items())
        if limit.measurement in values
    ]
    if not values:
        outcome.missing = True
        return outcome
    outcome.n_samples = len(values)
    outcome.n_violations = sum(1 for _, value in values if not limit.satisfied(value))
    # "Worst" is the extreme in the direction the limit constrains, so the
    # reported number is the one the claim actually stands or falls on.
    picker = min if limit.kind == "min" else max
    worst_corner, worst_value = picker(values, key=lambda item: item[1])
    outcome.worst_corner = worst_corner
    outcome.worst_value = worst_value
    return outcome


def evaluate_line(line: SpecLine, samples: dict[str, dict[str, float]]) -> LineOutcome:
    """Evaluate one spec line against one run's per-corner measurements."""
    result = LineOutcome(line=line, n_corners=len(samples))
    if not line.gated:
        result.status = "PENDING"
        return result
    result.outcomes = [_worst(limit, samples) for limit in line.limits]
    statuses = {outcome.status for outcome in result.outcomes}
    if "FAIL" in statuses:
        result.status = "FAIL"
    elif statuses == {"PASS"}:
        result.status = "PASS"
    else:
        result.status = "NO DATA"

    for name in line.reference:
        values = [v[name] for v in samples.values() if name in v]
        if values:
            result.reference[name] = (min(values), max(values))
    return result


# --- bench-specific cross-checks --------------------------------------------


@dataclass
class TcComparison:
    """Box-method TC vs what an endpoint-only evaluation would have claimed."""

    worst_box_ppm: float | None = None
    worst_box_corner: str = ""
    worst_endpoint_ppm: float | None = None
    understated_by_ppm: float = 0.0
    understated_at: str = ""
    interior_extremum_corners: list[str] = field(default_factory=list)

    @property
    def endpoint_only_would_mislead(self) -> bool:
        return bool(self.interior_extremum_corners) or self.understated_by_ppm > 0.05


def endpoint_tc_ppm(values: dict[str, float]) -> float | None:
    """TC a 3-point (-40/27/125 degC) evaluation would report, in ppm/degC.

    This is the number the suite exists to *not* claim: it is computed only
    so the record set can show, corner by corner, how much an endpoint-only
    evaluation would have understated the real box figure.
    """
    needed = ("vref_m40", "vref_27", "vref_125")
    if any(name not in values for name in needed):
        return None
    points = [values[name] for name in needed]
    nominal = values["vref_27"]
    if not nominal:
        return None
    return (max(points) - min(points)) / (nominal * BOX_SPAN_C) * 1e6


def compare_box_to_endpoints(samples: dict[str, dict[str, float]]) -> TcComparison:
    """Box TC vs endpoint-only TC, and where the curvature peak is interior."""
    comparison = TcComparison()
    for corner_id, values in sorted(samples.items()):
        box = values.get("tc_ppm")
        endpoint = endpoint_tc_ppm(values)
        if box is None:
            continue
        if comparison.worst_box_ppm is None or box > comparison.worst_box_ppm:
            comparison.worst_box_ppm = box
            comparison.worst_box_corner = corner_id
            comparison.worst_endpoint_ppm = endpoint
        if endpoint is not None and box - endpoint > comparison.understated_by_ppm:
            comparison.understated_by_ppm = box - endpoint
            comparison.understated_at = corner_id
        # An extremum strictly outside the three endpoint values can only
        # have come from inside the sweep: exactly the curvature peak an
        # endpoint-only evaluation steps over.
        endpoints = [values[n] for n in ("vref_m40", "vref_27", "vref_125") if n in values]
        box_min, box_max = values.get("vref_box_min"), values.get("vref_box_max")
        if endpoints and box_min is not None and box_max is not None:
            tolerance = 1e-9
            if box_max > max(endpoints) + tolerance or box_min < min(endpoints) - tolerance:
                comparison.interior_extremum_corners.append(corner_id)
    return comparison


@dataclass
class AxisCrossCheck:
    """Internal temperature sweep vs the harness's own outer temperature axis."""

    n_compared: int = 0
    worst_delta_v: float = 0.0
    worst_at: str = ""

    @property
    def consistent(self) -> bool:
        return self.n_compared > 0 and self.worst_delta_v < 1e-4


#: Outer-axis temperature -> the measurement taken at the same temperature
#: inside ``output-voltage-tc``'s own sweep.
_SWEEP_COLUMN_AT = {-40.0: "vref_m40", 27.0: "vref_27", 125.0: "vref_125"}


def cross_check_temperature_axes(samples: dict[str, dict[str, float]]) -> AxisCrossCheck:
    """Do the two independent temperature mechanisms agree?

    ``vref`` is an operating point taken at the temperature the *harness* set
    via ``.temp``; ``vref_m40``/``vref_27``/``vref_125`` come out of the
    testbench's own ``dc temp`` sweep. They are the same physical quantity
    reached two different ways, so a disagreement means one of the two
    mechanisms is not doing what the record claims -- the failure mode that
    would otherwise produce confident, wrong TC numbers.
    """
    check = AxisCrossCheck()
    for corner_id, values in sorted(samples.items()):
        key = parse_corner_id(corner_id)
        if key is None or "vref" not in values:
            continue
        column = _SWEEP_COLUMN_AT.get(key.temp_c)
        if column is None or column not in values:
            continue
        delta = abs(values["vref"] - values[column])
        check.n_compared += 1
        if delta > check.worst_delta_v:
            check.worst_delta_v = delta
            check.worst_at = corner_id
    return check


# --- manifest / index consistency -------------------------------------------


def check_limits_match_manifest(line: SpecLine, checks: dict) -> list[str]:
    """Every gated limit must also be a check in the bench's own ``tb.json``.

    The suite index and the manifest hold the same ratified numbers on
    purpose (a bare ``run_corners.py <slug>`` must judge itself against the
    spec too). Duplication without an equality check is how one copy quietly
    gets relaxed, so this asserts they agree -- it is run by the suite's unit
    tests, not only by a human reading both files.
    """
    problems: list[str] = []
    for limit in line.limits:
        spec = checks.get(limit.measurement)
        if spec is None:
            problems.append(
                f"{line.slug}: tb.json has no check for {limit.measurement!r}, but the "
                f"suite gates {line.key} on {limit.describe()}"
            )
            continue
        if limit.kind not in spec:
            problems.append(
                f"{line.slug}: tb.json check for {limit.measurement!r} has no "
                f"{limit.kind!r} bound, but the suite gates {line.key} on "
                f"{limit.describe()}"
            )
            continue
        if abs(float(spec[limit.kind]) - limit.value) > 1e-9:
            problems.append(
                f"{line.slug}: tb.json says {limit.measurement} {limit.kind}="
                f"{spec[limit.kind]}, the suite index says {limit.value} -- the "
                "ratified value must be the same in both"
            )
    return problems
