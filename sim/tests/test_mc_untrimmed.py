#!/usr/bin/env python3
"""Unit checks for the pure helpers in sim/mc-untrimmed/run_mc_untrimmed.py.

No PDK, ngspice or fleet required:

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
REPO = SIM.parent
sys.path.insert(0, str(SIM))

_spec = importlib.util.spec_from_file_location(
    "run_mc_untrimmed", SIM / "mc-untrimmed" / "run_mc_untrimmed.py"
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

NETLIST = (REPO / "design" / "netlist" / "bandgap_top.spice").read_text()
# `ppolyf_u_1k` etc. are different models and must not be matched.
PPOLYF_LINE = re.compile(r"^X\S+(?:\s+\S+){3}\s+ppolyf_u\b", re.MULTILINE)


def fake_log(n, isup=1e-5):
    blocks = []
    for i in range(n):
        blocks.append(f"vref_val = {1.2 + 0.001 * i:.6e}\nisup_val = {isup:.6e}\n")
    return "\n".join(blocks)


class ResistorMismatchSigma(unittest.TestCase):
    def test_known_value(self):
        w, l = 2.0, 10.0
        r_w = 2e-6 - 2 * 2.55e-8
        r_l = 10e-6 - 2 * 2e-11
        expected = 0.7071 * 0.021e-6 / math.sqrt(r_w * r_l)
        self.assertAlmostEqual(
            run.resistor_mismatch_sigma(w, l) / expected, 1.0, places=12
        )

    def test_decreases_with_area(self):
        small = run.resistor_mismatch_sigma(2.0, 10.0)
        self.assertLess(run.resistor_mismatch_sigma(2.0, 40.0), small)
        self.assertLess(run.resistor_mismatch_sigma(8.0, 10.0), small)

    def test_non_physical_geometry(self):
        with self.assertRaises(ValueError):
            run.resistor_mismatch_sigma(0.0, 10.0)
        with self.assertRaises(ValueError):
            run.resistor_mismatch_sigma(2.0, 0.0)
        with self.assertRaises(ValueError):
            run.resistor_mismatch_sigma(-1.0, 10.0)


class StripTrailingEnd(unittest.TestCase):
    def test_removes_end_case_insensitive(self):
        for end in (".end", ".END", "  .End  "):
            out = run.strip_trailing_end(f"R1 a b 1k\n{end}\n")
            self.assertEqual(out, "R1 a b 1k\n")

    def test_keeps_ends(self):
        text = ".subckt foo a b\nR1 a b 1k\n.ends foo\n.ends\n.end\n"
        out = run.strip_trailing_end(text)
        self.assertIn(".ends foo", out)
        self.assertIn(".ends\n", out)
        self.assertNotIn("\n.end\n", "\n" + out)

    def test_ends_with_newline(self):
        self.assertTrue(run.strip_trailing_end("R1 a b 1k").endswith("\n"))
        self.assertTrue(run.strip_trailing_end("R1 a b 1k\n.end").endswith("\n"))

    def test_real_netlist(self):
        out = run.strip_trailing_end(NETLIST)
        self.assertNotIn(
            ".end", [ln.strip().lower() for ln in out.splitlines()]
        )


class UnwrapTopSubckt(unittest.TestCase):
    """#508: a wrapped DUT (the extracted netlist) must include at deck
    level exactly like the flat file it replaces; a DUT with no
    `bandgap_top` wrapper (the default schematic) must pass through
    unchanged."""

    def test_strips_bandgap_top_wrapper_keeps_inner_subckts(self):
        text = (
            "* header\n"
            ".subckt bandgap_top vdd vss vref\n"
            "\n"
            "XR1 a b vss ppolyf_u r_width=2u r_length=10u m=1\n"
            ".subckt bandgap_core vdd sns1 sns2 vss fb vref ibias casc\n"
            "XM1 d g vss vss nfet_03v3 L=0.5u W=2u nf=1 m=1\n"
            ".ends\n"
            "\n"
            ".ends bandgap_top\n"
        )
        out = run.unwrap_top_subckt(text)
        self.assertEqual(
            out,
            "* header\n"
            "\n"
            "XR1 a b vss ppolyf_u r_width=2u r_length=10u m=1\n"
            ".subckt bandgap_core vdd sns1 sns2 vss fb vref ibias casc\n"
            "XM1 d g vss vss nfet_03v3 L=0.5u W=2u nf=1 m=1\n"
            ".ends\n",
        )

    def test_noop_on_default_netlist_and_inner_subckts(self):
        self.assertEqual(run.unwrap_top_subckt(NETLIST), NETLIST)
        # The default DUT's only `bandgap_top` subckt text is xschem's
        # `**`-comment line; a comment must never count as a wrapper.
        self.assertIn("**.subckt bandgap_top vdd vss vref", NETLIST)

    def test_variants_of_wrapped_match_variants_of_flat(self):
        # The same-deck property #508 rests on: unwrapping the subckt form
        # and feeding it through the variant construction yields what the
        # deleted flat file yielded, minus its own header comment lines.
        subckt = (
            "* subckt-form header\n"
            ".subckt bandgap_top vdd vss vref\n"
            "\n"
            "XR1 a b vss ppolyf_u r_width=2u r_length=10u m=1\n"
            "\n"
            ".ends bandgap_top\n"
        )
        flat = (
            "* flat-form header\n"
            "\n"
            "XR1 a b vss ppolyf_u r_width=2u r_length=10u m=1\n"
        )
        new_variants, new_injected = run.prepare_dut_variants(
            run.unwrap_top_subckt(subckt)
        )
        old_variants, old_injected = run.prepare_dut_variants(flat)
        self.assertEqual(new_injected, old_injected)
        for key in ("baseline", "mm"):
            new = new_variants[key].splitlines()
            old = old_variants[key].splitlines()
            self.assertEqual(new[1:], old[1:])  # cards identical
            self.assertTrue(new[0].startswith("*"))


class InjectResistorMismatch(unittest.TestCase):
    def test_real_netlist(self):
        expected = len(PPOLYF_LINE.findall(NETLIST))
        self.assertGreater(expected, 0)
        new, injected = run.inject_resistor_mismatch(NETLIST)
        self.assertEqual(len(injected), expected)
        for info in injected:
            self.assertGreater(info["sigma"], 0)
            self.assertIn(f"{info['instance']} ", new)
        # Every rewritten line carries an agauss draw; others are untouched.
        old_lines, new_lines = NETLIST.splitlines(), new.splitlines()
        self.assertEqual(len(old_lines), len(new_lines))
        changed = 0
        for old, cur in zip(old_lines, new_lines):
            if PPOLYF_LINE.match(old):
                changed += 1
                self.assertIn("agauss(0,", cur)
                self.assertNotEqual(old, cur)
            else:
                self.assertEqual(old, cur)
        self.assertEqual(changed, expected)

    def test_single_line_values(self):
        text = "XR1 a b vss ppolyf_u r_width=2u r_length=10u m=1\n"
        new, injected = run.inject_resistor_mismatch(text)
        sigma = run.resistor_mismatch_sigma(2.0, 10.0)
        self.assertEqual(injected[0]["instance"], "XR1")
        self.assertEqual(injected[0]["width_um"], 2.0)
        self.assertEqual(injected[0]["length_um"], 10.0)
        self.assertAlmostEqual(injected[0]["sigma"], sigma)
        self.assertIn("r_width=2u", new)
        self.assertIn("r_length={10u*(1+agauss(0,", new)
        self.assertTrue(new.rstrip().endswith("m=1"))

    def test_no_ppolyf_u_raises(self):
        with self.assertRaises(RuntimeError):
            run.inject_resistor_mismatch("R1 a b 1k\nXR a b c d ppolyf_u_1k r_width=2u r_length=4u\n")

    def test_missing_geometry_raises(self):
        with self.assertRaises(RuntimeError):
            run.inject_resistor_mismatch("XR1 a b vss ppolyf_u r_width=2u m=1\n")
        with self.assertRaises(RuntimeError):
            run.inject_resistor_mismatch("XR1 a b vss ppolyf_u r_length=2u m=1\n")


class Extract(unittest.TestCase):
    def test_parses_n_samples(self):
        res = run.extract(fake_log(run.N_SAMPLES))
        self.assertEqual(res["n"], run.N_SAMPLES)
        self.assertAlmostEqual(res["min"], 1.2)
        self.assertAlmostEqual(res["max"], 1.2 + 0.001 * (run.N_SAMPLES - 1))
        self.assertAlmostEqual(
            res["mean"], 1.2 + 0.001 * (run.N_SAMPLES - 1) / 2, places=9
        )
        self.assertGreater(res["sigma"], 0)
        self.assertEqual(res["degenerate_count"], 0)

    def test_short_or_long_log_raises(self):
        with self.assertRaises(RuntimeError):
            run.extract(fake_log(run.N_SAMPLES - 1))
        with self.assertRaises(RuntimeError):
            run.extract(fake_log(run.N_SAMPLES + 1))
        with self.assertRaises(RuntimeError):
            run.extract("")

    def test_degenerate_isup_flagged(self):
        res = run.extract(fake_log(run.N_SAMPLES, isup=0.0))
        self.assertEqual(res["degenerate_count"], run.N_SAMPLES)
        self.assertEqual(res["degenerate_indices"], list(range(run.N_SAMPLES)))


class SharedConstruction(unittest.TestCase):
    """The helpers the fleet request builder reuses (#238)."""

    TB = (SIM / "mc-untrimmed" / "testbench" / "tb_mc_untrimmed.spice").read_text()

    def test_prepare_dut_variants_is_the_local_path_construction(self):
        variants, injected = run.prepare_dut_variants(NETLIST)
        self.assertEqual(variants["baseline"], run.strip_trailing_end(NETLIST))
        self.assertEqual((variants["mm"], injected), run.inject_resistor_mismatch(variants["baseline"]))
        self.assertNotIn("agauss", variants["baseline"])

    def test_testbench_constants_match_the_run_constants(self):
        self.assertEqual(
            run.testbench_constants(self.TB),
            {"mc_runs": run.N_SAMPLES, "seed": run.SEED, "supply_v": run.SUPPLY_V},
        )

    def test_testbench_circuit_lines_drop_control_includes_and_comments(self):
        lines = run.testbench_circuit_lines(self.TB)
        self.assertEqual([l.split()[0] for l in lines], ["vsup", "vssref", ".ic"])
        self.assertFalse(any("setseed" in l or "dowhile" in l for l in lines))

    def test_group_definition_covers_every_group_switch(self):
        defn = run.group_definition()
        self.assertEqual(set(defn["groups"]), set(run.GROUPS))
        self.assertEqual(defn["n_samples"], 300)
        self.assertEqual(defn["sections"], list(run.SECTIONS))


class ProvenanceClass(unittest.TestCase):
    def test_record_path_uses_the_shared_classifier(self):
        # The local copy is gone (#553): the bench classifies through the one
        # harness helper, same as the fleet request / ingest tools.
        from harness.testbench import dut_provenance_class

        self.assertIs(run.dut_provenance_class, dut_provenance_class)

    def test_classes(self):
        P = Path
        self.assertEqual(run.dut_provenance_class(P("layout/netlist/x.spice")), "extracted")
        self.assertEqual(
            run.dut_provenance_class(P("sim/dut/frozen/x.spice")), "frozen schematic"
        )
        self.assertEqual(
            run.dut_provenance_class(P("design/netlist/bandgap_top.spice")), "schematic"
        )


class BuildRecordRunContext(unittest.TestCase):
    """#561: the five per-run metadata fields are invocation state passed to
    `build_record`, not module state -- two renders in one process cannot
    contaminate each other."""

    RECORD = "20261125-000000-abc1234"
    STAMP = datetime(2026, 11, 25, tzinfo=timezone.utc)

    class _Pdk:
        variant = "gf180mcuD"
        path = "/pdk/stub"

    @classmethod
    def setUpClass(cls):
        cls.dut = REPO / "design" / "netlist" / "bandgap_top.spice"
        _variants, cls.injected = run.prepare_dut_variants(run.unwrap_top_subckt(NETLIST))
        base = {"mm_ctrl": 1.20200, "mm_res": 1.20210, "mm_fetbjt": 1.20440, "mm_all": 1.20460}
        sig = {"mm_ctrl": 0.0, "mm_res": 0.0009, "mm_fetbjt": 0.0033, "mm_all": 0.0035}
        cls.results = {}
        for group, mean0 in base.items():
            cls.results[group] = {}
            for temp in run.TEMPS:
                mean = mean0 + 0.001 * (temp - 27.0) / 100.0
                cls.results[group][temp] = {
                    "n": run.N_SAMPLES,
                    "mean": mean,
                    "sigma": sig[group],
                    "min": mean - 4 * sig[group],
                    "max": mean + 4 * sig[group],
                    "isup_mean": 2.0e-5,
                    "degenerate_count": 0,
                    "degenerate_indices": [],
                }

    def render(self, run_context=None):
        return run.build_record(
            self.RECORD, self.STAMP, self._Pdk(), "46", self.dut,
            self.injected, self.results, run_context=run_context,
        )

    def test_overridden_then_default_renders_each_run_its_own_metadata(self):
        first = self.render(run_context={
            "issue": "123",
            "supersedes": "20260101-000000-deadbee",
            "netlist_caveat": "CAVEAT-X (test override).",
            "miss_note": "NOTE-X (test override).",
            "author": "agent-fleet",
        })
        second = self.render()
        self.assertIn("agent-fleet (issue #123)", first)
        self.assertIn("- **Supersedes**: 20260101-000000-deadbee", first)
        self.assertIn("CAVEAT-X (test override).", first)
        self.assertIn("NOTE-X (test override).", first)
        self.assertIn("agent-builder (issue #13)", second)
        self.assertIn("- **Supersedes**: (none -- first record for this claim)", second)
        self.assertIn("Provisional-amp caveat", second)
        self.assertIn("feeds directly into #14's", second)
        for leaked in ("issue #123", "agent-fleet", "deadbee", "CAVEAT-X", "NOTE-X"):
            self.assertNotIn(leaked, second)

    def test_partial_context_keeps_the_historical_defaults(self):
        text = self.render(run_context={
            "issue": "239",
            "supersedes": "(none)",
            "netlist_caveat": "FLEET-CAVEAT.",
            "miss_note": "FLEET-NOTE.",
        })
        self.assertIn("agent-builder (issue #239)", text)
        self.assertIn("FLEET-CAVEAT.", text)
        self.assertIn("FLEET-NOTE.", text)
        self.assertNotIn("Provisional-amp caveat", text)

    def test_unknown_context_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(run_context={"issue": "1", "issu": "2"})

    def test_defaults_are_the_historical_first_run_values(self):
        self.assertEqual(
            run.default_run_context(),
            {
                "issue": "13",
                "supersedes": "(none -- first record for this claim)",
                "netlist_caveat": run.DEFAULT_NETLIST_CAVEAT,
                "miss_note": run.DEFAULT_MISS_NOTE,
                "author": run.DEFAULT_AUTHOR,
            },
        )


if __name__ == "__main__":
    unittest.main()
