#!/usr/bin/env python3
"""Helpers shared by the fleet (`klt sim`) request adapters and ingestors.

Factored out of `sim/tools/tc_ingest.py` (issue #237) so the TC ingestion and
the psrr-dc / line-regulation / startup ingestion (`sim/tools/fleet_ingest.py`)
apply one completeness rule instead of three copies:

* an expected unit that is absent, errored, or lacks a *finite numeric*
  required measurement is never dropped -- it is reported as missing/failed;
* duplicate and unexpected corner ids are report-level problems;
* provenance (DUT hash, bench hash, submitting vs worker klt version) that is
  absent or inconsistent is a problem, not a footnote.

Pure functions, stdlib only: no PDK, ngspice, fleet or network.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

#: ``runner_compatibility`` values `klt sim --backend batch` can report
#: (klayout_tools/sim_batch.py `_read_runner_identity`).
COMPAT_OK = "match"


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def is_finite_number(x) -> bool:
    """A real, finite number. ``bool`` is not a measurement; NaN/inf are not
    evidence (a ``nan`` that slipped through `isinstance(x, float)` would
    compare False against every limit and could read as PASS downstream)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def corner_key(corner_id: str) -> tuple[str, float]:
    """'tt/2.970V/27C' -> ('tt', 2.97). Raises on any other shape
    (including the supply-less ``tt/novdd/27C``)."""
    process, supply, _temp = corner_id.split("/")
    return process, float(supply.rstrip("Vv"))


def parse_klt_corner_id(corner_id: str) -> tuple[str, float | None, float]:
    """'tt/2.970V/-40C' -> ('tt', 2.97, -40.0); 'tt/novdd/27C' -> ('tt', None, 27.0).

    Raises ValueError on anything else (including Monte Carlo ``/mcN`` ids,
    which these deterministic corner benches never request)."""
    parts = corner_id.split("/")
    if len(parts) != 3:
        raise ValueError(f"unparseable corner id {corner_id!r}")
    process, supply, temp = parts
    if not temp.endswith(("C", "c")):
        raise ValueError(f"unparseable temperature in {corner_id!r}")
    sup = None if supply == "novdd" else float(supply.rstrip("Vv"))
    return process, sup, float(temp[:-1])


def parse_klt_mc_corner_id(corner_id: str) -> tuple[str, float | None, float, int]:
    """'tt/3.300V/-40C/mc17' -> ('tt', 3.3, -40.0, 17).

    The Monte Carlo sample form of :func:`parse_klt_corner_id` (klt appends
    ``/mc<sample_index>`` to the corner a sample was drawn from). Deliberately
    a separate function: the deterministic corner benches must keep rejecting
    an ``/mcN`` id (a sampled id in a corner report is a wrong report), while
    the MC ingester must reject the *absence* of one. Raises ValueError on
    anything that is not exactly ``<process>/<supply>/<temp>C/mc<N>``."""
    base, sep, tail = corner_id.rpartition("/")
    if not sep or not tail.startswith("mc") or not tail[2:].isdigit():
        raise ValueError(f"not a Monte Carlo sample corner id {corner_id!r}")
    process, supply, temp = parse_klt_corner_id(base)
    return process, supply, temp, int(tail[2:])


def diagnostics_text(c: dict, limit: int = 300) -> str:
    diag = "; ".join(
        (f"{d.get('code')}: {d.get('message')}" if isinstance(d, dict) else f"malformed diagnostic {d!r}")
        for d in c.get("diagnostics", []) or []
    )
    return diag[:limit]


ACCEPTED_CORNER_STATUSES = ("pass", "fail")  # fail = legitimate spec miss; still graded
FATAL_SEVERITIES = ("error", "fatal")


def _is_fatal_diag(d) -> bool:
    """Missing / non-dict / non-string severity is treated as fatal (fail closed)."""
    if not isinstance(d, dict):
        return True
    sev = d.get("severity")
    return not isinstance(sev, str) or sev.strip().lower() in FATAL_SEVERITIES


def execution_rejection(c: dict) -> str | None:
    """Why a corner's execution cannot be trusted, or None.

    Status must be exactly ``pass`` or ``fail``; independently, any error/fatal
    (or severity-less) diagnostic rejects. Warnings are retained, not fatal."""
    status = c.get("status")
    reasons = []
    if not isinstance(status, str) or status not in ACCEPTED_CORNER_STATUSES:
        reasons.append(f"status={status!r}" + ("" if status in ("error", "inconclusive") else " (unknown corner status)"))
    fatal = [d for d in (c.get("diagnostics") or []) if _is_fatal_diag(d)]
    if fatal:
        txt = "; ".join(
            f"{d.get('code')}: {d.get('message')}" if isinstance(d, dict) else f"malformed diagnostic {d!r}"
            for d in fatal
        )
        reasons.append(f"error diagnostic {txt}"[:300])
    return "; ".join(reasons) if reasons else None


def collect_units(report: dict, expected: list, required, key_of):
    """Generic completeness collection over one klt report.

    ``expected`` is a list of hashable unit keys; ``key_of(corner_id)`` maps a
    report corner id to such a key (raising on an unparseable id). ``required``
    are the measurement names every unit must return as finite numbers.

    -> (points, missing, failed, problems)

    points  : {key: {measurement: finite value}} for units with every required
              measurement.
    missing : [(key, reason)] absent units, or units lacking a finite required
              measurement (null / absent / NaN / inf), whatever klt's status.
    failed  : [(key, reason)] units whose execution is untrusted: klt status
              ``error`` / ``inconclusive`` / missing / unknown (only ``pass``
              and ``fail`` are accepted), any error/fatal diagnostic, or
              repeated measurement names (ambiguous payload, even if identical).
    problems: report-level issues (duplicate / unexpected / unparseable ids).
    """
    points, failed, missing, problems = {}, [], [], []
    seen = {}
    for c in report.get("corners", []):
        try:
            key = key_of(c["corner_id"])
        except Exception:
            problems.append(f"unparseable corner id {c.get('corner_id')!r}")
            continue
        if key in seen:
            problems.append(f"duplicate corner {key}")
        seen[key] = c
    expected_set = set(expected)
    for key in seen:
        if key not in expected_set:
            problems.append(f"unexpected corner {key}")
    for key in expected:
        c = seen.get(key)
        if c is None:
            missing.append((key, "absent from report"))
            continue
        names = [m["name"] for m in c.get("measurements", [])]
        dups = sorted({n for n in names if names.count(n) > 1}, key=str)
        if dups:
            failed.append((key, "ambiguous report: duplicate measurement name(s) " + ", ".join(map(repr, dups))))
            continue
        vals = {m["name"]: m.get("value") for m in c.get("measurements", [])}
        nonfinite = sorted(
            n for n, v in vals.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isfinite(v)
        )
        bad = [n for n in required if not is_finite_number(vals.get(n))]
        status = c.get("status")
        diag = diagnostics_text(c)
        rej = execution_rejection(c)
        if rej:
            failed.append((key, rej + (f" ({diag})" if diag and status == "error" and "error diagnostic" not in rej else "")))
            continue
        if bad:
            why = f"status={status}; measurement(s) without a finite value: " + ", ".join(bad)
            if nonfinite:
                why += " (non-finite: " + ", ".join(nonfinite) + ")"
            if diag:
                why += f" ({diag})"
            missing.append((key, why))
            continue
        points[key] = {k: v for k, v in vals.items() if is_finite_number(v)}
    return points, missing, failed, problems


def provenance_problems(report: dict, plan: dict | None, *, require_remote: bool = True) -> list[str]:
    """Why the report's provenance cannot back the plan that requested it.

    ``plan`` carries what the submitting side knew (``submitting_klt_version``);
    the report carries what ran. Missing or inconsistent versions are problems
    (the batch image can lag the submitting client and silently ignore request
    options), never silently accepted.
    """
    probs: list[str] = []
    env = report.get("environment") or {}
    remote = env.get("remote") or {}
    prov = report.get("provenance") or {}
    if require_remote:
        if not remote:
            probs.append("report has no environment.remote: not a fleet run")
        else:
            if remote.get("runner_compatibility") != COMPAT_OK:
                probs.append(
                    f"fleet runner klt compatibility is {remote.get('runner_compatibility')!r} "
                    f"(runner {remote.get('runner_klt_version')!r}, client {remote.get('client_klt_version')!r}); "
                    f"required {COMPAT_OK!r}"
                )
            if not remote.get("runner_klt_version"):
                probs.append("worker (runner) klt version not recorded")
            if not remote.get("client_klt_version"):
                probs.append("submitting (client) klt version not recorded")
    if not prov.get("klt_version"):
        probs.append("report provenance.klt_version missing")
    sub = (plan or {}).get("submitting_klt_version")
    client = remote.get("client_klt_version") or prov.get("klt_version")
    if sub and client and sub != client:
        probs.append(f"submitting klt version {sub!r} in the plan differs from the report's {client!r}")
    return probs


def hash_problems(plan: dict, *, dut_sha: str | None, tb_sha: str, manifest_sha: str, deck_sha: dict,
                  requests: dict[str, str] | None = None) -> list[str]:
    """Hash mismatches between what the plan froze and what is on disk now.

    ``deck_sha`` maps request name -> sha256 of the body.spice that is
    actually in the work dir (what the fleet was handed). ``requests`` maps
    request name -> exact text of its request.json; when supplied every
    planned request must be present and byte-identical to its frozen
    ``request_sha256`` (None skips the check, for callers with no work dir)."""
    probs = []
    if dut_sha is not None and plan.get("dut", {}).get("sha256") != dut_sha:
        probs.append(f"DUT sha256 {dut_sha[:12]} differs from the plan's {str(plan.get('dut', {}).get('sha256'))[:12]}")
    if plan.get("tb_netlist_sha256") != tb_sha:
        probs.append("testbench netlist changed since the request was generated")
    if plan.get("manifest_sha256") != manifest_sha:
        probs.append("tb.json changed since the request was generated")
    for r in plan.get("requests", []):
        got = deck_sha.get(r["name"])
        if got != r.get("deck_sha256"):
            probs.append(f"request {r['name']!r}: deck sha256 differs from the plan (edited after generation?)")
        if requests is None:
            continue
        want = r.get("request_sha256")
        if not want:
            probs.append(f"request {r['name']!r}: plan has no request_sha256 to verify request.json against")
        elif r["name"] not in requests:
            probs.append(f"request {r['name']!r}: request.json missing, cannot verify it against the plan")
        elif sha256_bytes(requests[r["name"]].encode()) != want:
            probs.append(f"request {r['name']!r}: request.json sha256 differs from the plan (edited after generation?)")
    return probs
