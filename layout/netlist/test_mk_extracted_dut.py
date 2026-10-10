#!/usr/bin/env python3
"""Unit tests for ``mk_extracted_dut.py`` (gf180-bandgap#315).

The script is the single step between what ``klt extract --parasitics``
measured and the post-layout DUT netlist the extracted-level PVT evidence
simulates. These tests use small synthetic ``extract`` / ``lvs`` dicts; no
PDK and no ``klayout``/``klt`` package is required.

    python3 -m unittest layout.netlist.test_mk_extracted_dut -v
    # or, from this directory:
    python3 -m unittest test_mk_extracted_dut -v
"""

from __future__ import annotations

import contextlib
import copy
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mk_extracted_dut as mk  # noqa: E402


def make_extract() -> dict:
    """A minimal extract report satisfying every back-annotation precondition.

    nfet: body on the deck-synthesised ``vsubs`` (BA1).
    pfet: body alone on anonymous well net ``$W`` (BA2).
    two bjt units: bases alone on ``$B1``/``$B2`` (BA3).
    one MiM cap: bottom plate on ``vdd``, top plate ``$F`` (paired to fb),
    with ``$F`` also used by the resistor so it is not isolated.
    """
    devices = [
        {"name": "$1", "class": "nfet",
         "nets": {"d": "$F", "g": "$G", "s": "vss", "b": "vsubs"},
         "params": {"w_um": 2.0, "l_um": 0.5}},
        {"name": "$2", "class": "pfet",
         "nets": {"d": "$F", "g": "$G", "s": "vdd", "b": "$W"},
         "params": {"w_um": 4.0, "l_um": 0.5}},
        {"name": "$3", "class": "ppolyf_u",
         "nets": {"a": "$F", "b": "$G", "w": "vdd"},
         "params": {"w_um": 1.0, "l_um": 10.0}},
        {"name": "$4", "class": "bjt",
         "nets": {"c": "vsubs", "b": "$B1", "e": "$G"}, "params": {}},
        {"name": "$5", "class": "bjt",
         "nets": {"c": "vsubs", "b": "$B2", "e": "$G"}, "params": {}},
        {"name": "$6", "class": mk.CAP_MODEL,
         "nets": {"a": "vdd", "b": "$F"}, "params": {"area_um2": 100.0}},
    ]
    return {
        "file": "synthetic.gds",
        "deck": "synthetic-deck",
        "pdk": {"variant": "gf180mcuD", "version": "1.0"},
        "device_count": len(devices),
        "device_counts": {"nfet": 1, "pfet": 1, "ppolyf_u": 1, "bjt": 2, mk.CAP_MODEL: 1},
        "nets": [{"name": n} for n in
                 ("$F", "$G", "$W", "$B1", "$B2", "vdd", "vss", "vsubs")],
        "devices": devices,
        "parasitics": {
            "r_count": 1, "c_count": 1,
            "total_resistance_ohm": 12.5, "total_capacitance_ff": 3.0,
            "nets": [{"net": "$G", "resistance_ohm": 12.5, "capacitance_ff": 3.0}],
        },
    }


def make_lvs() -> dict:
    return {"net_correspondence": [
        {"layout": "$F", "reference": "FB"},
        {"layout": "$G", "reference": "net-g.1"},
        {"layout": "$B1", "reference": None},
    ]}


def device(extract: dict, name: str) -> dict:
    return next(d for d in extract["devices"] if d["name"] == name)


class SanitizeAndNamesTests(unittest.TestCase):
    def test_sanitize_strips_dollar_lowercases_and_replaces_illegal(self):
        self.assertEqual(mk._sanitize("$12"), "12")
        self.assertEqual(mk._sanitize("\\$A b-C.d"), "__a_b_c_d")
        self.assertNotRegex(mk._sanitize("$x y\\z$"), r"[$\\\s]")

    def test_lvs_names_win_and_are_sanitized(self):
        m = mk.net_name_map(make_extract(), make_lvs())
        self.assertEqual(m["$F"], "fb")
        self.assertEqual(m["$G"], "net_g_1")

    def test_unpaired_nets_get_mechanical_names(self):
        m = mk.net_name_map(make_extract(), make_lvs())
        self.assertEqual(m["$W"], "w")
        # Entry with no reference is not a pairing.
        self.assertEqual(m["$B1"], "b1")

    def test_no_lvs_report(self):
        m = mk.net_name_map(make_extract(), None)
        self.assertEqual(m["$F"], "f")
        self.assertEqual(m["vdd"], "vdd")

    def test_pins_keep_spelling_even_if_lvs_pairs_them(self):
        lvs = {"net_correspondence": [{"layout": "vsubs", "reference": "SUBSTRATE"}]}
        m = mk.net_name_map(make_extract(), lvs)
        self.assertEqual(m["vsubs"], "vsubs")

    def test_names_collision_free_for_distinct_anonymous_nets(self):
        m = mk.net_name_map(make_extract(), None)
        anon = [m[k] for k in ("$F", "$G", "$W", "$B1", "$B2")]
        self.assertEqual(len(set(anon)), len(anon))

    def test_no_dollar_in_any_name(self):
        m = mk.net_name_map(make_extract(), make_lvs())
        self.assertFalse([v for v in m.values() if "$" in v or "\\" in v])


class BackAnnotationTests(unittest.TestCase):
    def build(self, extract: dict):
        names = mk.net_name_map(extract, make_lvs())
        return mk.build_back_annotations(extract, names)

    def test_happy_path_aliases(self):
        a = self.build(make_extract())
        self.assertEqual(a("vsubs"), "vss")
        self.assertEqual(a("$W"), "vdd")
        self.assertEqual(a("$B1"), "vss")
        self.assertEqual(a("$B2"), "vss")
        self.assertEqual(a("$F"), "$F")  # no BA4: top plate untouched
        self.assertEqual([e.split(":")[0] for e in a.log],
                         ["BA1", "BA2", "BA3", "BA3"])

    # -- BA1
    def test_ba1_missing_vsubs_raises(self):
        ex = make_extract()
        for d in ex["devices"]:
            for t, n in d["nets"].items():
                if n == "vsubs":
                    d["nets"][t] = "vss"
        with self.assertRaisesRegex(AssertionError, "vsubs"):
            self.build(ex)

    # -- BA2
    def test_ba2_no_well_net_raises(self):
        ex = make_extract()
        device(ex, "$2")["nets"]["b"] = "vdd"  # body already on the real net
        with self.assertRaisesRegex(AssertionError, "PMOS well"):
            self.build(ex)

    def test_ba2_two_well_nets_raises(self):
        ex = make_extract()
        ex["devices"].append({"name": "$7", "class": "pfet",
                              "nets": {"d": "$F", "g": "$G", "s": "vdd", "b": "$W2"},
                              "params": {"w_um": 1.0, "l_um": 0.5}})
        with self.assertRaisesRegex(AssertionError, "PMOS well"):
            self.build(ex)

    def test_ba2_well_shared_with_other_terminal_not_a_well_net(self):
        ex = make_extract()
        device(ex, "$3")["nets"]["w"] = "$W"  # well reaches something else
        with self.assertRaisesRegex(AssertionError, "PMOS well"):
            self.build(ex)

    # -- BA3
    def test_ba3_base_already_on_real_net_raises(self):
        ex = make_extract()
        device(ex, "$4")["nets"]["b"] = "vss"
        with self.assertRaisesRegex(AssertionError, "isolated base net"):
            self.build(ex)

    def test_ba3_shared_base_net_raises(self):
        ex = make_extract()
        device(ex, "$5")["nets"]["b"] = "$B1"  # two units, one base net
        with self.assertRaisesRegex(AssertionError, "isolated base net"):
            self.build(ex)

    # -- MiM premise that replaced BA4
    def test_cap_count_not_one_raises(self):
        ex = make_extract()
        ex["devices"] = [d for d in ex["devices"] if d["class"] != mk.CAP_MODEL]
        with self.assertRaisesRegex(AssertionError, "exactly one MiM cap"):
            self.build(ex)
        ex = make_extract()
        ex["devices"].append(copy.deepcopy(device(ex, "$6")) | {"name": "$8"})
        with self.assertRaisesRegex(AssertionError, "exactly one MiM cap"):
            self.build(ex)

    def test_cap_floating_plate_raises(self):
        ex = make_extract()
        device(ex, "$6")["nets"]["b"] = "$ISO"  # only the cap touches it
        with self.assertRaisesRegex(AssertionError, "isolated"):
            self.build(ex)

    def test_cap_bottom_plate_not_vdd_raises(self):
        ex = make_extract()
        device(ex, "$6")["nets"]["a"] = "$G"
        with self.assertRaisesRegex(AssertionError, "bottom plate"):
            self.build(ex)

    def test_cap_top_plate_not_fb_raises(self):
        ex = make_extract()
        device(ex, "$6")["nets"]["b"] = "$G"  # real net, but paired as net_g_1
        with self.assertRaisesRegex(AssertionError, "top plate"):
            self.build(ex)


class EmitTests(unittest.TestCase):
    def emit(self, flat=False, extract=None):
        ex = extract or make_extract()
        ex["_ae_cache"] = {"$4": 25.0, "$5": 25.0}
        return mk.emit(ex, make_lvs(), flat=flat)

    def test_wrapped_has_subckt_and_ends(self):
        lines, _, counts = self.emit()
        self.assertEqual(lines[0], ".subckt bandgap_top vdd vss vref")
        self.assertIn(".ends bandgap_top", lines)
        self.assertEqual(counts["bjt"], 2)

    def test_flat_omits_subckt_wrapper(self):
        lines, _, _ = self.emit(flat=True)
        text = "\n".join(lines)
        self.assertNotRegex(text, r"(?m)^\.subckt")
        self.assertNotRegex(text, r"(?m)^\.ends")
        self.assertIn("FLAT form", text)

    def test_no_dollar_or_backslash_in_cards(self):
        lines, _, _ = self.emit()
        self.assertFalse([l for l in lines if "$" in l or "\\" in l])

    def test_mos_junction_geometry_from_sd_col(self):
        lines, _, _ = self.emit()
        card = next(l for l in lines if l.startswith("XM1 "))
        w, sd = 2.0, mk.SD_COL_UM
        area, perim = mk._fmt(w * sd), mk._fmt(2 * (w + sd))
        self.assertIn("nfet_03v3", card)
        for tok in (f"ad={area}p", f"as={area}p", f"pd={perim}u", f"ps={perim}u",
                    "nf=1", "m=1", "L=0.5u", "W=2u"):
            self.assertIn(tok, card.split())
        # body went through BA1 (vsubs -> vss); drain through T1 (fb)
        self.assertEqual(card.split()[1:5], ["fb", "net_g_1", "vss", "vss"])

    def test_pmos_body_back_annotated_to_vdd(self):
        lines, _, _ = self.emit()
        card = next(l for l in lines if l.startswith("XM2 "))
        self.assertIn("pfet_03v3", card)
        self.assertEqual(card.split()[4], "vdd")
        self.assertIn(f"ad={mk._fmt(4.0 * mk.SD_COL_UM)}p", card.split())

    def test_resistor_card_carries_drawn_geometry(self):
        lines, _, _ = self.emit()
        card = next(l for l in lines if l.startswith("XR3 "))
        self.assertIn("ppolyf_u", card.split())
        self.assertIn("r_width=1u", card.split())
        self.assertIn("r_length=10u", card.split())

    def test_pnp_bound_by_ae_and_bases_to_vss(self):
        lines, _, _ = self.emit()
        cards = [l for l in lines if l.startswith("XQ")]
        self.assertEqual(len(cards), 2)
        for c in cards:
            self.assertIn("pnp_05p00x05p00", c)
            self.assertEqual(c.split()[2], "vss")

    def test_pnp_unknown_ae_raises(self):
        ex = make_extract()
        ex["_ae_cache"] = {"$4": 37.0, "$5": 25.0}
        with self.assertRaisesRegex(AssertionError, "no gf180mcu PNP"):
            mk.emit(ex, make_lvs())

    def test_cap_card_side_from_area(self):
        lines, _, _ = self.emit()
        card = next(l for l in lines if l.startswith("XC6 "))
        self.assertIn("c_width=10u", card.split())
        self.assertIn("c_length=10u", card.split())
        self.assertEqual(card.split()[1:3], ["vdd", "fb"])

    def test_unhandled_class_is_hard_error(self):
        ex = make_extract()
        ex["devices"].append({"name": "$9", "class": "mystery",
                              "nets": {}, "params": {}})
        with self.assertRaises(SystemExit):
            mk.emit(ex, make_lvs())

    def test_parasitics_carried_with_names_and_substrate_alias(self):
        lines, _, _ = self.emit()
        self.assertIn("Rg_par net_g_1 net_g_1__par 12.5", lines)
        self.assertIn("Cg_par net_g_1__par vss 3e-15", lines)


class AeParsingTests(unittest.TestCase):
    def parse(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.spice"
            p.write_text(text)
            return mk.parse_ae(p)

    def test_parse_ae_units_and_escaped_names(self):
        out = self.parse(
            "* comment\n"
            "Q\\$4 \\$1 \\$2 \\$3 bjt AE=25P PE=20U\n"
            "Q5 a b c bjt AE=100P\n"
            "Q\\$6 a b c bjt AE=2.5e-11\n"
            "Q7 a b c bjt AE=0.1N\n"
            "R1 a b 1k\n"
        )
        self.assertEqual(set(out), {"$4", "$5", "$6", "$7"})
        self.assertAlmostEqual(out["$4"], 25.0)
        self.assertAlmostEqual(out["$5"], 100.0)
        self.assertAlmostEqual(out["$6"], 25.0)
        self.assertAlmostEqual(out["$7"], 100.0)  # 0.1n m^2

    def test_round_trip_into_emit(self):
        ex = make_extract()
        ex["_ae_cache"] = self.parse(
            "Q\\$4 c b e bjt AE=25P\nQ\\$5 c b e bjt AE=100P\n")
        self.assertAlmostEqual(mk._bjt_ae_um2(ex, "$4"), 25.0)
        self.assertAlmostEqual(mk._bjt_ae_um2(ex, "$5"), 100.0)
        lines, _, _ = mk.emit(ex, make_lvs())
        models = [l.split()[4] for l in lines if l.startswith("XQ")]
        self.assertEqual(models, ["pnp_05p00x05p00", "pnp_10p00x10p00"])

    def test_bjt_ae_default_when_unreported(self):
        self.assertEqual(mk._bjt_ae_um2(make_extract(), "$nope"), 25.0)


class MainTests(unittest.TestCase):
    """End-to-end through ``main()``: header contents and ``--check``."""

    def setUp(self):
        # main() reports paths relative to REPO_ROOT, so work under it.
        self._tmp = tempfile.TemporaryDirectory(dir=mk.REPO_ROOT)
        self.addCleanup(self._tmp.cleanup)
        d = Path(self._tmp.name)
        import json
        self.extract = d / "r.extract.json"
        self.extract.write_text(json.dumps(make_extract()))
        (d / "r.extracted.spice").write_text(
            "Q\\$4 c b e bjt AE=25P\nQ\\$5 c b e bjt AE=25P\n")
        self.lvs = d / "r.lvs.json"
        self.lvs.write_text(json.dumps(make_lvs()))
        self.out = d / "out.spice"

    def run_main(self, *extra: str) -> tuple[int, str]:
        argv = ["mk_extracted_dut.py", "--extract", str(self.extract),
                "--lvs", str(self.lvs), "-o", str(self.out), *extra]
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            rc = mk.main()
        return rc, buf.getvalue()

    def test_transform_keys_are_the_expected_set(self):
        self.assertEqual([k for k, _ in mk.TRANSFORMS],
                         [f"T{i}" for i in range(1, 10)])

    def test_header_lists_every_applied_transform(self):
        rc, _ = self.run_main()
        self.assertEqual(rc, 0)
        text = self.out.read_text()
        for key, _ in mk.TRANSFORMS:
            self.assertRegex(text, rf"(?m)^\* {key}\. ")

    def test_removing_a_transform_drops_it_from_header(self):
        # Guards the test above: the header is driven by TRANSFORMS, so a
        # removed entry must disappear (and the full-set check must trip).
        with mock.patch.object(mk, "TRANSFORMS", mk.TRANSFORMS[:-1]):
            self.run_main()
        text = self.out.read_text()
        self.assertNotRegex(text, r"(?m)^\* T9\. ")

    def test_header_lists_applied_merges_and_sha(self):
        self.run_main()
        text = self.out.read_text()
        self.assertIn("*   BA1: vsubs -> vss", text)
        self.assertIn("*   BA2: $W -> vdd", text)
        self.assertIn("*   BA3: $B1 -> vss", text)
        self.assertRegex(text, r"(?m)^\* sha256 \(this file, sans this line\): [0-9a-f]{32}$")

    def test_flat_flag_omits_wrapper(self):
        self.run_main("--flat")
        text = self.out.read_text()
        self.assertNotRegex(text, r"(?m)^\.subckt bandgap_top")
        self.assertNotRegex(text, r"(?m)^\.ends")
        self.assertIn(" --flat ", text)
        self.run_main()  # unflattened run restores the wrapper
        self.assertRegex(self.out.read_text(), r"(?m)^\.subckt bandgap_top vdd vss vref$")

    def test_check_passes_on_identical_output(self):
        self.run_main()
        rc, out = self.run_main("--check")
        self.assertEqual(rc, 0)
        self.assertIn("ok:", out)

    def test_check_fails_on_drift(self):
        self.run_main()
        self.out.write_text(self.out.read_text() + "* hand edit\n")
        rc, out = self.run_main("--check")
        self.assertEqual(rc, 1)
        self.assertIn("stale", out)

    def test_check_fails_when_output_missing_and_does_not_write(self):
        rc, _ = self.run_main("--check")
        self.assertEqual(rc, 1)
        self.assertFalse(self.out.exists())

    def test_check_detects_changed_extract(self):
        import json
        self.run_main()
        ex = make_extract()
        device(ex, "$1")["params"]["w_um"] = 3.0
        self.extract.write_text(json.dumps(ex))
        rc, _ = self.run_main("--check")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
