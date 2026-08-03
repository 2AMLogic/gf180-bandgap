"""The suite index: ratified spec row -> testbench -> pass/fail limit.

This module is the single place where "which spec line is verified by which
testbench, against which number" is written down. Everything else in the
suite is mechanism.

The numbers here are the **ratified** ones from README.md's "Target
specification (RATIFIED 2026-07-31)" table (see
``spec/decision-records/0003-target-spec-ratification.md``). Per CLAUDE.md
they are not to be relaxed to make a run pass: if a bench fails, the record
says FAIL and the fix goes through design or a ``spec/`` decision record.

Each limit is deliberately duplicated in the bench's own ``tb.json`` checks
(so a bare ``python3 sim/run_corners.py <slug>`` also judges itself against
the ratified value) and here (so the suite can roll several measurements up
into one per-spec-line verdict, and so a bench that covers two rows -- as
``output-voltage-tc`` and ``line-regulation`` both do -- reports them
separately). :func:`sim.suite.analysis.check_limits_match_manifest` asserts
the two copies agree, so the duplication cannot silently drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Ratified nominal output, for reference in the summary header.
VREF_NOMINAL_V = 1.20


@dataclass(frozen=True)
class Limit:
    """One pass/fail bound on one measurement, at every corner."""

    measurement: str
    kind: str          # "min" (measurement must be >= value) or "max" (<= value)
    value: float
    units: str = ""

    def satisfied(self, sample: float) -> bool:
        return sample >= self.value if self.kind == "min" else sample <= self.value

    def describe(self) -> str:
        symbol = ">=" if self.kind == "min" else "<="
        return f"{self.measurement} {symbol} {self.value:g}{self.units}"


@dataclass(frozen=True)
class SpecLine:
    """One row of the ratified spec table, and how it is substantiated."""

    key: str
    row: str                       # the README.md table row this claims
    target: str                    # the ratified target, as written
    slug: str                      # sim/<slug>/ -- the bench that verifies it
    owner: str = "#12"             # which issue owns that bench
    limits: tuple[Limit, ...] = ()
    reference: tuple[str, ...] = ()   # measurements reported but not gated
    note: str = ""

    @property
    def gated(self) -> bool:
        """False when the verdict comes from the bench itself, not from a limit.

        Used for a bench this suite integrates but does not own (``startup``,
        #11): the suite reports that bench's own overall status rather than
        second-guessing its measurement names.
        """
        return bool(self.limits)


#: The suite, in README.md table order.
SUITE: tuple[SpecLine, ...] = (
    SpecLine(
        key="output-reference",
        row="Output reference",
        target="1.20 V +/-2% untrimmed (1.176-1.224 V)",
        slug="output-voltage-tc",
        limits=(
            Limit("vref", "min", 1.176, " V"),
            Limit("vref", "max", 1.224, " V"),
        ),
        note=(
            "Corner portion of the row only: process x temperature x supply. "
            "The row's 3-sigma untrimmed *mismatch* portion (mismatch MC, "
            "N>=300) is #13's `mc-untrimmed` bench; the two legs are judged "
            "together by the combined verdict below (`COMBINED_ACCURACY`, "
            "`sim/suite/combined.py`), which is the row's ratified basis. This "
            "line remains reported on its own so it stays visible which leg "
            "binds."
        ),
    ),
    SpecLine(
        key="temp-coefficient",
        row="Temp coefficient (-40..125 degC)",
        target="< 50 ppm/degC (box method)",
        slug="output-voltage-tc",
        limits=(Limit("tc_ppm", "max", 50.0, " ppm/degC"),),
        reference=("vref_box_min", "vref_box_max", "vref_m40", "vref_27", "vref_125"),
        note=(
            "Box method over an internal 1 degC-step -40..125 degC sweep "
            "(166 points per corner), not the three-point outer axis; "
            "TC = (Vmax - Vmin)/(V_27C * 165 degC) * 1e6."
        ),
    ),
    SpecLine(
        key="psrr",
        row="PSRR",
        target="> 60 dB DC-1 kHz",
        slug="psrr-dc",
        limits=(
            Limit("psrr_1hz_db", "min", 60.0, " dB"),
            Limit("psrr_1khz_db", "min", 60.0, " dB"),
        ),
        reference=(
            "psrr_10hz_db",
            "psrr_100hz_db",
            "psrr_10khz_db",
            "psrr_100khz_db",
            "psrr_1mhz_db",
        ),
        note=(
            "DC figure = the low-frequency asymptote at 1 Hz (an AC analysis "
            "cannot evaluate 0 Hz); 1 kHz is the band edge the row names. The "
            "other spot frequencies are the reference curve, not claims; "
            "1 MHz is the table's stretch goal (> 30 dB), recorded not gated. "
            "Unloaded -- the row's load condition is open item A4."
        ),
    ),
    SpecLine(
        key="line-regulation",
        row="Line regulation",
        target="< 1 mV/V (DC, 2.97-3.63 V)",
        slug="line-regulation",
        limits=(Limit("linereg_mv_per_v", "max", 1.0, " mV/V"),),
        reference=("vref_lo", "vref_hi"),
        note=(
            "Box over a continuous 133-point supply sweep, "
            "(Vmax - Vmin)/0.66 V -- not the endpoint chord."
        ),
    ),
    SpecLine(
        key="supply-range",
        row="Supply / Output reference over supply",
        target="3.3 V +/-10%: Vref stays within 1.176-1.224 V across 2.97-3.63 V",
        slug="line-regulation",
        limits=(
            Limit("vref_min", "min", 1.176, " V"),
            Limit("vref_max", "max", 1.224, " V"),
        ),
        note=(
            "The supply-tolerance aspect of the output-reference row, checked "
            "at every one of the 133 sweep points rather than only at the "
            "three nominal rails."
        ),
    ),
    SpecLine(
        key="quiescent-current",
        row="Quiescent current",
        target="< 50 uA",
        slug="iq",
        limits=(Limit("iq_ua", "max", 50.0, " uA"),),
        reference=("vref",),
        note=(
            "Total supply current of the whole block at every PVT corner; the "
            "row binds at ff/125 degC/3.63 V. There is no separate startup "
            "branch to itemize yet -- when #11's branch lands inside "
            "bandgap_top it is counted by this same measurement, and #11's "
            "own itemization should be cross-referenced from the record then."
        ),
    ),
    SpecLine(
        key="startup",
        row="Startup",
        target="self-starting at all corners, < 1 ms to within 1% of final value",
        slug="startup",
        owner="#11",
        note=(
            "Verified by #11's transient bench and degenerate-state search. "
            "This suite wires that bench in by slug and reports its own "
            "overall verdict; it deliberately does NOT reimplement it."
        ),
    ),
)


@dataclass(frozen=True)
class CombinedRow:
    """A ratified row whose verdict needs two benches combined, not one.

    The Output-reference row is ratified on a **two-legged** basis -- mismatch
    MC *and* process corners -- so no single bench's own pass/fail is that
    row's verdict. :mod:`sim.suite.combined` states the combination rule and
    emits the joint verdict; this entry is the index of what it combines.
    """

    row: str
    target: str
    legs: tuple[tuple[str, str], ...]   # (slug, what that leg supplies)
    note: str


#: The one ratified row the suite claims by combining two benches.
COMBINED_ACCURACY = CombinedRow(
    row="Output reference (untrimmed accuracy, both legs)",
    target="1.20 V +/-2% untrimmed (3 sigma, mismatch MC N>=300 + process corners)",
    legs=(
        ("output-voltage-tc", "deterministic Vref at each of 81 process x "
                              "temperature x supply corners"),
        ("mc-untrimmed", "the `mm_all` group's N>=300 local-mismatch "
                         "distribution of Vref, per temperature"),
    ),
    note=(
        "Per corner: the mismatch distribution measured at tt/3.30 V is "
        "grafted onto every corner's own deterministic Vref and the full "
        "3-sigma interval must fit inside 1.176-1.224 V. Rolled up per "
        "temperature (worst-margin corner governs). The graft assumes local "
        "mismatch is separable from the global corner and cross-checks that "
        "assumption against the MC bench's own deterministic control group -- "
        "see `sim/suite/combined.py` and "
        "`python3 sim/run_combined_accuracy.py`."
    ),
)


@dataclass(frozen=True)
class UnclaimedRow:
    """A ratified table row this suite does not, and should not, claim."""

    row: str
    reason: str


#: Rows of the ratified table that are outside the suite's scope. Printed with
#: every summary: "simulation-complete" is only an honest phrase if what is
#: *not* covered is stated in the same breath.
NOT_CLAIMED_HERE: tuple[UnclaimedRow, ...] = (
    UnclaimedRow("Trim", "no trim segments exist in the schematic yet -- #14"),
    UnclaimedRow("Output noise", "threshold is open item A6 (README.md); no bench yet"),
    UnclaimedRow("Load", "load condition is open item A7 (README.md); no bench yet"),
    UnclaimedRow("Area", "a layout claim, not a simulation claim -- #15/#16"),
    UnclaimedRow("Long-term drift", "not specified for a canary block"),
)


def by_slug() -> dict[str, list[SpecLine]]:
    """Spec lines grouped by the bench that verifies them, in suite order."""
    grouped: dict[str, list[SpecLine]] = {}
    for line in SUITE:
        grouped.setdefault(line.slug, []).append(line)
    return grouped


def slugs() -> list[str]:
    """Experiment slugs the suite drives, in first-appearance order."""
    seen: list[str] = []
    for line in SUITE:
        if line.slug not in seen:
            seen.append(line.slug)
    return seen


@dataclass
class SlugPlan:
    """What the suite intends to do with one experiment slug."""

    slug: str
    lines: list[SpecLine] = field(default_factory=list)

    @property
    def owner(self) -> str:
        return self.lines[0].owner if self.lines else "#12"
