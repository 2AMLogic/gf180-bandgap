#!/usr/bin/env python3
"""Unit tests for ``run_lvs.py``'s engine selection (gf180-bandgap#109).

No PDK, no ``klt``, and no ``netgen`` binary required: every subprocess
``run_lvs.main()`` shells out to (``git rev-parse``, ``make_reference.py``,
``klt extract``, ``klt lvs``) is replaced by :class:`FakeKlt`, which parses
the request document `run_lvs` wrote and answers as `klt lvs` would. That is
deliberate — CI installs neither `klt` nor `netgen` (upstream's own CI skips
its real-binary netgen tests for the same reason), so the *contract* under
test here is the request document and report-file layout `run_lvs` produces,
not netgen's verdict.

    python3 -m unittest layout.lvs.test_run_lvs -v
    # or, from this directory:
    python3 -m unittest test_run_lvs -v
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_lvs  # noqa: E402

EXTRACT_PAYLOAD = {
    "device_count": 3,
    "device_counts": {"nfet": 2, "pfet": 1},
}


def _lvs_payload(engine: str, status: str = "match") -> dict:
    """The subset of `klt lvs`'s JSON response `run_lvs` actually reads."""
    matched = 3 if status == "match" else 0
    return {
        "schema_version": 1,
        "engine": engine,
        "status": status,
        "mismatch_count": 0 if status == "match" else 1,
        "counts": {
            "devices": {"layout": 3, "reference": 3, "matched": matched},
            "nets": {"layout": 4, "reference": 4, "matched": matched if status == "match" else 0},
            "pins": {"layout": 2, "reference": 2, "matched": matched},
        },
    }


class FakeKlt:
    """A ``subprocess.run`` stand-in that answers as the real tools would."""

    #: `klt lvs`'s own actionable error when the netgen binary is absent.
    #: Copied verbatim from `klayout_tools.lvs._run_netgen_lvs`'s
    #: `FileNotFoundError` handler, wrapped in the JSON error envelope
    #: `klayout_tools.cli.output.emit_error` writes to **stderr** under
    #: `--format json` (exit 1) — so the test asserts on the text a real
    #: missing binary would surface, not on one this test invented.
    NETGEN_MISSING_MESSAGE = (
        "could not launch netgen: binary not found on PATH. Install netgen "
        "(https://github.com/RTimothyEdwards/netgen) or use engine 'klayout' "
        "instead. ([Errno 2] No such file or directory: 'netgen')"
    )
    NETGEN_MISSING = json.dumps(
        {
            "schema_version": 1,
            "error": {"command": "lvs", "message": NETGEN_MISSING_MESSAGE},
        },
        indent=2,
    ) + "\n"

    def __init__(self, repo_root: Path, *, netgen_missing: bool = False,
                 netgen_status: str = "match") -> None:
        self.repo_root = repo_root
        self.netgen_missing = netgen_missing
        self.netgen_status = netgen_status
        self.calls: list[list[str]] = []
        self.requests: list[dict] = []

    def __call__(self, argv, **kwargs):  # noqa: ANN001 - subprocess.run signature
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        name = Path(argv[0]).name
        if name == "git":
            return subprocess.CompletedProcess(argv, 0, "0123456789abcdef\n", "")
        if argv[0] == sys.executable:  # make_reference.py regeneration
            return subprocess.CompletedProcess(argv, 0, "", "")
        if name != "klt":
            raise AssertionError(f"unexpected subprocess: {argv}")
        if argv[1] == "extract":
            return subprocess.CompletedProcess(argv, 0, json.dumps(EXTRACT_PAYLOAD), "")
        if argv[1] == "lvs":
            return self._lvs(argv)
        raise AssertionError(f"unexpected klt subcommand: {argv}")

    def _lvs(self, argv: list[str]) -> subprocess.CompletedProcess:
        request = json.loads((self.repo_root / argv[2]).read_text())
        engine = request.get("engine", "klayout")
        # `run_lvs` invokes each engine twice (`--format json`, then `--format
        # text`); record the json pass only, so `requests` reads as one entry
        # per engine actually compared.
        if "json" in argv:
            self.requests.append(request)
        if engine == "netgen" and self.netgen_missing:
            return subprocess.CompletedProcess(argv, 1, "", self.NETGEN_MISSING)
        status = self.netgen_status if engine == "netgen" else "match"
        if "json" in argv:
            return subprocess.CompletedProcess(
                argv, 0 if status == "match" else 3,
                json.dumps(_lvs_payload(engine, status)), "",
            )
        return subprocess.CompletedProcess(
            argv, 0 if status == "match" else 3, f"lvs {engine}: {status}\n", "",
        )


class ArgumentParsingTests(unittest.TestCase):
    """The flag is opt-in: absent ``--engine``, nothing about the run changes."""

    def test_default_engine_is_klayout(self) -> None:
        args = run_lvs.build_parser().parse_args(["a.gds"])
        self.assertEqual(args.engine, "klayout")
        self.assertEqual(run_lvs.DEFAULT_ENGINE, "klayout")

    def test_accepts_each_supported_engine(self) -> None:
        for value in ("klayout", "netgen", "both"):
            with self.subTest(engine=value):
                args = run_lvs.build_parser().parse_args(["a.gds", "--engine", value])
                self.assertEqual(args.engine, value)

    def test_rejects_unknown_engine(self) -> None:
        # `magic` is netgen's usual upstream extraction partner, and exactly the
        # engine klayout-tools deliberately did *not* wire up — so it is the
        # most plausible wrong value a user would try.
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stderr(io.StringIO()):
                run_lvs.build_parser().parse_args(["a.gds", "--engine", "magic"])
        self.assertEqual(raised.exception.code, 2)

    def test_help_documents_the_flag(self) -> None:
        help_text = run_lvs.build_parser().format_help()
        self.assertIn("--engine {klayout,netgen,both}", help_text)
        self.assertIn("netgen", help_text)


class RequestDocumentTests(unittest.TestCase):
    """The request document is committed evidence, so its shape is pinned."""

    def _request(self, engine: str) -> dict:
        return run_lvs._build_request(
            gds_path=Path("/repo/layout/bandgap_top/bandgap_top.gds"),
            reports_dir=Path("/repo/layout/lvs/reports/bandgap_top"),
            reference=Path("/repo/layout/lvs/bandgap_top.ref.spice"),
            deck="gf180mcu",
            top="bandgap_top",
            engine=engine,
        )

    def test_klayout_request_omits_the_engine_key(self) -> None:
        """`klt lvs` already defaults to `klayout`; omitting the key keeps every
        request document byte-identical to the ones committed before #109."""
        self.assertNotIn("engine", self._request("klayout"))

    def test_netgen_request_sets_the_engine_key(self) -> None:
        self.assertEqual(self._request("netgen")["engine"], "netgen")

    def test_paths_are_relative_to_the_request_directory(self) -> None:
        """`klt lvs` resolves relative paths against the request file's own
        directory, not the process cwd — a regression here would make the
        request point at nonexistent files."""
        request = self._request("netgen")
        self.assertEqual(
            request["layout"]["file"], "../../../bandgap_top/bandgap_top.gds"
        )
        self.assertEqual(request["reference"]["netlist"], "../../bandgap_top.ref.spice")
        self.assertEqual(request["layout"]["deck"], "gf180mcu")
        self.assertEqual(request["layout"]["top"], "bandgap_top")
        self.assertEqual(request["reference"]["top"], "bandgap_top")

    def test_report_stems_never_collide(self) -> None:
        stems = {engine: run_lvs._engine_stem(engine) for engine in run_lvs.ENGINES}
        self.assertEqual(stems["klayout"], "lvs")  # unsuffixed, pre-#109 series
        self.assertEqual(stems["netgen"], "lvs-netgen")
        self.assertEqual(len(set(stems.values())), len(run_lvs.ENGINES))


class MainFlowTests(unittest.TestCase):
    """End-to-end over stubbed subprocesses: which reports land on disk."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        gds_dir = self.repo_root / "layout" / "bandgap_top"
        gds_dir.mkdir(parents=True)
        self.gds = gds_dir / "bandgap_top.gds"
        self.gds.write_bytes(b"")
        self.reports_root = self.repo_root / "layout" / "lvs" / "reports"
        self.reports_dir = self.reports_root / "bandgap_top"

    def _run(self, extra_argv: list[str], fake: FakeKlt) -> tuple[int, str, str]:
        argv = ["run_lvs.py", str(self.gds), *extra_argv]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(run_lvs, "REPO_ROOT", self.repo_root), \
                mock.patch.object(run_lvs, "REPORTS_ROOT", self.reports_root), \
                mock.patch.object(run_lvs, "REFERENCE",
                                  self.repo_root / "layout/lvs/bandgap_top.ref.spice"), \
                mock.patch.object(run_lvs.subprocess, "run", fake), \
                mock.patch.object(run_lvs.shutil, "which", return_value="/usr/bin/klt"), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_lvs.main()
        return code, out.getvalue(), err.getvalue()

    def _report_names(self) -> set[str]:
        return {p.name for p in self.reports_dir.iterdir()}

    def test_default_run_touches_only_the_klayout_engine(self) -> None:
        fake = FakeKlt(self.repo_root)
        code, out, _ = self._run([], fake)
        self.assertEqual(code, 0)
        self.assertEqual([r.get("engine") for r in fake.requests], [None])
        suffixes = {n.split(".", 1)[1] for n in self._report_names()}
        self.assertEqual(
            suffixes,
            {"extract.json", "lvs-request.json", "lvs.json", "lvs.txt"},
        )
        self.assertIn("engine           : klayout", out)
        self.assertNotIn("cross-check", out)

    def test_netgen_only_run_writes_the_suffixed_series(self) -> None:
        fake = FakeKlt(self.repo_root)
        code, out, _ = self._run(["--engine", "netgen"], fake)
        self.assertEqual(code, 0)
        self.assertEqual([r.get("engine") for r in fake.requests], ["netgen"])
        suffixes = {n.split(".", 1)[1] for n in self._report_names()}
        self.assertEqual(
            suffixes,
            {"extract.json", "lvs-netgen-request.json", "lvs-netgen.json",
             "lvs-netgen.txt"},
        )
        self.assertIn("engine           : netgen", out)

    def test_both_engines_write_distinct_non_overwritten_reports(self) -> None:
        fake = FakeKlt(self.repo_root)
        code, out, _ = self._run(["--engine", "both"], fake)
        self.assertEqual(code, 0)
        self.assertEqual([r.get("engine") for r in fake.requests], [None, "netgen"])
        names = self._report_names()
        # One record id, two complete and distinct report series under it.
        record_ids = {n.split(".", 1)[0] for n in names}
        self.assertEqual(len(record_ids), 1)
        suffixes = {n.split(".", 1)[1] for n in names}
        self.assertEqual(
            suffixes,
            {"extract.json",
             "lvs-request.json", "lvs.json", "lvs.txt",
             "lvs-netgen-request.json", "lvs-netgen.json", "lvs-netgen.txt"},
        )
        self.assertIn("cross-check      : agree (klayout=match netgen=match)", out)

    def test_both_engines_report_a_disagreement_loudly(self) -> None:
        fake = FakeKlt(self.repo_root, netgen_status="mismatch")
        code, out, _ = self._run(["--engine", "both"], fake)
        # A tool-level disagreement is evidence to read, not a gate: `mismatch`
        # already exits 0 here, so a disagreement does too — but it must be
        # visible in the run's own output, not only in the JSON.
        self.assertEqual(code, 0)
        self.assertIn("cross-check      : DISAGREE (klayout=match netgen=mismatch)", out)

    def test_a_second_run_never_reuses_a_record_id(self) -> None:
        """Append-only: `_record_id` probes `<id>.*`, so a netgen-only run
        cannot hand its id back to a later klayout run (which would clobber
        the extraction artefacts already filed under it)."""
        fixed = run_lvs._dt.datetime(2026, 8, 4, 12, 0, 0, tzinfo=run_lvs._dt.timezone.utc)
        with mock.patch.object(run_lvs._dt, "datetime") as clock:
            clock.now.return_value = fixed
            self._run(["--engine", "netgen"], FakeKlt(self.repo_root))
            self._run([], FakeKlt(self.repo_root))
        record_ids = {p.name.split(".", 1)[0] for p in self.reports_dir.iterdir()}
        self.assertEqual(len(record_ids), 2)

    def test_missing_netgen_binary_surfaces_the_klt_error(self) -> None:
        fake = FakeKlt(self.repo_root, netgen_missing=True)
        code, out, err = self._run(["--engine", "netgen"], fake)
        self.assertEqual(code, 1)
        self.assertIn("could not launch netgen: binary not found on PATH", err)
        self.assertIn("klt lvs --engine netgen failed (exit 1)", err)
        # No silent fallback to the klayout engine, and no half-written verdict.
        self.assertEqual([r.get("engine") for r in fake.requests], ["netgen"])
        self.assertNotIn("lvs status", out)
        self.assertEqual(
            {n.split(".", 1)[1] for n in self._report_names()},
            {"extract.json", "lvs-netgen-request.json"},
        )

    def test_missing_netgen_binary_aborts_a_both_run_after_klayout(self) -> None:
        fake = FakeKlt(self.repo_root, netgen_missing=True)
        code, out, err = self._run(["--engine", "both"], fake)
        self.assertEqual(code, 1)
        self.assertIn("could not launch netgen: binary not found on PATH", err)
        # The klayout verdict it *did* reach stays on disk as evidence, but the
        # run must not claim a cross-checked verdict it never obtained.
        self.assertIn("lvs.json", self._report_names_suffixes())
        self.assertNotIn("cross-check", out)

    def _report_names_suffixes(self) -> set[str]:
        return {n.split(".", 1)[1] for n in self._report_names()}


if __name__ == "__main__":
    unittest.main()
