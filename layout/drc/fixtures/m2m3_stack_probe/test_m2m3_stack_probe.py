#!/usr/bin/env python3
"""Checks for the Metal2/Metal3 routing-stack probe (gf180-bandgap#160).

The probe fixture exists to answer two questions with a tool run instead of
an assertion (see ``generate.py``'s docstring and
``layout/routing/multi-metal-routing-study.md``):

1. does a net routed Metal1 -> Via1 -> Metal2 -> Via2 -> Metal3 and back down
   extract as **one** net (klayout-tools#220's stack, which the study's whole
   scheme depends on and which the block's MIM-cap via stack does not
   exercise as a two-terminal route)?
2. are two such nets, run side by side at the proposed track pitch, kept
   **distinct**?

The committed evidence for both is
``layout/lvs/reports/m2m3_stack_probe/*.extract.json`` (extraction) and
``layout/drc/reports/m2m3_stack_probe/*.drc.json`` (DRC, ``status: clean``).
These tests re-derive that evidence on demand, and each stage skips rather
than fails where its tool is absent::

    uv run --with klayout python3 -m unittest \\
        layout.drc.fixtures.m2m3_stack_probe.test_m2m3_stack_probe -v
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GDS = HERE / "m2m3_stack_probe.gds"

try:
    import klayout.db  # noqa: F401

    HAVE_KLAYOUT = True
except ImportError:  # pragma: no cover - environment-dependent
    HAVE_KLAYOUT = False

probe = None
if HAVE_KLAYOUT:
    # Loaded by path under a unique name rather than `import generate`: this
    # repo has several `generate.py` modules (this fixture,
    # `trivial_poly_res`, `bandgap_top`), and a bare import picks whichever
    # one a sibling test already put in `sys.modules`.
    _spec = importlib.util.spec_from_file_location(
        "m2m3_stack_probe_generate", HERE / "generate.py"
    )
    assert _spec is not None and _spec.loader is not None
    probe = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(probe)

# Minima read out of the installed gf180mcu DRC deck
# (klayout_tools/decks/gf180mcu.py, klt 0.2.0), in nm.
METAL_WIDTH_MIN = 280  # metal2.width.1 / metal3.width.1
METAL_SPACE_MIN = 280  # metal2.space.1 / metal3.space.1
VIA_WIDTH_MIN = 260  # via1.width.1 / via2.width.1
VIA_ENC_MIN = 10  # metal2.enclosing.via1.1 / metal3.enclosing.via2.1

# The probe's resistor model. The two devices are the only resistors in the
# probe, so every resistor record the parser finds must carry this model.
PROBE_RES_MODEL = "ppolyf_u"


class ProbeNetlistError(ValueError):
    """The extracted netlist is not the probe's two-resistor series loop:
    either a resistor record is in a shape this parser does not support, or
    the parsed devices are not connected as the probe requires."""


class ResistorRecord:
    """One parsed resistor record: conduction terminals, substrate, model."""

    __slots__ = ("line", "model", "name", "shape", "substrate", "terminals")

    def __init__(self, name, shape, terminals, substrate, model, line):
        self.name = name
        self.shape = shape  # "R" or "X"
        self.terminals = terminals  # (a, b), opaque net-name tokens
        self.substrate = substrate
        self.model = model
        self.line = line

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"ResistorRecord({self.line!r})"


def _is_param(token: str) -> bool:
    return "=" in token


def parse_resistor_records(netlist: str) -> list[ResistorRecord]:
    """Parse the probe's resistor devices out of an extracted SPICE netlist.

    Deliberately bounded (gf180-bandgap#303), not a general SPICE parser.
    Two record shapes are supported, matched by token *position* so that a
    model name in a comment or a parameter value cannot be mistaken for a
    device, and net names (e.g. ``\\$1``) are kept as opaque tokens:

    * R shape (klt at the ``signoff/klt-pin.txt`` revision, and the
      committed legacy extraction)::

          R<name> <a> <b> <substrate> <value> <model> [key=value ...]

    * X shape (newer klt, subckt-style)::

          X<name> <a> <b> <substrate> <model> [key=value ...]

    Every ``R`` record is a resistor and must match the R shape. An ``X``
    record is a resistor when its model position holds the probe model; an
    ``X`` record naming the probe model anywhere else among its positional
    tokens is malformed. Other ``X`` records and all other device letters
    are unrelated and ignored. Malformed records raise ProbeNetlistError
    instead of silently dropping out of the device count.
    """
    records: list[ResistorRecord] = []
    for lineno, raw in enumerate(netlist.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("*", ".")):
            continue
        if line.startswith("+"):
            raise ProbeNetlistError(
                f"line {lineno}: continuation lines are not supported by the "
                f"probe's netlist parser: {raw!r}"
            )
        tokens = line.split()
        name, rest = tokens[0], tokens[1:]
        kind = name[0].upper()
        if kind == "R":
            # positional: a b substrate value model; then key=value only.
            positional = rest[:5]
            params = rest[5:]
            if (
                len(positional) != 5
                or any(_is_param(t) for t in positional)
                or not all(_is_param(t) for t in params)
            ):
                raise ProbeNetlistError(
                    f"line {lineno}: malformed R resistor record (expected "
                    f"'R<name> <a> <b> <substrate> <value> <model> "
                    f"[key=value ...]'): {raw!r}"
                )
            a, b, sub, _value, model = positional
            records.append(ResistorRecord(name, "R", (a, b), sub, model, raw))
        elif kind == "X":
            positional = [t for t in rest if not _is_param(t)]
            n_pos = len(positional)
            # Positional tokens must all precede the parameters.
            if rest[:n_pos] != positional:
                if PROBE_RES_MODEL in positional:
                    raise ProbeNetlistError(
                        f"line {lineno}: malformed X resistor record "
                        f"(positional token after key=value): {raw!r}"
                    )
                continue
            if not positional or positional[-1] != PROBE_RES_MODEL:
                if PROBE_RES_MODEL in positional:
                    raise ProbeNetlistError(
                        f"line {lineno}: malformed X resistor record "
                        f"({PROBE_RES_MODEL!r} is not in the model position): "
                        f"{raw!r}"
                    )
                continue  # some other subckt instance
            nodes = positional[:-1]
            if len(nodes) != 3:
                raise ProbeNetlistError(
                    f"line {lineno}: malformed X resistor record (expected "
                    f"'X<name> <a> <b> <substrate> {PROBE_RES_MODEL} "
                    f"[key=value ...]', got {len(nodes)} nodes): {raw!r}"
                )
            a, b, sub = nodes
            records.append(
                ResistorRecord(name, "X", (a, b), sub, PROBE_RES_MODEL, raw)
            )
    return records


def validate_series_loop(records: list[ResistorRecord]) -> frozenset[str]:
    """Check the probe's series-loop connectivity; return the shared net pair.

    Exactly two resistors, both of the probe model, each with two distinct
    conduction terminals that are not its substrate, and both connecting the
    *same* unordered pair of nets — which is only true if both Metal2/Metal3
    routes conduct and the two tracks stay distinct.
    """
    listing = "".join(f"\n  {r.line}" for r in records) or " (none)"
    if len(records) != 2:
        raise ProbeNetlistError(
            f"expected exactly 2 resistor records, found {len(records)}:"
            f"{listing}"
        )
    pairs = []
    for r in records:
        if r.model != PROBE_RES_MODEL:
            raise ProbeNetlistError(
                f"resistor {r.name} has model {r.model!r}, expected "
                f"{PROBE_RES_MODEL!r}: {r.line!r}"
            )
        a, b = r.terminals
        if a == b:
            raise ProbeNetlistError(
                f"resistor {r.name} has both conduction terminals on net "
                f"{a!r} (shorted): {r.line!r}"
            )
        if r.substrate in (a, b):
            raise ProbeNetlistError(
                f"resistor {r.name} has a conduction terminal on its "
                f"substrate net {r.substrate!r}: {r.line!r}"
            )
        pairs.append(frozenset((a, b)))
    if pairs[0] != pairs[1]:
        raise ProbeNetlistError(
            "the two resistors do not share both nets (open or "
            f"disconnected route): {sorted(pairs[0])} vs {sorted(pairs[1])}"
            f"{listing}"
        )
    return pairs[0]


class NetlistParserFixtureTests(unittest.TestCase):
    """Tool-independent fixtures for the parser/validator used by
    ``ExtractionTests.test_the_two_resistors_share_both_nets``. These run
    with neither klayout nor klt installed."""

    HEADER = (
        "* extracted by klt extract --deck gf180mcu\n"
        "\n"
        "* cell m2m3_stack_probe\n"
        "* pin vsubs\n"
        ".SUBCKT m2m3_stack_probe vsubs\n"
    )
    FOOTER = ".ENDS m2m3_stack_probe\n"

    # The committed legacy extraction (layout/lvs/reports/m2m3_stack_probe/
    # 20260817-005816-f5d9512.extracted.spice), verbatim device records.
    R_LEGACY = (
        "R$1 \\$1 \\$2 vsubs 3570 ppolyf_u",
        "R$2 \\$2 \\$1 vsubs 3570 ppolyf_u",
    )
    # klt at the signoff/klt-pin.txt revision (d5893304): R shape with
    # trailing geometry parameters.
    R_PINNED = (
        "R$1 \\$1 \\$2 vsubs 3570 ppolyf_u L=20.4U W=2U",
        "R$2 \\$2 \\$1 vsubs 3570 ppolyf_u L=20.4U W=2U",
    )
    # Newer klt (0.7.0+g8eec069c7576), reported in #303.
    X_NEWER = (
        "X$1 \\$1 \\$2 vsubs ppolyf_u r=3570 L=20.4U W=2U",
        "X$2 \\$2 \\$1 vsubs ppolyf_u r=3570 L=20.4U W=2U",
    )

    def netlist(self, *records: str) -> str:
        body = "".join(
            f"* device instance $1 r0 *1 1,10 ppolyf_u\n{r}\n" for r in records
        )
        return self.HEADER + body + self.FOOTER

    def check(self, *records: str) -> frozenset[str]:
        return validate_series_loop(parse_resistor_records(self.netlist(*records)))

    def assertRejected(self, *records: str) -> None:
        with self.assertRaises(ProbeNetlistError):
            self.check(*records)

    # --- positive -------------------------------------------------------

    def test_supported_shapes_yield_the_same_series_loop(self) -> None:
        for name, recs in (
            ("legacy R", self.R_LEGACY),
            ("pinned R", self.R_PINNED),
            ("newer X", self.X_NEWER),
        ):
            with self.subTest(shape=name):
                parsed = parse_resistor_records(self.netlist(*recs))
                self.assertEqual(len(parsed), 2)
                self.assertEqual([r.model for r in parsed], ["ppolyf_u"] * 2)
                self.assertEqual([r.substrate for r in parsed], ["vsubs"] * 2)
                self.assertEqual(
                    validate_series_loop(parsed), frozenset({"\\$1", "\\$2"})
                )

    def test_committed_legacy_extraction_file_validates(self) -> None:
        path = (
            HERE.parents[2] / "lvs" / "reports" / "m2m3_stack_probe"
            / "20260817-005816-f5d9512.extracted.spice"
        )
        parsed = parse_resistor_records(path.read_text())
        self.assertEqual([r.shape for r in parsed], ["R", "R"])
        self.assertEqual(
            validate_series_loop(parsed), frozenset({"\\$1", "\\$2"})
        )

    def test_terminal_order_does_not_matter(self) -> None:
        self.check(
            "R$1 \\$1 \\$2 vsubs 3570 ppolyf_u",
            "R$2 \\$1 \\$2 vsubs 3570 ppolyf_u",
        )
        self.check(
            "X$1 \\$2 \\$1 vsubs ppolyf_u r=3570",
            "X$2 \\$1 \\$2 vsubs ppolyf_u r=3570",
        )

    def test_escaped_net_names_are_opaque(self) -> None:
        pair = self.check(
            "R$1 \\$10 n\\$2 vsubs 3570 ppolyf_u",
            "R$2 n\\$2 \\$10 vsubs 3570 ppolyf_u",
        )
        self.assertEqual(pair, frozenset({"\\$10", "n\\$2"}))

    def test_comments_and_unrelated_records_are_ignored(self) -> None:
        self.check(
            "* R$9 \\$1 \\$3 vsubs 3570 ppolyf_u",
            "M$5 d g s b nfet_03v3 L=0.28U W=1U",
            "X$7 \\$1 \\$2 vsubs some_other_cell",
            "C$8 \\$1 vsubs 1e-15 cap",
            *self.R_LEGACY,
        )

    # --- negative: device count ----------------------------------------

    def test_wrong_resistor_count_is_rejected(self) -> None:
        self.assertRejected()
        self.assertRejected(self.R_LEGACY[0])
        self.assertRejected(self.X_NEWER[0])
        self.assertRejected(*self.R_LEGACY, "R$3 \\$1 \\$2 vsubs 3570 ppolyf_u")
        self.assertRejected(*self.X_NEWER, "X$3 \\$1 \\$2 vsubs ppolyf_u r=1")

    def test_other_resistor_model_is_rejected(self) -> None:
        self.assertRejected(
            self.R_LEGACY[0], "R$2 \\$2 \\$1 vsubs 3570 ppolyf_s"
        )

    # --- negative: malformed records -----------------------------------

    def test_malformed_r_records_are_rejected(self) -> None:
        for bad in (
            "R$2 \\$2 \\$1 vsubs 3570",  # truncated: no model
            "R$2 \\$2 \\$1 3570 ppolyf_u",  # missing substrate
            "R$2 \\$2",  # truncated
            "R$2 \\$2 \\$1 vsubs 3570 model=ppolyf_u",  # model only as param
            "R$2 \\$2 \\$1 vsubs r=3570 ppolyf_u",  # value as param
            "R$2 \\$2 \\$1 vsubs 3570 ppolyf_u extra",  # stray positional
        ):
            with self.subTest(record=bad):
                self.assertRejected(self.R_LEGACY[0], bad)

    def test_malformed_x_records_are_rejected(self) -> None:
        for bad in (
            "X$2 \\$2 \\$1 ppolyf_u r=3570",  # missing substrate
            "X$2 \\$2 ppolyf_u",  # truncated
            "X$2 \\$2 \\$1 vsubs extra ppolyf_u r=3570",  # extra node
            "X$2 \\$2 \\$1 vsubs ppolyf_u r=3570 tail",  # positional after params
            "X$2 ppolyf_u \\$2 \\$1 vsubs",  # model not last positional
        ):
            with self.subTest(record=bad):
                self.assertRejected(self.X_NEWER[0], bad)

    def test_model_name_in_comment_or_param_is_not_a_device(self) -> None:
        # Only one real resistor; the other mentions of the model must not
        # be counted as the second.
        self.assertRejected(
            self.X_NEWER[0],
            "* X$2 \\$2 \\$1 vsubs ppolyf_u r=3570",
            "X$2 \\$2 \\$1 vsubs other_cell model=ppolyf_u",
        )

    def test_continuation_lines_are_rejected(self) -> None:
        self.assertRejected(
            self.R_LEGACY[0], "R$2 \\$2 \\$1 vsubs", "+ 3570 ppolyf_u"
        )

    # --- negative: connectivity ----------------------------------------

    def test_shorted_conduction_terminals_are_rejected(self) -> None:
        self.assertRejected(
            "R$1 \\$1 \\$1 vsubs 3570 ppolyf_u",
            "R$2 \\$1 \\$1 vsubs 3570 ppolyf_u",
        )
        self.assertRejected(
            "X$1 \\$1 \\$1 vsubs ppolyf_u r=3570",
            "X$2 \\$1 \\$1 vsubs ppolyf_u r=3570",
        )

    def test_open_route_is_rejected(self) -> None:
        self.assertRejected(
            "R$1 \\$1 \\$2 vsubs 3570 ppolyf_u",
            "R$2 \\$3 \\$1 vsubs 3570 ppolyf_u",
        )
        self.assertRejected(
            "X$1 \\$1 \\$2 vsubs ppolyf_u r=3570",
            "X$2 \\$3 \\$4 vsubs ppolyf_u r=3570",
        )

    def test_substrate_cannot_stand_in_for_a_conduction_terminal(self) -> None:
        self.assertRejected(
            "R$1 vsubs \\$2 vsubs 3570 ppolyf_u",
            "R$2 \\$2 vsubs vsubs 3570 ppolyf_u",
        )
        self.assertRejected(
            "X$1 vsubs \\$2 vsubs ppolyf_u r=3570",
            "X$2 \\$2 vsubs vsubs ppolyf_u r=3570",
        )


@unittest.skipUnless(HAVE_KLAYOUT, "requires the klayout python module")
class SizingTests(unittest.TestCase):
    """The fixture draws the *proposed* sizing, so it is only evidence for
    the study if it really clears the deck's minima."""

    def test_track_and_via_sizing_clears_the_deck_minima(self) -> None:
        self.assertGreaterEqual(probe.TRACK_W, METAL_WIDTH_MIN)
        self.assertGreaterEqual(probe.TRACK_SP, METAL_SPACE_MIN)
        self.assertGreaterEqual(probe.VIA, VIA_WIDTH_MIN)
        self.assertGreaterEqual(probe.VIA_ENC, VIA_ENC_MIN)
        self.assertEqual(probe.VIA_PAD, probe.VIA + 2 * probe.VIA_ENC)

    def test_generation_is_deterministic(self) -> None:
        """Re-running the generator must reproduce the committed GDS
        byte-for-byte — the same contract ``layout/README.md`` documents for
        every generated layout in this repo."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "regenerated.gds"
            probe.build().layout.write(str(out), probe.save_options())
            self.assertEqual(out.read_bytes(), GDS.read_bytes())


@unittest.skipUnless(shutil.which("klt") is not None, "requires klt on PATH")
class ExtractionTests(unittest.TestCase):
    """The load-bearing result: the routing stack conducts, and adjacent
    tracks do not merge.

    The two resistors are wired into a series loop over nothing but the
    proposed stack, so the extracted netlist has exactly two routed nets
    (plus the deck-synthesized ``vsubs``). Four nets would mean the stack is
    invisible to extraction; one would mean the two tracks were read as
    shorted.
    """

    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    "klt", "extract", str(GDS),
                    "--deck", "gf180mcu",
                    "--top", "m2m3_stack_probe",
                    "--format", "json",
                    "-o", str(Path(tmp) / "probe.spice"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:  # pragma: no cover - tool-dependent
                raise unittest.SkipTest(f"klt extract failed: {proc.stderr.strip()}")
            cls.payload = json.loads(proc.stdout)
            cls.netlist = (Path(tmp) / "probe.spice").read_text()

    def test_both_resistors_are_recognised(self) -> None:
        self.assertEqual(self.payload["status"], "extracted")
        self.assertEqual(self.payload["device_count"], 2)
        self.assertEqual(self.payload["device_counts"], {"ppolyf_u": 2})

    def test_the_stack_conducts_and_the_two_tracks_stay_distinct(self) -> None:
        # 2 routed nets + the deck-synthesized substrate net.
        self.assertEqual(self.payload["net_count"], 3)

    def test_the_two_resistors_share_both_nets(self) -> None:
        """Series loop: each resistor's two terminals are the *same* pair of
        nets, which is only true if both Metal2/Metal3 routes conduct.

        Parsed by device model and token position (R or X record shape, see
        ``parse_resistor_records``), not by instance prefix (#303). An
        unsupported record shape fails here with the netlist attached; it is
        not grounds for a skip."""
        try:
            pair = validate_series_loop(parse_resistor_records(self.netlist))
        except ProbeNetlistError as exc:
            self.fail(f"{exc}\n--- extracted netlist ---\n{self.netlist}")
        # Exactly the two routed nets; the third net is the substrate.
        self.assertEqual(len(pair), 2)
        self.assertNotIn("vsubs", pair)


if __name__ == "__main__":
    unittest.main()
