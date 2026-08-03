#!/usr/bin/env python3
"""Confirm the compensation MiM cap's ``fb`` up-hop Via4 lands on the plate.

    uv run --with klayout python3 layout/netlist/verify_mim_routing.py

**Historical note (superseded by gf180-bandgap#88, kept for context).** #17's
Test Plan originally required confirming "a MIM cap with plates physically
wired to ``vdd``/``fb`` (not just recognised as a device)" by layer
inspection rather than by an LVS delta, because at the time neither
``klt extract`` nor ``klt lvs`` could confirm the top-plate connection
themselves: this layout's ``fb`` up-hop ``Via4`` landed on a ``FuseTop``
routing tab held *outside* ``CAP_MK``/``MIM_L_MK`` (a workaround for
klayout-tools#364, which read a DRM-legal on-plate via as a ``vdd``/``fb``
short), so the deck's own connectivity graph never saw that via touch the
*recognised* top plate. Check A below merged the ``FuseTop`` shapes and
asserted that the recognised-plate region and the tab the ``Via4`` actually
landed on were one polygon -- i.e. that the one link no tool modelled was
real; Check B re-extracted a scratch copy of the GDS with ``CAP_MK``/
``MIM_L_MK`` widened to cover the tab, so the deck's plate-to-metal join
would apply, and confirmed the resulting top-plate net matched ``fb`` via
``klt lvs``.

**Current state.** klayout-tools#364/PR #368 fixed the underlying tool
limitation, and gf180-bandgap#88 redrew the contact: the ``fb`` up-hop
``Via4`` now lands directly inside the recognised top-plate region (see
``layout/bandgap_top/generate.py``'s ``_mim_cap`` docstring), so `klt
extract`/`klt lvs` confirm this connection themselves, with no marker
widening and no layer-inspection workaround --
``layout/lvs/make_reference.py`` step 9 models the top plate as `fb`
directly, and the committed ``klt lvs`` report is `status: match`. Check A
below is kept as a cheap regression guard (it now takes its ``NOTE A``
branch and passes trivially); Check B's widened-marker re-extraction is
retired, since it now proves nothing an ordinary ``klt extract``/``klt lvs``
run of the committed GDS does not already prove more directly.

Exit status is 0 if Check A passes (either the historical link-is-real proof,
or -- the expected case now -- its ``NOTE A`` "already on-plate" branch).
"""

from __future__ import annotations

import sys
from pathlib import Path

import klayout.db as kdb

REPO_ROOT = Path(__file__).resolve().parents[2]
GDS = REPO_ROOT / "layout" / "bandgap_top" / "bandgap_top.gds"

FUSETOP = (75, 0)
CAP_MK = (117, 5)
MIM_L_MK = (117, 10)
METAL4 = (46, 0)
VIA4 = (41, 0)


def _region(layout: kdb.Layout, cell: kdb.Cell, spec: tuple[int, int]) -> kdb.Region:
    index = layout.find_layer(*spec)
    if index is None:
        return kdb.Region()
    return kdb.Region(cell.begin_shapes_rec(index))


def check_a_geometry() -> bool:
    """The recognised plate and the Via4 landing are one FuseTop polygon."""
    layout = kdb.Layout()
    layout.read(str(GDS))
    cell = layout.top_cell()

    fusetop = _region(layout, cell, FUSETOP).merged()
    cap_mk = _region(layout, cell, CAP_MK).merged()
    mim_l_mk = _region(layout, cell, MIM_L_MK).merged()
    via4 = _region(layout, cell, VIA4).merged()
    metal4 = _region(layout, cell, METAL4).merged()

    recognised = fusetop & cap_mk & mim_l_mk
    if recognised.is_empty():
        print("FAIL A: no FuseTop & CAP_MK & MIM_L_MK region -- no recognised top plate")
        return False

    # The Via4 that carries fb off the top plate: the one landing on FuseTop.
    via4_on_fusetop = via4.interacting(fusetop)
    if via4_on_fusetop.count() != 1:
        print(f"FAIL A: expected exactly 1 Via4 landing on FuseTop, got {via4_on_fusetop.count()}")
        return False

    # It must NOT be on the recognised plate -- that is the whole reason the
    # deck cannot see this connection. (If this ever stops holding, the
    # workaround has been removed and BA4 in mk_extracted_dut.py must go too.)
    if not (via4_on_fusetop & recognised).is_empty():
        print(
            "NOTE A: the fb Via4 now lands inside the recognised plate region -- "
            "the deck can see this contact itself and this check is obsolete"
        )
        return True

    # The load-bearing assertion: plate and tab are one merged FuseTop polygon,
    # so the Via4 on the tab is electrically on the plate.
    carrier = fusetop.interacting(via4_on_fusetop)
    if carrier.count() != 1:
        print(f"FAIL A: Via4 lands on {carrier.count()} FuseTop polygons, expected 1")
        return False
    if (recognised - carrier).area() != 0:
        print(
            "FAIL A: the recognised plate is NOT part of the same FuseTop polygon the "
            "fb Via4 lands on -- the top plate is genuinely floating"
        )
        return False

    dbu = layout.dbu
    print(
        f"PASS A: recognised top plate ({recognised.area() * dbu * dbu:.1f} um^2) and the "
        f"fb Via4 landing are one merged FuseTop polygon "
        f"({carrier.area() * dbu * dbu:.1f} um^2) -- physically one piece of metal"
    )

    # Bottom plate: the deck sees this one itself (its Via3 lands inside the
    # Metal4 plate box), but report the geometry so both halves are on the record.
    plate_m4 = metal4.interacting(recognised)
    print(
        f"        bottom plate: Metal4 region under the top plate is "
        f"{plate_m4.area() * dbu * dbu:.1f} um^2 (its own via stack is deck-visible)"
    )
    return True


def main() -> int:
    ok_a = check_a_geometry()
    print()
    print("MiM plate routing:", "VERIFIED" if ok_a else "NOT VERIFIED")
    return 0 if ok_a else 1


if __name__ == "__main__":
    sys.exit(main())
