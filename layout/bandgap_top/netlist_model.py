#!/usr/bin/env python3
"""Parse and flatten ``design/netlist/bandgap_top.spice`` into a device model.

This module is the **single source of truth** shared by the layout generator
(``layout/bandgap_top/generate.py``) and the LVS reference-netlist writer
(``layout/lvs/make_reference.py``). Both read the committed, schematic-derived
netlist through here rather than restating device sizes, so the drawn geometry
and the LVS reference can never silently drift apart from the schematic (or
from each other) the way two hand-maintained copies would.

What it does
------------

1. Parse the xschem-emitted SPICE (``.subckt`` / ``X…`` / ``R…`` /
   ``+``-continuation lines) into subcircuit definitions plus a top-level
   instance list.
2. Flatten the hierarchy into a single list of primitive instances, each with
   a dotted path name (``core.M1``, ``amp.MC3``, ``core.trim.RU17``) and its
   terminal nets resolved to flat, hierarchically-qualified net names.
3. Classify each primitive by its PDK model name into one of the device
   families the layout has to draw: ``mos`` (``nfet_03v3``/``pfet_03v3``),
   ``res`` (``ppolyf_u``/``ppolyf_u_1k``), ``bjt`` (``pnp_*``), ``cap``
   (``cap_mim_*``), and ``ideal_res`` (the bare ``RS0…RS5`` trim straps, which
   are a metal option, not a drawn device).
4. Compute the **layout-visible reduction** of the netlist — the netlist as the
   ``klt`` gf180mcu extraction deck can actually see it. See
   :func:`reduce_nets` for why that reduction is needed and exactly what it
   assumes.

Units: every geometric quantity returned by this module is an **integer number
of nanometres** (the layout database unit used throughout ``layout/``), never a
float micron. SPICE suffixes (``u``, ``n``, …) are resolved on parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NETLIST = REPO_ROOT / "design" / "netlist" / "bandgap_top.spice"

#: PDK model name -> device family the layout has to draw.
MOS_MODELS = {"nfet_03v3": "nfet", "pfet_03v3": "pfet"}
RES_MODELS = {"ppolyf_u", "ppolyf_u_1k"}
BJT_MODELS = {"pnp_05p00x05p00", "pnp_10p00x10p00"}
CAP_MODELS_PREFIX = "cap_mim_"

#: Resistor models this layout draws recognition markers for, i.e. the ones
#: ``klt extract`` returns as real devices. Only the base ``ppolyf_u``
#: flavour: ``generate.py``'s ``draw_res``/``draw_trim`` mark a base-flavour
#: body with ``RES_MK``/``Pplus``/``SAB`` (the deck's ``ppolyf_u``
#: recogniser), and deliberately mark a high-sheet-rho ``ppolyf_u_1k`` body
#: with ``Resistor`` (62/0) and **no** ``RES_MK`` — so it is claimed by
#: neither recogniser and stays ordinary poly interconnect rather than being
#: read at the base flavour's 350 Ω/□ (see ``plan.ResItem.high_rho``). That
#: was forced when the deck had no high-sheet-rho entry at all
#: (klayout-tools#299, since resolved upstream); taking up the deck's new
#: ``ppolyf_u_1k`` entry is tracked as gf180-bandgap#78. A model *not* in
#: this set collapses to a short in :func:`reduce_nets`, matching the
#: extracted side.
EXTRACTED_RES_MODELS = {"ppolyf_u"}

#: Readable, stable path prefixes for the three top-level subcircuit
#: instances (``Xx1``/``Xx2``/``Xx3``), derived from the subcircuit name so a
#: rename in the schematic surfaces here rather than being silently absorbed.
_PREFIX_FROM_SUBCKT = {
    "bandgap_core": "core",
    "bandgap_amp": "amp",
    "bandgap_startup": "startup",
    "bandgap_trim": "trim",
}

_SUFFIX = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "x": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}

_NUM_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)$")


class NetlistError(Exception):
    """Raised for a netlist this module cannot interpret."""


def parse_value(text: str) -> float:
    """Parse a SPICE numeric literal (``2u``, ``230.180u``, ``1e12``) to a float."""
    match = _NUM_RE.match(text.strip())
    if match is None:
        raise NetlistError(f"cannot parse numeric value: {text!r}")
    mantissa, suffix = match.groups()
    value = float(mantissa)
    if suffix:
        key = suffix.lower()
        # SPICE ignores trailing unit letters ("2uF" == "2u"); match the
        # longest recognised multiplier prefix.
        for candidate in ("meg", "t", "g", "k", "m", "u", "n", "p", "f", "x"):
            if key.startswith(candidate):
                value *= _SUFFIX[candidate]
                break
        else:
            raise NetlistError(f"unknown SPICE suffix in {text!r}")
    return value


def nm(value_metres: float) -> int:
    """Convert a value in metres to whole nanometres (the layout dbu)."""
    return int(round(value_metres * 1e9))


@dataclass(frozen=True)
class RawInstance:
    """One instance line as written in its defining subcircuit."""

    name: str
    nodes: tuple[str, ...]
    model: str
    params: dict[str, str]
    kind: str  # "sub" (X-card) or "ideal_res" (bare R-card)


@dataclass(frozen=True)
class Subckt:
    name: str
    pins: tuple[str, ...]
    instances: tuple[RawInstance, ...]


@dataclass(frozen=True)
class Device:
    """One flattened primitive instance."""

    path: str
    family: str  # "mos" | "res" | "bjt" | "cap" | "ideal_res"
    model: str
    nets: dict[str, str]
    params: dict[str, float]  # metres / dimensionless, as written

    # -- MOS convenience accessors ------------------------------------------
    @property
    def mos_kind(self) -> str:
        return MOS_MODELS[self.model]

    @property
    def w_nm(self) -> int:
        return nm(self.params["w"])

    @property
    def l_nm(self) -> int:
        return nm(self.params["l"])

    @property
    def nf(self) -> int:
        return int(self.params.get("nf", 1))


@dataclass
class FlatNetlist:
    devices: list[Device] = field(default_factory=list)
    top_pins: tuple[str, ...] = ()

    def by_family(self, family: str) -> list[Device]:
        return [d for d in self.devices if d.family == family]

    def get(self, path: str) -> Device:
        for device in self.devices:
            if device.path == path:
                return device
        raise NetlistError(f"no such device path: {path}")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def _logical_lines(text: str) -> Iterable[str]:
    """Yield logical SPICE lines, joining ``+`` continuations, dropping
    comments (``*`` at column 0) and blank lines."""
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("*"):
            continue
        if line.lstrip().startswith("+"):
            if current is None:
                raise NetlistError(f"continuation line with no preceding line: {line!r}")
            current += " " + line.lstrip()[1:].strip()
            continue
        if current is not None:
            yield current
        current = line.strip()
    if current is not None:
        yield current


def _split_params(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split a token list into positional tokens and ``key=value`` params.

    Handles the quoted-expression form xschem emits (``ad='int((nf+1)/2) …'``)
    by treating any token containing ``=`` as the start of a parameter and
    swallowing tokens until quotes balance.
    """
    positional: list[str] = []
    params: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" in token:
            key, _, value = token.partition("=")
            while value.count("'") % 2 == 1 and index + 1 < len(tokens):
                index += 1
                value += " " + tokens[index]
            params[key.strip().lower()] = value.strip().strip("'")
        else:
            positional.append(token)
        index += 1
    return positional, params


def parse(path: Path | str = DEFAULT_NETLIST) -> tuple[dict[str, Subckt], list[RawInstance]]:
    """Parse ``path`` into ``({subckt name: Subckt}, top-level instances)``."""
    text = Path(path).read_text()
    subckts: dict[str, Subckt] = {}
    top_instances: list[RawInstance] = []

    current_name: str | None = None
    current_pins: tuple[str, ...] = ()
    current_instances: list[RawInstance] = []

    for line in _logical_lines(text):
        lowered = line.lower()
        if lowered.startswith(".subckt"):
            tokens = line.split()
            current_name = tokens[1]
            current_pins = tuple(t for t in tokens[2:] if "=" not in t)
            current_instances = []
            continue
        if lowered.startswith(".ends"):
            if current_name is None:
                raise NetlistError(".ends outside a .subckt")
            subckts[current_name] = Subckt(
                current_name, current_pins, tuple(current_instances)
            )
            current_name = None
            continue
        if lowered.startswith((".param", ".end", ".global", ".include", ".lib")):
            continue

        head = line[0].upper()
        if head not in ("X", "R"):
            continue
        tokens = line.split()
        positional, params = _split_params(tokens)
        name = positional[0][1:]
        if head == "X":
            model = positional[-1]
            nodes = tuple(positional[1:-1])
            instance = RawInstance(name, nodes, model, params, "sub")
        else:
            # Bare R-card: R<name> n1 n2 <value or {expr}>
            nodes = tuple(positional[1:3])
            value = " ".join(positional[3:]) if len(positional) > 3 else ""
            instance = RawInstance(name, nodes, value, params, "ideal_res")

        if current_name is None:
            top_instances.append(instance)
        else:
            current_instances.append(instance)

    return subckts, top_instances


# --------------------------------------------------------------------------- #
# Flattening
# --------------------------------------------------------------------------- #

#: Terminal-name order per device family, matching the PDK subcircuit pin
#: order in ``sm141064.ngspice``.
TERMINALS = {
    "mos": ("d", "g", "s", "b"),
    "res": ("n1", "n2", "sub"),
    "bjt": ("c", "b", "e"),
    "cap": ("p", "n"),
    "ideal_res": ("n1", "n2"),
}


def _family(instance: RawInstance) -> str:
    if instance.kind == "ideal_res":
        return "ideal_res"
    model = instance.model
    if model in MOS_MODELS:
        return "mos"
    if model in RES_MODELS:
        return "res"
    if model in BJT_MODELS:
        return "bjt"
    if model.startswith(CAP_MODELS_PREFIX):
        return "cap"
    return "subckt"


def _numeric_params(instance: RawInstance, family: str) -> dict[str, float]:
    wanted = {
        "mos": ("w", "l", "nf", "m"),
        "res": ("r_width", "r_length", "m"),
        "bjt": ("m",),
        "cap": ("c_width", "c_length", "m"),
        "ideal_res": (),
    }[family]
    out: dict[str, float] = {}
    for key in wanted:
        if key in instance.params:
            try:
                out[key] = parse_value(instance.params[key])
            except NetlistError:
                pass
    return out


def flatten(
    subckts: dict[str, Subckt], top_instances: list[RawInstance]
) -> FlatNetlist:
    """Flatten the hierarchy into primitive devices with global net names."""
    flat = FlatNetlist()

    def walk(instances: Iterable[RawInstance], prefix: str, net_map: dict[str, str]) -> None:
        for instance in instances:
            family = _family(instance)
            path = f"{prefix}{instance.name}"
            if family == "subckt":
                definition = subckts.get(instance.model)
                if definition is None:
                    raise NetlistError(
                        f"instance {path} references undefined subcircuit "
                        f"{instance.model!r}"
                    )
                if len(definition.pins) != len(instance.nodes):
                    raise NetlistError(
                        f"instance {path}: {len(instance.nodes)} nodes vs "
                        f"{len(definition.pins)} pins on {instance.model}"
                    )
                child_prefix = _PREFIX_FROM_SUBCKT.get(instance.model)
                child_prefix = (
                    f"{prefix}{child_prefix}." if child_prefix else f"{path}."
                )
                child_map = {
                    pin: net_map.get(node, f"{prefix}{node}")
                    for pin, node in zip(definition.pins, instance.nodes)
                }
                # Internal (non-pin) nets get the child's own prefix.
                walk(
                    definition.instances,
                    child_prefix,
                    _ChildNetMap(child_map, child_prefix),
                )
                continue

            terminals = TERMINALS[family]
            if len(instance.nodes) < len(terminals):
                raise NetlistError(
                    f"instance {path}: expected {len(terminals)} terminals, "
                    f"got {len(instance.nodes)}"
                )
            nets = {
                term: net_map.get(node, f"{prefix}{node}")
                for term, node in zip(terminals, instance.nodes)
            }
            flat.devices.append(
                Device(path, family, instance.model, nets, _numeric_params(instance, family))
            )

    top_map = _ChildNetMap({}, "")
    walk(top_instances, "", top_map)
    # Every net referenced at the top level of the file is a global net.
    flat.top_pins = ("vdd", "vss", "vref")
    return flat


class _ChildNetMap(dict):
    """Net-name resolver for one hierarchy level.

    Pin nets map to the parent's net name; every other node is local and gets
    this level's path prefix. Implemented as a ``dict`` subclass so ``.get``
    keeps the "pin -> parent net" mapping while unknown keys fall through to
    the prefixed local name.
    """

    def __init__(self, pin_map: dict[str, str], prefix: str) -> None:
        super().__init__(pin_map)
        self.prefix = prefix

    def get(self, key: str, default: str | None = None) -> str:  # type: ignore[override]
        if key in self:
            return self[key]
        return f"{self.prefix}{key}"


def load(path: Path | str = DEFAULT_NETLIST) -> FlatNetlist:
    """Parse + flatten ``path`` in one call."""
    subckts, top_instances = parse(path)
    return flatten(subckts, top_instances)


# --------------------------------------------------------------------------- #
# Layout-visible reduction
# --------------------------------------------------------------------------- #


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


#: Preference order used to pick the surviving name of a merged net group.
_NAME_PRIORITY = ("vdd", "vss", "vref", "sns1", "sns2", "fb", "casc", "ibias")


def trim_strap_shorted(expression: str, trim_code: int) -> bool:
    """Is trim-strap ``expression`` a short at ``trim_code``?

    ``design/bandgap_trim.sch`` writes each strap as
    ``{1e-3 + 1e12*(floor(code/2^k) - 2*floor(code/2^(k+1)))}`` — i.e. 1 mOhm
    (a short) when bit *k* of the code is 0, and 1e12 Ohm (an open) when it is
    1. This reproduces that bit test directly from the expression's own
    divisor rather than assuming a strap ordering.
    """
    match = re.search(r"floor\(\s*trim_code\s*/\s*(\d+)\s*\)", expression)
    if match is None:
        raise NetlistError(f"cannot read a trim bit out of strap expression: {expression!r}")
    divisor = int(match.group(1))
    return (trim_code // divisor) % 2 == 0


def reduce_nets(flat: FlatNetlist, trim_code: int) -> dict[str, str]:
    """Return ``{schematic net name: layout-visible net name}``.

    **Why a reduction is needed.** The netlist a correctly-drawn layout
    extracts to under ``klt``'s gf180mcu extraction deck
    (``klayout_tools/decks/gf180mcu.py``) is not quite the schematic netlist.
    Two classes of schematic construct have no extracted counterpart, so the
    nets they join have to be merged before the two sides can be compared:

    * every resistor whose model is **not** in :data:`EXTRACTED_RES_MODELS`
      is **collapsed to a short**. Today that is exactly ``startup.RPU``
      (``ppolyf_u_1k``), whose body ``generate.py`` deliberately draws without
      the ``RES_MK`` marker so no recogniser claims it — see that constant.
    * every ideal ``RS*`` trim strap is resolved to a short or an open at the
      drawn trim code (it is a metal option, not a device — the layout draws
      it as Metal1, and :func:`plan.trim_strap_spans` derives the drawn strap
      geometry from these same expressions).

    Everything else the schematic draws is now a real extracted device and is
    modelled one-for-one in ``layout/lvs/make_reference.py``: base-flavour
    ``ppolyf_u`` resistors (``RES_MK``/``Pplus``/``SAB``-marked), ``pnp_*``
    bipolars (``DRC_BJT``-marked) and the ``cap_mim_*`` compensation capacitor
    (``CAP_MK``/``MIM_L_MK``-marked). That was not true when this function was
    written — the deck then recognised only ``nfet``/``pfet`` — and the
    remaining ``ppolyf_u_1k`` gap is a tool-capability limitation, not a
    layout simplification: the layout still draws the device.
    """
    union = UnionFind()
    for device in flat.devices:
        for net in device.nets.values():
            union.find(net)

    for device in flat.devices:
        if device.family == "res":
            if device.model not in EXTRACTED_RES_MODELS:
                union.union(device.nets["n1"], device.nets["n2"])
        elif device.family == "ideal_res":
            if trim_strap_shorted(device.model, trim_code):
                union.union(device.nets["n1"], device.nets["n2"])

    groups: dict[str, list[str]] = {}
    for net in union.parent:
        groups.setdefault(union.find(net), []).append(net)

    mapping: dict[str, str] = {}
    for members in groups.values():
        canonical = _pick_name(members)
        for member in members:
            mapping[member] = canonical
    return mapping


def _pick_name(members: list[str]) -> str:
    for preferred in _NAME_PRIORITY:
        if preferred in members:
            return preferred
    # Otherwise prefer the shallowest (fewest dots), then lexicographic — a
    # deterministic choice, so the emitted reference netlist is diff-stable.
    return sorted(members, key=lambda n: (n.count("."), n))[0]


if __name__ == "__main__":  # pragma: no cover - developer convenience
    netlist = load()
    counts: dict[str, int] = {}
    for device in netlist.devices:
        counts[device.family] = counts.get(device.family, 0) + 1
    print("device families:", counts)
    mapping = reduce_nets(netlist, trim_code=32)
    print("schematic nets:", len(set(mapping)))
    print("layout-visible nets:", len(set(mapping.values())))
    for device in netlist.by_family("mos"):
        print(
            f"  {device.path:20s} {device.mos_kind} "
            f"W={device.w_nm} L={device.l_nm} nf={device.nf} "
            + " ".join(f"{k}={mapping[v]}" for k, v in device.nets.items())
        )
