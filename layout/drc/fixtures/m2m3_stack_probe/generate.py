#!/usr/bin/env python3
"""Generate ``m2m3_stack_probe.gds`` — the Metal2/Metal3 routing-stack probe.

Evidence fixture for the multi-level-metal routing study
(``layout/routing/multi-metal-routing-study.md``, gf180-bandgap#160). The
study proposes replacing ``bandgap_top``'s Metal1-only corridor-and-rail
routing with **Metal2 vertical spines + Metal3 horizontal row rails running
over the devices**. Two of its assumptions are load-bearing and neither can
be settled by reading a document:

1. **The extraction deck really carries the Metal1→Via1→Metal2→Via2→Metal3
   stack** (klayout-tools#220), i.e. a net routed up onto Metal2/Metal3 and
   back down extracts as *one* net rather than as disconnected pieces. The
   block's only existing multi-metal geometry is the compensation MIM cap's
   via stack, which is a capacitor-plate contact, not a two-terminal route
   between two devices — so it does not exercise this.
2. **The proposed track sizing is DRC-clean under the deck as installed
   today**, including the ``via1..via4.width.1`` / ``metalN.enclosing.viaN``
   rules that did not exist when the MIM cap's via stack was drawn
   (gf180-bandgap#159 — the current ``generate.py`` ``VIA_W = 240`` nm is
   *below* the ``via*.width.1`` 260 nm minimum this fixture sizes against).

Shape: two identical ``ppolyf_u`` poly resistors, 28 µm apart, wired **in
series into a single loop** using nothing but the proposed routing stack —
``R_A``'s top terminal to ``R_B``'s bottom terminal on net *M*, and ``R_A``'s
bottom terminal to ``R_B``'s top terminal on net *N*::

      R_A                       R_B
      (poly, x 0..2 um)         (poly, x 30..32 um)
        top ---- M -------------- bot
        bot ---- N -------------- top

Each of the two connections climbs Metal1 → Via1 → Metal2 (a *vertical*
track, drawn deliberately **over the resistor's own poly body** — the
over-the-cell case the study depends on) → Via2 → Metal3 (a *horizontal*
track spanning the gap between the two devices) → Via2 → Metal2 → Via1 →
Metal1. The two nets' Metal2 tracks run side by side at the proposed
``TRACK_PITCH`` for a 720 nm stretch, and their two Metal3 tracks run
parallel for the whole 30 µm span, so ``metal2.space.1`` / ``metal3.space.1``
are exercised at exactly the pitch the study budgets area against.

That makes the extraction result a three-way discriminator, not a smoke test:

===============  ==================================================
extracted nets   meaning
===============  ==================================================
**2**            correct — the stack conducts and the two adjacent
                 tracks stay distinct (what the study assumes)
4                the Metal2/Metal3 stack is *not* extracted (each
                 resistor terminal is its own isolated net)
1                the two parallel tracks are read as shorted
===============  ==================================================

Run from the repo root::

    uv run --with klayout python3 layout/drc/fixtures/m2m3_stack_probe/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled), so
re-running leaves ``git diff`` empty — the same reproducibility contract
``layout/README.md`` documents for ``trivial_poly_res`` and for
``bandgap_top``.

Checked with (both committed under ``layout/drc/reports/m2m3_stack_probe/``
and ``layout/lvs/reports/m2m3_stack_probe/``)::

    python3 layout/drc/run_drc.py \\
        layout/drc/fixtures/m2m3_stack_probe/m2m3_stack_probe.gds
    klt extract layout/drc/fixtures/m2m3_stack_probe/m2m3_stack_probe.gds \\
        --deck gf180mcu --top m2m3_stack_probe --format json
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import klayout.db as kdb

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))

from klayout_builder import BuilderBase  # noqa: E402

TOP_CELL = "m2m3_stack_probe"

# --------------------------------------------------------------------------- #
# Layers (gf180mcu GDS numbering, same table layout/bandgap_top/generate.py
# uses).
# --------------------------------------------------------------------------- #
L_POLY2 = (30, 0)
L_PPLUS = (31, 0)
L_CONTACT = (33, 0)
L_METAL1 = (34, 0)
L_VIA1 = (35, 0)
L_METAL2 = (36, 0)
L_VIA2 = (38, 0)
L_METAL3 = (42, 0)
L_SAB = (49, 0)
L_RES_MK = (110, 5)

LAYER_NAMES = {
    L_POLY2: "Poly2",
    L_PPLUS: "Pplus",
    L_CONTACT: "Contact",
    L_METAL1: "Metal1",
    L_VIA1: "Via1",
    L_METAL2: "Metal2",
    L_VIA2: "Via2",
    L_METAL3: "Metal3",
    L_SAB: "SAB",
    L_RES_MK: "RES_MK",
}

# --------------------------------------------------------------------------- #
# Geometry, in nanometres (dbu = 0.001 um). Every value is quoted against the
# gf180mcu deck rule it has to clear, read out of the *installed* deck
# (`klayout_tools/decks/gf180mcu.py`) rather than from memory — see
# `layout/routing/multi-metal-routing-study.md` § "Sizing against the deck".
# --------------------------------------------------------------------------- #
CT = 240  # contact.width.1 min 220
ENC_CT = 100  # poly2.enclosing.contact.1 min 70; metal1.enclosing.contact.1 min 5
IMPLANT_ENC = 200  # marker overhang past the resistor body, as in plan.py
RES_PAD = 440  # unmarked free-end poly pad, > IMPLANT_ENC (plan.RES_PAD)

M1_W = 400  # metal1.width.1 min 230
M1_PAD = CT + 2 * ENC_CT  # 440 nm square Metal1 landing pad over a contact

#: Proposed routing-track geometry. Metal2/Metal3 share one set of rules —
#: `metal2.width.1` / `metal3.width.1` are both 280 nm, and
#: `metal2.space.1` / `metal3.space.1` are both 280 nm.
TRACK_W = 400  # metal2.width.1 / metal3.width.1 min 280 (1.43x margin)
TRACK_SP = 320  # metal2.space.1 / metal3.space.1 min 280 (1.14x margin)
TRACK_PITCH = TRACK_W + TRACK_SP  # 720 nm

VIA = 260  # via1.width.1 / via2.width.1 min 260 (exactly the DRM's fixed size)
VIA_ENC = 70  # metal2.enclosing.via1.1 / metal3.enclosing.via2.1 min 10 (7x)
VIA_PAD = VIA + 2 * VIA_ENC  # 400 nm square landing pad == TRACK_W

# Resistor bodies: two identical vertical ppolyf_u bars.
RES_W = 2000
RES_L = 20000
RES_A_X = 0
RES_B_X = 30000

# Track heights/positions of the two routed nets.
NET_M_TRACK_Y = 10000  # Metal3 track for net M (crosses both poly bodies)
NET_N_TRACK_Y = NET_M_TRACK_Y + TRACK_PITCH  # its neighbour, one pitch above


class Builder(BuilderBase):
    def __init__(self) -> None:
        super().__init__(TOP_CELL, LAYER_NAMES)

    def square(self, layer: tuple[int, int], cx: int, cy: int, size: int) -> None:
        self.box(layer, cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2)

    def hwire(self, layer: tuple[int, int], x0: int, x1: int, cy: int, width: int) -> None:
        self.box(layer, min(x0, x1), cy - width // 2, max(x0, x1), cy + width // 2)

    def vwire(self, layer: tuple[int, int], cx: int, y0: int, y1: int, width: int) -> None:
        self.box(layer, cx - width // 2, min(y0, y1), cx + width // 2, max(y0, y1))


def draw_resistor(b: Builder, x0: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Draw one vertical ``ppolyf_u`` bar at ``x0``.

    Returns the ``(x, y)`` of its bottom and top terminal contacts. The
    recognition-marker discipline mirrors ``bandgap_top``'s ``draw_res``: the
    body carries ``Pplus`` + ``SAB`` + ``RES_MK`` (the deck's ``ppolyf_u``
    recogniser is ``pplus & poly2 & sab & res_mk``), and each free end gets a
    dedicated *unmarked* poly pad that sticks out past the marker box, so the
    contact lands on genuine terminal region rather than inside the body
    (gf180-bandgap#73).
    """
    cx = x0 + RES_W // 2
    b.box(L_POLY2, x0, 0, x0 + RES_W, RES_L)
    for layer in (L_PPLUS, L_SAB, L_RES_MK):
        b.box(layer, x0 - IMPLANT_ENC, -IMPLANT_ENC, x0 + RES_W + IMPLANT_ENC, RES_L + IMPLANT_ENC)

    terminals: list[tuple[int, int]] = []
    for pad_y0, pad_y1 in ((-RES_PAD, 0), (RES_L, RES_L + RES_PAD)):
        b.box(L_POLY2, x0, pad_y0, x0 + RES_W, pad_y1)
        cy = (pad_y0 + pad_y1) // 2
        b.square(L_CONTACT, cx, cy, CT)
        b.square(L_METAL1, cx, cy, M1_PAD)
        terminals.append((cx, cy))
    return terminals[0], terminals[1]


def route(
    b: Builder,
    start: tuple[int, int],
    end: tuple[int, int],
    up_x: int,
    down_x: int,
    track_y: int,
) -> None:
    """Wire ``start`` to ``end`` over the proposed Metal2/Metal3 stack.

    ``start``/``end`` are Metal1 landing-pad centres (each already sitting on
    a contact into a resistor terminal). The route runs Metal1 → Via1 →
    Metal2 (vertical, at ``up_x`` / ``down_x``, deliberately over the poly
    body) → Via2 → Metal3 (horizontal, at ``track_y``) → Via2 → Metal2 →
    Via1 → Metal1, i.e. every level of the stack the study's scheme uses.
    """
    for (px, py), tx in ((start, up_x), (end, down_x)):
        # Metal1 jog from the terminal pad across to the track's x position
        # (zero-length when the track sits directly over the terminal).
        b.hwire(L_METAL1, px, tx, py, M1_W)
        b.square(L_METAL1, tx, py, M1_PAD)
        # Metal1 -> Via1 -> Metal2.
        b.square(L_VIA1, tx, py, VIA)
        b.square(L_METAL2, tx, py, VIA_PAD)
        # Metal2 vertical run up/down to the Metal3 track height.
        b.vwire(L_METAL2, tx, py, track_y, TRACK_W)
        # Metal2 -> Via2 -> Metal3.
        b.square(L_METAL2, tx, track_y, VIA_PAD)
        b.square(L_VIA2, tx, track_y, VIA)
        b.square(L_METAL3, tx, track_y, VIA_PAD)
    # The Metal3 track itself, spanning the two via columns.
    b.hwire(L_METAL3, up_x, down_x, track_y, TRACK_W)


def build() -> Builder:
    b = Builder()
    a_bot, a_top = draw_resistor(b, RES_A_X)
    b_bot, b_top = draw_resistor(b, RES_B_X)

    # Net M: R_A top -> R_B bottom. Its Metal2 columns sit directly over each
    # resistor's own body (x = the body centre).
    route(b, a_top, b_bot, up_x=a_top[0], down_x=b_bot[0], track_y=NET_M_TRACK_Y)
    # Net N: R_A bottom -> R_B top, on the neighbouring track — one
    # TRACK_PITCH across in Metal2 and one TRACK_PITCH up in Metal3, so both
    # spacing rules are exercised against a real neighbour rather than
    # against empty field.
    route(
        b,
        a_bot,
        b_top,
        up_x=a_bot[0] + TRACK_PITCH,
        down_x=b_top[0] + TRACK_PITCH,
        track_y=NET_N_TRACK_Y,
    )
    return b


def save_options() -> kdb.SaveLayoutOptions:
    opts = kdb.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    return opts


def main() -> None:
    b = build()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, f"{TOP_CELL}.gds")
    b.layout.write(out_path, save_options())
    bbox = b.cell.bbox()
    print(f"wrote {out_path}")
    print(f"bbox          : {bbox.width() / 1000:.2f} x {bbox.height() / 1000:.2f} um")
    print(f"track pitch   : {TRACK_PITCH / 1000:.2f} um "
          f"({TRACK_W / 1000:.2f} wide + {TRACK_SP / 1000:.2f} space)")
    print(f"via size      : {VIA / 1000:.2f} um, enclosure {VIA_ENC / 1000:.2f} um")
    print("expected klt extract: 2 devices (ppolyf_u), 2 nets")


if __name__ == "__main__":
    main()
