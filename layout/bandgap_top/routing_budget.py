#!/usr/bin/env python3
"""Where ``bandgap_top``'s drawn area goes, now that it routes on Metal2/Metal3.

The area *verdict* lives in :mod:`area_report` (drawn GDS bbox vs. the
ratified target). This module answers the follow-up question #156/DR-0005
left open: **of the overhead multiplier over device body area, how much is
routing, and how much is floorplan?**

Its baseline moved with gf180-bandgap#166. Until that issue ``generate.py``
drew the single-metal corridor-and-rail scheme, and this module *estimated*
what a Metal2/Metal3 over-the-cell re-route would recover
(``layout/routing/multi-metal-routing-study.md``, gf180-bandgap#160). That
re-route is now **drawn**, so the two roles swap: the estimate becomes a
recorded number to check the implementation against, and the decomposition
below describes the multi-metal block that actually exists.

It does that in four steps:

1. **Decompose the drawn block** into the terms ``generate.build()`` itself
   places — the device field's width, each row's device content height, the
   inter-row gaps, the bottom margin and the guard ring. There is no
   corridor term and no rail-band term any more; that is the whole point of
   #166. The decomposition is *checked* rather than asserted: its
   reconstructed bounding box must equal ``build()``'s to the nanometre (see
   ``check_identity``), so a term cannot be quietly mis-attributed.
2. **Check the drawn routing really fits over the cells**, track by track,
   against the installed gf180mcu DRC deck's real Metal2/Metal3 width/space
   minima — per row, does the row's own device height hold the Metal3 rails
   ``generate.route_rows`` drew into it, and does the Metal2 spine bundle fit
   across the device field?
3. **Compare the study's estimate against the realised measurement**
   (``STUDY_ESTIMATE_AREA_UM2`` vs. the drawn ``S1``) — the "estimate vs.
   measurement" record ``AREA.md`` Finding 6 carries.
4. **Model what is left** — the row-stripe floorplan whitespace, which
   routing does not touch — and print the row-packing efficiency the
   currently-ratified/interim target (``area_report.RATIFIED_TARGET_UM2``;
   see ``spec/decision-records/`` for its current provenance) still needs.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_top/routing_budget.py

Every number printed here comes from the current netlist and the current
generator, so the write-ups that quote it cannot silently go stale the way
``floorplan.md`` §8's estimate did (``AREA.md`` Finding 1). The two numbers
that *cannot* be re-derived — the pre-#166 measurement, and the study's
estimate of what would replace it — are carried as named constants with
their provenance, and are never recomputed.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import area_report  # noqa: E402
import generate  # noqa: E402
import plan as plan_mod  # noqa: E402

# --------------------------------------------------------------------------- #
# Drawn routing-track geometry, in nanometres.
#
# Taken from `generate` rather than re-declared here, so this module reports
# what is actually drawn instead of what someone once intended to draw. The
# deck minima these have to clear (`metal2.width.1`/`metal3.width.1` 280 nm,
# `metal2.space.1`/`metal3.space.1` 280 nm, read out of the installed
# klayout_tools/decks/gf180mcu.py at klt 0.2.0) are asserted against these
# values in test_routing_budget.py, so a deck update that moves a minimum
# fails loudly instead of drifting.
#
# Metal4 is deliberately NOT routed on: the deck has no metal4.width/space
# rule at all (Metal4 appears only inside the MiM-capacitor rules), so
# routing on it would put block geometry outside DRC coverage -- and stray
# Metal4 near the compensation cap is exactly what `mim.space.1` polices.
# Metal5 is left to the MiM cap's own `fb` wire.
# --------------------------------------------------------------------------- #
TRACK_W = generate.TRACK_W  # 400 nm
TRACK_SP = generate.TRACK_SP  # 320 nm
TRACK_PITCH = generate.TRACK_PITCH  # 720 nm

#: Marker overhang the written GDS carries beyond ``build()``'s own bbox: the
#: guard ring's Pplus is drawn ``IMPLANT_ENC`` outside the ring's COMP on
#: every side. Added so modelled areas are directly comparable with
#: ``area_report.py``'s measured GDS bounding box.
GDS_MARKER_MARGIN = 2 * plan_mod.IMPLANT_ENC  # 400 nm per axis

# --------------------------------------------------------------------------- #
# The two numbers this module can no longer derive, because the geometry they
# describe is no longer drawn. Both are recorded values with provenance, not
# recomputed ones -- see the module docstring.
# --------------------------------------------------------------------------- #

#: The single-metal block as measured immediately before gf180-bandgap#166
#: replaced it: 239.20 x 337.85 um of Poly2 corridor + stacked Metal1 rails
#: (``AREA.md`` "Headline" as of #156; the study's S0 row). Kept so the
#: recovery this rewrite achieved stays quotable from a tool run.
PRE_REWRITE_AREA_UM2 = 80813.72
PRE_REWRITE_CORRIDOR_NM = 16900  # 25 spines x SPINE_PITCH + FIELD_GAP (width)
PRE_REWRITE_RAIL_BAND_NM = 56420  # the 15 stacked Metal1 rail bands (height)

#: ``layout/routing/multi-metal-routing-study.md`` §1/§5, scenario S1 — the
#: estimate this implementation was costed against, before it was drawn. Its
#: height carried a modelled landing band of 1.0 um per row, and its width
#: conservatively kept the old scheme's 0.20 um left margin (study §5). Both
#: went to zero in the drawn result, which is Finding 6's whole content.
STUDY_ESTIMATE_AREA_UM2 = 65896.39
STUDY_ESTIMATE_LANDING_BAND_NM = 1000
STUDY_ESTIMATE_LEFT_MARGIN_NM = 200


@dataclass(frozen=True)
class RowTerms:
    """One row's contribution to the block's height and width."""

    name: str
    width_nm: int  # device-field extent of the row, from the block's left edge
    content_nm: int  # device content height (the tallest item in the row)
    rails: int  # distinct nets Metal3-rail-routed inside this row
    item_area_nm2: int  # sum of the row's drawn item bounding boxes

    @property
    def rail_demand_nm(self) -> int:
        """Height this row's own Metal3 rails occupy at ``TRACK_PITCH``.

        Costs no *block* height — the rails run over the row's own devices —
        but it has to fit inside ``content_nm`` for that to be true.
        """
        return self.rails * TRACK_PITCH


@dataclass(frozen=True)
class Decomposition:
    """The drawn block, split into the terms ``generate.build()`` places.

    Post-#166 there is no corridor term and no rail-band term: routing costs
    the block nothing in either axis, so every term below is floorplan.
    """

    rows: tuple[RowTerms, ...]
    routed_nets: int
    spine_bundle_nm: int  # width the Metal2 spines span over the device field
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
    def row_box_area_nm2(self) -> int:
        """Sum of per-row bounding boxes — the block with *all* stripe
        whitespace removed but each row kept intact."""
        return sum(row.width_nm * row.content_nm for row in self.rows)

    @property
    def item_area_nm2(self) -> int:
        """Sum of the drawn item bounding boxes — the placement floor."""
        return sum(row.item_area_nm2 for row in self.rows)

    @property
    def stripe_box_nm2(self) -> int:
        """The full-width row-stripe box the rows sit in — the whitespace
        multi-metal routing did *not* recover (study §6)."""
        return self.field_width_nm * (self.content_height_nm + self.row_gap_nm)

    @property
    def row_packing(self) -> float:
        """Fraction of the stripe box the row footprints actually fill."""
        return self.row_box_area_nm2 / self.stripe_box_nm2

    def width_nm(self) -> int:
        return self.field_width_nm + self.guard_nm

    def height_nm(self) -> int:
        return (
            self.bottom_margin_nm
            + self.content_height_nm
            + self.row_gap_nm
            + self.guard_nm
        )


def decompose() -> tuple[Decomposition, dict]:
    """Build the block in memory and split its bounding box into terms."""
    flat, rows = plan_mod.load_plan()
    nets = plan_mod.routed_nets(rows)

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
                width_nm=geo["right"],
                content_nm=geo["row_h"],
                rails=len(geo["nets"]),
                item_area_nm2=item_area,
            )
        )

    body_rows = area_report.body_area_um2(flat)
    decomposition = Decomposition(
        rows=tuple(row_terms),
        routed_nets=len(nets),
        spine_bundle_nm=max(stats["spine_x"].values()) + TRACK_W,
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

    A row's rails run *over* its devices on Metal3 instead of stacking above
    them, so they cost zero block height — provided the row is tall enough to
    hold them at ``TRACK_PITCH``. ``generate.route_rows`` asserts the same
    invariant while drawing; this is the reporting side of it.
    Returns ``(row, rails, demand_nm, content_nm)`` per row.
    """
    return [(row.name, row.rails, row.rail_demand_nm, row.content_nm) for row in d.rows]


def um2(nm2: float) -> float:
    return nm2 / 1e6


def gds_area_um2(width_nm: int, height_nm: int) -> float:
    """Modelled area in the same units ``area_report.py`` measures.

    ``build()``'s bbox excludes the guard ring's own Pplus marker overhang;
    the written GDS includes it, which is the 0.4 um per axis difference
    between this module's model and ``area_report.py``'s measurement.
    """
    return um2((width_nm + GDS_MARKER_MARGIN) * (height_nm + GDS_MARKER_MARGIN))


def drawn_area_um2(d: Decomposition) -> float:
    """The drawn block's area, in ``area_report.py``'s units."""
    return gds_area_um2(d.width_nm(), d.height_nm())


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    area_um2: float
    #: ``True`` when the number came from the current geometry; ``False`` for
    #: the recorded values that describe geometry no longer drawn.
    derived: bool

    def multiplier(self, body_um2: float) -> float:
        return self.area_um2 / body_um2


def scenarios(d: Decomposition) -> list[Scenario]:
    """The drawn block, next to the two recorded numbers it is judged against."""
    return [
        Scenario(
            "S0",
            "recorded: pre-#166 Poly2 corridor + stacked Metal1 rails",
            PRE_REWRITE_AREA_UM2,
            derived=False,
        ),
        Scenario(
            "EST",
            "recorded: study §5's estimate for the M2/M3 re-route",
            STUDY_ESTIMATE_AREA_UM2,
            derived=False,
        ),
        Scenario(
            "S1",
            "as drawn: Metal2 spines + Metal3 over-the-cell row rails",
            drawn_area_um2(d),
            derived=True,
        ),
    ]


def repack_area_um2(d: Decomposition, efficiency: float) -> float:
    """Area of a square block packing the rows at ``efficiency`` (S3 family).

    Each row keeps its own footprint (device content — the Metal3 rails are
    inside it), but rows are no longer forced into a single full-width
    stripe, which is only possible now that rails no longer have to reach a
    left-edge corridor. ``efficiency`` is the fraction of the content box the
    row footprints fill.
    """
    packed_nm2 = sum(row.width_nm * row.content_nm for row in d.rows) / efficiency
    side_nm = packed_nm2**0.5
    return gds_area_um2(int(side_nm + d.guard_nm), int(side_nm + d.guard_nm))


def required_efficiency(d: Decomposition, target_um2: float) -> float:
    """Row-packing efficiency a square re-packed block needs to hit ``target``."""
    guard = d.guard_nm + GDS_MARKER_MARGIN
    # (side + guard)^2 = target  ->  side = sqrt(target) - guard
    side_nm = (target_um2 * 1e6) ** 0.5 - guard
    if side_nm <= 0:
        return float("inf")
    packed_nm2 = sum(row.width_nm * row.content_nm for row in d.rows)
    return packed_nm2 / (side_nm * side_nm)


def main() -> int:
    d, stats = decompose()
    model_w, model_h = check_identity(d, stats)
    body = d.body_area_um2
    target = area_report.RATIFIED_TARGET_UM2

    print("Drawn block, decomposed (all terms from generate.build(), nm -> um)")
    print(f"  routed nets                 : {d.routed_nets}")
    print(f"  device field                : {d.field_width_nm / 1000:8.2f} um  (width)")
    print(f"  device content              : {d.content_height_nm / 1000:8.2f} um  (height)")
    print(f"  inter-row gaps              : {d.row_gap_nm / 1000:8.2f} um  (height)")
    print(f"  bottom margin (POLY_EXT)    : {d.bottom_margin_nm / 1000:8.2f} um  (height)")
    print(f"  guard ring + clearance      : {d.guard_nm / 1000:8.2f} um  (both axes)")
    print("  Metal2/Metal3 routing       :     0.00 um  (both axes -- over the cells)")
    print(f"  -> reconstructs build() bbox: {model_w / 1000:.2f} x {model_h / 1000:.2f} um  [checked]")
    print()

    print("Per-row terms and drawn Metal3 rail fit")
    print(f"  {'row':<11} {'width':>8} {'content':>8} {'rails':>6} {'M3 need':>8} {'fit':>6}")
    for row, (_n, rails, demand, content) in zip(d.rows, track_fit(d)):
        fit = "ok" if demand <= content else "TIGHT"
        print(
            f"  {row.name:<11} {row.width_nm / 1000:8.2f} {row.content_nm / 1000:8.2f} "
            f"{rails:6d} {demand / 1000:8.2f} {fit:>6}"
        )
    print(f"  Metal2 spine bundle         : {d.spine_bundle_nm / 1000:.2f} um across the "
          f"{d.field_width_nm / 1000:.2f} um device field "
          f"({100 * d.spine_bundle_nm / d.field_width_nm:.1f} %), over the devices")
    print(f"  track geometry              : {TRACK_W / 1000:.2f} um wide, "
          f"{TRACK_SP / 1000:.2f} um space (deck minima 0.28 / 0.28)")
    print()

    print("Packing, as drawn")
    print(f"  sum of item bounding boxes  : {um2(d.item_area_nm2):10.2f} um^2")
    print(f"  sum of row bounding boxes   : {um2(d.row_box_area_nm2):10.2f} um^2")
    print(f"  full-width row-stripe box   : {um2(d.stripe_box_nm2):10.2f} um^2")
    print(f"  -> row boxes fill it        : {100 * d.row_packing:9.1f} %")
    print()

    print("Estimate vs. measurement (#160 estimated it, #166 drew it)")
    print(f"  device body area (netlist)  : {body:10.2f} um^2")
    print(f"  ratified target             : {target:10.2f} um^2 "
          f"-> needs <= {target / body:.2f}x body area")
    print()
    print(f"  {'':<4} {'area um^2':>11} {'mult':>7} {'vs target':>11}   scenario")
    for scenario in scenarios(d):
        delta = scenario.area_um2 - target
        mark = " " if scenario.derived else "*"
        print(
            f"  {scenario.key:<4} {scenario.area_um2:11.2f} "
            f"{scenario.multiplier(body):6.2f}x {delta:+11.2f} {mark}  {scenario.label}"
        )
    print("  (* recorded value -- geometry this generator no longer draws)")
    drawn = drawn_area_um2(d)
    print()
    print(f"  recovered vs. pre-#166      : {PRE_REWRITE_AREA_UM2 - drawn:10.2f} um^2 "
          f"({100 * (PRE_REWRITE_AREA_UM2 - drawn) / PRE_REWRITE_AREA_UM2:.1f} %)")
    print(f"  drawn vs. study estimate    : {drawn - STUDY_ESTIMATE_AREA_UM2:+10.2f} um^2 "
          f"({100 * (drawn - STUDY_ESTIMATE_AREA_UM2) / STUDY_ESTIMATE_AREA_UM2:+.1f} %)")
    print("    the estimate's two stated conservatisms both went to zero: its "
          f"{STUDY_ESTIMATE_LANDING_BAND_NM / 1000:g} um/row")
    print(f"    landing band (rails ended up inside each row's own content) and the "
          f"{STUDY_ESTIMATE_LEFT_MARGIN_NM / 1000:g} um left margin it kept.")
    print()

    print("What routing did NOT fix: the row-stripe floorplan (study §6, "
          "follow-on issue)")
    for efficiency in (0.60, 0.70, 0.80, 0.90):
        area = repack_area_um2(d, efficiency)
        print(
            f"  packing efficiency {efficiency:.2f}      : {area:10.2f} um^2 "
            f"{area / body:6.2f}x {area - target:+11.2f} vs target"
        )
    need = required_efficiency(d, target)
    print(f"  -> efficiency needed to hit the ratified target: {need:.3f} "
          f"(row-stripe floorplan achieves {d.row_packing:.3f} today)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
