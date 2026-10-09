#!/usr/bin/env python3
"""Solve and verify the lumped-R1 length for the embedded diagnostic cores (#227).

Several diagnostic benches collapse the output-branch summing resistor R1 and
the 63-segment bandgap_trim ladder (at its default code 32, i.e. R1 + 32 trim
units in series) into ONE ppolyf_u device. ppolyf_u is a compound model
(R = a*L + b: a length term plus a per-device overhead), so the lumped device
pays the overhead once where the real stack pays it 33 times, and the lumped
length is NOT base_R1_length + 32*unit_length. This tool measures the real PDK
model directly (two-terminal DC .op, R = V/I) and:

  1. builds the reference stack exactly as sim/dut/bandgap_top.spice does
     (R1 base + the bandgap_trim subckt extracted verbatim from that file, at
     its trim_code=32 default),
  2. measures two lumped lengths and solves R(L) = R_reference (linear in L at
     fixed W for this model),
  3. rounds to the 1e-6 u resolution used in the netlists and re-measures the
     rounded length against the reference over -40/27/125 C and two bias
     conditions, reporting the error in ppm.

Single ngspice process per invocation (a handful of DC operating points); it
is a measurement aid, not a corner/Monte Carlo sweep. Only the corner given by
--corner is exercised (default res_typical).

    python3 sim/tools/measure_lumped_r1.py            # solve + verify
    python3 sim/tools/measure_lumped_r1.py --check-length 560.0   # verify only

Needs ngspice and the gf180mcu PDK (sim/run_corners.py --check-env).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

TOP = SIM / "dut" / "bandgap_top.spice"
TEMPS = (-40.0, 27.0, 125.0)
#: (label, V at the bottom terminal, V across the stack). The substrate is
#: always 0 V. "lowbias" mirrors the 50 mV two-terminal check the startup
#: bench headers describe; "opbias" is near the real operating point (R1 sits
#: between the e3 node ~0.7 V and vref ~1.2 V).
BIASES = (("lowbias", 0.0, 0.05), ("opbias", 0.7, 0.5))
W = "2u"


def pdk_paths(corner: str) -> tuple[str, str]:
    from harness import pdk as pdk_mod  # type: ignore

    p = pdk_mod.find_pdk()
    print(f"PDK {p.variant} open_pdks {p.version} ({p.path})")
    return str(p.design_include), str(p.model_lib)


def trim_subckt() -> str:
    text = TOP.read_text()
    m = re.search(r"^\.subckt bandgap_trim .*?^\.ends[^\n]*$", text, re.S | re.M)
    if not m:
        raise SystemExit(f"no bandgap_trim subckt in {TOP}")
    return m.group(0)


def base_r1_length() -> str:
    m = re.search(r"^XR1 e3 tn0 vss ppolyf_u r_width=2u r_length=(\S+) ", TOP.read_text(), re.M)
    if not m:
        raise SystemExit(f"no XR1 in {TOP}")
    return m.group(1)


def deck(design: str, models: str, corner: str, lumped: list[str], base: str) -> str:
    """One deck: reference stack + one branch per lumped length.

    Every branch is its own two-terminal path from a top source to a bottom
    source, so each resistance is V/I of that branch alone.
    """
    out = ["* lumped-R1 equivalence (sim/tools/measure_lumped_r1.py, #227)"]
    out.append(f".include {design}")
    out.append(f".lib {models} {corner}")
    out.append(trim_subckt())
    out.append("vsub sub 0 0")
    # reference stack: R1 base + trim ladder (code 32 default)
    out.append(f"XR1ref atop tn0 sub ppolyf_u r_width={W} r_length={base} m=1")
    out.append("XXTRIM tn0 abot sub bandgap_trim")
    out.append("vtop atop 0 0.05")
    out.append("vbot abot 0 0")
    for i, ln in enumerate(lumped):
        out.append(f"XRL{i} ltop{i} lbot{i} sub ppolyf_u r_width={W} r_length={ln}u m=1")
        out.append(f"vltop{i} ltop{i} 0 0.05")
        out.append(f"vlbot{i} lbot{i} 0 0")
    return "\n".join(out)


def control(n_lumped: int, temps, biases) -> str:
    lines = [".control", "set noaskquit"]
    for t in temps:
        for label, vbot, vdrop in biases:
            lines.append(f"option temp={t}")
            lines.append(f"alter vbot dc = {vbot}")
            lines.append(f"alter vtop dc = {vbot + vdrop}")
            for i in range(n_lumped):
                lines.append(f"alter vlbot{i} dc = {vbot}")
                lines.append(f"alter vltop{i} dc = {vbot + vdrop}")
            lines.append("op")
            lines.append(f"echo PT {t} {label} {vdrop} ref $&i(vtop)" + "".join(
                f" L{i} $&i(vltop{i})" for i in range(n_lumped)))
    lines += ["quit", ".endc", ".end"]
    return "\n".join(lines)


def run(design, models, corner, lumped, base, temps, biases):
    text = deck(design, models, corner, lumped, base)
    # control block must precede .end; strip the trailing .end from deck()
    text += "\n" + control(len(lumped), temps, biases) + "\n"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "lumped_r1.cir"
        f.write_text(text)
        proc = subprocess.run(
            ["ngspice", "-b", str(f)], capture_output=True, text=True, timeout=300
        )
    pts = []
    for line in proc.stdout.splitlines():
        if not line.startswith("PT "):
            continue
        tok = line.split()
        t, label, vdrop = float(tok[1]), tok[2], float(tok[3])
        cur = {}
        k = 4
        while k < len(tok):
            cur[tok[k]] = float(tok[k + 1])
            k += 2
        # supply current flows out of the + terminal: i(v) is negative
        res = {key: vdrop / abs(val) for key, val in cur.items()}
        pts.append((t, label, vdrop, res))
    if not pts:
        raise SystemExit("no measurements parsed from ngspice\n" + proc.stdout[-2000:] + proc.stderr[-2000:])
    return pts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corner", default="res_typical")
    ap.add_argument("--check-length", type=float, help="verify this lumped length (um) only")
    args = ap.parse_args()

    design, models = pdk_paths(args.corner)
    base = base_r1_length()
    base_u = float(base.rstrip("u"))
    print(f"base R1 length in {TOP.relative_to(SIM.parent)}: {base}; corner {args.corner}")

    if args.check_length is None:
        # step 1: two probe lengths at tt/27 C, low bias -> linear solve
        l1, l2 = 500.0, 600.0
        pts = run(design, models, args.corner, [f"{l1}", f"{l2}"], base, (27.0,), BIASES[:1])
        _, _, _, r = pts[0]
        r_ref, r1, r2 = r["ref"], r["L0"], r["L1"]
        a = (r2 - r1) / (l2 - l1)
        b = r1 - a * l1
        sol = (r_ref - b) / a
        print(f"R(L) = {a:.6f} ohm/um * L + {b:.3f} ohm (W={W}); R_ref(R1 + 32 units) = {r_ref:.3f} ohm")
        length = round(sol, 6)
        print(f"solved lumped length = {sol:.6f} u -> {length:.6f} u")
    else:
        length = args.check_length

    unit = float(re.search(r"XRU0 .*r_length=(\S+?)u", trim_subckt()).group(1))
    naive = base_u + 32 * unit  # what a length summation would give (wrong)
    pts = run(design, models, args.corner, [f"{length:.6f}", f"{naive:.6f}"], base, TEMPS, BIASES)
    worst = 0.0
    worst_naive = 0.0
    print(f"verification, lumped L = {length:.6f} u vs real stack (R1 base + bandgap_trim @ code 32):")
    for t, label, vdrop, r in pts:
        ppm = (r["L0"] - r["ref"]) / r["ref"] * 1e6
        nppm = (r["L1"] - r["ref"]) / r["ref"] * 1e6
        worst = max(worst, abs(ppm))
        worst_naive = max(worst_naive, abs(nppm))
        print(f"  T={t:6.1f} C {label:8s} V={vdrop:.3f}  R_ref={r['ref']:.3f}  R_lumped={r['L0']:.3f}  err={ppm:+.2f} ppm   naive-sum err={nppm:+.0f} ppm")
    print(f"worst |err| = {worst:.2f} ppm at the solved length; naive length sum {naive:.6f} u "
          f"is off by up to {worst_naive:.0f} ppm (R = a*L + b overhead)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
