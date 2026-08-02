#!/usr/bin/env python3
"""Emit the LVS **reference** netlist for ``bandgap_top``.

``klt lvs`` compares a layout-extracted netlist against a reference netlist.
The reference cannot be ``design/netlist/bandgap_top.spice`` verbatim, because
the extracted side is what ``klt``'s gf180mcu extraction deck can *see*: MOS
(``nfet``/``pfet``), poly resistors (``ppolyf_u`` and the high-sheet-rho
``ppolyf_u_1k``), vertical bipolars (``bjt``) and the MIM capacitor
(``cap_mim_2f0_m4m5_noshield``), each decomposed exactly the way the layout
draws it and parameterised off the drawn marker geometry rather than the
schematic's own device parameters.

So this script mechanically derives the reference from the committed
schematic netlist plus :mod:`plan` (the same module ``generate.py`` draws
from), applying exactly the transformations the extraction deck's own
capabilities and this layout's own drawn decomposition imply — no hand
editing, no per-device fudging:

1. **Flatten** ``design/netlist/bandgap_top.spice``
   (:mod:`layout.bandgap_top.netlist_model`).
2. **Expand each MOS to its drawn finger count** (``plan.fingers``): *n*
   parallel unit devices of ``W/n``, matching the *n* separate gate islands
   the layout draws. Total ``W`` and ``L`` are preserved.
3. **Add the layout's edge dummy devices** (``plan.build_rows``), which are
   real transistors in the layout and so must be real transistors here.
4. **Re-target the MOS body terminals** to the nets the deck actually
   produces: NMOS bodies to the deck's ``vsubs`` global, PMOS bodies to the
   single Nwell net of the contiguous PMOS band.
5. **Emit one ``ppolyf_u`` card per drawn resistor body** — ``core.R1`` and
   ``core.R2`` (each one folded serpentine = one recognised device) and each
   of the 63 trim-ladder unit segments — with ``R`` predicted from the
   *recognised marker area* (``plan.res_body_area_nm2`` /
   ``plan.trim_unit_area_nm2``), which is what the extractor measures.
6. **Emit one ``ppolyf_u_1k`` card for ``startup.RPU``.** Its schematic model
   is ``ppolyf_u_1k`` (high sheet rho); ``generate.py`` marks that body
   ``RES_MK``/``SAB``/``Resistor`` (62/0) — deliberately *not* ``Pplus`` — to
   match the deck's ``ppolyf_u_1k`` recogniser (klayout-tools#299, resolved;
   taken up here as gf180-bandgap#78), so ``R`` is predicted the same way as
   step 5 but at the deck's 1000 Ω/□ (``plan.PPOLYF_U_1K_SHEET_RHO``) instead
   of the base flavour's 350 Ω/□.
7. **Resolve the ideal ``RS0..RS5`` trim straps** at the trim code the layout
   draws its metal strap option for (``plan.DRAWN_TRIM_CODE``). The drawn
   Metal1 straps are derived from these same expressions
   (``plan.trim_strap_spans``), so the two sides short the same chain nodes.
8. **Emit one ``bjt`` card per drawn PNP unit** (the real p+ emitter,
   ``AE = 2.5e-11``). Each unit's Nwell is its own island, so each unit's
   base is its own (unnamed) net — the deck never connects Nwell to Contact.

   **Historical note.** Before klayout-tools#304, the deck recognised a
   bipolar emitter as ``Comp & Nwell & DRC_BJT`` and modelled no implant
   layers, so it could not tell the n+ **base-contact ring** apart from the
   p+ emitter it surrounds: every unit extracted as two bipolars sharing one
   base (Nwell) net. This repo filed that generically upstream as
   klayout-tools#302; klayout-tools#304 (deck commit ``be4b4f82``) resolved
   it on 2026-08-02 by excluding ``Nplus`` from the emitter region, so the
   n+ tie ring no longer extracts as a device. Under the current deck each
   drawn unit extracts as exactly one ``bjt``, which is what this step now
   emits — see gf180-bandgap#84 and ``layout/README.md`` § "Friction filed".
9. **Emit one MIM-capacitor card with two floating plate nets.** The deck
   registers a recognised cap's plates as their own connectivity nodes that
   are *never* joined to the metal stack (``decks.CapacitorDevice``, "Known
   limitation"), so the cap's terminals cannot reach ``vdd``/``fb`` on the
   extracted side no matter how the layout routes them — and since #77 the
   layout *does* route them, with a real via stack (``generate._mim_cap``);
   see ``layout/README.md``.

Every one of those steps is a **tool-capability or drawn-decomposition
consequence**, not a design simplification. What the resulting verdict does
and does not prove is stated in ``layout/README.md``.

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
#: layer, so it cannot derive a real body net. It is also the bulk terminal
#: of every extracted ``ppolyf_u`` (``ResistorDevice.bulk_to_substrate``) and
#: the collector of every extracted ``bjt`` (the deck models no drawn
#: collector layer -- a vertical bipolar's collector *is* the substrate).
SUBSTRATE_NET = "vsubs"

#: Name used for the PMOS band's single Nwell net. The extraction deck never
#: connects Nwell to Contact (doing so would short every device in the well
#: together), so the extracted PMOS body is an unnamed net; the comparer
#: matches it structurally.
NWELL_NET = "nwl"

TOP = "bandgap_top"

#: Device-class names the deck emits, mirrored here so the reference's own
#: SPICE model tokens create identically-named device classes.
RES_CLASS = "ppolyf_u"
RES_1K_CLASS = "ppolyf_u_1k"
BJT_CLASS = "bjt"
CAP_CLASS = "cap_mim_2f0_m4m5_noshield"


def sanitise(net: str) -> str:
    """Hierarchy-safe net name for SPICE (``amp.n1`` -> ``amp_n1``)."""
    return net.replace(".", "_")


def device_name(key: str) -> str:
    return key.replace(".", "_").replace("#", "_")


def _res_ohms(
    area_nm2: int, width_nm: int, sheet_rho: float = plan_mod.PPOLYF_U_SHEET_RHO
) -> float:
    """``sheet_rho * A / W**2`` — KLayout's own resistor value, in ohms.

    ``DeviceExtractorResistor`` recovers ``(L, W)`` from the recognised
    region's area and perimeter and reports ``R = sheet_rho * L / W``; for
    every body this layout draws the recovered ``W`` is the drawn body width,
    so ``L = A / W`` and the value reduces to this expression. ``sheet_rho``
    defaults to the base ``ppolyf_u`` flavour; pass
    ``plan_mod.PPOLYF_U_1K_SHEET_RHO`` for a high-rho (``ResItem.high_rho``)
    body.
    """
    return sheet_rho * area_nm2 / (width_nm * width_nm)


def build_reference(trim_code: int) -> tuple[str, dict]:
    flat, rows = plan_mod.load_plan()
    reduction = netlist_model.reduce_nets(flat, trim_code)

    def net_of(name: str) -> str:
        return sanitise(reduction.get(name, name))

    lines: list[str] = []
    counts = {
        "nfet": 0,
        "pfet": 0,
        "dummy": 0,
        RES_CLASS: 0,
        RES_1K_CLASS: 0,
        BJT_CLASS: 0,
        CAP_CLASS: 0,
    }
    used_nets: set[str] = set()

    def use(*nets: str) -> None:
        used_nets.update(nets)

    for row in rows:
        for item in row.items:
            name = device_name(getattr(item, "key", ""))

            if isinstance(item, plan_mod.MosItem):
                drain = net_of(item.nets["d"])
                gate = net_of(item.nets["g"])
                source = net_of(item.nets["s"])
                body = SUBSTRATE_NET if item.kind == "nfet" else NWELL_NET
                use(drain, gate, source, body)
                lines.append(
                    f"M{name} {drain} {gate} {source} {body} {item.kind} "
                    f"L={item.l_nm / 1000.0:g}U W={item.w_nm / 1000.0:g}U"
                )
                counts[item.kind] += 1
                if item.dummy:
                    counts["dummy"] += 1

            elif isinstance(item, plan_mod.ResItem):
                # Step 6: a high-rho body is marked RES_MK/SAB/Resistor
                # (deliberately not Pplus) to match the deck's ppolyf_u_1k
                # recogniser at 1000 Ω/□; the base flavour matches the
                # ppolyf_u recogniser at 350 Ω/□.
                res_class = RES_1K_CLASS if item.high_rho else RES_CLASS
                sheet_rho = (
                    plan_mod.PPOLYF_U_1K_SHEET_RHO
                    if item.high_rho
                    else plan_mod.PPOLYF_U_SHEET_RHO
                )
                n1, n2 = (net_of(net) for net in item.nets)
                use(n1, n2, SUBSTRATE_NET)
                ohms = _res_ohms(
                    plan_mod.res_body_area_nm2(item), item.width_nm, sheet_rho
                )
                lines.append(
                    f"R{name} {n1} {n2} {SUBSTRATE_NET} {ohms:.6f} {res_class}"
                )
                counts[res_class] += 1

            elif isinstance(item, plan_mod.TrimLadderItem):
                units = [flat.get(path) for path in item.devices]
                nodes = plan_mod.trim_chain_nodes(units)
                ohms = _res_ohms(
                    plan_mod.trim_unit_area_nm2(item), item.unit_width_nm
                )
                for index, unit in enumerate(units):
                    n1 = net_of(nodes[index])
                    n2 = net_of(nodes[index + 1])
                    use(n1, n2, SUBSTRATE_NET)
                    lines.append(
                        f"R{device_name(unit.path)} {n1} {n2} {SUBSTRATE_NET} "
                        f"{ohms:.6f} {RES_CLASS}"
                    )
                    counts[RES_CLASS] += 1

            elif isinstance(item, plan_mod.PnpItem):
                # Step 8: each unit's own Nwell island is its own (unnamed)
                # extracted net -- the deck connects Nwell to nothing. One
                # real p+ emitter extracts per unit (klayout-tools#304).
                base = f"nw_{name}"
                emitter = net_of(item.emitter_net)
                use(base, emitter, SUBSTRATE_NET)
                area_nm2 = plan_mod.pnp_emitter_area_nm2(item)
                lines.append(
                    f"Q{name} {SUBSTRATE_NET} {base} {emitter} "
                    f"{BJT_CLASS} AE={area_nm2 * 1e-18:.6e}"
                )
                counts[BJT_CLASS] += 1

            # TapItem draws no device (pure body/guard contact).

    cap = plan_mod.mim_cap(flat)
    cap_name = device_name(cap.key)
    # Step 9: the plates are their own connectivity nodes on the extracted
    # side, joined to nothing else, so they are their own nets here too.
    plate_top = f"{cap_name}_top"
    plate_bot = f"{cap_name}_bot"
    use(plate_top, plate_bot)
    farads = plan_mod.mim_plate_area_nm2(cap) / 1e6 * plan_mod.MIM_CAP_F_PER_UM2
    lines.append(f"C{cap_name} {plate_bot} {plate_top} {farads:.6e} {CAP_CLASS}")
    counts[CAP_CLASS] += 1

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
        "* design/netlist/bandgap_top.spice + layout/bandgap_top/plan.py. See",
        "* that script's docstring for the nine mechanical transformations",
        "* applied and why each one is a klt-extraction-deck capability (or a",
        "* drawn-decomposition) consequence rather than a design",
        "* simplification.",
        "*",
        f"* drawn trim code : {trim_code}",
        f"* MOS devices     : {counts['nfet']} nfet + {counts['pfet']} pfet "
        f"({counts['dummy']} of them edge dummies)",
        f"* resistors       : {counts[RES_CLASS]} {RES_CLASS} + "
        f"{counts[RES_1K_CLASS]} {RES_1K_CLASS}",
        f"* bipolars        : {counts[BJT_CLASS]} {BJT_CLASS} "
        "(1 per drawn PNP unit -- see the docstring's step 8)",
        f"* capacitors      : {counts[CAP_CLASS]} {CAP_CLASS}",
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
