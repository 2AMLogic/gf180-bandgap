#!/usr/bin/env python3
"""Turn a ``klt extract --parasitics`` report into a ``sim/dut``-ready netlist.

    python3 layout/netlist/mk_extracted_dut.py \
        --extract layout/netlist/reports/bandgap_top/<rid>.extract.json \
        --lvs     layout/lvs/reports/bandgap_top/<rid>.lvs.json \
        -o        layout/netlist/bandgap_top_extracted.spice

``klt extract``'s own SPICE output is a *topology* netlist, not a simulatable
deck: device cards carry the extraction deck's class tokens (``bjt``,
``ppolyf_u``, ``cap_mim_2f0_m4m5_noshield``) rather than callable gf180mcu
subcircuits, nets are anonymous ``$<n>`` names escaped with backslashes that
ngspice's ``$``-comment rule mangles, and three whole classes of terminal
(MOS well/substrate bodies, bipolar bases, MiM plates) sit on layers the
deck's connectivity stack does not model, so they come out floating.

This script performs the conversion **explicitly and auditably**: every
transform it applies is one of the numbered entries in ``TRANSFORMS`` below,
each one is echoed into the generated file's header, and every net-level
back-annotation is *asserted* against the extracted structure before it is
applied (a back-annotation whose precondition no longer holds is a hard
error, not a silent no-op). That is the whole point: the resulting netlist is
a post-layout artifact whose every departure from what the extractor
literally measured is written down where a reader of the evidence records can
audit it, per CLAUDE.md's "verification is the product".

What is **measured** (i.e. carried through unchanged from the layout):

* every device's existence, class and connectivity on the deck's
  Poly2/COMP/Contact/Metal1..Metal5/Via1..Via4 stack -- including the drawn
  finger decomposition (81 discrete MOS fingers, not the schematic's ``nf``
  multipliers) and the drawn PNP decomposition (8 discrete 5x5 units);
* every resistor's drawn ``r_length``/``r_width`` from its marker geometry;
* the MiM cap's drawn plate area;
* per-net first-order lumped RC parasitics (``klt extract --parasitics``).

What is **back-annotated** (asserted from the schematic because the deck
cannot see it) is listed in ``BACK_ANNOTATIONS`` and reproduced in the
generated header. Nothing else is invented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Drawn geometry this repo's own layout generator owns.
#
# generate.draw_mos draws every MOS finger on its *own* COMP island as
# ``2 * SD_COL + L`` wide by ``W`` tall -- so each extracted finger has two
# full, unshared source/drain columns of exactly SD_COL. That makes the
# junction area/perimeter of an extracted finger exact drawn geometry rather
# than an assumption; see TRANSFORMS entry T6.
# --------------------------------------------------------------------------- #
SD_COL_UM = 0.9  # generate.SD_COL = 900 nm

MOS_MODELS = {"nfet": "nfet_03v3", "pfet": "pfet_03v3"}
RES_MODELS = {"ppolyf_u": "ppolyf_u", "ppolyf_u_1k": "ppolyf_u_1k"}
CAP_MODEL = "cap_mim_2f0_m4m5_noshield"

# The layout draws every PNP as a 5 um x 5 um unit cell (plan.pnp_size); the
# schematic's 10x10 device is drawn as four such units in parallel. AE is what
# the extractor measures, so bind on it rather than on a name.
PNP_BY_AE_UM2 = {25.0: "pnp_05p00x05p00", 100.0: "pnp_10p00x10p00"}

TRANSFORMS = [
    (
        "T1",
        "Net names: the extractor's anonymous `$<n>` labels are replaced by the "
        "schematic-side names `klt lvs` paired them with (its "
        "`net_correspondence` table), lowercased. Nets with no pairing keep a "
        "mechanical `x<n>` name. This is a rename only -- no net is merged or "
        "split by it.",
    ),
    (
        "T2",
        "Escaping: ngspice treats a space-delimited `$` as an end-of-line "
        "comment, so KLayout's `\\$<n>` node spelling would truncate device "
        "cards. T1's rename removes every `$` from the deck.",
    ),
    (
        "T3",
        "MOS cards: `X<n> d g s b nfet|pfet L=..U W=..U` is rebound to the "
        "gf180mcu `nfet_03v3`/`pfet_03v3` subcircuit with `nf=1 m=1` -- each "
        "extracted device is one drawn finger, so the schematic's `nf` "
        "multiplier is already spent as real, separately-extracted geometry.",
    ),
    (
        "T4",
        "Resistor cards: `R<n> a b w <ohms> ppolyf_u[_1k]` -- a bare, linear, "
        "value-only card the extraction engine writes -- is rebound to the "
        "gf180mcu `ppolyf_u`/`ppolyf_u_1k` subcircuit with the *drawn* "
        "`r_length`/`r_width` the extractor measured off the marker geometry. "
        "This restores the PDK model's own temperature coefficient and "
        "mismatch statistics, which a bare ohms value has none of.",
    ),
    (
        "T5",
        "Bipolar cards: `Q<n> c b e bjt AE=..` is rebound to the gf180mcu "
        "`pnp_<WxL>` subcircuit selected by the extractor's own measured `AE` "
        "(25 um^2 -> pnp_05p00x05p00). Each drawn unit stays a separate "
        "device; the schematic's 10x10 PNP is four parallel drawn 5x5 units.",
    ),
    (
        "T6",
        "MOS junction geometry: the extractor emits no `AS/AD/PS/PD` (a stated "
        "scope limit of its PDK-model binding), which would leave every "
        "source/drain junction capacitance at zero. They are recomputed from "
        "*drawn* geometry: `generate.draw_mos` gives each finger its own COMP "
        "island with two unshared %.1f um source/drain columns, so "
        "AS=AD=W*%.1fu and PS=PD=2*(W+%.1fu) exactly. `NRS/NRD` are left at "
        "the PDK default (0): the drawn contact columns fill the whole "
        "diffusion width, so sheet-resistance-to-contact is negligible."
        % (SD_COL_UM, SD_COL_UM, SD_COL_UM),
    ),
    (
        "T7",
        "MiM cap card: `C<n> a b <farads> cap_mim_...` is rebound to the "
        "gf180mcu `cap_mim_2f0_m4m5_noshield` subcircuit with the drawn plate "
        "dimensions (from the extractor's measured plate area), restoring the "
        "PDK model's voltage/temperature coefficients and leakage.",
    ),
    (
        "T8",
        "Parasitics: `klt extract --parasitics`'s per-net first-order lumped "
        "RC (net -> R -> internal node -> C -> substrate) is carried through "
        "verbatim, with T1's names applied.",
    ),
    (
        "T9",
        "Pin list: the extracted top cell's `vdd vref vss vsubs` is emitted as "
        "`bandgap_top vdd vss vref` to match `sim/dut/README.md`'s three-pin "
        "convention, with `vsubs` aliased per BA1 below.",
    ),
]


class Aliaser:
    """Applies, and audits, the schematic-asserted net merges (BA1..BA4)."""

    def __init__(self) -> None:
        self.alias: dict[str, str] = {}
        self.log: list[str] = []

    def add(self, src: str, dst: str, reason_key: str) -> None:
        self.alias[src] = dst
        self.log.append(f"{reason_key}: {src} -> {dst}")

    def __call__(self, net: str) -> str:
        return self.alias.get(net, net)


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def _sanitize(name: str) -> str:
    """A SPICE-safe node/instance token: no `$`, no backslash, no spaces."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name.lstrip("$")).lower()


def net_name_map(extract: dict, lvs: dict | None) -> dict[str, str]:
    """T1/T2: `$<n>` -> the schematic-side name `klt lvs` paired it with."""
    mapping: dict[str, str] = {}
    if lvs is not None:
        for entry in lvs.get("net_correspondence", []):
            layout, reference = entry.get("layout"), entry.get("reference")
            if layout and reference:
                mapping[layout] = _sanitize(reference)
    for net in extract["nets"]:
        name = net["name"]
        if name not in mapping:
            mapping[name] = _sanitize(name) if name.startswith("$") else name
    # Pins keep their own spelling regardless of what LVS paired them with.
    for pin in ("vdd", "vss", "vref", "vsubs"):
        mapping[pin] = pin
    return mapping


def build_back_annotations(extract: dict, names: dict[str, str]) -> Aliaser:
    """The four schematic-asserted merges, each asserted before it is applied.

    Every one of these exists because a *terminal region* of a recognised
    device sits on a layer the extraction deck's connectivity stack does not
    carry (Nwell, the deck-synthesised substrate, or a MiM plate), so the
    extractor gives that terminal a private node instead of the net the layout
    physically routes it to. They are not layout corrections: three of the
    four are pure tool-coverage gaps, and the fourth (BA4) is a layout defect
    already tracked in its own right -- see the module docstring and
    layout/netlist/README.md.
    """
    aliaser = Aliaser()

    # -- degree bookkeeping, used by every assertion below.
    degree: dict[str, list[tuple[str, str, str]]] = {}
    for dev in extract["devices"]:
        for terminal, net in dev["nets"].items():
            degree.setdefault(net, []).append((dev["name"], dev["class"], terminal))

    # BA1 -- substrate. The deck synthesises a `vsubs` net for every NMOS/PNP
    # bulk terminal because gf180mcu draws no distinct p-substrate tap layer
    # it can key on (`klt lvs` reports this itself, as
    # `device.body_unverified`). The schematic ties every NMOS bulk and every
    # PNP collector to `vss`, and the drawn guard ring is a Pplus/COMP ring on
    # the `vss` rail, so the substrate *is* `vss` in this block.
    assert "vsubs" in degree, "expected a deck-synthesised vsubs net"
    aliaser.add("vsubs", "vss", "BA1")

    # BA2 -- PMOS well. Same class of gap on the other side: the deck has no
    # well-tap layer, so all 47 PMOS bodies land on one anonymous well net
    # that reaches nothing else. The schematic ties every PMOS bulk to `vdd`.
    well_nets = {
        net
        for net, users in degree.items()
        if users
        and all(cls == "pfet" and term == "b" for _, cls, term in users)
    }
    assert len(well_nets) == 1, f"expected exactly one anonymous PMOS well net, got {well_nets}"
    aliaser.add(next(iter(well_nets)), "vdd", "BA2")

    # BA3 -- bipolar bases. A recognised `bjt`'s base region is the Nwell
    # layer, which is not one of the deck's connectivity metals, so every
    # drawn unit's base is a private node reaching nothing -- the exact
    # capacitor-plate gap klayout-tools#314 fixed for `CapacitorDevice`, still
    # open for `BipolarDevice`. The layout draws an Nplus base-tie ring on the
    # `vss` rail around every unit (generate.draw_pnp), and the schematic ties
    # every PNP base to `vss`.
    base_nets = {
        net
        for net, users in degree.items()
        if users and all(cls == "bjt" and term == "b" for _, cls, term in users)
    }
    n_bjt = sum(1 for d in extract["devices"] if d["class"] == "bjt")
    assert len(base_nets) == n_bjt, (
        f"expected one isolated base net per drawn PNP unit ({n_bjt}), got {len(base_nets)}"
    )
    for net in sorted(base_nets):
        aliaser.add(net, "vss", "BA3")

    # BA4 -- MiM cap top plate. Unlike BA1..BA3 this one is *not* purely a
    # tool gap any more. klayout-tools#314 joined recognised plate nets to the
    # connectivity stack, and it works: this cap's bottom plate now extracts
    # on the real `vdd` net. The top plate does not, because the drawn Via4
    # that carries `fb` off it lands on a routing tab deliberately kept
    # outside `CAP_MK`/`MIM_L_MK` -- i.e. outside the region the deck
    # recognises as the plate -- a shape drawn as a workaround for the very
    # limitation #314 has since removed, and one already known to be
    # non-manufacturable (gf180-bandgap#82: zero bottom-plate overlap, against
    # MIMTM.2/MIMTM.3). The schematic's `XCC vdd out ...` puts this cap
    # between `vdd` and the amp output (`fb` at the top level), and that is
    # the circuit the layout is trying to be, so the run is done against it --
    # loudly, here and in every record's provenance note.
    cap_devs = [d for d in extract["devices"] if d["class"] == CAP_MODEL]
    assert len(cap_devs) == 1, f"expected exactly one MiM cap, got {len(cap_devs)}"
    cap = cap_devs[0]
    plates = {t: n for t, n in cap["nets"].items()}
    floating = [n for n in plates.values() if len(degree[n]) == 1]
    assert len(floating) == 1, (
        "expected exactly one isolated MiM plate net (the fb top plate); got "
        f"{floating} -- if this is now empty the layout's top-plate contact "
        "extracts for real and BA4 must be deleted, not adjusted"
    )
    assert "vdd" in plates.values(), (
        "expected the MiM bottom plate to extract on the real vdd net "
        "(klayout-tools#314); got " + repr(plates)
    )
    fb = names.get("$12")
    assert fb == "fb", f"expected an extracted net paired with schematic FB, got {fb!r}"
    aliaser.add(floating[0], "$12", "BA4")

    return aliaser


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def emit(
    extract: dict, lvs: dict | None, flat: bool = False
) -> tuple[list[str], Aliaser, dict[str, str]]:
    names = net_name_map(extract, lvs)
    aliaser = build_back_annotations(extract, names)

    def net(raw: str) -> str:
        return names[aliaser(raw)]

    lines: list[str] = (
        [
            "* FLAT form: cards at deck level, no `.subckt bandgap_top` wrapper --",
            "* for a bench that flattens its DUT instead of instantiating it.",
            "",
        ]
        if flat
        else [".subckt bandgap_top vdd vss vref", ""]
    )
    counts: dict[str, int] = {}

    for dev in sorted(extract["devices"], key=lambda d: (d["class"], d["name"])):
        cls, name, nets, params = dev["class"], dev["name"], dev["nets"], dev["params"]
        counts[cls] = counts.get(cls, 0) + 1
        inst = _sanitize(name)
        if cls in MOS_MODELS:  # T3 + T6
            w, length = params["w_um"], params["l_um"]
            area = w * SD_COL_UM
            perim = 2 * (w + SD_COL_UM)
            lines.append(
                f"XM{inst} {net(nets['d'])} {net(nets['g'])} {net(nets['s'])} "
                f"{net(nets['b'])} {MOS_MODELS[cls]} "
                f"L={_fmt(length)}u W={_fmt(w)}u nf=1 "
                f"ad={_fmt(area)}p as={_fmt(area)}p "
                f"pd={_fmt(perim)}u ps={_fmt(perim)}u m=1"
            )
        elif cls in RES_MODELS:  # T4
            lines.append(
                f"XR{inst} {net(nets['a'])} {net(nets['b'])} {net(nets['w'])} "
                f"{RES_MODELS[cls]} r_width={_fmt(params['w_um'])}u "
                f"r_length={_fmt(params['l_um'])}u m=1"
            )
        elif cls == "bjt":  # T5
            ae = _bjt_ae_um2(extract, name)
            model = PNP_BY_AE_UM2.get(round(ae, 3))
            assert model, f"no gf180mcu PNP bound for a drawn emitter area of {ae} um^2"
            lines.append(
                f"XQ{inst} {net(nets['c'])} {net(nets['b'])} {net(nets['e'])} {model} m=1"
            )
        elif cls == CAP_MODEL:  # T7
            side = math.sqrt(params["area_um2"])
            lines.append(
                f"XC{inst} {net(nets['a'])} {net(nets['b'])} {CAP_MODEL} "
                f"c_width={_fmt(side)}u c_length={_fmt(side)}u m=1"
            )
        else:
            raise SystemExit(f"unhandled extracted device class: {cls}")

    lines += ["", "* T8: per-net first-order lumped RC parasitics (klt extract --parasitics)"]
    for entry in extract["parasitics"]["nets"]:
        raw = entry["net"]
        node = net(raw)
        internal = f"{node}__par"
        lines.append(f"R{_sanitize(raw)}_par {node} {internal} {_fmt(entry['resistance_ohm'])}")
        lines.append(
            f"C{_sanitize(raw)}_par {internal} {net('vsubs')} "
            f"{_fmt(entry['capacitance_ff'] * 1e-15)}"
        )

    if not flat:
        lines += ["", ".ends bandgap_top"]
    return lines, aliaser, counts


def _bjt_ae_um2(extract: dict, name: str) -> float:
    """The extractor reports AE on the SPICE card, not in the JSON params."""
    return extract.setdefault("_ae_cache", {}).get(name, 25.0)


def parse_ae(spice_path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in spice_path.read_text().splitlines():
        m = re.match(r"^Q\\?\$?(\S+)\s+.*\bAE=([0-9.eE+-]+)([PUNpun]?)", line)
        if m:
            scale = {"P": 1e-12, "U": 1e-6, "N": 1e-9, "": 1.0}[m.group(3).upper()]
            out["$" + m.group(1)] = float(m.group(2)) * scale * 1e12  # -> um^2
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, required=True, help="<rid>.extract.json")
    parser.add_argument("--spice", type=Path, help="<rid>.extracted.spice (default: alongside)")
    parser.add_argument("--lvs", type=Path, help="<rid>.lvs.json, for net naming (T1)")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--flat",
        action="store_true",
        help="emit the cards at deck level with no `.subckt bandgap_top` wrapper, "
        "for a bench that flattens its DUT instead of instantiating it (this "
        "repo: sim/mc-untrimmed, whose `.ic` seeds name top-level nodes)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if the committed output has drifted",
    )
    args = parser.parse_args()
    for attr in ("extract", "spice", "lvs", "output"):
        value = getattr(args, attr)
        if value is not None:
            setattr(args, attr, value.resolve())

    extract = json.loads(args.extract.read_text())
    spice = args.spice or args.extract.with_suffix("").with_suffix(".extracted.spice")
    extract["_ae_cache"] = parse_ae(spice)
    lvs = json.loads(args.lvs.read_text()) if args.lvs else None

    lines, aliaser, counts = emit(extract, lvs, flat=args.flat)

    header = [
        "* Post-layout EXTRACTED DUT netlist -- GENERATED, do not edit by hand.",
        "*",
        f"* extract report : {args.extract.relative_to(REPO_ROOT)}",
        f"* extracted spice: {spice.relative_to(REPO_ROOT)}",
        f"* lvs report     : {args.lvs.relative_to(REPO_ROOT) if args.lvs else '(none)'}",
        f"* layout gds     : {extract['file']}",
        f"* extraction deck: {extract['deck']}  (klt extract --parasitics)",
        f"* pdk            : {extract['pdk']['variant']} {extract['pdk']['version']}",
        f"* devices        : {extract['device_count']} {extract['device_counts']}",
        "*   parasitics    : "
        f"{extract['parasitics']['r_count']} R / {extract['parasitics']['c_count']} C, "
        f"{extract['parasitics']['total_resistance_ohm']:.1f} ohm and "
        f"{extract['parasitics']['total_capacitance_ff']:.1f} fF total",
        "* regenerate     : python3 layout/netlist/mk_extracted_dut.py"
        f" --extract {args.extract.relative_to(REPO_ROOT)}"
        f" --lvs {args.lvs.relative_to(REPO_ROOT) if args.lvs else 'NONE'}"
        f"{' --flat' if args.flat else ''}"
        f" -o {args.output.relative_to(REPO_ROOT)}",
        "*",
        "* Provenance class is derived from the path by sim/dut: a netlist under",
        "* layout/ reports itself as `Netlist provenance: extracted`.",
        "*",
        "* ------------------------------------------------------------------",
        "* Mechanical transforms applied to the extractor's own output",
        "* ------------------------------------------------------------------",
    ]
    for key, text in TRANSFORMS:
        wrapped = _wrap(text, 68)
        header.append(f"* {key}. {wrapped[0]}")
        header += [f"*     {line}" for line in wrapped[1:]]
    header += [
        "*",
        "* ------------------------------------------------------------------",
        "* Back-annotated nets: terminals the extraction deck cannot resolve",
        "* ------------------------------------------------------------------",
        "* BA1  substrate `vsubs` -> `vss`      (deck has no p-substrate tap layer)",
        "* BA2  PMOS well net    -> `vdd`      (deck has no well-tap layer)",
        "* BA3  8 PNP base nets  -> `vss`      (Nwell is not a connectivity metal;",
        "*      the capacitor-plate gap klayout-tools#314 fixed, still open for",
        "*      BipolarDevice -- filed upstream, see layout/netlist/README.md)",
        "* BA4  MiM cap top plate -> `fb`      (the drawn Via4 lands on a routing",
        "*      tab outside CAP_MK, so the deck does not see the contact; that tab",
        "*      is also non-manufacturable per gf180-bandgap#82. The BOTTOM plate",
        "*      extracts on the real `vdd` net with no help, so #314's join does",
        "*      work here -- this half is a layout defect, not a tool gap.)",
        "*",
        "* Applied merges (source -> target, in extractor net names):",
    ]
    header += [f"*   {entry}" for entry in aliaser.log]
    header += [
        "*",
        "* Everything else -- device existence, class, connectivity, drawn",
        "* resistor L/W, drawn plate area, drawn finger and PNP-unit counts, and",
        "* the per-net RC parasitics -- is measured, not asserted.",
        "",
    ]

    body = "\n".join(header + lines) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    body = body.replace(
        "* Provenance class is derived",
        f"* sha256 (this file, sans this line): {digest[:32]}\n* Provenance class is derived",
        1,
    )

    if args.check:
        if not args.output.exists() or args.output.read_text() != body:
            print(f"error: {args.output} is stale; re-run without --check")
            return 1
        print(f"ok: {args.output} matches the committed extraction report")
        return 0

    args.output.write_text(body)
    print(f"wrote {args.output.relative_to(REPO_ROOT)}")
    print(f"  devices      : {sum(counts.values())} {counts}")
    print(f"  back-annotated: {len(aliaser.log)} nets")
    return 0


def _wrap(text: str, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        out.append(cur)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
