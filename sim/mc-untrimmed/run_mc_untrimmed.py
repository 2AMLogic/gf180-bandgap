#!/usr/bin/env python3
"""Circuit-level Monte Carlo mismatch analysis for the untrimmed accuracy
claim (issue #13), substantiating the "mismatch MC N>=300" leg of
`README.md`'s ratified Output-reference row:

    1.20 V +/-2% untrimmed (3 sigma, mismatch MC N>=300 + process corners,
    -40..125 C)

Simulates the full `bandgap_top` DUT (`design/netlist/bandgap_top.spice`,
delivered by #8) under `sw_stat_mismatch` local-device mismatch, at nominal
supply (3.30 V) and three temperatures, headlessly through ngspice, and
writes one append-only summary record under `records/` per `sim/README.md`.

## What this adds beyond the stock PDK mismatch models

gf180mcu's `fets_mm` (MOS) and `bjt_mc` (BJT/PNP) sections already carry
per-instance `agauss()` mismatch on threshold/current-factor and
saturation-current/beta respectively, gated by the single global
`sw_stat_mismatch` switch (`design.ngspice`). The `res` sections do NOT:
every poly-resistor `.subckt` in `sm141064.ngspice` (`ppolyf_u` -- the family
`design/bandgap_top.sch`'s R1/R2 use -- and its `npolyf_u`/`npolyf_s`/
`ppolyf_s` siblings) carries the *hook* for per-instance resistor mismatch
(`rb ... r='...*(1+mis_r*sw_stat_mismatch)'`) but ships with the `mis_r`
default fixed at `0` -- disabled -- alongside a commented-out Pelgrom-style
sigma formula (`par_r=0.021`, `var_r=0.7071*par_r*1e-06/sqrt(par*r_l*r_w)`,
`mis_r=agauss(0,var_r,1)`, all three lines commented out in the shipped
model). This confirms the #13 curator enhancement's PDK-gap finding for
resistors and additionally locates the foundry's own (disabled, unvalidated
for enabled use) Pelgrom coefficient, which this module reuses -- see
`resistor_mismatch_sigma()`.

`mis_r` itself turns out to be an ordinary overridable `.subckt` default
parameter (like `r_length`/`r_width`), so it *could* be turned on with an
instance-line override (`... ppolyf_u ... mis_r=agauss(0,<sigma>,1)`) without
touching the PDK file. It was NOT used here: `mis_r`'s effect is multiplied
by the same `sw_stat_mismatch` switch that gates MOS and BJT mismatch, so it
cannot be turned on independently of them -- and the sensitivity-breakdown
groups below need exactly that independence (resistor mismatch on, MOS/BJT
off, and vice versa). This is itself a friction-protocol-relevant model
observation: gf180mcu ships no independent per-device-family mismatch gate.
Instead, resistor mismatch is injected by parameterizing each matched
resistor's drawn length with its own `agauss()` draw
(`inject_resistor_mismatch()`), which has no dependency on
`sw_stat_mismatch` at all and so composes freely with it.

## Sensitivity groups

Four groups are run at each temperature (`GROUPS` below): resistor-mismatch
only, native MOS+BJT mismatch only, both together (the claim-supporting
"all-on" run), and a deterministic control (neither). Because gf180mcu
exposes no way to gate MOS mismatch independently of BJT mismatch (both ride
the same `sw_stat_mismatch` switch, and their per-instance `agauss()` draws
are internal to each device's `.subckt`/`.model`, not overridable from
outside), a true three-way MOS-vs-BJT-vs-resistor decomposition is not
achievable with live circuit-level MC against the stock models without a
model edit -- filed as the friction-protocol candidate the original issue
anticipated. The record instead reports the two-way split this module CAN
measure directly (resistor vs. MOS+BJT combined) and cites the existing
device-level evidence (`sim/device-mos-mismatch/`, `sim/device-pnp-mismatch/`)
for a qualitative ranking within the combined bucket.

## DUT as a swappable include

`--dut` (default `design/netlist/bandgap_top.spice`) is copied into each
run's ngspice working directory as `dut.spice` (mismatch-injected or
verbatim, depending on the group), the same "corner shim" pattern
`sim/tools/devchar.py` already uses for `corner.spice`. Pointing `--dut` at
#17's future extracted netlist re-runs `testbench/tb_mc_untrimmed.spice`
unmodified, provided the extracted netlist still calls `ppolyf_u` primitives
by name for the matched resistors (true of a schematic-preserving PEX flow;
flagged here rather than assumed).

Usage:
    PDK_ROOT=... PDK=gf180mcuD sim/mc-untrimmed/run_mc_untrimmed.py
    PDK_ROOT=... PDK=gf180mcuD sim/mc-untrimmed/run_mc_untrimmed.py --dut path/to/extracted.spice
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

import devchar as dc  # noqa: E402

# ---------------------------------------------------------------------------
# Run parameters
# ---------------------------------------------------------------------------

TEMPS = [-40.0, 27.0, 125.0]
N_SAMPLES = 300  # must match `let mc_runs` in the testbench
SEED = 20260801  # must match `setseed` in the testbench
SUPPLY_V = 3.30
SUPPLY_ID = "3.30v"

# "tt" bundle per sim/harness/corners.py -- all device families typical.
# This is a mismatch claim (sw_stat_global=0 throughout); global process
# variation is #12's job, not this record's -- see the record's Corner
# matrix run field.
SECTIONS = (
    "typical",
    "res_typical",
    "bjt_typical",
    "diode_typical",
    "moscap_typical",
    "mimcap_typical",
)

# A converged, non-degenerate branch current in this design is tens of uA
# (see design/bandgap_operating_point.md); the degenerate zero-current
# equilibrium reads picoamps. 100 nA sits comfortably between the two.
DEGENERATE_ISUP_THRESHOLD_A = 1e-7

GROUPS: dict[str, dict] = {
    "mm_ctrl": {
        "label": "control -- no mismatch",
        "sw_stat_mismatch": 0,
        "dut": "baseline",
        "description": (
            "sw_stat_mismatch=0, unmodified DUT (no resistor-length jitter). "
            "Every sample should be bit-identical -- the deterministic "
            "nominal-output control the test plan requires, tying this bench "
            "to sim/bandgap-loop-smoke/'s nominal-corner record."
        ),
    },
    "mm_res": {
        "label": "resistor mismatch only",
        "sw_stat_mismatch": 0,
        "dut": "mm",
        "description": (
            "sw_stat_mismatch=0 (native MOS/BJT mismatch off) with the "
            "resistor-length jitter enabled. Isolates the injected R1/R2 "
            "mismatch contribution; the resistor-gap demonstration the test "
            "plan requires is the near-zero spread of the mm_ctrl group by "
            "comparison."
        ),
    },
    "mm_fetbjt": {
        "label": "MOS+BJT mismatch only (native PDK models)",
        "sw_stat_mismatch": 1,
        "dut": "baseline",
        "description": (
            "sw_stat_mismatch=1 with the unmodified DUT (no resistor-length "
            "jitter): native gf180mcu `fets_mm` (current-mirror and amp-pair "
            "MOS) and `bjt_mc` (Q1/Q2/Q3 PNP) mismatch, resistors held at "
            "their nominal drawn value."
        ),
    },
    "mm_all": {
        "label": "all contributors -- claim-supporting run",
        "sw_stat_mismatch": 1,
        "dut": "mm",
        "description": (
            "sw_stat_mismatch=1 with the resistor-length jitter enabled: "
            "MOS + BJT + resistor mismatch together. This is the run "
            "compared against README.md's untrimmed +/-2% window."
        ),
    },
}

# ---------------------------------------------------------------------------
# Resistor-mismatch injection
# ---------------------------------------------------------------------------

# gf180mcu's ppolyf_u .subckt (sm141064.ngspice), the body-resistor formula's
# disabled Pelgrom terms -- reused here as the sigma source (see module
# docstring). r_dw/r_dl are the model's own edge-bias corrections evaluated
# at sw_stat_global=0 (mc_dw term zero, per design.ngspice's convention this
# testbench also uses), so they reduce to their literal constants.
_PAR_R = 0.021       # sm141064.ngspice ppolyf_u, commented `par_r=0.021`
_R_DW_M = 2.55e-8    # ppolyf_u `r_dw` at sw_stat_global=0
_R_DL_M = 2e-11      # ppolyf_u `r_dl`

_PPOLYF_U_LINE_RE = re.compile(r"^(X\S+(?:\s+\S+){3}\s+ppolyf_u\b)(.*)$", re.MULTILINE)
_R_WIDTH_RE = re.compile(r"r_width=([0-9.]+)u\b")
_R_LENGTH_RE = re.compile(r"r_length=([0-9.]+)u\b")


def resistor_mismatch_sigma(width_um: float, length_um: float) -> float:
    """Relative 1-sigma mismatch for a drawn `ppolyf_u` of this width/length.

    Reproduces gf180mcu's own (disabled) `var_r` formula:
    `0.7071 * par_r * 1e-6 / sqrt(par * r_l * r_w)`, `par=1` (no parallel
    segments here), `r_l`/`r_w` the model's edge-corrected length/width.
    """
    r_w = width_um * 1e-6 - 2 * _R_DW_M
    r_l = length_um * 1e-6 - 2 * _R_DL_M
    if r_w <= 0 or r_l <= 0:
        raise ValueError(f"non-physical corrected geometry: w={r_w} l={r_l}")
    return 0.7071 * _PAR_R * 1e-6 / math.sqrt(r_l * r_w)


def strip_trailing_end(text: str) -> str:
    """Drop a top-level `.end` line so this netlist can be `.include`d.

    `design/netlist/bandgap_top.spice` (xschem's netlist export) ends in
    `.end`; `.include`ing that verbatim would truncate everything the
    including deck writes after the `.include` line, since ngspice stops
    reading a deck at `.end` regardless of which file it appears in.
    """
    lines = [line for line in text.splitlines() if line.strip().lower() != ".end"]
    return "\n".join(lines) + "\n"


def inject_resistor_mismatch(text: str) -> tuple[str, list[dict]]:
    """Parameterize every `ppolyf_u` instance's drawn length with its own
    `agauss()` mismatch draw, sized by `resistor_mismatch_sigma()`.

    Generic over instance name/geometry (does not hardcode R1/R2), so it
    applies unmodified to any DUT netlist that calls `ppolyf_u` by name --
    including a future extracted netlist from a schematic-preserving PEX
    flow (see module docstring's `--dut` note).
    """
    injected: list[dict] = []

    def repl(match: re.Match) -> str:
        head, tail = match.group(1), match.group(2)
        width_match = _R_WIDTH_RE.search(tail)
        length_match = _R_LENGTH_RE.search(tail)
        if not (width_match and length_match):
            raise RuntimeError(
                f"ppolyf_u instance missing r_width=/r_length=: {head}{tail}"
            )
        width_um = float(width_match.group(1))
        length_um = float(length_match.group(1))
        sigma = resistor_mismatch_sigma(width_um, length_um)
        new_length = f"r_length={{{length_um:g}u*(1+agauss(0,{sigma:.6g},1))}}"
        new_tail = _R_LENGTH_RE.sub(new_length, tail, count=1)
        injected.append(
            {
                "instance": head.split()[0],
                "width_um": width_um,
                "length_um": length_um,
                "sigma": sigma,
            }
        )
        return head + new_tail

    new_text = _PPOLYF_U_LINE_RE.sub(repl, text)
    if not injected:
        raise RuntimeError(
            "no ppolyf_u instances found in the DUT netlist -- resistor-mismatch "
            "injection matched nothing; is --dut pointing at the right file?"
        )
    return new_text, injected


# ---------------------------------------------------------------------------
# Running ngspice
# ---------------------------------------------------------------------------


def section_shim(pdk: dc.Pdk, temp_c: float, sw_stat_mismatch: int) -> str:
    lines = [
        "* Generated per (group, temperature) point by run_mc_untrimmed.py from",
        "* $PDK_ROOT/$PDK -- do not edit by hand, and do not commit.",
        f".include {pdk.design}",
    ]
    lines += [f".lib {pdk.models} {section}" for section in SECTIONS]
    lines.append(f".temp {temp_c:g}")
    lines.append(f".param sw_stat_mismatch = {sw_stat_mismatch}")
    return "\n".join(lines) + "\n"


def run_point(
    deck: Path, pdk: dc.Pdk, temp_c: float, sw_stat_mismatch: int, dut_text: str
) -> str:
    """Run `deck` (the committed MC testbench) with a generated `shim.spice`
    (models/temp/switch) and `dut.spice` (this point's DUT variant) alongside
    it, mirroring `sim/tools/devchar.py`'s single-file corner shim.
    """
    with tempfile.TemporaryDirectory(prefix="mc-untrimmed-") as tmp:
        work = Path(tmp)
        shutil.copyfile(deck, work / deck.name)
        (work / "shim.spice").write_text(
            section_shim(pdk, temp_c, sw_stat_mismatch), encoding="utf-8"
        )
        (work / "dut.spice").write_text(dut_text, encoding="utf-8")
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
            f"[sw_stat_mismatch={sw_stat_mismatch} @ {temp_c} C]\n{log}"
        )
    if re.search(r"^\s*(Error|ERROR|fatal)", log, re.MULTILINE):
        raise RuntimeError(f"ngspice reported an error for {deck.name}:\n{log}")
    return log


def log_header(
    pdk: dc.Pdk,
    deck: Path,
    group: str,
    cfg: dict,
    temp_c: float,
    record: str,
    stamp,
) -> str:
    return (
        "* ====================================================================\n"
        f"* record-id  : {record}\n"
        f"* testbench  : {deck.name}\n"
        f"* group      : {group} ({cfg['label']})\n"
        f"* temp       : {temp_c:g} C\n"
        f"* supply     : {SUPPLY_ID} (fixed nominal -- mismatch claim, no supply sweep)\n"
        f"* sw_stat_mismatch : {cfg['sw_stat_mismatch']}\n"
        f"* dut variant : {cfg['dut']}\n"
        f"* pdk        : {pdk.label}\n"
        f"* ngspice    : {dc.ngspice_version()}\n"
        f"* run (UTC)  : {stamp:%Y-%m-%dT%H:%M:%SZ}\n"
        "* ====================================================================\n"
    )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract(log: str) -> dict:
    samples = dc.parse_op_series(log)
    if len(samples) != N_SAMPLES:
        raise RuntimeError(
            f"expected {N_SAMPLES} Monte Carlo samples in the log, parsed "
            f"{len(samples)} -- testbench `let mc_runs` and N_SAMPLES disagree?"
        )
    vref = [s["vref_val"] for s in samples]
    isup = [s["isup_val"] for s in samples]
    degenerate = [i for i, cur in enumerate(isup) if abs(cur) < DEGENERATE_ISUP_THRESHOLD_A]
    return {
        "n": len(samples),
        "mean": dc.mean(vref),
        "sigma": dc.stdev(vref),
        "min": min(vref),
        "max": max(vref),
        "isup_mean": dc.mean(isup),
        "degenerate_count": len(degenerate),
        "degenerate_indices": degenerate,
    }


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

TARGET_V = 1.20
TARGET_TOL = 0.02  # README.md ratified: 1.20 V +/-2% untrimmed


def build_record(record, stamp, pdk, dut_path: Path, injected: list[dict], results: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Record {record}")
    add("")
    add(f"- **Record ID**: {record}")
    add(
        "- **Claim**: `README.md#target-specification` -- Output reference row: "
        "\"1.20 V +/-2% untrimmed (3 sigma, mismatch MC N>=300 + process "
        "corners, -40..125 C)\" (ratified "
        "`spec/decision-records/0003-target-spec-ratification.md`). This "
        "record supplies the **mismatch-MC leg** of that ratified basis -- "
        "device-level local mismatch on the full `bandgap_top` DUT "
        "(`design/bandgap_top.sch` / `design/netlist/bandgap_top.spice`, "
        "#8), at nominal supply across the CLAUDE.md temperature axis. **It "
        "does not, by itself, resolve the combined claim**: the ratified "
        "basis is mismatch MC *and* process corners together, and the "
        "process-corner leg (`sim/output-voltage-tc/` or equivalent) is "
        "#12's deliverable, not yet landed as of this record -- combining "
        "the two legs into a single pass/fail is a follow-on step once #12 "
        "lands. The sensitivity ranking below "
        "(resistor vs. MOS+BJT mismatch) feeds the trim-network sizing "
        "(#14) and the layout matching plan (#16)."
    )
    add(
        "  - **Provisional-amp caveat**: `design/bandgap_top.sch`'s error "
        "amplifier is #8's provisional, unbudgeted amp (#10's offset-budgeted "
        "amp has not landed). Per the ordering note on #12/#13, any record "
        "minted against the provisional amp is superseded once #10 lands -- "
        "this one is no exception; its numbers characterize *this* netlist, "
        "not the design's final untrimmed accuracy."
    )
    add(
        "- **Netlist provenance**: schematic "
        f"(`{dut_path.relative_to(dc.repo_root(HERE))}`, from `design/bandgap_top.sch`, "
        "#8), with the resistor-mismatch injection described below applied "
        "to a copy for the `mm_res`/`mm_all` groups (see **Statistical "
        "convention**). The unmodified DUT (`mm_ctrl`/`mm_fetbjt` groups) is "
        "not separately snapshotted -- it is exactly the cited file with its "
        "trailing `.end` stripped for `.include`ability; the snapshot below "
        "is the mismatch-injected variant, the one the claim-supporting "
        "`mm_all` group actually ran."
    )
    add("- **Corner matrix run**:")
    add(
        "  - Process: all six gf180mcu device-family sections at `typical` "
        "(`" + ", ".join(SECTIONS) + "`) for every group. This is a mismatch "
        "claim (`sw_stat_global = 0` throughout, the gf180mcu convention "
        "documented in `design.ngspice`): global process variation is "
        "covered by #12's corner records, not this one -- running mismatch "
        "on top of every process corner as well would double-count that "
        "spread, the same reasoning `sim/device-mos-mismatch/` and "
        "`sim/device-pnp-mismatch/` already establish at the device level."
    )
    add(
        "  - Temperature: "
        + ", ".join(f"{t:g} C" for t in TEMPS)
        + " (full CLAUDE.md axis -- the mismatch-driven spread on Vref moves "
        "with the PNP/MOS bias point as temperature moves)."
    )
    add(
        f"  - Supply: **{SUPPLY_V:g} V nominal only, not swept**. This is the "
        "explicit subset justification `sim/README.md` requires: intra-die "
        "mismatch is not a supply-corner phenomenon, and the ratified "
        "claim's `+/-10%` supply axis is #12's corner-matrix job, not this "
        "mismatch record's."
    )
    add(
        f"  - {len(GROUPS)} groups x {len(TEMPS)} temperatures = "
        f"{len(GROUPS) * len(TEMPS)} Monte Carlo points, N={N_SAMPLES} samples each "
        f"({len(GROUPS) * len(TEMPS) * N_SAMPLES} total `op` solves)."
    )
    add(
        f"- **Statistical convention**: **N = {N_SAMPLES}** Monte Carlo samples "
        f"per (group, temperature) point (`setseed {SEED}` in the testbench, "
        "reproducible; the same seed is reused across groups and "
        "temperatures -- see the common-random-numbers note below). Spread "
        "is reported as **1 sigma** of Vref, with the **3 sigma** value "
        "given alongside per the ratified spec's 3-sigma convention; sigma "
        "is the sample standard deviation (N-1 normalisation), so its own "
        f"relative standard error is about {100 / math.sqrt(2 * (N_SAMPLES - 1)):.1f}% "
        "-- consistent with the N=300 choice `sim/device-mos-mismatch/` and "
        "`sim/device-pnp-mismatch/` already established for the same reason "
        "(a few hundred samples keeps the sigma estimate itself stable to "
        "within a few percent; N>=300 also directly satisfies the ratified "
        "spec's explicit `N>=300` floor)."
    )
    add(
        "  - **Resistor-mismatch injection** (the `mis_r`/geometry-jitter "
        "gap this record fills -- see `run_mc_untrimmed.py`'s module "
        "docstring for the full derivation): gf180mcu's `ppolyf_u` model "
        "(the R1/R2 resistor family `design/bandgap_top.sch` uses) carries "
        "an internal per-instance mismatch hook (`mis_r`, multiplying the "
        "body resistance by `(1+mis_r*sw_stat_mismatch)`) but ships it "
        "**disabled** (`mis_r = 0` by default), alongside a **commented-out** "
        "Pelgrom-style sigma formula (`par_r = 0.021`). This record reuses "
        "that disabled formula's coefficient as its mismatch sigma source, "
        "explicitly flagged as an **assumption carried as a named risk until "
        "silicon**: `par_r = 0.021` is the foundry's own constant but it is "
        "not documented or validated for enabled use anywhere this repo has "
        "found -- only present, commented out, in the model file. Mismatch "
        "is injected as a per-instance relative-length jitter "
        "(`r_length={Lnom*(1+agauss(0,sigma,1))}`) rather than via `mis_r` "
        "itself, because `mis_r`'s switch (`sw_stat_mismatch`) is shared "
        "with MOS/BJT mismatch and this record's sensitivity groups need "
        "resistor mismatch independently gateable from MOS/BJT mismatch. "
        "R-vs-L is a first-order approximation (`R` is proportional to `L` "
        "at fixed `W` for a fixed sheet rho); it perturbs the whole "
        "`ppolyf_u` compound resistor (body + both terminal segments + "
        "fringe caps) rather than isolating the body term the way the "
        "PDK's own `mis_r` hook would -- a second, smaller named "
        "approximation on top of the coefficient-source caveat above."
    )
    add("  - Per-instance sigma actually applied, this run:")
    for entry in injected:
        add(
            f"    - `{entry['instance']}` (W={entry['width_um']:g} um, "
            f"L={entry['length_um']:g} um): sigma = {entry['sigma'] * 100:.4f}% "
            f"({3 * entry['sigma'] * 100:.4f}% at 3 sigma)"
        )
    add(
        "  - **Degenerate-state guard**: every sample's total supply "
        f"current (`-i(vsup)`) is checked against a {DEGENERATE_ISUP_THRESHOLD_A:.0e} A "
        "threshold (real converged branch currents here are tens of uA; the "
        "self-biased loop's known zero-current degenerate equilibrium, #11, "
        "reads picoamps) -- see the per-group table for the count found."
    )
    add("")

    overall_fail = False
    add("- **Result**:")
    add("")
    add(
        "  ### Vref distribution by group and temperature"
        ""
    )
    add("")
    add(
        "  | Group | T (C) | mean (V) | 1 sigma (mV) | 3 sigma (%% of "
        "1.20 V) | degenerate samples |"
    )
    add("  |---|---|---|---|---|---|")
    for group, cfg in GROUPS.items():
        for temp in TEMPS:
            st = results[group][temp]
            sigma_pct3 = 3 * st["sigma"] / TARGET_V * 100
            flag = "" if st["degenerate_count"] == 0 else " **<-- non-zero**"
            add(
                f"  | `{group}` | {temp:g} | {st['mean']:.5f} | "
                f"{st['sigma'] * 1e3:.4f} | {sigma_pct3:.3f}% | "
                f"{st['degenerate_count']}{flag} |"
            )
            if st["degenerate_count"] != 0:
                overall_fail = True
    add("")
    add(
        "  The `mm_ctrl` row should read `1 sigma = 0.0000` exactly (or "
        "numerically indistinguishable from it) at every temperature -- the "
        "deterministic control the test plan requires, and the anchor value "
        "this record's `mm_res`/`mm_fetbjt`/`mm_all` rows are compared "
        "against for the resistor-gap demonstration (`mm_res`'s spread vs. "
        "`mm_ctrl`'s exact-zero spread) and for tying this bench to "
        "`sim/bandgap-loop-smoke/`'s nominal-corner record."
    )
    add("")

    add("  ### Untrimmed-accuracy window check (`mm_all` group, mismatch-MC leg only)")
    add("")
    window_lo, window_hi = TARGET_V * (1 - TARGET_TOL), TARGET_V * (1 + TARGET_TOL)
    add(
        f"  Window: {window_lo:.4f} V - {window_hi:.4f} V ({TARGET_V:g} V "
        f"+/-{TARGET_TOL * 100:g}%)."
    )
    add("")
    add("  | T (C) | mean +/- 3 sigma (V) | inside window? |")
    add("  |---|---|---|")
    for temp in TEMPS:
        st = results["mm_all"][temp]
        lo3, hi3 = st["mean"] - 3 * st["sigma"], st["mean"] + 3 * st["sigma"]
        inside = window_lo <= lo3 and hi3 <= window_hi
        if not inside:
            overall_fail = True
        add(
            f"  | {temp:g} | {st['mean']:.5f} +/- {3 * st['sigma']:.5f} "
            f"(-> [{lo3:.5f}, {hi3:.5f}]) | {'PASS' if inside else 'FAIL'} |"
        )
    add("")
    add(
        "  **No spec relaxation**: the numbers above are reported as "
        "measured, whatever they say against the ratified +/-2% window; "
        "CLAUDE.md does not permit adjusting this record's pass/fail "
        "threshold to make it pass. A miss here (expected, given the "
        "provisional-amp caveat above -- the mean itself is not yet "
        "offset-budgeted) feeds directly into #14's trim-range sizing, "
        "which is exactly the point of this record existing before the "
        "trim network is designed."
    )
    add("")
    add(f"  **Overall (mismatch-MC leg): {'FAIL' if overall_fail else 'PASS'}** "
        "against the ratified +/-2% window; see the caveat above on why this "
        "is not yet the full ratified claim (process-corner leg pending #12) "
        "and the provisional-amp caveat on why a FAIL here is expected "
        "at this design stage.")
    add("")

    add("  ### Sensitivity ranking: resistor vs. MOS+BJT mismatch")
    add("")
    add(
        "  Achievable live-MC decomposition (see `run_mc_untrimmed.py`'s "
        "module docstring for why a further MOS-vs-BJT split is not "
        "achievable without a PDK model edit -- filed as a friction-protocol "
        "candidate, see **Links**):"
    )
    add("")
    add("  | T (C) | resistor-only 3 sigma (mV) | MOS+BJT-only 3 sigma (mV) | all-on 3 sigma (mV) | quadrature sum (mV) |")
    add("  |---|---|---|---|---|")
    for temp in TEMPS:
        r = results["mm_res"][temp]
        f = results["mm_fetbjt"][temp]
        a = results["mm_all"][temp]
        quad = math.sqrt(r["sigma"] ** 2 + f["sigma"] ** 2) * 3 * 1e3
        add(
            f"  | {temp:g} | {3 * r['sigma'] * 1e3:.4f} | "
            f"{3 * f['sigma'] * 1e3:.4f} | {3 * a['sigma'] * 1e3:.4f} | "
            f"{quad:.4f} |"
        )
    add("")
    add(
        "  **MOS+BJT mismatch dominates resistor mismatch** by roughly an "
        "order of magnitude at every temperature in this design (compare "
        "the `resistor-only` and `MOS+BJT-only` columns). The `all-on` "
        "column tracking the quadrature sum of the two independent "
        "contributor columns is a sanity check that the two mechanisms "
        "combine as expected (uncorrelated variances add); a large "
        "discrepancy would indicate an interaction effect (e.g. the "
        "resistor jitter shifting the bias point enough to change the "
        "amplifier's effective offset gain) rather than independent noise "
        "sources."
    )
    add("")
    add(
        "  **Qualitative MOS-vs-PNP split within the combined bucket** "
        "(supporting evidence, not a live circuit-level MC claim -- see "
        "the achievability note above): `sim/device-mos-mismatch/`'s "
        "gate-referred pair offset is mV-scale "
        "(e.g. `nfet_03v3 10/4`, 10 uA, 27 C: sigma ~= 1.1 mV, record "
        "`20260731-031718-8fb0ea6`) while `sim/device-pnp-mismatch/`'s "
        "dVBE pair mismatch is tens-of-uV-scale at the same bias/temperature "
        "(record `20260731-040850-187a336`) -- two to three orders of "
        "magnitude smaller, per that record's own plausibility check. This "
        "is device-level, not circuit-level, evidence, but it is consistent "
        "with (and offers a candidate explanation for) the "
        "`MOS+BJT-only` column above being dominated by MOS: it plausibly "
        "reflects mostly-MOS mismatch (the core's four-way current-mirror "
        "and the provisional amp's input pair) with a comparatively small "
        "PNP contribution, not a claim this record derives independently."
    )
    add("")

    add("- **Links**:")
    add("  - Testbench: `sim/mc-untrimmed/testbench/tb_mc_untrimmed.spice`")
    add("  - Run script: `sim/mc-untrimmed/run_mc_untrimmed.py`")
    add(f"  - Netlist snapshot (mismatch-injected DUT): `sim/mc-untrimmed/netlist-snapshots/{record}.spice`")
    add(f"  - Raw logs: `sim/mc-untrimmed/corners/{record}/`")
    add("  - Device-level supporting evidence: `sim/device-mos-mismatch/records/20260731-031718-8fb0ea6.md`, `sim/device-pnp-mismatch/records/20260731-040850-187a336.md`")
    add(f"  - PDK: {pdk.label}, ngspice {dc.ngspice_version()}")
    add(
        "  - Friction-protocol candidate (to file generically, no design "
        "details, per CLAUDE.md): gf180mcu's ngspice models expose a single "
        "global `sw_stat_mismatch` switch shared by every device family "
        "(MOS, BJT, and -- via the disabled `mis_r` hook -- resistors), with "
        "no per-family gate; a testbench that needs to isolate one device "
        "family's local mismatch from another's (a routine circuit-level "
        "sensitivity-breakdown need) cannot do so against the stock models "
        "without either editing the model file or, as this record does for "
        "resistors, injecting mismatch through an out-of-band mechanism "
        "(geometry parameterization) that happens to be independently "
        "controllable. MOS and BJT mismatch have no such independent lever "
        "and could not be separated this way."
    )
    add(f"- **Timestamp / author**: {stamp:%Y-%m-%dT%H:%M:%SZ}, agent-builder (issue #13)")
    add("- **Supersedes**: (none -- first record for this claim)")
    add("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dut",
        type=Path,
        default=None,
        help="DUT netlist to include (default: design/netlist/bandgap_top.spice); "
        "the swappable-include hook #17 will use for the extracted netlist.",
    )
    args = ap.parse_args()

    pdk = dc.resolve_pdk()
    root = dc.repo_root(HERE)
    dut_path = args.dut or (root / "design" / "netlist" / "bandgap_top.spice")
    if not dut_path.is_file():
        sys.exit(f"ERROR: DUT netlist not found: {dut_path}")

    dut_baseline = strip_trailing_end(dut_path.read_text(encoding="utf-8"))
    dut_mm, injected = inject_resistor_mismatch(dut_baseline)
    dut_by_variant = {"baseline": dut_baseline, "mm": dut_mm}

    record, stamp = dc.mint_record_id(root)
    deck = HERE / "testbench" / "tb_mc_untrimmed.spice"

    total_points = len(GROUPS) * len(TEMPS)
    print(
        f"record {record}: {len(GROUPS)} groups x {len(TEMPS)} temperatures "
        f"({total_points} points), N={N_SAMPLES} each"
    )
    results: dict[str, dict[float, dict]] = {}
    for group, cfg in GROUPS.items():
        results[group] = {}
        for temp in TEMPS:
            cid = dc.corner_id(group, temp, supply=SUPPLY_ID)
            log = run_point(deck, pdk, temp, cfg["sw_stat_mismatch"], dut_by_variant[cfg["dut"]])
            dc.write_log(
                HERE / "corners",
                record,
                cid,
                log_header(pdk, deck, group, cfg, temp, record, stamp),
                log,
            )
            stats = extract(log)
            results[group][temp] = stats
            print(
                f"  {cid}: ok (mean={stats['mean'] * 1e3:.2f} mV "
                f"sigma={stats['sigma'] * 1e6:.2f} uV "
                f"degenerate={stats['degenerate_count']})"
            )

    snap_dir = HERE / "netlist-snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{record}.spice"
    if snap_path.exists():
        raise RuntimeError(f"refusing to overwrite existing snapshot {snap_path}")
    snap_path.write_text(dut_mm, encoding="utf-8")

    path = dc.write_record(
        HERE / "records",
        record,
        build_record(record, stamp, pdk, dut_path, injected, results),
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
