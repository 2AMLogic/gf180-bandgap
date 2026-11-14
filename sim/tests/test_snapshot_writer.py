#!/usr/bin/env python3
"""The netlist snapshot has exactly one writer (issue #480).

``netlist-snapshots/<record-id>.spice`` is append-only evidence
(``sim/README.md``, CLAUDE.md). That invariant used to be hand-rolled at six
call sites in four mutually inconsistent ways -- no guard at all, an
``exists()``-then-write race, a bare ``FileExistsError``, a silent
``copyfile``. It now lives in one place:
:func:`harness.report.write_snapshot_text`, with
:func:`harness.report.write_device_netlist_snapshot` delegating to it.

Two things are checked here:

* **Structurally** -- no production module builds a ``netlist-snapshots`` path
  except as an argument to one of those two helpers. This is the only
  coverage reaching ``tc_ingest``, ``run_pnp_array`` and ``run_mc_untrimmed``,
  whose snapshot write sits inline in ``main()`` against hard-coded in-repo
  paths: driving those would write into the real append-only evidence
  directories, which no test may do. The per-ingestor ``RecordExists``
  behaviour tests live beside each ingestor's own fixtures
  (``test_fleet_ingest``, ``test_load_ingest``, ``test_mc_fleet``,
  ``test_device_benches``).
* **Behaviourally** -- the one writer still produces the exact bytes each
  retired idiom did, so no existing record's frozen deck changes meaning.

No PDK, ngspice or fleet required:

    python3 -m unittest discover -s sim/tests -t sim/tests -v
"""

from __future__ import annotations

import ast
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from harness import report as hreport  # noqa: E402

SNAPSHOT_DIR = "netlist-snapshots"
WRITERS = frozenset({"write_snapshot_text", "write_device_netlist_snapshot"})
RECORD = "20260801-120000-abc1234"


def production_sources() -> list[Path]:
    """Every ``sim/`` module that ships, i.e. everything but this test suite."""
    return sorted(p for p in SIM.rglob("*.py") if p.parent != Path(__file__).parent)


def snapshot_path_sites(tree: ast.AST) -> list[tuple[ast.stmt, int]]:
    """Statements that build a ``<something> / "netlist-snapshots"`` path.

    Returns ``(enclosing statement, line)`` pairs. Keyed on the division
    operator so a mention of the directory in prose -- a record's markdown
    body, a docstring -- is not mistaken for a path construction.
    """
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    sites = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Constant)
            and node.right.value == SNAPSHOT_DIR
        ):
            continue
        stmt = node
        while stmt is not None and not isinstance(stmt, ast.stmt):
            stmt = parents.get(stmt)
        if stmt is not None:
            sites.append((stmt, node.lineno))
    return sites


def calls_a_writer(stmt: ast.stmt) -> bool:
    for node in ast.walk(stmt):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in WRITERS:
            return True
    return False


class OneWriter(unittest.TestCase):
    def test_every_snapshot_path_is_an_argument_to_the_shared_writer(self):
        offenders = []
        for src in production_sources():
            tree = ast.parse(src.read_text(), filename=str(src))
            for stmt, line in snapshot_path_sites(tree):
                if not calls_a_writer(stmt):
                    offenders.append(f"{src.relative_to(SIM.parent)}:{line}")
        self.assertEqual(
            offenders, [],
            "these build a netlist-snapshots path without going through "
            f"{sorted(WRITERS)}; the append-only refusal must not be re-implemented: "
            + ", ".join(offenders))

    def test_the_known_call_sites_are_all_still_covered(self):
        """Guards the scan above against silently matching nothing."""
        found = {}
        for src in production_sources():
            tree = ast.parse(src.read_text(), filename=str(src))
            if snapshot_path_sites(tree):
                found[str(src.relative_to(SIM.parent))] = len(snapshot_path_sites(tree))
        self.assertEqual(sorted(found), [
            "sim/device-pnp-array/run_pnp_array.py",
            "sim/device-resistor-tc/run_resistor_tc.py",
            "sim/harness/report.py",
            "sim/mc-untrimmed/run_mc_untrimmed.py",
            "sim/tools/fleet_ingest.py",
            "sim/tools/load_ingest.py",
            "sim/tools/mc_fleet_ingest.py",
            "sim/tools/tc_ingest.py",
        ])
        self.assertEqual(sum(found.values()), 8)


class ByteCompatibility(unittest.TestCase):
    """The one writer emits what each retired hand-rolled idiom emitted."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_text_matches_the_retired_write_text(self):
        text = "* frozen deck\n.include \"x.spice\"\nv1 a 0 3.3\n.end\n"
        expected = self.tmp / "expected.spice"
        expected.write_text(text)
        got = hreport.write_snapshot_text(self.tmp / "snap", RECORD, text)
        self.assertEqual(got.read_bytes(), expected.read_bytes())
        self.assertEqual(got.name, f"{RECORD}.spice")

    def test_text_matches_the_retired_utf8_write_text(self):
        text = "* frozen deck -- 1.2 V, 27 C\n.end\n"
        expected = self.tmp / "expected.spice"
        expected.write_text(text, encoding="utf-8")
        got = hreport.write_snapshot_text(self.tmp / "snap", RECORD, text)
        self.assertEqual(got.read_bytes(), expected.read_bytes())

    def test_deck_copy_matches_the_retired_copyfile(self):
        deck = self.tmp / "body.spice"
        deck.write_bytes(b"* frozen fleet deck\r\nv1 a 0 3.3\n.end\n")  # mixed EOLs stay verbatim
        expected = self.tmp / "expected.spice"
        shutil.copyfile(deck, expected)
        got = hreport.write_device_netlist_snapshot(self.tmp / "snap", RECORD, deck)
        self.assertEqual(got.read_bytes(), expected.read_bytes())
        self.assertEqual(got.read_bytes(), deck.read_bytes())

    def test_parent_directory_is_created(self):
        nested = self.tmp / "exp" / SNAPSHOT_DIR
        self.assertFalse(nested.exists())
        hreport.write_snapshot_text(nested, RECORD, "* deck\n")
        self.assertTrue((nested / f"{RECORD}.spice").is_file())

    def test_device_snapshot_delegates_to_the_text_writer(self):
        deck = self.tmp / "body.spice"
        deck.write_text("* deck\n")
        seen = []
        real = hreport.write_snapshot_text
        try:
            def spy(snapshot_dir, record, text):
                seen.append((snapshot_dir, record, text))
                return real(snapshot_dir, record, text)

            hreport.write_snapshot_text = spy
            hreport.write_device_netlist_snapshot(self.tmp / "snap", RECORD, deck)
        finally:
            hreport.write_snapshot_text = real
        self.assertEqual(seen, [(self.tmp / "snap", RECORD, b"* deck\n")])


class AppendOnly(unittest.TestCase):
    """One refusal, one message, for text and deck callers alike."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.snap = Path(self._td.name) / SNAPSHOT_DIR

    def test_text_writer_refuses_and_preserves_the_existing_bytes(self):
        first = hreport.write_snapshot_text(self.snap, RECORD, "* original\n")
        with self.assertRaises(hreport.RecordExists) as cm:
            hreport.write_snapshot_text(self.snap, RECORD, "* replacement\n")
        self.assertIn("sim/ is append-only", str(cm.exception))
        self.assertIn("a re-run must mint a new record ID", str(cm.exception))
        self.assertEqual(first.read_bytes(), b"* original\n")

    def test_deck_writer_refuses_with_the_same_typed_error(self):
        deck = self.snap.parent / "body.spice"
        deck.write_text("* original\n")
        hreport.write_device_netlist_snapshot(self.snap, RECORD, deck)
        deck.write_text("* replacement\n")
        with self.assertRaises(hreport.RecordExists):
            hreport.write_device_netlist_snapshot(self.snap, RECORD, deck)
        self.assertEqual((self.snap / f"{RECORD}.spice").read_text(), "* original\n")

    def test_record_exists_is_still_a_runtime_error(self):
        """Callers that caught the retired ad-hoc ``RuntimeError`` still catch this."""
        self.assertTrue(issubclass(hreport.RecordExists, RuntimeError))


if __name__ == "__main__":
    unittest.main()
