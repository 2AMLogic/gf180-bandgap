#!/usr/bin/env python3
"""Unit tests for ``layout/erc/run_erc.py``'s verdict helpers (#192).

The helpers under test are the ones that turn a ``klt erc`` JSON report into
the T1 item-11 verdict -- which supplies were declared, which findings name
one of them, and whether the report's input hash pins the committed GDS.
They are pure functions over an already-parsed payload, so they are tested
against hand-built payloads here rather than by shelling out to ``klt``;
the end-to-end behaviour is covered by the committed reports under
``reports/bandgap_top/`` and the ``run_erc.py`` invocations that produced
them (``README.md``).

    python3 -m unittest layout.erc.test_run_erc -v
    # or, from this directory:
    python3 -m unittest test_run_erc -v
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_erc  # noqa: E402


def _finding(rule: str, net: str | None, other: str | None = None) -> dict:
    return {"rule": rule, "net": net, "other_net": other}


class DeclaredSuppliesTests(unittest.TestCase):
    def test_selects_only_kind_supply(self) -> None:
        spec = {
            "nets": [
                {"name": "vdd", "kind": "supply"},
                {"name": "vss", "kind": "supply"},
                {"name": "vref", "kind": "signal"},
            ]
        }
        self.assertEqual(run_erc.declared_supplies(spec), ["vdd", "vss"])

    def test_kind_defaults_to_signal(self) -> None:
        """An entry with no `kind` is a signal per klt erc's own default, so
        it must not be silently graded as a supply."""
        spec = {"nets": [{"name": "probe"}, {"name": "vdd", "kind": "supply"}]}
        self.assertEqual(run_erc.declared_supplies(spec), ["vdd"])

    def test_no_nets_section(self) -> None:
        self.assertEqual(run_erc.declared_supplies({"stackup": []}), [])


class SupplyFindingsTests(unittest.TestCase):
    def test_clean_report_yields_nothing(self) -> None:
        payload = {"erc_findings": []}
        self.assertEqual(run_erc.supply_findings(payload, ["vdd", "vss"]), [])

    def test_unconnected_net_on_a_declared_supply_is_a_hit(self) -> None:
        payload = {"erc_findings": [_finding("erc.unconnected_net", "vdd")]}
        self.assertEqual(len(run_erc.supply_findings(payload, ["vdd", "vss"])), 1)

    def test_supply_short_matches_on_either_net_field(self) -> None:
        """erc.supply_short populates both `net` and `other_net`; a supply
        named in either half must be caught."""
        payload = {"erc_findings": [_finding("erc.supply_short", "other", "vss")]}
        self.assertEqual(len(run_erc.supply_findings(payload, ["vdd", "vss"])), 1)

    def test_floating_gate_is_not_this_items_subject(self) -> None:
        """T1 item 11 grades erc.unconnected_net/erc.supply_short only -- a
        floating-gate or antenna finding is a real defect but does not block
        this item (klayout-tools#1994)."""
        payload = {
            "erc_findings": [
                {"rule": "erc.floating_gate", "net": "vdd", "other_net": None},
                {"rule": "erc.missing_tie", "net": "vss", "other_net": None},
            ]
        }
        self.assertEqual(run_erc.supply_findings(payload, ["vdd", "vss"]), [])

    def test_finding_naming_an_undeclared_net_is_not_a_supply_hit(self) -> None:
        payload = {"erc_findings": [_finding("erc.unconnected_net", "no_such_rail")]}
        self.assertEqual(run_erc.supply_findings(payload, ["vdd", "vss"]), [])


class Sha256Tests(unittest.TestCase):
    def test_matches_hashlib_and_carries_the_klt_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stream.gds"
            path.write_bytes(b"not really a gds")
            expected = hashlib.sha256(b"not really a gds").hexdigest()
            self.assertEqual(run_erc.sha256_of(path), f"sha256:{expected}")


class VerdictLinesTests(unittest.TestCase):
    GDS_HASH = "sha256:" + "ab" * 32

    def _payload(self, content_hash: str | None, findings: list[dict]) -> dict:
        provenance: dict = {"input": {"content_hash": content_hash}}
        if content_hash is None:
            provenance = {"input": None}
        return {"provenance": provenance, "erc_findings": findings}

    def test_matching_hash_and_clean_supplies_has_no_failures(self) -> None:
        payload = self._payload(self.GDS_HASH, [])
        lines, failures = run_erc.verdict_lines(payload, ["vdd", "vss"], self.GDS_HASH)
        self.assertEqual(failures, [])
        self.assertTrue(any("matches the GDS on disk" in line for line in lines))

    def test_mismatched_hash_is_a_failure(self) -> None:
        payload = self._payload("sha256:" + "cd" * 32, [])
        _, failures = run_erc.verdict_lines(payload, ["vdd"], self.GDS_HASH)
        self.assertEqual(len(failures), 1)
        self.assertIn("does not match the GDS on disk", failures[0])

    def test_absent_provenance_block_is_a_failure_not_a_pass(self) -> None:
        """A klt build too old to emit provenance must not read as 'matches'."""
        _, failures = run_erc.verdict_lines(
            {"erc_findings": []}, ["vdd"], self.GDS_HASH
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("<absent>", failures[0])

    def test_supply_findings_are_listed_but_are_not_themselves_failures(self) -> None:
        """verdict_lines() reports; the --expect gate in main() decides. The
        controls run with --expect findings, where a hit is the point."""
        payload = self._payload(self.GDS_HASH, [_finding("erc.supply_short", "vdd", "vss")])
        lines, failures = run_erc.verdict_lines(payload, ["vdd", "vss"], self.GDS_HASH)
        self.assertEqual(failures, [])
        self.assertTrue(any("supply finding: 1" in line for line in lines))


class ExitCodeContractTests(unittest.TestCase):
    def test_exit_four_is_accepted(self) -> None:
        """klt erc exits 4 (status 'not_checked') on every gf180mcu run,
        because --pdk ships a sky130 antenna table only. That is an antenna
        -coverage fact, not a power-delivery one, so it must not be treated
        as a failed run -- see run_erc.py's module docstring."""
        self.assertIn(4, run_erc.OK_EXIT_CODES)
        self.assertIn(0, run_erc.OK_EXIT_CODES)
        self.assertIn(3, run_erc.OK_EXIT_CODES)
        self.assertNotIn(1, run_erc.OK_EXIT_CODES)
        self.assertNotIn(2, run_erc.OK_EXIT_CODES)


if __name__ == "__main__":
    unittest.main()
