#!/usr/bin/env python3
"""Unit tests for ``layout/common/klayout_builder.py`` (gf180-bandgap#167).

    python3 -m unittest layout.common.test_klayout_builder -v
    # or, from this directory:
    python3 -m unittest test_klayout_builder -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from klayout_builder import BuilderBase  # noqa: E402

L_POLY2 = (30, 0)
L_METAL1 = (34, 0)
L_METAL1_LBL = (34, 10)

LAYER_NAMES = {
    L_POLY2: "Poly2",
    L_METAL1: "Metal1",
}


class BuilderBaseTests(unittest.TestCase):
    def test_creates_top_cell_with_requested_name(self) -> None:
        b = BuilderBase("probe_top", LAYER_NAMES)
        self.assertEqual(b.cell.name, "probe_top")

    def test_dbu_is_one_picometre(self) -> None:
        b = BuilderBase("probe_top", LAYER_NAMES)
        self.assertEqual(b.layout.dbu, 0.001)

    def test_registers_exactly_the_supplied_layers(self) -> None:
        b = BuilderBase("probe_top", LAYER_NAMES)
        self.assertEqual(set(b._layers.keys()), set(LAYER_NAMES.keys()))
        for pair, name in LAYER_NAMES.items():
            info = b.layout.get_info(b._layers[pair])
            self.assertEqual((info.layer, info.datatype), pair)
            self.assertEqual(info.name, name)

    def test_does_not_register_a_layer_absent_from_layer_names(self) -> None:
        """A caller with a smaller LAYER_NAMES (e.g. m2m3_stack_probe's 10
        entries vs. bandgap_top's 23) must not pick up layers it never
        listed -- LAYER_NAMES stays per-caller, not centralized here."""
        b = BuilderBase("probe_top", {L_POLY2: "Poly2"})
        self.assertNotIn(L_METAL1, b._layers)

    def test_box_inserts_on_the_registered_layer(self) -> None:
        b = BuilderBase("probe_top", LAYER_NAMES)
        b.box(L_METAL1, 0, 0, 1000, 500)
        shapes = list(b.cell.shapes(b._layers[L_METAL1]).each())
        self.assertEqual(len(shapes), 1)
        box = shapes[0].box
        self.assertEqual((box.left, box.bottom, box.right, box.top), (0, 0, 1000, 500))

    def test_box_on_a_different_layer_does_not_leak_into_another(self) -> None:
        b = BuilderBase("probe_top", LAYER_NAMES)
        b.box(L_POLY2, 0, 0, 100, 100)
        self.assertEqual(len(list(b.cell.shapes(b._layers[L_METAL1]).each())), 0)
        self.assertEqual(len(list(b.cell.shapes(b._layers[L_POLY2]).each())), 1)

    def test_two_instances_use_independent_layouts(self) -> None:
        """Each BuilderBase() call must create its own kdb.Layout/cell --
        callers rely on this to build multiple independent GDS outputs
        (bandgap_top and m2m3_stack_probe) in the same process/test run."""
        a = BuilderBase("top_a", LAYER_NAMES)
        b = BuilderBase("top_b", LAYER_NAMES)
        a.box(L_METAL1, 0, 0, 10, 10)
        self.assertEqual(len(list(b.cell.shapes(b._layers[L_METAL1]).each())), 0)
        self.assertNotEqual(a.cell.name, b.cell.name)


if __name__ == "__main__":
    unittest.main()
