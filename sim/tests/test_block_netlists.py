#!/usr/bin/env python3
"""Checks for ``sim/tools/check_block_netlists.py`` (#475). No PDK or xschem.

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM / "tools"))

import check_block_netlists as cbn  # noqa: E402

REPO = SIM.parent
NETLIST_DIR = REPO / "design" / "netlist"

#: A minimal but shape-faithful top export: one wrapper cell, four plain
#: ``.subckt`` definitions, the trim default nested inside its subcircuit.
SYN_TOP = (
    "**.subckt bandgap_top vdd vss vref\n"
    "Xx1 vdd sns1 sns2 vss fb vref ibias casc bandgap_core\n"
    "**.ends\n"
    ".subckt bandgap_core vdd sns1 sns2 vss fb vref ibias casc\n"
    "XM1 d1 fb vdd vdd pfet_03v3 L=8.5u W=85u m=1\n"
    "XR1 e3 tn0 vss ppolyf_u r_width=2u r_length=446.000000u m=1\n"
    "XXTRIM tn0 vref vss bandgap_trim\n"
    ".ends\n"
    ".subckt bandgap_amp in_p in_n vss out vdd tail_bias\n"
    "XCC vdd out cap_mim_2f0_m4m5_noshield c_width=60u c_length=60u m=1\n"
    ".ends\n"
    ".subckt bandgap_startup vdd vss fb casc ibias\n"
    "XRPU det vdd vss ppolyf_u_1k r_width=2u r_length=4000u m=1\n"
    ".ends\n"
    ".subckt bandgap_trim bot top sub\n"
    "**** begin user architecture code\n"
    ".param trim_code=32\n"
    "**** end user architecture code\n"
    "XRU0 bot tn1 sub ppolyf_u r_width=2u r_length=2.771871u m=1\n"
    "RS0 tn1 bot {1e-3 + 1e12*(floor(trim_code/1)-2*floor(trim_code/2))} m=1\n"
    ".ends\n"
    ".end\n"
)

#: Matching per-block exports.  XM1 is split over a ``+`` continuation and
#: surrounded by comments, so joining and comment-stripping are exercised;
#: the core carries an expanded trim cell; the standalone trim hoists its
#: ``.param`` default ahead of the wrapper.
SYN_CORE = (
    "** sch_path: design/bandgap_core.sch\n"
    "* expanding   symbol:  bandgap_trim.sym # of pins=3\n"
    ".subckt bandgap_trim bot top sub\n"
    ".param trim_code=32\n"
    "XRU0 bot tn1 sub ppolyf_u r_width=2u r_length=2.771871u m=1\n"
    "RS0 tn1 bot {1e-3 + 1e12*(floor(trim_code/1)-2*floor(trim_code/2))} m=1\n"
    ".ends\n"
    "**.subckt bandgap_core vdd sns1 sns2 vss fb vref ibias casc\n"
    "\n"
    "*.iopin vdd\n"
    "XM1 d1 fb vdd vdd pfet_03v3 L=8.5u W=85u\n"
    "+ m=1\n"
    "XR1 e3 tn0 vss ppolyf_u r_width=2u r_length=446.000000u m=1\n"
    "XXTRIM tn0 vref vss bandgap_trim\n"
    "**.ends\n"
    ".end\n"
)

SYN_AMP = (
    "**.subckt bandgap_amp in_p in_n vss out vdd tail_bias\n"
    "XCC vdd out cap_mim_2f0_m4m5_noshield c_width=60u c_length=60u m=1\n"
    "**.ends\n"
    ".end\n"
)

SYN_STARTUP = (
    "**.subckt bandgap_startup vdd vss fb casc ibias\n"
    "XRPU det vdd vss ppolyf_u_1k r_width=2u r_length=4000u m=1\n"
    "**.ends\n"
    ".end\n"
)

SYN_TRIM = (
    "** sch_path: design/bandgap_trim.sch\n"
    "\n"
    ".param trim_code=32\n"
    "\n"
    "**.subckt bandgap_trim bot top sub\n"
    "*.iopin bot\n"
    "XRU0 bot tn1 sub ppolyf_u r_width=2u r_length=2.771871u m=1\n"
    "RS0 tn1 bot {1e-3 + 1e12*(floor(trim_code/1)-2*floor(trim_code/2))} m=1\n"
    "**.ends\n"
    ".end\n"
)


def write_tree(root: Path, texts: dict[str, str]) -> None:
    """Write ``bandgap_<key>.spice`` files (key 'top' -> bandgap_top.spice)."""
    for key, text in texts.items():
        (root / f"bandgap_{key}.spice").write_text(text)


def synthetic_tree(root: Path, **overrides: str) -> Path:
    texts = {"top": SYN_TOP, "core": SYN_CORE, "amp": SYN_AMP,
             "startup": SYN_STARTUP, "trim": SYN_TRIM}
    texts.update(overrides)
    write_tree(root, texts)
    return root / "bandgap_top.spice"


def committed_tree(root: Path, **overrides: str) -> Path:
    """The real committed exports copied into root; overrides replace text."""
    texts = {p.stem.removeprefix("bandgap_"): p.read_text()
             for p in sorted(NETLIST_DIR.glob("bandgap_*.spice"))}
    texts.update(overrides)
    write_tree(root, texts)
    return root / "bandgap_top.spice"


def replace_once(text: str, old: str, new: str) -> str:
    """Replace exactly one occurrence; asserts the mutation landed."""
    assert text.count(old) >= 1, f"fixture lacks {old!r}"
    return text.replace(old, new, 1)


def drop_cell(text: str, name: str) -> str:
    """Remove one cell (wrapper ``**.subckt`` or plain ``.subckt``) wholesale."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if not skipping and re.match(rf"^\**\.subckt\s+{name}\b", stripped):
            skipping = True
            continue
        if skipping:
            if re.match(r"^\**\.ends\b", stripped):
                skipping = False
            continue
        out.append(line)
    assert not skipping, f"cell {name} never closed"
    return "\n".join(out) + "\n"


def flagged(errors: list[str], needle: str) -> list[str]:
    return [e for e in errors if needle in e]


class Parse(unittest.TestCase):
    def test_continuation_joined_and_comments_dropped(self):
        cells, file_params, problems = cbn.parse_export(SYN_CORE)
        self.assertEqual(problems, [])
        self.assertEqual(file_params, {})
        self.assertEqual(list(cells), ["bandgap_trim", "bandgap_core"])
        core = cells["bandgap_core"]
        self.assertEqual(core.pins, ["vdd", "sns1", "sns2", "vss", "fb", "vref", "ibias", "casc"])
        self.assertEqual(core.devices[0], ("XM1", "d1", "fb", "vdd", "vdd", "pfet_03v3",
                                           "L=8.5u", "W=85u", "m=1"))
        self.assertEqual(len(core.devices), 3)

    def test_file_level_param_captured(self):
        _, file_params, problems = cbn.parse_export(SYN_TRIM)
        self.assertEqual(problems, [])
        self.assertEqual(file_params, {"trim_code": "32"})

    def test_orphan_continuation_is_a_problem(self):
        _, _, problems = cbn.parse_export("+ m=1\n.end\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("continuation", problems[0])

    def test_stray_device_outside_any_cell_is_a_problem(self):
        _, _, problems = cbn.parse_export("XM1 a b c model\n.end\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("outside any cell", problems[0])


class InSync(unittest.TestCase):
    def test_synthetic_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = synthetic_tree(Path(tmp))
            self.assertEqual(cbn.check(top, Path(tmp)), [])

    def test_committed_exports_pass(self):
        self.assertEqual(cbn.check(cbn.TOP_DEFAULT, cbn.EXPORT_DIR_DEFAULT), [])

    def test_comments_only_edit_passes(self):
        core = SYN_CORE.replace("*.iopin vdd\n", "*.iopin vdd\n* a fresh comment\n")
        with tempfile.TemporaryDirectory() as tmp:
            top = synthetic_tree(Path(tmp), core=core)
            self.assertEqual(cbn.check(top, Path(tmp)), [])


class Drift(unittest.TestCase):
    """One meaningful value per block (#475 test plan), on copies of the
    committed exports."""

    def _check_committed_with(self, **overrides: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            top = committed_tree(Path(tmp), **overrides)
            return cbn.check(top, Path(tmp))

    def test_core_device_parameter(self):
        errs = self._check_committed_with(
            core=replace_once((NETLIST_DIR / "bandgap_core.spice").read_text(),
                              "L=8.5u W=85u", "L=8.5u W=84u"))
        self.assertTrue(flagged(errs, "bandgap_core.spice [bandgap_core]"), errs)
        self.assertTrue(flagged(errs, "XM1"), errs)

    def test_amp_device_parameter(self):
        errs = self._check_committed_with(
            amp=replace_once((NETLIST_DIR / "bandgap_amp.spice").read_text(),
                             "c_length=60u", "c_length=61u"))
        self.assertTrue(flagged(errs, "bandgap_amp.spice [bandgap_amp]"), errs)

    def test_startup_device_parameter(self):
        errs = self._check_committed_with(
            startup=replace_once((NETLIST_DIR / "bandgap_startup.spice").read_text(),
                                 "r_length=4000u", "r_length=4001u"))
        self.assertTrue(flagged(errs, "bandgap_startup.spice [bandgap_startup]"), errs)

    def test_trim_device_parameter(self):
        errs = self._check_committed_with(
            trim=replace_once((NETLIST_DIR / "bandgap_trim.spice").read_text(),
                              "r_length=2.771871u", "r_length=2.800000u"))
        self.assertTrue(flagged(errs, "bandgap_trim.spice [bandgap_trim]"), errs)

    def test_core_continuation_line(self):
        errs = self._check_committed_with(
            core=replace_once((NETLIST_DIR / "bandgap_core.spice").read_text(),
                              "nrs='0.18u / W' sa=0 sb=0 sd=0 m=1",
                              "nrs='0.18u / W' sa=0 sb=0 sd=0 m=2"))
        self.assertTrue(flagged(errs, "bandgap_core.spice [bandgap_core]"), errs)
        self.assertTrue(flagged(errs, "XM1"), errs)

    def test_core_expanded_trim_cell_drift_names_trim(self):
        errs = self._check_committed_with(
            core=replace_once((NETLIST_DIR / "bandgap_core.spice").read_text(),
                              "RS0 tn1 bot {1e-3", "RS0 tn1 bot {1e-4"))
        self.assertTrue(flagged(errs, "bandgap_core.spice [bandgap_trim]"), errs)

    def test_swapped_pins(self):
        text = (NETLIST_DIR / "bandgap_startup.spice").read_text()
        assert "**.subckt bandgap_startup vdd vss fb casc ibias" in text
        swapped = text.replace("**.subckt bandgap_startup vdd vss fb casc ibias",
                               "**.subckt bandgap_startup vss vdd fb casc ibias")
        errs = self._check_committed_with(startup=swapped)
        self.assertTrue(flagged(errs, "pins"), errs)

    def test_missing_cell_in_export(self):
        errs = self._check_committed_with(
            trim=drop_cell((NETLIST_DIR / "bandgap_trim.spice").read_text(), "bandgap_trim"))
        self.assertTrue(flagged(errs, "no bandgap_trim cell"), errs)

    def test_missing_definition_in_top(self):
        errs = self._check_committed_with(
            top=drop_cell((NETLIST_DIR / "bandgap_top.spice").read_text(), "bandgap_amp"))
        self.assertTrue(flagged(errs, "no same-named .subckt"), errs)
        self.assertTrue(flagged(errs, "bandgap_amp"), errs)

    def test_missing_export_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            committed_tree(Path(tmp))
            (Path(tmp) / "bandgap_startup.spice").unlink()
            errs = cbn.check(Path(tmp) / "bandgap_top.spice", Path(tmp))
        self.assertTrue(flagged(errs, "bandgap_startup.spice: block export missing"), errs)

    def test_missing_top_file(self):
        errs = cbn.check(Path("/nonexistent/bandgap_top.spice"), Path("/nonexistent"))
        self.assertEqual(errs, ["/nonexistent/bandgap_top.spice: top export missing"])

    def test_param_default_drift_in_export(self):
        errs = self._check_committed_with(
            trim=replace_once((NETLIST_DIR / "bandgap_trim.spice").read_text(),
                              ".param trim_code=32", ".param trim_code=31"))
        self.assertTrue(flagged(errs, ".param trim_code"), errs)

    def test_param_default_drift_in_top(self):
        errs = self._check_committed_with(
            top=replace_once((NETLIST_DIR / "bandgap_top.spice").read_text(),
                             ".param trim_code=32", ".param trim_code=33"))
        self.assertTrue(flagged(errs, ".param trim_code"), errs)

    def test_device_count_change(self):
        text = (NETLIST_DIR / "bandgap_startup.spice").read_text()
        out: list[str] = []
        skip_cont = False
        for line in text.splitlines():
            if skip_cont and line.startswith("+"):
                skip_cont = False
                continue
            skip_cont = False
            if line.startswith("XMKCASC"):
                skip_cont = True
                continue
            out.append(line)
        errs = self._check_committed_with(startup="\n".join(out) + "\n")
        self.assertTrue(flagged(errs, "device statements"), errs)
        self.assertTrue(flagged(errs, "XMKCASC"), errs)


if __name__ == "__main__":
    unittest.main()
