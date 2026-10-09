#!/usr/bin/env python3
"""Unit-contract regressions for sim/output-noise (issue #252). NEWLY CREATED file.

PDK-free. ngspice's `noise` analysis (>= 27) returns onoise_spectrum in
V/sqrt(Hz) and onoise_total in V rms unless `sqrnoise` is set (verified by
sim/output-noise/unit-probe/). The bench must therefore only scale, never
sqrt(). These tests fail on the original double-square-root shape.

    python3 -m unittest sim/tests/test_output_noise_units.py -v
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import runner, testbench  # noqa: E402
from harness.pdk import Pdk  # noqa: E402

BENCH = SIM_DIR / "output-noise"
PROBE = BENCH / "unit-probe"

# Raw ngspice values (default amplitude mode) -> expected reported values.
RAW_TOTAL_V = 18.3e-6          # onoise_total, V rms
RAW_SPOT_V_RTHZ = {"80": 9.0e-9, "100": 4.5e-9, "120": 2.25e-9}


def evaluate(expr: str, vectors: dict[str, float]) -> float:
    """Evaluate a tb.json measure expression with known raw vectors.

    Only `sqrt` and `real` are needed by this bench's grammar.
    """
    py = expr
    for name, val in vectors.items():
        py = py.replace(name, repr(val))
    return float(eval(py, {"__builtins__": {}}, {"sqrt": math.sqrt, "real": lambda x: x}))


class OutputNoiseConversion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tb = testbench.load(BENCH)

    def test_integrated_is_scaled_only(self):
        got = evaluate(
            self.tb.measure["onoise_int_0p1_10hz_uvrms"], {"noise2.onoise_total": RAW_TOTAL_V}
        )
        self.assertAlmostEqual(got, 18.3, places=9)
        # The double-sqrt shape would give sqrt(18.3e-6)*1e6 = 4278 "uVrms".
        self.assertNotAlmostEqual(got, math.sqrt(RAW_TOTAL_V) * 1e6, delta=1.0)

    def test_spot_outputs_are_scaled_only(self):
        for key, idx, nv in (
            ("onoise_1khz_nv_rthz", "80", 9.0),
            ("onoise_10khz_nv_rthz", "100", 4.5),
            ("onoise_100khz_nv_rthz", "120", 2.25),
        ):
            vec = f"noise3.onoise_spectrum[{idx}]"
            self.assertIn(vec, self.tb.measure[key])
            got = evaluate(self.tb.measure[key], {vec: RAW_SPOT_V_RTHZ[idx]})
            self.assertAlmostEqual(got, nv, places=9)
            self.assertNotIn("sqrt", self.tb.measure[key])

    def test_no_sqrt_in_any_noise_measure(self):
        for key, expr in self.tb.measure.items():
            if key.startswith("onoise_"):
                self.assertNotIn("sqrt", expr, key)

    def test_keys_bands_and_frequency_checks_preserved(self):
        self.assertEqual(
            set(self.tb.measure),
            {
                "onoise_int_0p1_10hz_uvrms", "onoise_1khz_nv_rthz", "onoise_10khz_nv_rthz",
                "onoise_100khz_nv_rthz", "vref_op", "f_band_lo_hz", "f_band_hi_hz",
                "f_spot_1khz_hz", "f_spot_10khz_hz", "f_spot_100khz_hz",
            },
        )
        m = self.tb.measure
        self.assertEqual(m["f_band_lo_hz"], "real(noise1.frequency[0])")
        self.assertEqual(m["f_band_hi_hz"], "real(noise1.frequency[40])")
        self.assertEqual(m["f_spot_1khz_hz"], "real(noise3.frequency[80])")
        self.assertEqual(m["f_spot_10khz_hz"], "real(noise3.frequency[100])")
        self.assertEqual(m["f_spot_100khz_hz"], "real(noise3.frequency[120])")
        self.assertEqual(m["vref_op"], "op1.v(vref)")

    def test_mode_contract_and_analysis_order(self):
        a = list(self.tb.analyses)
        self.assertEqual(a[0], "unset sqrnoise")
        self.assertEqual(
            a[1:],
            ["op", "noise v(vref) vsup dec 20 0.1 10", "noise v(vref) vsup dec 20 0.1 100k"],
        )

    def test_deck_forces_amplitude_mode_before_noise(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "libs.tech" / "ngspice").mkdir(parents=True)
            (root / "SOURCES").write_text("open_pdks deadbeef\n")
            pdk = Pdk(path=root, variant="fake", source="test")
            from harness.corners import CORNERS, PvtPoint
            deck = runner.compose_deck(
                self.tb, pdk, PvtPoint(corner=CORNERS["tt"], temp_c=27.0, vdd=3.3)
            )
        self.assertIsNone(re.search(r"(?<!un)set sqrnoise", deck))
        self.assertLess(deck.index("unset sqrnoise"), deck.index("noise v(vref) vsup"))

    def test_claim_text_matches_contract(self):
        self.assertNotIn("provisional sizing", self.tb.claim)
        self.assertIn("substituted for", self.tb.claim)
        self.assertNotIn("mean-square", self.tb.claim)
        self.assertNotIn("V^2/Hz density", self.tb.claim)
        self.assertIn("telescopic-cascode", self.tb.claim)


@unittest.skipUnless(shutil.which("ngspice"), "ngspice not installed")
class ResistorProbe(unittest.TestCase):
    """Bounded single-point PDK-free probe (2 short runs; not a PVT grid)."""

    K, T, R, FL, FH = 1.380649e-23, 300.15, 5000.0, 0.1, 10.0

    def run_mode(self, line: str) -> dict[str, float]:
        deck = (PROBE / "resistor_noise_probe.spice").read_text().replace("SQRNOISE_MODE", line)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "deck.cir").write_text(deck)
            # -n: ignore every .spiceinit; HOME pinned to the empty temp dir.
            p = subprocess.run(
                ["ngspice", "-n", "-b", "deck.cir"], cwd=d, env={"HOME": d, "PATH": "/usr/bin:/bin"},
                capture_output=True, text=True, timeout=60,
            )
        return {m.group(1): float(m.group(2)) for m in
                re.finditer(r"^(\S+) = ([-+0-9.eE]+)$", p.stdout, re.M)}

    def test_units(self):
        psd = 4 * self.K * self.T * self.R
        dens, rms = math.sqrt(psd), math.sqrt(psd * (self.FH - self.FL))
        d = self.run_mode("unset sqrnoise")
        s = self.run_mode("set sqrnoise")
        for k in ("noise1.onoise_spectrum[0]", "noise3.onoise_spectrum[100]"):
            self.assertAlmostEqual(d[k] / dens, 1.0, delta=1e-3)
            self.assertAlmostEqual(s[k] / psd, 1.0, delta=1e-3)
        self.assertAlmostEqual(d["noise2.onoise_total"] / rms, 1.0, delta=1e-3)
        self.assertAlmostEqual(s["noise2.onoise_total"] / rms**2, 1.0, delta=1e-3)


if __name__ == "__main__":
    unittest.main()
