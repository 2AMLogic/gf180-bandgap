#!/usr/bin/env python3
"""Lint the decision records under spec/decision-records/.

CLAUDE.md says spec changes go through a decision record and that agents do
not relax the ratified spec; spec/README.md says a ratified record "is never
deleted or rewritten". This makes both mechanical. Checks:

  1. filenames are NNNN-<slug>.md, numbering is contiguous from 0001, no
     duplicate NNNN;
  2. the `- **Status**:` line starts with proposed | ratified |
     superseded by NNNN (case-insensitive, free-text suffix allowed) and a
     `superseded by` target exists (bare `0006` or `[0006](file.md)`);
  3. `Date` is present on every record; `Decided by` on every record numbered
     above GRANDFATHERED_NO_DECIDED_BY (0001 carries `Author`, 0002 neither,
     and ratified records must not be edited to add one);
  4. the index table in spec/README.md has exactly one row per record and the
     row's normalized status (keyword + supersession target) matches;
  5. immutability against the merge base with origin/main: a record that was
     `ratified` on the base must still exist and be byte-identical, except
     its Status entry may become `superseded by NNNN` (NNNN existing).

  python3 spec/check_decision_records.py                      # skip 5 if no base
  python3 spec/check_decision_records.py --require-append-only  # fail instead

Stdlib-only. Exit codes: 0 pass, 1 a check failed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPEC_DIR.parent
RECORDS_REL = "spec/decision-records"
README_REL = "spec/README.md"

# Records that predate the `Decided by` field; they are ratified, so they
# cannot be edited to add it.
GRANDFATHERED_NO_DECIDED_BY = 2

FILENAME_RE = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
STATUS_START_RE = re.compile(r"^- \*\*Status\*\*:[ \t]*(.*)$")
FIELD_START_RE = re.compile(r"^- \*\*")
SUPERSEDED_RE = re.compile(r"^superseded\s+by\s+\[?(\d{4})\b")
KEYWORD_RE = re.compile(r"^(proposed|ratified)\b")
INDEX_ROW_RE = re.compile(r"^\|\s*\[(\d{4})\]\([^)]*\)\s*\|.*\|\s*([^|]*?)\s*\|\s*$")

Status = tuple  # (keyword, target-or-None)


def parse_status_text(raw: str) -> Status | None:
    """Normalize free-form status text to (keyword, supersession target)."""
    text = raw.strip().lstrip("*_`").strip().lower()
    m = SUPERSEDED_RE.match(text)
    if m:
        return ("superseded", m.group(1))
    m = KEYWORD_RE.match(text)
    if m:
        return (m.group(1), None)
    return None


def _status_span(lines: list[str]) -> tuple[int, int] | None:
    """[start, end) line span of the Status bullet incl. continuation lines."""
    for i, line in enumerate(lines):
        if STATUS_START_RE.match(line):
            end = i + 1
            while (
                end < len(lines)
                and lines[end].strip()
                and not FIELD_START_RE.match(lines[end])
            ):
                end += 1
            return i, end
    return None


def record_status(text: str) -> tuple[Status | None, bool]:
    """(normalized status or None if unparseable, Status line present)."""
    lines = text.splitlines()
    span = _status_span(lines)
    if span is None:
        return None, False
    first = STATUS_START_RE.match(lines[span[0]]).group(1)
    joined = " ".join([first] + [ln.strip() for ln in lines[span[0] + 1 : span[1]]])
    return parse_status_text(joined), True


def strip_status(text: str) -> str:
    lines = text.splitlines()
    span = _status_span(lines)
    if span is None:
        return text
    return "\n".join(lines[: span[0]] + ["<STATUS>"] + lines[span[1] :])


def _has_field(text: str, name: str) -> bool:
    return re.search(rf"^- \*\*{re.escape(name)}\*\*:", text, re.M) is not None


def check_records(records: dict[str, str]) -> list[str]:
    """Checks 1-3 over {filename: text}."""
    problems: list[str] = []
    numbers: dict[str, list[str]] = {}
    for name in sorted(records):
        m = FILENAME_RE.match(name)
        if not m:
            problems.append(f"{name}: filename is not NNNN-<slug>.md (lowercase slug)")
            continue
        numbers.setdefault(m.group(1), []).append(name)
    for num, names in sorted(numbers.items()):
        if len(names) > 1:
            problems.append(f"duplicate record number {num}: {', '.join(names)}")
    if numbers:
        top = max(int(n) for n in numbers)
        for n in range(1, top + 1):
            if f"{n:04d}" not in numbers:
                problems.append(f"numbering gap: no record {n:04d} (highest is {top:04d})")

    for name in sorted(records):
        m = FILENAME_RE.match(name)
        if not m:
            continue
        text = records[name]
        status, present = record_status(text)
        if not present:
            problems.append(f"{name}: missing `- **Status**:` line")
        elif status is None:
            problems.append(
                f"{name}: Status must begin with proposed | ratified | superseded by NNNN"
            )
        elif status[0] == "superseded" and status[1] not in numbers:
            problems.append(f"{name}: superseded by {status[1]}, which does not exist")
        elif status[0] == "superseded" and status[1] == m.group(1):
            problems.append(f"{name}: superseded by itself")
        if not _has_field(text, "Date"):
            problems.append(f"{name}: missing `- **Date**:` field")
        if int(m.group(1)) > GRANDFATHERED_NO_DECIDED_BY and not _has_field(
            text, "Decided by"
        ):
            problems.append(f"{name}: missing `- **Decided by**:` field")
    return problems


def parse_index(readme: str) -> tuple[dict[str, list[Status | None]], list[str]]:
    rows: dict[str, list[Status | None]] = {}
    for line in readme.splitlines():
        m = INDEX_ROW_RE.match(line)
        if m:
            rows.setdefault(m.group(1), []).append(parse_status_text(m.group(2)))
    return rows, []


def check_index(records: dict[str, str], readme: str) -> list[str]:
    problems: list[str] = []
    rows, _ = parse_index(readme)
    by_num = {}
    for name, text in records.items():
        m = FILENAME_RE.match(name)
        if m:
            by_num[m.group(1)] = text
    for num in sorted(by_num):
        if num not in rows:
            problems.append(f"{README_REL}: index has no row for {num}")
    for num, entries in sorted(rows.items()):
        if num not in by_num:
            problems.append(f"{README_REL}: index row {num} has no record")
            continue
        if len(entries) > 1:
            problems.append(f"{README_REL}: index has {len(entries)} rows for {num}")
        want, _ = record_status(by_num[num])
        for got in entries:
            if got != want:
                problems.append(
                    f"{README_REL}: index status for {num} is {_fmt(got)} but the "
                    f"record says {_fmt(want)}"
                )
    return problems


def _fmt(status: Status | None) -> str:
    if status is None:
        return "unparseable"
    return status[0] if status[1] is None else f"{status[0]} by {status[1]}"


def check_immutable(current: dict[str, str], base: dict[str, str]) -> list[str]:
    """Check 5 over {filename: text} dicts (no git)."""
    problems: list[str] = []
    for name in sorted(base):
        base_status, _ = record_status(base[name])
        if base_status is None or base_status[0] != "ratified":
            continue
        if name not in current:
            problems.append(f"{name}: ratified record deleted or renamed")
            continue
        if current[name] == base[name]:
            continue
        cur_status, _ = record_status(current[name])
        cur_num = {FILENAME_RE.match(n).group(1) for n in current if FILENAME_RE.match(n)}
        if cur_status is None or cur_status[0] != "superseded":
            problems.append(
                f"{name}: ratified record modified (only a move to "
                "`superseded by NNNN` is allowed); supersede it with a new record"
            )
        elif cur_status[1] not in cur_num:
            problems.append(f"{name}: superseded by {cur_status[1]}, which does not exist")
        elif strip_status(current[name]) != strip_status(base[name]):
            problems.append(
                f"{name}: ratified record body modified alongside the Status change "
                "(only the Status entry may change)"
            )
    return problems


# --- git glue ---------------------------------------------------------------


def _git(root: Path, *args: str):
    try:
        return subprocess.run(
            ("git", *args), cwd=str(root), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, check=False,
        )
    except OSError:
        return None


def default_base_ref() -> str:
    base = os.environ.get("GITHUB_BASE_REF", "").strip()
    return f"origin/{base}" if base else "origin/main"


def load_base_records(root: Path, base_ref: str) -> tuple[dict[str, str] | None, str | None]:
    """({filename: text} at the merge base, skip_reason)."""
    resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}")
    if resolved is None:
        return None, "git is not available"
    if resolved.returncode != 0:
        return None, f"{base_ref} does not resolve here (run `git fetch origin main`)"
    mb = _git(root, "merge-base", base_ref, "HEAD")
    if mb is None or mb.returncode != 0:
        return None, f"no merge base between HEAD and {base_ref}"
    sha = mb.stdout.strip()
    ls = _git(root, "ls-tree", "--name-only", sha, f"{RECORDS_REL}/")
    if ls is None or ls.returncode != 0:
        return None, "git ls-tree against the merge base failed"
    out: dict[str, str] = {}
    for path in ls.stdout.splitlines():
        name = path.rsplit("/", 1)[-1]
        if not name.endswith(".md") or name == "TEMPLATE.md":
            continue
        show = _git(root, "show", f"{sha}:{path}")
        if show is None or show.returncode != 0:
            return None, f"git show {sha[:7]}:{path} failed"
        out[name] = show.stdout
    return out, None


def load_records(directory: Path) -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(directory.glob("*.md"))
        if p.name != "TEMPLATE.md"
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--base-ref", default=default_base_ref())
    ap.add_argument("--require-append-only", action="store_true",
                    help="fail (instead of skipping) when the merge base is unavailable")
    args = ap.parse_args(argv)

    root: Path = args.root
    records = load_records(root / RECORDS_REL)
    readme = (root / README_REL).read_text(encoding="utf-8")
    problems = check_records(records) + check_index(records, readme)

    base, skip = load_base_records(root, args.base_ref)
    if base is None:
        if args.require_append_only:
            problems.append(f"immutability check could not run: {skip} (--require-append-only)")
        else:
            print(f"SKIP: ratified-record immutability check: {skip}")
    else:
        problems += check_immutable(records, base)

    for p in problems:
        print(p)
    print(f"{len(records)} decision record(s) checked; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
