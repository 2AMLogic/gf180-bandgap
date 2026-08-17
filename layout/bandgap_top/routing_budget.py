#!/usr/bin/env python3
"""Where ``bandgap_top``'s drawn area goes, and what multi-metal routing recovers.

The area *verdict* lives in :mod:`area_report` (drawn GDS bbox vs. the
ratified target). This module answers the follow-up question #156/DR-0005
left open and gf180-bandgap#160 asks: **of the 3.19x overhead multiplier
over device body area, how much is single-metal routing, and how much would
a Metal2/Metal3 over-the-cell re-route actually give back?**

It does that in three steps, none of which is an assertion:

1. **Decompose the drawn block** into the terms ``generate.build()`` itself
   places — the Poly2 corridor's width, each row's device content height,
   each row's stacked Metal1 rail band, the inter-row gaps and the guard
   ring. The decomposition is *checked*: its reconstructed bounding box must
   equal the committed GDS's bounding box to the nanometre (see
   ``check_identity``), so a term cannot be quietly mis-attributed.
2. **Check the proposed routing scheme fits**, track by track, against the
   installed gf180mcu DRC deck's real Metal2/Metal3 width/space minima —
   per row, does the row's own device height hold its Metal3 rails, and does
   the Metal2 spine bundle fit across the device field?
3. **Model the recoverable area** under that scheme and print the resulting
   overhead multiplier next to the one the ratified 0.05 mm2 target needs.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_top/routing_budget.py

Written up, with the arithmetic and the DR-0005 implication, in
``layout/routing/multi-metal-routing-study.md`` (gf180-bandgap#160). This
module is that document's testbench: every number the study quotes is
printed here, from the current netlist and the current generator, so the
study cannot silently go stale the way ``floorplan.md`` §8's own estimate
did (``AREA.md`` Finding 1).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import area_report  # noqa: E402
import generate  # noqa: E402
import netlist_model  # noqa: E402
import plan as plan_mod  # noqa: E402

# --------------------------------------------------------------------------- #
# Proposed routing-track geometry, in nanometres.
#
# Read out of the *installed* deck (klayout_tools/decks/gf180mcu.py, klt
# 0.2.0), not from memory. `metal2.width.1` / `metal3.width.1` are both
# 280 nm and `metal2.space.1` / `metal3.space.1` are both 280 nm, so one
# track geometry serves both levels. The same sizing is drawn, DRC'd and
# extracted for real by the probe fixture under
# layout/drc/fixtures/m2m3_stack_probe/.
#
# Metal4 is deliberately NOT used: the deck has no metal4.width/space rule at
# all (Metal4 appears only inside the MiM-capacitor rules), so routing on it
# would put block geometry outside DRC coverage -- and stray Metal4 near the
# compensation cap is exactly what `mim.space.1` polices. Metal5 is left to
# the MiM cap's own `fb` wire.
# --------------------------------------------------------------------------- #
TRACK_W = 400  # metal2.width.1 / metal3.width.1 min 280
TRACK_SP = 320  # metal2.space.1 / metal3.space.1 min 280
TRACK_PITCH = TRACK_W + TRACK_SP  # 720 nm

#: Vertical band that must stay above each row's devices in the proposed
#: scheme, for the Metal1 -> Via1 -> Metal2 hop off a gate stub. Budget:
#: ``generate.BAR_TOP`` (700 nm of Metal1 bar already drawn above each MOS
#: COMP) + half a Via1 landing pad (200 nm) + one ``metal1.space.1`` (230 nm,
#: rounded to 100 here as the pad is centred inside the existing bar) = 1.0 um.
#: Compare ``generate.HEAD + generate.BAR_W // 2`` = 1.5 um, the *current*
#: cost of a single-rail row (``NTAP``); ``LANDING_BAND_CONSERVATIVE`` keeps
#: that value so the estimate is bracketed rather than tuned.
LANDING_BAND = 1000
LANDING_BAND_CONSERVATIVE = generate.HEAD + generate.BAR_W // 2  # 1500 nm

#: Marker overhang the written GDS carries beyond ``build()``'s own bbox: the
#: guard ring's Pplus is drawn ``IMPLANT_ENC`` outside the ring's COMP on
#: every side. Added so modelled areas are directly comparable with
#: ``area_report.py``'s measured GDS bounding box.
GDS_MARKER_MARGIN = 2 * plan_mod.IMPLANT_ENC  # 400 nm per axis


@dataclass(frozen=True)
class RowTerms:
    """One row's contribution to the block's height and width."""

    name: str
    width_nm: int  # device-field extent of the row (excludes the corridor)
    content_nm: int  # device content height (the tallest item in the row)
    rail_band_nm: int  # stacked Metal1 rail band drawn above the content
    rails: int  # distinct nets rail-routed in this row
    item_area_nm2: int  # sum of the row's drawn item bounding boxes


@dataclass(frozen=True)
class Decomposition:
    """The drawn block, split into the terms ``generate.build()`` places."""

    rows: tuple[RowTerms, ...]
    routed_nets: int
    corridor_nm: int  # Poly2 spine corridor + FIELD_GAP, down the left edge
    left_margin_nm: int  # the vss spine's own half-width, left of x = 0
    bottom_margin_nm: int  # POLY_EXT below the bottom row
    row_gap_nm: int  # total inter-row gap
    guard_nm: int  # guard ring + clearance, per axis (both sides)
    body_area_um2: float  # device body area, from the current netlist

    # -- measured totals ---------------------------------------------------- #
    @property
    def field_width_nm(self) -> int:
        return max(row.width_nm for row in self.rows)

    @property
    def content_height_nm(self) -> int:
        return sum(row.content_nm for row in self.rows)

    @property
    def rail_height_nm(self) -> int:
        return sum(row.rail_band_nm for row in self.rows)

    @property
    def row_box_area_nm2(self) -> int:
        """Sum of per-row bounding boxes — the block with *all* stripe
        whitespace removed but each row kept intact."""
        return sum(row.width_nm * row.content_nm for row in self.rows)

    @property
    def item_area_nm2(self) -> int:
        """Sum of the drawn item bounding boxes — the placement floor."""
        return sum(row.item_area_nm2 for row in self.rows)

    def width_nm(self, corridor_nm: int | None = None) -> int:
        corridor = self.corridor_nm if corridor_nm is None else corridor_nm
        return self.left_margin_nm + corridor + self.field_width_nm + self.guard_nm

    def height_nm(self, landing_band_nm: int | None = None) -> int:
        rails = (
            self.rail_height_nm
            if landing_band_nm is None
            else landing_band_nm * len(self.rows)
        )
        return (
            self.bottom_margin_nm
            + self.content_height_nm
            + rails
            + self.row_gap_nm
            + self.guard_nm
        )


def decompose() -> tuple[Decomposition, dict]:
    """Build the block in memory and split its bounding box into terms."""
    flat, rows = plan_mod.load_plan()
    nets = plan_mod.routed_nets(rows)
    field_x0 = len(nets) * generate.SPINE_PITCH + generate.FIELD_GAP

    _builder, stats = generate.build()

    row_terms: list[RowTerms] = []
    for geo in stats["rows"]:
        item_area = 0
        for item, _x, item_w in geo["placements"]:
            _w, item_h = generate.item_size(item)
            item_area += item_w * item_h
        row_terms.append(
            RowTerms(
                name=geo["row"].name,
                width_nm=geo["right"] - field_x0,
                content_nm=geo["content_top"] - geo["y0"],
                rail_band_nm=geo["top"] - geo["content_top"],
                rails=len(geo["nets"]),
                item_area_nm2=item_area,
            )
        )

    body_rows = area_report.body_area_um2(flat)
    decomposition = Decomposition(
        rows=tuple(row_terms),
        routed_nets=len(nets),
        corridor_nm=field_x0,
        left_margin_nm=generate.SPINE_W // 2,
        bottom_margin_nm=generate.POLY_EXT,
        row_gap_nm=(len(row_terms) - 1) * generate.ROW_GAP,
        guard_nm=2 * (generate.GUARD_W + generate.GUARD_CLEAR),
        body_area_um2=sum(area for _p, _b, area in body_rows),
    )
    return decomposition, stats


def check_identity(d: Decomposition, stats: dict) -> tuple[int, int]:
    """Assert the decomposition reconstructs ``build()``'s own bounding box.

    Returns the reconstructed ``(width, height)`` in nm. This is what stops
    the model below from being a plausible-looking story: every nanometre of
    the drawn block is accounted for by exactly one term.
    """
    x0, y0, x1, y1 = stats["bbox"]
    drawn_w, drawn_h = x1 - x0, y1 - y0
    model_w, model_h = d.width_nm(), d.height_nm()
    if (model_w, model_h) != (drawn_w, drawn_h):
        raise AssertionError(
            "routing_budget's decomposition no longer reconstructs the drawn "
            f"block: model {model_w} x {model_h} nm vs. drawn {drawn_w} x "
            f"{drawn_h} nm. generate.build() has grown a term this module "
            "does not model -- fix the decomposition, do not adjust the model."
        )
    return model_w, model_h


def track_fit(d: Decomposition) -> list[tuple[str, int, int, int]]:
    """Per-row Metal3 rail-track demand vs. the row's own device height.

    In the proposed scheme a row's rails run *over* its devices on Metal3
    instead of stacking above them on Metal1, so they cost zero block height
    — provided the row is tall enough to hold them at ``TRACK_PITCH``.
    Returns ``(row, rails, demand_nm, content_nm)`` per row.
    """
    return [
        (row.name, row.rails, row.rails * TRACK_PITCH, row.content_nm)
        for row in d.rows
    ]


def um2(nm2: float) -> float:
    return nm2 / 1e6


def gds_area_um2(width_nm: int, height_nm: int) -> float:
    """Modelled area in the same units ``area_report.py`` measures.

    ``build()``'s bbox excludes the guard ring's own Pplus marker overhang;
    the written GDS includes it, which is the 0.4 um per axis difference
    between this module's model and ``area_report.py``'s measurement.
    """
    return um2(
        (width_nm + GDS_MARKER_MARGIN) * (height_nm + GDS_MARKER_MARGIN)
    )


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    area_um2: float

    def multiplier(self, body_um2: float) -> float:
        return self.area_um2 / body_um2


def scenarios(d: Decomposition) -> list[Scenario]:
    """The as-drawn block and the modelled multi-metal variants."""
    out = [
        Scenario(
            "S0",
            "as drawn: Poly2 corridor + stacked Metal1 rails",
            gds_area_um2(d.width_nm(), d.height_nm()),
        ),
        Scenario(
            "S1",
            f"M2/M3 over-the-cell, {LANDING_BAND / 1000:g} um landing band",
            gds_area_um2(d.width_nm(corridor_nm=0), d.height_nm(LANDING_BAND)),
        ),
        Scenario(
            "S1c",
            f"S1, conservative {LANDING_BAND_CONSERVATIVE / 1000:g} um landing band",
            gds_area_um2(
                d.width_nm(corridor_nm=0), d.height_nm(LANDING_BAND_CONSERVATIVE)
            ),
        ),
        Scenario(
            "S2",
            "bound: S1 with a zero-height landing band (unbuildable)",
            gds_area_um2(d.width_nm(corridor_nm=0), d.height_nm(0)),
        ),
    ]
    return out


def repack_area_um2(d: Decomposition, efficiency: float, landing_band_nm: int) -> float:
    """Area of a square block packing the rows at ``efficiency`` (S3 family).

    Each row keeps its own footprint (device content + the landing band), but
    rows are no longer forced to a single full-width stripe — which is only
    possible once rails stop having to reach a left-edge corridor, i.e. once
    the routing is multi-metal. ``efficiency`` is the fraction of the
    content box the row footprints fill.
    """
    packed_nm2 = sum(
        row.width_nm * (row.content_nm + landing_band_nm) for row in d.rows
    ) / efficiency
    side_nm = packed_nm2 ** 0.5
    return gds_area_um2(
        int(side_nm + d.guard_nm), int(side_nm + d.guard_nm)
    )


def required_efficiency(d: Decomposition, target_um2: float, landing_band_nm: int) -> float:
    """Row-packing efficiency a square re-packed block needs to hit ``target``."""
    guard = d.guard_nm + GDS_MARKER_MARGIN
    # (side + guard)^2 = target  ->  side = sqrt(target) - guard
    side_nm = (target_um2 * 1e6) ** 0.5 - guard
    if side_nm <= 0:
        return float("inf")
    packed_nm2 = sum(
        row.width_nm * (row.content_nm + landing_band_nm) for row in d.rows
    )
    return packed_nm2 / (side_nm * side_nm)


def main() -> int:
    d, stats = decompose()
    model_w, model_h = check_identity(d, stats)
    body = d.body_area_um2
    target = area_report.RATIFIED_TARGET_UM2

    print("Drawn block, decomposed (all terms from generate.build(), nm -> um)")
    print(f"  routed nets                 : {d.routed_nets}")
    print(f"  Poly2 corridor + field gap  : {d.corridor_nm / 1000:8.2f} um  (width)")
    print(f"  device field                : {d.field_width_nm / 1000:8.2f} um  (width)")
    print(f"  left margin (spine half-w)  : {d.left_margin_nm / 1000:8.2f} um  (width)")
    print(f"  device content              : {d.content_height_nm / 1000:8.2f} um  (height)")
    print(f"  stacked Metal1 rail bands   : {d.rail_height_nm / 1000:8.2f} um  (height)")
    print(f"  inter-row gaps              : {d.row_gap_nm / 1000:8.2f} um  (height)")
    print(f"  bottom margin (POLY_EXT)    : {d.bottom_margin_nm / 1000:8.2f} um  (height)")
    print(f"  guard ring + clearance      : {d.guard_nm / 1000:8.2f} um  (both axes)")
    print(f"  -> reconstructs build() bbox: {model_w / 1000:.2f} x {model_h / 1000:.2f} um  [checked]")
    print()

    print("Per-row terms and proposed Metal3 rail fit")
    print(f"  {'row':<11} {'width':>8} {'content':>8} {'railband':>9} "
          f"{'rails':>6} {'M3 need':>8} {'fit':>6}")
    for row, (_n, rails, demand, content) in zip(d.rows, track_fit(d)):
        fit = "ok" if demand <= content else "TIGHT"
        print(
            f"  {row.name:<11} {row.width_nm / 1000:8.2f} {row.content_nm / 1000:8.2f} "
            f"{row.rail_band_nm / 1000:9.2f} {rails:6d} {demand / 1000:8.2f} {fit:>6}"
        )
    bundle = d.routed_nets * TRACK_PITCH
    print(f"  Metal2 spine bundle         : {bundle / 1000:.2f} um of the "
          f"{d.field_width_nm / 1000:.2f} um device field "
          f"({100 * bundle / d.field_width_nm:.1f} %)")
    print(f"  track geometry              : {TRACK_W / 1000:.2f} um wide, "
          f"{TRACK_SP / 1000:.2f} um space (deck minima 0.28 / 0.28)")
    print()

    print("Packing, as drawn")
    content_box = d.field_width_nm * (d.content_height_nm + d.row_gap_nm)
    print(f"  sum of item bounding boxes  : {um2(d.item_area_nm2):10.2f} um^2")
    print(f"  sum of row bounding boxes   : {um2(d.row_box_area_nm2):10.2f} um^2")
    print(f"  full-width row-stripe box   : {um2(content_box):10.2f} um^2")
    print(f"  -> row boxes fill it        : {100 * d.row_box_area_nm2 / content_box:9.1f} %")
    print()

    print("Modelled scenarios (areas comparable with area_report.py's GDS bbox)")
    print(f"  device body area (netlist)  : {body:10.2f} um^2")
    print(f"  ratified target             : {target:10.2f} um^2 "
          f"-> needs <= {target / body:.2f}x body area")
    print()
    print(f"  {'':<4} {'area um^2':>11} {'mult':>7} {'vs target':>11}  scenario")
    for scenario in scenarios(d):
        delta = scenario.area_um2 - target
        print(
            f"  {scenario.key:<4} {scenario.area_um2:11.2f} "
            f"{scenario.multiplier(body):6.2f}x {delta:+11.2f}  {scenario.label}"
        )
    print()

    print("S3 family: S1 plus a 2-D re-pack of the rows (routing change is a "
          "prerequisite, not sufficient)")
    for efficiency in (0.60, 0.70, 0.80, 0.90):
        area = repack_area_um2(d, efficiency, LANDING_BAND)
        print(
            f"  packing efficiency {efficiency:.2f}      : {area:10.2f} um^2 "
            f"{area / body:6.2f}x {area - target:+11.2f} vs target"
        )
    need = required_efficiency(d, target, LANDING_BAND)
    have = d.row_box_area_nm2 / content_box
    print(f"  -> efficiency needed to hit the ratified target: {need:.3f} "
          f"(row-stripe floorplan achieves {have:.3f} today)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
