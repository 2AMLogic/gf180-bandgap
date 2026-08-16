#!/usr/bin/env python3
"""Run the gf180mcu vertical-PNP local-mismatch Monte Carlo (issue #25).

Executes `testbench/tb_pnp_mismatch.spice` headlessly through ngspice at
three temperatures on the `bjt_typical` corner, commits the raw per-point
logs, freezes the netlist snapshot, and writes one append-only summary
record under `records/` per `sim/README.md`.

This experiment is driven directly against `sim/harness`'s library modules
(`pdk.py`, `runner.py`, `report.py`, `corners.py`, `stats.py`) rather than the
retired `sim/tools/devchar.py` (issue #117): PDK discovery, ngspice-version
detection, git provenance / record-id minting, the two-terminal
device-testbench corner-id naming (`sim/README.md`'s `nosupply` grammar), and
parsing/summarising a Monte Carlo `op` series (`harness.stats`, shared with
the other Monte Carlo benches -- issue #154) are all harness functions now.
What stays local is genuinely specific to this experiment -- composing/running
the per-point Monte Carlo deck (a `dowhile` / `reset` loop, not a single PVT
point) -- none of which the current `tb.json` single-grid contract expresses.
`testbench/tb.json` still documents this experiment for
harness discovery (`sim/run_corners.py --list`) and supports a secondary,
representative generic-CLI run
(`python3 sim/run_corners.py device-pnp-mismatch`) that reports one
(un-reproducible, single-draw) sample of each pair's dVBE; it is not what
produces the record below, whose N=300, seeded distribution is the actual
claim.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-pnp-mismatch/run_pnp_mismatch.py
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import corners as harness_corners  # noqa: E402
from harness import pdk as harness_pdk  # noqa: E402
from harness import report as harness_report  # noqa: E402
from harness import stats as harness_stats  # noqa: E402
from harness.runner import ngspice_version  # noqa: E402

SECTION = "bjt_typical"
TEMPS = [-40.0, 27.0, 125.0]
N_SAMPLES = 300  # must match `let mc_runs` in the control block below
SEED = 20260730  # must match `setseed` in the control block below

PAIR_BIAS_MV = 33.4  # sim/device-pnp-vbe/'s ~33.4 mV PTAT signal, for scale

# vector -> (label, bias A)
PAIRS = {
    "da1": ("pnp_05p00x05p00 identical pair", 1e-6),
    "da10": ("pnp_05p00x05p00 identical pair", 10e-6),
    "dr1": ("pnp_05p00x05p00 / pnp_10p00x10p00 area-ratioed pair", 1e-6),
    "dr10": ("pnp_05p00x05p00 / pnp_10p00x10p00 area-ratioed pair", 10e-6),
}

# Guards against a silently-ignored `sw_stat_mismatch`: if the switch were not
# actually wired up, every `reset` draw would resolve to the same op point and
# every pair would report sigma == 0.000 without complaint (issue #121).
# SIGMA_FLOOR_V is well under the smallest sigma ever observed on this
# experiment (~0.038 mV, `dr1` @ -40 C) -- more than an order of magnitude
# down -- so it only trips on a genuinely non-randomizing draw, not on normal
# run-to-run variation. MEAN_K bounds the sample mean to a generous multiple
# of its expected standard error (sigma / sqrt(N)), applied only to the
# ZERO_MEAN_PAIRS: `da1`/`da10` are two nominally identical devices, so their
# dVBE mean should sit at zero. `dr1`/`dr10` are the *area-ratioed* pair -- a
# deterministic Vbe difference of several tens of mV from the area ratio
# itself dominates their mean, so the same "mean near zero" check does not
# apply to them; the sigma floor above still covers those two.
SIGMA_FLOOR_V = 3e-6  # 0.003 mV
MEAN_K = 8
ZERO_MEAN_PAIRS = {"da1", "da10"}


# --------------------------------------------------------------------------
# Deck composition / ngspice execution -- this experiment runs a `dowhile`
# Monte Carlo loop (N=300 `reset` + `op` samples per point), not the
# single-scalar `let m_<name>` convention sim/harness/runner.py's
# compose_deck() targets, so it composes its own minimal shim instead of
# going through compose_deck(). PDK model paths still come from
# sim/harness/pdk.py -- nothing here re-resolves the PDK on its own.
# --------------------------------------------------------------------------


def _run_corner(deck: Path, pdk: harness_pdk.Pdk, section: str, temp_c: float) -> str:
    """Run `deck` through ngspice's N_SAMPLES-sample Monte Carlo loop."""
    with tempfile.TemporaryDirectory(prefix="device-pnp-mismatch-") as tmp:
        work = Path(tmp)
        local_deck = work / deck.name
        (work / "corner.spice").write_text(
            harness_report.corner_shim(
                pdk, section, temp_c, script_name="run_pnp_mismatch.py"
            ),
            encoding="utf-8",
        )
        (work / "control.spice").write_text(
            ".control\n"
            f"setseed {SEED}\n"
            "set width  = 512\n"
            "set height = 100000\n"
            f"let mc_runs = {N_SAMPLES}\n"
            "let run = 0\n"
            "dowhile run < mc_runs\n"
            "  reset\n"
            "  op\n"
            "  let da1  = v(ea1a)  - v(ea1b)\n"
            "  let da10 = v(ea10a) - v(ea10b)\n"
            "  let dr1  = v(er1a)  - v(er1b)\n"
            "  let dr10 = v(er10a) - v(er10b)\n"
            "  print da1 da10 dr1 dr10\n"
            "  let run = run + 1\n"
            "end\n"
            "quit\n"
            ".endc\n",
            encoding="utf-8",
        )
        local_deck.write_text(
            '.include "corner.spice"\n'
            + deck.read_text(encoding="utf-8")
            + '\n.include "control.spice"\n.end\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["ngspice", "-b", deck.name],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )
    log = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(
            f"ngspice exited {proc.returncode} for {deck.name} "
            f"[{section} @ {temp_c} C]\n{log}"
        )
    if re.search(r"^\s*(Error|ERROR|fatal)", log, re.MULTILINE):
        raise RuntimeError(f"ngspice reported an error for {deck.name}:\n{log}")
    return log


# --------------------------------------------------------------------------
# Device-specific analysis
# --------------------------------------------------------------------------


def extract(log: str) -> dict[str, dict[str, float]]:
    samples = harness_stats.parse_op_series(log)
    if len(samples) != N_SAMPLES:
        raise RuntimeError(
            f"expected {N_SAMPLES} Monte Carlo samples in the log, parsed "
            f"{len(samples)} -- testbench control loop and N_SAMPLES disagree?"
        )
    out: dict[str, dict[str, float]] = {}
    for key in PAIRS:
        values = [s[key] for s in samples]
        mean = harness_stats.mean(values)
        sigma = harness_stats.stdev(values)
        if sigma <= SIGMA_FLOOR_V:
            raise RuntimeError(
                f"pair {key!r}: sigma={sigma * 1e3:.6f} mV is at or below the "
                f"{SIGMA_FLOOR_V * 1e3:g} mV floor -- the Monte Carlo draw does "
                "not appear to be re-randomizing (sw_stat_mismatch ignored?)"
            )
        if key in ZERO_MEAN_PAIRS:
            bound = MEAN_K * sigma / math.sqrt(N_SAMPLES)
            if abs(mean) > bound:
                raise RuntimeError(
                    f"pair {key!r}: mean={mean * 1e3:+.6f} mV exceeds {MEAN_K}x "
                    f"its expected standard error ({bound * 1e3:.6f} mV) -- the "
                    "draw may not be centered at zero / re-randomizing correctly"
                )
        out[key] = {
            "mean": mean,
            "sigma": sigma,
            "max_abs": max(abs(v) for v in values),
        }
    return out


def build_record(record, stamp, pdk, ngspice, results) -> str:
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
    add(f"  - PDK: {pdk.variant} ({pdk.path}), ngspice {ngspice}")
    add(
        f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder "
        "(issue #25, re-run onto sim/harness by issue #117)"
    )
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


def main() -> int:
    pdk = harness_pdk.find_pdk()
    root = harness_pdk.REPO_ROOT
    ngspice = ngspice_version()
    git = harness_report.git_provenance(root)
    record = harness_report.allocate_record_id(root, HERE / "records", git=git)
    stamp = datetime.strptime(record[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    deck = HERE / "testbench" / "tb_pnp_mismatch.spice"

    print(f"record {record}: {len(TEMPS)} Monte Carlo points, N={N_SAMPLES} each")
    results: dict[float, dict] = {}
    for temp in TEMPS:
        cid = harness_corners.device_corner_id(SECTION, temp)
        log = _run_corner(deck, pdk, SECTION, temp)
        harness_report.write_device_corner_log(
            HERE / "corners",
            record,
            cid,
            harness_report.device_log_header(
                pdk, deck, SECTION, temp, record, stamp, ngspice
            ),
            log,
        )
        results[temp] = extract(log)
        print(f"  {cid}: ok")

    harness_report.write_device_netlist_snapshot(
        HERE / "netlist-snapshots", record, deck
    )
    path = harness_report.device_write_record(
        HERE / "records", record, build_record(record, stamp, pdk, ngspice, results)
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
