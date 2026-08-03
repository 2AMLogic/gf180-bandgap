#!/usr/bin/env python3
"""Format checker for the append-only evidence records under ``sim/``.

``sim/README.md`` is the authoritative convention for evidence records; this
module is its enforcement. It is deliberately independent of the code that
*writes* records (``sim/harness/report.py``) -- a checker that shared the
producer's rendering helpers could not notice the producer drifting away from
the ratified format.

    python3 sim/check_records.py                     # check the whole repo
    python3 sim/check_records.py --require-append-only

Run as step 4 of ``.github/scripts/lint.sh`` (so both ``npm run lint`` and the
CI ``lint`` job execute it). Stdlib only, no venv, matching the harness rule.

What is checked, per ``sim/<slug>/records/<record-id>.md``:

- the nine required fields from ``sim/README.md`` are present and non-empty;
- the filename is a well-formed ``<YYYYMMDD>-<HHMMSS>-<short-sha>`` and the
  **Record ID** field repeats it exactly;
- ``netlist-snapshots/<record-id>.spice`` and ``corners/<record-id>/`` exist,
  the latter holding at least one log;
- every ``corners/<record-id>/<corner-id>.log`` name parses under the
  corner-id grammar documented in ``sim/README.md`` (see ``parse_corner_id``);
- a **Supersedes** value that is not a "(none)" form names a record that
  exists in the same experiment directory;
- a record that is the *current head* of its supersession chain (nothing
  else in the experiment names it in a **Supersedes** field) carries at
  least as many ``corners/<record-id>/*.log`` files as the predecessor its
  own **Supersedes** field names -- a head record with fewer raw logs than
  the evidence it supersedes is not hand-checkable on its own terms, even
  though the directory itself is non-empty. A record that has since been
  superseded by a later head is not re-checked against this rule: once a
  fresh head exists, that is where a reader is directed for current,
  self-supporting evidence, and evidence is append-only (a defect in an
  already-committed, already-superseded record is fixed by minting a new
  head, not by editing the old one);
- nothing under ``records/``, ``netlist-snapshots/`` or ``corners/`` has been
  modified or deleted relative to the merge base -- evidence is append-only.

What is deliberately *not* checked: the prose inside a field (a record is a
human/agent-written argument, not a form), and files under ``corners/<id>/``
that are not ``*.log`` (the layout in ``sim/README.md`` names the logs; it
does not forbid a future sidecar artefact, and a checker that guessed here
would block legitimate evidence).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Layout constants -- kept in step with sim/harness/report.py, which writes
# into these directories, and with the layout diagram in sim/README.md.
RECORDS_DIR = "records"
SNAPSHOT_DIR = "netlist-snapshots"
CORNERS_DIR = "corners"

RECORD_SUFFIX = ".md"
SNAPSHOT_SUFFIX = ".spice"
LOG_SUFFIX = ".log"

#: The nine fields of the summary record format, in ``sim/README.md`` order.
REQUIRED_FIELDS: tuple[str, ...] = (
    "Record ID",
    "Claim",
    "Netlist provenance",
    "Corner matrix run",
    "Statistical convention",
    "Result",
    "Links",
    "Timestamp / author",
    "Supersedes",
)

#: ``<YYYYMMDD>-<HHMMSS>-<short-git-sha>``.
RECORD_ID_RE = re.compile(r"^(?P<date>\d{8})-(?P<time>\d{6})-(?P<sha>[0-9a-f]{7,40})$")
#: The same shape, found inside free text (used to read a Supersedes value).
RECORD_ID_IN_TEXT_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{7,40}")

#: A top-level record field: ``- **Name**: value``. Nested bullets (two-space
#: indented) are continuation of the field above, not new fields.
FIELD_RE = re.compile(r"^- \*\*(?P<name>[^*]+?)\*\*:(?P<value>.*)$")

#: Values that mean "this record supersedes nothing".
_NO_SUPERSESSION_RE = re.compile(r"^\(?\s*(none|n/?a)\b", re.IGNORECASE)

# --- corner-id grammar (sim/README.md) --------------------------------------
#
# `<process>_<temp>c_<supply>`, split on the *last two* underscores so the
# process field may itself carry a device-family prefix (`bjt_ff`,
# `res_typical`). The process vocabulary is deliberately open: gf180mcu names
# a model section per device family, so a device-level testbench selects
# `typical` / `bjt_ff` / `res_ss` rather than one of the harness's five MOS
# corner names.
_PROCESS_TOKEN_RE = re.compile(r"^[a-z][a-z0-9]*$")
#: Signed junction temperature in degrees C: `-40c`, `27c`, `125c`.
_TEMP_RE = re.compile(r"^-?\d+(?:\.\d+)?c$")
#: `2.97v`, or `nwell2p97v` when the swept rail needs naming (`p` stands in
#: for the decimal point so the field stays a single underscore-free token).
_SUPPLY_RE = re.compile(r"^(?P<node>[a-z]+)?(?P<volts>\d+(?:[.p]\d+)?)v$")
#: A testbench with no supply rail to sweep (device testbenches drive the DUT
#: from an ideal source). The record's Corner matrix run field must say why.
NO_SUPPLY = "nosupply"

#: ``sim/<slug>/<evidence-dir>/<rest>``.
EVIDENCE_PATH_RE = re.compile(
    r"^sim/(?P<slug>[^/]+)/(?P<kind>%s)/(?P<rest>.+)$"
    % "|".join(re.escape(d) for d in (RECORDS_DIR, SNAPSHOT_DIR, CORNERS_DIR))
)


@dataclass(frozen=True)
class Problem:
    """One failure, reported as ``<path>: <message>``."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


@dataclass
class RecordField:
    """One ``- **Name**: value`` field plus its indented continuation lines."""

    name: str
    line: int
    inline: str
    continuation: list[str] = field(default_factory=list)

    @property
    def value(self) -> str:
        parts = [self.inline.strip()] + [line.strip() for line in self.continuation]
        return "\n".join(part for part in parts if part)


@dataclass
class Experiment:
    """The evidence tree of one ``sim/<slug>/`` experiment directory."""

    slug: str
    records: dict = field(default_factory=dict)      # record-id -> repo path
    snapshots: dict = field(default_factory=dict)    # record-id -> repo path
    corner_files: dict = field(default_factory=dict)  # record-id -> [basename]
    strays: list = field(default_factory=list)       # [Problem]


# --- parsing ----------------------------------------------------------------


def parse_fields(text: str) -> tuple[dict, list[str]]:
    """Split a record body into its top-level fields.

    Returns ``(fields, duplicate_names)``. A field's value is its inline text
    plus every indented line up to the next top-level line, so multi-line
    fields (Corner matrix run, Result, Links) are read whole.
    """
    fields: dict = {}
    duplicates: list[str] = []
    current: RecordField | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = FIELD_RE.match(line)
        if match:
            name = match.group("name").strip()
            current = RecordField(name=name, line=number, inline=match.group("value"))
            if name in fields:
                duplicates.append(name)
            else:
                fields[name] = current
            continue
        if current is None or not line.strip():
            continue
        if line[:1].isspace():
            current.continuation.append(line)
        else:
            current = None  # a heading, rule, or paragraph ends the field block
    return fields, duplicates


def validate_record_id(record_id: str) -> str | None:
    """``None`` if ``record_id`` is well formed, else why it is not."""
    match = RECORD_ID_RE.match(record_id)
    if not match:
        return (
            f"{record_id!r} is not a <YYYYMMDD>-<HHMMSS>-<short-git-sha> record id"
        )
    try:
        _dt.datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")
    except ValueError:
        return f"{record_id!r} carries an impossible date/time"
    return None


def parse_corner_id(corner_id: str) -> str | None:
    """``None`` if ``corner_id`` parses, else why it does not.

    The grammar is the one documented in ``sim/README.md``::

        <corner-id> ::= <process> "_" <temp> "c" "_" <supply>
        <process>   ::= token ("_" token)*        # tt, ss, bjt_ff, res_typical
        <temp>      ::= "-"? digits ("." digits)? # -40c, 27c, 125c
        <supply>    ::= "nosupply" | node? volts "v"   # 2.97v, nwell2p97v

    Splitting on the *last two* underscores is what lets the process field
    carry a device-family prefix; neither temp nor supply may contain one.
    """
    parts = corner_id.split("_")
    if len(parts) < 3:
        return (
            f"{corner_id!r} does not parse as <process>_<temp>c_<supply> "
            "(see the corner-id grammar in sim/README.md)"
        )
    process, temp, supply = parts[:-2], parts[-2], parts[-1]
    if not all(_PROCESS_TOKEN_RE.match(token) for token in process):
        return (
            f"{corner_id!r}: process field {'_'.join(process)!r} is not one or more "
            "lowercase alphanumeric tokens (tt, ss, bjt_ff, res_typical, ...)"
        )
    if not _TEMP_RE.match(temp):
        return (
            f"{corner_id!r}: temperature field {temp!r} is not a signed number "
            "followed by 'c' (-40c, 27c, 125c)"
        )
    if supply != NO_SUPPLY and not _SUPPLY_RE.match(supply):
        return (
            f"{corner_id!r}: supply field {supply!r} is neither <volts>v / "
            f"<node><volts>v (2.97v, nwell2p97v) nor the literal {NO_SUPPLY!r}"
        )
    return None


# --- collection -------------------------------------------------------------


def collect_experiments(paths) -> dict:
    """Group repo-relative paths into per-experiment evidence trees."""
    experiments: dict = {}
    for path in sorted(paths):
        match = EVIDENCE_PATH_RE.match(path)
        if not match:
            continue
        experiment = experiments.setdefault(
            match.group("slug"), Experiment(match.group("slug"))
        )
        kind, rest = match.group("kind"), match.group("rest")
        if kind == RECORDS_DIR:
            if "/" in rest:
                experiment.strays.append(
                    Problem(path, f"{RECORDS_DIR}/ holds one flat <record-id>.md per run")
                )
            elif rest.endswith(RECORD_SUFFIX):
                experiment.records[rest[: -len(RECORD_SUFFIX)]] = path
        elif kind == SNAPSHOT_DIR:
            if "/" in rest:
                experiment.strays.append(
                    Problem(
                        path,
                        f"{SNAPSHOT_DIR}/ holds one flat <record-id>{SNAPSHOT_SUFFIX} per run",
                    )
                )
            elif rest.endswith(SNAPSHOT_SUFFIX):
                experiment.snapshots[rest[: -len(SNAPSHOT_SUFFIX)]] = path
        else:
            parts = rest.split("/")
            if len(parts) != 2:
                experiment.strays.append(
                    Problem(
                        path,
                        f"{CORNERS_DIR}/ holds one <record-id>/ directory of logs per run",
                    )
                )
            else:
                experiment.corner_files.setdefault(parts[0], []).append(parts[1])
    return experiments


def list_evidence_paths(root: Path) -> tuple[list, str]:
    """Repo-relative evidence paths, plus a one-word description of the source.

    Tracked files only (``git ls-files``, same exclusions as ``collect()`` in
    ``.github/scripts/lint.sh``) so generated or ignored artefacts are never
    linted. Falls back to a filesystem walk outside a git checkout.
    """
    completed = _git(
        root,
        "ls-files",
        "-z",
        "--",
        "sim",
        ":!:.loom/**",
        ":!:.claude/**",
    )
    if completed is not None and completed.returncode == 0:
        paths = [p for p in completed.stdout.split("\0") if p]
        return paths, "tracked files"
    sim_dir = root / "sim"
    paths = [
        str(p.relative_to(root)).replace(os.sep, "/")
        for p in sorted(sim_dir.rglob("*"))
        if p.is_file()
    ]
    return paths, "filesystem walk (not a git checkout)"


# --- record checks ----------------------------------------------------------


def _resolve_supersedes_target(
    value: str, record_id: str, experiment: Experiment
) -> str | None:
    """The one record-id ``value`` names within ``experiment``, if any.

    ``None`` for a "(none)" form, prose with no record-id, a self-reference,
    or a reference to a record outside this experiment -- all of those are
    reported by ``_check_supersedes`` already; this helper only needs the
    happy path a log-count comparison can act on.
    """
    if _NO_SUPERSESSION_RE.match(value):
        return None
    for other in RECORD_ID_IN_TEXT_RE.findall(value):
        if other != record_id and other in experiment.records:
            return other
    return None


def _superseded_record_ids(root: Path, experiment: Experiment) -> set[str]:
    """Record ids named in some *other* record's **Supersedes** field.

    A record in this set is no longer the head of its supersession chain --
    a later record has already taken over as the current, citable evidence
    for the claim, so the log-count-vs-predecessor check in ``check_record``
    does not re-litigate it (see that check's docstring note on why).
    """
    superseded: set[str] = set()
    for record_id, path in experiment.records.items():
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fields, _ = parse_fields(text)
        supersedes = fields.get("Supersedes")
        if supersedes is None or not supersedes.value:
            continue
        target = _resolve_supersedes_target(supersedes.value, record_id, experiment)
        if target:
            superseded.add(target)
    return superseded


def check_record(
    root: Path,
    experiment: Experiment,
    record_id: str,
    superseded_ids: frozenset = frozenset(),
) -> list:
    """Every problem with one ``records/<record-id>.md`` and its siblings."""
    path = experiment.records[record_id]
    problems: list = []

    reason = validate_record_id(record_id)
    if reason:
        problems.append(Problem(path, f"filename: {reason}"))

    try:
        text = (root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return problems + [Problem(path, f"unreadable: {exc}")]

    fields, duplicates = parse_fields(text)
    for name in duplicates:
        problems.append(Problem(path, f"field **{name}** appears more than once"))
    for name in REQUIRED_FIELDS:
        found = fields.get(name)
        if found is None:
            problems.append(
                Problem(path, f"missing required field **{name}** (see sim/README.md)")
            )
        elif not found.value:
            problems.append(
                Problem(path, f"required field **{name}** is empty (line {found.line})")
            )

    declared = fields.get("Record ID")
    if declared is not None and declared.value and declared.value != record_id:
        problems.append(
            Problem(
                path,
                f"**Record ID** is {declared.value!r} but the filename says {record_id!r}",
            )
        )

    supersedes = fields.get("Supersedes")
    if supersedes is not None and supersedes.value:
        problems += _check_supersedes(path, experiment, record_id, supersedes.value)

    if record_id not in experiment.snapshots:
        problems.append(
            Problem(
                path,
                f"no frozen netlist at sim/{experiment.slug}/{SNAPSHOT_DIR}/"
                f"{record_id}{SNAPSHOT_SUFFIX}",
            )
        )

    corner_dir = f"sim/{experiment.slug}/{CORNERS_DIR}/{record_id}/"
    names = experiment.corner_files.get(record_id, [])
    logs = [name for name in names if name.endswith(LOG_SUFFIX)]
    if not names:
        problems.append(Problem(path, f"no raw per-corner logs at {corner_dir}"))
    elif not logs:
        problems.append(
            Problem(path, f"{corner_dir} holds no <corner-id>{LOG_SUFFIX} file")
        )
    for name in sorted(logs):
        reason = parse_corner_id(name[: -len(LOG_SUFFIX)])
        if reason:
            problems.append(Problem(corner_dir + name, reason))

    if record_id not in superseded_ids and supersedes is not None and supersedes.value:
        predecessor = _resolve_supersedes_target(supersedes.value, record_id, experiment)
        if predecessor is not None:
            predecessor_logs = [
                name
                for name in experiment.corner_files.get(predecessor, [])
                if name.endswith(LOG_SUFFIX)
            ]
            if len(logs) < len(predecessor_logs):
                problems.append(
                    Problem(
                        path,
                        f"{corner_dir} holds {len(logs)} log(s), fewer than its "
                        f"Supersedes predecessor {predecessor} "
                        f"({len(predecessor_logs)} log(s)) -- the current head "
                        "of a supersession chain must carry at least as many "
                        "raw per-corner logs as the record it supersedes, so it "
                        "stays hand-checkable on its own (sim/README.md); mint "
                        "a fresh record with the missing logs rather than "
                        "editing this one (evidence is append-only)",
                    )
                )

    return problems


def _check_supersedes(
    path: str, experiment: Experiment, record_id: str, value: str
) -> list:
    if _NO_SUPERSESSION_RE.match(value):
        return []
    referenced = RECORD_ID_IN_TEXT_RE.findall(value)
    if not referenced:
        return [
            Problem(
                path,
                "**Supersedes** names no <record-id>; say '(none)' when this "
                "record supersedes nothing",
            )
        ]
    problems = []
    for other in referenced:
        if other == record_id:
            problems.append(Problem(path, "**Supersedes** points at this record itself"))
        elif other not in experiment.records:
            problems.append(
                Problem(
                    path,
                    f"**Supersedes** names {other}, which has no record at "
                    f"sim/{experiment.slug}/{RECORDS_DIR}/{other}{RECORD_SUFFIX}",
                )
            )
    return problems


def check_experiments(root: Path, experiments: dict) -> list:
    """Every problem across every experiment, in a stable order."""
    problems: list = []
    for slug in sorted(experiments):
        experiment = experiments[slug]
        problems += experiment.strays
        superseded_ids = _superseded_record_ids(root, experiment)
        for record_id in sorted(experiment.records):
            problems += check_record(root, experiment, record_id, superseded_ids)
        # Orphans: evidence with no record is evidence nobody can cite.
        for record_id in sorted(experiment.snapshots):
            if record_id not in experiment.records:
                problems.append(
                    Problem(
                        experiment.snapshots[record_id],
                        f"orphan: no summary record at sim/{slug}/{RECORDS_DIR}/"
                        f"{record_id}{RECORD_SUFFIX}",
                    )
                )
        for record_id in sorted(experiment.corner_files):
            if record_id not in experiment.records:
                problems.append(
                    Problem(
                        f"sim/{slug}/{CORNERS_DIR}/{record_id}/",
                        f"orphan: no summary record at sim/{slug}/{RECORDS_DIR}/"
                        f"{record_id}{RECORD_SUFFIX}",
                    )
                )
    return problems


# --- append-only check ------------------------------------------------------


def _git(root: Path, *args: str):
    try:
        return subprocess.run(
            ("git", *args),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return None


def default_base_ref() -> str:
    """The ref a PR is diffed against: the PR base branch, else origin/main."""
    base = os.environ.get("GITHUB_BASE_REF", "").strip()
    return f"origin/{base}" if base else "origin/main"


def check_append_only(root: Path, base_ref: str) -> tuple[list, str | None]:
    """Evidence modified or deleted since the merge base with ``base_ref``.

    Returns ``(problems, skip_reason)``; ``skip_reason`` is set when the check
    could not run at all (no git, no such ref, unrelated histories) so the
    caller can decide between SKIP and failing.

    The comparison is merge-base vs the *working tree*, not vs ``base_ref``
    itself: unrelated commits landing on main after this branch's point must
    not read as this branch modifying evidence, and an uncommitted edit to a
    committed record is exactly the mistake this check exists to catch.
    """
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside is None:
        return [], "git is not available"
    if inside.returncode != 0:
        return [], f"{root} is not a git checkout"
    head = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if head is None or head.returncode != 0:
        return [], "no commits to compare (unborn HEAD)"
    resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}")
    if resolved is None or resolved.returncode != 0:
        return [], (
            f"{base_ref} does not resolve here (shallow clone, or no such remote "
            "branch) -- run `git fetch origin main` for the full check"
        )
    merge_base = _git(root, "merge-base", base_ref, "HEAD")
    if merge_base is None or merge_base.returncode != 0:
        return [], f"no merge base between HEAD and {base_ref}"
    base_sha = merge_base.stdout.strip()

    # --no-renames so a rename surfaces as delete+add and trips the D filter;
    # git's rename detection would otherwise hide it behind an R status.
    diff = _git(
        root,
        "diff",
        "--name-status",
        "--no-renames",
        "--diff-filter=MD",
        base_sha,
        "--",
        "sim",
    )
    if diff is None or diff.returncode != 0:
        return [], "git diff against the merge base failed"

    verb = {"M": "modified", "D": "deleted"}
    problems = []
    for line in diff.stdout.splitlines():
        status, _, path = line.partition("\t")
        path = path.strip()
        if not path or not EVIDENCE_PATH_RE.match(path):
            continue
        problems.append(
            Problem(
                path,
                f"{verb.get(status[:1], status)} since {base_sha[:7]} -- sim/ evidence "
                "is append-only: mint a new <record-id> and reference the old one "
                "via **Supersedes** (sim/README.md)",
            )
        )
    return problems, None


# --- CLI --------------------------------------------------------------------


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_records.py",
        description="Check sim/ evidence records against sim/README.md.",
    )
    parser.add_argument(
        "--root", default=None, help="repo root to check (default: this checkout)"
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="ref the append-only check diffs against (default: $GITHUB_BASE_REF, "
        "else origin/main)",
    )
    parser.add_argument(
        "--require-append-only",
        action="store_true",
        help="fail, instead of skipping, when the append-only check cannot run",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="do not list the records that were checked"
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else default_root()
    paths, source = list_evidence_paths(root)
    experiments = collect_experiments(paths)
    record_count = sum(len(e.records) for e in experiments.values())
    print(
        f"{record_count} record(s) across {len(experiments)} experiment(s) "
        f"[{source}]"
    )
    if not args.quiet:
        for slug in sorted(experiments):
            for record_id in sorted(experiments[slug].records):
                print(f"  {experiments[slug].records[record_id]}")

    problems = check_experiments(root, experiments)

    base_ref = args.base_ref or default_base_ref()
    append_only_problems, skip_reason = check_append_only(root, base_ref)
    if skip_reason is None:
        if not append_only_problems:
            print(f"append-only: clean against the merge base with {base_ref}")
    elif args.require_append_only:
        problems.append(
            Problem("", f"append-only check could not run: {skip_reason}")
        )
    else:
        print(f"SKIP: append-only check -- {skip_reason}")
    problems += append_only_problems

    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
