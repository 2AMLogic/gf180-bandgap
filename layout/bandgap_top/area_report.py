#!/usr/bin/env python3
"""Area-budget check: drawn GDS area vs. ``layout/floorplan.md`` §8's estimate.

Closes floorplan §11.1 ("GDS-verified area re-check", owner: *the future
layout-implementation issue*) by re-running §8's comparison against real
geometry instead of the schematic-derived floor that section could only
offer.

Three numbers are produced, each from a different source, so the comparison
cannot be quietly fudged:

* **drawn device body area** — recomputed from the *current*
  ``design/netlist/bandgap_top.spice`` via :mod:`netlist_model`, i.e. exactly
  the quantity floorplan §8's table estimates, but against today's netlist;
* **floorplan §8 estimate** — the number that document published, transcribed
  here as a constant with its provenance;
* **actual GDS bounding-box area** — read back out of the written GDS with
  ``klayout.db``, not from the generator's own bookkeeping.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_top/area_report.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import netlist_model  # noqa: E402
import plan as plan_mod  # noqa: E402

#: ``layout/floorplan.md`` §8, "Subtotal (drawn active/body area only)".
FLOORPLAN_ESTIMATE_UM2 = 10425.45

#: ``README.md`` "Target specification" Area row. Originally ratified
#: 2026-07-31 at 50,000 um^2 via issue #1/#35
#: (``spec/decision-records/0003-target-spec-ratification.md``); the drawn
#: layout has since measured over that target twice, each escalated (not
#: silently absorbed) per CLAUDE.md's no-spec-relaxation rule: issue #156
#: proposed an interim 85,000 um^2 ceiling
#: (``spec/decision-records/0005-area-target-overrun.md``, superseded), and
#: issue #166's Metal2/Metal3 re-route narrowed that to the current interim
#: ceiling below (``spec/decision-records/0006-area-target-narrowed-post-166.md``).
RATIFIED_TARGET_UM2 = 66000.0

GDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandgap_top.gds")


def body_area_um2(flat: netlist_model.FlatNetlist) -> list[tuple[str, str, float]]:
    """``(line item, basis, area um^2)`` for every drawn device in the netlist."""
    rows: list[tuple[str, str, float]] = []
    for device in flat.devices:
        if device.family == "mos":
            area = (device.w_nm * device.l_nm) / 1e6
            rows.append(
                (device.path, f"W={device.w_nm/1000:g}um x L={device.l_nm/1000:g}um", area)
            )
        elif device.family == "res":
            w = netlist_model.nm(device.params["r_width"])
            length = netlist_model.nm(device.params["r_length"])
            rows.append(
                (device.path, f"{length/1000:g}um x {w/1000:g}um", (w * length) / 1e6)
            )
        elif device.family == "bjt":
            side = 5.0 if "05p00" in device.model else 10.0
            rows.append((device.path, f"{side:g}um x {side:g}um emitter", side * side))
        elif device.family == "cap":
            w = netlist_model.nm(device.params["c_width"])
            h = netlist_model.nm(device.params["c_length"])
            rows.append((device.path, f"{w/1000:g}um x {h/1000:g}um MIM", (w * h) / 1e6))
    return rows


def gds_bbox_um() -> tuple[float, float]:
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(GDS)
    top = layout.top_cell()
    bbox = top.bbox()
    return bbox.width() * layout.dbu, bbox.height() * layout.dbu


def group_of(path: str) -> str:
    if path.startswith("core.trim."):
        return "trim ladder"
    return path.split(".")[0]


def main() -> int:
    flat = netlist_model.load()
    rows = body_area_um2(flat)

    groups: dict[str, float] = {}
    for path, _basis, area in rows:
        groups[group_of(path)] = groups.get(group_of(path), 0.0) + area
    total_body = sum(area for _p, _b, area in rows)

    width, height = gds_bbox_um()
    gds_area = width * height

    print("Drawn device body area, by group (from the current netlist):")
    for name in sorted(groups):
        print(f"  {name:14s} {groups[name]:10.2f} um^2")
    print(f"  {'TOTAL':14s} {total_body:10.2f} um^2")
    print()
    print(f"floorplan.md §8 estimate      : {FLOORPLAN_ESTIMATE_UM2:10.2f} um^2")
    print(
        f"  -> current netlist is         {total_body / FLOORPLAN_ESTIMATE_UM2:10.2f}x "
        "that estimate"
    )
    print()
    print(f"drawn GDS bounding box        : {width:.2f} x {height:.2f} um")
    print(f"drawn GDS area                : {gds_area:10.2f} um^2 "
          f"({gds_area / 1e6:.5f} mm^2)")
    print(f"ratified target               : {RATIFIED_TARGET_UM2:10.2f} um^2 "
          f"({RATIFIED_TARGET_UM2 / 1e6:.5f} mm^2)")
    margin = RATIFIED_TARGET_UM2 - gds_area
    verdict = "PASS" if margin >= 0 else "FAIL"
    print(
        f"  -> {verdict}: {abs(margin):.2f} um^2 "
        f"({abs(margin) / RATIFIED_TARGET_UM2 * 100:.1f}%) "
        f"{'of headroom' if margin >= 0 else 'OVER budget'}"
    )
    print(f"  -> layout overhead multiplier : {gds_area / total_body:.2f}x body area")
    print()
    print(f"drawn trim code               : {plan_mod.DRAWN_TRIM_CODE}")
    return 0 if margin >= 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
