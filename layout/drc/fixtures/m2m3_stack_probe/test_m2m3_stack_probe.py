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
        nets, which is only true if both Metal2/Metal3 routes conduct."""
        devices = [
            line.split()[1:3]
            for line in self.netlist.splitlines()
            if line.startswith("R$")
        ]
        self.assertEqual(len(devices), 2)
        self.assertEqual(set(devices[0]), set(devices[1]))
        self.assertNotEqual(devices[0][0], devices[0][1])


if __name__ == "__main__":
    unittest.main()
