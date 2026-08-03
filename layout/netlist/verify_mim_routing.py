#!/usr/bin/env python3
"""Prove the compensation MiM cap's plates are physically wired to ``vdd``/``fb``.

    uv run --with klayout python3 layout/netlist/verify_mim_routing.py

#17's Test Plan requires confirming "a MIM cap with plates physically wired to
``vdd``/``fb`` (not just recognised as a device)" **before** trusting any
downstream bench result -- and requires doing it by layer inspection rather
than by an LVS delta, because ``klt extract``/``klt lvs`` cannot confirm that
connection themselves for the top plate.

Two independent checks, both run here:

**Check A -- geometry (the link no tool models).** ``klt``'s gf180mcu deck
recognises the cap's top plate as ``FuseTop & CAP_MK & MIM_L_MK`` and joins
*that region* to the metal stack through a ``Via4`` landing on it
(klayout-tools#314). This layout's ``Via4`` deliberately lands one plate-width
to the right, on a ``FuseTop`` routing tab held *outside* ``CAP_MK`` -- so the
deck sees plate and tab as unrelated, and the top plate extracts isolated. But
plate and tab are drawn as two abutting boxes on the *same layer*: physically
one piece of metal. This check merges the ``FuseTop`` shapes and asserts that
the recognised-plate region and the ``Via4`` landing sit inside **one**
polygon -- i.e. that the only link in the ``fb`` chain no tool models is real.

**Check B -- everything downstream of the tab, by the tool.** Everything from
the ``Via4`` onwards *is* ordinary routing the extraction deck models. So this
check re-runs the extraction on a scratch copy of the GDS whose ``CAP_MK`` /
``MIM_L_MK`` boxes are widened to also cover the tab. That makes the deck
recognise tab-and-plate as one plate, its ``Via4`` as an on-plate via, and
klayout-tools#314's join then applies. If the drawn
tab -> Via4 -> Metal5 -> Via4 -> Metal4 pad -> Via3 -> Metal3 -> Via2 ->
Metal2 -> Via1 -> Metal1 chain really does reach the ``fb`` rail, the top
plate must now extract *on* ``fb`` -- which is checked by running ``klt lvs``
against the committed reference netlist with the cap's top-plate terminal
rewritten to ``fb``. A ``match`` verdict is the proof; anything else means the
chain does not reach ``fb``.

Neither check touches ``layout/bandgap_top/bandgap_top.gds``: the widened-marker
layout is written to a temporary directory and thrown away. The committed
layout keeps the narrow ``CAP_MK`` (and so the isolated top plate) because
widening it would change the recognised plate area -- the capacitance the
extracted netlist reports.

Exit status is 0 only if both checks pass.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import klayout.db as kdb

REPO_ROOT = Path(__file__).resolve().parents[2]
GDS = REPO_ROOT / "layout" / "bandgap_top" / "bandgap_top.gds"
REFERENCE = REPO_ROOT / "layout" / "lvs" / "bandgap_top.ref.spice"

FUSETOP = (75, 0)
CAP_MK = (117, 5)
MIM_L_MK = (117, 10)
METAL4 = (46, 0)
VIA4 = (41, 0)

CAP_CLASS = "cap_mim_2f0_m4m5_noshield"


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
        f"{plate_m4.area() * dbu * dbu:.1f} um^2 (its own via stack is deck-visible; "
        "see check B's baseline)"
    )
    return True


def _widened_gds(dest: Path) -> None:
    """A scratch copy whose CAP_MK/MIM_L_MK also cover the FuseTop routing tab."""
    layout = kdb.Layout()
    layout.read(str(GDS))
    cell = layout.top_cell()
    fusetop = _region(layout, cell, FUSETOP).merged()
    cap_mk = _region(layout, cell, CAP_MK).merged()
    carrier = fusetop.interacting(cap_mk)
    box = carrier.bbox().enlarged(400, 400)
    for spec in (CAP_MK, MIM_L_MK):
        index = layout.layer(*spec)
        cell.shapes(index).insert(box)
    layout.write(str(dest))


def _run(cmd: list[str], cwd: Path) -> dict:
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if out.returncode not in (0, 1):  # 1 = "mismatch", still a real report
        print(out.stdout, out.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return json.loads(out.stdout)


def check_b_extraction() -> bool:
    """With the tab inside CAP_MK, the top plate must extract on `fb`."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        gds = tmp / "bandgap_top.gds"
        _widened_gds(gds)

        extract = _run(
            [
                "klt", "extract", str(gds), "--deck", "gf180mcu",
                "--top", "bandgap_top", "--pdk", "gf180mcuD",
                "--format", "json", "-o", str(tmp / "widened.spice"),
            ],
            tmp,
        )
        caps = [d for d in extract["devices"] if d["class"] == CAP_CLASS]
        if len(caps) != 1:
            print(f"FAIL B: expected 1 recognised cap in the widened layout, got {len(caps)}")
            return False
        farads = caps[0]["params"]["area_um2"] * 2.0e-15

        # The committed reference, with the cap's top plate moved to `fb` and
        # its value taken from the widened layout's own measured plate area.
        reference = REFERENCE.read_text()
        reference, n = re.subn(
            r"^(C\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+" + re.escape(CAP_CLASS) + r"\s*$",
            lambda m: f"{m.group(1)} {m.group(2)} fb {farads:.6e} {CAP_CLASS}",
            reference,
            flags=re.MULTILINE,
        )
        if n != 1:
            print(f"FAIL B: expected 1 cap card in the reference netlist, rewrote {n}")
            return False
        ref_path = tmp / "reference.spice"
        ref_path.write_text(reference)

        request = {
            "layout": {"file": str(gds), "deck": "gf180mcu", "top": "bandgap_top"},
            "reference": {"netlist": str(ref_path), "top": "bandgap_top"},
        }
        lvs = _run(["klt", "lvs", json.dumps(request), "--format", "json"], tmp)

    status = lvs["status"]
    counts = lvs.get("counts", {})
    devices = counts.get("devices", {})
    nets = counts.get("nets", {})
    print(
        f"{'PASS' if status == 'match' else 'FAIL'} B: widened-marker LVS status={status} "
        f"devices={devices.get('matched')}/{devices.get('layout')} "
        f"nets={nets.get('matched')}/{nets.get('layout')} "
        f"(reference cap top plate rewritten to `fb`)"
    )
    if status != "match":
        for entry in lvs.get("mismatches", []):
            if entry.get("severity") == "error":
                print("   ", entry["category"], entry["description"])
    return status == "match"


def main() -> int:
    if shutil.which("klt") is None:
        print("klt not on PATH -- see layout/README.md for install instructions")
        return 2
    ok_a = check_a_geometry()
    ok_b = check_b_extraction()
    print()
    print("MiM plate routing:", "VERIFIED" if (ok_a and ok_b) else "NOT VERIFIED")
    return 0 if (ok_a and ok_b) else 1


if __name__ == "__main__":
    sys.exit(main())
