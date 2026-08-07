#!/usr/bin/env python3
"""Run the gf180mcu 3.3 V MOS local-mismatch Monte Carlo (issue #4).

Executes `testbench/tb_mos_mismatch.spice` headlessly through ngspice at three
temperatures on the `typical` corner, commits the raw per-point logs, freezes
the netlist snapshot, and writes one append-only summary record under
`records/` per `sim/README.md`.

This experiment is driven directly against `sim/harness`'s library modules
(`pdk.py`, `runner.py`, `report.py`, `corners.py`) rather than the retired
`sim/tools/devchar.py` (issue #117): PDK discovery, ngspice-version detection,
git provenance / record-id minting and the two-terminal device-testbench
corner-id naming (`sim/README.md`'s `nosupply` grammar) are all harness
functions now. What stays local is genuinely specific to this experiment --
composing/running the per-point Monte Carlo deck (a `dowhile` / `reset` loop,
not a single PVT point), parsing the repeated `print` samples, and the
mean/sigma/Pelgrom-scaling analysis -- none of which the current `tb.json`
single-grid contract expresses. `testbench/tb.json` still documents this
experiment for harness discovery (`sim/run_corners.py --list`) and supports a
secondary, representative generic-CLI run
(`python3 sim/run_corners.py device-mos-mismatch`) that reports one
(un-reproducible, single-draw) sample of each pair's gate-voltage difference;
it is not what produces the record below, whose N=300, seeded distribution is
the actual claim.

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/device-mos-mismatch/run_mos_mismatch.py
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
from harness.runner import ngspice_version  # noqa: E402

SECTION = "typical"
TEMPS = [-40.0, 27.0, 125.0]
N_SAMPLES = 300  # must match `let mc_runs` in the control block below
SEED = 20260731  # must match `setseed` in the control block below

# Guards against a silently-ignored `sw_stat_mismatch`: if the switch were not
# actually wired up, every `reset` draw would resolve to the same op point and
# every pair would report sigma == 0.000 without complaint (issue #121).
# SIGMA_FLOOR_V is well under the smallest sigma ever observed on this
# experiment (~1.10 mV, `dn4`/`dp4` @ -40 C) -- about an order of magnitude
# down -- so it only trips on a genuinely non-randomizing draw, not on normal
# run-to-run variation. MEAN_K bounds the sample mean to a generous multiple
# of its expected standard error (sigma / sqrt(N)); a mean far outside that
# is the other symptom of a non-random (or otherwise miswired) draw.
SIGMA_FLOOR_V = 1e-4  # 0.1 mV
MEAN_K = 8

# vector -> (label, W um, L um, bias A)
PAIRS = {
    "dn1": ("nfet_03v3 10/1", 10.0, 1.0, 1e-6),
    "dn4": ("nfet_03v3 10/4", 10.0, 4.0, 1e-6),
    "dp1": ("pfet_03v3 10/1", 10.0, 1.0, 1e-6),
    "dp4": ("pfet_03v3 10/4", 10.0, 4.0, 1e-6),
    "en1": ("nfet_03v3 10/1", 10.0, 1.0, 10e-6),
    "en4": ("nfet_03v3 10/4", 10.0, 4.0, 10e-6),
    "ep1": ("pfet_03v3 10/1", 10.0, 1.0, 10e-6),
    "ep4": ("pfet_03v3 10/4", 10.0, 4.0, 10e-6),
}


# --------------------------------------------------------------------------
# Deck composition / ngspice execution -- this experiment runs a `dowhile`
# Monte Carlo loop (N=300 `reset` + `op` samples per point), not the
# single-scalar `let m_<name>` convention sim/harness/runner.py's
# compose_deck() targets, so it composes its own minimal shim instead of
# going through compose_deck(). PDK model paths still come from
# sim/harness/pdk.py -- nothing here re-resolves the PDK on its own.
# --------------------------------------------------------------------------


def _corner_shim(pdk: harness_pdk.Pdk, section: str, temp_c: float) -> str:
    return (
        "* Generated per corner point by run_mos_mismatch.py from\n"
        "* $PDK_ROOT/$PDK (via sim/harness/pdk.py) -- do not edit by hand, "
        "and do not commit.\n"
        f'.include "{pdk.design_include}"\n'
        f'.lib "{pdk.model_lib}" {section}\n'
        f".temp {temp_c:g}\n"
    )


def _run_corner(deck: Path, pdk: harness_pdk.Pdk, section: str, temp_c: float) -> str:
    """Run `deck` through ngspice's N_SAMPLES-sample Monte Carlo loop."""
    with tempfile.TemporaryDirectory(prefix="device-mos-mismatch-") as tmp:
        work = Path(tmp)
        local_deck = work / deck.name
        (work / "corner.spice").write_text(
            _corner_shim(pdk, section, temp_c), encoding="utf-8"
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
            "  let dn1 = v(gn1a) - v(gn1b)\n"
            "  let dn4 = v(gn4a) - v(gn4b)\n"
            "  let dp1 = v(gp1a) - v(gp1b)\n"
            "  let dp4 = v(gp4a) - v(gp4b)\n"
            "  let en1 = v(hn1a) - v(hn1b)\n"
            "  let en4 = v(hn4a) - v(hn4b)\n"
            "  let ep1 = v(hp1a) - v(hp1b)\n"
            "  let ep4 = v(hp4a) - v(hp4b)\n"
            "  print dn1 dn4 dp1 dp4 en1 en4 ep1 ep4\n"
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


def _write_record(records_dir: Path, record: str, body: str) -> Path:
    """Write `records/<record-id>.md`, refusing to overwrite (append-only)."""
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / f"{record}.md"
    if path.exists():
        raise RuntimeError(
            f"refusing to overwrite existing record {path} -- sim/ is append-only; "
            "a re-run must mint a new record ID"
        )
    path.write_text(body, encoding="utf-8")
    return path


_OP_LINE = re.compile(r"^([a-zA-Z_][\w()\-.,+@#]*)\s*=\s*([-+0-9.eE]+)\s*$")


def _parse_op_series(log: str) -> list[dict[str, float]]:
    """Parse repeated `op`+`print` blocks (the Monte Carlo loop) into samples.

    A new sample starts whenever a name that has already been seen repeats.
    """
    samples: list[dict[str, float]] = []
    current: dict[str, float] = {}
    for line in log.splitlines():
        match = _OP_LINE.match(line.strip())
        if not match:
            continue
        name = match.group(1).lower()
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if name in current:
            samples.append(current)
            current = {}
        current[name] = value
    if current:
        samples.append(current)
    return samples


def _stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


# --------------------------------------------------------------------------
# Device-specific analysis
# --------------------------------------------------------------------------


def extract(log: str) -> dict[str, dict[str, float]]:
    samples = _parse_op_series(log)
    if len(samples) != N_SAMPLES:
        raise RuntimeError(
            f"expected {N_SAMPLES} Monte Carlo samples in the log, parsed "
            f"{len(samples)} -- testbench control loop and N_SAMPLES disagree?"
        )
    out: dict[str, dict[str, float]] = {}
    for key in PAIRS:
        values = [s[key] for s in samples]
        mean = _mean(values)
        sigma = _stdev(values)
        if sigma <= SIGMA_FLOOR_V:
            raise RuntimeError(
                f"pair {key!r}: sigma={sigma * 1e3:.6f} mV is at or below the "
                f"{SIGMA_FLOOR_V * 1e3:g} mV floor -- the Monte Carlo draw does "
                "not appear to be re-randomizing (sw_stat_mismatch ignored?)"
            )
        bound = MEAN_K * sigma / math.sqrt(N_SAMPLES)
        if abs(mean) > bound:
            raise RuntimeError(
                f"pair {key!r}: mean={mean * 1e3:+.6f} mV exceeds {MEAN_K}x its "
                f"expected standard error ({bound * 1e3:.6f} mV) -- the draw may "
                "not be centered at zero / re-randomizing correctly"
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
        "- **Claim**: gf180mcu 3.3 V MOS **local mismatch** for the mirror and "
        "amplifier-input devices of the Brokaw core selected in DR-0001 "
        "(`spec/decision-records/0001-bandgap-topology-selection.md`) -- the "
        "gate-referred offset of a nominally identical, equally biased device "
        "pair. This is the anchor for the offset budget (#10) and the "
        "circuit-level Monte Carlo (#13). **This record makes no spec pass/fail "
        "claim**: no ratified spec exists yet (#1); it reports a measured "
        "distribution, not a verdict."
    )
    add(
        "- **Netlist provenance**: schematic-level device testbench "
        "(`sim/device-mos-mismatch/testbench/tb_mos_mismatch.spice`) -- PDK "
        "device models instantiated directly; no `design/` schematic, no "
        "extracted layout."
    )
    add("- **Corner matrix run**:")
    add(
        f"  - Process: `{SECTION}` only. Local mismatch is intra-die variation and "
        "is deliberately decoupled from the global corner axis: the run sets "
        "`sw_stat_mismatch = 1` with `sw_stat_global = 0`, which is the gf180mcu "
        "convention documented in `design.ngspice`. Running mismatch on top of "
        "each process corner would double-count the global spread already "
        "recorded in the `sim/device-mos-vth/` corner matrix."
    )
    add(
        "  - Temperature: "
        + ", ".join(f"{t:g} C" for t in TEMPS)
        + " (full CLAUDE.md temperature axis -- mismatch is temperature-dependent"
        " because the same threshold spread refers to the gate differently as the"
        " inversion level moves)"
    )
    add(
        "  - Supply: **not applicable** -- every DUT is referred to its own source "
        "node at ground and driven by an ideal current source; there is no supply "
        "rail, so the +/-10% supply axis of the CLAUDE.md PVT matrix has nothing "
        "to sweep. This is the explicit subset justification `sim/README.md` "
        "requires; the log filenames carry `nosupply` in the supply field."
    )
    add(f"  - {len(TEMPS)} Monte Carlo points ({SECTION} x {len(TEMPS)} temperatures)")
    add(
        f"- **Statistical convention**: **N = {N_SAMPLES}** Monte Carlo samples per "
        "temperature, mismatch-only (`sw_stat_mismatch = 1`, `sw_stat_global = 0`). "
        "Spread is reported as **1 sigma** of the pair's gate-voltage difference, "
        "with the 3 sigma value given alongside; sigma is the sample standard "
        f"deviation (N-1 normalisation), so its own relative standard error is "
        f"about {100 / math.sqrt(2 * (N_SAMPLES - 1)):.1f}%. Run is reproducible: "
        f"`setseed {SEED}` in the testbench."
    )
    add("- **Result**: measured distribution (no spec comparison -- see Claim).")
    add("")

    add("### Pair gate-referred offset, 1 sigma (mV)")
    add("")
    add(
        "`sigma(dVgs)` is the pair difference; the equivalent single-device sigma "
        "is `sigma(dVgs)/sqrt(2)`. `A_pair` normalises to area as "
        "`sigma(dVgs) x sqrt(W L) / sqrt(2)` (drawn area) so #8/#10 can scale to "
        "other geometries -- it is a Pelgrom-style figure that lumps threshold and "
        "current-factor mismatch together, not a pure A_VT."
    )
    add("")
    add(
        "| DUT | Id | T (C) | mean (mV) | sigma (mV) | 3 sigma (mV) | "
        "worst sample, abs (mV) | 1-device sigma (mV) | A_pair (mV.um) |"
    )
    add("|---|---|---|---|---|---|---|---|---|")
    for key, (label, w, length, bias) in PAIRS.items():
        for temp in TEMPS:
            st = results[temp][key]
            sigma_mv = st["sigma"] * 1e3
            add(
                f"| `{label}` | {bias * 1e6:g} uA | {temp:g} | "
                f"{st['mean'] * 1e3:+.4f} | {sigma_mv:.4f} | {3 * sigma_mv:.3f} | "
                f"{st['max_abs'] * 1e3:.3f} | {sigma_mv / math.sqrt(2):.4f} | "
                f"{sigma_mv * math.sqrt(w * length) / math.sqrt(2):.3f} |"
            )
    add("")
    add(
        "The sample mean should sit at zero to within `sigma / sqrt(N)`; a mean "
        "materially larger than that would indicate the Monte Carlo draw is not "
        "re-randomising and the numbers should not be trusted."
    )
    add("")
    add(
        "The three temperatures reuse the **same seed**, so they are the same 300 "
        "device draws re-solved at a different temperature (common random "
        "numbers). The small temperature trend in sigma is therefore a real "
        "bias-point effect rather than sampling noise -- but it also means the "
        "three rows for a given DUT are *not* independent estimates of sigma."
    )
    add("")

    add("- **Links**:")
    add("  - Testbench: `sim/device-mos-mismatch/testbench/tb_mos_mismatch.spice`")
    add("  - Run script: `sim/device-mos-mismatch/run_mos_mismatch.py`")
    add(
        f"  - Netlist snapshot: `sim/device-mos-mismatch/netlist-snapshots/{record}.spice`"
    )
    add(f"  - Raw logs: `sim/device-mos-mismatch/corners/{record}/`")
    add(f"  - PDK: {pdk.variant} ({pdk.path}), ngspice {ngspice}")
    add(
        f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder "
        "(issue #4, re-run onto sim/harness by issue #117)"
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
    deck = HERE / "testbench" / "tb_mos_mismatch.spice"

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
    path = _write_record(
        HERE / "records", record, build_record(record, stamp, pdk, ngspice, results)
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
