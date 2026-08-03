"""Combine the two legs of the ratified untrimmed-accuracy row into ONE verdict.

README.md's ratified Output-reference row reads

    1.20 V +/-2% untrimmed (3 sigma, mismatch MC N>=300 **+** process
    corners, -40..125 degC)

and is substantiated by two benches that have, until now, only ever been
judged separately:

- the **process-corner leg**, ``sim/output-voltage-tc/`` -- one deterministic
  ``vref`` per (process, temperature, supply) point, 81 points, global
  process variation and the +/-10% supply axis;
- the **mismatch-MC leg**, ``sim/mc-untrimmed/`` -- the ``mm_all`` group's
  N=300 local-mismatch distribution of ``vref`` at ``tt``/3.30 V, one
  distribution per temperature.

Neither leg alone is the ratified claim: the corner leg has no mismatch and
the MC leg has no process/supply corners. This module states the combination
rule, checks the assumption that rule rests on, and emits one pass/fail per
corner (and a per-temperature roll-up of those).

## Combination rule

For every corner ``c = (process, T, supply)`` of the corner leg, and the
mismatch distribution measured at that same temperature ``T``:

    delta(T)  = mean(mm_all, T) - vref_det(tt_<T>c_3.30v)   # graft offset
    centre(c) = vref_det(c) + delta(T)
    halfwidth = 3 * sigma(mm_all, T)
    PASS(c)  <=> [centre(c) - halfwidth, centre(c) + halfwidth]
                 lies inside [1.176 V, 1.224 V]

i.e. the mismatch distribution measured at ``tt``/nominal supply is grafted
onto every corner's own deterministic operating point, and the ratified
3-sigma window is required to fit inside the ratified +/-2% window **at every
corner**.

``delta(T)`` is defined against the corner leg's own ``tt``/3.30 V point --
the one point both legs simulate -- so that at that corner the combined
interval is *exactly* the mismatch record's own ``mean +/- 3 sigma`` window.
The combined verdict therefore reproduces the MC record's table where the two
overlap, and only ever adds corners on top of it; it never quietly restates
that record's numbers as something else.

## The assumption, and the check that guards it

Grafting one corner's mismatch spread onto every corner assumes local
mismatch is **separable** from global process/supply corner: that the
mismatch-induced perturbation of ``vref`` has (to first order) the same
distribution at ``ss``/2.97 V as it has at ``tt``/3.30 V. That assumption is
not free, and this module does not let it pass silently:

- **Anchor cross-check.** The MC bench's deterministic control group
  (``mm_ctrl``: mismatch off, same DUT, ``tt``/3.30 V) and the corner leg's
  ``tt_<T>c_3.30v`` point are the same physical quantity computed by two
  independent code paths. They must agree to :data:`ANCHOR_TOL_V`. If they do
  not, the two legs are not describing the same circuit and the combined
  verdict is reported ``INVALID`` -- never a silent PASS, and never a FAIL
  blamed on the design. Where the check *can* be evaluated it also splits
  ``delta(T)`` into its two parts: the genuine mismatch-induced mean shift
  (``mean(mm_all) - mean(mm_ctrl)``) and any bench-to-bench disagreement
  (``mean(mm_ctrl) - vref_det(tt)``). The control group is optional evidence,
  not a precondition: a mismatch record whose committed logs do not include
  it still yields a verdict, with the check reported as *not evaluable* --
  stated in the report rather than passed over.
- **Stated, not hidden.** Separability is a first-order approximation: a
  slow-process corner changes ``gm/Id`` at the mirror and amp devices and so
  changes the mismatch gain slightly. Removing the approximation means
  running the MC at every process corner (81 x 300 solves), which is why the
  ratified row is written as MC **+** corners rather than MC-over-corners.
  The approximation is recorded in every report this module writes.

## Why per corner, with a per-temperature roll-up

The primary verdict granularity is **per corner** (81 of them), because that
is the granularity of the leg that actually varies across the matrix: the
process corner is not a distribution to be averaged, it is an enumerated
worst case, and collapsing it to a per-temperature number would throw away
*which* corner binds. The mismatch leg contributes a per-temperature width,
so it enters every corner at that corner's own temperature.

The report additionally rolls the per-corner verdicts up **per temperature**
(worst-margin corner at each of -40/27/125 degC), because the mismatch leg
is measured per temperature and the MC record's own window table is written
that way -- so the two documents can be read against each other line by line.

## Which two records get paired

Both legs default to their newest record, but *not* independently: a
schematic-netlist corner leg grafted with an extracted-netlist mismatch leg is
not two benches disagreeing, it is a category error, and the anchor
cross-check above would report it ``INVALID`` as though the design were at
fault. So :func:`select_records` pairs the legs on a shared **Netlist
provenance** class (``sim/README.md``'s required record field): the newest
record across both benches names the class, and each leg then contributes its
own newest record of that class. When no same-provenance pair exists, the
report states the problem and claims no verdict rather than reporting a
misleading ``INVALID``. An explicit ``--corner-record``/``--mc-record`` pin is
never overridden -- pinning a cross-provenance pair on purpose is allowed, and
labelled as such in the report.

## Reading evidence, never writing it

Like the rest of ``sim/suite``, this module reads the **raw logs** each run
wrote (``sim/<slug>/corners/<record-id>/<corner-id>.log``) and cites the
record that owns them by path. It mutates nothing under ``records/``,
``corners/`` or ``netlist-snapshots/``. Its own report goes to
``sim/suite/combined/<record-id>.md`` and is likewise append-only: a re-run
(for instance once #96's re-centring lands) mints a new report beside the
old one rather than editing it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import math
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from .analysis import parse_corner_id, read_corner_logs

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"
REPORT_DIR = SIM_DIR / "suite" / "combined"

#: The ratified +/-2% untrimmed window, from README.md's Output-reference row.
WINDOW_LO_V = 1.176
WINDOW_HI_V = 1.224

#: The ratified sigma multiple for the mismatch leg ("3 sigma" in the row).
SIGMA_MULTIPLE = 3.0

#: The two benches this verdict is built from.
CORNER_SLUG = "output-voltage-tc"
MC_SLUG = "mc-untrimmed"

#: MC groups (``sim/mc-untrimmed/run_mc_untrimmed.py``'s ``GROUPS``).
MC_CLAIM_GROUP = "mm_all"        # every contributor -- the claim-supporting run
MC_CONTROL_GROUP = "mm_ctrl"     # mismatch off -- the deterministic anchor
MC_RESISTOR_GROUP = "mm_res"     # resistor mismatch only -- the par_r share

#: The measurement each leg contributes.
CORNER_MEASUREMENT = "vref"
MC_SAMPLE = "vref_val"
MC_SUPPLY_SAMPLE = "isup_val"

#: How closely the MC control group and the corner leg's tt/3.30 V point must
#: agree for the graft to be legitimate. Both are an operating point of the
#: same DUT at the same corner reached by two independent code paths; 100 uV
#: is ~0.008% of Vref, far below any effect this verdict resolves, and far
#: above ngspice's own convergence noise between two identical solves.
ANCHOR_TOL_V = 1e-4

#: Multipliers applied to the resistor-mismatch sigma for the ``par_r``
#: sensitivity band (see :func:`par_r_sensitivity`).
PAR_R_FACTORS = (0.5, 2.0)

EXIT_OK = 0
EXIT_SPEC_FAIL = 1
EXIT_EVIDENCE_ERROR = 2

#: ``<name> = <scalar>`` as ngspice's ``print`` writes it inside the MC loop
#: ("vref_val = 1.222330e+00").
_SAMPLE_RE = re.compile(r"^\s*(\w+)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)\s*$")


# --- reading the mismatch leg -----------------------------------------------


def parse_mc_samples(text: str) -> list[dict[str, float]]:
    """Split one Monte Carlo log's repeated ``op``/``print`` blocks into samples.

    A new sample starts whenever a name that has already been seen repeats --
    the same rule ``sim/tools/devchar.py``'s ``parse_op_series`` uses, kept
    local so the suite stays a self-contained reader of raw logs.
    """
    samples: list[dict[str, float]] = []
    current: dict[str, float] = {}
    for raw in text.splitlines():
        match = _SAMPLE_RE.match(raw)
        if not match:
            continue
        name = match.group(1).lower()
        try:
            value = float(match.group(2))
        except ValueError:  # pragma: no cover - the regex constrains this
            continue
        if name in current:
            samples.append(current)
            current = {}
        current[name] = value
    if current:
        samples.append(current)
    return samples


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stdev(values: list[float]) -> float:
    """Sample standard deviation (N-1), the MC record's stated convention."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


@dataclass(frozen=True)
class GroupStats:
    """One MC group at one temperature."""

    group: str
    temp_c: float
    n: int
    mean_v: float
    sigma_v: float

    @property
    def sem_v(self) -> float:
        """Standard error of the mean -- the noise floor on ``mean_v``."""
        return self.sigma_v / math.sqrt(self.n) if self.n else 0.0


def read_mc_groups(corners_dir: Path) -> dict[tuple[str, float], GroupStats]:
    """``{(group, temp_c): GroupStats}`` from one MC record's raw logs.

    The MC bench names its logs with the ordinary ``<corner-id>`` grammar,
    with the *group* in the process field (``mm_all_27c_3.30v.log``), so the
    group and temperature are read back from the filename rather than from
    prose inside the log.
    """
    stats: dict[tuple[str, float], GroupStats] = {}
    if not corners_dir.is_dir():
        return stats
    for log in sorted(corners_dir.glob("*.log")):
        key = parse_corner_id(log.stem)
        if key is None:
            continue
        samples = parse_mc_samples(log.read_text(errors="replace"))
        values = [s[MC_SAMPLE] for s in samples if MC_SAMPLE in s]
        if not values:
            continue
        stats[(key.process, key.temp_c)] = GroupStats(
            group=key.process,
            temp_c=key.temp_c,
            n=len(values),
            mean_v=_mean(values),
            sigma_v=_stdev(values),
        )
    return stats


# --- evidence discovery -----------------------------------------------------


#: ``sim/README.md``'s required **Netlist provenance** field, as
#: ``sim/postlayout_delta.py`` reads it back off a record. Kept identical to
#: that module's pattern on purpose: one convention, one way of reading it.
PROVENANCE_FIELD = re.compile(r"^-\s+\*\*Netlist provenance\*\*:\s*(\S+)")

#: What a record that does not state the field (or cannot be read) reports as.
UNKNOWN_PROVENANCE = "unknown"


@dataclass(frozen=True)
class EvidenceRef:
    """Which record a leg's numbers came from, cited by path."""

    slug: str
    record_id: str
    record: str          # repo-relative path of the .md record
    logs: str            # repo-relative path of the raw-log directory
    live: bool = False   # produced by this very run rather than read back
    #: The record's own **Netlist provenance** class -- ``schematic``,
    #: ``extracted`` or :data:`UNKNOWN_PROVENANCE`.
    provenance: str = UNKNOWN_PROVENANCE

    @property
    def origin(self) -> str:
        return "this run" if self.live else "committed evidence"


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:  # pragma: no cover - only outside a checkout
        return str(path)


def provenance_of_path(record: Path) -> str:
    """The **Netlist provenance** class a record states, or ``unknown``."""
    try:
        text = record.read_text(errors="replace")
    except OSError:
        return UNKNOWN_PROVENANCE
    for line in text.splitlines():
        hit = PROVENANCE_FIELD.match(line)
        if hit:
            return hit.group(1).strip("`*.,;:").lower() or UNKNOWN_PROVENANCE
    return UNKNOWN_PROVENANCE


def record_provenance(slug: str, record_id: str, sim_dir: Path = SIM_DIR) -> str:
    """The provenance class of ``sim/<slug>/records/<record-id>.md``."""
    return provenance_of_path(sim_dir / slug / "records" / f"{record_id}.md")


def _with_live_provenance(ref: EvidenceRef, sim_dir: Path = SIM_DIR) -> EvidenceRef:
    """Read a live run's just-minted record for its provenance class.

    The suite hands the corner leg over as ``live`` evidence (its own run,
    not a record read back), citing the record it just wrote. That record
    states the same **Netlist provenance** field as any other, so the live
    leg can still constrain which mismatch record it may be paired with.
    """
    if not ref.record or ref.provenance != UNKNOWN_PROVENANCE:
        return ref
    candidate = Path(ref.record)
    for base in (REPO_ROOT, sim_dir.parent):
        if candidate.is_absolute():
            break
        if (base / ref.record).is_file():
            candidate = base / ref.record
            break
    if not candidate.is_file():
        return ref
    return replace(ref, provenance=provenance_of_path(candidate))


def record_ids(slug: str, sim_dir: Path = SIM_DIR) -> list[str]:
    """Every ``<record-id>`` under ``sim/<slug>/records/``, oldest first.

    Record ids start with ``<YYYYmmdd>-<HHMMSS>``, so lexical order is
    chronological order.
    """
    return [path.stem for path in sorted((sim_dir / slug / "records").glob("*.md"))]


def latest_record_id(
    slug: str,
    sim_dir: Path = SIM_DIR,
    provenance: str | None = None,
) -> str | None:
    """The newest ``<record-id>`` under ``sim/<slug>/records/``.

    Picking the newest automatically is what makes this verdict re-runnable:
    when a re-centring fix mints new records for either bench, a bare re-run
    reports against them with no argument changes. Pass ``provenance`` to
    restrict the search to one netlist-provenance class, which is how
    :func:`select_records` keeps the two legs describing the same circuit.
    """
    ids = record_ids(slug, sim_dir)
    if provenance is not None:
        ids = [rid for rid in ids if record_provenance(slug, rid, sim_dir) == provenance]
    return ids[-1] if ids else None


def evidence_for(
    slug: str,
    record_id: str | None = None,
    sim_dir: Path = SIM_DIR,
) -> EvidenceRef | None:
    """Locate one bench's record + raw logs, defaulting to its newest record.

    Defaulting here is deliberately *per leg* and provenance-blind; pairing the
    two legs is :func:`select_records`'s job, and :func:`load` goes through it.
    """
    resolved = record_id or latest_record_id(slug, sim_dir)
    if resolved is None:
        return None
    record = sim_dir / slug / "records" / f"{resolved}.md"
    logs = sim_dir / slug / "corners" / resolved
    if not record.is_file() or not logs.is_dir():
        return None
    return EvidenceRef(
        slug=slug,
        record_id=resolved,
        record=_repo_relative(record),
        logs=_repo_relative(logs),
        provenance=provenance_of_path(record),
    )


# --- pairing the two legs by netlist provenance -----------------------------


@dataclass(frozen=True)
class RecordPair:
    """Which record each leg contributes, and on what provenance class.

    The two legs are only a verdict when they describe the *same circuit*: a
    schematic-netlist corner leg grafted with an extracted-netlist mismatch
    leg is not a bench disagreement, it is a category error, and the anchor
    cross-check would report it as ``INVALID`` as if the design were at
    fault. So record selection is pairing, not two independent "newest of
    each" lookups.
    """

    corner_record: str | None
    mc_record: str | None
    corner_provenance: str | None
    mc_provenance: str | None
    #: The class both legs were matched on, or ``None`` when they were not.
    matched: str | None = None
    #: Fatal: no same-provenance pair could be formed without an explicit pin.
    problems: list[str] = field(default_factory=list)

    @property
    def cross_provenance(self) -> bool:
        """Do the two legs' records state *different* provenance classes?"""
        return (
            self.corner_provenance is not None
            and self.mc_provenance is not None
            and self.corner_provenance != self.mc_provenance
        )


def _pin_mismatch_problem(
    pinned_slug: str, pinned_class: str, free_slug: str, free_class: str | None
) -> str:
    have = (
        f"its newest record is **{free_class}**-provenance"
        if free_class
        else "it has no readable records"
    )
    return (
        f"the pinned `sim/{pinned_slug}/` record is **{pinned_class}**-provenance "
        f"but `sim/{free_slug}/` has no record of that class ({have}) -- the two "
        "legs would not describe the same circuit, so pin the other leg "
        "explicitly (`--corner-record`/`--mc-record`) to state which comparison "
        "is intended, or re-run that bench against the same netlist"
    )


def select_records(
    corner_record: str | None = None,
    mc_record: str | None = None,
    sim_dir: Path = SIM_DIR,
    corner_provenance: str | None = None,
    live_corner: bool = False,
) -> RecordPair:
    """Choose one record per leg, preferring a **same-provenance** pair.

    The rules, in order:

    1. An explicit ``--corner-record``/``--mc-record`` pin is never
       overridden -- pinning stays an unconditional override.
    2. When one leg is fixed (pinned, or supplied live by the running suite
       via ``live_corner``/``corner_provenance``), the other leg defaults to
       its newest record *of that same provenance class*.
    3. When neither leg is fixed, the newest record across both legs names
       the class -- the freshest evidence wins -- and each leg then
       contributes its newest record of that class. Classes only one leg has
       are skipped, so a bench that has not been re-run post-layout does not
       drag the other leg's extracted record into a cross-provenance pair.
    4. If no same-provenance pair exists at all, each leg falls back to its
       own newest record (today's behaviour, so the report can still cite
       what it found) **and a problem is reported** -- the caller gets a
       clear "pin these explicitly" diagnostic rather than a bare ``INVALID``
       that reads as a genuine bench disagreement.
    """
    corner_ids = record_ids(CORNER_SLUG, sim_dir)
    mc_ids = record_ids(MC_SLUG, sim_dir)
    live_corner = live_corner or corner_provenance is not None

    corner_class: str | None = corner_provenance
    if not live_corner and corner_record:
        corner_class = record_provenance(CORNER_SLUG, corner_record, sim_dir)
    mc_class: str | None = (
        record_provenance(MC_SLUG, mc_record, sim_dir) if mc_record else None
    )

    def pair(
        corner_id: str | None,
        mc_id: str | None,
        problems: list[str] | None = None,
    ) -> RecordPair:
        c_class = corner_class if live_corner or corner_id is None else record_provenance(
            CORNER_SLUG, corner_id, sim_dir
        )
        m_class = mc_class if mc_id is None else record_provenance(MC_SLUG, mc_id, sim_dir)
        matched = c_class if c_class is not None and c_class == m_class else None
        return RecordPair(
            corner_record=corner_id,
            mc_record=mc_id,
            corner_provenance=c_class,
            mc_provenance=m_class,
            matched=matched,
            problems=problems or [],
        )

    # 1. both legs fixed -- honour the pins exactly, whatever they pair.
    if (live_corner or corner_record) and mc_record:
        return pair(None if live_corner else corner_record, mc_record)

    # 2. one leg fixed -- the other matches its class when it can.
    if live_corner or corner_record:
        if corner_class is None:
            # A live corner leg whose record does not state the field: there
            # is no class to match on, so fall back to the newest MC record
            # rather than invent a constraint.
            return pair(None, mc_ids[-1] if mc_ids else None)
        chosen = latest_record_id(MC_SLUG, sim_dir, provenance=corner_class)
        if chosen is not None:
            return pair(None if live_corner else corner_record, chosen)
        fallback = mc_ids[-1] if mc_ids else None
        problems = (
            [
                _pin_mismatch_problem(
                    CORNER_SLUG,
                    corner_class,
                    MC_SLUG,
                    record_provenance(MC_SLUG, fallback, sim_dir) if fallback else None,
                )
            ]
            if fallback
            else []  # a wholly missing leg is already reported by load()
        )
        return pair(None if live_corner else corner_record, fallback, problems)

    if mc_record:
        assert mc_class is not None
        chosen = latest_record_id(CORNER_SLUG, sim_dir, provenance=mc_class)
        if chosen is not None:
            return pair(chosen, mc_record)
        fallback = corner_ids[-1] if corner_ids else None
        problems = (
            [
                _pin_mismatch_problem(
                    MC_SLUG,
                    mc_class,
                    CORNER_SLUG,
                    record_provenance(CORNER_SLUG, fallback, sim_dir)
                    if fallback
                    else None,
                )
            ]
            if fallback
            else []
        )
        return pair(fallback, mc_record, problems)

    # 3. neither leg fixed -- the newest record across both legs names the
    #    class, and both legs then contribute their newest record of it.
    both: list[tuple[str, str, str]] = [  # (record-id, slug, class)
        (rid, CORNER_SLUG, record_provenance(CORNER_SLUG, rid, sim_dir))
        for rid in corner_ids
    ] + [(rid, MC_SLUG, record_provenance(MC_SLUG, rid, sim_dir)) for rid in mc_ids]
    for _, _, klass in sorted(both, key=lambda item: item[0], reverse=True):
        corner_id = latest_record_id(CORNER_SLUG, sim_dir, provenance=klass)
        mc_id = latest_record_id(MC_SLUG, sim_dir, provenance=klass)
        if corner_id is not None and mc_id is not None:
            return pair(corner_id, mc_id)

    # 4. no same-provenance pair exists: cite the newest of each, and say so.
    corner_id = corner_ids[-1] if corner_ids else None
    mc_id = mc_ids[-1] if mc_ids else None
    problems = []
    if corner_id and mc_id:
        problems.append(
            "the two legs have no same-provenance pair of records: "
            f"`sim/{CORNER_SLUG}/`'s newest is "
            f"**{record_provenance(CORNER_SLUG, corner_id, sim_dir)}**-provenance "
            f"(`{corner_id}`) and `sim/{MC_SLUG}/`'s newest is "
            f"**{record_provenance(MC_SLUG, mc_id, sim_dir)}**-provenance "
            f"(`{mc_id}`), and neither bench has a record of the other's class. "
            "Combining them would graft a mismatch distribution measured on one "
            "netlist onto corners measured on another, so no verdict is claimed "
            "here -- pin `--corner-record`/`--mc-record` explicitly if a "
            "cross-provenance comparison is what you intend, or re-run one bench "
            "against the other's netlist"
        )
    return pair(corner_id, mc_id, problems)


# --- the combination itself -------------------------------------------------


@dataclass(frozen=True)
class MismatchLeg:
    """The mismatch distribution the combination grafts onto every corner."""

    temp_c: float
    n: int
    mean_v: float
    sigma_v: float
    anchor_v: float                       # corner leg's own tt/3.30 V point
    control_v: float | None = None        # mm_ctrl, when its logs are present
    resistor_sigma_v: float | None = None

    @property
    def offset_v(self) -> float:
        """``delta(T)`` -- the graft offset applied to every corner."""
        return self.mean_v - self.anchor_v

    @property
    def mismatch_shift_v(self) -> float | None:
        """The part of ``delta`` that is a genuine mismatch mean shift."""
        return None if self.control_v is None else self.mean_v - self.control_v

    @property
    def sem_v(self) -> float:
        return self.sigma_v / math.sqrt(self.n) if self.n else 0.0

    @property
    def halfwidth_v(self) -> float:
        return SIGMA_MULTIPLE * self.sigma_v

    @property
    def offset_is_noise(self) -> bool:
        """Is the measured offset within 2 standard errors of zero?"""
        return abs(self.offset_v) <= 2 * self.sem_v


@dataclass(frozen=True)
class AnchorCheck:
    """MC control group vs the corner leg's tt/nominal point, per temperature."""

    temp_c: float
    corner_v: float
    corner_id: str
    control_v: float | None = None

    @property
    def evaluable(self) -> bool:
        return self.control_v is not None

    @property
    def delta_v(self) -> float | None:
        return None if self.control_v is None else self.control_v - self.corner_v

    @property
    def agrees(self) -> bool:
        """False only when the check ran and failed (not when it could not run)."""
        return self.delta_v is None or abs(self.delta_v) <= ANCHOR_TOL_V

    @property
    def status(self) -> str:
        if not self.evaluable:
            return "not evaluable"
        return "yes" if self.agrees else "NO"


@dataclass(frozen=True)
class CornerVerdict:
    """One corner of the corner leg, judged with the mismatch spread applied."""

    corner_id: str
    temp_c: float
    deterministic_v: float
    offset_v: float
    halfwidth_v: float

    @property
    def centre_v(self) -> float:
        return self.deterministic_v + self.offset_v

    @property
    def low_v(self) -> float:
        return self.centre_v - self.halfwidth_v

    @property
    def high_v(self) -> float:
        return self.centre_v + self.halfwidth_v

    @property
    def margin_v(self) -> float:
        """Distance to the nearer window edge; negative means outside it."""
        return min(self.low_v - WINDOW_LO_V, WINDOW_HI_V - self.high_v)

    @property
    def binding_edge(self) -> str:
        return "lower" if (self.low_v - WINDOW_LO_V) < (WINDOW_HI_V - self.high_v) else "upper"

    @property
    def status(self) -> str:
        return "PASS" if self.margin_v >= 0 else "FAIL"

    @property
    def corner_only_status(self) -> str:
        """What the corner leg alone said -- for leg-by-leg attribution."""
        inside = WINDOW_LO_V <= self.deterministic_v <= WINDOW_HI_V
        return "PASS" if inside else "FAIL"


@dataclass
class TemperatureRollup:
    """The per-corner verdicts at one temperature, worst corner governing."""

    temp_c: float
    verdicts: list[CornerVerdict] = field(default_factory=list)

    @property
    def worst(self) -> CornerVerdict | None:
        return min(self.verdicts, key=lambda v: v.margin_v) if self.verdicts else None

    @property
    def n_fail(self) -> int:
        return sum(1 for v in self.verdicts if v.status == "FAIL")

    @property
    def status(self) -> str:
        if not self.verdicts:
            return "NO DATA"
        return "FAIL" if self.n_fail else "PASS"


@dataclass(frozen=True)
class ParRSensitivity:
    """How much the verdict moves if the ``par_r`` coefficient is wrong.

    ``sim/mc-untrimmed`` sources its resistor-mismatch sigma from a
    Pelgrom-style coefficient (``par_r = 0.021``) that ships **commented out**
    in gf180mcu's ``ppolyf_u`` model, so it is an assumption rather than a
    validated number. This scales that one contributor and re-judges, so the
    risk it carries is quantified rather than merely named.
    """

    factor: float
    temp_c: float
    halfwidth_v: float
    n_fail: int
    n_corners: int

    @property
    def verdict(self) -> str:
        return "FAIL" if self.n_fail else "PASS"


@dataclass
class CombinedVerdict:
    """One verdict on the ratified untrimmed-accuracy row, both legs applied."""

    legs: dict[float, MismatchLeg] = field(default_factory=dict)
    verdicts: list[CornerVerdict] = field(default_factory=list)
    rollups: list[TemperatureRollup] = field(default_factory=list)
    anchors: list[AnchorCheck] = field(default_factory=list)
    sensitivity: list[ParRSensitivity] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    corner_evidence: EvidenceRef | None = None
    mc_evidence: EvidenceRef | None = None
    #: The netlist-provenance class both legs were matched on, when they were
    #: (``None`` when the two records state different classes).
    matched_provenance: str | None = None
    #: Fatal: a leg could not be read at all, so there is no verdict to give.
    problems: list[str] = field(default_factory=list)
    #: Non-fatal: coverage the two legs do not share (e.g. a temperature one
    #: leg measured and the other did not). Reported, not silently dropped.
    notes: list[str] = field(default_factory=list)

    @property
    def cross_provenance(self) -> bool:
        """Were the two legs read from records of *different* netlist provenance?

        Only ever true when the caller pinned such a pair explicitly, or when
        no same-provenance pair exists at all (in which case a problem is
        reported too): the default selection refuses to form one silently
        (see :func:`select_records`). A record that does not state the field
        is *unknown*, not different -- that is a reporting gap, not a
        cross-provenance comparison.
        """
        if self.corner_evidence is None or self.mc_evidence is None:
            return False
        classes = {self.corner_evidence.provenance, self.mc_evidence.provenance}
        return UNKNOWN_PROVENANCE not in classes and len(classes) > 1

    @property
    def anchors_agree(self) -> bool:
        """True unless a check that could be evaluated actually disagreed."""
        return all(a.agrees for a in self.anchors)

    @property
    def anchors_evaluated(self) -> int:
        return sum(1 for a in self.anchors if a.evaluable)

    @property
    def n_fail(self) -> int:
        return sum(1 for v in self.verdicts if v.status == "FAIL")

    @property
    def status(self) -> str:
        if self.problems or not self.verdicts:
            return "NO DATA"
        if not self.anchors_agree:
            # The graft's own precondition failed: report the methodology as
            # broken rather than reporting a verdict it cannot support.
            return "INVALID"
        return "FAIL" if self.n_fail else "PASS"

    @property
    def worst(self) -> CornerVerdict | None:
        return min(self.verdicts, key=lambda v: v.margin_v) if self.verdicts else None


def anchor_corner_id(temp_c: float) -> str:
    """The corner both legs simulate: ``tt`` process, nominal 3.30 V supply."""
    return f"tt_{temp_c:g}c_3.30v"


def build_legs(
    mc_stats: dict[tuple[str, float], GroupStats],
    corner_samples: dict[str, dict[str, float]],
) -> tuple[dict[float, MismatchLeg], list[AnchorCheck], list[str], list[str]]:
    """Per-temperature mismatch legs, anchored on the corner leg's tt point."""
    legs: dict[float, MismatchLeg] = {}
    anchors: list[AnchorCheck] = []
    problems: list[str] = []
    notes: list[str] = []
    temps = sorted({temp for group, temp in mc_stats if group == MC_CLAIM_GROUP})
    if not temps:
        problems.append(
            f"the mismatch leg has no `{MC_CLAIM_GROUP}` group logs -- without the "
            "claim-supporting group there is no distribution to combine"
        )
    for temp in temps:
        claim = mc_stats[(MC_CLAIM_GROUP, temp)]
        corner_id = anchor_corner_id(temp)
        anchor_values = corner_samples.get(corner_id, {})
        if CORNER_MEASUREMENT not in anchor_values:
            notes.append(
                f"no `{corner_id}` point in the process-corner leg -- the mismatch "
                f"distribution measured at {temp:g} degC has no shared corner to be "
                "grafted onto, so it is not combined"
            )
            continue
        control = mc_stats.get((MC_CONTROL_GROUP, temp))
        resistor = mc_stats.get((MC_RESISTOR_GROUP, temp))
        legs[temp] = MismatchLeg(
            temp_c=temp,
            n=claim.n,
            mean_v=claim.mean_v,
            sigma_v=claim.sigma_v,
            anchor_v=anchor_values[CORNER_MEASUREMENT],
            control_v=control.mean_v if control else None,
            resistor_sigma_v=resistor.sigma_v if resistor else None,
        )
        anchors.append(
            AnchorCheck(
                temp_c=temp,
                corner_v=anchor_values[CORNER_MEASUREMENT],
                corner_id=corner_id,
                control_v=control.mean_v if control else None,
            )
        )
    return legs, anchors, problems, notes


def par_r_sensitivity(
    legs: dict[float, MismatchLeg],
    verdicts: list[CornerVerdict],
) -> list[ParRSensitivity]:
    """Re-judge every corner with the resistor-mismatch sigma scaled up/down.

    The resistor contribution enters the measured all-on variance as its own
    (approximately independent) term, so scaling ``par_r`` by ``k`` gives

        sigma_all(k)^2 = sigma_all^2 + (k^2 - 1) * sigma_res^2

    -- anchored on the *measured* all-on sigma rather than on a reconstructed
    quadrature sum, so the correction only ever moves the one contributor
    whose coefficient is in doubt.
    """
    results: list[ParRSensitivity] = []
    for factor in PAR_R_FACTORS:
        for temp in sorted(legs):
            leg = legs[temp]
            if leg.resistor_sigma_v is None:
                continue
            variance = leg.sigma_v**2 + (factor**2 - 1) * leg.resistor_sigma_v**2
            sigma = math.sqrt(max(variance, 0.0))
            halfwidth = SIGMA_MULTIPLE * sigma
            at_temp = [v for v in verdicts if v.temp_c == temp]
            scaled = [
                CornerVerdict(
                    corner_id=v.corner_id,
                    temp_c=v.temp_c,
                    deterministic_v=v.deterministic_v,
                    offset_v=v.offset_v,
                    halfwidth_v=halfwidth,
                )
                for v in at_temp
            ]
            results.append(
                ParRSensitivity(
                    factor=factor,
                    temp_c=temp,
                    halfwidth_v=halfwidth,
                    n_fail=sum(1 for v in scaled if v.status == "FAIL"),
                    n_corners=len(scaled),
                )
            )
    return results


def evaluate(
    corner_samples: dict[str, dict[str, float]],
    mc_stats: dict[tuple[str, float], GroupStats],
) -> CombinedVerdict:
    """Judge the ratified accuracy row with both legs applied together."""
    combined = CombinedVerdict()
    if not corner_samples:
        combined.problems.append(
            f"the process-corner leg has no `{CORNER_MEASUREMENT}` logs to read"
        )
        return combined
    (
        combined.legs,
        combined.anchors,
        combined.problems,
        combined.notes,
    ) = build_legs(mc_stats, corner_samples)

    for corner_id, values in sorted(corner_samples.items()):
        key = parse_corner_id(corner_id)
        if key is None or CORNER_MEASUREMENT not in values:
            combined.skipped.append(f"{corner_id} (no `{CORNER_MEASUREMENT}` measurement)")
            continue
        leg = combined.legs.get(key.temp_c)
        if leg is None:
            combined.skipped.append(
                f"{corner_id} (no mismatch distribution measured at {key.temp_c:g} degC)"
            )
            continue
        combined.verdicts.append(
            CornerVerdict(
                corner_id=corner_id,
                temp_c=key.temp_c,
                deterministic_v=values[CORNER_MEASUREMENT],
                offset_v=leg.offset_v,
                halfwidth_v=leg.halfwidth_v,
            )
        )

    for temp in sorted(combined.legs):
        rollup = TemperatureRollup(temp_c=temp)
        rollup.verdicts = [v for v in combined.verdicts if v.temp_c == temp]
        combined.rollups.append(rollup)

    combined.sensitivity = par_r_sensitivity(combined.legs, combined.verdicts)
    return combined


# --- rendering --------------------------------------------------------------


def _mv(volts: float) -> str:
    return f"{volts * 1e3:.3f}"


def render(
    combined: CombinedVerdict,
    started: _dt.datetime | None = None,
    git: dict | None = None,
) -> str:
    """The combined-verdict report, as Markdown."""
    started = started or _dt.datetime.now(_dt.timezone.utc)
    git = git or {}
    lines: list[str] = [
        f"# Combined untrimmed-accuracy verdict "
        f"{started.strftime('%Y%m%d-%H%M%S')}-{git.get('short', 'unknown')}",
        "",
        "- **Claim**: `README.md#target-specification` -- Output reference row, "
        "\"1.20 V +/-2% untrimmed (3 sigma, mismatch MC N>=300 **+** process "
        "corners, -40..125 degC)\" (ratified "
        "`spec/decision-records/0003-target-spec-ratification.md`). This report "
        "is the **combination** of that row's two legs into one verdict; it "
        "runs no simulation of its own.",
        f"- **Generated**: {started.isoformat(timespec='seconds')} by "
        "`sim/run_combined_accuracy.py`",
        f"- **git**: `{git.get('commit', 'unknown')}` on `{git.get('branch', 'unknown')}`"
        + (" (dirty)" if git.get("dirty") else " (clean)"),
        "",
        "## Legs combined (evidence, by path)",
        "",
        "| Leg | Bench | Record | Netlist provenance | Raw logs | Source |",
        "|---|---|---|---|---|---|",
    ]
    for label, ref in (
        ("process corners", combined.corner_evidence),
        ("mismatch MC", combined.mc_evidence),
    ):
        if ref is None:
            lines.append(f"| {label} | — | **missing** | — | — | — |")
            continue
        record = (
            f"[`{ref.record}`]({_relative_link(ref.record)})"
            if ref.record
            else "not recorded (`--no-write` run)"
        )
        logs = f"`{ref.logs}/`" if ref.logs else "—"
        provenance = (
            "not stated"
            if ref.provenance == UNKNOWN_PROVENANCE
            else f"**{ref.provenance}**"
        )
        lines.append(
            f"| {label} | `{ref.slug}` | {record} | {provenance} | {logs} "
            f"| {ref.origin} |"
        )
    lines += _provenance_pairing_lines(combined)

    lines += ["", "## Verdict", ""]
    headline = {
        "PASS": "**PASS** — at every corner, the mismatch distribution's full "
        f"{SIGMA_MULTIPLE:g}-sigma width fits inside the ratified "
        f"{WINDOW_LO_V:.3f}–{WINDOW_HI_V:.3f} V window.",
        "FAIL": None,  # filled in below with the count
        "INVALID": "**INVALID** — the anchor cross-check below failed, so the "
        "two legs are not describing the same circuit and no combined verdict "
        "is claimed from them."
        + (
            " The two records were pinned to **different** netlist provenance "
            "classes, which is reason enough for the check to fail: read the "
            "disagreement as the pairing's, not the design's."
            if combined.cross_provenance
            else ""
        ),
        "NO DATA": "**NO DATA** — one or both legs could not be read, or the two "
        "legs could not be paired on a shared netlist provenance; see the "
        "problems listed below.",
    }[combined.status]
    if combined.status == "FAIL":
        headline = (
            f"**FAIL** — {combined.n_fail} of {len(combined.verdicts)} corners put "
            f"part of the {SIGMA_MULTIPLE:g}-sigma mismatch distribution outside the "
            f"ratified {WINDOW_LO_V:.3f}–{WINDOW_HI_V:.3f} V window."
        )
    lines.append(headline)

    if combined.problems:
        lines += ["", "Problems reading the evidence:", ""]
        lines += [f"- {problem}" for problem in combined.problems]
    if combined.notes:
        lines += ["", "Coverage the two legs do not share:", ""]
        lines += [f"- {note}" for note in combined.notes]

    lines += _rollup_section(combined)
    lines += _leg_section(combined)
    lines += _anchor_section(combined)
    lines += _corner_section(combined)
    lines += _sensitivity_section(combined)
    lines += _methodology_section(combined)
    return "\n".join(lines) + "\n"


def _relative_link(repo_relative: str) -> str:
    """Link from ``sim/suite/combined/<file>.md`` back to a repo path."""
    return "../../../" + repo_relative


def _provenance_pairing_lines(combined: CombinedVerdict) -> list[str]:
    """State, in the report, which provenance class the two legs were paired on.

    Without this a reader has to open both records to find out whether the
    comparison was apples-to-apples -- the exact thing that made a
    cross-provenance pairing readable as a bench disagreement.
    """
    if combined.corner_evidence is None or combined.mc_evidence is None:
        return []
    if combined.cross_provenance:
        return [
            "",
            "**Provenance pairing: CROSS-PROVENANCE.** The process-corner leg is "
            f"**{combined.corner_evidence.provenance}**-netlist evidence and the "
            f"mismatch leg is **{combined.mc_evidence.provenance}**-netlist "
            "evidence, so the two legs do not describe the same circuit. Their "
            "anchor cross-check disagrees by construction; nothing below should "
            "be read as a disagreement between the two benches, still less as a "
            "property of the design.",
        ]
    if combined.matched_provenance == UNKNOWN_PROVENANCE:
        return [
            "",
            "**Provenance pairing: not stated.** Neither record carries the "
            "**Netlist provenance** field `sim/README.md` requires, so the two "
            "legs could not be confirmed to describe the same circuit.",
        ]
    if combined.matched_provenance is None:
        return [
            "",
            "**Provenance pairing: unconfirmed.** Only one of the two legs states "
            "a **Netlist provenance** class, so the pairing could not be checked.",
        ]
    return [
        "",
        f"**Provenance pairing: {combined.matched_provenance}.** Both legs were "
        f"matched on the same **{combined.matched_provenance}**-netlist "
        "provenance class (`sim/README.md`'s **Netlist provenance** field), so "
        "the two legs describe the same circuit and the graft below is "
        "apples-to-apples.",
    ]


def _rollup_section(combined: CombinedVerdict) -> list[str]:
    if not combined.rollups:
        return []
    lines = [
        "",
        "### Per temperature (worst corner governs)",
        "",
        "| T (degC) | corners | failing | worst corner | combined 3-sigma interval (V) "
        "| margin to window (mV) | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for rollup in combined.rollups:
        worst = rollup.worst
        if worst is None:
            lines.append(
                f"| {rollup.temp_c:g} | 0 | — | — | — | — | NO DATA |"
            )
            continue
        lines.append(
            f"| {rollup.temp_c:g} | {len(rollup.verdicts)} | {rollup.n_fail} "
            f"| `{worst.corner_id}` "
            f"| [{worst.low_v:.5f}, {worst.high_v:.5f}] "
            f"| {_mv(worst.margin_v)} ({worst.binding_edge} edge) "
            f"| {rollup.status} |"
        )
    return lines


def _leg_section(combined: CombinedVerdict) -> list[str]:
    if not combined.legs:
        return []
    lines = [
        "",
        "### The mismatch leg, as grafted onto each corner",
        "",
        "| T (degC) | N | `mm_all` mean (V) | anchor `tt`/3.30 V (V) | graft offset "
        "delta (mV) | s.e.m. (mV) | 1 sigma (mV) | 3 sigma half-width (mV) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for temp in sorted(combined.legs):
        leg = combined.legs[temp]
        note = " (noise)" if leg.offset_is_noise else " (resolved)"
        lines.append(
            f"| {temp:g} | {leg.n} | {leg.mean_v:.5f} | {leg.anchor_v:.5f} "
            f"| {_mv(leg.offset_v)}{note} | {_mv(leg.sem_v)} "
            f"| {_mv(leg.sigma_v)} | {_mv(leg.halfwidth_v)} |"
        )
    shifts = [
        (temp, leg.mismatch_shift_v)
        for temp, leg in sorted(combined.legs.items())
        if leg.mismatch_shift_v is not None
    ]
    lines += [
        "",
        "`graft offset delta` is `mean(mm_all) - vref_det(tt/3.30 V)`: the shift "
        "applied to every corner's deterministic value so that the combined "
        "interval at `tt`/3.30 V is exactly the mismatch record's own "
        "`mean +/- 3 sigma` window. It is marked `(noise)` when it is within two "
        "standard errors of zero, i.e. not distinguishable from Monte Carlo "
        "sampling noise at this N.",
    ]
    if shifts:
        lines += [
            "",
            "Where the control group is present, the offset separates into a "
            "mismatch-induced mean shift (`mean(mm_all) - mean(mm_ctrl)`) and a "
            "bench-to-bench residual (the anchor check below): "
            + ", ".join(f"{temp:g} degC {_mv(shift)} mV" for temp, shift in shifts)
            + " of mismatch shift.",
        ]
    return lines


def _anchor_section(combined: CombinedVerdict) -> list[str]:
    if not combined.anchors:
        return []
    lines = [
        "",
        "### Anchor cross-check (the graft's precondition)",
        "",
        "The MC bench's deterministic control (`mm_ctrl`, mismatch off) and the "
        "corner leg's `tt/3.30 V` point are the same operating point reached by "
        "two independent code paths. Grafting one bench's spread onto the other "
        "bench's corners is only legitimate if they agree.",
        "",
        "| T (degC) | `mm_ctrl` (V) | corner leg (V) | corner-id | delta (uV) | agrees? |",
        "|---|---|---|---|---|---|",
    ]
    for anchor in combined.anchors:
        control = f"{anchor.control_v:.6f}" if anchor.evaluable else "—"
        delta = f"{anchor.delta_v * 1e6:.2f}" if anchor.delta_v is not None else "—"
        lines.append(
            f"| {anchor.temp_c:g} | {control} | {anchor.corner_v:.6f} "
            f"| `{anchor.corner_id}` | {delta} | {anchor.status} |"
        )
    lines += [
        "",
        f"Tolerance: {ANCHOR_TOL_V * 1e6:.0f} uV. A disagreement makes the "
        "combined verdict `INVALID` rather than FAIL: it would mean the two "
        "legs are not describing the same circuit, which is a bench problem, "
        "not a design result.",
    ]
    not_evaluable = [a for a in combined.anchors if not a.evaluable]
    if not_evaluable:
        lines += [
            "",
            "**Not evaluable at "
            + ", ".join(f"{a.temp_c:g} degC" for a in not_evaluable)
            + f"**: the mismatch record's committed logs contain no "
            f"`{MC_CONTROL_GROUP}` group at "
            + ("those temperatures" if len(not_evaluable) > 1 else "that temperature")
            + ". The combined verdict still stands (the graft is anchored on the "
            "corner leg's own `tt`/3.30 V point either way), but any "
            "bench-to-bench disagreement would be absorbed into the graft offset "
            "instead of being caught here. Pin an older record with "
            f"`--mc-record <id>` to re-run the check against a record whose "
            "control-group logs are present.",
        ]
    return lines


def _corner_section(combined: CombinedVerdict) -> list[str]:
    if not combined.verdicts:
        return []
    lines = [
        "",
        "### Per corner (the primary verdict)",
        "",
        "| corner-id | deterministic Vref (V) | combined interval (V) "
        "| margin (mV) | corner leg alone | combined |",
        "|---|---|---|---|---|---|",
    ]
    for verdict in sorted(combined.verdicts, key=lambda v: v.corner_id):
        lines.append(
            f"| `{verdict.corner_id}` | {verdict.deterministic_v:.5f} "
            f"| [{verdict.low_v:.5f}, {verdict.high_v:.5f}] "
            f"| {_mv(verdict.margin_v)} | {verdict.corner_only_status} "
            f"| {verdict.status} |"
        )
    corner_only_fail = sum(1 for v in combined.verdicts if v.corner_only_status == "FAIL")
    lines += [
        "",
        f"Attribution: {corner_only_fail} of {len(combined.verdicts)} corners already "
        f"fail on the deterministic corner value alone; the combined verdict fails "
        f"at {combined.n_fail}. The difference is the mismatch leg's contribution — "
        "corners whose deterministic value sits inside the window but whose "
        f"{SIGMA_MULTIPLE:g}-sigma mismatch skirt does not.",
    ]
    if combined.skipped:
        lines += [
            "",
            "Corners not judged (no matching evidence in the other leg):",
            "",
        ]
        lines += [f"- `{item}`" for item in combined.skipped]
    return lines


def _sensitivity_section(combined: CombinedVerdict) -> list[str]:
    if not combined.sensitivity:
        if not combined.legs:
            return []
        return [
            "",
            "### `par_r` sensitivity (the named methodology risk)",
            "",
            f"**Not evaluable from this record**: the mismatch record's committed "
            f"logs contain no `{MC_RESISTOR_GROUP}` group, so the resistor share of "
            "the measured spread — the share the assumed `par_r = 0.021` "
            "coefficient governs — cannot be scaled and re-judged here. Pin a "
            "record whose resistor-only group logs are present with "
            "`--mc-record <id>` to bound the risk quantitatively; the accepted "
            "bound is recorded in "
            "`spec/decision-records/0004-par-r-mismatch-coefficient-risk.md`.",
        ]
    lines = [
        "",
        "### `par_r` sensitivity (the named methodology risk)",
        "",
        "The mismatch leg's resistor sigma comes from gf180mcu's own "
        "Pelgrom-style coefficient `par_r = 0.021`, which ships **commented "
        "out** in the `ppolyf_u` model and is therefore an assumption, not a "
        "validated number (`spec/decision-records/0004-par-r-mismatch-"
        "coefficient-risk.md`). Scaling only that contributor bounds what the "
        "assumption can cost:",
        "",
        "| par_r factor | T (degC) | 3 sigma half-width (mV) | failing corners | verdict |",
        "|---|---|---|---|---|",
    ]
    for item in sorted(combined.sensitivity, key=lambda s: (s.factor, s.temp_c)):
        lines.append(
            f"| x{item.factor:g} | {item.temp_c:g} | {_mv(item.halfwidth_v)} "
            f"| {item.n_fail}/{item.n_corners} | {item.verdict} |"
        )
    baseline = {
        temp: leg.halfwidth_v for temp, leg in combined.legs.items()
    }
    unchanged = all(
        item.n_fail == sum(
            1 for v in combined.verdicts if v.temp_c == item.temp_c and v.status == "FAIL"
        )
        for item in combined.sensitivity
    )
    lines += [
        "",
        "Baseline half-widths for comparison: "
        + ", ".join(f"{temp:g} degC {_mv(width)} mV" for temp, width in sorted(baseline.items()))
        + ".",
        "",
        (
            "**No corner's verdict changes** under either scaling, so the combined "
            "verdict does not currently rest on the exact value of `par_r`."
            if unchanged
            else "**At least one corner's verdict changes** under this scaling — the "
            "combined verdict is sensitive to `par_r` and the coefficient must be "
            "validated before the verdict is treated as final."
        ),
    ]
    return lines


def _methodology_section(combined: CombinedVerdict) -> list[str]:
    return [
        "",
        "## Methodology (and its stated approximation)",
        "",
        "**Granularity: per corner, rolled up per temperature.** The primary "
        "verdict is one pass/fail per corner of the process-corner leg, because "
        "the process corner is an enumerated worst case rather than a "
        "distribution — collapsing it to a per-temperature number would hide "
        "*which* corner binds. The mismatch leg is measured per temperature, so "
        "it enters each corner at that corner's own temperature; the "
        "per-temperature table is the worst-margin corner at each of "
        "-40/27/125 degC, in the same shape as the MC record's own window table.",
        "",
        "**The rule.** For each corner `c` at temperature `T`:",
        "",
        "```",
        "centre(c) = vref_det(c) + delta(T)                  # corner leg + graft offset",
        "delta(T)  = mean(mm_all, T) - vref_det(tt_<T>c_3.30v)  # anchored on the corner",
        "                                                    # leg's own tt/3.30 V point",
        f"half(T)   = {SIGMA_MULTIPLE:g} * sigma(mm_all, T)"
        "                    # the ratified 3-sigma width",
        f"PASS(c)  <=> [centre - half, centre + half] within "
        f"[{WINDOW_LO_V:.3f}, {WINDOW_HI_V:.3f}] V",
        "```",
        "",
        "`delta` is anchored on the corner leg's own `tt`/3.30 V point — the one "
        "point both benches simulate — so the combined interval at that corner "
        "*is* the mismatch record's own `mean +/- 3 sigma` window rather than a "
        "restatement of it. The MC bench's deterministic control group "
        f"(`{MC_CONTROL_GROUP}`) never enters the graft; it is used only by the "
        "anchor cross-check above, and the combined verdict still stands when "
        "that group is absent from the record.",
        "",
        "**Approximation carried (stated, not hidden).** The mismatch "
        "distribution is measured at `tt`/3.30 V only and is applied unchanged "
        "at every process corner and supply. Local mismatch is treated as "
        "separable from the global corner — a first-order approximation, since "
        "a slow corner shifts `gm/Id` at the mirror and amp devices and so "
        "moves the mismatch gain slightly. Removing it means running the MC at "
        "every corner (81 x N solves), which is precisely why the ratified row "
        "is written as mismatch MC **+** process corners rather than "
        "MC-over-corners. The anchor cross-check above is the guard that keeps "
        "this approximation from being applied to two benches that disagree "
        "about the circuit itself.",
        "",
        "**Which records are read.** The two legs are paired on a *shared* "
        "netlist provenance (`sim/README.md`'s **Netlist provenance** field): "
        "the newest record across both benches names the class, and each leg "
        "then contributes its own newest record of that class — schematic with "
        "schematic, extracted with extracted. A bench that has not been re-run "
        "post-layout therefore never drags the other leg's extracted record "
        "into the graft; when no same-provenance pair exists at all, this "
        "report says so and claims no verdict instead of reporting the "
        "resulting anchor disagreement as if the benches disagreed. An "
        "explicit `--corner-record`/`--mc-record` pin always overrides the "
        "pairing, including deliberately across classes.",
        "",
        "**Re-running.** Within that pairing rule, both legs default to their "
        "newest record, so once either leg is re-run — for instance after the "
        "temperature-coefficient / centre re-centring work — a bare "
        "`python3 sim/run_combined_accuracy.py` re-judges against the new "
        "evidence with no argument changes, and mints a new report beside this "
        "one. Nothing here is ever edited in place.",
        "",
        "---",
        "",
        "Generated by `sim/run_combined_accuracy.py` (`sim/suite/combined.py`). "
        "This is a roll-up of the two records it cites, not a substitute for "
        "them: the per-corner and per-sample evidence lives under "
        "`sim/output-voltage-tc/` and `sim/mc-untrimmed/` and is append-only "
        "(`sim/README.md`).",
    ]


# --- CLI --------------------------------------------------------------------


def load(
    corner_record: str | None = None,
    mc_record: str | None = None,
    sim_dir: Path = SIM_DIR,
    corner_samples: dict[str, dict[str, float]] | None = None,
    corner_evidence: EvidenceRef | None = None,
) -> CombinedVerdict:
    """Read both legs off disk (or take the corner leg from a live run) and judge.

    Record selection goes through :func:`select_records`, so an unpinned run
    pairs the two legs on a *shared* netlist-provenance class rather than
    taking the newest record of each bench independently.
    """
    live_corner = corner_samples is not None
    if live_corner and corner_evidence is not None:
        corner_evidence = _with_live_provenance(corner_evidence, sim_dir)
    pairing = select_records(
        corner_record,
        mc_record,
        sim_dir,
        corner_provenance=(
            corner_evidence.provenance
            if live_corner
            and corner_evidence is not None
            and corner_evidence.provenance != UNKNOWN_PROVENANCE
            else None
        ),
        live_corner=live_corner,
    )
    if not live_corner:
        corner_evidence = (
            evidence_for(CORNER_SLUG, pairing.corner_record, sim_dir)
            if pairing.corner_record
            else None
        )
        corner_samples = (
            read_corner_logs(sim_dir / CORNER_SLUG / "corners" / corner_evidence.record_id)
            if corner_evidence
            else {}
        )
    mc_evidence = (
        evidence_for(MC_SLUG, pairing.mc_record, sim_dir) if pairing.mc_record else None
    )
    mc_stats = (
        read_mc_groups(sim_dir / MC_SLUG / "corners" / mc_evidence.record_id)
        if mc_evidence
        else {}
    )

    combined = evaluate(corner_samples, mc_stats)
    combined.corner_evidence = corner_evidence
    combined.mc_evidence = mc_evidence
    combined.matched_provenance = (
        corner_evidence.provenance
        if corner_evidence is not None
        and mc_evidence is not None
        and corner_evidence.provenance == mc_evidence.provenance
        else None
    )
    for problem in reversed(pairing.problems):
        combined.problems.insert(0, problem)
    if corner_evidence is None and not corner_samples:
        combined.problems.insert(
            0, f"no readable record + raw logs found under `sim/{CORNER_SLUG}/`"
        )
    if mc_evidence is None:
        combined.problems.insert(
            0, f"no readable record + raw logs found under `sim/{MC_SLUG}/`"
        )
    return combined


def build_parser() -> argparse.ArgumentParser:
    return _build_parser()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_combined_accuracy.py",
        description=(
            "Combine sim/mc-untrimmed's mismatch leg and sim/output-voltage-tc's "
            "process-corner leg into one pass/fail verdict against the ratified "
            "untrimmed-accuracy row. Unpinned, the two legs are paired on a "
            "shared netlist provenance (schematic with schematic, extracted "
            "with extracted) -- each leg's newest record of that class."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 sim/run_combined_accuracy.py                  # newest same-provenance pair\n"
            "  python3 sim/run_combined_accuracy.py --no-write       # print only\n"
            "  python3 sim/run_combined_accuracy.py --mc-record 20260802-034414-5066d85\n"
            "\n"
            "Exit codes: 0 combined PASS, 1 combined FAIL, 2 evidence missing or\n"
            "the methodology cross-check failed.\n"
        ),
    )
    parser.add_argument(
        "--corner-record",
        metavar="RECORD-ID",
        help=f"pin the process-corner leg to one sim/{CORNER_SLUG}/records/<id> "
        "(default: the newest of the provenance class the legs pair on; a pin "
        "is never overridden, and the other leg then matches its class)",
    )
    parser.add_argument(
        "--mc-record",
        metavar="RECORD-ID",
        help=f"pin the mismatch leg to one sim/{MC_SLUG}/records/<id> "
        "(default: the newest of the provenance class the legs pair on; a pin "
        "is never overridden, and the other leg then matches its class)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print the report without writing it under sim/suite/combined/",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    sys.path.insert(0, str(SIM_DIR))
    from harness import report as harness_report  # noqa: E402  (needs sys.path)

    started = _dt.datetime.now(_dt.timezone.utc)
    git = harness_report.git_provenance(REPO_ROOT)

    combined = load(corner_record=args.corner_record, mc_record=args.mc_record)
    text = render(combined, started=started, git=git)
    print(text)

    if not args.no_write:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{started.strftime('%Y%m%d-%H%M%S')}-{git.get('short', 'unknown')}.md"
        path = REPORT_DIR / name
        if path.exists():  # pragma: no cover - same second, same commit
            path = REPORT_DIR / f"{path.stem}-1.md"
        path.write_text(text)
        print(f"report written to {path.relative_to(REPO_ROOT)}")

    if combined.status == "PASS":
        return EXIT_OK
    if combined.status == "FAIL":
        return EXIT_SPEC_FAIL
    return EXIT_EVIDENCE_ERROR
