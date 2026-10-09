#!/usr/bin/env python3
"""Unit checks for extract/build_record in the sim/device-* run scripts.

Covers run_pnp_vbe, run_mos_vth, run_pnp_mismatch, run_mos_mismatch (extract +
build_record) and run_resistor_tc (resistances + build_record), using tiny
hand-written synthetic ngspice logs. Every generated record is also pushed
through sim/harness/evidence_lint.py. No PDK, ngspice or fleet required:

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import importlib.util
import math
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from harness import corners as harness_corners  # noqa: E402
from harness import evidence_lint  # noqa: E402
from harness import report as harness_report  # noqa: E402
from harness.pdk import Pdk  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, SIM / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pnp_vbe = _load("run_pnp_vbe", "device-pnp-vbe/run_pnp_vbe.py")
mos_vth = _load("run_mos_vth", "device-mos-vth/run_mos_vth.py")
pnp_mm = _load("run_pnp_mismatch", "device-pnp-mismatch/run_pnp_mismatch.py")
mos_mm = _load("run_mos_mismatch", "device-mos-mismatch/run_mos_mismatch.py")
res_tc = _load("run_resistor_tc", "device-resistor-tc/run_resistor_tc.py")

RECORD = "20260101-000000-abcdef0"
STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)
PDK = Pdk(path=Path("/fake/gf180mcuD"), variant="gf180mcuD", source="test")
NGSPICE = "ngspice-test"


def lint(testcase, slug: str, text: str, corner_ids) -> None:
    """Write `text` as a record in a scratch tree and assert evidence_lint passes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = []
        for kind, name, body in (
            ("records", f"{RECORD}.md", text),
            ("netlist-snapshots", f"{RECORD}.spice", "* stub\n"),
            *(("corners", f"{RECORD}/{cid}.log", "stub\n") for cid in corner_ids),
        ):
            rel = f"sim/{slug}/{kind}/{name}"
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            paths.append(rel)
        experiments = evidence_lint.collect_experiments(paths)
        problems = [str(p) for p in evidence_lint.check_experiments(root, experiments)]
        testcase.assertEqual(problems, [])
    fields, dups = evidence_lint.parse_fields(text)
    testcase.assertEqual(dups, [])
    for name in evidence_lint.REQUIRED_FIELDS:
        testcase.assertTrue(fields[name].value, name)


# ---------------------------------------------------------------- DC tables


def dc_table(columns, rows) -> str:
    out = ["Circuit: stub", "", "Index   " + "   ".join(columns)]
    for i, row in enumerate(rows):
        out.append(f"{i}\t" + "\t".join(f"{v:.9e}" for v in row))
    return "\n".join(out) + "\n"


def pnp_log(temp_c: float) -> str:
    vt = pnp_vbe._thermal_voltage(temp_c)
    cols = ["v-sweep"]
    for _k, (_m, vcol, icol, _a) in pnp_vbe.DEVICES.items():
        cols += [vcol, icol]
    rows = []
    for i in range(91):
        x = round(-12.0 + 0.1 * i, 6)  # log10(I)
        row = [x]
        for key in pnp_vbe.DEVICES:
            area = {"5x5": 1.0, "10x10": 4.0}.get(key, 0.5)
            vbe = 0.7 - 0.002 * (temp_c - 27.0) - vt * math.log(area) + (
                vt * math.log(10.0) * (x + 6.0)
            )
            row += [vbe, 10.0**x / 2.7]  # beta = 1.7
        rows.append(row)
    return dc_table(cols, rows)


def mos_log(vt0: float = 0.6) -> str:
    cols = ["v-sweep", "v(gn1)", "v(gn4)", "v(gp1)", "v(gp4)"]
    rows = []
    for i in range(101):
        x = round(-8.0 + 0.05 * i, 6)
        vgs = vt0 + 0.05 * (x + 6.0)
        rows.append([x, vgs, vgs, -vgs, -vgs])
    return dc_table(cols, rows)


class PnpVbeExtract(unittest.TestCase):
    def test_happy_path(self):
        res = pnp_vbe.extract(pnp_log(27.0), 27.0)
        vt = pnp_vbe._thermal_voltage(27.0)
        self.assertAlmostEqual(res["vbe"]["5x5"][1e-6], 0.7, places=6)
        self.assertAlmostEqual(res["beta"]["5x5"][1e-6], 1.7, places=6)
        self.assertAlmostEqual(res["ideality"]["5x5"][1e-6], 1.0, places=6)
        self.assertAlmostEqual(
            res["dvbe"][10e-6], vt * math.log(4.0), places=6
        )
        self.assertAlmostEqual(res["area_ratio_eff"][10e-6], 4.0, places=4)
        lo, hi, at_floor, at_ceiling = res["window"]["5x5"]
        self.assertTrue(at_floor and at_ceiling)

    def test_no_header_raises(self):
        with self.assertRaises(ValueError):
            pnp_vbe.extract("Circuit: stub\nno table here\n", 27.0)

    def test_header_without_rows_raises(self):
        with self.assertRaises(ValueError):
            pnp_vbe.extract("Index   v-sweep   v(e5x5)\n", 27.0)

    def test_missing_column_raises(self):
        log = dc_table(["v-sweep", "v(e5x5)"], [[-12.0, 0.5], [-11.9, 0.51]])
        with self.assertRaises(ValueError):
            pnp_vbe.extract(log, 27.0)

    def test_truncated_row_is_skipped_not_fatal_to_header(self):
        lines = pnp_log(27.0).splitlines()
        lines[-1] = lines[-1].rsplit("\t", 3)[0]  # cut the final row short
        res = pnp_vbe.extract("\n".join(lines), 27.0)
        self.assertIn("vbe", res)

    def test_usable_window_none_when_ideality_high(self):
        self.assertEqual(
            [math.isnan(v) for v in pnp_vbe.usable_window([-6.0, -5.9], [2.0, 2.0])[:2]],
            [True, True],
        )


class PnpVbeRecord(unittest.TestCase):
    def test_record_passes_lint(self):
        results = {
            (s, t): pnp_vbe.extract(pnp_log(t), t)
            for s in pnp_vbe.SECTIONS
            for t in pnp_vbe.TEMPS
        }
        text = pnp_vbe.build_record(RECORD, STAMP, PDK, NGSPICE, results)
        self.assertIn(f"- **Record ID**: {RECORD}", text)
        ids = [
            harness_corners.device_corner_id(s, t)
            for s in pnp_vbe.SECTIONS
            for t in pnp_vbe.TEMPS
        ]
        lint(self, "device-pnp-vbe", text, ids)


class MosVth(unittest.TestCase):
    def test_extract_happy_path(self):
        res = mos_vth.extract(mos_log(0.6))
        # Icrit = 100 nA * W/L: 1 uA for 10/1, 250 nA for 10/4.
        self.assertAlmostEqual(res["icrit"]["nfet_03v3 10/1"], 1e-6)
        self.assertAlmostEqual(res["vth"]["nfet_03v3 10/1"], 0.6, places=6)
        want = 0.6 + 0.05 * (math.log10(250e-9) + 6.0)
        self.assertAlmostEqual(res["vth"]["nfet_03v3 10/4"], want, places=6)
        # PMOS sign flip: Vgs is reported positive.
        self.assertAlmostEqual(res["vth"]["pfet_03v3 10/1"], 0.6, places=6)
        self.assertAlmostEqual(res["vgs"]["pfet_03v3 10/1"][1e-6], 0.6, places=6)

    def test_malformed_logs_raise(self):
        with self.assertRaises(ValueError):
            mos_vth.extract("nothing useful\n")
        with self.assertRaises(ValueError):
            mos_vth.extract("Index  v-sweep  v(gn1)\n")
        with self.assertRaises(ValueError):  # columns missing for the other DUTs
            mos_vth.extract(dc_table(["v-sweep", "v(gn1)"], [[-8.0, 0.1], [-7.9, 0.2]]))

    def test_record_passes_lint(self):
        results = {
            (s, t): mos_vth.extract(mos_log(0.6 + 0.01 * i))
            for i, s in enumerate(mos_vth.SECTIONS)
            for t in mos_vth.TEMPS
        }
        text = mos_vth.build_record(RECORD, STAMP, PDK, NGSPICE, results)
        ids = [
            harness_corners.device_corner_id(s, t)
            for s in mos_vth.SECTIONS
            for t in mos_vth.TEMPS
        ]
        lint(self, "device-mos-vth", text, ids)


# ------------------------------------------------------------ Monte Carlo


def mc_log(keys, n, amp=1e-3, mean_shift=None, constant=False) -> str:
    """n blocks of `key = value` lines; zero-mean +/- pairs unless overridden."""
    mean_shift = mean_shift or {}
    blocks = []
    for i in range(n):
        sign = 1 if i % 2 == 0 else -1
        spread = 1.0 + 0.1 * ((i // 2) % 5)
        lines = []
        for k in keys:
            v = 0.0 if constant else sign * amp * spread
            v += mean_shift.get(k, 0.0)
            lines.append(f"{k} = {v:.9e}")
        blocks.append("\n".join(lines))
    return "Circuit: stub\n" + "\n".join(blocks) + "\n"


class MismatchExtractMixin:
    mod = None
    amp = 1e-3
    zero_mean_keys: tuple = ()

    def keys(self):
        return list(self.mod.PAIRS)

    def test_extract_happy_path(self):
        res = self.mod.extract(mc_log(self.keys(), self.mod.N_SAMPLES, self.amp))
        self.assertEqual(list(res), self.keys())
        for st in res.values():
            self.assertAlmostEqual(st["mean"], 0.0, places=12)
            self.assertGreater(st["sigma"], self.mod.SIGMA_FLOOR_V)
            self.assertAlmostEqual(st["max_abs"], self.amp * 1.4, places=9)

    def test_truncated_log_raises(self):
        for n in (0, self.mod.N_SAMPLES - 1):
            with self.subTest(n=n), self.assertRaises(RuntimeError):
                self.mod.extract(mc_log(self.keys(), n, self.amp))

    def test_truncated_final_block_raises_or_keyerror(self):
        log = mc_log(self.keys(), self.mod.N_SAMPLES, self.amp)
        cut = "\n".join(log.rstrip("\n").splitlines()[:-1]) + "\n"
        with self.assertRaises(KeyError):
            self.mod.extract(cut)

    def test_non_randomizing_draw_raises(self):
        with self.assertRaisesRegex(RuntimeError, "re-randomizing"):
            self.mod.extract(
                mc_log(self.keys(), self.mod.N_SAMPLES, self.amp, constant=True)
            )

    def test_offset_mean_raises_on_zero_mean_pairs(self):
        for key in self.zero_mean_keys:
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "mean"):
                self.mod.extract(
                    mc_log(
                        self.keys(),
                        self.mod.N_SAMPLES,
                        self.amp,
                        mean_shift={key: 10 * self.amp},
                    )
                )


class MosMismatchExtract(MismatchExtractMixin, unittest.TestCase):
    mod = mos_mm
    amp = 2e-3  # well above the 0.1 mV floor
    zero_mean_keys = tuple(mos_mm.PAIRS)


class PnpMismatchExtract(MismatchExtractMixin, unittest.TestCase):
    mod = pnp_mm
    amp = 1e-4
    zero_mean_keys = tuple(pnp_mm.ZERO_MEAN_PAIRS)

    def test_area_ratioed_pairs_may_carry_a_large_mean(self):
        shift = {"dr1": 0.033, "dr10": 0.033}
        res = pnp_mm.extract(
            mc_log(self.keys(), pnp_mm.N_SAMPLES, self.amp, mean_shift=shift)
        )
        self.assertAlmostEqual(res["dr1"]["mean"], 0.033, places=9)


class MismatchRecords(unittest.TestCase):
    def test_pnp_record_passes_lint(self):
        res = pnp_mm.extract(mc_log(list(pnp_mm.PAIRS), pnp_mm.N_SAMPLES, 1e-4))
        results = {t: res for t in pnp_mm.TEMPS}
        text = pnp_mm.build_record(RECORD, STAMP, PDK, NGSPICE, results)
        ids = [harness_corners.device_corner_id(pnp_mm.SECTION, t) for t in pnp_mm.TEMPS]
        lint(self, "device-pnp-mismatch", text, ids)

    def test_mos_record_passes_lint(self):
        res = mos_mm.extract(mc_log(list(mos_mm.PAIRS), mos_mm.N_SAMPLES, 2e-3))
        results = {t: res for t in mos_mm.TEMPS}
        text = mos_mm.build_record(RECORD, STAMP, PDK, NGSPICE, results)
        self.assertIn(f"**N = {mos_mm.N_SAMPLES}**", text)
        ids = [harness_corners.device_corner_id(mos_mm.SECTION, t) for t in mos_mm.TEMPS]
        lint(self, "device-mos-mismatch", text, ids)


# ------------------------------------------------------------ resistor TC


def res_log(scale: float = 1.0) -> str:
    """Op log: current = bias / R for each DUT, R = 1 kohm * scale."""
    lines = ["Circuit: stub"]
    for name, (_f, vec, _w, _l, bias) in res_tc.DUTS.items():
        lines.append(f"{vec} = {-bias / (1e3 * scale):.9e}")  # sign must be ignored
    for name, vec in res_tc.HV_DUTS.items():
        lines.append(f"{vec} = {res_tc.HV_BIAS_V / (1e3 * scale):.9e}")
    return "\n".join(lines) + "\n"


class ResistorTc(unittest.TestCase):
    def test_resistances_happy_path(self):
        r = res_tc.resistances(res_log())
        self.assertEqual(len(r), len(res_tc.DUTS) + len(res_tc.HV_DUTS))
        for name in res_tc.DUTS:
            self.assertAlmostEqual(r[name], 1e3, places=6)
        self.assertAlmostEqual(r["ppolyf_u_1k/W1/HV"], 1e3, places=6)

    def test_missing_vector_raises(self):
        log = "\n".join(
            line for line in res_log().splitlines() if "i(v_pu_w1)" not in line
        )
        with self.assertRaises(KeyError):
            res_tc.resistances(log)

    def test_empty_log_raises(self):
        with self.assertRaises(KeyError):
            res_tc.resistances("")

    def test_sheet_and_ppm(self):
        self.assertAlmostEqual(res_tc.sheet("ppolyf_u/W1", 3500.0), 350.0)
        self.assertAlmostEqual(res_tc.ppm_per_c(1.1, 0.9, 1.0, 100.0), 2000.0)

    def test_record_passes_lint(self):
        results = {}
        for si, s in enumerate(res_tc.SECTIONS):
            for ti, t in enumerate(res_tc.TEMPS):
                results[(s, t)] = res_tc.resistances(res_log(1.0 + 0.01 * si + 0.001 * ti))
        supply = {v: res_tc.resistances(res_log()) for v in (2.97, 3.63)}
        text = res_tc.build_record(RECORD, STAMP, PDK, NGSPICE, results, supply)
        ids = [
            harness_corners.device_corner_id(s, t)
            for s in res_tc.SECTIONS
            for t in res_tc.TEMPS
        ] + [
            harness_corners.device_corner_id(
                "res_typical", 27.0, f"nwell{v:.2f}v".replace(".", "p")
            )
            for v in (2.97, 3.63)
        ]
        lint(self, "device-resistor-tc", text, ids)


class RecordStamp(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(
            harness_report.record_stamp("20260101-123456-abcdef0"),
            datetime(2026, 1, 1, 12, 34, 56, tzinfo=timezone.utc),
        )
        self.assertEqual(
            harness_report.record_stamp(
                harness_report.format_record_id("abc1234", STAMP)
            ),
            STAMP,
        )

    def test_malformed_id_raises_clear_error(self):
        for bad in ("", "abc", "2026-01-01-abcdef0", "20261301-000000-abc"):
            with self.assertRaises(ValueError) as cm:
                harness_report.record_stamp(bad)
            self.assertIn("malformed record id", str(cm.exception))


class RunDeviceExperiment(unittest.TestCase):
    def _run(self, here, **kw):
        (here / "testbench").mkdir(parents=True, exist_ok=True)
        (here / "testbench" / "tb_fake.spice").write_text("* deck\n", encoding="utf-8")
        calls = []

        def run_corner(deck, pdk, section, temp):
            calls.append((deck.name, section, temp))
            return f"log {section} {temp}\n"

        def build_record(record, stamp, pdk, ngspice, results):
            return f"{record}|{stamp.isoformat()}|{sorted(results.items())}\n"

        rc = harness_report.run_device_experiment(
            here,
            "tb_fake.spice",
            [("s1", -40.0), ("s1", 27.0), ("s2", 27.0)],
            run_corner,
            kw.pop("extract", lambda log, section, temp: {"n": len(log)}),
            build_record,
            banner="record {record}: fake",
            pdk=PDK,
            ngspice=NGSPICE,
            git={"short": "abc1234", "branch": "t", "dirty": False},
            root=here,
            **kw,
        )
        return rc, calls

    def test_writes_expected_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            rc, calls = self._run(here)
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 3)
            (rec,) = (here / "records").glob("*.md")
            record = rec.stem
            self.assertTrue((here / "netlist-snapshots" / f"{record}.spice").exists())
            logs = sorted(p.name for p in (here / "corners" / record).iterdir())
            self.assertEqual(
                logs,
                sorted(
                    f"{harness_corners.device_corner_id(s, t)}.log"
                    for s, t in [("s1", -40.0), ("s1", 27.0), ("s2", 27.0)]
                ),
            )
            first = (here / "corners" / record / logs[0]).read_text()
            self.assertIn(record, first)
            self.assertIn("log s", first)
            text = rec.read_text()
            self.assertIn(harness_report.record_stamp(record).isoformat(), text)
            self.assertIn("('s1', -40.0)", text)

    def test_custom_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            self._run(here, key=lambda section, temp: temp)
            (rec,) = (here / "records").glob("*.md")
            self.assertIn("(27.0,", rec.read_text())

    def test_extract_failure_writes_no_record(self):
        def bad(log, section, temp):
            if section == "s2":
                raise ValueError("out of range")
            return {}

        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            rc, _ = self._run(here, extract=bad, tolerate_extract_errors=True)
            self.assertEqual(rc, 1)
            self.assertFalse((here / "records").exists())
            self.assertFalse((here / "netlist-snapshots").exists())

    def test_extract_failure_propagates_by_default(self):
        def bad(log, section, temp):
            raise ValueError("boom")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self._run(Path(tmp), extract=bad)


if __name__ == "__main__":
    unittest.main()
