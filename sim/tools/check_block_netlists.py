#!/usr/bin/env python3
"""Static check: per-block netlists match their cells in bandgap_top.spice (#475).

``design/netlist/`` holds one xschem export per block next to the canonical
top export.  Only two of them feed a tool (``bandgap_top.spice`` -> sim/dut/
via mk_dut.py; ``bandgap_amp.spice`` -> the amp DUT source); the rest exist
to be read -- by reviewers (design/README.md's reviewable-in-git posture)
and by the sim/*/netlist-snapshots/ records that cite them as provenance
(#393).  Nothing regenerated them, so they lied: #475 found ten of
bandgap_core.spice's seventeen device statements contradicting the very
schematic the top export came from.  This check turns that drift into a lint
failure, comparing -- from the committed files alone, no xschem, no PDK:

  * each block export exists and carries its own cell.  xschem comments the
    netlisted-top wrapper to ``**.subckt``/``**.ends`` (the same form
    mk_dut.py uncomments), so both the wrapper and a plain ``.subckt``
    count as a cell;
  * the ordered pin list matches the same-named ``.subckt`` in the top
    export;
  * the ordered device statements match once ``+`` continuation lines are
    joined (comments and whitespace are not compared, so a comments-only
    edit still passes);
  * ``.param`` defaults match wherever xschem emitted them: the standalone
    trim carries ``.param trim_code=...`` at file level ahead of its
    wrapper, while the top export nests the default inside the subcircuit
    -- both placements are read and the values compared;
  * further cells an export expands on the way down (bandgap_core.spice
    carries a full bandgap_trim) are compared against the same-named top
    definition too, each cell separately.

    python3 sim/tools/check_block_netlists.py

Exit 0 = every block in sync, 1 = drift (every error names its file, and
the cell or block it is about).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOP_DEFAULT = REPO / "design" / "netlist" / "bandgap_top.spice"
EXPORT_DIR_DEFAULT = REPO / "design" / "netlist"

#: The per-block exports the operator ruling keeps (#475): cell
#: ``bandgap_<block>`` lives in ``design/netlist/bandgap_<block>.spice``.
BLOCKS = ("core", "amp", "startup", "trim")

#: xschem's commented-out top-cell wrapper -- the same form mk_dut.py
#: uncomments.  Here it is a real boundary, not a comment to drop.
COMMENTED_WRAPPER_RE = re.compile(r"^\*\*(\.(?:subckt|ends)\b.*)$", re.IGNORECASE)

SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s*(.*)$", re.IGNORECASE)
ENDS_RE = re.compile(r"^\.ends\b", re.IGNORECASE)
PARAM_RE = re.compile(r"^\.param\b\s*(.*)$", re.IGNORECASE)
ASSIGN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S+)")


class Cell:
    """One subcircuit found in an export: ordered pins, devices, params."""

    def __init__(self, name: str, pins: list[str]) -> None:
        self.name = name
        self.pins = pins
        self.devices: list[tuple[str, ...]] = []
        self.params: dict[str, str] = {}

    def visible_params(self, file_params: dict[str, str]) -> dict[str, str]:
        """Params this cell sees: file-level defaults, overridden in-body."""
        merged = dict(file_params)
        merged.update(self.params)
        return merged


def parse_export(text: str) -> tuple[dict[str, Cell], dict[str, str], list[str]]:
    """Parse one xschem export into ``(cells, file_params, problems)``.

    ``cells`` is insertion-ordered (file order).  ``file_params`` are the
    ``.param`` assignments outside any cell -- xschem hoists the netlisted
    top's architecture code there (the standalone trim's trim_code default).
    ``problems`` are structural failures in their own right: an orphan
    continuation, a device outside any cell, nested or unbalanced subckts,
    duplicate cell names.
    """
    cells: dict[str, Cell] = {}
    file_params: dict[str, str] = {}
    problems: list[str] = []
    current: Cell | None = None
    logical: list[tuple[int, str]] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("+"):
            if not logical:
                problems.append(f"line {lineno}: continuation with no statement to continue")
                continue
            logical[-1] = (logical[-1][0], logical[-1][1] + " " + line[1:].strip())
            continue
        wrapper = COMMENTED_WRAPPER_RE.match(line)
        if wrapper:
            line = wrapper.group(1).strip()
        elif line.startswith("*"):
            continue  # any other comment: dropped, never compared
        logical.append((lineno, line))

    for lineno, stmt in logical:
        subckt = SUBCKT_RE.match(stmt)
        if subckt:
            name = subckt.group(1)
            if current is not None:
                problems.append(f"line {lineno}: .subckt {name} nested inside {current.name}")
                continue
            if name in cells:
                problems.append(f"line {lineno}: duplicate .subckt {name}")
                continue
            current = Cell(name, subckt.group(2).split())
            cells[name] = current
            continue
        if ENDS_RE.match(stmt):
            if current is None:
                problems.append(f"line {lineno}: .ends with no open .subckt")
            current = None
            continue
        param = PARAM_RE.match(stmt)
        if param:
            assigns = dict(ASSIGN_RE.findall(param.group(1)))
            if not assigns:
                problems.append(f"line {lineno}: unparsable .param: {stmt[:60]}")
                continue
            if current is None:
                file_params.update(assigns)
            else:
                current.params.update(assigns)
            continue
        if stmt.startswith("."):
            continue  # deck directives (.end, .include, ...) are not devices
        if current is None:
            problems.append(f"line {lineno}: device outside any cell: {stmt[:60]}")
            continue
        current.devices.append(tuple(stmt.split()))
    return cells, file_params, problems


def _device_err(block_dev: tuple[str, ...], top_dev: tuple[str, ...], index: int) -> str | None:
    name = block_dev[0] if block_dev else (top_dev[0] if top_dev else "?")
    if len(block_dev) != len(top_dev):
        return f"device #{index} '{name}': {len(block_dev)} tokens (block) vs {len(top_dev)} (top)"
    for pos, (bt, tt) in enumerate(zip(block_dev, top_dev)):
        if bt != tt:
            return f"device #{index} '{name}' differs at token {pos}: {bt} (block) vs {tt} (top)"
    return None


def compare_cell(block_cell: Cell, block_params: dict[str, str],
                 top_cell: Cell, top_params: dict[str, str]) -> list[str]:
    """Human-readable mismatches (empty = the two cells are equivalent)."""
    errs: list[str] = []
    if block_cell.pins != top_cell.pins:
        errs.append(
            "pins: '" + " ".join(block_cell.pins) + "' (block) vs '"
            + " ".join(top_cell.pins) + "' (top)"
        )
    bd, td = block_cell.devices, top_cell.devices
    if len(bd) != len(td):
        errs.append(f"{len(bd)} device statements (block) vs {len(td)} (top)")
    for index, (b, t) in enumerate(zip(bd, td), start=1):
        e = _device_err(b, t, index)
        if e:
            errs.append(e)
    for index in range(min(len(bd), len(td)) + 1, len(bd) + 1):
        errs.append(f"device #{index} '{bd[index - 1][0]}' present in block, absent from top")
    for index in range(min(len(bd), len(td)) + 1, len(td) + 1):
        errs.append(f"device #{index} '{td[index - 1][0]}' absent from block, present in top")
    for key in sorted(set(block_params) | set(top_params)):
        bv = block_params.get(key, "<absent>")
        tv = top_params.get(key, "<absent>")
        if bv != tv:
            errs.append(f".param {key}: {bv} (block) vs {tv} (top)")
    return errs


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def check_export(top: Path, top_cells: dict[str, Cell], top_file_params: dict[str, str],
                 export: Path, block: str) -> list[str]:
    """Errors for one block export against the parsed top export."""
    rel = _rel(export)
    if not export.is_file():
        return [f"{rel}: block export missing"]
    cells, file_params, problems = parse_export(export.read_text())
    errs = [f"{rel}: {p}" for p in problems]
    expected = f"bandgap_{block}"
    if expected not in cells:
        errs.append(f"{rel}: no {expected} cell ({expected} wrapper) in this export")
    for name, cell in cells.items():
        top_cell = top_cells.get(name)
        if top_cell is None:
            errs.append(f"{rel} [{name}]: no same-named .subckt in {_rel(top)}")
            continue
        cell_errs = compare_cell(
            cell, cell.visible_params(file_params),
            top_cell, top_cell.visible_params(top_file_params),
        )
        errs += [f"{rel} [{name}]: {e}" for e in cell_errs]
    return errs


def check(top: Path, export_dir: Path, blocks: tuple[str, ...] = BLOCKS) -> list[str]:
    """All errors across every block export (empty = everything in sync)."""
    if not top.is_file():
        return [f"{_rel(top)}: top export missing"]
    top_cells, top_file_params, problems = parse_export(top.read_text())
    errs = [f"{_rel(top)}: {p}" for p in problems]
    for block in blocks:
        export = export_dir / f"bandgap_{block}.spice"
        errs += check_export(top, top_cells, top_file_params, export, block)
    return errs


def main() -> int:
    top = TOP_DEFAULT
    top_cells, top_file_params, problems = parse_export(top.read_text())
    status = 0
    for block in BLOCKS:
        export = EXPORT_DIR_DEFAULT / f"bandgap_{block}.spice"
        errs = [f"{_rel(top)}: {p}" for p in problems] if block == BLOCKS[0] else []
        errs += check_export(top, top_cells, top_file_params, export, block)
        flag = "ok  " if not errs else "FAIL"
        print(f"{flag} {export.name}")
        for e in errs:
            print(f"       - {e}")
        status |= bool(errs)
    if status:
        print(f"FAIL: block netlists disagree with {top.name} -- regenerate the stale ones with:")
        print("  klt netlist design/bandgap_<block>.sch -o design/netlist/bandgap_<block>.spice \\")
        print("    --rcfile design/xschemrc --relative-paths")
    else:
        print(f"PASS: {len(BLOCKS)}/{len(BLOCKS)} block netlists in sync with {_rel(top)}")
    return 1 if status else 0


if __name__ == "__main__":
    sys.exit(main())
