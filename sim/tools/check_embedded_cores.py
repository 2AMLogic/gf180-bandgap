#!/usr/bin/env python3
"""Static check: embedded bandgap_core copies match the canonical core (#227).

Six diagnostic testbenches embed their own copy of bandgap_core (they need
nodes a subcircuit boundary would hide, or ideal/perturbed devices). Those
copies silently go stale whenever the canonical core resizes (DR-0007 did).
This check compares the resistor/BJT realization of each embedded copy
against sim/dut/bandgap_top.spice:

  * XR2: model, width, length            == canonical
  * XQ2: model, multiplier               == canonical (pnp_05p00x05p00 m=4)
  * XQ1/XQ3: model, multiplier           == canonical
  * XR1, explicit realization (R1 -> tn0 + an XXTRIM bandgap_trim instance):
      base length == canonical base R1, and the trim ladder (unit length,
      segment count) == canonical
  * XR1, lumped realization (one device standing in for base R1 + 32 trim
      units): length == LUMPED_R1_LENGTH_U, the value solved against the real
      PDK model by sim/tools/measure_lumped_r1.py. It is deliberately NOT
      the canonical base length (446u) and NOT a sum of lengths.

Pure text, stdlib only, no PDK or ngspice. Exit 0 = in sync.

    python3 sim/tools/check_embedded_cores.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
REPO = SIM.parent
CANONICAL = SIM / "dut" / "bandgap_top.spice"

#: Lumped R1 + 32 trim units length (um), tt/27 C, from measure_lumped_r1.py.
#: Re-solve (and update the inventory note) if canonical base R1, the trim
#: unit, or the PDK resistor model changes.
LUMPED_R1_LENGTH_U = "545.639857"

#: The six embedded-core benches and the realization of R1 each one uses.
BENCHES = {
    "sim/amp-loop-stability/testbench/tb_loop_stability.spice": "lumped",
    "sim/amp-offset-sensitivity/testbench/tb_offset_sensitivity.spice": "lumped",
    "sim/amp-psrr/testbench/tb_psrr.spice": "lumped",
    "sim/bandgap-loop-smoke/testbench/bandgap_loop_smoke.spice": "lumped",
    "sim/core-mirror-sensitivity/testbench/tb_core_mirror_sensitivity.spice": "explicit",
    "sim/core-psrr-ideal-amp/testbench/tb_core_psrr_ideal_amp.spice": "lumped",
}

_DEV = re.compile(r"^(X(?:R1|R2|Q1|Q2|Q3))\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$", re.M)
_LEN = re.compile(r"\br_length=([0-9.]+)u")
_WID = re.compile(r"\br_width=([0-9.]+)u")
_MULT = re.compile(r"\bm=(\d+)")
_UNIT = re.compile(r"^XRU\d+\s+\S+\s+\S+\s+\S+\s+ppolyf_u\s+(.*)$", re.M)


def parse_core(text: str) -> dict:
    """Extract the realization facts of a core netlist (canonical or embedded)."""
    devs = {}
    for m in _DEV.finditer(text):
        name, rest = m.group(1), m.group(6)
        if name.startswith("XR"):
            nodes = (m.group(2), m.group(3), m.group(4))
            model = m.group(5)
        else:
            nodes = (m.group(2), m.group(3), m.group(4))
            model = m.group(5)
        ln, wd, mu = _LEN.search(rest), _WID.search(rest), _MULT.search(rest)
        devs[name] = {
            "model": model,
            "nodes": nodes,
            "length": ln.group(1) if ln else None,
            "width": wd.group(1) if wd else None,
            "m": int(mu.group(1)) if mu else 1,
        }
    units = []
    for m in _UNIT.finditer(text):
        ln = _LEN.search(m.group(1))
        units.append(ln.group(1) if ln else None)
    return {
        "devices": devs,
        "trim_units": units,
        "has_trim_instance": bool(re.search(r"^XXTRIM\s", text, re.M)),
    }


def realization(core: dict) -> str:
    r1 = core["devices"].get("XR1")
    if r1 is None:
        return "missing"
    explicit = r1["nodes"][1] == "tn0" and core["has_trim_instance"]
    return "explicit" if explicit else "lumped"


def check_core(text: str, canon: dict, expected_real: str, lumped_len: str = LUMPED_R1_LENGTH_U) -> list[str]:
    """Return a list of human-readable mismatches (empty = in sync)."""
    core = parse_core(text)
    d, c = core["devices"], canon["devices"]
    errs: list[str] = []
    for name in ("XR2", "XQ1", "XQ2", "XQ3"):
        if name not in d:
            errs.append(f"{name}: missing")
            continue
        for key in ("model", "m") + (("width", "length") if name == "XR2" else ()):
            if d[name][key] != c[name][key]:
                errs.append(f"{name}.{key}: {d[name][key]!r} != canonical {c[name][key]!r}")
    got = realization(core)
    if got != expected_real:
        errs.append(f"XR1 realization is {got}, expected {expected_real}")
    r1 = d.get("XR1")
    if r1 is None:
        errs.append("XR1: missing")
    else:
        if r1["model"] != c["XR1"]["model"] or r1["width"] != c["XR1"]["width"] or r1["m"] != c["XR1"]["m"]:
            errs.append("XR1: model/width/m differ from canonical")
        if got == "explicit":
            if r1["length"] != c["XR1"]["length"]:
                errs.append(f"XR1.length (base): {r1['length']} != canonical {c['XR1']['length']}")
            if core["trim_units"] != canon["trim_units"]:
                errs.append(
                    f"trim ladder: {len(core['trim_units'])} units "
                    f"(first {core['trim_units'][:1]}) != canonical {len(canon['trim_units'])} "
                    f"(first {canon['trim_units'][:1]})"
                )
        elif got == "lumped" and r1["length"] != lumped_len:
            errs.append(f"XR1.length (lumped): {r1['length']} != solved {lumped_len} (see measure_lumped_r1.py)")
    return errs


def main() -> int:
    canon = parse_core(CANONICAL.read_text())
    failed = 0
    for rel, expected in BENCHES.items():
        errs = check_core((REPO / rel).read_text(), canon, expected)
        status = "ok" if not errs else "STALE"
        print(f"{status:5s} {rel} [{expected}]")
        for e in errs:
            print(f"        - {e}")
        failed += bool(errs)
    print(f"{len(BENCHES) - failed}/{len(BENCHES)} embedded cores in sync with {CANONICAL.relative_to(REPO)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
