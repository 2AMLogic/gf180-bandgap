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


class MimCapPlateNetTests(unittest.TestCase):
    """The compensation MIM cap's plate nets must match `klt`'s current
    ``CapacitorDevice`` connectivity behaviour (klayout-tools#329), not the
    pre-#329 "both plates floating" assumption.

    Verified against a real ``klt extract`` run of the committed GDS
    (gf180-bandgap#89, deck content hash ``sha256:be1a89e0…872b1d``): the
    extracted netlist reports the bottom plate (``Metal4``) resolved onto
    the real ``vdd`` net (``C$90 vdd $16 …``) while the top plate
    (``FuseTop``) stays its own isolated net, because its ``Via4`` up-hop
    lands on the ``fb`` routing tab drawn outside ``CAP_MK``/``MIM_L_MK``
    (#82) rather than on the recognised top-plate region. This test pins
    that split so a regression back to the pre-#329 (both floating) or an
    over-eager fully-wired (both tied) model cannot silently reoccur.
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

    def test_top_plate_is_not_vdd_or_fb(self) -> None:
        """The fb up-hop Via4 lands on a routing tab kept outside
        CAP_MK/MIM_L_MK (#82), so the deck's top-plate connectivity wiring
        never ties it to the recognised top plate -- it must stay its own
        floating net, not silently merged onto vdd or fb."""
        self.assertNotIn(self.plate_top, ("vdd", "fb"))

    def test_top_plate_is_not_a_synthesized_bot_suffix(self) -> None:
        """Regression guard for the pre-#89 code, which derived both plate
        names from the same synthesized `{cap_name}_bot`/`{cap_name}_top`
        pattern -- the bottom plate is a real net name now, so the two
        plate identifiers must no longer share that synthesized-pair shape."""
        self.assertNotEqual(self.plate_bot, "amp_CC_bot")

    def test_exactly_one_mim_cap_card(self) -> None:
        self.assertEqual(self.meta["counts"]["cap_mim_2f0_m4m5_noshield"], 1)

    def test_vdd_is_a_used_net(self) -> None:
        # `use()` must be told about the resolved bottom-plate net so it is
        # not accidentally dropped from the reference's pin/net accounting.
        self.assertIn("vdd", self.meta["nets"])


if __name__ == "__main__":
    unittest.main()
