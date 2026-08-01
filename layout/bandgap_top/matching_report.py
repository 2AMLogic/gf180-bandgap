#!/usr/bin/env python3
"""Mechanical check that the drawn geometry realises ``floorplan.md`` §0's
matching plan — the automated form of "open it in KLayout and eyeball it".

Three checks, one per matching tier in ``layout/floorplan.md`` §0:

**Tier 1 — common centroid.** For every matched MOS array, read the *drawn*
x position of every finger back out of the generator's placement, compute each
member device's finger centroid, and require all members of the array to share
one centroid (to within half a drawn finger pitch, which is the resolution at
which "same centroid" is even meaningful). A device whose fingers sit off to
one side of the array fails here, no matter how the plan describes it.

**Tier 2 — identical resistor unit geometry.** Require every drawn
``ppolyf_u`` segment in the matched resistor group (``R1``, ``R2``, and all 63
trim-ladder units) to share one unit width, per floorplan §3.1/§3.2.

**Tier 3 — PNP array.** Require ``Q2``'s four drawn units to share ``Q1``'s
centroid exactly, and the array to carry a dummy unit at each edge. ``Q1``/
``Q2`` is the pairing checked (rather than all three PNPs) because two
single-unit devices cannot share a centroid at all — see :mod:`plan`'s tier-3
note for why ``Q1``/``Q2`` is the pairing that wins when one has to.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_top/matching_report.py

Exit code is 0 when every check passes, 3 when any check fails — so this is
usable as a gate, not just a printout.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate  # noqa: E402
import plan as plan_mod  # noqa: E402

#: Rows that are matched arrays, and the floorplan section that says so.
MATCHED_ROWS = {
    "AMPPAIR": "§0 tier 1 / §6 — amp input pair",
    "AMPLOAD": "§0 tier 1 / §6 — amp mirror load",
    "AMPNCASC": "§0 tier 1 / §6 — amp NMOS cascode pair",
    "AMPPCASC": "§0 tier 1 / §6 — amp PMOS cascode pair",
    "COREMIRROR": "§0 tier 1 / §5 — core mirror M1-M3",
    "CORECASC": "§0 tier 1 / §5 — core cascode MC1-MC3",
}


def _letters(devices: list[str]) -> dict[str, str]:
    """Map device path -> single letter, in first-appearance order."""
    out: dict[str, str] = {}
    for path in devices:
        if path not in out:
            out[path] = chr(ord("A") + len(out))
    return out


def check_mos_arrays(row_geometry: list[dict]) -> list[str]:
    failures: list[str] = []
    for geo in row_geometry:
        row = geo["row"]
        if row.name not in MATCHED_ROWS:
            continue
        placements = [
            (item, x, w)
            for item, x, w in geo["placements"]
            if isinstance(item, plan_mod.MosItem)
        ]
        order = [item.device or "DUMMY" for item, _x, _w in placements]
        letters = _letters([p for p in order if p != "DUMMY"])
        letters["DUMMY"] = "D"
        pattern = " ".join(letters[p] for p in order)

        centres: dict[str, list[float]] = {}
        pitch: list[int] = []
        for item, x, w in placements:
            if item.dummy:
                continue
            centres.setdefault(item.device, []).append(x + w / 2)
            pitch.append(w)
        centroids = {d: sum(v) / len(v) for d, v in centres.items()}
        span = max(centroids.values()) - min(centroids.values())
        tol = max(pitch) / 2
        ok = span <= tol
        if not ok:
            failures.append(
                f"{row.name}: centroid spread {span/1000:.3f} um exceeds "
                f"tolerance {tol/1000:.3f} um"
            )

        print(f"{row.name:12s} {MATCHED_ROWS[row.name]}")
        print(f"  devices        : " + ", ".join(f"{letters[d]}={d}" for d in centroids))
        print(f"  drawn order    : {pattern}")
        print(
            "  centroids (um) : "
            + ", ".join(f"{letters[d]}={centroids[d]/1000:.3f}" for d in centroids)
        )
        print(
            f"  centroid spread: {span/1000:.3f} um "
            f"(tolerance {tol/1000:.3f} um) -> {'OK' if ok else 'FAIL'}"
        )
        print()
    return failures


def check_resistor_units(rows: list[plan_mod.Row]) -> list[str]:
    widths: dict[str, set[int]] = {}
    for row in rows:
        for item in row.items:
            if isinstance(item, plan_mod.ResItem) and item.key.startswith("core."):
                widths.setdefault("matched resistor group", set()).add(item.width_nm)
            elif isinstance(item, plan_mod.TrimLadderItem):
                widths.setdefault("matched resistor group", set()).add(item.unit_width_nm)
    group = widths.get("matched resistor group", set())
    print("resistor array (§0 tier 2 / §3.1, §3.2)")
    print(f"  drawn unit widths: {sorted(w/1000 for w in group)} um")
    ok = len(group) == 1
    print(f"  single unit width -> {'OK' if ok else 'FAIL'}")
    print()
    return [] if ok else [f"resistor array: {len(group)} distinct unit widths drawn"]


def check_pnp_array(rows: list[plan_mod.Row]) -> list[str]:
    row = next(r for r in rows if r.name == "PNP")
    items: list[plan_mod.PnpItem] = list(row.items)
    labels = ["D" if i.dummy else (i.device or "?").split(".")[-1] for i in items]
    failures: list[str] = []

    edges_dummy = items[0].dummy and items[-1].dummy
    inner = [i for i in items if not i.dummy]
    positions: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        if item.dummy:
            continue
        positions.setdefault(item.device, []).append(index)
    centroids = {d: sum(v) / len(v) for d, v in positions.items()}
    # The operative pair: Q1 and Q2 set dVBE across R2, which reaches vref
    # multiplied by R1/R2 (~12.8x). Q3 lands on vref at unity gain.
    span = abs(centroids["core.Q1"] - centroids["core.Q2"])
    balanced = span == 0.0

    print("PNP array (§0 tier 3 / §4.1)")
    print(f"  drawn order    : {' '.join(labels)}")
    print(
        "  unit centroids : "
        + ", ".join(f"{d.split('.')[-1]}={c:.2f}" for d, c in centroids.items())
    )
    print(f"  edge dummies   -> {'OK' if edges_dummy else 'FAIL'}")
    print(
        f"  Q1/Q2 centroid spread {span:.2f} unit cells -> "
        f"{'OK' if balanced else 'FAIL'}"
    )
    print(
        f"  Q3 offset from Q1     {abs(centroids['core.Q3'] - centroids['core.Q1']):.2f}"
        " unit cells (unity-gain term; see plan.py tier-3 note)"
    )
    print(f"  drawn units    : {len(inner)} real + {len(items) - len(inner)} dummy")
    print()
    if not edges_dummy:
        failures.append("PNP array: missing an edge dummy")
    if not balanced:
        failures.append(f"PNP array: Q1/Q2 centroid spread {span:.2f} unit cells")
    return failures


def main() -> int:
    _b, stats = generate.build()
    _flat, rows = plan_mod.load_plan()

    print("Matching verification for bandgap_top (layout/floorplan.md §0)")
    print("=" * 66)
    print()
    failures = check_mos_arrays(stats["rows"])
    failures += check_resistor_units(rows)
    failures += check_pnp_array(rows)

    if failures:
        print("FAIL:")
        for line in failures:
            print(f"  - {line}")
        return 3
    print("All matching checks pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
