#!/usr/bin/env python3
"""Unit tests for ``make_reference.py``'s MIM-cap plate-net modelling
(gf180-bandgap#89).

No PDK and no ``klayout``/``klt`` package required -- ``make_reference.py``,
``plan.py`` and ``netlist_model.py`` are pure stdlib, deriving the reference
netlist directly from the committed schematic netlist and plan data.

    python3 -m unittest layout.lvs.test_make_reference -v
    # or, from this directory:
    python3 -m unittest test_make_reference -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bandgap_top"))

import make_reference  # noqa: E402
import plan  # noqa: E402


class PnpJunctionParameterTests(unittest.TestCase):
    """The reference's ``bjt`` cards must carry all six junction parameters
    ``klt extract`` reports (``AE PE AB PB AC PC``), not just ``AE``
    (gf180-bandgap#111). Before this, ``PE``/``AB``/``PB``/``AC``/``PC``
    read as ``0`` on the reference side, which netgen's parameter-level
    comparator (unlike klayout's deck-aware one) flagged as 22
    ``device.property`` mismatches across the 8 drawn PNP units.

    Expected values verified against a real ``klt extract`` run of the
    committed GDS (``20260804-143026-c876a0f.extracted.spice``): every
    drawn unit (5um emitter) reports
    ``AE=25P PE=20U AB=108.16P PB=41.6U AC=108.16P PC=41.6U``.
    """

    #: bjt device card: `Qname sub base emitter bjt AE=.. PE=.. AB=.. PB=.. AC=.. PC=..`
    BJT_LINE_RE = re.compile(
        r"^Q\S+ \S+ \S+ \S+ bjt "
        r"AE=(\S+) PE=(\S+) AB=(\S+) PB=(\S+) AC=(\S+) PC=(\S+)$",
        re.M,
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.reference_text, cls.meta = make_reference.build_reference(plan.DRAWN_TRIM_CODE)
        cls.bjt_matches = cls.BJT_LINE_RE.findall(cls.reference_text)

    def test_eight_bjt_cards_found(self) -> None:
        self.assertEqual(len(self.bjt_matches), 8)
        self.assertEqual(self.meta["counts"]["bjt"], 8)

    def test_every_parameter_is_nonzero(self) -> None:
        for line_values in self.bjt_matches:
            for value in line_values:
                self.assertNotEqual(
                    float(value), 0.0, f"expected a nonzero junction parameter, got {value}"
                )

    def test_values_match_klt_extract_ground_truth(self) -> None:
        # (AE, PE, AB, PB, AC, PC) at this layout's 5um emitter, verified
        # against 20260804-143026-c876a0f.extracted.spice.
        expected = (
            2.5e-11,
            2.0e-5,
            1.0816e-10,
            4.16e-5,
            1.0816e-10,
            4.16e-5,
        )
        for line_values in self.bjt_matches:
            got = tuple(float(v) for v in line_values)
            for got_value, expected_value in zip(got, expected):
                self.assertAlmostEqual(got_value, expected_value, delta=expected_value * 1e-6)

    def test_collector_parameters_duplicate_base_parameters(self) -> None:
        # plan.pnp_base_nwell_side_nm's docstring: the deck has no drawn
        # collector-region shape to measure separately, so AC/PC duplicate
        # AB/PB exactly.
        for _ae, _pe, ab, pb, ac, pc in self.bjt_matches:
            self.assertEqual(ab, ac)
            self.assertEqual(pb, pc)

    def test_matches_plan_helper_functions(self) -> None:
        item = plan.PnpItem("t", 5.0, "e", "b")
        expected = (
            f"{plan.pnp_emitter_area_nm2(item) * 1e-18:.6e}",
            f"{plan.pnp_emitter_perimeter_nm(item) * 1e-9:.6e}",
            f"{plan.pnp_base_area_nm2(item) * 1e-18:.6e}",
            f"{plan.pnp_base_perimeter_nm(item) * 1e-9:.6e}",
            f"{plan.pnp_base_area_nm2(item) * 1e-18:.6e}",
            f"{plan.pnp_base_perimeter_nm(item) * 1e-9:.6e}",
        )
        self.assertIn(expected, self.bjt_matches)


class TopLevelPinTests(unittest.TestCase):
    """The reference's declared pin list must equal the *actually
    extractable* pin set (gf180-bandgap#111). ``nwl`` (the PMOS band's
    Nwell) is never promoted to a top-level pin by the deck -- it never
    connects Nwell to Contact, so the net carries no Metal1 label to
    promote on -- yet the reference used to declare it unconditionally,
    which netgen's stricter top-level pin-matching (unlike klayout's
    tolerant comparer) flagged as a ``pin.unmatched`` mismatch.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.reference_text, cls.meta = make_reference.build_reference(plan.DRAWN_TRIM_CODE)
        subckt_re = re.compile(r"^\.SUBCKT bandgap_top (.+)$", re.M)
        match = subckt_re.search(cls.reference_text)
        if match is None:
            raise AssertionError("expected a .SUBCKT bandgap_top header line")
        cls.declared_pins = match.group(1).split()

    def test_nwl_is_not_a_declared_pin(self) -> None:
        self.assertNotIn("nwl", self.declared_pins)

    def test_declared_pins_match_extractable_set(self) -> None:
        # Verified against a real `klt extract` run of the committed GDS
        # (20260804-151012-fefb292.lvs-netgen.json): counts.pins is
        # layout=4 reference=4 matched=4 once nwl is dropped.
        self.assertEqual(sorted(self.declared_pins), ["vdd", "vref", "vss", "vsubs"])

    def test_meta_pins_agree_with_subckt_header(self) -> None:
        self.assertEqual(self.meta["pins"], self.declared_pins)


class MimCapPlateNetTests(unittest.TestCase):
    """The compensation MIM cap's plate nets must match `klt`'s current
    ``CapacitorDevice`` connectivity behaviour (klayout-tools#329/#364), not
    the pre-#329 "both plates floating" assumption, nor the intermediate
    (post-#329, pre-#88) "bottom real, top floating" state.

    Verified against a real ``klt extract`` run of the committed GDS
    (gf180-bandgap#88): the extracted netlist reports the bottom plate
    (``Metal4``) resolved onto the real ``vdd`` net and, since #88 redrew the
    ``fb`` up-hop ``Via4`` to land directly inside the recognised top-plate
    region (inside the ``Metal4`` bottom-plate footprint, DRM-legal per
    ``MIMTM.2``, and no longer read as a short since klayout-tools#364/PR
    #368), the top plate (``FuseTop``) now resolves onto the real ``fb`` net
    too. This test pins that both plates now resolve to their real nets, so
    a regression back to the pre-#329 (both floating) or pre-#88
    (bottom real, top floating) model cannot silently reoccur.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.reference_text, cls.meta = make_reference.build_reference(plan.DRAWN_TRIM_CODE)
        cap_line_re = re.compile(r"^C\S+\s+(\S+)\s+(\S+)\s+\S+\s+cap_mim_2f0_m4m5_noshield$", re.M)
        match = cap_line_re.search(cls.reference_text)
        if match is None:
            raise AssertionError(
                "expected exactly one cap_mim_2f0_m4m5_noshield card in the "
                "generated reference netlist"
            )
        cls.plate_bot, cls.plate_top = match.group(1), match.group(2)

    def test_bottom_plate_resolves_to_vdd(self) -> None:
        """Metal4 is one of the deck's tracked ``metals[]`` layers (#314/#329),
        and the drawn Via1..Via3 stack lands inside that box (#77), so the
        bottom plate must be the cap's real net, not a synthesized one."""
        self.assertEqual(self.plate_bot, "vdd")

    def test_top_plate_resolves_to_fb(self) -> None:
        """The fb up-hop Via4 now lands directly inside the recognised top
        plate (#88), so the deck's top-plate connectivity wiring ties it to
        the real fb net -- it must no longer stay its own floating net."""
        self.assertEqual(self.plate_top, "fb")

    def test_top_plate_is_not_a_synthesized_bot_suffix(self) -> None:
        """Regression guard for the pre-#89 code, which derived both plate
        names from the same synthesized `{cap_name}_bot`/`{cap_name}_top`
        pattern -- both plates are real net names now, so neither identifier
        may share that synthesized-pair shape."""
        self.assertNotEqual(self.plate_bot, "amp_CC_bot")
        self.assertNotEqual(self.plate_top, "amp_CC_top")

    def test_exactly_one_mim_cap_card(self) -> None:
        self.assertEqual(self.meta["counts"]["cap_mim_2f0_m4m5_noshield"], 1)

    def test_vdd_is_a_used_net(self) -> None:
        # `use()` must be told about the resolved bottom-plate net so it is
        # not accidentally dropped from the reference's pin/net accounting.
        self.assertIn("vdd", self.meta["nets"])


if __name__ == "__main__":
    unittest.main()
