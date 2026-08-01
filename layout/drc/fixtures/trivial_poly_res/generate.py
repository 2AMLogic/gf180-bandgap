#!/usr/bin/env python3
"""Generate ``trivial_poly_res.gds``: a trivial single-device layout (a
poly2 resistor with two contacted terminals) used to prove out this repo's
``klt drc --deck gf180mcu`` bring-up (issue #15).

Built directly with the ``klayout.db`` (``pya``-compatible) Python API --
``klt`` has no layout-generation capability yet (klayout-tools Phase 3,
"write", has not started). Mirrors the construction pattern in
klayout-tools' own worked example, ``examples/drc/generate.py``: a
``kdb.Layout`` with layer/datatype pairs matching the target DRC deck,
boxes inserted directly, ``layout.write(path)``.

Shape, by layer (all coordinates in database units; ``dbu_um = 0.001``, so
1 dbu = 1 nm, matching the gf180mcu deck's convention):

- ``Poly2`` (30/0): two wide contact "head" pads joined by a narrow body
  bar. The body is drawn 100 dbu (0.10 um) wide -- narrower than the
  ``poly2.width.1`` rule's 180 dbu (0.18 um) minimum -- a **seeded
  violation**, deliberately, so the DRC report is proven to catch
  something (mirrors the sky130 worked example's narrow poly bar).
- ``Contact`` (33/0): one 240x240 dbu (0.24 x 0.24 um) cut in each head pad
  -- above the ``contact.width.1`` 220 dbu minimum, and enclosed by Poly2
  with an 180 dbu margin on every side -- above the
  ``poly2.enclosing.contact.1`` 70 dbu minimum. Clean by design; the
  narrow body is this fixture's only seeded violation.
- ``Metal1`` (34/0): one routing pad over each contact, well above the
  ``metal1.width.1`` 230 dbu minimum. Clean by design.

Run from the repo root:

    uv run --with klayout python3 layout/drc/fixtures/trivial_poly_res/generate.py

Regenerates ``trivial_poly_res.gds`` next to this script, byte-for-byte
deterministically -- GDSII header timestamps are disabled explicitly (see
``save_options()``), so re-running produces an identical file and
``git diff`` stays empty.
The committed DRC reports under ``layout/drc/reports/trivial_poly_res/``
are the ``klt drc`` output against that exact file -- see
``layout/README.md`` for the reproducible invocation and the append-only
report convention (do not overwrite a committed report on re-run).
"""

import os

import klayout.db as kdb

# Layer/datatype pairs, per klayout-tools' gf180mcu deck
# (src/klayout_tools/decks/gf180mcu.py).
POLY2 = (30, 0)
CONTACT = (33, 0)
METAL1 = (34, 0)


def _terminal(
    top: kdb.Cell,
    poly2: int,
    contact: int,
    metal1: int,
    pad_box: kdb.Box,
    contact_box: kdb.Box,
    metal1_box: kdb.Box,
) -> None:
    """Insert one clean poly2/contact/metal1 resistor terminal."""
    top.shapes(poly2).insert(pad_box)
    top.shapes(contact).insert(contact_box)
    top.shapes(metal1).insert(metal1_box)


def build() -> kdb.Layout:
    layout = kdb.Layout()
    layout.dbu = 0.001  # micrometres per dbu -> dbu_um = 0.001 (1 dbu = 1 nm)
    top = layout.create_cell("TRIVIAL_POLY_RES")

    poly2 = layout.layer(*POLY2)
    layout.set_info(poly2, kdb.LayerInfo(*POLY2, "Poly2"))
    contact = layout.layer(*CONTACT)
    layout.set_info(contact, kdb.LayerInfo(*CONTACT, "Contact"))
    metal1 = layout.layer(*METAL1)
    layout.set_info(metal1, kdb.LayerInfo(*METAL1, "Metal1"))

    # Bottom terminal ("A"): wide poly2 head, centered 240x240 contact,
    # 400x400 metal1 landing pad -- every rule clean.
    _terminal(
        top,
        poly2,
        contact,
        metal1,
        pad_box=kdb.Box(900, -600, 1500, 0),
        contact_box=kdb.Box(1080, -420, 1320, -180),
        metal1_box=kdb.Box(1000, -500, 1400, -100),
    )

    # Resistor body: 100 dbu (0.10 um) wide -- narrower than the
    # poly2.width.1 minimum of 180 dbu (0.18 um). Seeded violation.
    top.shapes(poly2).insert(kdb.Box(1100, 0, 1200, 3000))

    # Top terminal ("B"): mirror of the bottom terminal -- clean.
    _terminal(
        top,
        poly2,
        contact,
        metal1,
        pad_box=kdb.Box(900, 3000, 1500, 3600),
        contact_box=kdb.Box(1080, 3180, 1320, 3420),
        metal1_box=kdb.Box(1000, 3100, 1400, 3500),
    )

    return layout


def save_options() -> kdb.SaveLayoutOptions:
    """Writer options that make the emitted GDS byte-stable.

    ``klayout.db``'s GDSII writer stamps wall-clock modification/access
    times into the ``BGNLIB``/``BGNSTR`` records by default, so two runs
    over identical geometry produce byte-different files. Disabling
    timestamps makes the output a pure function of the geometry, which is
    what lets ``layout/README.md``'s "regenerate and ``git diff`` should be
    empty" check actually hold.
    """
    opts = kdb.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    return opts


def main() -> None:
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "trivial_poly_res.gds")
    build().write(out_path, save_options())
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
