#!/usr/bin/env python3
"""Emit the LVS **reference** netlist for ``bandgap_top``.

``klt lvs`` compares a layout-extracted netlist against a reference netlist.
The reference cannot be ``design/netlist/bandgap_top.spice`` verbatim, because
the extracted side is not a full-device netlist: ``klt``'s gf180mcu extraction
deck recognises **only** ``nfet``/``pfet`` (from ``COMP``/``Poly2``/``Nwell``)
and treats ``Poly2`` as a plain conductor. It has no resistor, bipolar or
MIM-capacitor device extractor, and no Metal2..Metal5 connectivity.

So this script mechanically derives the reference from the committed
schematic netlist, applying exactly the transformations the extraction deck's
own capabilities imply — no hand editing, no per-device fudging:

1. **Flatten** ``design/netlist/bandgap_top.spice``
   (:mod:`layout.bandgap_top.netlist_model`).
2. **Collapse every ``ppolyf_u``/``ppolyf_u_1k`` resistor to a short** — its
   drawn body is ``Poly2``, which the deck connects as a conductor.
3. **Resolve the ideal ``RS0..RS5`` trim straps** at the trim code the layout
   draws its metal strap option for (``plan.DRAWN_TRIM_CODE``).
4. **Drop every ``pnp_*`` and ``cap_mim_*``** — drawn in the layout, but
   outside the deck's device set.
5. **Expand each MOS to its drawn finger count** (``plan.fingers``): *n*
   parallel unit devices of ``W/n``, matching the *n* separate gate islands
   the layout draws. Total ``W`` and ``L`` are preserved.
6. **Add the layout's edge dummy devices** (``plan.build_rows``), which are
   real transistors in the layout and so must be real transistors here.
7. **Re-target the body terminals** to the nets the deck actually produces:
   NMOS bodies to the deck's ``vsubs`` global, PMOS bodies to the single
   Nwell net of the contiguous PMOS band.

Every one of those seven steps is a **tool-capability consequence**, not a
design simplification — the layout still draws all of the dropped devices.
The resulting LVS verdict is therefore a *MOS-device-and-connectivity* LVS,
not a full-device LVS; ``layout/README.md`` says so explicitly and the gap is
filed generically against klayout-tools.

Usage::

    python3 layout/lvs/make_reference.py -o layout/lvs/bandgap_top.ref.spice
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "layout" / "bandgap_top"))

import netlist_model  # noqa: E402
import plan as plan_mod  # noqa: E402

#: Net the ``klt`` gf180mcu extraction deck ties every NMOS body to
#: (``decks.ExtractionDeck.substrate_net``); the deck draws no substrate-tap
#: layer, so it cannot derive a real body net.
SUBSTRATE_NET = "vsubs"

#: Name used for the PMOS band's single Nwell net. The extraction deck never
#: connects Nwell to Contact (doing so would short every device in the well
#: together), so the extracted PMOS body is an unnamed net; the comparer
#: matches it structurally.
NWELL_NET = "nwl"

TOP = "bandgap_top"


def sanitise(net: str) -> str:
    """Hierarchy-safe net name for SPICE (``amp.n1`` -> ``amp_n1``)."""
    return net.replace(".", "_")


def build_reference(trim_code: int) -> tuple[str, dict]:
    flat, rows = plan_mod.load_plan()
    reduction = netlist_model.reduce_nets(flat, trim_code)

    def net_of(name: str) -> str:
        return sanitise(reduction.get(name, name))

    lines: list[str] = []
    counts = {"nfet": 0, "pfet": 0, "dummy": 0}
    used_nets: set[str] = set()

    for row in rows:
        for item in row.items:
            if not isinstance(item, plan_mod.MosItem):
                continue
            drain = net_of(item.nets["d"])
            gate = net_of(item.nets["g"])
            source = net_of(item.nets["s"])
            body = SUBSTRATE_NET if item.kind == "nfet" else NWELL_NET
            used_nets.update((drain, gate, source, body))
            name = item.key.replace(".", "_").replace("#", "_")
            lines.append(
                f"M{name} {drain} {gate} {source} {body} {item.kind} "
                f"L={item.l_nm / 1000.0:g}U W={item.w_nm / 1000.0:g}U"
            )
            counts[item.kind] += 1
            if item.dummy:
                counts["dummy"] += 1

    # Pins: the block's three real ports plus the two body nets the deck
    # synthesises. `Netlist.make_top_level_pins()` promotes every *named*
    # extracted net to a pin, and only vdd/vss/vref carry a Metal1 label in
    # the layout, so those three plus `vsubs` are the extracted pin set.
    pins = [p for p in ("vdd", "vss", "vref") if p in used_nets]
    pins.append(SUBSTRATE_NET)
    pins.append(NWELL_NET)

    header = [
        "* LVS reference netlist for bandgap_top -- GENERATED, do not edit.",
        "*",
        "* Produced by layout/lvs/make_reference.py from",
        "* design/netlist/bandgap_top.spice. See that script's docstring for the",
        "* seven mechanical transformations applied and why each one is a",
        "* klt-extraction-deck capability consequence rather than a design",
        "* simplification.",
        "*",
        f"* drawn trim code : {trim_code}",
        f"* MOS devices     : {counts['nfet']} nfet + {counts['pfet']} pfet "
        f"({counts['dummy']} of them edge dummies)",
        "",
        f".SUBCKT {TOP} " + " ".join(pins),
    ]
    body = sorted(lines)
    return "\n".join(header + body + [".ENDS " + TOP, ""]), {
        "counts": counts,
        "pins": pins,
        "nets": sorted(used_nets),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        default=str(REPO_ROOT / "layout" / "lvs" / "bandgap_top.ref.spice"),
        help="output SPICE path",
    )
    parser.add_argument(
        "--trim-code",
        type=int,
        default=plan_mod.DRAWN_TRIM_CODE,
        help="trim code the layout's metal strap option is drawn for",
    )
    args = parser.parse_args()

    text, info = build_reference(args.trim_code)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    Path(args.output).write_text(text)
    print(f"wrote {args.output}")
    print(f"  devices : {info['counts']}")
    print(f"  pins    : {' '.join(info['pins'])}")
    print(f"  nets    : {len(info['nets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
