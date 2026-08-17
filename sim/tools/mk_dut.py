#!/usr/bin/env python3
"""Turn an xschem netlist export into an includable DUT fragment.

    python3 sim/tools/mk_dut.py design/netlist/bandgap_top.spice sim/dut/bandgap_top.spice

The corner runner ``.include``s a DUT netlist ahead of each testbench (see
``sim/harness/README.md``), so the DUT file must hold **subcircuit
definitions only** -- no ``.end`` (it would truncate every generated deck),
no ``.control``/``.temp``/``.lib`` (the harness owns the corner it is
sweeping).

An xschem export of a *top-level* schematic is not that shape out of the
box. xschem writes the top cell's own port list commented out::

    **.subckt bandgap_top vdd vss vref
    Xx1 ...
    **.ends
    ... child .subckt definitions ...
    .end

i.e. the top cell's contents sit at deck level, with the ``.subckt``/``.ends``
that would wrap them commented to ``**``. This script performs exactly two
mechanical edits -- uncomment those two lines, drop the deck-owning
directives -- so that the result is the same circuit, instantiable by any
testbench as ``Xdut vdd vss vref bandgap_top``.

Doing this in a script rather than by hand matters because the schematic is
still moving (#10's amp, #11's startup branch): regenerating the DUT after a
schematic edit is one command, and the emitted header records which export
it came from and that export's sha256, so a stale DUT is visible rather than
silent.

Exit codes: 0 wrote the fragment, 1 the source could not be converted.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness.paths import _repo_relative  # noqa: E402  (needs sys.path)

#: Directives a DUT fragment may not carry -- see ``harness.testbench``.
DROP_DIRECTIVES = (".end", ".temp", ".lib", ".global", ".option", ".options")

#: ``**.subckt`` / ``**.ends`` -- xschem's commented-out top-cell wrapper.
COMMENTED_WRAPPER_RE = re.compile(r"^\*\*(\.(?:subckt|ends)\b.*)$", re.IGNORECASE)

#: A ``.control`` block: dropped whole, not line by line.
CONTROL_OPEN_RE = re.compile(r"^\.control\b", re.IGNORECASE)
CONTROL_CLOSE_RE = re.compile(r"^\.endc\b", re.IGNORECASE)


def convert(text: str) -> tuple[str, list[str]]:
    """Return ``(fragment, notes)`` for one xschem export."""
    out: list[str] = []
    notes: list[str] = []
    in_control = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if in_control:
            if CONTROL_CLOSE_RE.match(stripped):
                in_control = False
            continue
        if CONTROL_OPEN_RE.match(stripped):
            in_control = True
            notes.append("dropped a .control block (the harness supplies its own)")
            continue

        wrapper = COMMENTED_WRAPPER_RE.match(stripped)
        if wrapper:
            out.append(wrapper.group(1))
            notes.append(f"uncommented xschem's top-cell wrapper: {wrapper.group(1)}")
            continue

        if stripped.startswith(".") and stripped.split()[0].lower() in DROP_DIRECTIVES:
            notes.append(f"dropped deck-level directive: {stripped}")
            continue

        out.append(line)

    fragment = "\n".join(out).strip("\n") + "\n"
    return fragment, notes


def validate(fragment: str) -> list[str]:
    """Structural problems that would make this fragment unusable as a DUT."""
    problems: list[str] = []
    depth = 0
    top_level_devices: list[str] = []
    subckts: list[str] = []
    for lineno, raw in enumerate(fragment.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        head = stripped.split()[0].lower()
        if head == ".subckt":
            depth += 1
            subckts.append(stripped.split()[1])
            continue
        if head == ".ends":
            depth -= 1
            if depth < 0:
                problems.append(f"line {lineno}: .ends with no matching .subckt")
                depth = 0
            continue
        if stripped.startswith("+") or head.startswith("."):
            continue
        if depth == 0:
            top_level_devices.append(f"line {lineno}: {stripped[:60]}")
    if depth:
        problems.append(f"{depth} unclosed .subckt block(s)")
    if not subckts:
        problems.append("no .subckt definitions found -- this is not a DUT fragment")
    if top_level_devices:
        problems.append(
            "device instances outside any .subckt (a DUT fragment defines "
            "subcircuits; the testbench instantiates them):\n  "
            + "\n  ".join(top_level_devices[:5])
        )
    return problems


def header(source: Path, sha256: str, subckts: list[str]) -> str:
    rel = _repo_relative(source)
    return "\n".join(
        [
            "* DUT netlist fragment -- GENERATED, do not edit by hand.",
            "*",
            f"* source     : {rel}",
            f"* sha256     : {sha256}",
            f"* regenerate : python3 sim/tools/mk_dut.py {rel} <this file>",
            "*",
            "* Subcircuits defined here: " + ", ".join(subckts),
            "*",
            "* Included by the corner runner ahead of each testbench (tb.json's",
            "* \"dut\" key, or --dut). Holds subcircuit definitions only: no .end,",
            "* .control, .temp or .lib -- the harness owns those per PVT point.",
            "",
            "",
        ]
    )


def subckt_names(fragment: str) -> list[str]:
    return [
        line.split()[1]
        for line in fragment.splitlines()
        if line.strip().lower().startswith(".subckt")
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="mk_dut.py",
        description="Convert an xschem netlist export into an includable DUT fragment.",
    )
    parser.add_argument("source", help="xschem export, e.g. design/netlist/bandgap_top.spice")
    parser.add_argument("destination", help="DUT fragment to write, e.g. sim/dut/bandgap_top.spice")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if the destination is missing or out of date",
    )
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_file():
        print(f"error: no such netlist: {source}", file=sys.stderr)
        return 1
    raw = source.read_text()
    fragment, notes = convert(raw)

    problems = validate(fragment)
    if problems:
        print(f"error: {source} did not convert to a usable DUT fragment:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    body = header(source, hashlib.sha256(source.read_bytes()).hexdigest(),
                  subckt_names(fragment)) + fragment
    destination = Path(args.destination)

    if args.check:
        if not destination.is_file():
            print(f"FAIL: {destination} does not exist", file=sys.stderr)
            return 1
        if destination.read_text() != body:
            print(
                f"FAIL: {destination} is out of date with respect to {source}; "
                f"regenerate with `python3 sim/tools/mk_dut.py {source} {destination}`",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {destination} is up to date with {source}")
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(body)
    for note in notes:
        print(f"  {note}")
    print(f"wrote {destination} ({len(fragment.splitlines())} lines, "
          f"subcircuits: {', '.join(subckt_names(fragment))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
