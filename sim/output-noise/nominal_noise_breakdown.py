#!/usr/bin/env python3
"""Nominal-corner per-device noise-contribution breakdown for output-noise.

Issue #188's scope calls for one thing the `tb.json` single-grid contract
does not express: "at the nominal point (tt/27C/3.30V) additionally capture
ngspice's per-device noise-contribution summary at 1 Hz and 1 kHz and name
the dominant contributors in the record's notes". ngspice only emits that
breakdown for a *single-frequency* `noise` analysis with `pts_per_summary=1`
(a decade/lin sweep with more than one point instead prints a much coarser,
decade-spaced summary) -- a different `analyses` shape than the dense
0.1-10 Hz / 0.1 Hz-100 kHz sweeps `testbench/tb_output_noise.spice` runs for
the actual per-corner measurements. Rather than bolt a second deck shape onto
the manifest every one of the 81 grid points would then pay for, this script
runs it once, at one corner, and writes the result as free text for
`sim/run_corners.py output-noise --notes-file <path>` (`sim/README.md`'s
optional `## Notes` field) to fold into the record.

Reuses `testbench/tb_output_noise.spice` as the netlist fragment (the same
vsup/Xdut/.ic block the per-corner grid uses) so this diagnostic measures
exactly the same circuit, just with a different `.control` body.

Usage:
    python3 sim/output-noise/nominal_noise_breakdown.py
    python3 sim/output-noise/nominal_noise_breakdown.py \
        --dut layout/netlist/bandgap_top_extracted.spice \
        --out /tmp/output-noise-notes-extracted.txt
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness.corners import CORNERS, PvtPoint  # noqa: E402
from harness.pdk import find_pdk  # noqa: E402
from harness.runner import NGSPICE, compose_deck, ngspice_version  # noqa: E402
from harness.testbench import Testbench, resolve_dut  # noqa: E402

NETLIST = HERE / "testbench" / "tb_output_noise.spice"
NOMINAL_VDD = 3.30
NOMINAL_TEMP_C = 27.0

# Single-point noise analyses with pts_per_summary=1: ngspice folds the
# per-device onoise_<instance> breakdown directly into that one plot (see
# the worked examples in the PR description / issue #188 comments) instead
# of only the aggregate onoise_spectrum/onoise_total it prints for a dense
# sweep.
ANALYSES = (
    "op",
    "noise v(vref) vsup lin 1 1 1 1",
    "echo === NOISE_BREAKDOWN_1HZ_START ===",
    "setplot noise1",
    "print all",
    "echo === NOISE_BREAKDOWN_1HZ_END ===",
    "noise v(vref) vsup lin 1 1000 1000 1",
    "echo === NOISE_BREAKDOWN_1KHZ_START ===",
    "setplot noise2",
    "print all",
    "echo === NOISE_BREAKDOWN_1KHZ_END ===",
)

_VEC_RE = re.compile(r"^(onoise[._]\S+)\s*=\s*([-+0-9.eE]+)\s*$")
_TOTAL_RE = re.compile(r"^onoise_spectrum\s*=\s*([-+0-9.eE]+)\s*$")

# Suffixes that split a bare per-device total into its 1/f vs thermal (or,
# for a BJT, its base/collector/emitter resistance) share -- summing these
# alongside the bare entry would double-count.
_SPLIT_SUFFIXES = ("_1overf", "_thermal", "_ib", "_ic", "_rb", "_rc", "_re")
_MOS_SPLIT_LEAVES = {
    "1overf", "id", "igb", "igd", "igs",
    "rbdb", "rbpb", "rbpd", "rbps", "rbsb", "rd", "rg", "rs",
}


def is_bare_total(name: str) -> bool:
    """Is this vector a per-device total, not a further 1/f-vs-thermal split?

    ngspice names a MOSFET's total noise contribution ``onoise.m.<path>.m0``
    (dot-separated) and its shot/thermal-vs-flicker components
    ``onoise.m.<path>.m0.<leaf>``; a BJT's total is ``onoise_q.<path>.q0``
    (underscore-separated) with components ``..._ib``/``_ic``/etc; a
    resistor's total is either ``onoise_r.<path>.rt1``/``rt2`` (the
    macro-modelled ``ppolyf_u`` family splits each device into two halves)
    or a bare ``onoise_r.<path>`` for a primitive ``R`` element -- both
    forms carry ``_1overf``/``_thermal`` components under the same rule.
    """
    if name.startswith("onoise.m."):
        return name.rsplit(".", 1)[-1] not in _MOS_SPLIT_LEAVES
    if name.startswith(("onoise_q.", "onoise_r.")):
        return not name.endswith(_SPLIT_SUFFIXES)
    return False


def device_family(name: str) -> str:
    if name.startswith("onoise.m."):
        return "MOSFET (thermal + flicker, fnoimod=1 BSIM4 sections)"
    if name.startswith("onoise_q."):
        return "BJT (shot + thermal, kf/af sections)"
    if name.startswith("onoise_r."):
        return "resistor (thermal, ppolyf_u family)"
    return "other"


def block_bucket(name: str) -> str | None:
    """Coarse subcircuit-level bucket, schematic hierarchy only.

    Only meaningful against the hierarchical schematic DUT
    (``xdut.xx1...`` / ``xdut.xx2...`` / ``xdut.xx3...``): the post-layout
    extracted netlist is flattened by extraction (sim/dut/README.md), so no
    instance-path prefix survives to bucket by. Returns ``None`` when the
    path carries no such prefix, so the caller can report per-device-family
    totals only and say why the per-block view is unavailable.
    """
    if ".xxtrim." in name:
        return "trim resistor ladder (bandgap_trim)"
    if ".xx1." in name:
        return "core (PNPs, cascode PMOS mirror array, R1/R2)"
    if ".xx2." in name:
        return "amp (bandgap_amp input pair / bias)"
    if ".xx3." in name:
        return "startup circuit"
    return None


def parse_section(text: str, start_marker: str, end_marker: str) -> tuple[dict[str, float], float]:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    body = text[start:end]
    values: dict[str, float] = {}
    total = None
    for line in body.splitlines():
        m = _TOTAL_RE.match(line.strip())
        if m:
            total = float(m.group(1))
            continue
        m = _VEC_RE.match(line.strip())
        if m:
            values[m.group(1)] = float(m.group(2))
    if total is None:
        raise ValueError(f"no onoise_spectrum total found between {start_marker!r}/{end_marker!r}")
    return values, total


def summarize_section(values: dict[str, float], total: float, top_n: int = 8) -> str:
    """Render one frequency point's breakdown as percent-of-total-power lines.

    ngspice's per-device noise summary (this module's ``ANALYSES``, i.e. a
    single-point ``noise`` analysis with ``pts_per_summary=1``) prints each
    device's own ``onoise_<name>`` bare total alongside the circuit's overall
    ``onoise_spectrum`` -- but empirically (verified against two independent
    hand-built RC networks with known, symmetric, equal-split noise sources:
    N identical resistors each attribute exactly 1/N of total *power*) the
    two do **not** combine linearly. They combine in quadrature: summing
    ``(value_i / total) ** 2`` across every bare device reconstructs 1.0 to
    12 significant figures (verified against this DUT too -- 1.0000000000009
    summed across its 170 bare MOSFET/BJT/resistor entries at 1 Hz). So each
    device's *share of total output-noise power* is ``(value_i / total) ** 2``,
    not ``value_i / total`` -- the latter overcounts by ~2-3x on a circuit
    with several comparably-sized contributors, exactly the "251%" a naive
    linear sum would print here.
    """
    bare = {name: v for name, v in values.items() if is_bare_total(name)}
    total_sq = total * total

    by_family: dict[str, float] = {}
    by_block: dict[str, float] = {}
    have_blocks = False
    for name, v in bare.items():
        power = v * v
        by_family[device_family(name)] = by_family.get(device_family(name), 0.0) + power
        bucket = block_bucket(name)
        if bucket is not None:
            have_blocks = True
            by_block[bucket] = by_block.get(bucket, 0.0) + power

    lines = [f"  Total onoise_spectrum: {total:.6e} V^2/Hz"]
    lines.append("  By device family (share of total output-noise power):")
    for family, power in sorted(by_family.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {power / total_sq * 100:6.2f}%  {family}")

    if have_blocks:
        lines.append("  By subcircuit block (schematic hierarchy):")
        for bucket, power in sorted(by_block.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {power / total_sq * 100:6.2f}%  {bucket}")
    else:
        lines.append(
            "  By subcircuit block: n/a (this DUT's instance hierarchy is flat -- "
            "see layout/netlist/README.md -- so no per-block split survives)."
        )

    lines.append(f"  Top {top_n} individual device contributors:")
    for name, v in sorted(bare.items(), key=lambda kv: -(kv[1] * kv[1]))[:top_n]:
        lines.append(f"    {v * v / total_sq * 100:6.2f}%  {name}")
    return "\n".join(lines)


def run(dut_arg: str) -> str:
    pdk = find_pdk()
    dut_path = resolve_dut(dut_arg, NETLIST.parent)
    tb = Testbench(
        directory=NETLIST.parent,
        name="output-noise-nominal-breakdown",
        netlist=NETLIST,
        dut=dut_path,
        analyses=ANALYSES,
        measure={},
    )
    point = PvtPoint(corner=CORNERS["tt"], temp_c=NOMINAL_TEMP_C, vdd=NOMINAL_VDD)
    deck_text = compose_deck(tb, pdk, point)

    with tempfile.TemporaryDirectory() as tmp:
        deck_path = Path(tmp) / "nominal_breakdown.spice"
        deck_path.write_text(deck_text)
        proc = subprocess.run(
            [NGSPICE, "-b", str(deck_path)],
            capture_output=True,
            text=True,
            cwd=tmp,
            check=False,
        )
    output = proc.stdout + "\n" + proc.stderr

    values_1hz, total_1hz = parse_section(
        output, "=== NOISE_BREAKDOWN_1HZ_START ===", "=== NOISE_BREAKDOWN_1HZ_END ==="
    )
    values_1khz, total_1khz = parse_section(
        output, "=== NOISE_BREAKDOWN_1KHZ_START ===", "=== NOISE_BREAKDOWN_1KHZ_END ==="
    )

    lines = [
        "Nominal-corner (tt/27 C/3.30 V) per-device noise-contribution breakdown",
        f"DUT: {tb.dut_path} ({tb.dut_provenance_class})",
        f"ngspice: {ngspice_version()}, pdk: {pdk.variant} @ {pdk.version}",
        "",
        "Noise models active at this corner: gf180mcu's pinned BSIM4 MOS sections "
        "set fnoimod=1 with noia/noib/noic flicker-noise parameters, and the BJT "
        "sections carry kf/af flicker-noise parameters -- both contribute to the "
        "1 Hz figure below; only thermal noise (BJT shot + resistor/channel "
        "thermal) survives by 1 kHz on a part with a sub-kHz 1/f corner.",
        "",
        "At 1 Hz:",
        summarize_section(values_1hz, total_1hz),
        "",
        "At 1 kHz:",
        summarize_section(values_1khz, total_1khz),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dut", default="sim/dut/bandgap_top.spice", metavar="PATH",
        help="DUT netlist (default: sim/dut/bandgap_top.spice)",
    )
    parser.add_argument("--out", default="", metavar="PATH", help="write notes text to PATH too")
    args = parser.parse_args(argv)

    text = run(args.dut)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"\nnotes written: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
