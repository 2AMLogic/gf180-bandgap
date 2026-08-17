#!/usr/bin/env python3
"""Generate ``bandgap_top.gds`` — the physical layout of the bandgap block.

Built directly with the ``klayout.db`` (``pya``-compatible) Python API, the
same construction pattern ``layout/drc/fixtures/trivial_poly_res/generate.py``
uses for the DRC bring-up fixture (``klt`` has no layout-*write* verb; ``klt
gen`` runs named PCell generators, not an arbitrary block builder).

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_top/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled), so
re-running leaves ``git diff`` empty — the same reproducibility contract
``layout/README.md`` documents for the DRC fixture.

Routing style, and why it looks like this
-----------------------------------------

``klt``'s gf180mcu **extraction** deck used to model exactly **one** metal
level (``Metal1``, 34/0) — no ``Metal2``..``Metal5``, so a block routed
above Metal1 would have extracted as a pile of disconnected nets. That used
to be why this layout was routed entirely on ``Metal1`` plus ``Poly2``: a
dedicated per-net ``Poly2`` corridor down the left edge of the block, one
``Metal1`` rail per net stacked above each row, and a ``Poly2`` stub off
every device terminal to reach its rail. The extraction deck has since
gained the full Metal1–Metal5 stack with vias (klayout-tools#220), and
gf180-bandgap#160/#166 replaced that scheme with the multi-level-metal
routing described below.

The separate **DRC** deck was never Metal1-only, and is even less so today:
since klayout-tools#188 it also carries ``metal2``/``metal3``/``metal5``
width|space, ``metaltop``.* and ``mim.space.1``/``mim.enclosing.fusetop.1``
rules (see ``layout/README.md`` § "The gf180mcu DRC deck: coverage" for the
full, current list). The **via** layers (``Via1``..``Via4``,
35/0/38/0/40/0/41/0) carry ``via1.width.1``..``via4.width.1`` (#159) and
``metalN.enclosing.viaN.1`` rules — everything drawn above Metal1, including
``Metal4``/``FuseTop`` and the vias themselves, is checked.

**Metal2 vertical spines, Metal3 over-the-cell row rails** (study §3,
gf180-bandgap#160/#166) — no reserved corridor:

* ``Poly2`` (30/0) is device-local again: gate poly and resistor bodies
  only, no routing. Every device terminal — MOS source/drain/gate,
  resistor/PNP/tap free ends — ends on a small local ``Contact`` +
  ``Metal1`` pad (:func:`draw_mos` widens the poly gate stub the same way
  :func:`draw_res` already widened a resistor's free end, so a gate can be
  reached by a contact like every other terminal).
* ``Metal2`` (36/0) carries one vertical **spine** per routed net, chosen by
  :func:`assign_spine_x` to sit *over* the device field — not beside it in a
  dedicated corridor, which is what actually recovers the corridor's width
  (study §5). A spine only needs to avoid **other nets'** Metal2 (other
  spines, other terminals' risers, below) at the deck's `metal2.space.1`;
  it costs nothing else, because Metal2 does not interact with the
  ``COMP``/``Poly2``/``Metal1`` geometry it runs above (proven against a
  real DRC/extraction run by the ``m2m3_stack_probe`` fixture, study §8).
* ``Metal3`` (42/0) carries one horizontal **row rail** per net used in that
  row, positioned *inside* the row's own device-content height (not stacked
  above it) — :func:`route_rows` asserts this fits before drawing, the same
  invariant ``routing_budget.py``'s ``track_fit`` check verifies against the
  netlist. A rail spans from its net's spine x out to that row's own
  terminals; where it crosses the spine, one ``Via2`` ties the two together.
* Each terminal's own **Metal1 → Via1 → Metal2 → Via2 → Metal3** hop (drawn
  by :func:`_riser`) is a short Metal2 "riser" climbing from the terminal's
  local pad up (or down) to its net's row-rail height, landing directly on
  the rail. It is the multi-metal counterpart of the old scheme's ``Poly2``
  stub — Metal2 is immune to shorting a *different* net's Metal1 straps the
  same way Poly2 was, so it can climb past them freely.
* ``Metal4``/``Metal5`` stay MIM-cap-only (study §4: the deck has no
  ``metal4.width``/``metal4.space`` rule at all, so routing on Metal4 would
  put geometry outside DRC coverage).

**Why two passes.** :func:`assign_spine_x` needs every terminal's position
before it can legalize spine x's against them, but terminal positions come
from actually drawing each row's items. ``build()`` therefore runs
:func:`place_rows` twice: once against a :class:`NullBuilder` (all drawing
calls are no-ops) purely to discover terminal positions, then for real once
spines are assigned. Item placement never depends on the routing scheme, so
both passes place every item identically.

**How much this recovers, and how the estimate compares with what's
actually drawn**, is written up in
``layout/routing/multi-metal-routing-study.md`` (gf180-bandgap#160) and
``layout/bandgap_top/AREA.md``.

**One more consumer of the stack**: the compensation MIM capacitor's
``Metal4``/``FuseTop`` plates (drawn by ``_mim_cap``) are wired to the
``vdd``/``fb`` row rails above through a ``Via1``..``Via4`` stack (#77) —
now landing directly on the AMPPCASC row's own Metal3 rails (a shorter
stack than before Metal1 rails moved to Metal3). See ``_mim_cap``'s own
docstring for why that via stack has to be shaped the way it is.

Matching plan, device folding and the netlist reduction the extraction deck
implies all live in the two modules this one builds on:
:mod:`netlist_model` and :mod:`plan`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))

import klayout.db as kdb  # noqa: E402

from klayout_builder import BuilderBase  # noqa: E402
import plan as plan_mod  # noqa: E402
from plan import (  # noqa: E402
    MimCapItem,
    MosItem,
    PnpItem,
    ResItem,
    TapItem,
    TrimLadderItem,
    pnp_size,
    res_geometry,
    trim_geometry,
)

# Geometry shared with layout/lvs/make_reference.py, which has to predict the
# drawn resistor/bipolar/MIM-cap geometry to emit matching reference device
# parameters -- so it lives in plan.py (the module both readers share) and is
# re-exported here. Each value's deck-minimum justification stays in the
# constants table below.
from plan import (  # noqa: E402
    CT,
    ENC_CT,
    IMPLANT_ENC,
    MIM_PLATE_INSET,
    PNP_COL_GAP,
    PNP_GAP,
    PNP_NW_ENC,
    PNP_RING,
    POLY_SP,
    RES_PAD,
    TRIM_PAD,
)

TOP_CELL = "bandgap_top"

# --------------------------------------------------------------------------- #
# Layers (gf180mcu GDS numbering, from the PDK's own
# libs.tech/klayout/tech/gf180mcu.lyp / .map)
# --------------------------------------------------------------------------- #
L_NWELL = (21, 0)
L_COMP = (22, 0)
L_POLY2 = (30, 0)
L_PPLUS = (31, 0)
L_NPLUS = (32, 0)
L_CONTACT = (33, 0)
L_METAL1 = (34, 0)
L_METAL1_LBL = (34, 10)
L_VIA1 = (35, 0)
L_METAL2 = (36, 0)
L_VIA2 = (38, 0)
L_METAL3 = (42, 0)
L_VIA3 = (40, 0)
L_METAL4 = (46, 0)
L_VIA4 = (41, 0)
L_FUSETOP = (75, 0)
L_METAL5 = (81, 0)
L_SAB = (49, 0)
L_RESISTOR_MK = (62, 0)
L_RES_MK = (110, 5)
L_CAP_MK = (117, 5)
L_MIM_MK = (117, 10)
L_DRC_BJT = (127, 5)

LAYER_NAMES = {
    L_NWELL: "Nwell",
    L_COMP: "COMP",
    L_POLY2: "Poly2",
    L_PPLUS: "Pplus",
    L_NPLUS: "Nplus",
    L_CONTACT: "Contact",
    L_METAL1: "Metal1",
    L_METAL1_LBL: "Metal1_Label",
    L_VIA1: "Via1",
    L_METAL2: "Metal2",
    L_VIA2: "Via2",
    L_METAL3: "Metal3",
    L_VIA3: "Via3",
    L_METAL4: "Metal4",
    L_VIA4: "Via4",
    L_FUSETOP: "FuseTop",
    L_METAL5: "Metal5",
    L_SAB: "SAB",
    L_RESISTOR_MK: "Resistor",
    L_RES_MK: "RES_MK",
    L_CAP_MK: "CAP_MK",
    L_MIM_MK: "MIM_L_MK",
    L_DRC_BJT: "DRC_BJT",
}

# --------------------------------------------------------------------------- #
# Geometry constants, in nanometres (layout dbu = 0.001 um).
#
# Every value is at or above the gf180mcu deck minimum it serves; the deck
# minimum is quoted alongside so the margin is auditable.
#
# The ones the LVS reference writer also needs (CT, ENC_CT, IMPLANT_ENC,
# POLY_SP, RES_PAD, TRIM_PAD, PNP_*, MIM_PLATE_INSET) are defined in plan.py
# and imported above; their justifications are quoted there.
# --------------------------------------------------------------------------- #
CT_PITCH = 500  # contact.space.1 min 250 -> 260 space here
SD_COL = 900  # source/drain column width
POLY_EXT = 400  # gate poly2 extension past COMP
STUB_W = 380  # poly2 stub width (>= CT + 2*70), used for every device's local
# contact-widening pad (MOS gate, resistor/PNP/trim free ends)
BAR_W = 400  # Metal1 bar/rail width, metal1.width.1 min 230
BAR_TOP = 300  # Metal1 terminal-pad top, above the item's own edge -- just
# enough for a Via1 landing (VIA1_LAND inset, below) with margin. Sized
# small deliberately (study §3): the old single-metal scheme needed this
# much larger (700nm) to leave room for a further Poly2 climb toward a
# corridor rail; the Metal2/Metal3 scheme's riser (_riser) does that climbing
# instead, so the local Metal1 pad no longer has to reach far -- reaching
# less also keeps every terminal's local pad clear of the next row's own
# terminals across ROW_GAP (gf180-bandgap#166).
ISLAND_GAP = 500  # COMP-to-COMP between islands, comp.space.1 min 280
ROW_GAP = 1100
NWELL_ENC = 600  # Nwell overlap of PMOS COMP, nwell.enclosing.comp.1 min 120
NWELL_CLEAR = 2000  # Nwell edge -> unrelated COMP
GUARD_W = 1600  # guard-ring COMP width
GUARD_CLEAR = 1600  # block content -> guard ring inner edge

# --------------------------------------------------------------------------- #
# Compensation-cap via stack (#77) and the Metal2/Metal3 row-routing stack
# (gf180-bandgap#160/#166) share the same via layers/sizes -- everywhere in
# this block routes on Metal1..Metal3/Poly2 except the compensation cap's own
# Metal4/Metal5 plates (see the module docstring's "Routing style"). Sizes
# mirror CT/ENC_CT's proportions (a square via with a symmetric metal
# enclosure). The gf180mcu **DRC** deck does carry metal2/metal3/metal5.
# width|space and mim.space.1/mim.enclosing.fusetop.1 rules (klayout-tools#188;
# see layout/README.md). The via layers themselves (35/0, 38/0, 40/0, 41/0)
# were rule-free when the cap's stack was first drawn, but klt has since
# gained ``via1.width.1``..``via4.width.1`` (DRM ``Vn.1``: each via is a
# fixed 0.26 x 0.26um square) -- #159 found the drift once klt started
# enforcing it. ``VIA_W`` below is now the exact DRM value (not a
# self-chosen conservative margin) so it matches both halves of ``Vn.1``
# even though ``width_check`` only enforces the min half.
# --------------------------------------------------------------------------- #
VIA_W = 260  # via1..via4 width -- DRM Vn.1 fixed size, 0.26um
VIA_ENC = 100  # metal enclosure of a via, matches ENC_CT (used by _mim_cap's
# own Metal4/Metal5 pads, which have room to spare beyond the row-routing
# stack's tighter ROUTE_VIA_ENC below)
VIA_PAD = VIA_W + 2 * VIA_ENC  # 460 nm square landing pad
FB_M5_WIRE_W = 700  # fb top-plate route: Metal5 wire width (>> VIA_W, margin)
# MIMTM.2 ("min. MiM bottom-plate overlap of Via4", 0.4um) is not transcribed
# into the gf180mcu DRC deck (see layout/README.md's "The gf180mcu DRC deck:
# coverage"), but the fb up-hop Via4 below is still placed to honour it by a
# wide margin -- see the asserts in `_mim_cap`.
MIM_VIA_OVERLAP_MIN = 400  # MIMTM.2 minimum, nm
FB_DOWNHOP_CLEAR = 3000  # fb down-hop x, clear of the bottom plate (mim.space.1: 1.2um min Metal4-Metal4 spacing)

# --------------------------------------------------------------------------- #
# Metal2/Metal3 row routing (gf180-bandgap#160/#166, study §3/§4). Sizing
# read out of the *installed* deck (klayout_tools/decks/gf180mcu.py, klt
# 0.2.0): metal2.width.1/metal3.width.1 min 280nm, metal2.space.1/
# metal3.space.1 min 280nm, metal2.enclosing.via1.1/metal3.enclosing.via2.1
# min 10nm. Replaces the old Poly2-corridor-and-Metal1-rail scheme the
# module docstring's "Routing style" used to describe.
# --------------------------------------------------------------------------- #
TRACK_W = 400  # metal2.width.1 / metal3.width.1 min 280 (1.43x margin)
TRACK_SP = 320  # metal2.space.1 / metal3.space.1 min 280 (1.14x margin)
TRACK_PITCH = TRACK_W + TRACK_SP  # 720nm net-to-net pitch (Metal2 spines and
# Metal3 row rails alike)
ROUTE_VIA_ENC = 70  # metal2.enclosing.via1.1 / metal3.enclosing.via2.1 min 10
ROUTE_VIA_PAD = VIA_W + 2 * ROUTE_VIA_ENC  # 400nm -- equals TRACK_W, so a via
# landing on a routing track needs no extra widening beyond the track itself
assert ROUTE_VIA_PAD == TRACK_W
VIA1_LAND = 200  # inset from a terminal's own Metal1 pad edge where Via1
# lands, so the via sits comfortably inside the pad rather than at its edge
GUARD_TIE_LAND = 300  # how far below y=0 (row 0's own bottom edge) the guard
# ring's vss tie strap reaches -- entirely inside the guard-clearance band,
# never crossing a device row (see the module docstring's "Routing style")


@dataclass
class Terminal:
    net: str
    stub_x: int
    #: Y of the terminal's own already-drawn local Metal1 pad, where
    #: :func:`_riser` lands its Via1 -- *not* a routing-layer position (the
    #: old scheme's ``stub_y0`` was the bottom of a Poly2 stub that itself
    #: still had to reach the rail; this terminal's Metal1 geometry is
    #: already device-local and complete, see the module docstring's
    #: "Routing style").
    anchor_y: int


class Builder(BuilderBase):
    def __init__(self) -> None:
        super().__init__(TOP_CELL, LAYER_NAMES)

    def label(self, x: int, y: int, text: str) -> None:
        self.cell.shapes(self._layers[L_METAL1_LBL]).insert(
            kdb.Text(text, kdb.Trans(kdb.Vector(x, y)))
        )

    def contact(self, cx: int, cy: int) -> None:
        self.box(L_CONTACT, cx - CT // 2, cy - CT // 2, cx + CT // 2, cy + CT // 2)

    def contact_column(self, cx: int, y0: int, y1: int) -> None:
        """Fill ``[y0, y1]`` with a contact array on ``CT_PITCH``, centred."""
        span = y1 - y0
        count = max(1, (span + CT_PITCH - CT) // CT_PITCH)
        used = count * CT + (count - 1) * (CT_PITCH - CT)
        start = y0 + (span - used) // 2
        for i in range(count):
            cy = start + i * CT_PITCH + CT // 2
            self.contact(cx, cy)


class NullBuilder(Builder):
    """A :class:`Builder` whose drawing calls are all no-ops.

    ``build()`` runs the row-placement pass once against this class purely
    to discover terminal positions (:func:`assign_spine_x` needs them before
    it can legalize spine x's), then again for real against a genuine
    :class:`Builder` once spines are known -- see the module docstring's
    "Why two passes". Deliberately skips ``BuilderBase.__init__`` (no real
    ``klayout.db`` layout is needed for a dry run).
    """

    def __init__(self) -> None:  # noqa: super-init-not-called -- see docstring
        pass

    def box(self, layer: tuple[int, int], x0: int, y0: int, x1: int, y1: int) -> None:
        pass

    def label(self, x: int, y: int, text: str) -> None:
        pass


# --------------------------------------------------------------------------- #
# Item drawing
# --------------------------------------------------------------------------- #


def mos_size(item: MosItem) -> tuple[int, int]:
    return 2 * SD_COL + item.l_nm, item.w_nm


def draw_mos(b: Builder, item: MosItem, x0: int, y0: int) -> list[Terminal]:
    w, l = item.w_nm, item.l_nm
    x1 = x0 + 2 * SD_COL + l
    y1 = y0 + w

    b.box(L_COMP, x0, y0, x1, y1)
    implant = L_PPLUS if item.kind == "pfet" else L_NPLUS
    b.box(implant, x0 - IMPLANT_ENC, y0 - IMPLANT_ENC, x1 + IMPLANT_ENC, y1 + IMPLANT_ENC)

    gate_x0 = x0 + SD_COL
    gate_x1 = gate_x0 + l
    b.box(L_POLY2, gate_x0, y0 - POLY_EXT, gate_x1, y1 + POLY_EXT)

    terminals: list[Terminal] = []

    # Gate: a local Contact + Metal1 pad, same as every other terminal (study
    # §3) -- the channel-length-wide gate poly is widened to STUB_W here so
    # the contact has room (mirrors draw_res's free-end pad, below). The
    # widened box's own top edge stays *at* the gate poly's natural tip
    # (``gate_top``) rather than growing past it: a row's tallest item's
    # gate poly already reaches to within ``ROW_GAP`` of the next row's own
    # poly, so any extra height here risks poly2.space.1 against it.
    gcx = (gate_x0 + gate_x1) // 2
    gate_top = y1 + POLY_EXT
    gcy = gate_top - 200
    b.box(L_POLY2, gcx - STUB_W // 2, gcy - 200, gcx + STUB_W // 2, gate_top)
    b.contact(gcx, gcy)
    b.box(L_METAL1, gcx - BAR_W // 2, gcy - BAR_W // 2, gcx + BAR_W // 2, gcy + BAR_W // 2)
    terminals.append(Terminal(item.nets["g"], gcx, gcy))

    for term, cx in (("s", x0 + SD_COL // 2), ("d", x1 - SD_COL // 2)):
        b.contact_column(cx, y0 + ENC_CT, y1 - ENC_CT)
        top = y1 + BAR_TOP
        b.box(L_METAL1, cx - BAR_W // 2, y0 - 80, cx + BAR_W // 2, top)
        terminals.append(Terminal(item.nets[term], cx, top - VIA1_LAND))

    return terminals


def draw_res(b: Builder, item: ResItem, x0: int, y0: int) -> list[Terminal]:
    pitch = item.width_nm + POLY_SP
    n = item.segments
    _, leg, _ = res_geometry(item)

    for i in range(n):
        lx = x0 + i * pitch
        b.box(L_POLY2, lx, y0, lx + item.width_nm, y0 + leg)
    for i in range(n - 1):
        lx = x0 + i * pitch
        rx = x0 + (i + 1) * pitch + item.width_nm
        if i % 2 == 0:  # link at the top
            b.box(L_POLY2, lx, y0 + leg - item.width_nm, rx, y0 + leg)
        else:  # link at the bottom
            b.box(L_POLY2, lx, y0, rx, y0 + item.width_nm)

    # A ppolyf_u body is p+ implanted, unsalicided poly (no COMP under it).
    # RES_MK + SAB mark the same footprint as Pplus: the deck's ppolyf_u
    # recogniser is `pplus.and(poly2).and(sab).and(res_mk)`, so all three
    # markers need to cover the resistor body for `klt extract` to see it
    # as a device rather than plain interconnect (#73). A high-sheet-rho
    # (`ppolyf_u_1k`) body used to omit RES_MK: when this was originally
    # drawn the deck had no device entry for that flavour
    # (klayout-tools#299), and RES_MK's 350 ohm/sq would have been silently
    # wrong for it, so `Resistor` (62/0) alone was drawn instead -- one of
    # `ResistorDevice.excludes` for the base flavour -- keeping it a short
    # rather than a wrong value. klayout-tools#299 is now resolved: the deck
    # carries a `ppolyf_u_1k` entry recognised by SAB + Resistor + RES_MK
    # (deliberately *not* Pplus), so both flavours now draw RES_MK; the
    # high-rho body also keeps its Resistor (62/0) marker (drawn below),
    # while the base flavour keeps Pplus -- that's the only remaining
    # difference between the two recognisers (gf180-bandgap#78).
    body_layers = (L_SAB, L_RES_MK) if item.high_rho else (L_PPLUS, L_RES_MK, L_SAB)
    for layer in body_layers:
        b.box(
            layer,
            x0 - IMPLANT_ENC,
            y0 - IMPLANT_ENC,
            x0 + (n - 1) * pitch + item.width_nm + IMPLANT_ENC,
            y0 + leg + IMPLANT_ENC,
        )
    if item.high_rho:
        b.box(
            L_RESISTOR_MK,
            x0 - IMPLANT_ENC,
            y0 - IMPLANT_ENC,
            x0 + (n - 1) * pitch + item.width_nm + IMPLANT_ENC,
            y0 + leg + IMPLANT_ENC,
        )

    # Free ends: leg 0's is at the bottom; leg n-1's is at the top for odd n,
    # at the bottom for even n (links alternate top/bottom).
    free_ends = [(0, "bottom"), (n - 1, "top" if n % 2 == 1 else "bottom")]
    terminals: list[Terminal] = []
    for (index, side), net in zip(free_ends, item.nets):
        cx = x0 + index * pitch + item.width_nm // 2
        # A dedicated, unmarked poly pad just past the resistor's true free
        # edge -- outside the RES_MK/Pplus/SAB box above (RES_PAD > the
        # marker's IMPLANT_ENC overhang), so it stays part of the
        # recognised body's "C" (terminal) region and directly abuts the
        # marked body. KLayout's DeviceExtractorResistor requires the
        # terminal region to touch the body at each of the resistor's two
        # ends; a contact landing *inside* the marked body -- as this used
        # to do, bridged out to the row rail only via Metal1 -- does not
        # satisfy that (logged as "Expected two polygons on contacts
        # interacting with one resistor shape (found 0)"), so the leg's own
        # body/head must be genuinely two-piece poly, not one uniformly
        # marked run (#73).
        if side == "bottom":
            pad_y0, pad_y1 = y0 - RES_PAD, y0
        else:
            pad_y0, pad_y1 = y0 + leg, y0 + leg + RES_PAD
        b.box(L_POLY2, cx - item.width_nm // 2, pad_y0, cx + item.width_nm // 2, pad_y1)
        cy = (pad_y0 + pad_y1) // 2
        b.contact(cx, cy)
        b.box(L_METAL1, cx - BAR_W // 2, cy - BAR_W // 2, cx + BAR_W // 2, cy + BAR_W // 2)
        terminals.append(Terminal(net, cx, cy))
    return terminals


def draw_trim(b: Builder, item: TrimLadderItem, x0: int, y0: int) -> list[Terminal]:
    unit_x = item.unit_length_nm + 2 * TRIM_PAD
    pitch = unit_x + POLY_SP
    uw = item.unit_width_nm
    lower_n = item.split_after_unit
    upper_n = item.units - lower_n

    row0_y = y0
    row1_y = y0 + uw + 3600
    row1_x0 = x0 + 2000

    def draw_unit(ux: int, uy: int) -> tuple[int, int]:
        """Draw one unit segment; return its two pad-contact x positions."""
        b.box(L_POLY2, ux, uy, ux + unit_x, uy + uw)
        # Pplus/SAB mark the unit's full footprint (matching the original
        # Pplus box), but RES_MK is pulled in to the unit_length_nm centre,
        # excluding the TRIM_PAD contact-pad zone at each end. The deck's
        # ppolyf_u body is `poly2 & res_mk & pplus & sab`, so RES_MK alone
        # sets the recognised extent (Pplus/SAB being wider doesn't widen
        # it); keeping RES_MK narrower than the TRIM_PAD pads leaves each
        # pad's own poly as unmarked "terminal" region directly abutting
        # the recognised body -- required by KLayout's DeviceExtractorResistor,
        # which needs the terminal region to touch the body at each end, not
        # just land inside it under a contact (#73).
        b.box(L_PPLUS, ux - IMPLANT_ENC, uy - IMPLANT_ENC, ux + unit_x + IMPLANT_ENC, uy + uw + IMPLANT_ENC)
        b.box(L_SAB, ux - IMPLANT_ENC, uy - IMPLANT_ENC, ux + unit_x + IMPLANT_ENC, uy + uw + IMPLANT_ENC)
        b.box(L_RES_MK, ux + TRIM_PAD, uy - IMPLANT_ENC, ux + unit_x - TRIM_PAD, uy + uw + IMPLANT_ENC)
        left_cx = ux + TRIM_PAD // 2
        right_cx = ux + unit_x - TRIM_PAD // 2
        for cx in (left_cx, right_cx):
            b.contact(cx, uy + uw // 2)
        return left_cx, right_cx

    # Lower sub-row: units 1..lower_n, left to right.
    lower_pads = [draw_unit(x0 + i * pitch, row0_y) for i in range(lower_n)]
    # Upper sub-row: units lower_n+1..N, drawn right to left so the inter-row
    # link is a short vertical at the right edge rather than a full traverse.
    upper_pads = [
        draw_unit(row1_x0 + (upper_n - 1 - i) * pitch, row1_y) for i in range(upper_n)
    ]

    def bridge(x_left: int, x_right: int, cy: int) -> None:
        b.box(L_METAL1, x_left - BAR_W // 2, cy - BAR_W // 2, x_right + BAR_W // 2, cy + BAR_W // 2)

    for i in range(lower_n - 1):
        bridge(lower_pads[i][1], lower_pads[i + 1][0], row0_y + uw // 2)
    for i in range(upper_n - 1):
        bridge(upper_pads[i + 1][1], upper_pads[i][0], row1_y + uw // 2)

    # Inter-sub-row link (node after unit `lower_n`), at the right edge.
    link_x = max(lower_pads[-1][1], upper_pads[0][1])
    b.box(L_METAL1, link_x - BAR_W // 2, row0_y + uw // 2 - BAR_W // 2, link_x + BAR_W // 2, row1_y + uw // 2 + BAR_W // 2)
    bridge(lower_pads[-1][1], link_x, row0_y + uw // 2)
    bridge(upper_pads[0][1], link_x, row1_y + uw // 2)

    # Metal-option trim straps for DRAWN_TRIM_CODE. `item.strap_spans` is
    # derived in plan.py from the schematic's own ideal RS* strap expressions
    # (`plan.trim_strap_spans`), so the drawn Metal1 shorts exactly the chain
    # nodes the schematic shorts -- one strap per *closed code bit*, not one
    # span across the whole strapped group. The single-span form this used to
    # draw is electrically identical but a different network (see
    # `trim_strap_spans`' docstring), which `layout/lvs` compares (#75).
    strap_y = y0 + uw + 1800
    tn0_x = lower_pads[0][0]

    def node_x(index: int) -> int:
        """Metal1 x position of trim-chain node ``index`` in the lower sub-row."""
        if index == 0:
            return tn0_x
        if index < lower_n:
            return lower_pads[index - 1][1]
        if index == lower_n:
            return link_x
        raise ValueError(
            f"{item.key}: strap node {index} sits in the upper sub-row; only "
            f"nodes 0..{lower_n} have a drawn strap track"
        )

    for index in sorted({n for span in item.strap_spans for n in span}):
        cx = node_x(index)
        b.box(L_METAL1, cx - BAR_W // 2, row0_y + uw // 2, cx + BAR_W // 2, strap_y + BAR_W // 2)
    for lo_node, hi_node in item.strap_spans:
        xs = sorted((node_x(lo_node), node_x(hi_node)))
        b.box(L_METAL1, xs[0] - BAR_W // 2, strap_y - BAR_W // 2, xs[1] + BAR_W // 2, strap_y + BAR_W // 2)

    top = row1_y + uw
    terminals: list[Terminal] = []
    for cx, net in ((tn0_x, item.nets[0]), (upper_pads[-1][0], item.nets[1])):
        # The bottom of this box must enclose the pad's own base contact
        # (drawn by `draw_unit` at the same `cx`, centred on this same row's
        # `cy`) the same way `bridge()` does elsewhere in this function --
        # starting exactly at `cy` instead of `cy - BAR_W // 2` left that
        # contact's bottom half uncovered (metal1.enclosing.contact.1, #159).
        row_cy = (row0_y if cx == tn0_x else row1_y) + uw // 2
        bar_top = top + BAR_TOP
        b.box(L_METAL1, cx - BAR_W // 2, row_cy - BAR_W // 2, cx + BAR_W // 2, bar_top)
        terminals.append(Terminal(net, cx, bar_top - VIA1_LAND))
    return terminals


def draw_pnp(b: Builder, item: PnpItem, x0: int, y0: int) -> list[Terminal]:
    emitter = int(item.emitter_um * 1000)
    size, _ = pnp_size(item)
    cx = x0 + size // 2
    cy = y0 + size // 2

    def ring(layer: tuple[int, int], outer: int, width: int) -> None:
        o = outer // 2
        i = o - width
        b.box(layer, cx - o, cy - o, cx + o, cy - i)
        b.box(layer, cx - o, cy + i, cx + o, cy + o)
        b.box(layer, cx - o, cy - i, cx - i, cy + i)
        b.box(layer, cx + i, cy - i, cx + o, cy + i)

    base_outer = emitter + 2 * (PNP_GAP + PNP_RING)
    nwell = base_outer + 2 * PNP_NW_ENC
    coll_inner = nwell + 2 * PNP_COL_GAP
    coll_outer = coll_inner + 2 * PNP_RING

    b.box(L_NWELL, cx - nwell // 2, cy - nwell // 2, cx + nwell // 2, cy + nwell // 2)
    b.box(L_DRC_BJT, x0, y0, x0 + size, y0 + size)

    # Emitter: p+ COMP inside the Nwell.
    b.box(L_COMP, cx - emitter // 2, cy - emitter // 2, cx + emitter // 2, cy + emitter // 2)
    b.box(
        L_PPLUS,
        cx - emitter // 2 - IMPLANT_ENC,
        cy - emitter // 2 - IMPLANT_ENC,
        cx + emitter // 2 + IMPLANT_ENC,
        cy + emitter // 2 + IMPLANT_ENC,
    )
    b.contact_column(cx, cy - emitter // 2 + ENC_CT, cy + emitter // 2 - ENC_CT)
    b.box(L_METAL1, cx - BAR_W // 2, cy - emitter // 2, cx + BAR_W // 2, y0 + size + BAR_TOP)

    # Base: n+ COMP ring inside the Nwell.
    ring(L_COMP, base_outer, PNP_RING)
    ring(L_NPLUS, base_outer + 2 * IMPLANT_ENC, PNP_RING + 2 * IMPLANT_ENC)
    # Collector: p+ COMP ring in the substrate, outside the Nwell.
    ring(L_COMP, coll_outer, PNP_RING)
    ring(L_PPLUS, coll_outer + 2 * IMPLANT_ENC, PNP_RING + 2 * IMPLANT_ENC)

    # Base and collector are both tied to vss (every PNP here is
    # diode-connected, base = collector = substrate; floorplan §4.2), so one
    # Metal1 strap on the left flank contacts both rings.
    strap_x = cx - coll_outer // 2 + PNP_RING // 2
    b.contact_column(strap_x, cy - PNP_RING // 2, cy + PNP_RING // 2)
    base_strap_x = cx - base_outer // 2 + PNP_RING // 2
    b.contact_column(base_strap_x, cy - PNP_RING // 2, cy + PNP_RING // 2)
    # The horizontal strap must enclose every contact `contact_column` placed
    # above (metal1.enclosing.contact.1) -- the column spans the full ring
    # height (`cy +/- PNP_RING // 2`), not just `BAR_W`, so the strap has to
    # match that span rather than the narrower rail width used elsewhere
    # (#159: a `BAR_W`-tall strap left the column's outer contacts partially
    # uncovered once klt started checking this enclosure).
    b.box(
        L_METAL1,
        strap_x - BAR_W // 2,
        cy - PNP_RING // 2,
        base_strap_x + BAR_W // 2,
        cy + PNP_RING // 2,
    )
    b.box(L_METAL1, strap_x - BAR_W // 2, cy, strap_x + BAR_W // 2, y0 + size + BAR_TOP)

    bar_top = y0 + size + BAR_TOP
    terminals: list[Terminal] = [
        Terminal(item.emitter_net, cx, bar_top - VIA1_LAND),
        Terminal(item.base_net, strap_x, bar_top - VIA1_LAND),
    ]
    return terminals


TAP_H = 1600


def draw_tap(b: Builder, item: TapItem, x0: int, y0: int) -> list[Terminal]:
    x1 = x0 + item.length_nm
    y1 = y0 + TAP_H
    b.box(L_COMP, x0, y0, x1, y1)
    implant = L_PPLUS if item.kind == "psub" else L_NPLUS
    b.box(implant, x0 - IMPLANT_ENC, y0 - IMPLANT_ENC, x1 + IMPLANT_ENC, y1 + IMPLANT_ENC)
    cy = (y0 + y1) // 2
    x = x0 + ENC_CT + CT // 2
    while x + CT // 2 + ENC_CT <= x1:
        b.contact(x, cy)
        x += CT_PITCH
    b.box(L_METAL1, x0, cy - BAR_W // 2, x1, cy + BAR_W // 2)
    cx = x0 + BAR_W
    bar_top = y1 + BAR_TOP
    b.box(L_METAL1, cx - BAR_W // 2, cy, cx + BAR_W // 2, bar_top)
    return [Terminal(item.net, cx, bar_top - VIA1_LAND)]


def item_size(item: object) -> tuple[int, int]:
    if isinstance(item, MosItem):
        return mos_size(item)
    if isinstance(item, ResItem):
        w, h, _ = res_geometry(item)
        return w, h
    if isinstance(item, TrimLadderItem):
        w, h, _, _ = trim_geometry(item)
        return w, h
    if isinstance(item, PnpItem):
        return pnp_size(item)
    if isinstance(item, TapItem):
        return item.length_nm, TAP_H
    raise TypeError(f"unsupported item {item!r}")


def draw_item(b: Builder, item: object, x: int, y: int) -> list[Terminal]:
    if isinstance(item, MosItem):
        return draw_mos(b, item, x, y)
    if isinstance(item, ResItem):
        return draw_res(b, item, x, y)
    if isinstance(item, TrimLadderItem):
        return draw_trim(b, item, x, y)
    if isinstance(item, PnpItem):
        return draw_pnp(b, item, x, y)
    if isinstance(item, TapItem):
        return draw_tap(b, item, x, y)
    raise TypeError(f"unsupported item {item!r}")


# --------------------------------------------------------------------------- #
# Block assembly
# --------------------------------------------------------------------------- #


def place_rows(b: Builder, rows: list[plan_mod.Row]) -> list[dict]:
    """Place every row's items left to right, starting at the block's own
    left edge (``x = 0`` -- no reserved routing corridor, see the module
    docstring's "Routing style"), collecting each row's terminals and
    geometry. Item placement never depends on the routing scheme, so this
    can run once against a :class:`NullBuilder` to discover terminal
    positions before spines are assigned, then again for real -- see
    ``build()``.
    """
    row_geometry: list[dict] = []
    y = 0
    for row in rows:
        sizes = [item_size(item) for item in row.items]
        row_h = max(h for _, h in sizes)
        x = 0
        terminals: list[Terminal] = []
        placements: list[tuple[object, int, int]] = []
        for item, (w, _h) in zip(row.items, sizes):
            terminals.extend(draw_item(b, item, x, y))
            placements.append((item, x, w))
            x += w + ISLAND_GAP
        row_right = x - ISLAND_GAP
        row_geometry.append(
            {
                "row": row,
                "y0": y,
                "row_h": row_h,
                "right": row_right,
                "terminals": terminals,
                "placements": placements,
            }
        )
        y = y + row_h + ROW_GAP
    return row_geometry


def assign_spine_x(
    nets: list[str], row_geometry: list[dict]
) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """Choose each net's Metal2 spine x, positioned *over* the device field
    instead of in a dedicated corridor (study §3) -- that repositioning is
    what actually recovers the old corridor's block width (study §5), since
    Metal2 does not interact with the ``COMP``/``Poly2``/``Metal1`` geometry
    it runs above (the ``m2m3_stack_probe`` fixture proves this against a
    real DRC/extraction run, study §8).

    A greedy legalizer on the ``TRACK_PITCH`` grid: each net gets the
    smallest slot that clashes with neither an already-placed spine (over
    any row-height range the two spines' own row-usage shares) nor any
    *other* net's terminal in any row this spine's own span crosses --
    including rows the net itself does not use, since the spine still runs
    through them on its way between the rows it does. Returns
    ``(spine_x, spine_span)``; ``spine_span`` is each net's own
    ``(y_lo, y_hi)`` row-usage range, reused by ``draw_spines``.
    """
    placed: list[tuple[int, int, int]] = []
    spine_x: dict[str, int] = {}
    spine_span: dict[str, tuple[int, int]] = {}
    for net in nets:
        rows_used = [
            i for i, g in enumerate(row_geometry) if any(t.net == net for t in g["terminals"])
        ]
        assert rows_used, f"{net}: routed net with no drawn terminal"
        lo, hi = rows_used[0], rows_used[-1]
        y_lo = row_geometry[lo]["y0"]
        y_hi = row_geometry[hi]["y0"] + row_geometry[hi]["row_h"]
        k = 0
        while not _spine_slot_clear(k * TRACK_PITCH, y_lo, y_hi, net, row_geometry, lo, hi, placed):
            k += 1
        x = k * TRACK_PITCH
        spine_x[net] = x
        spine_span[net] = (y_lo, y_hi)
        placed.append((x, y_lo, y_hi))
    return spine_x, spine_span


def _spine_slot_clear(
    x: int,
    y_lo: int,
    y_hi: int,
    net: str,
    row_geometry: list[dict],
    lo: int,
    hi: int,
    placed: list[tuple[int, int, int]],
) -> bool:
    for px, py_lo, py_hi in placed:
        if y_lo <= py_hi and py_lo <= y_hi and abs(x - px) < TRACK_PITCH:
            return False
    for i in range(lo, hi + 1):
        for t in row_geometry[i]["terminals"]:
            d = abs(x - t.stub_x)
            if d == 0:
                # Exact alignment only merges safely when it is the *same*
                # net's own terminal (its riser and this spine become one
                # touching Metal2 shape); a different net sitting exactly
                # here would be a dead short.
                if t.net != net:
                    return False
                continue
            # A near-miss is unsafe regardless of net: a same-net terminal
            # that is close but *not* exactly aligned still draws a
            # disconnected riser (it reaches the spine's net only through
            # the row's own Metal3 rail, not by touching the spine
            # directly), so it needs the same TRACK_PITCH clearance a
            # different net's terminal would.
            if d < TRACK_PITCH:
                return False
    return True


def _riser(b: Builder, x: int, anchor_y: int, ty: int) -> None:
    """One terminal's Metal1(existing) -> Via1 -> Metal2 -> Via2 -> Metal3
    (rail) hop -- the multi-metal counterpart of the old scheme's Poly2
    stub (module docstring's "Routing style"). The Metal2 riser climbs from
    the terminal's own already-drawn local pad (``anchor_y``) up or down to
    its net's row-rail height (``ty``), landing directly on the rail; Metal2
    is immune to shorting a *different* net's Metal1 straps the way Poly2
    was, so it can climb past them freely.
    """
    b.box(L_VIA1, x - VIA_W // 2, anchor_y - VIA_W // 2, x + VIA_W // 2, anchor_y + VIA_W // 2)
    lo, hi = sorted((anchor_y, ty))
    # The riser body must clear both vias' own enclosure at each end, not
    # just stop exactly at their centres (metal2.enclosing.via1.1/via2.1).
    end_margin = VIA_W // 2 + ROUTE_VIA_ENC
    b.box(L_METAL2, x - ROUTE_VIA_PAD // 2, lo - end_margin, x + ROUTE_VIA_PAD // 2, hi + end_margin)
    b.box(L_VIA2, x - VIA_W // 2, ty - VIA_W // 2, x + VIA_W // 2, ty + VIA_W // 2)


def route_rows(b: Builder, row_geometry: list[dict], spine_x: dict[str, int]) -> None:
    """Draw each row's Metal3 rails (inside that row's own device-content
    height, over its own devices -- study §3) and every terminal's riser up
    to its net's rail. Fills in each row's ``"rail_geo"``/``"nets"`` entries.
    """
    for g in row_geometry:
        by_net: dict[str, list[Terminal]] = {}
        for t in g["terminals"]:
            by_net.setdefault(t.net, []).append(t)
        # Deterministic, stable net ordering -- same tie-break the old
        # per-row rail stack used (furthest-reaching net first).
        order = sorted(by_net, key=lambda n: (max(t.stub_x for t in by_net[n]), n))
        assert len(order) * TRACK_PITCH <= g["row_h"], (
            f"{g['row'].name}: {len(order)} net rails need "
            f"{len(order) * TRACK_PITCH / 1000:.2f} um at {TRACK_PITCH / 1000:.2f} um "
            f"pitch, more than the row's own {g['row_h'] / 1000:.2f} um of device "
            "content -- routing_budget.py's track_fit check should have caught this"
        )
        rail_geo: dict[str, tuple[int, int, int]] = {}
        for i, net in enumerate(order):
            sx = spine_x[net]
            xs = [t.stub_x for t in by_net[net]] + [sx]
            left, right = min(xs), max(xs)
            ty = g["y0"] + TRACK_PITCH // 2 + i * TRACK_PITCH
            b.box(L_METAL3, left - TRACK_W // 2, ty - TRACK_W // 2, right + TRACK_W // 2, ty + TRACK_W // 2)
            # Spine -> rail hop, where the spine (drawn separately by
            # draw_spines) crosses this row at its own x.
            b.box(L_VIA2, sx - VIA_W // 2, ty - VIA_W // 2, sx + VIA_W // 2, ty + VIA_W // 2)
            rail_geo[net] = (ty, left, right)
            for t in by_net[net]:
                _riser(b, t.stub_x, t.anchor_y, ty)
        g["rail_geo"] = rail_geo
        g["nets"] = order


def draw_spines(
    b: Builder,
    spine_x: dict[str, int],
    spine_span: dict[str, tuple[int, int]],
    vss_extra_lo: int | None = None,
) -> None:
    """Draw each net's Metal2 spine over its own row-usage span.
    ``vss_extra_lo``, if given, extends the ``vss`` spine's own bottom edge
    down to meet the guard ring's tie (``build()``'s "Guard ring" step).
    """
    for net, sx in spine_x.items():
        y_lo, y_hi = spine_span[net]
        if net == "vss" and vss_extra_lo is not None:
            y_lo = min(y_lo, vss_extra_lo)
        b.box(L_METAL2, sx - TRACK_W // 2, y_lo, sx + TRACK_W // 2, y_hi)


def build() -> tuple[Builder, dict]:
    flat, rows = plan_mod.load_plan()
    nets = plan_mod.routed_nets(rows)

    # Pass 1 (dry run): discover terminal positions so spines can be
    # legalized against them -- see the module docstring's "Why two passes".
    dry_row_geometry = place_rows(NullBuilder(), rows)
    spine_x, spine_span = assign_spine_x(nets, dry_row_geometry)

    # Pass 2: draw for real, now that spine x's are known.
    b = Builder()
    row_geometry = place_rows(b, rows)
    route_rows(b, row_geometry, spine_x)

    block_top = row_geometry[-1]["y0"] + row_geometry[-1]["row_h"]
    block_right = max(g["right"] for g in row_geometry)
    for net, sx in spine_x.items():
        assert sx + TRACK_W // 2 <= block_right, (
            f"{net}: spine x {sx / 1000:.2f} um falls outside the device "
            f"field ({block_right / 1000:.2f} um) -- assign_spine_x's "
            "legalizer ran out of safe slots within the field"
        )

    # One Nwell for the whole PMOS band (keeps the extracted PMOS body a
    # single net). The band is contiguous by construction -- see plan.py.
    pmos_rows = [g for g in row_geometry if g["row"].nwell]
    nwell_box = (
        -NWELL_ENC,
        min(g["y0"] for g in pmos_rows) - POLY_EXT - NWELL_ENC,
        max(g["right"] for g in pmos_rows) + NWELL_ENC,
        max(g["y0"] + g["row_h"] for g in pmos_rows) + NWELL_ENC,
    )
    b.box(L_NWELL, *nwell_box)

    # Net labels on Metal1 (34/10) -- kept on Metal1 (not the Metal2/Metal3
    # routing layers) because that is the layer `Netlist.make_top_level_pins()`
    # promotes to a pin, so the label has to sit on a terminal's own local
    # Metal1 pad (real conductor there) rather than at a rail/spine position.
    # Only the block's own pins are labelled -- labelling internal nets would
    # invent pins the schematic does not have.
    for net in ("vdd", "vss", "vref"):
        target = next(t for g in row_geometry for t in g["terminals"] if t.net == net)
        b.label(target.stub_x, target.anchor_y, net)

    # Guard ring: p+ COMP tied to vss, around the whole block (floorplan §9).
    gx0 = -GUARD_CLEAR - GUARD_W
    gy0 = -POLY_EXT - GUARD_CLEAR - GUARD_W
    gx1 = block_right + GUARD_CLEAR + GUARD_W
    gy1 = block_top + GUARD_CLEAR + GUARD_W
    _guard_ring(b, gx0, gy0, gx1, gy1)

    # Tie the guard ring to vss: a *short* Metal1 strap from the ring up to
    # just below y = 0 (row 0's own bottom edge), entirely inside the
    # guard-clearance band -- never crossing a device row, unlike the old
    # scheme's full-height strap (safe there only because the corridor it
    # ran through was itself device-free; the vss spine now runs *over* the
    # device field, so a strap sharing its x can no longer run the full
    # height without risking a different net's Metal1). Via1 + a Metal2 pad
    # there ties into the vss spine, whose own bottom edge is extended down
    # to meet it (draw_spines' `vss_extra_lo`).
    vss_sx = spine_x["vss"]
    strap_top = -POLY_EXT - GUARD_TIE_LAND
    b.box(L_METAL1, vss_sx - BAR_W // 2, gy0, vss_sx + BAR_W // 2, strap_top)
    tie_y = strap_top - VIA1_LAND
    b.box(L_VIA1, vss_sx - VIA_W // 2, tie_y - VIA_W // 2, vss_sx + VIA_W // 2, tie_y + VIA_W // 2)
    b.box(
        L_METAL2,
        vss_sx - ROUTE_VIA_PAD // 2,
        tie_y - ROUTE_VIA_PAD // 2,
        vss_sx + ROUTE_VIA_PAD // 2,
        tie_y + ROUTE_VIA_PAD // 2,
    )

    draw_spines(b, spine_x, spine_span, vss_extra_lo=tie_y - ROUTE_VIA_PAD)

    # Compensation MIM capacitor, stacked over the device field (Metal4 /
    # FuseTop / Metal5). `klt extract`'s gf180mcu deck now recognises this
    # stack (klayout-tools#220/#225, #73's CAP_MK marker), so both plates are
    # wired for real (#77) -- see `_mim_cap` and plan.MimCapItem.
    cap = plan_mod.mim_cap(flat)
    assert cap.nets == ("vdd", "fb"), (
        f"{cap.key}: expected (bottom=vdd, top=fb), got {cap.nets} -- "
        "_mim_cap's via stack targets those two nets specifically"
    )
    cap_x = 0
    cap_y = next(g for g in row_geometry if g["row"].name == "AMPPAIR")["y0"]
    # AMPPCASC is the row the cap's footprint stacks over that also happens
    # to carry both `vdd` and `fb` rails (the amp PMOS cascode pair's body
    # tie and gate net, respectively) -- see the module docstring's "Routing
    # style" and `_mim_cap`'s own docstring for why piggy-backing on an
    # already-drawn rail, rather than drawing a fresh one, is what the via
    # stack does.
    via_row = next(g for g in row_geometry if g["row"].name == "AMPPCASC")
    vdd_ty, vdd_left, vdd_right = via_row["rail_geo"]["vdd"]
    fb_ty, fb_left, fb_right = via_row["rail_geo"]["fb"]

    # The AMPPCASC row's own vdd/fb rails are sized to reach that row's
    # *own* terminals, which does not necessarily already cover the fixed x
    # positions the cap's via stack needs (mim_cap_via_x, derived purely
    # from the cap's own geometry) -- extend the rails to reach them, same
    # layer, same net, so this merges into the existing rail rather than
    # creating a second disconnected one.
    mim_vdd_x, _mim_fb_up_x, mim_fb_down_x = mim_cap_via_x(cap, cap_x)
    if mim_vdd_x < vdd_left:
        b.box(L_METAL3, mim_vdd_x - TRACK_W // 2, vdd_ty - TRACK_W // 2, vdd_left + TRACK_W // 2, vdd_ty + TRACK_W // 2)
        vdd_left = mim_vdd_x
    elif mim_vdd_x > vdd_right:
        b.box(L_METAL3, vdd_right - TRACK_W // 2, vdd_ty - TRACK_W // 2, mim_vdd_x + TRACK_W // 2, vdd_ty + TRACK_W // 2)
        vdd_right = mim_vdd_x
    if mim_fb_down_x > fb_right:
        b.box(L_METAL3, fb_right - TRACK_W // 2, fb_ty - TRACK_W // 2, mim_fb_down_x + TRACK_W // 2, fb_ty + TRACK_W // 2)
        fb_right = mim_fb_down_x
    elif mim_fb_down_x < fb_left:
        b.box(L_METAL3, mim_fb_down_x - TRACK_W // 2, fb_ty - TRACK_W // 2, fb_left + TRACK_W // 2, fb_ty + TRACK_W // 2)
        fb_left = mim_fb_down_x

    _mim_cap(b, cap, cap_x, cap_y, vdd_ty, (vdd_left, vdd_right), fb_ty, (fb_left, fb_right))

    stats = {
        "flat": flat,
        "rows": row_geometry,
        "nets": nets,
        # Each routed net's Metal2 spine x and its (y_lo, y_hi) row-usage
        # span, as chosen by assign_spine_x. Reported (not just drawn) so
        # routing_budget.py can measure the spine bundle's real extent over
        # the device field instead of re-deriving the legalizer's answer.
        "spine_x": spine_x,
        "spine_span": spine_span,
        "bbox": (gx0, gy0, gx1, gy1),
        "core_bbox": (0, -POLY_EXT, block_right, block_top),
        "cap": cap,
    }
    return b, stats


def _guard_ring(b: Builder, x0: int, y0: int, x1: int, y1: int) -> None:
    segments = [
        (x0, y0, x1, y0 + GUARD_W),
        (x0, y1 - GUARD_W, x1, y1),
        (x0, y0 + GUARD_W, x0 + GUARD_W, y1 - GUARD_W),
        (x1 - GUARD_W, y0 + GUARD_W, x1, y1 - GUARD_W),
    ]
    for sx0, sy0, sx1, sy1 in segments:
        b.box(L_COMP, sx0, sy0, sx1, sy1)
        b.box(L_PPLUS, sx0 - IMPLANT_ENC, sy0 - IMPLANT_ENC, sx1 + IMPLANT_ENC, sy1 + IMPLANT_ENC)
        b.box(L_METAL1, sx0, sy0, sx1, sy1)
        if sx1 - sx0 > sy1 - sy0:
            cy = (sy0 + sy1) // 2
            x = sx0 + ENC_CT + CT // 2
            while x + CT // 2 + ENC_CT <= sx1:
                b.contact(x, cy)
                x += CT_PITCH
        else:
            cx = (sx0 + sx1) // 2
            yy = sy0 + ENC_CT + CT // 2
            while yy + CT // 2 + ENC_CT <= sy1:
                b.contact(cx, yy)
                yy += CT_PITCH


def mim_cap_via_x(cap: MimCapItem, x0: int) -> tuple[int, int, int]:
    """The three x positions ``_mim_cap``'s via stacks land at, computed
    from the cap's own geometry alone (``x0`` is its own left edge). Shared
    with ``build()`` so it can pre-widen the AMPPCASC row's ``vdd``/``fb``
    Metal3 rails to reach them (the rails' own natural extent, driven by
    their row's terminals, does not necessarily already cover these) before
    drawing the cap.
    """
    inset = MIM_PLATE_INSET
    vdd_x = x0 + inset // 2
    fb_up_x = x0 + cap.width_nm // 2
    fb_down_x = x0 + cap.width_nm + FB_DOWNHOP_CLEAR
    return vdd_x, fb_up_x, fb_down_x


def _via_pad(b: Builder, metal_layer: tuple[int, int], via_layer: tuple[int, int], cx: int, cy: int) -> None:
    """One via-stack step: a ``VIA_PAD``-square landing pad on ``metal_layer``
    with a centred ``VIA_W``-square via on ``via_layer`` immediately beneath
    it (``via_layer`` is the stack level connecting the metal *below*
    ``metal_layer`` up to it -- e.g. ``metal_layer=L_METAL2,
    via_layer=L_VIA1`` draws a Metal2 pad sitting on a Via1 that reaches down
    to whatever Metal1 is already there)."""
    b.box(metal_layer, cx - VIA_PAD // 2, cy - VIA_PAD // 2, cx + VIA_PAD // 2, cy + VIA_PAD // 2)
    b.box(via_layer, cx - VIA_W // 2, cy - VIA_W // 2, cx + VIA_W // 2, cy + VIA_W // 2)


def _mim_cap(
    b: Builder,
    cap: MimCapItem,
    x0: int,
    y0: int,
    vdd_ty: int,
    vdd_span: tuple[int, int],
    fb_ty: int,
    fb_span: tuple[int, int],
) -> None:
    """Draw the compensation MIM cap, both plates wired for real (#77, #88).

    ``vdd_ty``/``fb_ty`` are the heights of the already-drawn ``vdd``/``fb``
    Metal3 row rails in the row the cap stacks over (``AMPPCASC`` -- see
    ``build()``); ``vdd_span``/``fb_span`` are those rails' ``(left, right)``
    horizontal extents, used only to assert the chosen via x lands on drawn
    rail rather than past its end.

    Two different via-stack shapes, because the two plates sit on different
    layers relative to the deck's ``metals``/``vias`` connectivity stack
    (Metal1..Metal5, Via1..Via4 -- see ``klayout_tools.decks.gf180mcu``), but
    both now land their up-hop ``Via4`` *inside* the recognised plate
    footprint they contact, and both have to leave the recognised bottom/top
    plate geometry -- so the device's extracted ``C`` -- unchanged, since
    `klt lvs` (see below) still checks it against the reference with no real
    tolerance:

    * **Bottom plate (``vdd``, Metal4)** is *itself* one of the stack's
      metals, so the via stack just climbs Metal1 -> Via1 -> Metal2 -> Via2
      -> Metal3 -> Via3 straight into the already-drawn bottom-plate
      polygon -- no separate landing pad needed, and no change to that
      polygon's shape. The landing x is inside the bottom plate's own
      ``MIM_PLATE_INSET`` margin (the ring between the Metal4 box's edge and
      the smaller FuseTop box inset within it), clear of the top plate.

    * **Top plate (``fb``, FuseTop)** used to be routed through a small
      **tab** drawn outside ``CAP_MK``/``MIM_L_MK``, entirely past the
      bottom plate's own right edge, specifically so its contact ``Via4``
      would *not* land inside the Metal4 bottom-plate footprint. That was a
      workaround for a real tool limitation
      (`klayout-tools#364 <https://github.com/2AMLogic/klayout-tools/issues/364>`_,
      fixed by
      `PR #368 <https://github.com/2AMLogic/klayout-tools/pull/368>`_): a
      DRM-legal top-plate ``Via4`` -- one landing inside the bottom-plate
      footprint, exactly what ``MIMTM.2`` requires -- necessarily overlaps
      the Metal4 conductor in plan view, and before that fix `klt extract`'s
      generic per-layer ``metals[]``/``vias[]`` connectivity loop read that
      overlap as an ordinary via, merging the two plates onto one net. The
      tab routed *around* the bottom plate instead, at the cost of not being
      DRM-legal (gf180-bandgap#82: the tab itself had **zero** bottom-plate
      overlap, against ``MIMTM.3``'s 0.6um minimum, and the up-hop ``Via4``
      landing on it had **zero** ``Metal4`` overlap, against ``MIMTM.2``'s
      0.4um minimum).

      **PR #368 excludes a capacitor's own ``top_plate_via`` /
      ``bottom_plate`` overlap from that generic connectivity loop before it
      runs**, so a DRM-legal top-plate ``Via4`` now wires the top plate to
      ``top_plate_via_metal`` (Metal5) without also shorting it to the
      bottom plate. gf180-bandgap#88 re-verified this directly (a minimal
      repro: a `Via4` landing inside both a capacitor's declared
      `top_plate`/`bottom_plate` footprints now extracts `net_count == 2`,
      not `1`) before redrawing this contact against it. The tab, the
      Metal5 sideways wire that carried its signal *around* the bottom
      plate, the down-hop `Via4` that dropped back onto a disjoint Metal4
      pad, and that standalone pad are all gone: the up-hop `Via4` now lands
      directly on the recognised top plate, well inside the Metal4
      bottom-plate footprint (see the asserts below for the exact margins
      against ``MIMTM.2``), and climbs straight to Metal5 from there. A
      *new* Metal5 wire then carries the signal sideways to a down-hop point
      clear of the bottom plate (``FB_DOWNHOP_CLEAR`` past its right edge,
      the same margin the old down-hop kept, now measured from the bottom
      plate rather than from the tab that no longer exists), where an
      ordinary Via4 -> Metal4 (a small disjoint pad, spaced by
      ``mim.space.1``'s 1.2um Metal4-Metal4 minimum) -> Via3 -> Metal3 ->
      Via2 -> Metal2 -> Via1 chain reaches down into the already-drawn ``fb``
      rail, same as before.

      ``CAP_MK``/``MIM_L_MK`` no longer need the tab-shaped right-edge
      exception either: with no tab to exclude, both markers are drawn with
      the same ``+400`` overhang on all four sides the other three edges
      already had, so the recognised top plate is exactly the FuseTop box
      -- unchanged from before, so the extracted ``C`` is unchanged too.

    Since both plates' up-hop vias now land inside their own recognised
    plate's footprint, `klt extract` resolves *both* terminals to their real
    net without any marker-widening trick: the bottom plate to ``vdd``
    (klayout-tools#329, gf180-bandgap#89) and the top plate to ``fb``
    (klayout-tools#364/PR #368, gf180-bandgap#88). See
    ``layout/lvs/make_reference.py`` step 9 for the reference-netlist side of
    that, and ``layout/netlist/mk_extracted_dut.py`` for the now-deleted
    ``BA4`` back-annotation this made unnecessary.
    """
    w, h = cap.width_nm, cap.height_nm
    inset = MIM_PLATE_INSET
    vdd_x, fb_up_x, fb_down_x = mim_cap_via_x(cap, x0)

    # -- vdd (bottom plate) contact point: inside the Metal4 box's own
    # MIM_PLATE_INSET margin band, clear of the FuseTop top plate on top of
    # it.
    assert x0 <= vdd_x - VIA_PAD // 2 and vdd_x + VIA_PAD // 2 <= x0 + inset, (
        f"{cap.key}: vdd via pad does not fit inside the bottom plate's "
        "MIM_PLATE_INSET margin"
    )
    assert vdd_span[0] <= vdd_x <= vdd_span[1], f"{cap.key}: vdd contact x falls outside the drawn vdd rail"
    assert y0 <= vdd_ty <= y0 + h, f"{cap.key}: vdd rail height falls outside the cap's own footprint"

    # -- fb (top plate) up-hop contact point: centred on the cap's own
    # width, well inside both the recognised FuseTop plate (MIM_PLATE_INSET
    # margin) and the Metal4 bottom plate beneath it (MIMTM.2's 0.4um
    # minimum overlap, honoured here with a much wider margin -- see the
    # asserts immediately below).
    assert x0 + inset + VIA_W // 2 <= fb_up_x <= x0 + w - inset - VIA_W // 2, (
        f"{cap.key}: fb up-hop via does not land inside the recognised FuseTop top plate"
    )
    assert (
        x0 + MIM_VIA_OVERLAP_MIN + VIA_W // 2 <= fb_up_x <= x0 + w - MIM_VIA_OVERLAP_MIN - VIA_W // 2
    ), f"{cap.key}: fb up-hop via does not meet MIMTM.2's bottom-plate overlap minimum"
    assert y0 + inset + VIA_W // 2 <= fb_ty <= y0 + h - inset - VIA_W // 2, (
        f"{cap.key}: fb rail height falls outside the top plate (with via clearance)"
    )
    assert (
        y0 + MIM_VIA_OVERLAP_MIN + VIA_W // 2 <= fb_ty <= y0 + h - MIM_VIA_OVERLAP_MIN - VIA_W // 2
    ), f"{cap.key}: fb rail height does not meet MIMTM.2's bottom-plate overlap minimum"

    # -- fb down-hop: clear of the bottom plate's own right edge by
    # FB_DOWNHOP_CLEAR, which leaves mim.space.1's 1.2um Metal4-Metal4
    # minimum spacing comfortably satisfied between the bottom plate and the
    # standalone down-hop pad below.
    assert fb_down_x - VIA_PAD // 2 - (x0 + w) >= 1200, (
        f"{cap.key}: fb down-hop pad does not clear the bottom plate by mim.space.1's 1.2um minimum"
    )
    assert fb_span[0] <= fb_down_x <= fb_span[1], f"{cap.key}: fb down-hop x falls outside the drawn fb rail"

    # Bottom plate (Metal4) -- unchanged, solid box.
    b.box(L_METAL4, x0, y0, x0 + w, y0 + h)

    # Top plate (FuseTop): just the recognised box -- no more routing tab.
    b.box(L_FUSETOP, x0 + inset, y0 + inset, x0 + w - inset, y0 + h - inset)

    b.box(L_METAL5, x0 + 900, y0 + 900, x0 + w - 900, y0 + h - 900)
    # The deck's MiM recogniser requires both CAP_MK and MIM_L_MK on the top
    # plate (`top_plate_requires`); draw both over the same +400 margin on
    # all four sides -- there is no tab to exclude any more, so this is now a
    # plain symmetric marker box (#88; previously the right edge was pulled
    # in to the plate's own edge to keep the tab unrecognised -- see the
    # docstring for why that is gone).
    b.box(L_MIM_MK, x0 - 400, y0 - 400, x0 + w + 400, y0 + h + 400)
    b.box(L_CAP_MK, x0 - 400, y0 - 400, x0 + w + 400, y0 + h + 400)

    # vdd: Metal3 (existing AMPPCASC rail, gf180-bandgap#166) -> Via3 ->
    # straight into the bottom plate drawn above. Shorter than before the
    # row-routing rewrite: the rail used to be Metal1, needing an extra
    # Metal1 -> Via1 -> Metal2 -> Via2 hop to reach Metal3 first.
    b.box(L_VIA3, vdd_x - VIA_W // 2, vdd_ty - VIA_W // 2, vdd_x + VIA_W // 2, vdd_ty + VIA_W // 2)

    # fb up-hop: Via4 lands directly on the recognised FuseTop top plate,
    # inside the Metal4 bottom-plate footprint (DRM-legal per MIMTM.2, and
    # no longer read as a vdd/fb short since klayout-tools#364/PR #368) ->
    # Metal5.
    b.box(L_VIA4, fb_up_x - VIA_W // 2, fb_ty - VIA_W // 2, fb_up_x + VIA_W // 2, fb_ty + VIA_W // 2)
    b.box(L_METAL5, fb_up_x - VIA_PAD // 2, fb_ty - VIA_PAD // 2, fb_up_x + VIA_PAD // 2, fb_ty + VIA_PAD // 2)

    # fb Metal5 wire: up-hop (over the bottom plate) to down-hop (clear of
    # the bottom plate), both at the same rail height so this is one
    # straight run.
    b.box(
        L_METAL5,
        min(fb_up_x, fb_down_x) - FB_M5_WIRE_W // 2,
        fb_ty - FB_M5_WIRE_W // 2,
        max(fb_up_x, fb_down_x) + FB_M5_WIRE_W // 2,
        fb_ty + FB_M5_WIRE_W // 2,
    )

    # fb down-hop: Metal5 -> Via4 -> Metal4 (a standalone pad, spaced clear
    # of the bottom plate) -> Via3 -> Metal3 (the existing AMPPCASC fb rail,
    # gf180-bandgap#166). Shorter than before the row-routing rewrite: the
    # rail used to be Metal1, needing an extra Via2 -> Metal2 -> Via1 hop.
    b.box(L_VIA4, fb_down_x - VIA_W // 2, fb_ty - VIA_W // 2, fb_down_x + VIA_W // 2, fb_ty + VIA_W // 2)
    _via_pad(b, L_METAL4, L_VIA3, fb_down_x, fb_ty)
    _via_pad(b, L_METAL3, L_VIA2, fb_down_x, fb_ty)
    _via_pad(b, L_METAL2, L_VIA1, fb_down_x, fb_ty)


def save_options() -> kdb.SaveLayoutOptions:
    opts = kdb.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    return opts


def main() -> None:
    b, stats = build()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "bandgap_top.gds")
    b.layout.write(out_path, save_options())

    x0, y0, x1, y1 = stats["bbox"]
    area_um2 = (x1 - x0) * (y1 - y0) / 1e6
    print(f"wrote {out_path}")
    print(f"rows          : {len(stats['rows'])}")
    print(f"routed nets   : {len(stats['nets'])}")
    print(f"block bbox    : {(x1 - x0) / 1000:.2f} x {(y1 - y0) / 1000:.2f} um")
    print(f"block area    : {area_um2:.1f} um^2  ({area_um2 / 1e6:.5f} mm^2)")


if __name__ == "__main__":
    main()
