#!/usr/bin/env python3
"""Unit tests for ``routing_budget.py`` (gf180-bandgap#160, #166).

Until #166 these pinned an *estimate*: ``generate.py`` still drew the
single-metal corridor-and-rail scheme, and ``routing_budget.py`` modelled
what a Metal2/Metal3 over-the-cell re-route would recover. That re-route is
now drawn, so these tests pin the *realised* block instead:

* the area decomposition really reconstructs the drawn block — and, now that
  routing costs zero block area, that the drawn block equals what
  ``area_report.py`` measures out of the committed GDS;
* the block genuinely has no routing term left: no Poly2 corridor in the
  width, no stacked-rail band in the height, and every row's Metal3 rails fit
  inside that row's own device content at the deck-legal ``TRACK_PITCH``;
* the recovery the study estimated was actually achieved (``AREA.md``
  Finding 6's estimate-vs-measurement record);
* the study's headline conclusion — multi-metal routing alone does **not**
  reach the ratified target's required overhead multiplier — still holds
  against the *measured* block, not just against the model of it.

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
    import generate
    import routing_budget

# Minima read out of the installed gf180mcu DRC deck
# (klayout_tools/decks/gf180mcu.py, klt 0.2.0), in nm. Duplicated here
# deliberately: if a deck update moves one of these, this test fails and the
# drawn track sizing gets re-derived rather than silently drifting.
METAL2_WIDTH_MIN = 280  # metal2.width.1 (== metal3.width.1)
METAL2_SPACE_MIN = 280  # metal2.space.1 (== metal3.space.1)
VIA_WIDTH_MIN = 260  # via1.width.1 (== via2.width.1), DRM Vn.1 (#159)
VIA_ENCLOSURE_MIN = 10  # metal2.enclosing.via1.1 (== metal3.enclosing.via2.1)


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

    def test_drawn_scenario_matches_the_measured_gds_area(self) -> None:
        """S1 (the model's "as drawn") must equal what ``area_report.py``
        measures out of the committed GDS — the model is calibrated against
        real geometry, not against itself. Regenerate the GDS
        (``generate.py``) if this fails; do not adjust the model."""
        drawn = next(
            s for s in routing_budget.scenarios(self.decomposition) if s.key == "S1"
        )
        self.assertTrue(drawn.derived)
        gds_w, gds_h = area_report.gds_bbox_um()
        self.assertAlmostEqual(drawn.area_um2, gds_w * gds_h, places=2)

    def test_routing_costs_the_block_no_area_in_either_axis(self) -> None:
        """#166's whole premise: with Metal2 spines over the device field and
        Metal3 rails inside each row, the block's width is nothing but the
        device field plus the guard ring, and its height nothing but device
        content plus the row gaps and margins. A regression that reintroduced
        a corridor or a stacked-rail band would break one of these."""
        d = self.decomposition
        self.assertEqual(d.width_nm(), d.field_width_nm + d.guard_nm)
        self.assertEqual(
            d.height_nm(),
            d.bottom_margin_nm + d.content_height_nm + d.row_gap_nm + d.guard_nm,
        )

    def test_row_stripe_whitespace_dominates_the_row_boxes(self) -> None:
        """The premise of the study's S3 family: most of the block's
        whitespace is *between* rows, not inside them."""
        d = self.decomposition
        self.assertLess(d.row_box_area_nm2, d.stripe_box_nm2)
        self.assertGreater(d.row_box_area_nm2, d.item_area_nm2)


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class DrawnTrackGeometryTests(unittest.TestCase):
    """The sizing ``generate.py`` actually draws, against the deck minima."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.decomposition, _stats = routing_budget.decompose()

    def test_track_geometry_clears_the_deck_minima(self) -> None:
        self.assertGreaterEqual(routing_budget.TRACK_W, METAL2_WIDTH_MIN)
        self.assertGreaterEqual(routing_budget.TRACK_SP, METAL2_SPACE_MIN)
        self.assertEqual(
            routing_budget.TRACK_PITCH,
            routing_budget.TRACK_W + routing_budget.TRACK_SP,
        )

    def test_reported_track_geometry_is_the_drawn_track_geometry(self) -> None:
        """``routing_budget`` reports ``generate``'s constants rather than a
        second copy of them, so the report cannot describe sizing the
        generator does not draw."""
        self.assertEqual(routing_budget.TRACK_W, generate.TRACK_W)
        self.assertEqual(routing_budget.TRACK_SP, generate.TRACK_SP)
        self.assertEqual(routing_budget.TRACK_PITCH, generate.TRACK_PITCH)

    def test_drawn_via_sizing_clears_the_deck_minima(self) -> None:
        """#159's regression: ``VIA_W`` drifted below the deck's own
        ``via*.width.1`` after the deck gained the rule. Pinned here so a
        future edit cannot walk it back below the minimum, and so the routing
        stack's own metal enclosure stays legal."""
        self.assertGreaterEqual(generate.VIA_W, VIA_WIDTH_MIN)
        self.assertGreaterEqual(generate.ROUTE_VIA_ENC, VIA_ENCLOSURE_MIN)
        # A via landing on a routing track must fit inside the track itself,
        # or every landing would need extra widening the pitch does not budget.
        self.assertLessEqual(generate.ROUTE_VIA_PAD, routing_budget.TRACK_W)

    def test_every_row_holds_its_rails_over_its_own_devices(self) -> None:
        """Over-the-cell Metal3 rails only cost zero block height if the row
        is tall enough to carry them at ``TRACK_PITCH``. ``route_rows``
        asserts this while drawing; this is the independent check."""
        for name, rails, demand, content in routing_budget.track_fit(self.decomposition):
            with self.subTest(row=name, rails=rails):
                self.assertLessEqual(demand, content)

    def test_metal2_spine_bundle_fits_across_the_device_field(self) -> None:
        """The spines run *over* the device field rather than beside it, so
        the legalizer's chosen x's must all land inside that field."""
        d = self.decomposition
        self.assertLessEqual(d.spine_bundle_nm, d.field_width_nm)
        self.assertGreaterEqual(
            d.spine_bundle_nm, d.routed_nets * routing_budget.TRACK_PITCH
        )


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class RealisedRecoveryTests(unittest.TestCase):
    """Estimate vs. measurement — ``AREA.md`` Finding 6.

    If one of these fails, the *write-ups* need re-deriving (re-run
    ``routing_budget.py`` and update ``AREA.md`` / the study) — do not delete
    the test to make it green.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.decomposition, _stats = routing_budget.decompose()
        cls.by_key = {s.key: s for s in routing_budget.scenarios(cls.decomposition)}

    def test_the_rewrite_recovered_a_material_amount(self) -> None:
        s0, s1 = self.by_key["S0"], self.by_key["S1"]
        recovered = (s0.area_um2 - s1.area_um2) / s0.area_um2
        self.assertGreater(recovered, 0.10)

    def test_the_drawn_block_meets_or_beats_the_study_estimate(self) -> None:
        """The study costed this rewrite at ``STUDY_ESTIMATE_AREA_UM2``; the
        drawn block has to actually get there. It beats it, because the
        estimate's two stated conservatisms (a 1.0 um/row landing band and a
        0.20 um left margin) both went to zero — see ``AREA.md`` Finding 6."""
        self.assertLessEqual(
            self.by_key["S1"].area_um2, routing_budget.STUDY_ESTIMATE_AREA_UM2
        )

    def test_routing_alone_does_not_reach_the_ratified_target(self) -> None:
        """The study's headline conclusion, now checked against the drawn
        block rather than a model of it."""
        body = self.decomposition.body_area_um2
        required = area_report.RATIFIED_TARGET_UM2 / body
        self.assertGreater(self.by_key["S1"].multiplier(body), required)

    def test_a_repack_is_what_closes_the_remaining_gap(self) -> None:
        needed = routing_budget.required_efficiency(
            self.decomposition, area_report.RATIFIED_TARGET_UM2
        )
        self.assertGreater(needed, self.decomposition.row_packing)
        self.assertLess(needed, 1.0)


if __name__ == "__main__":
    unittest.main()
