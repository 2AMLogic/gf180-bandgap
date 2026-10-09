#!/usr/bin/env python3
"""Emit `klt sim` Monte Carlo requests for the untrimmed-accuracy mismatch leg.

The "mismatch MC N>=300" leg of the ratified untrimmed-accuracy row is
produced locally by `sim/mc-untrimmed/run_mc_untrimmed.py`, which drives
ngspice from the invoking host. Shared dispatch workers must not run that
grid; this script expresses it as `klt sim` requests (`monte_carlo`) that
`KLT_SIM_BACKEND=batch` sends to the Spot fleet. It only WRITES requests and a
plan the ingestor (`sim/tools/mc_fleet_ingest.py`) reads; it never dispatches.

Single source of truth: the group table (`GROUPS`), temperatures, N, seed,
supply, device-family sections, the per-group DUT variants (resistor-length
mismatch injection) and the bench circuit cards (`vsup`, `vssref`, `.ic`) all
come from `run_mc_untrimmed.py` and its committed testbench -- nothing is
re-typed here.

What the pinned `klt sim` (0.7.0) `monte_carlo` contract can and cannot
express, and the mapping used (verified against klayout_tools/sim.py and
docs/cli/sim.md; see the PR for #238):

* ``monte_carlo: {n, seed, vary}`` re-runs each corner point ``n`` times, one
  ngspice process per sample, each with ``.options seed=<rndseed>`` derived
  by SHA-256 from (seed, corner index, sample index). N=300 is expressible.
  ``vary: "mismatch"`` varies only the mismatch seed component.
* Groups. gf180mcu has no per-family mismatch gate (``sw_stat_mismatch`` is
  one global switch), so ``monte_carlo`` alone cannot select a group. The
  group is carried by the *netlist*: ``.param sw_stat_mismatch = <0|1>`` and
  the DUT variant (baseline, or resistor-length jitter injected via
  ``agauss()`` in the instance line). One request PER GROUP x TEMPERATURE
  (12 requests); the fleet sees four decks, not one.
* Seed handling. The klt sample seed mixes in the corner's index within the
  request, so two temperatures in ONE request would draw different dice. The
  legacy bench (and physics: mismatch is a property of the die, not of the
  temperature) uses the same dice at every temperature and group, so each
  request holds a single temperature -> corner index 0 -> the same
  per-sample seed everywhere. (`mm_res`/`mm_all` still draw resistor
  mismatch from the same stream as the native models, exactly as before.)
* ``analysis`` is one card and there is no `.meas op`. The op point is read as
  a degenerate one-point ``dc vsup 3.3 3.3 1`` sweep with MIN/MAX `.meas`
  (MIN and MAX of a one-point sweep must agree; the ingestor checks it).
* The legacy ``.control`` loop (`reset`/`op`, ``setseed``) is replaced by
  klt's one-process-per-sample fan-out; the numbers are a different (equally
  valid) draw of the same distribution, not bit-identical to old records.

    python3 sim/tools/mk_klt_mc_request.py WORKDIR [--dut PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(HERE))

import fleet_common as fc  # noqa: E402

GENERATOR = "sim/tools/mk_klt_mc_request.py"
PLAN_SCHEMA = "gf180-bandgap/mc-fleet-plan/1"
SUPPLY_SOURCE = "vsup"
PROCESS_NAME = "tt"
#: The ratified floor of the row: "mismatch MC N>=300".
MIN_SAMPLES = 300
VARY = "mismatch"
#: digits after the decimal point of the mantissa ngspice prints for `.meas` (`%.*e`).
MEAS_PREC = 10
MODELS = {"pdk": "gf180mcuD", "lib": "libs.tech/ngspice/sm141064.ngspice"}
TB_PATH = SIM / "mc-untrimmed" / "testbench" / "tb_mc_untrimmed.spice"
#: .meas cards: a one-point dc sweep, so MIN == MAX is the value.
MEASUREMENTS = (
    ("vref_lo", ".meas dc vref_lo MIN v(vref)", "V"),
    ("vref_hi", ".meas dc vref_hi MAX v(vref)", "V"),
    ("isup_lo", ".meas dc isup_lo MIN i(vsup)", "A"),
    ("isup_hi", ".meas dc isup_hi MAX i(vsup)", "A"),
)
MEAS_NAMES = tuple(m[0] for m in MEASUREMENTS)


def load_run_module():
    """`sim/mc-untrimmed/run_mc_untrimmed.py` (a hyphenated directory, so not
    importable by name): the group/DUT/testbench definitions live there."""
    name = "run_mc_untrimmed"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SIM / "mc-untrimmed" / "run_mc_untrimmed.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def temp_tag(t: float) -> str:
    return f"{t:g}".replace("-", "m").replace(".", "p")


def request_name(group: str, temp_c: float) -> str:
    return f"{group}_{temp_tag(temp_c)}c"


def definition_sha256(defn: dict) -> str:
    return fc.sha256_bytes(json.dumps(defn, sort_keys=True).encode())


def build_request(run, *, temp_c: float, n: int, seed: int) -> dict:
    """One request: one temperature, N samples. The group lives in the deck."""
    v = run.SUPPLY_V
    return {
        "netlist": "body.spice",
        "engine": "ngspice",
        "models": dict(MODELS),
        "corners": {
            "process": [{"name": PROCESS_NAME, "sections": list(run.SECTIONS)}],
            "supply_v": {SUPPLY_SOURCE: [v]},
            "temperature_c": [temp_c],
        },
        "analysis": {"kind": "dc", "args": f"{SUPPLY_SOURCE} {v:g} {v:g} 1"},
        "measurements": [{"name": n_, "spice": card, "unit": u} for n_, card, u in MEASUREMENTS],
        "monte_carlo": {"n": n, "seed": seed, "vary": VARY},
        # `.meas` prints 6 significant digits by default; ngspice >= 46 honours measureprec
        # (docs/cli/sim.md "Measurement output precision"). A runner older than the client
        # may drop the option silently (klayout-tools#2901) -- harmless here: the 6-digit
        # quantization (sd ~3 uV) is far below every group's spread -- and the ingestor
        # records the digits it actually received.
        "options": {"timeout_s": 120, "keep_artifacts": False, "ngspice_init": [f"set measureprec={MEAS_PREC}"]},
    }


TOP_SUBCKT = "bandgap_top"
INSTANCE = "xdut"
_SUBCKT_RE = re.compile(r"^\s*\.subckt\s+" + TOP_SUBCKT + r"\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_VNODE_RE = re.compile(r"\bv\(([^)\s]+)\)", re.IGNORECASE)


def top_ports(dut_text: str) -> list[str]:
    m = _SUBCKT_RE.search(dut_text)
    if not m:
        raise ValueError(
            f"DUT has no `.subckt {TOP_SUBCKT}` definition: the fleet MC bench instantiates the "
            "includable fragment (sim/dut/bandgap_top.spice), not the flattened design/netlist export"
        )
    return m.group(1).split()


def subckt_bench_circuit(run, tb_text: str, dut_text: str) -> list[str]:
    """The legacy bench circuit, re-expressed for the includable DUT fragment.

    The committed testbench was written for the flattened xschem export
    (top-level nodes at deck level, ``v(xx1.casc)``). The canonical DUT
    (`sim/dut/bandgap_top.spice`, the file corner records hash) wraps the same
    circuit in ``.subckt bandgap_top``, so the cards are taken from the
    testbench as-is and only (a) the DUT instance is added, nets named by
    port, and (b) ``.ic`` references to nodes that are not ports gain the
    instance prefix -- exactly what the other benches' ``Xdut`` does.
    """
    ports = top_ports(dut_text)
    lowered = {p.lower() for p in ports}

    def prefix(m: re.Match) -> str:
        name = m.group(1)
        return m.group(0) if name.lower() in lowered else f"v({INSTANCE}.{name})"

    out = []
    for line in run.testbench_circuit_lines(tb_text):
        out.append(_VNODE_RE.sub(prefix, line) if line.lower().startswith(".ic") else line)
    out.insert(0, f"{INSTANCE} {' '.join(ports)} {TOP_SUBCKT}")
    return out


def build_deck(run, name: str, *, design_text: str, dut_text: str, sw_stat_mismatch: int, tb_text: str) -> str:
    """One self-contained deck (the fleet stages only the request's netlist)."""
    out = [
        f"* mc-untrimmed/{name} -- GENERATED by {GENERATOR}, do not edit",
        # gf180mcu BSIM4 bins are per finger; see mk_klt_request.py for why.
        ".options wnflag=1",
        "* ---- begin inlined design.ngspice (PDK) ----",
        run.strip_trailing_end(design_text).rstrip(),
        "* ---- end inlined design.ngspice ----",
        # after design.ngspice, which defaults it to 0 (the legacy shim does the same).
        f".param sw_stat_mismatch = {sw_stat_mismatch}",
        "* ---- begin inlined DUT ----",
        dut_text.rstrip(),
        "* ---- end inlined DUT ----",
        "* ---- begin bench circuit (from sim/mc-untrimmed/testbench/tb_mc_untrimmed.spice) ----",
        *subckt_bench_circuit(run, tb_text, dut_text),
        "* ---- end bench circuit ----",
        "",
    ]
    return "\n".join(out)


def build_plan(*, dut: Path, dut_rel: str, design_text: str, tb_text: str | None = None,
               n: int | None = None, seed: int | None = None,
               submitting_klt_version: str | None = None) -> tuple[dict, dict[str, str]]:
    """Pure builder -> (plan, files); ``files`` maps relative paths to text."""
    run = load_run_module()
    n = run.N_SAMPLES if n is None else n
    seed = run.SEED if seed is None else seed
    if n < MIN_SAMPLES:
        raise ValueError(f"N={n} < {MIN_SAMPLES}: the ratified row requires mismatch MC N>={MIN_SAMPLES}")
    tb_text = TB_PATH.read_text() if tb_text is None else tb_text
    consts = run.testbench_constants(tb_text)
    if consts["mc_runs"] != run.N_SAMPLES or consts["seed"] != run.SEED or consts["supply_v"] != run.SUPPLY_V:
        raise ValueError(f"run_mc_untrimmed.py constants disagree with its testbench: {consts}")
    variants, injected = run.prepare_dut_variants(dut.read_text())
    defn = run.group_definition()
    files: dict[str, str] = {}
    entries: list[dict] = []
    for group, cfg in run.GROUPS.items():
        for temp in run.TEMPS:
            name = request_name(group, temp)
            deck = build_deck(run, name, design_text=design_text, dut_text=variants[cfg["dut"]],
                              sw_stat_mismatch=cfg["sw_stat_mismatch"], tb_text=tb_text)
            req = build_request(run, temp_c=temp, n=n, seed=seed)
            req_text = json.dumps(req, indent=2) + "\n"
            files[f"{name}/body.spice"], files[f"{name}/request.json"] = deck, req_text
            entries.append({
                "name": name, "group": group, "temp_c": float(temp),
                "sw_stat_mismatch": cfg["sw_stat_mismatch"], "dut_variant": cfg["dut"],
                "n": n, "seed": seed, "vary": VARY,
                "deck_sha256": fc.sha256_bytes(deck.encode()),
                "request_sha256": fc.sha256_bytes(req_text.encode()),
                "dut_variant_sha256": fc.sha256_bytes(variants[cfg["dut"]].encode()),
            })
    plan = {
        "schema": PLAN_SCHEMA,
        "submitting_klt_version": submitting_klt_version,
        "dut": {"path": dut_rel, "sha256": fc.sha256_file(dut)},
        "tb_netlist_sha256": fc.sha256_bytes(tb_text.encode()),
        "definition": defn,
        "definition_sha256": definition_sha256(defn),
        "n": n, "seed": seed, "vary": VARY, "supply_v": run.SUPPLY_V,
        "temps_c": [float(t) for t in run.TEMPS],
        "groups": list(run.GROUPS),
        "injected": injected,
        "requests": entries,
    }
    files["plan.json"] = json.dumps(plan, indent=2) + "\n"
    return plan, files


def klt_version() -> str | None:
    import subprocess

    try:
        out = subprocess.run(["klt", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.split()[-1] if out else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("outdir")
    ap.add_argument("--dut", default="sim/dut/bandgap_top.spice")
    a = ap.parse_args()

    sys.path.insert(0, str(SIM))
    from harness import pdk as hp

    dut = (REPO / a.dut).resolve()
    plan, files = build_plan(
        dut=dut, dut_rel=str(dut.relative_to(REPO)), design_text=hp.find_pdk().design_include.read_text(),
        submitting_klt_version=klt_version(),
    )
    out = Path(a.outdir).resolve()
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    print(f"wrote {out}/plan.json ({len(plan['requests'])} request(s), N={plan['n']} seed={plan['seed']}); NOT dispatched.")
    for r in plan["requests"]:
        print(f"  {r['name']}: {r['n']} samples -> klt sim --backend batch -o {out}/{r['name']}/out "
              f"{out}/{r['name']}/request.json --format json > {out}/{r['name']}/report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
