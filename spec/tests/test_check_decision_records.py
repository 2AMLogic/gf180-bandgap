#!/usr/bin/env python3
"""Unit tests for spec/check_decision_records.py. No git, no network.

    python3 -m unittest discover -s spec/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC_DIR))

import check_decision_records as cd  # noqa: E402


def rec(status="ratified", date=True, decided=True, body="Body."):
    lines = ["# DR", "", f"- **Status**: {status}"]
    if date:
        lines.append("- **Date**: 2026-01-01")
    if decided:
        lines.append("- **Decided by**: someone")
    return "\n".join(lines) + "\n\n" + body + "\n"


A = "0001-a.md"
B = "0002-b.md"
C = "0003-c.md"


def good():
    return {A: rec(), B: rec(decided=False), C: rec("proposed")}


def index(*rows):
    head = "| Record | Title | Status |\n|---|---|---|\n"
    return head + "\n".join(
        f"| [{n}](decision-records/{n}-x.md) | T | {s} |" for n, s in rows
    )


class RecordChecks(unittest.TestCase):
    def test_good(self):
        self.assertEqual(cd.check_records(good()), [])

    def has(self, problems, text):
        self.assertTrue(any(text in p for p in problems), problems)

    def test_duplicate(self):
        r = good()
        r["0003-d.md"] = rec()
        self.has(cd.check_records(r), "duplicate record number 0003")

    def test_gap(self):
        r = good()
        del r[B]
        self.has(cd.check_records(r), "numbering gap: no record 0002")

    def test_bad_filename(self):
        r = good()
        r["4-x.md"] = rec()
        self.has(cd.check_records(r), "filename is not")

    def test_bad_keyword(self):
        r = good()
        r[C] = rec("draft")
        self.has(cd.check_records(r), "Status must begin with")

    def test_missing_status(self):
        r = good()
        r[C] = "# x\n- **Date**: d\n- **Decided by**: x\n"
        self.has(cd.check_records(r), "missing `- **Status**:`")

    def test_dangling_supersede(self):
        r = good()
        r[C] = rec("superseded by 0009")
        self.has(cd.check_records(r), "does not exist")

    def test_supersede_forms(self):
        for form in ("superseded by 0001", "Superseded by [0001](0001-a.md)"):
            r = good()
            r[C] = rec(form)
            self.assertEqual(cd.check_records(r), [], form)

    def test_missing_date(self):
        r = good()
        r[C] = rec(date=False)
        self.has(cd.check_records(r), "missing `- **Date**:`")

    def test_missing_decided_by_after_grandfathered(self):
        r = good()
        r[C] = rec(decided=False)
        self.has(cd.check_records(r), "missing `- **Decided by**:`")

    def test_case_suffix_and_continuation(self):
        r = good()
        r[A] = "# x\n\n- **Status**: Ratified (accepted\n  by survey)\n- **Date**: d\n"
        self.assertEqual(cd.check_records(r), [])
        r[A] = "# x\n\n- **Status**:\n  ratified\n- **Date**: d\n"
        self.assertEqual(cd.check_records(r), [])


class IndexChecks(unittest.TestCase):
    def has(self, problems, text):
        self.assertTrue(any(text in p for p in problems), problems)

    def test_good(self):
        idx = index(("0001", "Ratified (x)"), ("0002", "ratified"), ("0003", "Proposed"))
        self.assertEqual(cd.check_index(good(), idx), [])

    def test_missing_row(self):
        idx = index(("0001", "Ratified"), ("0002", "Ratified"))
        self.has(cd.check_index(good(), idx), "no row for 0003")

    def test_extra_row(self):
        idx = index(("0001", "Ratified"), ("0002", "Ratified"), ("0003", "Proposed"),
                    ("0004", "Proposed"))
        self.has(cd.check_index(good(), idx), "row 0004 has no record")

    def test_mismatch(self):
        idx = index(("0001", "Ratified"), ("0002", "Ratified"), ("0003", "Ratified"))
        self.has(cd.check_index(good(), idx), "index status for 0003")

    def test_supersede_target_mismatch(self):
        r = good()
        r[C] = rec("superseded by 0001")
        idx = index(("0001", "Ratified"), ("0002", "Ratified"),
                    ("0003", "Superseded by 0002"))
        self.has(cd.check_index(r, idx), "index status for 0003")
        idx = index(("0001", "Ratified"), ("0002", "Ratified"),
                    ("0003", "Superseded by [0001](x.md)"))
        self.assertEqual(cd.check_index(r, idx), [])


class Immutability(unittest.TestCase):
    def has(self, problems, text):
        self.assertTrue(any(text in p for p in problems), problems)

    def test_unchanged(self):
        self.assertEqual(cd.check_immutable(good(), good()), [])

    def test_body_edit(self):
        cur = good()
        cur[A] = rec(body="Relaxed.")
        self.has(cd.check_immutable(cur, good()), "ratified record modified")

    def test_delete(self):
        cur = good()
        del cur[A]
        self.has(cd.check_immutable(cur, good()), "deleted or renamed")

    def test_allowed_supersede(self):
        cur = good()
        cur[A] = rec("superseded by 0003")
        self.assertEqual(cd.check_immutable(cur, good()), [])

    def test_supersede_with_body_edit(self):
        cur = good()
        cur[A] = rec("superseded by 0003", body="Relaxed.")
        self.has(cd.check_immutable(cur, good()), "body modified")

    def test_supersede_dangling(self):
        cur = good()
        cur[A] = rec("superseded by 0009")
        self.has(cd.check_immutable(cur, good()), "does not exist")

    def test_ratified_to_proposed(self):
        cur = good()
        cur[A] = rec("proposed")
        self.has(cd.check_immutable(cur, good()), "ratified record modified")

    def test_proposed_may_change(self):
        cur = good()
        cur[C] = rec("ratified", body="Changed.")
        self.assertEqual(cd.check_immutable(cur, good()), [])


class RealTree(unittest.TestCase):
    def test_real_spec_passes(self):
        root = cd.REPO_ROOT
        records = cd.load_records(root / cd.RECORDS_REL)
        readme = (root / cd.README_REL).read_text(encoding="utf-8")
        self.assertEqual(cd.check_records(records) + cd.check_index(records, readme), [])


if __name__ == "__main__":
    unittest.main()
