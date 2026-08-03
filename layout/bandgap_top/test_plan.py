#!/usr/bin/env python3
"""Unit tests for ``plan.py``'s folded-resistor geometry (gf180-bandgap#86).

No PDK and no ``klayout`` package required -- ``plan.py`` and
``netlist_model.py`` are pure stdlib, parsing the committed schematic
netlist directly.

    python3 -m unittest layout.bandgap_top.test_plan -v
    # or, from this directory:
    python3 -m unittest test_plan -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plan  # noqa: E402


class ResGeometryLengthTests(unittest.TestCase):
    """``res_geometry``'s leg length must reproduce the schematic ``r_length``.

    ``klt extract`` reports a resistor's drawn length as
    ``res_body_area_nm2(item) / item.width_nm`` (see that function's
    docstring for the corner and pad-sliver terms `klt`'s recognised body
    picks up). Before #86 the leg formula budgeted a whole fold *pitch*
    (``width + POLY_SP``) per link, but a link only contributes ``POLY_SP``
    of new area -- the link box overlaps both legs it joins by a full leg
    width -- so every folded resistor drew ``(n - 1) * width_nm`` short of
    its schematic length. This test pins the corrected formula so that
    regression cannot silently reoccur.
    """

    @classmethod
    def setUpClass(cls) -> None:
        flat, rows = plan.load_plan()
        cls.res_items: list[plan.ResItem] = [
            item for row in rows for item in row.items if isinstance(item, plan.ResItem)
        ]
        # Sanity: this design has folded resistors with more than one
        # distinct fold count (28, 4, 57) plus unfolded trim-ladder units are
        # handled by a separate TrimLadderItem/trim_geometry path entirely,
        # so nothing here is exercising a degenerate n=1 case only.
        if not cls.res_items:
            raise AssertionError("expected at least one ResItem in the plan")

    def test_every_res_item_has_at_least_one_fold(self) -> None:
        # If this design ever adds an unfolded (segments=1) ResItem, the
        # formula below still has to hold -- see test_edge_case_single_segment.
        segment_counts = {item.key: item.segments for item in self.res_items}
        self.assertIn("core.R1", segment_counts)
        self.assertIn("core.R2", segment_counts)
        self.assertIn("startup.RPU", segment_counts)
        # The three real fold counts this layout draws, per #86's "Measured
        # effect" table -- pinning them catches an accidental re-fold that
        # would silently narrow this test's coverage.
        self.assertEqual(segment_counts["core.R1"], 28)
        self.assertEqual(segment_counts["core.R2"], 4)
        self.assertEqual(segment_counts["startup.RPU"], 57)

    def test_drawn_body_length_matches_schematic_r_length(self) -> None:
        """``res_body_area_nm2(item) / item.width_nm == item.length_nm``.

        Tolerance is ``item.segments`` dbu (one dbu per fold), per #86's own
        acceptance criteria -- the leg formula floor-divides, so up to
        ``n - 1`` dbu of the schematic length can be lost to integer
        rounding across ``n`` legs.
        """
        for item in self.res_items:
            with self.subTest(item=item.key, segments=item.segments):
                area = plan.res_body_area_nm2(item)
                self.assertEqual(area % item.width_nm, 0, f"{item.key}: area not a multiple of width")
                drawn_length_nm = area // item.width_nm
                delta = abs(drawn_length_nm - item.length_nm)
                self.assertLessEqual(
                    delta,
                    item.segments,
                    f"{item.key}: drawn length {drawn_length_nm} nm vs "
                    f"schematic r_length {item.length_nm} nm (n={item.segments})",
                )

    def test_pre_86_pitch_based_formula_would_undershoot(self) -> None:
        """Regression guard: the old ``pitch``-per-link budget draws short.

        Reproduces the pre-#86 formula directly (not by calling
        ``res_geometry``) and confirms it under-draws every folded item by
        ``(n - 1) * width_nm`` -- so if a future edit reintroduces the bug,
        this test documents exactly what it would look like, even though the
        primary regression guard is ``test_drawn_body_length_matches_schematic_r_length``
        above.
        """
        for item in self.res_items:
            if item.segments <= 1:
                continue
            with self.subTest(item=item.key):
                n = item.segments
                pitch = item.width_nm + plan.POLY_SP
                old_leg = (item.length_nm - (n - 1) * pitch) // n
                old_area = (
                    n * item.width_nm * old_leg
                    + (n - 1) * plan.POLY_SP * item.width_nm
                    + 2 * item.width_nm * plan.IMPLANT_ENC
                )
                old_drawn_length_nm = old_area // item.width_nm
                shortfall = item.length_nm - old_drawn_length_nm
                # The old formula's shortfall is (n - 1) * width_nm minus the
                # 2 * IMPLANT_ENC pad-sliver credit res_body_area_nm2 already
                # accounts for (see its docstring), modulo floor-division
                # rounding of at most n dbu -- this is #86's own "Measured
                # effect" table, reproduced exactly (e.g. core.R1: -53.62 um).
                self.assertGreater(shortfall, 0, f"{item.key}: pre-#86 formula should undershoot")
                self.assertAlmostEqual(
                    shortfall,
                    (n - 1) * item.width_nm - 2 * plan.IMPLANT_ENC,
                    delta=n,
                )

    def test_edge_case_single_segment(self) -> None:
        """A hypothetical unfolded (``segments=1``) item has no fold links.

        ``(n - 1) * POLY_SP == 0`` for ``n == 1``, so the formula reduces to
        budgeting the whole length minus the two pad slivers -- still an
        exact match (no floor-division loss at all, since there is only one
        leg to divide into).
        """
        item = plan.ResItem(
            key="test.unfolded",
            width_nm=2000,
            length_nm=10_000,
            segments=1,
            nets=("a", "b"),
        )
        area = plan.res_body_area_nm2(item)
        drawn_length_nm = area // item.width_nm
        self.assertEqual(drawn_length_nm, item.length_nm)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
