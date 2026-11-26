"""The one parser for the ``<corner-id>`` grammar ratified in ``sim/README.md``.

Every raw per-corner log is ``sim/<slug>/corners/<record-id>/<corner-id>.log``,
and two readers parse that name: the evidence checker
(``sim/harness/evidence_lint.py``), which rejects a name the grammar does not
accept, and the spec-line suite (``sim/suite/analysis.py``), which reads the
process, temperature and supply back out of it. Both come here, so they cannot
disagree about what a corner log's name has to look like -- they did while
each kept its own grammar, and the suite counted a malformed supply as a
temperature comparison the checker would have rejected.

The grammar::

    <corner-id> ::= <process> "_" <temp> "c" "_" <supply>
    <process>   ::= token ("_" token)*        # tt, ss, bjt_ff, res_typical
    <temp>      ::= "-"? digits ("." digits)? # -40c, 27c, 125c
    <supply>    ::= "nosupply" | node? volts "v"   # 2.97v, nwell2p97v

Splitting on the *last two* underscores is what lets the process field
carry a device-family prefix; neither temp nor supply may contain one.

This module is independent of the code that *writes* corner ids
(``sim/harness/corners.py``) and of both readers, and it sits directly under
``sim/`` because that is the directory both readers' packages share: each
puts it on ``sys.path`` before importing. Stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PROCESS_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*")
#: Signed junction temperature in degrees C: `-40c`, `27c`, `125c`.
_TEMP_RE = re.compile(r"-?\d+(?:\.\d+)?c")
#: `2.97v`, or `nwell2p97v` when the swept rail needs naming (`p` stands in
#: for the decimal point so the field stays a single underscore-free token).
_SUPPLY_RE = re.compile(r"[a-z]*\d+(?:[.p]\d+)?v")
#: A testbench with no supply rail to sweep (device testbenches drive the DUT
#: from an ideal source). The record's Corner matrix run field must say why.
NO_SUPPLY = "nosupply"


@dataclass(frozen=True)
class CornerKey:
    """A parsed ``<corner-id>``."""

    process: str
    temp_c: float
    supply: str

    @property
    def corner_id(self) -> str:
        return f"{self.process}_{self.temp_c:g}c_{self.supply}"


def corner_id_problem(corner_id: str) -> str | None:
    """``None`` if ``corner_id`` parses, else why it does not."""
    parts = corner_id.split("_")
    if len(parts) < 3:
        return (
            f"{corner_id!r} does not parse as <process>_<temp>c_<supply> "
            "(see the corner-id grammar in sim/README.md)"
        )
    process, temp, supply = parts[:-2], parts[-2], parts[-1]
    if not all(_PROCESS_TOKEN_RE.fullmatch(token) for token in process):
        return (
            f"{corner_id!r}: process field {'_'.join(process)!r} is not one or more "
            "lowercase alphanumeric tokens (tt, ss, bjt_ff, res_typical, ...)"
        )
    if not _TEMP_RE.fullmatch(temp):
        return (
            f"{corner_id!r}: temperature field {temp!r} is not a signed number "
            "followed by 'c' (-40c, 27c, 125c)"
        )
    if supply != NO_SUPPLY and not _SUPPLY_RE.fullmatch(supply):
        return (
            f"{corner_id!r}: supply field {supply!r} is neither <volts>v / "
            f"<node><volts>v (2.97v, nwell2p97v) nor the literal {NO_SUPPLY!r}"
        )
    return None


def parse_corner_id(corner_id: str) -> CornerKey | None:
    """The three fields of ``corner_id``, or ``None`` if it does not parse.

    ``None`` exactly when :func:`corner_id_problem` gives a reason, so a name
    the checker rejects is never counted by the suite.
    """
    if corner_id_problem(corner_id) is not None:
        return None
    process, temp, supply = corner_id.rsplit("_", 2)
    return CornerKey(
        process=process,
        temp_c=float(temp[:-1]),
        supply=supply,
    )
