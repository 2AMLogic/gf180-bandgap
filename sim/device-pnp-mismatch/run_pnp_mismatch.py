#!/usr/bin/env python3
"""Run the gf180mcu vertical-PNP local-mismatch Monte Carlo (issue #25).

Executes `testbench/tb_pnp_mismatch.spice` headlessly through ngspice at
three temperatures on the `bjt_typical` corner, commits the raw per-point
logs, freezes the netlist snapshot, and writes one append-only summary
record under `records/` per `sim/README.md`.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-pnp-mismatch/run_pnp_mismatch.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

import devchar as dc  # noqa: E402

SECTION = "bjt_typical"
TEMPS = [-40.0, 27.0, 125.0]
N_SAMPLES = 300  # must match `let mc_runs` in the testbench
SEED = 20260730  # must match `setseed` in the testbench

PAIR_BIAS_MV = 33.4  # sim/device-pnp-vbe/'s ~33.4 mV PTAT signal, for scale

# vector -> (label, bias A)
PAIRS = {
    "da1": ("pnp_05p00x05p00 identical pair", 1e-6),
    "da10": ("pnp_05p00x05p00 identical pair", 10e-6),
    "dr1": ("pnp_05p00x05p00 / pnp_10p00x10p00 area-ratioed pair", 1e-6),
    "dr10": ("pnp_05p00x05p00 / pnp_10p00x10p00 area-ratioed pair", 10e-6),
}


def extract(log: str) -> dict[str, dict[str, float]]:
    samples = dc.parse_op_series(log)
    if len(samples) != N_SAMPLES:
        raise RuntimeError(
            f"expected {N_SAMPLES} Monte Carlo samples in the log, parsed "
            f"{len(samples)} -- testbench `let mc_runs` and N_SAMPLES disagree?"
        )
    out: dict[str, dict[str, float]] = {}
    for key in PAIRS:
        values = [s[key] for s in samples]
        out[key] = {
            "mean": dc.mean(values),
            "sigma": dc.stdev(values),
            "max_abs": max(abs(v) for v in values),
        }
    return out


def build_record(record, stamp, pdk, results) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add(
        "- **Claim**: gf180mcu vertical (substrate) PNP **local mismatch** for "
        "the Brokaw core selected in DR-0001 "
        "(`spec/decision-records/0001-bandgap-topology-selection.md`) -- sigma "
        "of dVBE for (a) two identical `pnp_05p00x05p00` devices and (b) the "
        "area-ratioed `pnp_05p00x05p00` / `pnp_10p00x10p00` pair, at equal "
        "emitter current. This is the PNP counterpart to "
        "`sim/device-mos-mismatch/`'s MOS gate-referred offset and feeds the "
        "offset budget (#10) and the circuit-level Monte Carlo (#13) alongside "
        "it. **This record makes no spec pass/fail claim**: no ratified spec "
        "exists yet (#1); it reports a measured distribution, not a verdict."
    )
    add(
        "- **Netlist provenance**: schematic-level device testbench "
        "(`sim/device-pnp-mismatch/testbench/tb_pnp_mismatch.spice`) -- PDK "
        "device models instantiated directly; no `design/` schematic, no "
        "extracted layout."
    )
    add("- **Corner matrix run**:")
    add(
        f"  - Process: `{SECTION}` only (the nominal BJT process point). Local "
        "mismatch is intra-die variation and is deliberately decoupled from the "
        "global corner axis: the run sets `sw_stat_mismatch = 1` with "
        "`sw_stat_global = 0`, which is the gf180mcu convention documented in "
        "`design.ngspice` and the same convention `sim/device-mos-mismatch/` "
        "uses. Running mismatch on top of each BJT process corner "
        "(`bjt_ss`/`bjt_typical`/`bjt_ff`) would double-count the global "
        "spread already recorded in the `sim/device-pnp-vbe/` corner matrix."
    )
    add(
        "  - Temperature: "
        + ", ".join(f"{t:g} C" for t in TEMPS)
        + " (full CLAUDE.md temperature axis -- the mismatch spread on `is` "
        "and `bf` refers to VBE differently as the bias point moves with "
        "temperature)"
    )
    add(
        "  - Supply: **not applicable** -- every DUT is a diode-connected "
        "device referred to its own emitter node at ground and driven by an "
        "ideal current source; there is no supply rail, so the +/-10% supply "
        "axis of the CLAUDE.md PVT matrix has nothing to sweep. This is the "
        "explicit subset justification `sim/README.md` requires; the log "
        "filenames carry `nosupply` in the supply field."
    )
    add(f"  - {len(TEMPS)} Monte Carlo points ({SECTION} x {len(TEMPS)} temperatures)")
    add(
        f"- **Statistical convention**: **N = {N_SAMPLES}** Monte Carlo samples "
        "per temperature, mismatch-only (`sw_stat_mismatch = 1`, "
        "`sw_stat_global = 0`). Spread is reported as **1 sigma** of the "
        "pair's emitter-voltage difference (dVBE), with the 3 sigma value "
        "given alongside; sigma is the sample standard deviation (N-1 "
        f"normalisation), so its own relative standard error is about "
        f"{100 / math.sqrt(2 * (N_SAMPLES - 1)):.1f}%. Run is reproducible: "
        f"`setseed {SEED}` in the testbench."
    )
    add("- **Result**: measured distribution (no spec comparison -- see Claim).")
    add("")

    add("### Pair dVBE, 1 sigma (mV)")
    add("")
    add(
        f"For scale: `sim/device-pnp-vbe/`'s area-ratioed pair reports a dVBE "
        f"*signal* of ~{PAIR_BIAS_MV:g} mV at 27 C, 10 uA (record "
        "`20260731-030932-8fb0ea6`) -- the sigma figures below are the "
        "mismatch noise sitting in series with that signal, not a fraction of "
        "it derived from this record."
    )
    add("")
    add("| Pair | Id | T (C) | mean (mV) | sigma (mV) | 3 sigma (mV) | worst sample, abs (mV) |")
    add("|---|---|---|---|---|---|---|")
    for key, (label, bias) in PAIRS.items():
        for temp in TEMPS:
            st = results[temp][key]
            sigma_mv = st["sigma"] * 1e3
            add(
                f"| `{label}` | {bias * 1e6:g} uA | {temp:g} | "
                f"{st['mean'] * 1e3:+.4f} | {sigma_mv:.4f} | {3 * sigma_mv:.3f} | "
                f"{st['max_abs'] * 1e3:.3f} |"
            )
    add("")
    add(
        "The sample mean should sit at zero to within `sigma / sqrt(N)`; a mean "
        "materially larger than that would indicate the Monte Carlo draw is not "
        "re-randomising and the numbers should not be trusted."
    )
    add("")
    add(
        "The three temperatures reuse the **same seed**, so they are the same "
        f"{N_SAMPLES} device draws re-solved at a different temperature (common "
        "random numbers). The three rows for a given pair are therefore *not* "
        "independent estimates of sigma."
    )
    add("")
    add(
        f"**Plausibility check**: sigma(dVBE) is 2-3 orders of magnitude smaller "
        f"than the {PAIR_BIAS_MV:g} mV PTAT signal (tens of uV vs tens of mV) -- "
        "expected, since the PDK's per-instance `mis_is_pnp_*` / `mis_bf_pnp_*` "
        "agauss() sigmas are themselves small (0.05-0.3%) relative to the "
        "MOS `fets_mm` mismatch sigmas that produce the mV-scale spread in "
        "`sim/device-mos-mismatch/`. It is not required that PNP mismatch be "
        "smaller than the MOS pair offset -- it is, here, because this PDK's "
        "BJT matching model is tighter than its MOS matching model, not "
        "because of any device-physics necessity."
    )
    add("")

    add("- **Links**:")
    add("  - Testbench: `sim/device-pnp-mismatch/testbench/tb_pnp_mismatch.spice`")
    add("  - Run script: `sim/device-pnp-mismatch/run_pnp_mismatch.py`")
    add(
        f"  - Netlist snapshot: `sim/device-pnp-mismatch/netlist-snapshots/{record}.spice`"
    )
    add(f"  - Raw logs: `sim/device-pnp-mismatch/corners/{record}/`")
    add(f"  - PDK: {pdk.label}, ngspice {dc.ngspice_version()}")
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #25)")
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


def main() -> int:
    pdk = dc.resolve_pdk()
    root = dc.repo_root(HERE)
    record, stamp = dc.mint_record_id(root)
    deck = HERE / "testbench" / "tb_pnp_mismatch.spice"

    print(f"record {record}: {len(TEMPS)} Monte Carlo points, N={N_SAMPLES} each")
    results: dict[float, dict] = {}
    for temp in TEMPS:
        cid = dc.corner_id(SECTION, temp)
        log = dc.run_corner(deck, pdk, SECTION, temp)
        dc.write_log(
            HERE / "corners",
            record,
            cid,
            dc.log_header(pdk, deck, SECTION, temp, record, stamp),
            log,
        )
        results[temp] = extract(log)
        print(f"  {cid}: ok")

    dc.snapshot_netlist(HERE / "netlist-snapshots", record, deck)
    path = dc.write_record(
        HERE / "records", record, build_record(record, stamp, pdk, results)
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
