"""Shared guard for local multi-point ngspice grids.

On a host configured for the Spot batch fleet (``KLT_SIM_BACKEND=batch`` or
``remote``) a multi-point PVT grid must not fan out as local ``ngspice -b``
processes. This guard refuses that; it never falls back to a local run and
never submits anything itself (generic fleet dispatch is separate work).

Override: ``KLT_SIM_BACKEND=local`` (or unset/empty) allows a local grid. It is
an environment variable on purpose, so it reaches every subprocess of
``sim/selftest.sh`` by inheritance.
"""

from __future__ import annotations

import os

#: Default local parallelism. Explicit ``-j/--jobs`` is honoured unchanged.
DEFAULT_LOCAL_JOBS_CAP = 2

FLEET_BACKENDS = ("batch", "remote")


def default_jobs() -> int:
    return min(DEFAULT_LOCAL_JOBS_CAP, os.cpu_count() or 1)


def guard_local_grid(n_points: int) -> None:
    """Exit if a >1-point grid is about to run locally on a fleet-backed host."""
    backend = os.environ.get("KLT_SIM_BACKEND", "").strip()
    if backend in FLEET_BACKENDS and n_points > 1:
        raise SystemExit(
            f"KLT_SIM_BACKEND={backend!r}: refusing to run a {n_points}-point grid "
            "as local ngspice processes on this host. Submit it to the fleet with a "
            "`klt sim` request (see sim/tools/mk_klt_*_request.py), or set "
            "KLT_SIM_BACKEND=local to run locally on purpose."
        )
