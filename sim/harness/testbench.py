"""Testbench manifests.

Testbenches follow the directory convention ratified in ``sim/README.md``:
each experiment gets ``sim/<experiment-slug>/`` and its testbench lives in
that experiment's ``testbench/`` subdirectory:

    sim/<experiment-slug>/testbench/tb.json            the manifest (this module)
    sim/<experiment-slug>/testbench/<something>.spice  a *netlist fragment*

The fragment must NOT contain ``.include`` of models, ``.lib``, ``.temp``,
``.control`` or ``.end``: the harness owns all of those so that one netlist
can be swept across the whole PVT grid without editing. The harness hands
the fragment these parameters:

    vdd_val   the supply for this PVT point (nominal, +tol or -tol)
    vdd_nom   the nominal supply, for ratio-style measurements
    temp_c    the temperature for this PVT point (also set via .temp)

plus anything in the manifest's ``params`` map.

A manifest may also name a **device under test**::

    sim/<experiment-slug>/testbench/tb.json   {"dut": "sim/dut/bandgap_top.spice"}

The DUT is a second fragment holding nothing but ``.subckt`` definitions;
the harness ``.include``s it ahead of the testbench so several testbenches
share one netlist, and so the *same* testbench can be re-run against a
different netlist (a frozen copy, or a post-layout extracted netlist) with
``--dut <path>`` and no edit to the testbench at all. Which netlist a record
was taken against is carried in its **Netlist provenance** field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .corners import (
    DEFAULT_CORNER_SET,
    DEFAULT_NOMINAL_SUPPLY_V,
    DEFAULT_SUPPLY_TOLERANCE,
    DEFAULT_TEMPERATURES_C,
)

MANIFEST_NAME = "tb.json"

#: Name of the per-experiment subdirectory that holds the testbench, per
#: the directory convention in ``sim/README.md``.
TESTBENCH_DIRNAME = "testbench"

FORBIDDEN_DIRECTIVES = (".control", ".endc", ".end", ".lib", ".temp", ".include")

#: A DUT fragment is allowed to pull in sub-netlists of its own (an extracted
#: netlist routinely does), but it must not own the deck: a stray ``.end``
#: would truncate every generated deck at the DUT, and ``.lib`` / ``.temp``
#: would pin the corner the harness is sweeping.
FORBIDDEN_DUT_DIRECTIVES = (".control", ".endc", ".end", ".lib", ".temp")

#: Repository root -- ``sim/harness/testbench.py`` -> ``<repo>``. DUT paths in
#: a manifest are written repo-relative so they read the same from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Testbench:
    directory: Path
    name: str
    netlist: Path
    dut: Path | None = None
    description: str = ""
    claim: str = ""
    subset_reason: str = ""
    nominal_supply_v: float = DEFAULT_NOMINAL_SUPPLY_V
    supply_tolerance: float = DEFAULT_SUPPLY_TOLERANCE
    temperatures_c: tuple[float, ...] = DEFAULT_TEMPERATURES_C
    corners: tuple[str, ...] = (DEFAULT_CORNER_SET,)
    analyses: tuple[str, ...] = ("op",)
    measure: dict[str, str] = field(default_factory=dict)
    params: dict[str, str | float] = field(default_factory=dict)
    checks: dict[str, dict] = field(default_factory=dict)
    options: tuple[str, ...] = ()

    @property
    def experiment(self) -> str:
        """The ``<experiment-slug>`` this testbench belongs to.

        ``sim/<experiment-slug>/testbench/tb.json`` -> ``<experiment-slug>``.
        """
        return self.directory.parent.name

    @property
    def experiment_dir(self) -> Path:
        """``sim/<experiment-slug>/`` -- where records/corners/snapshots live."""
        return self.directory.parent

    @property
    def netlist_sha256(self) -> str:
        return hashlib.sha256(self.netlist.read_bytes()).hexdigest()

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256((self.directory / MANIFEST_NAME).read_bytes()).hexdigest()

    @property
    def dut_sha256(self) -> str:
        return "" if self.dut is None else hashlib.sha256(self.dut.read_bytes()).hexdigest()

    @property
    def dut_path(self) -> str:
        """The DUT netlist as a repo-relative path (absolute if outside the repo)."""
        if self.dut is None:
            return ""
        return _repo_relative(self.dut)

    @property
    def dut_provenance_class(self) -> str:
        """``schematic`` / ``extracted`` / ``frozen`` -- read off the DUT path.

        ``sim/README.md`` requires every record to say whether it was taken
        against the schematic netlist or a post-layout extracted one. The
        classification follows the directory the DUT lives in so that a
        post-layout re-run (#17) reports itself correctly with no flag to
        forget: anything under ``layout/`` is extracted.
        """
        if self.dut is None:
            return "schematic"
        path = self.dut_path
        if path.startswith("layout/"):
            return "extracted"
        if "/frozen/" in path:
            return "frozen schematic"
        return "schematic"

    def provenance(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "claim": self.claim,
            "experiment": self.experiment,
            "directory": self.directory.name,
            "netlist": self.netlist.name,
            "netlist_sha256": self.netlist_sha256,
            "manifest_sha256": self.manifest_sha256,
            "dut": self.dut_path,
            "dut_sha256": self.dut_sha256,
            "dut_provenance_class": self.dut_provenance_class,
            "nominal_supply_v": self.nominal_supply_v,
            "supply_tolerance": self.supply_tolerance,
        }


def _require(manifest: dict, key: str, path: Path):
    if key not in manifest:
        raise ValueError(f"{path}: missing required key {key!r}")
    return manifest[key]


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def resolve_dut(value: str | Path, manifest_dir: Path) -> Path:
    """Locate a DUT netlist named by a manifest or by ``--dut``.

    Repo-relative first (how manifests are written, so they read the same
    from any working directory), then relative to the manifest, then as
    given -- which covers an absolute path to a netlist outside the repo.
    """
    candidate = Path(value)
    tried: list[Path] = []
    for option in (REPO_ROOT / candidate, manifest_dir / candidate, candidate):
        if option.is_file():
            return option.resolve()
        tried.append(option)
    raise FileNotFoundError(
        f"DUT netlist {str(value)!r} does not exist; tried: "
        + ", ".join(str(t) for t in tried)
    )


def load(directory: str | Path, dut: str | Path | None = None) -> Testbench:
    """Load a testbench manifest into a :class:`Testbench`.

    Accepts the experiment directory (``sim/<slug>/``), its ``testbench/``
    subdirectory, or the ``tb.json`` path itself. ``dut`` overrides the
    manifest's own ``dut`` key -- the swap point that lets one testbench run
    unedited against a frozen or post-layout extracted netlist.
    """
    directory = Path(directory).resolve()
    if directory.is_file() and directory.name == MANIFEST_NAME:
        directory = directory.parent
    if (directory / TESTBENCH_DIRNAME / MANIFEST_NAME).is_file():
        directory = directory / TESTBENCH_DIRNAME
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no {MANIFEST_NAME} in {directory}")

    manifest = json.loads(manifest_path.read_text())

    netlist = directory / _require(manifest, "netlist", manifest_path)
    if not netlist.is_file():
        raise FileNotFoundError(f"{manifest_path}: netlist {netlist} does not exist")

    measure = dict(_require(manifest, "measure", manifest_path))
    if not measure:
        raise ValueError(f"{manifest_path}: 'measure' must define at least one measurement")
    for key in measure:
        if not key.replace("_", "").isalnum():
            raise ValueError(
                f"{manifest_path}: measurement name {key!r} must be alphanumeric/underscore "
                "(it becomes an ngspice vector name)"
            )

    dut_value = dut if dut is not None else manifest.get("dut")
    dut_path = resolve_dut(dut_value, directory) if dut_value else None

    tb = Testbench(
        directory=directory,
        name=manifest.get("name", directory.parent.name),
        netlist=netlist,
        dut=dut_path,
        description=manifest.get("description", ""),
        claim=manifest.get("claim", ""),
        # A manifest may pre-declare why its grid is a deliberate subset of
        # the mandated PVT matrix (e.g. an axis the testbench sweeps
        # internally). --subset-reason still overrides, and either way the
        # text is copied verbatim into the record: sim/README.md wants the
        # justification *on the record*, not merely in a shell history.
        subset_reason=manifest.get("subset_reason", ""),
        nominal_supply_v=float(manifest.get("nominal_supply_v", DEFAULT_NOMINAL_SUPPLY_V)),
        supply_tolerance=float(manifest.get("supply_tolerance", DEFAULT_SUPPLY_TOLERANCE)),
        temperatures_c=tuple(
            float(t) for t in manifest.get("temperatures_c", DEFAULT_TEMPERATURES_C)
        ),
        corners=tuple(manifest.get("corners", (DEFAULT_CORNER_SET,))),
        analyses=tuple(manifest.get("analyses", ("op",))),
        measure=measure,
        params={k: v for k, v in manifest.get("params", {}).items()},
        checks=dict(manifest.get("checks", {})),
        options=tuple(manifest.get("options", ())),
    )
    validate_netlist(tb)
    validate_dut(tb)
    return tb


def _offending_directives(path: Path, forbidden: tuple[str, ...]) -> list[str]:
    problems: list[str] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip().lower()
        if not line.startswith("."):
            continue
        if line.split()[0] in forbidden:
            problems.append(f"  line {lineno}: {raw.strip()}")
    return problems


def validate_dut(tb: Testbench) -> None:
    """Reject a DUT netlist that would take the deck over.

    An xschem export ends in ``.end``; ``.include``-ing that verbatim would
    truncate every generated deck right after the DUT, and the missing
    measurements would look like a convergence failure rather than the
    packaging mistake it is. ``.include`` *is* allowed here -- an extracted
    netlist legitimately pulls in sub-netlists.
    """
    if tb.dut is None:
        return
    problems = _offending_directives(tb.dut, FORBIDDEN_DUT_DIRECTIVES)
    if problems:
        raise ValueError(
            f"{tb.dut}: a DUT netlist must hold subcircuit definitions only, no "
            f"{', '.join(FORBIDDEN_DUT_DIRECTIVES)} -- the harness supplies the "
            "models, corner libs, temperature and control block:\n" + "\n".join(problems)
        )


def validate_netlist(tb: Testbench) -> None:
    """Reject fragments that try to own what the harness owns.

    Catching this here is much friendlier than debugging a duplicated
    ``.end`` or a hardcoded ``.temp 27`` that silently pins every corner to
    room temperature.
    """
    problems = _offending_directives(tb.netlist, FORBIDDEN_DIRECTIVES)
    if problems:
        raise ValueError(
            f"{tb.netlist}: netlist fragments must not contain "
            f"{', '.join(FORBIDDEN_DIRECTIVES)} -- the harness supplies the models, "
            "corner libs, temperature and control block:\n" + "\n".join(problems)
        )


def discover(root: str | Path) -> list[Path]:
    """Every experiment directory under ``root`` that owns a testbench.

    Looks for ``<root>/<experiment-slug>/testbench/tb.json`` and returns the
    ``<experiment-slug>`` directories, sorted.
    """
    root = Path(root)
    return sorted(
        p.parent.parent for p in root.glob(f"*/{TESTBENCH_DIRNAME}/{MANIFEST_NAME}")
    )
