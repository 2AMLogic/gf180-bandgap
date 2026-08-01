"""The spec-line verification suite: one testbench per ratified spec row.

``sim/run_suite.py`` runs every bench in :mod:`sim.suite.spec`'s index over
the full PVT matrix and emits a per-spec-line pass/fail summary. That summary
is the operational definition of "simulation-complete" on this block's
maturity ladder (README.md, "Status").

The suite does not simulate anything itself: it drives ``sim/run_corners.py``
per experiment slug (so every bench mints a normal append-only record under
``sim/<slug>/records/`` in the format ``sim/README.md`` ratifies) and then
reads the raw per-corner logs those runs wrote, to roll individual
measurements up into per-spec-line verdicts.
"""

SUITE_VERSION = "0.1.0"

__all__ = ["SUITE_VERSION"]
