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

``klt``'s gf180mcu decks model exactly **one** metal level (``Metal1``,
34/0) — there is no ``Metal2``..``Metal5`` in either the DRC deck or the
extraction deck's connectivity graph. A block routed on layers the extraction
deck cannot see would extract as a pile of disconnected nets, so this layout
is routed entirely on ``Metal1`` plus ``Poly2``, using poly as the
crossunder layer:

* **Corridor spines** — one vertical ``Poly2`` spine per net, in a dedicated
  comp-free corridor down the left edge of the block.
* **Row rails** — inside each row, one horizontal ``Metal1`` rail per net
  used by that row, running from that net's spine out over the row's devices.
* **Device stubs** — every device terminal rises out of the device on a short
  ``Poly2`` stub to its net's rail. Poly and Metal1 cross freely (they only
  connect through a drawn ``Contact``), so a stub can pass under any number
  of rails belonging to other nets.

That is a correct single-metal routing discipline, but it is *not* how this
block would be routed with a real multi-metal stack, and it costs
significant area (see ``layout/bandgap_top/AREA.md``). The tool gap is filed
generically against klayout-tools; see ``layout/README.md`` § "Friction
filed".

Matching plan, device folding and the netlist reduction the extraction deck
implies all live in the two modules this one builds on:
:mod:`netlist_model` and :mod:`plan`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import klayout.db as kdb  # noqa: E402

import plan as plan_mod  # noqa: E402
from plan import (  # noqa: E402
    MimCapItem,
    MosItem,
    PnpItem,
    ResItem,
    Row,
    TapItem,
    TrimLadderItem,
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
L_METAL4 = (46, 0)
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
    L_METAL4: "Metal4",
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
# --------------------------------------------------------------------------- #
CT = 240  # contact.width.1 min 220
CT_PITCH = 500  # contact.space.1 min 250 -> 260 space here
ENC_CT = 100  # comp/poly2 enclosing contact, min 70
SD_COL = 900  # source/drain column width
POLY_EXT = 400  # gate poly2 extension past COMP
STUB_W = 380  # poly2 stub width (>= CT + 2*70)
BAR_W = 400  # Metal1 bar/rail width, metal1.width.1 min 230
STUB_BOT = 250  # poly2 stub bottom, above COMP top
STUB_CT = 330  # stub<->bar contact bottom, above COMP top
BAR_TOP = 700  # Metal1 SD bar top, above COMP top
HEAD = 1300  # COMP top -> first rail centre
TRACK_PITCH = 640  # rail pitch (400 wide + 240 space; metal1.space.1 min 230)
ISLAND_GAP = 500  # COMP-to-COMP between islands, comp.space.1 min 280
ROW_GAP = 1100
SPINE_W = 400
SPINE_PITCH = 640  # 400 wide + 240 space; poly2.space.1 min 240
FIELD_GAP = 900  # corridor -> device field
IMPLANT_ENC = 200  # Pplus/Nplus overlap of COMP
RES_PAD = 440  # ppolyf_u free-end contact pad height, > IMPLANT_ENC so the
# pad stays outside the RES_MK/Pplus/SAB marker box (CT + 2*ENC_CT room for
# the pad's own contact enclosure; see draw_res, #73)
NWELL_ENC = 600  # Nwell overlap of PMOS COMP, nwell.enclosing.comp.1 min 120
NWELL_CLEAR = 2000  # Nwell edge -> unrelated COMP
POLY_SP = 300  # poly2.space.1 min 240
GUARD_W = 1600  # guard-ring COMP width
GUARD_CLEAR = 1600  # block content -> guard ring inner edge


@dataclass
class Terminal:
    net: str
    stub_x: int
    stub_y0: int


class Builder:
    def __init__(self) -> None:
        self.layout = kdb.Layout()
        self.layout.dbu = 0.001
        self.cell = self.layout.create_cell(TOP_CELL)
        self._layers: dict[tuple[int, int], int] = {}
        for pair, name in LAYER_NAMES.items():
            index = self.layout.layer(*pair)
            self.layout.set_info(index, kdb.LayerInfo(pair[0], pair[1], name))
            self._layers[pair] = index

    def box(self, layer: tuple[int, int], x0: int, y0: int, x1: int, y1: int) -> None:
        self.cell.shapes(self._layers[layer]).insert(kdb.Box(x0, y0, x1, y1))

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

    gcx = (gate_x0 + gate_x1) // 2
    b.box(L_POLY2, gcx - STUB_W // 2, y1 + POLY_EXT - 100, gcx + STUB_W // 2, y1 + POLY_EXT + 100)
    terminals.append(Terminal(item.nets["g"], gcx, y1 + POLY_EXT - 100))

    for term, cx in (("s", x0 + SD_COL // 2), ("d", x1 - SD_COL // 2)):
        b.contact_column(cx, y0 + ENC_CT, y1 - ENC_CT)
        b.box(L_METAL1, cx - BAR_W // 2, y0 - 80, cx + BAR_W // 2, y1 + BAR_TOP)
        b.contact(cx, y1 + STUB_CT + CT // 2)
        b.box(L_POLY2, cx - STUB_W // 2, y1 + STUB_BOT, cx + STUB_W // 2, y1 + STUB_CT + CT + ENC_CT)
        terminals.append(Terminal(item.nets[term], cx, y1 + STUB_BOT))

    return terminals


def res_geometry(item: ResItem) -> tuple[int, int, int]:
    """``(width, height, leg_length)`` of a folded ``ppolyf_u`` serpentine."""
    pitch = item.width_nm + POLY_SP
    n = item.segments
    leg = (item.length_nm - (n - 1) * pitch) // n
    if leg <= item.width_nm + 2 * (ENC_CT + CT):
        raise ValueError(f"{item.key}: {n} segments is too many for L={item.length_nm}")
    return (n - 1) * pitch + item.width_nm, leg, leg


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
    # (`ppolyf_u_1k`) body is *not* marked RES_MK: the deck has no device
    # entry for that flavour (klayout-tools#299), and RES_MK's 350 ohm/sq
    # would be silently wrong for it, so `Resistor` (62/0) is drawn instead
    # -- one of `ResistorDevice.excludes` for the base flavour -- keeping it
    # a short (today's behaviour) rather than a wrong value.
    body_layers = (L_PPLUS, L_SAB) if item.high_rho else (L_PPLUS, L_RES_MK, L_SAB)
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
        b.box(L_METAL1, cx - BAR_W // 2, cy - CT // 2 - 80, cx + BAR_W // 2, y0 + leg + BAR_TOP)
        b.contact(cx, y0 + leg + STUB_CT + CT // 2)
        b.box(
            L_POLY2,
            cx - STUB_W // 2,
            y0 + leg + STUB_BOT,
            cx + STUB_W // 2,
            y0 + leg + STUB_CT + CT + ENC_CT,
        )
        terminals.append(Terminal(net, cx, y0 + leg + STUB_BOT))
    return terminals


TRIM_PAD = 440


def trim_geometry(item: TrimLadderItem) -> tuple[int, int, int, int]:
    """``(width, height, unit_pitch, sub_row_counts)`` for the trim ladder."""
    unit_x = item.unit_length_nm + 2 * TRIM_PAD
    pitch = unit_x + POLY_SP
    lower = item.strap_after_unit  # units 1..31 in the strapped group
    upper = item.units - lower
    width = max(lower, upper) * pitch + 2000
    height = 2 * item.unit_width_nm + 3600
    return width, height, pitch, lower


def draw_trim(b: Builder, item: TrimLadderItem, x0: int, y0: int) -> list[Terminal]:
    unit_x = item.unit_length_nm + 2 * TRIM_PAD
    pitch = unit_x + POLY_SP
    uw = item.unit_width_nm
    lower_n = item.strap_after_unit
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

    # Metal-option trim strap for DRAWN_TRIM_CODE: shorts units 1..lower_n.
    strap_y = y0 + uw + 1800
    tn0_x = lower_pads[0][0]
    b.box(L_METAL1, tn0_x - BAR_W // 2, row0_y + uw // 2, tn0_x + BAR_W // 2, strap_y + BAR_W // 2)
    b.box(L_METAL1, tn0_x - BAR_W // 2, strap_y - BAR_W // 2, link_x + BAR_W // 2, strap_y + BAR_W // 2)
    b.box(L_METAL1, link_x - BAR_W // 2, strap_y - BAR_W // 2, link_x + BAR_W // 2, row1_y + uw // 2)

    top = row1_y + uw
    terminals: list[Terminal] = []
    for cx, net in ((tn0_x, item.nets[0]), (upper_pads[-1][0], item.nets[1])):
        b.box(L_METAL1, cx - BAR_W // 2, row0_y + uw // 2 if cx == tn0_x else row1_y + uw // 2, cx + BAR_W // 2, top + BAR_TOP)
        b.contact(cx, top + STUB_CT + CT // 2)
        b.box(L_POLY2, cx - STUB_W // 2, top + STUB_BOT, cx + STUB_W // 2, top + STUB_CT + CT + ENC_CT)
        terminals.append(Terminal(net, cx, top + STUB_BOT))
    return terminals


PNP_GAP = 800
PNP_RING = 1200
PNP_NW_ENC = 700
PNP_COL_GAP = 900


def pnp_size(item: PnpItem) -> tuple[int, int]:
    emitter = int(item.emitter_um * 1000)
    base_outer = emitter + 2 * (PNP_GAP + PNP_RING)
    nwell = base_outer + 2 * PNP_NW_ENC
    coll_outer = nwell + 2 * (PNP_COL_GAP + PNP_RING)
    return coll_outer, coll_outer


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
    b.box(L_METAL1, strap_x - BAR_W // 2, cy - BAR_W // 2, base_strap_x + BAR_W // 2, cy + BAR_W // 2)
    b.box(L_METAL1, strap_x - BAR_W // 2, cy, strap_x + BAR_W // 2, y0 + size + BAR_TOP)

    terminals: list[Terminal] = []
    for tx, net in ((cx, item.emitter_net), (strap_x, item.base_net)):
        b.contact(tx, y0 + size + STUB_CT + CT // 2)
        b.box(
            L_POLY2,
            tx - STUB_W // 2,
            y0 + size + STUB_BOT,
            tx + STUB_W // 2,
            y0 + size + STUB_CT + CT + ENC_CT,
        )
        terminals.append(Terminal(net, tx, y0 + size + STUB_BOT))
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
    b.box(L_METAL1, cx - BAR_W // 2, cy, cx + BAR_W // 2, y1 + BAR_TOP)
    b.contact(cx, y1 + STUB_CT + CT // 2)
    b.box(L_POLY2, cx - STUB_W // 2, y1 + STUB_BOT, cx + STUB_W // 2, y1 + STUB_CT + CT + ENC_CT)
    return [Terminal(item.net, cx, y1 + STUB_BOT)]


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


def build() -> tuple[Builder, dict]:
    flat, rows = plan_mod.load_plan()
    nets = plan_mod.routed_nets(rows)
    spine_x = {net: i * SPINE_PITCH for i, net in enumerate(nets)}
    field_x0 = len(nets) * SPINE_PITCH + FIELD_GAP

    b = Builder()

    row_geometry: list[dict] = []
    y = 0
    for row in rows:
        sizes = [item_size(item) for item in row.items]
        row_h = max(h for _, h in sizes)
        x = field_x0
        terminals: list[Terminal] = []
        placements: list[tuple[object, int, int]] = []
        for item, (w, _h) in zip(row.items, sizes):
            terminals.extend(draw_item(b, item, x, y))
            placements.append((item, x, w))
            x += w + ISLAND_GAP
        row_right = x - ISLAND_GAP

        # One rail per net used in this row, ordered so the net whose
        # rightmost stub is furthest out takes the highest track (keeps rails
        # short and makes the ordering deterministic).
        by_net: dict[str, list[Terminal]] = {}
        for terminal in terminals:
            by_net.setdefault(terminal.net, []).append(terminal)
        order = sorted(by_net, key=lambda n: (max(t.stub_x for t in by_net[n]), n))

        track0 = y + row_h + HEAD
        for track, net in enumerate(order):
            ty = track0 + track * TRACK_PITCH
            sx = spine_x[net]
            right = max(t.stub_x for t in by_net[net])
            b.box(L_METAL1, sx - BAR_W // 2, ty - BAR_W // 2, right + BAR_W // 2, ty + BAR_W // 2)
            b.contact(sx, ty)
            for terminal in by_net[net]:
                b.box(
                    L_POLY2,
                    terminal.stub_x - STUB_W // 2,
                    terminal.stub_y0,
                    terminal.stub_x + STUB_W // 2,
                    ty + CT // 2 + ENC_CT,
                )
                b.contact(terminal.stub_x, ty)

        top = track0 + (len(order) - 1) * TRACK_PITCH + BAR_W // 2
        row_geometry.append(
            {
                "row": row,
                "y0": y,
                "content_top": y + row_h,
                "top": top,
                "right": row_right,
                "nets": order,
                "placements": placements,
            }
        )
        y = top + ROW_GAP

    block_top = y - ROW_GAP
    block_right = max(g["right"] for g in row_geometry)

    # Corridor spines span the whole block.
    for net in nets:
        sx = spine_x[net]
        b.box(L_POLY2, sx - SPINE_W // 2, -POLY_EXT - 400, sx + SPINE_W // 2, block_top + 400)

    # One Nwell for the whole PMOS band (keeps the extracted PMOS body a
    # single net). The band is contiguous by construction -- see plan.py.
    pmos_rows = [g for g in row_geometry if g["row"].nwell]
    nwell_box = (
        -SPINE_W // 2 - NWELL_ENC,
        min(g["y0"] for g in pmos_rows) - POLY_EXT - NWELL_ENC,
        max(g["right"] for g in pmos_rows) + NWELL_ENC,
        max(g["top"] for g in pmos_rows) + NWELL_ENC,
    )
    b.box(L_NWELL, *nwell_box)

    # Net labels on Metal1 (34/10). Only the block's own pins are labelled --
    # `Netlist.make_top_level_pins()` promotes every *named* net to a pin, so
    # labelling internal nets would invent pins the schematic does not have.
    for net in ("vdd", "vss", "vref"):
        sx = spine_x[net]
        target = next(g for g in row_geometry if net in g["nets"])
        ty = target["content_top"] + HEAD + target["nets"].index(net) * TRACK_PITCH
        b.label(sx, ty, net)

    # Guard ring: p+ COMP tied to vss, around the whole block (floorplan §9).
    gx0 = -SPINE_W // 2 - GUARD_CLEAR - GUARD_W
    gy0 = -POLY_EXT - GUARD_CLEAR - GUARD_W
    gx1 = block_right + GUARD_CLEAR + GUARD_W
    gy1 = block_top + GUARD_CLEAR + GUARD_W
    _guard_ring(b, gx0, gy0, gx1, gy1)

    # Tie the guard ring to vss with a Metal1 strap over the vss spine. vss
    # is the first spine (x = 0), so a strap 200 nm either side of it touches
    # every vss rail (each rail starts at its own spine) and nothing else --
    # the next spine is 700 nm away, leaving 300 nm of Metal1 clearance. A
    # *poly* strap would not work here: poly crossing the guard ring's COMP
    # would extract as a spurious NMOS device.
    b.box(L_METAL1, spine_x["vss"] - BAR_W // 2, gy0, spine_x["vss"] + BAR_W // 2, block_top)

    # Compensation MIM capacitor, stacked over the device field (Metal4 /
    # FuseTop / Metal5 -- layers outside both klt decks; see plan.MimCapItem).
    cap = plan_mod.mim_cap(flat)
    cap_x = field_x0
    cap_y = next(g for g in row_geometry if g["row"].name == "AMPPAIR")["y0"]
    _mim_cap(b, cap, cap_x, cap_y)

    stats = {
        "flat": flat,
        "rows": row_geometry,
        "nets": nets,
        "bbox": (gx0, gy0, gx1, gy1),
        "core_bbox": (-SPINE_W // 2, -POLY_EXT, block_right, block_top),
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


def _mim_cap(b: Builder, cap: MimCapItem, x0: int, y0: int) -> None:
    w, h = cap.width_nm, cap.height_nm
    b.box(L_METAL4, x0, y0, x0 + w, y0 + h)
    b.box(L_FUSETOP, x0 + 600, y0 + 600, x0 + w - 600, y0 + h - 600)
    b.box(L_METAL5, x0 + 900, y0 + 900, x0 + w - 900, y0 + h - 900)
    # The deck's MiM recogniser requires both CAP_MK and MIM_L_MK on the top
    # plate (`top_plate_requires`); draw CAP_MK over the same footprint as
    # the existing MIM_L_MK box (#73).
    b.box(L_MIM_MK, x0 - 400, y0 - 400, x0 + w + 400, y0 + h + 400)
    b.box(L_CAP_MK, x0 - 400, y0 - 400, x0 + w + 400, y0 + h + 400)


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
