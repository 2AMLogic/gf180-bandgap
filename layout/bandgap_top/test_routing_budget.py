#!/usr/bin/env python3
"""Unit tests for ``routing_budget.py`` (gf180-bandgap#160).

These pin the three things ``layout/routing/multi-metal-routing-study.md``
rests on, so the study cannot go stale unnoticed the way ``floorplan.md``
§8's body-area estimate did (``AREA.md`` Finding 1):

* the area decomposition really reconstructs the drawn block (and the
  committed GDS's own measured area);
* the proposed Metal2/Metal3 track geometry clears the installed deck's
  width/space minima, and every row can hold its own rails over its devices;
* the study's headline conclusion — multi-metal routing alone does **not**
  reach the ratified target's required overhead multiplier — still holds
  against the current netlist.

Needs the ``klayout`` module (``routing_budget`` builds the block in memory);
skipped where it is absent, same as any other layout-side check::

    uv run --with klayout python3 -m unittest \\
        layout.bandgap_top.test_routing_budget -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import klayout.db  # noqa: F401

    HAVE_KLAYOUT = True
except ImportError:  # pragma: no cover - environment-dependent
    HAVE_KLAYOUT = False

if HAVE_KLAYOUT:
    import area_report
    import routing_budget

# Minima read out of the installed gf180mcu DRC deck
# (klayout_tools/decks/gf180mcu.py, klt 0.2.0), in nm. Duplicated here
# deliberately: if a deck update moves one of these, this test fails and the
# study's sizing table gets re-derived rather than silently drifting.
METAL2_WIDTH_MIN = 280  # metal2.width.1 (== metal3.width.1)
METAL2_SPACE_MIN = 280  # metal2.space.1 (== metal3.space.1)


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class DecompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.decomposition, cls.stats = routing_budget.decompose()

    def test_decomposition_reconstructs_the_drawn_block(self) -> None:
        """Every nm of ``build()``'s bbox is attributed to exactly one term."""
        width, height = routing_budget.check_identity(self.decomposition, self.stats)
        x0, y0, x1, y1 = self.stats["bbox"]
        self.assertEqual((width, height), (x1 - x0, y1 - y0))

    def test_baseline_scenario_matches_the_measured_gds_area(self) -> None:
        """S0 (the model's "as drawn") must equal what ``area_report.py``
        measures out of the committed GDS — the model is calibrated against
        real geometry, not against itself."""
        baseline = next(s for s in routing_budget.scenarios(self.decomposition)
                        if s.key == "S0")
        gds_w, gds_h = area_report.gds_bbox_um()
        self.assertAlmostEqual(baseline.area_um2, gds_w * gds_h, places=2)

    def test_row_stripe_whitespace_dominates_the_row_boxes(self) -> None:
        """The premise of the study's S3 family: most of the block's
        whitespace is *between* rows, not inside them."""
        d = self.decomposition
        stripe_box = d.field_width_nm * (d.content_height_nm + d.row_gap_nm)
        self.assertLess(d.row_box_area_nm2, stripe_box)
        self.assertGreater(d.row_box_area_nm2, d.item_area_nm2)


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class ProposedTrackGeometryTests(unittest.TestCase):
    def test_track_geometry_clears_the_deck_minima(self) -> None:
        self.assertGreaterEqual(routing_budget.TRACK_W, METAL2_WIDTH_MIN)
        self.assertGreaterEqual(routing_budget.TRACK_SP, METAL2_SPACE_MIN)
        self.assertEqual(
            routing_budget.TRACK_PITCH,
            routing_budget.TRACK_W + routing_budget.TRACK_SP,
        )

    def test_every_row_can_hold_its_rails_over_its_own_devices(self) -> None:
        """Over-the-cell Metal3 rails only cost zero block height if the row
        is tall enough to carry them at ``TRACK_PITCH``."""
        decomposition, _stats = routing_budget.decompose()
        for name, rails, demand, content in routing_budget.track_fit(decomposition):
            with self.subTest(row=name, rails=rails):
                self.assertLessEqual(demand, content)

    def test_metal2_spine_bundle_fits_across_the_device_field(self) -> None:
        decomposition, _stats = routing_budget.decompose()
        bundle = decomposition.routed_nets * routing_budget.TRACK_PITCH
        self.assertLess(bundle, decomposition.field_width_nm)


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class StudyConclusionTests(unittest.TestCase):
    """The study's two load-bearing claims, pinned against the netlist.

    If either of these fails, the *study* needs re-deriving (re-run
    ``routing_budget.py`` and update
    ``layout/routing/multi-metal-routing-study.md``) — do not delete the
    test to make it green.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.decomposition, _stats = routing_budget.decompose()
        cls.by_key = {s.key: s for s in routing_budget.scenarios(cls.decomposition)}

    def test_routing_alone_recovers_a_material_amount(self) -> None:
        s0, s1 = self.by_key["S0"], self.by_key["S1"]
        recovered = (s0.area_um2 - s1.area_um2) / s0.area_um2
        self.assertGreater(recovered, 0.10)

    def test_routing_alone_does_not_reach_the_ratified_target(self) -> None:
        body = self.decomposition.body_area_um2
        required = area_report.RATIFIED_TARGET_UM2 / body
        # Even the unbuildable zero-landing-band bound stays above it.
        self.assertGreater(self.by_key["S1"].multiplier(body), required)
        self.assertGreater(self.by_key["S2"].multiplier(body), required)

    def test_a_repack_is_what_closes_the_remaining_gap(self) -> None:
        needed = routing_budget.required_efficiency(
            self.decomposition,
            area_report.RATIFIED_TARGET_UM2,
            routing_budget.LANDING_BAND,
        )
        d = self.decomposition
        today = d.row_box_area_nm2 / (
            d.field_width_nm * (d.content_height_nm + d.row_gap_nm)
        )
        self.assertGreater(needed, today)
        self.assertLess(needed, 1.0)


if __name__ == "__main__":
    unittest.main()
