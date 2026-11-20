#!/usr/bin/env python3
"""Regression guard: every via cut in the committed GDS is landed.

#504 found a Via1 in ``bandgap_top.gds`` with *nothing beneath it* — an
orphan cut the released ``klt`` DRC deck cannot see, because
``metal1.enclosing.via1.1`` pre-filters with ``.interacting``: a cut with
zero overlap on the conductor below is skipped rather than flagged. PR #506
removed that orphan (a vestigial MiM-cap down-hop); this test keeps it
removed.

For each via layer in the committed ``bandgap_top.gds``, every cut must be
fully covered by the metal **below** and the metal **above**::

    Region(via) - Region(metal) == {}

Checked pairs (gf180mcu GDS numbering, layer constants imported from
``generate`` so this test cannot drift from what is drawn): Via1 against
Metal1+Metal2, Via2 against Metal2+Metal3, Via3 against Metal3+Metal4,
Via4 against Metal4+Metal5.

Via counts are pinned to #507's measurement (Via1 300 / Via2 371 /
Via3 2 / Via4 2) so a layer-number typo that resolves an empty layer
cannot pass vacuously. ``CheckerNegativeControlTests`` asserts the check
itself flags #504's exact orphan box ``(62870,134020;63130,134280)`` — the
box measured failing on the pre-fix GDS (``4161a1b7``, Via1 count 301,
uncovered_by_Metal1 = 1).

The ``layout/drc/fixtures/m2m3_stack_probe`` fixture satisfies the same
invariant on the via layers it draws (Via1/Via2, 4 cuts each; it carries
no Via3/Via4), so it is covered here too (#507 acceptance criterion 4).

Needs the ``klayout`` module; skipped where it is absent, same as any
other layout-side check::

    uv run --with klayout python3 -m unittest \\
        layout.bandgap_top.test_via_landing -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Load-bearing: sys.path[0] is this file's dir only under `python3 file.py`.
# Under the documented `python3 -m <dotted.module>` form it is the CWD. #479
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import klayout.db

    HAVE_KLAYOUT = True
except ImportError:  # pragma: no cover - environment-dependent
    HAVE_KLAYOUT = False

if HAVE_KLAYOUT:
    import generate

GDS = Path(__file__).resolve().parent / "bandgap_top.gds"
FIXTURE_GDS = (
    Path(__file__).resolve().parents[2]
    / "layout"
    / "drc"
    / "fixtures"
    / "m2m3_stack_probe"
    / "m2m3_stack_probe.gds"
)

#: #507's measurement on #506's regenerated GDS. A count drift here means
#: the routing stack changed — re-measure and re-pin deliberately, do not
#: delete the assertion.
EXPECTED_VIA_COUNTS = {"Via1": 300, "Via2": 371, "Via3": 2, "Via4": 2}

#: The fixture draws only a Metal2/Metal3 stack probe (#507 AC 4): Via1 and
#: Via2 cuts, no Via3/Via4 layers at all.
EXPECTED_FIXTURE_VIA_COUNTS = {"Via1": 4, "Via2": 4}


def _via_pairs() -> list[tuple[str, tuple, str, tuple, str, tuple]]:
    """(via name, via layer, below name, below layer, above name, above layer)."""
    return [
        ("Via1", generate.L_VIA1, "Metal1", generate.L_METAL1, "Metal2", generate.L_METAL2),
        ("Via2", generate.L_VIA2, "Metal2", generate.L_METAL2, "Metal3", generate.L_METAL3),
        ("Via3", generate.L_VIA3, "Metal3", generate.L_METAL3, "Metal4", generate.L_METAL4),
        ("Via4", generate.L_VIA4, "Metal4", generate.L_METAL4, "Metal5", generate.L_METAL5),
    ]


def _load(path: Path) -> tuple[klayout.db.Layout, list]:
    """Read a GDS and flatten every top cell so all shapes are reachable."""
    layout = klayout.db.Layout()
    layout.read(str(path))
    tops = layout.top_cells()
    for cell in tops:
        cell.flatten(-1, True)
    return layout, tops


def _require_layer(layout: klayout.db.Layout, layer: tuple, what: str) -> int:
    li = layout.find_layer(*layer)
    if li is None:
        raise AssertionError(f"{what} layer {layer} not present in the GDS")
    return li


def _merged_region(tops: list, li: int) -> klayout.db.Region:
    region = klayout.db.Region()
    for cell in tops:
        region += klayout.db.Region(cell.shapes(li))
    return region


def _shape_count(tops: list, li: int) -> int:
    return sum(cell.shapes(li).size() for cell in tops)


def _uncovered(
    layout: klayout.db.Layout, tops: list, via_layer: tuple, metal_layer: tuple
) -> list[tuple[int, int, int, int]]:
    """``(left, bottom, right, top)`` dbu boxes of via area with no metal."""
    via_li = _require_layer(layout, via_layer, "via")
    metal_li = _require_layer(layout, metal_layer, "metal")
    uncovered = _merged_region(tops, via_li) - _merged_region(tops, metal_li)
    return [
        (b.left, b.bottom, b.right, b.top) for b in (p.bbox() for p in uncovered.each())
    ]


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class CommittedGdsViaLandingTests(unittest.TestCase):
    """The guard itself: #504's defect class cannot re-enter the GDS."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.layout, cls.tops = _load(GDS)

    def test_every_cut_is_covered_by_the_metal_below_and_above(self) -> None:
        for via_name, via_l, below_name, below_l, above_name, above_l in _via_pairs():
            for metal_name, metal_l in (
                (below_name, below_l),
                (above_name, above_l),
            ):
                with self.subTest(via=via_name, metal=metal_name):
                    boxes = _uncovered(self.layout, self.tops, via_l, metal_l)
                    self.assertEqual(
                        boxes,
                        [],
                        f"{via_name} cuts not covered by {metal_name} "
                        f"(dbu boxes, first 3 of {len(boxes)}): {boxes[:3]}",
                    )

    def test_via_counts_match_the_507_measurement(self) -> None:
        for via_name, via_l, *_ in _via_pairs():
            with self.subTest(via=via_name):
                li = _require_layer(self.layout, via_l, via_name)
                self.assertEqual(_shape_count(self.tops, li), EXPECTED_VIA_COUNTS[via_name])


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class M2M3FixtureViaLandingTests(unittest.TestCase):
    """#507 AC 4: the stack-probe fixture upholds the same invariant on the
    via layers it draws. It carries no Via3/Via4 stack, so those pairs are
    absent by design — but at least Via1 and Via2 must have been checked,
    otherwise the pass would be vacuous."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.layout, cls.tops = _load(FIXTURE_GDS)

    def test_drawn_via_pairs_are_fully_landed(self) -> None:
        checked = []
        for via_name, via_l, below_name, below_l, above_name, above_l in _via_pairs():
            if self.layout.find_layer(*via_l) is None:
                continue
            checked.append(via_name)
            with self.subTest(via=via_name):
                li = _require_layer(self.layout, via_l, via_name)
                self.assertEqual(
                    _shape_count(self.tops, li),
                    EXPECTED_FIXTURE_VIA_COUNTS[via_name],
                )
                for metal_name, metal_l in (
                    (below_name, below_l),
                    (above_name, above_l),
                ):
                    boxes = _uncovered(self.layout, self.tops, via_l, metal_l)
                    self.assertEqual(
                        boxes,
                        [],
                        f"{via_name} cuts not covered by {metal_name} "
                        f"(dbu boxes, first 3 of {len(boxes)}): {boxes[:3]}",
                    )
        self.assertGreaterEqual(set(checked), {"Via1", "Via2"})


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class CheckerNegativeControlTests(unittest.TestCase):
    """The check must flag an orphan cut, not swallow it: #504's exact Via1
    box on a synthetic layout, with a properly landed neighbour that must
    stay silent."""

    def test_orphan_cut_is_reported_and_landed_cut_is_not(self) -> None:
        layout = klayout.db.Layout()
        layout.dbu = 0.001
        top = layout.create_cell("synthetic")
        via_li = layout.layer(*generate.L_VIA1)
        m1_li = layout.layer(*generate.L_METAL1)
        m2_li = layout.layer(*generate.L_METAL2)
        # #504's orphan: a Via1 with Metal2 above it but nothing beneath.
        top.shapes(via_li).insert(klayout.db.Box(62870, 134020, 63130, 134280))
        top.shapes(m2_li).insert(klayout.db.Box(62800, 133950, 63200, 134350))
        # A properly landed neighbour must not be flagged.
        top.shapes(via_li).insert(klayout.db.Box(1000, 1000, 1260, 1260))
        top.shapes(m1_li).insert(klayout.db.Box(990, 990, 1270, 1270))
        top.shapes(m2_li).insert(klayout.db.Box(990, 990, 1270, 1270))

        tops = [top]
        uncovered_below = _uncovered(layout, tops, generate.L_VIA1, generate.L_METAL1)
        uncovered_above = _uncovered(layout, tops, generate.L_VIA1, generate.L_METAL2)
        self.assertEqual(uncovered_below, [(62870, 134020, 63130, 134280)])
        self.assertEqual(uncovered_above, [])


if __name__ == "__main__":
    unittest.main()
