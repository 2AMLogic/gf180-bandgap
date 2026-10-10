#!/usr/bin/env python3
"""Ingest the fleet (`klt sim` `monte_carlo`) reports of the untrimmed-accuracy
mismatch leg into the `sim/mc-untrimmed/` record format.

Counterpart of `sim/tools/mk_klt_mc_request.py`: that script wrote the plan and
the 12 (group x temperature) requests; this one grades the `report.json` each
returned and, only when the grid is complete and consistent, mints an
append-only record (record + raw per-group logs + frozen decks) that
`sim/check_records.py` and `sim/suite/combined.py` read exactly like a record
from the local `run_mc_untrimmed.py`:

* ``corners/<record>/<group>_<T>c_3.30v.log`` holds one ``vref_val`` /
  ``isup_val`` block per sample (the shape `combined.parse_mc_samples` reads);
* the record's tables (mean / 1 sigma / 3 sigma per group and temperature, the
  mm_all window check, the sensitivity ranking) are rendered by the SAME
  `run_mc_untrimmed.build_record`;
* the record states the DUT identity (file sha256 -- the value corner records
  state -- plus the mismatch-injected variant's sha256 and the per-instance
  sigma) so `combined` can refuse to pair legs of different DUTs.

Completeness is never silently relaxed. A grid is INCOMPLETE (no record is
written, no verdict claimed) when any expected sample is absent, errored or
lacks a finite measurement, when N < 300, when a temperature or group is
missing, or when the report's provenance / seeds / DUT hash do not back the
plan. The only grading outcomes that still write a record are PASS and FAIL
against the ratified +/-2 % window.

    python3 sim/tools/mc_fleet_ingest.py WORKDIR [--dut PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = SIM.parent
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(HERE))

import fleet_common as fc  # noqa: E402
import mk_klt_mc_request as mk  # noqa: E402

EXPERIMENT = "mc-untrimmed"
#: The control group (mismatch off) must be exactly deterministic.
CONTROL_GROUP = "mm_ctrl"
CONTROL_SIGMA_MAX_V = 1e-9
#: vref_lo / vref_hi come from a one-point sweep and must agree.
SWEEP_AGREE_REL = 1e-9
SWEEP_AGREE_ABS = 1e-12


def corner_cid(run, group: str, temp: float) -> str:
    from harness import corners as harness_corners

    return harness_corners.device_corner_id(group, temp, run.SUPPLY_ID)


def expected_keys(run, entry: dict, n: int) -> list[tuple]:
    return [(mk.PROCESS_NAME, round(run.SUPPLY_V, 4), float(entry["temp_c"]), i) for i in range(n)]


def key_of(corner_id: str) -> tuple:
    process, supply, temp, idx = fc.parse_klt_mc_corner_id(corner_id)
    return process, None if supply is None else round(supply, 4), temp, idx


def plan_problems(run, plan: dict, *, dut_sha: str | None, tb_sha: str, decks: dict[str, str],
                  requests: dict[str, str] | None = None) -> list[str]:
    """Why the plan cannot describe the grid the ratified row asks for."""
    probs: list[str] = []
    if plan.get("schema") != mk.PLAN_SCHEMA:
        probs.append(f"plan schema {plan.get('schema')!r}, expected {mk.PLAN_SCHEMA!r}")
    n = plan.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or n < mk.MIN_SAMPLES:
        probs.append(f"plan N={n!r} is below the ratified floor N>={mk.MIN_SAMPLES}")
    if plan.get("vary") != mk.VARY:
        probs.append(f"plan monte_carlo.vary {plan.get('vary')!r}, expected {mk.VARY!r}")
    if plan.get("seed") != run.SEED:
        probs.append(f"plan seed {plan.get('seed')!r} differs from run_mc_untrimmed.SEED {run.SEED}")
    defn = run.group_definition()
    if plan.get("definition_sha256") != mk.definition_sha256(defn) or plan.get("definition") != defn:
        probs.append("the group / temperature / section definition in run_mc_untrimmed.py changed since the "
                     "request was generated (or the plan was edited)")
    if dut_sha is not None and plan.get("dut", {}).get("sha256") != dut_sha:
        probs.append(f"DUT sha256 {dut_sha[:12]} differs from the plan's {str(plan.get('dut', {}).get('sha256'))[:12]}")
    if plan.get("tb_netlist_sha256") != tb_sha:
        probs.append("testbench netlist changed since the request was generated")
    want = [(g, float(t)) for g in run.GROUPS for t in run.TEMPS]
    have = [(r.get("group"), float(r.get("temp_c"))) for r in plan.get("requests", [])]
    for gt in want:
        if gt not in have:
            probs.append(f"no request for group {gt[0]!r} at {gt[1]:g} C")
    for gt in sorted(set(have) - set(want), key=str):
        probs.append(f"unexpected request for group {gt[0]!r} at {gt[1]:g} C")
    for gt in {g for g in have if have.count(g) > 1}:
        probs.append(f"duplicate request for group {gt[0]!r} at {gt[1]:g} C")
    for r in plan.get("requests", []):
        cfg = run.GROUPS.get(r.get("group"))
        if cfg is None:
            continue
        if r.get("n") != n:
            probs.append(f"request {r['name']!r}: n={r.get('n')!r} differs from the plan's {n!r}")
        if (r.get("sw_stat_mismatch"), r.get("dut_variant")) != (cfg["sw_stat_mismatch"], cfg["dut"]):
            probs.append(f"request {r['name']!r}: group switches differ from run_mc_untrimmed.GROUPS")
        if fc.sha256_bytes(decks.get(r["name"], "").encode()) != r.get("deck_sha256") or r["name"] not in decks:
            probs.append(f"request {r['name']!r}: deck sha256 differs from the plan (edited after generation?)")
        if requests is not None and fc.sha256_bytes(requests.get(r["name"], "").encode()) != r.get("request_sha256"):
            probs.append(f"request {r['name']!r}: request.json sha256 differs from the plan")
    return probs


def sample_problems(entry: dict, report: dict, units: dict) -> list[str]:
    """Seed / index consistency of the returned samples (see `klt sim`'s seed contract)."""
    probs: list[str] = []
    mc = (report.get("environment") or {}).get("monte_carlo")
    if not isinstance(mc, dict):
        return [f"{entry['name']}: report has no environment.monte_carlo (not a Monte Carlo run)"]
    for k, want in (("n", entry["n"]), ("seed", entry["seed"]), ("vary", entry["vary"])):
        if mc.get(k) != want:
            probs.append(f"{entry['name']}: environment.monte_carlo.{k} is {mc.get(k)!r}, requested {want!r}")
    seeds, procs = [], set()
    for c in report.get("corners", []):
        try:
            key = key_of(c["corner_id"])
        except Exception:
            continue
        meta = c.get("monte_carlo")
        if not isinstance(meta, dict) or meta.get("sample_index") != key[3]:
            probs.append(f"{entry['name']}: {c['corner_id']} sample_index does not match its id")
            continue
        seeds.append((key[3], meta.get("seed")))
        procs.add(meta.get("process_seed"))
    if len({s for _, s in seeds}) != len(seeds):
        probs.append(f"{entry['name']}: sample seeds are not distinct (the sampler did not vary)")
    if len(procs) > 1:
        probs.append(f"{entry['name']}: process_seed varies across samples although vary={entry['vary']!r}")
    return probs


def assess(run, plan: dict, reports: dict[str, dict], *, dut_sha: str | None, tb_sha: str,
           decks: dict[str, str], requests: dict[str, str] | None = None,
           require_remote: bool = True) -> dict:
    """Grade the whole grid.

    -> {"overall": PASS|FAIL|INCOMPLETE, "stats": {group: {temp: stats}},
        "samples": {(group, temp): [(index, vref, isup)]},
        "missing": [...], "failed": [...], "problems": [...], "rndseeds": {name: {i: seed}}}
    """
    from harness import stats as harness_stats

    problems = plan_problems(run, plan, dut_sha=dut_sha, tb_sha=tb_sha, decks=decks, requests=requests)
    missing: list = []
    failed: list = []
    stats: dict[str, dict[float, dict]] = {g: {} for g in run.GROUPS}
    samples: dict[tuple, list] = {}
    rndseeds: dict[str, dict[int, int]] = {}
    n = plan.get("n") if isinstance(plan.get("n"), int) else 0
    for entry in plan.get("requests", []):
        name, group, temp = entry["name"], entry["group"], float(entry["temp_c"])
        rep = reports.get(name)
        if rep is None:
            missing.append(((name,), "no report.json returned for this request"))
            continue
        problems += [f"{name}: {p}" for p in fc.provenance_problems(rep, plan, require_remote=require_remote)]
        problems += [f"{name}: {p}" for p in fc.report_identity_problems(rep, entry.get("deck_sha256"))]
        exp = expected_keys(run, entry, entry["n"] if isinstance(entry.get("n"), int) else n)
        pts, miss, fail, probs = fc.collect_units(rep, exp, mk.MEAS_NAMES, key_of)
        missing += [((name,) + k, why) for k, why in miss]
        failed += [((name,) + k, why) for k, why in fail]
        problems += [f"{name}: {p}" for p in probs]
        problems += sample_problems(entry, rep, pts)
        rows = []
        for key in exp:
            v = pts.get(key)
            if v is None:
                continue
            if not math.isclose(v["vref_lo"], v["vref_hi"], rel_tol=SWEEP_AGREE_REL, abs_tol=SWEEP_AGREE_ABS) or \
               not math.isclose(v["isup_lo"], v["isup_hi"], rel_tol=SWEEP_AGREE_REL, abs_tol=SWEEP_AGREE_ABS):
                problems.append(f"{name}: sample {key[3]} MIN and MAX of the one-point sweep disagree "
                                "(more than one sweep point was simulated)")
                continue
            rows.append((key[3], v["vref_lo"], -v["isup_lo"]))
        rndseeds[name] = {
            c["monte_carlo"]["sample_index"]: c["monte_carlo"].get("seed")
            for c in rep.get("corners", []) if isinstance(c.get("monte_carlo"), dict)
        }
        samples[(group, temp)] = rows
        if len(rows) == entry.get("n") and len(rows) >= mk.MIN_SAMPLES:
            vref = [r[1] for r in rows]
            isup = [r[2] for r in rows]
            degenerate = [i for i, cur in enumerate(isup) if abs(cur) < run.DEGENERATE_ISUP_THRESHOLD_A]
            stats[group][temp] = {
                "n": len(rows), "mean": harness_stats.mean(vref), "sigma": harness_stats.stdev(vref),
                "min": min(vref), "max": max(vref), "isup_mean": harness_stats.mean(isup),
                "degenerate_count": len(degenerate), "degenerate_indices": degenerate,
            }
    # Common random numbers: every request must use the same per-sample seeds.
    names = list(rndseeds)
    for other in names[1:]:
        if rndseeds[other] != rndseeds[names[0]] and rndseeds[other] and rndseeds[names[0]]:
            problems.append(f"{other}: per-sample seeds differ from {names[0]} (common random numbers broken)")
    # Group sanity: control exactly deterministic, mismatch groups actually varying.
    for group, by_temp in stats.items():
        for temp, st in by_temp.items():
            if group == CONTROL_GROUP and st["sigma"] > CONTROL_SIGMA_MAX_V:
                problems.append(f"{group} at {temp:g} C: control sigma {st['sigma']:.3g} V is not exactly 0 "
                                "(a mismatch-off group must be deterministic)")
            if group != CONTROL_GROUP and not st["sigma"] > 0:
                problems.append(f"{group} at {temp:g} C: sigma is 0 -- mismatch was not sampled")
    complete = (
        not problems and not missing and not failed
        and all(len(stats[g]) == len(run.TEMPS) for g in run.GROUPS)
    )
    overall = "INCOMPLETE"
    if complete:
        fail = any(st["degenerate_count"] for g in stats.values() for st in g.values())
        lo, hi = run.TARGET_V * (1 - run.TARGET_TOL), run.TARGET_V * (1 + run.TARGET_TOL)
        for temp in run.TEMPS:
            st = stats["mm_all"][temp]
            fail |= not (lo <= st["mean"] - 3 * st["sigma"] and st["mean"] + 3 * st["sigma"] <= hi)
        overall = "FAIL" if fail else "PASS"
    return {"overall": overall, "stats": stats, "samples": samples, "missing": missing, "failed": failed,
            "problems": problems, "rndseeds": rndseeds}


# --------------------------------------------------------------------- evidence


def log_body(rows: list, header: str) -> str:
    """The raw per-group log: the blocks `combined.parse_mc_samples` reads."""
    out = [header]
    for _i, vref, isup in sorted(rows):
        out.append(f"vref_val = {vref:.10e}\nisup_val = {isup:.10e}\n")
    return "\n".join(out)


def identity_lines(plan: dict, dut_label: str) -> list[str]:
    """The record's explicit DUT identity, read by `suite.combined`."""
    by_variant = {r["dut_variant"]: r["dut_variant_sha256"] for r in plan["requests"]}
    return [
        f"  - **DUT identity**: canonical DUT `{dut_label}` sha256 `{plan['dut']['sha256']}` "
        "(the file hash corner records state for the same DUT); simulated as the `.subckt bandgap_top` "
        "fragment with the bench circuit of `sim/mc-untrimmed/testbench/tb_mc_untrimmed.spice`. "
        f"Variant sha256: baseline `{by_variant.get('baseline')}`, resistor-mismatch-injected `{by_variant.get('mm')}` "
        "(trailing `.end` stripped; injected per-instance sigma listed below). "
        f"Testbench sha256 `{plan['tb_netlist_sha256']}`; grid-definition sha256 `{plan['definition_sha256']}`.",
    ]


def seed_clause(plan: dict) -> str:
    return (
        f"`klt sim` `monte_carlo` `{{n: {plan['n']}, seed: {plan['seed']}, vary: \"{plan['vary']}\"}}` on the Spot "
        "fleet: one ngspice process per sample, each seeded `.options seed=<rndseed>` derived by SHA-256 from "
        "(seed, corner index, sample index). Each request holds ONE temperature, so the corner index is 0 and the "
        "per-sample seeds are identical across all groups and temperatures (checked at ingest) -- the same "
        "common-random-numbers convention as the local bench, and physically the same die at each temperature. "
        "The numbers are a different draw from the local bench's `setseed` stream, not a bit-for-bit replay; "
        "`.meas` values are requested at 11 significant digits (`options.ngspice_init: set measureprec=10`); a runner "
        "that drops the option still returns 6 digits (quantization sd about 3 uV, negligible against the "
        "sub-mV to mV spreads)"
    )


FLEET_NETLIST_CAVEAT = (
    "**Final-DUT record**: taken against the canonical `sim/dut/bandgap_top.spice`; its identity "
    "(file sha256, variant hashes, per-instance mismatch sigma) is stated under **DUT identity** below. "
    "`suite/combined.py` pairs this leg only with a corner record that states the same DUT sha256."
)
FLEET_MISS_NOTE = (
    "A miss is reported as measured; the ratified window is not adjusted to make a record pass, and a "
    "miss feeds trim-range sizing rather than being explained away."
)


def build_evidence_record(run, plan, result, reports, record, stamp, dut_label, dut_path, issue, supersedes, git=None) -> str:
    saved = dict(run.RUN_CONTEXT)
    run.RUN_CONTEXT.update({
        "issue": str(issue), "supersedes": supersedes or "(none)",
        "netlist_caveat": FLEET_NETLIST_CAVEAT, "miss_note": FLEET_MISS_NOTE,
    })
    try:
        return run.build_record(
            record, stamp, _PdkStub(), "fleet", dut_path, plan["injected"], result["stats"],
            seed_clause=seed_clause(plan), identity_lines=identity_lines(plan, dut_label),
            link_lines=[
                "  - Fleet request adapter: `sim/tools/mk_klt_mc_request.py`; ingestion: `sim/tools/mc_fleet_ingest.py`",
                f"  - Plan, requests and reports: `sim/mc-untrimmed/corners/{record}/` "
                "(`plan.json`, `request-<name>.json`, `report-<name>.json`, `deck-<name>.spice`)",
            ] + [_execution_line(n, rep) for n, rep in reports.items()],
            pdk_line=_pdk_line(reports),
        )
    finally:
        run.RUN_CONTEXT.clear()
        run.RUN_CONTEXT.update(saved)


def _execution_line(name: str, rep: dict) -> str:
    r = (rep.get("environment") or {}).get("remote") or {}
    if not r:
        return f"  - Fleet execution `{name}`: NOT RECORDED in the report (`environment.remote` absent)"
    return (f"  - Fleet execution `{name}`: {r.get('provider')} job `{r.get('job_id')}`, {r.get('instance_type')} "
            f"({r.get('lifecycle')}), state {r.get('state')}, exit {r.get('exit_code')}")


class _PdkStub:
    """build_record only reads pdk.variant/path for the (overridden) PDK link."""

    variant = "gf180mcuD"
    path = "fleet"


def _pdk_line(reports: dict) -> str:
    seen = []
    for rep in reports.values():
        prov = rep.get("provenance") or {}
        env = rep.get("environment") or {}
        remote = env.get("remote") or {}
        item = (f"{(prov.get('pdk') or {}).get('name')} ({(prov.get('pdk') or {}).get('version')}), "
                f"ngspice {env.get('engine_version')}, submitting klt {remote.get('client_klt_version')}, "
                f"worker klt {remote.get('runner_klt_version')} (compatibility {remote.get('runner_compatibility')})")
        if item not in seen:
            seen.append(item)
    return "  - PDK / tools (fleet): " + "; ".join(seen)


def write_evidence(run, exp_dir: Path, work: Path, plan: dict, result: dict, reports: dict, decks: dict, *,
                   dut_label: str, dut_path: Path, issue, supersedes=None, git=None, repo: Path = REPO,
                   stamp: datetime | None = None) -> Path:
    """Write record + logs + frozen decks + plan/request/report copies under
    ``exp_dir`` (``sim/mc-untrimmed``; a temp dir in tests). Never overwrites."""
    from harness import report as hreport

    if result["overall"] == "INCOMPLETE":
        raise ValueError("refusing to mint a record for an INCOMPLETE grid (no verdict is claimed)")
    record, st, cdir, git = fc.begin_evidence(exp_dir, repo=repo, git=git, stamp=stamp)
    for (group, temp), rows in result["samples"].items():
        cid = corner_cid(run, group, temp)
        header = (
            "* ====================================================================\n"
            f"* record-id  : {record}\n* group      : {group} ({run.GROUPS[group]['label']})\n"
            f"* temp       : {temp:g} C\n* supply     : {run.SUPPLY_ID} (fixed nominal)\n"
            f"* sw_stat_mismatch : {run.GROUPS[group]['sw_stat_mismatch']}\n* dut variant : {run.GROUPS[group]['dut']}\n"
            f"* source     : klt sim monte_carlo (fleet), {len(rows)} samples, request {mk.request_name(group, temp)}; "
            "per-sample ids and seeds are in report-<request>.json\n"
            "* ====================================================================\n"
        )
        hreport.write_device_corner_log(exp_dir / "corners", record, cid, "", log_body(rows, header))
    fc.copy_request_artifacts(work, cdir, [r["name"] for r in plan["requests"]], reports,
                              compact_reports=True, require_reports=True)
    for r in plan["requests"]:
        (cdir / f"deck-{r['name']}.spice").write_text(decks[r["name"]])
    snap = exp_dir / "netlist-snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    mm_deck = next(r["name"] for r in plan["requests"] if r["dut_variant"] == "mm")
    (snap / f"{record}.spice").write_text(
        f"* mismatch-injected DUT variant, as simulated by the fleet (frozen deck of request {mm_deck}).\n"
        + decks[mm_deck])
    text = build_evidence_record(run, plan, result, reports, record, st, dut_label, dut_path, issue, supersedes, git)
    return hreport.device_write_record(exp_dir / "records", record, text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workdir", help="dir written by mk_klt_mc_request.py, with <request>/report.json added")
    ap.add_argument("--dut", default="sim/dut/bandgap_top.spice", help="canonical DUT the requests were built from")
    ap.add_argument("--issue", default="239")
    ap.add_argument("--supersedes", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the verdict, write nothing")
    a = ap.parse_args()

    run = mk.load_run_module()
    work = Path(a.workdir).resolve()
    plan, reports, decks, requests = fc.load_work(work)
    dut = Path(a.dut) if Path(a.dut).is_absolute() else REPO / a.dut
    result = assess(run, plan, reports, dut_sha=fc.sha256_file(dut), tb_sha=fc.sha256_file(mk.TB_PATH),
                    decks=decks, requests=requests)
    nvalid = sum(len(v) for v in result["stats"].values())
    print(f"overall={result['overall']} (group,temp) points complete={nvalid}/{len(run.GROUPS) * len(run.TEMPS)} "
          f"missing={len(result['missing'])} failed={len(result['failed'])} problems={len(result['problems'])}")
    for label in ("problems", "missing", "failed"):
        for item in result[label][:10]:
            print(f"  {label[:-1] if label != 'missing' else label}: {item}")
    if a.dry_run or result["overall"] == "INCOMPLETE":
        return 0 if result["overall"] == "PASS" else 2
    path = write_evidence(run, SIM / EXPERIMENT, work, plan, result, reports, decks, dut_label=a.dut, dut_path=dut,
                          issue=a.issue, supersedes=a.supersedes)
    print(f"wrote {path}")
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
