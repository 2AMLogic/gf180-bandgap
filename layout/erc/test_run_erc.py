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

import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Load-bearing: sys.path[0] is this file's dir only under `python3 file.py`.
# Under the documented `python3 -m <dotted.module>` form it is the CWD. #479
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_erc  # noqa: E402

HERE = Path(__file__).resolve().parent
#: The committed signoff report and spec -- the passing control every #537
#: fixture starts from, so the tests exercise native report shapes rather
#: than hand-built lookalikes.
COMMITTED_REPORT = HERE / "reports/bandgap_top/20261120-210525-e0893ec.erc.json"
COMMITTED_SPEC = HERE / "erc-supply-spec.json"
COMMITTED_GDS = HERE.parent / "bandgap_top/bandgap_top.gds"
#: Hand-written (not implementation-derived) IDs, matching what `klt erc`
#: emits -- see the committed report's own erc_coverage.checked.
PSUB_TAP_ID = 'erc.missing_tie:["psub_tap"]'


def _committed_payload() -> dict:
    return json.loads(COMMITTED_REPORT.read_text())


def _committed_spec() -> dict:
    return json.loads(COMMITTED_SPEC.read_text())


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


class DeclaredTiesTests(unittest.TestCase):
    def test_committed_spec_declares_three_ties_in_order(self) -> None:
        self.assertEqual(
            run_erc.declared_ties(_committed_spec()),
            ["nwell_tap_pmos", "nwell_base_pnp", "psub_tap"],
        )

    def test_no_ties_section(self) -> None:
        self.assertEqual(run_erc.declared_ties({"nets": []}), [])


class TieCheckIdTests(unittest.TestCase):
    def test_matches_the_committed_report_ids(self) -> None:
        """The expected IDs must be byte-identical to what klt actually
        emitted into the committed report's erc_coverage.checked."""
        checked = _committed_payload()["erc_coverage"]["checked"]
        for name in ("nwell_tap_pmos", "nwell_base_pnp", "psub_tap"):
            self.assertIn(run_erc.tie_check_id(name), checked)

    def test_json_encodes_the_name_array(self) -> None:
        """klt JSON-encodes the one-element name array inside the ID, so a
        name needing escaping must be escaped -- an f-string splice would
        look for an ID the tool never emits."""
        self.assertEqual(
            run_erc.tie_check_id('tie"name'), 'erc.missing_tie:["tie\\"name"]'
        )


class TieCoverageFailuresTests(unittest.TestCase):
    """The #537 gate helper: every declared tie must be evidenced as a
    computed check before a zero-findings report can read as a verdict."""

    TIES = ["nwell_tap_pmos", "nwell_base_pnp", "psub_tap"]

    def setUp(self) -> None:
        self.payload = copy.deepcopy(_committed_payload())

    def test_committed_report_has_no_failures(self) -> None:
        self.assertEqual(run_erc.tie_coverage_failures(self.payload, self.TIES), [])

    def test_omitted_tie_fails_and_names_it(self) -> None:
        """The #537 reproduction: only psub_tap's ID leaves checked. It
        stays in checked_by_well_assertion in the committed report, so a
        helper that reads a well assertion as evidence the check ran
        passes this fixture -- and must not."""
        self.payload["erc_coverage"]["checked"].remove(PSUB_TAP_ID)
        self.assertIn(
            PSUB_TAP_ID, self.payload["erc_coverage"]["checked_by_well_assertion"]
        )
        failures = run_erc.tie_coverage_failures(self.payload, self.TIES)
        self.assertEqual(len(failures), 1)
        self.assertIn("psub_tap", failures[0])

    def test_skipped_tie_fails_even_when_also_checked(self) -> None:
        """The second independent fixture: every ID stays in checked and a
        native skip record appears for psub_tap. Membership in both
        collections must still fail -- a skip is not a verdict."""
        self.payload["erc_coverage"]["skipped"].append(
            {"id": PSUB_TAP_ID, "reason": "degenerate_tap_declaration"}
        )
        self.assertIn(PSUB_TAP_ID, self.payload["erc_coverage"]["checked"])
        failures = run_erc.tie_coverage_failures(self.payload, self.TIES)
        self.assertEqual(len(failures), 1)
        self.assertIn("psub_tap", failures[0])
        self.assertIn("degenerate_tap_declaration", failures[0])

    def test_missing_coverage_block_fails_every_declared_tie(self) -> None:
        del self.payload["erc_coverage"]
        failures = run_erc.tie_coverage_failures(self.payload, self.TIES)
        self.assertEqual(len(failures), len(self.TIES))
        for name in self.TIES:
            self.assertTrue(any(name in failure for failure in failures), name)

    def test_no_declared_ties_is_never_a_coverage_failure(self) -> None:
        """A spec without ties[] keeps its existing supply checks and gains
        no tie gate -- so a payload without any coverage block at all must
        not fail it."""
        del self.payload["erc_coverage"]
        self.assertEqual(run_erc.tie_coverage_failures(self.payload, []), [])

    def test_escaped_name_passes_when_properly_encoded(self) -> None:
        payload = {"erc_coverage": {"checked": ['erc.missing_tie:["tie\\"name"]'], "skipped": []}}
        self.assertEqual(run_erc.tie_coverage_failures(payload, ['tie"name']), [])

    def test_escaped_name_fails_when_only_naively_spliced(self) -> None:
        """An ID built by f-string splicing (no backslash escape) is not
        what klt emits, so matching it must not satisfy the gate."""
        payload = {"erc_coverage": {"checked": ['erc.missing_tie:["tie"name"]'], "skipped": []}}
        failures = run_erc.tie_coverage_failures(payload, ['tie"name'])
        self.assertEqual(len(failures), 1)


class SupplyCleanCommandGateTests(unittest.TestCase):
    """The same gate, exercised through ``main()`` itself (#537).

    A helper that is correct but never called by the command is exactly
    the failure these tests exist to catch, so every case here drives
    ``run_erc.main()`` end to end: the spec and a copy of the committed
    GDS are staged in a scratch repo root, a stub ``klt`` on ``PATH``
    replays a canned report (the committed signoff report with exactly one
    coverage entry changed, zero findings throughout), and the exit code
    and stderr are asserted.
    """

    def _replay(self, payload: dict, spec: dict, *extra: str) -> tuple[int, str, str]:
        tmp = Path(tempfile.mkdtemp(prefix="erc-gate-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = tmp / "repo"
        (root / "layout/bandgap_top").mkdir(parents=True)
        (root / "layout/erc/reports").mkdir(parents=True)
        (root / "bin").mkdir()
        shutil.copyfile(COMMITTED_GDS, root / "layout/bandgap_top/bandgap_top.gds")
        (root / "layout/erc/erc-supply-spec.json").write_text(json.dumps(spec))
        replay = root / "replay.json"
        replay.write_text(json.dumps(payload))
        klt = root / "bin" / "klt"
        klt.write_text(
            "#!/bin/sh\n"
            "# test stub: replay a canned klt erc report and exit 0\n"
            'cat "$ERC_REPLAY_JSON"\n'
            "exit 0\n"
        )
        klt.chmod(0o755)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with mock.patch.dict(
            os.environ,
            {
                "PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
                "ERC_REPLAY_JSON": str(replay),
            },
        ), mock.patch.object(run_erc, "REPO_ROOT", root), mock.patch.object(
            run_erc, "REPORTS_ROOT", root / "layout/erc/reports"
        ), contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            code = run_erc.main(
                [
                    str(root / "layout/bandgap_top/bandgap_top.gds"),
                    "--spec", str(root / "layout/erc/erc-supply-spec.json"),
                    *extra,
                ]
            )
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_committed_report_passes_the_supply_clean_gate(self) -> None:
        code, _, _ = self._replay(_committed_payload(), _committed_spec())
        self.assertEqual(code, 0)

    def test_omitted_tie_fails_the_command_and_names_it(self) -> None:
        payload = copy.deepcopy(_committed_payload())
        payload["erc_coverage"]["checked"].remove(PSUB_TAP_ID)
        code, _, err = self._replay(payload, _committed_spec())
        self.assertEqual(code, 1)
        self.assertIn("psub_tap", err)
        self.assertNotIn("nwell_tap_pmos", err)

    def test_skipped_tie_fails_the_command_and_names_it(self) -> None:
        payload = copy.deepcopy(_committed_payload())
        payload["erc_coverage"]["skipped"].append(
            {"id": PSUB_TAP_ID, "reason": "degenerate_tap_declaration"}
        )
        code, _, err = self._replay(payload, _committed_spec())
        self.assertEqual(code, 1)
        self.assertIn("psub_tap", err)
        self.assertNotIn("nwell_tap_pmos", err)

    def test_missing_coverage_block_fails_the_command_for_every_tie(self) -> None:
        payload = copy.deepcopy(_committed_payload())
        del payload["erc_coverage"]
        code, _, err = self._replay(payload, _committed_spec())
        self.assertEqual(code, 1)
        for name in ("nwell_tap_pmos", "nwell_base_pnp", "psub_tap"):
            self.assertIn(name, err)

    def test_spec_without_ties_keeps_its_supply_checks(self) -> None:
        spec = _committed_spec()
        del spec["ties"]
        code, _, _ = self._replay(_committed_payload(), spec)
        self.assertEqual(code, 0)

    def test_findings_mode_keeps_its_own_gate(self) -> None:
        """--expect findings must keep failing the clean report for its own
        reason (zero findings), not for tie coverage."""
        code, _, err = self._replay(
            _committed_payload(), _committed_spec(), "--expect", "findings"
        )
        self.assertEqual(code, 1)
        self.assertIn("ZERO findings", err)
        self.assertNotIn("psub_tap", err)

    def test_any_mode_still_gates_on_nothing(self) -> None:
        payload = copy.deepcopy(_committed_payload())
        payload["erc_coverage"]["checked"].remove(PSUB_TAP_ID)
        code, _, _ = self._replay(payload, _committed_spec(), "--expect", "any")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
