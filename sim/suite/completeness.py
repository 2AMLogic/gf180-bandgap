"""One completeness assessment, shared by the summary text and the exit code.

The summary used to count only the outcomes of the benches it was handed, and
the exit code looked only for runner errors and FAILs. A subset run could
therefore print "Simulation-complete", and a gated NO DATA or an absent bench
could exit 0. Both now read the same :class:`Completeness`, so what the
summary says and what the shell sees cannot disagree.

Three outcomes:

- ``complete``: the full index was run at full PVT and every bench, corner,
  gated measurement and the combined row is present and PASS. The only state
  that may claim "simulation-complete".
- ``subset``: nothing requested is wrong, but the run is deliberately not the
  whole suite (``--only`` omitted benches, ``--smoke``, or a reduced corner grid that
  leaves out manifest-required acceptance corners). Useful for
  debugging, exits 0, asserts nothing about completeness.
- ``blocked``: something requested is failing or its evidence is missing
  (absent bench, runner failure, gated NO DATA, a measurement missing at a
  corner, combined row not evaluated/INVALID). No acceptance claim; exits
  nonzero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EXIT_OK = 0
EXIT_SPEC_FAIL = 1
EXIT_RUN_ERROR = 2

COMPLETE = "complete"
SUBSET = "subset"
BLOCKED = "blocked"


@dataclass
class Completeness:
    state: str = SUBSET
    #: Index slugs this run did not request (empty for a full-suite run).
    omitted: list[str] = field(default_factory=list)
    smoke: bool = False
    #: ``{slug: [acceptance corner ids the requested grid did not cover]}``.
    #: Intentional omission (a diagnostic override), distinct from ``missing``,
    #: which is requested-but-absent evidence.
    uncovered: dict = field(default_factory=dict)
    #: Reasons the evidence is missing or the run broke (exit 2).
    missing: list[str] = field(default_factory=list)
    #: Spec violations (exit 1).
    failures: list[str] = field(default_factory=list)
    n_gated: int = 0
    n_pass: int = 0
    #: Why a subset cannot claim completeness, in plain words.
    subset_reasons: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.state == COMPLETE

    @property
    def blocked(self) -> bool:
        return self.state == BLOCKED

    @property
    def exit_code(self) -> int:
        if self.missing:
            return EXIT_RUN_ERROR
        if self.failures:
            return EXIT_SPEC_FAIL
        return EXIT_OK


def _corner_list(corners, limit: int = 4) -> str:
    shown = ", ".join(f"`{c}`" for c in corners[:limit])
    return shown + (f" and {len(corners) - limit} more" if len(corners) > limit else "")


def assess(benches, combined, required_slugs, smoke: bool = False) -> Completeness:
    """Judge a set of :class:`~suite.cli.BenchRun` against the full index."""
    result = Completeness(smoke=smoke)
    present = {bench.slug for bench in benches}
    result.omitted = [slug for slug in required_slugs if slug not in present]

    for bench in benches:
        if bench.status == "missing":
            result.missing.append(f"bench `{bench.slug}` is not in the tree ({bench.message})")
            continue
        if bench.status == "error":
            detail = f": {bench.message}" if bench.message else ""
            result.missing.append(
                f"bench `{bench.slug}` runner failed (exit {bench.returncode}){detail}"
            )
        elif bench.status == "check-failed":
            result.failures.append(f"bench `{bench.slug}` failed its own checks")
        for outcome in bench.outcomes:
            if not outcome.line.gated:
                continue
            result.n_gated += 1
            if outcome.status == "PASS" and bench.status == "ok":
                result.n_pass += 1
            if outcome.status == "FAIL":
                result.failures.append(
                    f"{outcome.line.row} (`{bench.slug}`) violates its ratified limit"
                )
            elif outcome.status != "PASS":
                for limit in outcome.outcomes:
                    if limit.status != "NO DATA":
                        continue
                    if limit.missing_corners and limit.n_samples:
                        why = (
                            f"`{limit.limit.measurement}` missing at "
                            f"{len(limit.missing_corners)} corner(s): "
                            f"{_corner_list(limit.missing_corners)}"
                        )
                    else:
                        why = f"`{limit.limit.measurement}` was not measured at any corner"
                    result.missing.append(f"{outcome.line.row} (`{bench.slug}`) NO DATA: {why}")
                if not outcome.outcomes:
                    result.missing.append(f"{outcome.line.row} (`{bench.slug}`) NO DATA")

    if combined is not None:
        if combined.status in {"NO DATA", "INVALID"}:
            result.missing.append(
                f"two-legged accuracy row is {combined.status}, not evaluated"
            )
        elif combined.status == "FAIL":
            result.failures.append(
                f"two-legged accuracy row FAILs at {combined.n_fail} corner(s)"
            )

    if result.omitted:
        result.subset_reasons.append(
            "benches not requested: " + ", ".join(f"`{s}`" for s in result.omitted)
        )
    for bench in benches:
        if smoke or bench.status == "missing":
            continue  # smoke already carries its own subset reason
        acceptance = getattr(bench, "acceptance_corners", None)
        requested = bench.expected_corners
        if acceptance is None or requested is None:
            continue
        have = set(requested)
        absent = [c for c in acceptance if c not in have]
        if absent:
            result.uncovered[bench.slug] = absent
    if result.uncovered:
        parts = [
            f"`{slug}` ({len(absent)} manifest-required corner(s) not requested, "
            f"e.g. {_corner_list(absent, limit=2)})"
            for slug, absent in result.uncovered.items()
        ]
        result.subset_reasons.append(
            "reduced corner grid omits acceptance coverage: " + ", ".join(parts)
        )
    if smoke:
        result.subset_reasons.append("smoke run covers one nominal corner, not the full PVT matrix")

    if result.missing or result.failures:
        result.state = BLOCKED
    elif result.subset_reasons:
        result.state = SUBSET
    elif combined is None or combined.status != "PASS":
        # Defensive: a full-index run always evaluates the combined row.
        result.missing.append("two-legged accuracy row was not evaluated")
        result.state = BLOCKED
    else:
        result.state = COMPLETE
    return result
