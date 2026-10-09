#!/usr/bin/env python3
"""Check sim/suite/spec.py limits against the ratified README spec table.

    python3 sim/check_spec_limits.py

The ratified numbers live in README.md's "Target specification" table.
sim/suite/spec.py (and each bench's tb.json) restate them as pass/fail
limits; the only other drift guard compares those two copies to each other.
This check closes the chain: it parses the numeric Target cell of each gated
row and fails -- naming the row, the README value and the spec.py value -- if
the suite's limits disagree. Rows whose target is TBD (Output noise, Load)
are skipped. Stdlib only, no PDK.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOL = 1e-9

# README row-name prefix -> (SpecLine keys that carry it,
#                            {measurement: kind}, how to read the Target cell)
#   "window": "<nominal> <unit> +/-<pct>%"  -> min/max = nominal*(1 -/+ pct/100)
#   "max":    "< <n> <unit>"                -> kind "max" at n
#   "min":    "> <n> <unit>"                -> kind "min" at n
ROWS = (
    ("Output reference", "window", ("output-reference", "supply-range"),
     {"vref"}),
    ("Temp coefficient", "max", ("temp-coefficient",), {"tc_ppm"}),
    ("PSRR", "min", ("psrr",), {"psrr_1hz_db", "psrr_1khz_db"}),
    ("Line regulation", "max", ("line-regulation",), {"linereg_mv_per_v"}),
    ("Quiescent current", "max", ("quiescent-current",), {"iq_ua"}),
)

_NUM = r"(\d+(?:\.\d+)?)"
_WINDOW = re.compile(_NUM + r"\s*V\s*(?:±|\+/-)\s*" + _NUM + r"\s*%")
_BOUND = re.compile(r"^\s*([<>])\s*" + _NUM)


def _section(text: str) -> list[str]:
    """Lines of the table under the 'Target specification' heading."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("#") and "Target specification" in ln), None)
    if start is None:
        raise ValueError("README has no 'Target specification' heading")
    rows = []
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        if ln.lstrip().startswith("|"):
            rows.append(ln)
    return rows


def parse_readme(text: str) -> dict[str, str]:
    """Map README parameter name -> Target cell text."""
    out: dict[str, str] = {}
    for ln in _section(text):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("Parameter",) or set(cells[0]) <= set("-: "):
            continue
        out[cells[0]] = cells[1]
    return out


def readme_bounds(name: str, mode: str, target: str) -> dict[str, float]:
    """Numeric bounds a Target cell states, as {'min'|'max': value}."""
    if mode == "window":
        m = _WINDOW.search(target)
        if not m:
            raise ValueError(f"cannot parse window from {target!r}")
        nominal, pct = float(m.group(1)), float(m.group(2))
        return {"min": nominal * (1 - pct / 100), "max": nominal * (1 + pct / 100)}
    m = _BOUND.match(target)
    if not m:
        raise ValueError(f"cannot parse bound from {target!r}")
    kind = "max" if m.group(1) == "<" else "min"
    if kind != mode:
        raise ValueError(f"expected a '{mode}' bound, README says {target!r}")
    return {kind: float(m.group(2))}


def check(readme_text: str, suite) -> list[str]:
    """Return a list of mismatch descriptions (empty means in agreement)."""
    problems: list[str] = []
    table = parse_readme(readme_text)
    by_key = {line.key: line for line in suite}
    for prefix, mode, keys, measurements in ROWS:
        name = next((n for n in table if n.startswith(prefix)), None)
        if name is None:
            problems.append(f"{prefix}: row not found in README table")
            continue
        try:
            want = readme_bounds(name, mode, table[name])
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
            continue
        for key in keys:
            line = by_key.get(key)
            if line is None:
                problems.append(f"{name}: spec.py has no SpecLine {key!r}")
                continue
            got = {(lim.measurement, lim.kind): lim.value for lim in line.limits}
            expected_meas = {"vref_min", "vref_max"} if key == "supply-range" \
                else measurements
            seen = {m for m, _ in got}
            if seen != expected_meas:
                problems.append(
                    f"{name} [{key}]: spec.py gates {sorted(seen)}, "
                    f"expected {sorted(expected_meas)}")
            for (meas, kind), value in got.items():
                if kind not in want:
                    problems.append(
                        f"{name} [{key}]: spec.py has a {kind} limit on {meas} "
                        f"({value:g}) the README does not state")
                elif abs(value - want[kind]) > TOL:
                    problems.append(
                        f"{name} [{key}]: README {kind} {want[kind]:g} "
                        f"!= spec.py {meas} {kind} {value:g}")
            for kind, value in want.items():
                if not any(k == kind for _, k in got):
                    problems.append(
                        f"{name} [{key}]: README {kind} {value:g} "
                        f"has no {kind} limit in spec.py")
    return problems


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from sim.suite import spec  # noqa: E402  (stdlib-only module)

    readme = REPO_ROOT / "README.md"
    problems = check(readme.read_text(encoding="utf-8"), spec.SUITE)
    for p in problems:
        print(f"MISMATCH: {p}")
    if problems:
        return 1
    print(f"ok: {len(ROWS)} README spec rows agree with sim/suite/spec.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
