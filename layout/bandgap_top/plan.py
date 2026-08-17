#!/usr/bin/env python3
"""Declarative floorplan for the ``bandgap_top`` layout.

This module turns the flattened schematic netlist
(:mod:`layout.bandgap_top.netlist_model`) into an explicit, ordered list of
**rows** of **items** — the placement plan the GDS generator draws and the LVS
reference-netlist writer mirrors. Both read this one module, so the drawn
geometry and the LVS reference can never disagree about how many fingers a
device was split into, which dummy devices exist, which trim-ladder nodes the
metal strap option shorts, or (since #75) what area of recognition-marker
geometry each resistor / bipolar / MIM-cap body ends up with — the last of
which is what sets the device parameters ``klt lvs`` compares. See
"Drawn-device geometry, shared with the LVS reference writer" below.

Row order (bottom to top) follows ``layout/floorplan.md``:

* the start-up bleeder ``XRPU`` and the start-up kick devices sit at the
  block periphery (floorplan §1, §7) — they interact with the matched core
  only through the two kick taps;
* the amplifier stack sits above them (floorplan §6);
* the core mirror/cascode array sits directly beneath the PNP array
  (floorplan §1: every mirror leg feeds the PNP-array/resistor-strip nodes);
* the PNP array, the R1/R2 summing resistors and the trim ladder are
  physically adjacent, in the ``Q3 -> R1 -> tn0 -> ladder -> vref`` order the
  floorplan's §3.2 diagram specifies.

All PMOS rows are contiguous so the whole PMOS band sits in **one** Nwell,
which keeps the extracted PMOS body a single net (the ``klt`` gf180mcu
extraction deck derives the PMOS body from the Nwell polygon; see
``netlist_model.reduce_nets``).

Matching plan realised here (floorplan §0's priority order)
----------------------------------------------------------

* **Tier 1 — amp input pair, amp mirror/cascode load, core mirror + cascode.**
  Each of these is drawn as an interdigitated, common-centroid array with
  dummy devices at both array edges:

  =============================  ==========================================
  array                          finger order (D = dummy)
  =============================  ==========================================
  amp ``M1``/``M2`` input pair   ``D (A B B A) x4 D``     (nf = 8 by layout)
  amp ``M3``/``M4`` load         ``D A B B A D``          (nf = 2 by layout)
  amp ``MC3``/``MC4`` cascode    ``D A B B A D``          (nf = 2 by layout)
  amp ``MC1``/``MC2`` cascode    ``D A B B A D``          (nf = 2 by layout)
  core ``M1``/``M2``/``M3``      ``D (A B C C B A) x2 D`` (nf = 4 by layout)
  core ``MC1``/``MC2``/``MC3``   ``D (A B C C B A) x2 D`` (nf = 4 by layout)
  =============================  ==========================================

  ``A B B A`` / ``A B C C B A`` repeat to a palindrome about the array
  centre, so every device in the array shares one centroid — the standard
  common-centroid finger order for a 2- or 3-element ratioed group.

* **Tier 2 — resistor array.** ``R1``/``R2`` and all 63 trim-ladder unit
  segments are drawn from the identical ``ppolyf_u`` unit width
  (``r_width = 2 um``) with identical per-segment contact geometry, per
  floorplan §3.1/§3.2.

* **Tier 3 — PNP array.** ``Q1``/``Q3`` (one unit each) and ``Q2`` (four
  units, per floorplan §4.1's "build Q2 from 4 unit devices, not the
  monolithic 10x10 cell") are placed as ``D Q3 Q2 Q2 Q1 Q2 Q2 D``, with
  dummy units at both array edges.

  Floorplan §4.1 asks for a common-centroid pattern over all three devices,
  which **cannot be drawn exactly**: ``Q1`` and ``Q3`` are one indivisible
  ``pnp_05p00x05p00`` unit each, so no placement can give two single-unit
  devices the same centroid. One pairing has to win, and it is ``Q1``/``Q2``:

  - ``Q1``/``Q2`` set ``dVBE`` across ``R2``, and that error reaches ``vref``
    multiplied by ``R1/R2`` (230.18 um / 18 um ~ 12.8x);
  - ``Q3``'s ``VBE`` lands on ``vref`` at unity gain.

  So a gradient-induced ``VBE`` error between ``Q1`` and ``Q2`` costs ~13x
  what the same error between ``Q1`` and ``Q3`` costs. ``Q2``'s four units
  are therefore placed symmetrically about ``Q1`` (exact shared centroid,
  verified by ``matching_report.py``), and ``Q3`` keeps floorplan §4.2's
  weaker requirement — "the same unit type as Q1, placed in the same
  common-centroid group for process-gradient consistency", which §4.2 itself
  distinguishes from the routing/placement symmetry ``Q1``/``Q2`` needs.

Former schematic/layout finger-count deviation (resolved by #65)
------------------------------------------------------------------

Fifteen devices used to be drawn with a **different finger count** than
``design/netlist/bandgap_top.spice`` carried (:data:`LAYOUT_FOLDS`), because
the schematic's ``nf`` (e.g. ``core.M1`` at ``nf=1``, 1 x 60 um) had never
been updated to match what this module always needed to draw (4 x 15 um, for
two layout-driven reasons: a single-finger device cannot be interdigitated
with anything, and a 60 um/200 um single-finger transistor is not a shape
anyone draws). Since ``ad``/``as``/``pd``/``ps`` are written as expressions
in ``nf``, that meant every simulated drain/source junction capacitance for
those 15 devices corresponded to geometry this module could not draw.

#65 corrected ``nf`` in the schematic to match the drawn finger counts (total
``W``/``L`` unchanged), re-emitted ``design/netlist/*.spice``, and re-ran the
affected ``sim/`` suites against the corrected netlist. :data:`LAYOUT_FOLDS`
is therefore empty: ``fingers()``'s fallback to ``device.nf`` already returns
the drawn count for every device now that the schematic and the layout agree.
See ``layout/README.md`` § "Findings and escalations" for the historical
record of the finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netlist_model import (
    Device,
    FlatNetlist,
    NetlistError,
    load,
    nm,
    trim_strap_shorted,
)

#: Trim code the layout's metal strap option is drawn for. 32 is the
#: mid-scale code ``design/bandgap_trim.sch`` defaults to (``.param
#: trim_code=32``); at code 32 straps RS0..RS4 are shorted and RS5 is open,
#: i.e. ladder units 1..31 are strapped out and units 32..63 are in circuit.
DRAWN_TRIM_CODE = 32

#: Layout finger counts that differ from the netlist's ``nf`` — see the
#: module docstring's "Former schematic/layout finger-count deviation"
#: section. Keys are flattened device paths.
#:
#: Empty as of issue #65: the 15 entries this dict used to carry (core
#: mirror/cascode at nf=4, amp input pair at nf=8, amp mirror load/cascodes
#: at nf=2, startup.MSENSE at nf=2) existed solely to reconcile a
#: schematic/layout mismatch -- the schematic declared nf=1 (or, for the amp
#: input pair, nf=4) while this module always needed to draw more fingers
#: for interdigitation/matching or reasonable aspect ratio. #65 corrected
#: the schematic's nf to match what this module draws, so ``fingers()``'s
#: fallback to ``device.nf`` now already returns the drawn count for every
#: device and no override is needed. Kept as a live (empty) dict rather than
#: removed so a future genuine layout-driven fold has a documented place to
#: go, with the same "report it, do not silently absorb it" discipline #65
#: itself was filed under.
LAYOUT_FOLDS: dict[str, int] = {}

#: Geometry of the dummy devices placed at every matched-array edge. Dummies
#: are drawn at the same L as the array they guard (set per row below) and at
#: a small W; all three terminals tie to the array's own supply rail so the
#: dummy is unconditionally off.
DUMMY_W_NM = 2000


@dataclass
class MosItem:
    """One drawn MOS finger (a single-gate island)."""

    key: str
    kind: str  # "nfet" | "pfet"
    w_nm: int
    l_nm: int
    nets: dict[str, str]  # s / g / d
    device: str | None = None  # flattened netlist path (None for a dummy)
    dummy: bool = False

    @property
    def is_mos(self) -> bool:
        return True


@dataclass
class ResItem:
    """One drawn ``ppolyf_u`` resistor, folded into ``segments`` serpentine legs."""

    key: str
    width_nm: int
    length_nm: int
    segments: int
    nets: tuple[str, str]
    devices: tuple[str, ...] = ()
    #: True for a schematic ``ppolyf_u_1k`` (or other high-sheet-rho) device,
    #: e.g. ``startup.RPU``. klayout-tools' gf180mcu extraction deck only
    #: models the base ``ppolyf_u`` flavour (klayout-tools#299) -- drawing
    #: this body with the same RES_MK/Pplus/SAB recognition markers as a
    #: real base-flavour resistor would get it mis-recognised at the wrong
    #: (350 ohm/sq) sheet resistance, so `generate.py` additionally marks a
    #: high-rho body with `Resistor` (62/0), one of the deck's declared
    #: `excludes` layers for its `ppolyf_u` entry -- keeping it a short,
    #: same as an unmarked device, rather than silently wrong (#73).
    high_rho: bool = False

    is_mos = False


@dataclass
class TrimLadderItem:
    """The 63-segment trim ladder, drawn as unit segments in ``rows`` sub-rows.

    The ladder is one series chain of ``units`` identical segments. Chain
    **node index** *k* is the node between drawn unit *k-1* and unit *k*, so
    node 0 is ``nets[0]`` (``core.tn0``), node ``units`` is ``nets[1]``
    (``vref``), and node *k* is schematic net ``devices[k].nets["n1"]``.
    :attr:`strap_spans` and :attr:`split_after_unit` are both stated in those
    indices.
    """

    key: str
    unit_width_nm: int
    unit_length_nm: int
    units: int
    sub_rows: int
    nets: tuple[str, str]  # (bottom = tn0, top = vref)
    #: Node-index pairs the drawn Metal1 trim option shorts, derived from the
    #: schematic's own ideal ``RS*`` strap expressions at
    #: :data:`DRAWN_TRIM_CODE` (:func:`trim_strap_spans`) — **not** from a
    #: hand-picked span. Drawing one strap per closed schematic bit, rather
    #: than a single span across the whole strapped group, is what makes the
    #: drawn ladder the *same network* as the schematic's (and not merely an
    #: electrically equivalent one) for LVS — see :func:`trim_strap_spans`.
    strap_spans: tuple[tuple[int, int], ...]
    #: Chain node the ladder wraps onto its second sub-row at — a pure
    #: placement choice (it splits the row into two roughly equal halves),
    #: with no electrical meaning.
    split_after_unit: int
    devices: tuple[str, ...] = ()

    is_mos = False


@dataclass
class PnpItem:
    """One vertical-PNP unit cell (emitter / base ring / collector ring)."""

    key: str
    emitter_um: float
    emitter_net: str
    base_net: str
    device: str | None = None
    dummy: bool = False

    is_mos = False


@dataclass
class TapItem:
    """A substrate or Nwell tap bar (no device, pure body/guard contact)."""

    key: str
    kind: str  # "psub" | "nwell"
    length_nm: int
    net: str

    is_mos = False


@dataclass
class MimCapItem:
    """The amplifier's compensation MIM capacitor.

    Drawn on Metal4 / FuseTop / Metal5, stacked **over** the device field
    rather than consuming its own floor area (standard practice for an M4/M5
    MIM). The ``klt`` gf180mcu **DRC** deck still reads none of those layers,
    but the **extraction** deck now recognises the cap itself
    (klayout-tools#225, plus the ``CAP_MK`` marker #73 drew), and both plates
    are wired for real to the block's ``vdd``/``fb`` routing via a genuine
    ``Via1``..``Via4`` stack (``generate._mim_cap``, #77) — this layout's
    only use of ``Metal2``..``Metal5``. Since klayout-tools#329,
    ``make_reference.py`` *does* have to know about part of that via stack:
    the deck ties a recognised cap's bottom plate into its own ``metals[]``
    connectivity node when the plate layer is one of the deck's tracked
    metals (gf180mcu's bottom plate is ``Metal4``), so the drawn
    ``Via1``..``Via3`` stack landing inside the bottom-plate box resolves
    that terminal to the cap's real net (``vdd`` here) rather than a
    synthesized one (``decks.CapacitorDevice``'s top/bottom-plate
    connectivity fields; gf180-bandgap#89). **Since gf180-bandgap#88, the
    top plate is resolved the same way**: the deck wires it through
    ``top_plate_via``/``top_plate_via_metal`` wherever a via actually lands
    on the *recognised* top-plate region without also shorting it to the
    bottom plate (klayout-tools#364/PR #368), and this layout's ``fb``
    up-hop via now lands directly inside that recognised region (see
    ``generate._mim_cap``'s docstring) — so the top plate resolves to its
    real net (``fb``) in the reference too, not a floating one. ``nets`` is
    ``(bottom, top)`` = ``(device.nets["p"], device.nets["n"])`` per
    ``TERMINALS["cap"]`` in :mod:`netlist_model`, which for ``amp.CC``
    resolves to ``("vdd", "fb")`` — bottom plate = Metal4 = ``vdd``, top
    plate = FuseTop = ``fb``.

    No geometry fields live here: the via stack's placement (which row's
    already-drawn rails to piggy-back on, and the standalone landing pad
    that keeps the down-hop via clear of the bottom plate) is a pure
    `generate.py` drawing decision with no bearing on the device parameters
    `make_reference.py` predicts, so — unlike ``MIM_PLATE_INSET`` et al.
    below, which both readers need — it stays local to
    ``generate._mim_cap``.
    """

    key: str
    width_nm: int
    height_nm: int
    nets: tuple[str, str]
    device: str


@dataclass
class Row:
    name: str
    items: list[object] = field(default_factory=list)
    nwell: bool = False  # row sits inside the PMOS band's Nwell
    note: str = ""


# --------------------------------------------------------------------------- #
# Drawn-device geometry, shared with the LVS reference writer
#
# These constants and the functions below used to live in ``generate.py``.
# They moved here because ``layout/lvs/make_reference.py`` has to *predict*
# the drawn geometry as well: ``klt lvs`` compares device parameters, and the
# parameter ``klt extract`` reports for a resistor / bipolar / MIM capacitor
# is measured off the recognised marker geometry, not read from the
# schematic. Keeping the geometry in the one module both ``generate.py`` and
# ``make_reference.py`` already read is the same single-source-of-truth rule
# this module's header states for finger counts and dummies (#75).
#
# ``generate.py`` re-exports every name below, so its own drawing code (and
# its geometry-constant table, which still carries each value's deck-minimum
# justification) is unchanged.
# --------------------------------------------------------------------------- #

CT = 240  # contact.width.1 min 220
ENC_CT = 100  # comp/poly2 enclosing contact, min 70
POLY_SP = 300  # poly2.space.1 min 240
IMPLANT_ENC = 200  # Pplus/Nplus overlap of COMP
RES_PAD = 440  # ppolyf_u free-end contact pad height, > IMPLANT_ENC so the
# pad stays outside the RES_MK/Pplus/SAB marker box (CT + 2*ENC_CT room for
# the pad's own contact enclosure; see generate.draw_res, #73)
TRIM_PAD = 440  # trim-unit end pad, kept outside that unit's RES_MK box
PNP_GAP = 800  # emitter -> base ring
PNP_RING = 1200  # base/collector ring width
PNP_NW_ENC = 700  # Nwell overlap of the base ring
PNP_COL_GAP = 900  # Nwell -> collector ring
MIM_PLATE_INSET = 600  # FuseTop top-plate inset inside the Metal4 bottom plate

#: Sheet resistance ``klt``'s gf180mcu extraction deck models the base
#: ``ppolyf_u`` flavour at (``decks.gf180mcu.EXTRACTION_DECK.resistors``),
#: transcribed there from the PDK's own ``res_extraction.lvs``/magic tech
#: file. Used only to predict the extracted ``R`` value in the LVS reference.
PPOLYF_U_SHEET_RHO = 350.0

#: Sheet resistance ``klt``'s gf180mcu extraction deck models the high-rho
#: ``ppolyf_u_1k`` flavour at (same ``resistors`` tuple as
#: ``PPOLYF_U_SHEET_RHO``, but the ``ppolyf_u_1k`` entry). Used only to
#: predict the extracted ``R`` value in the LVS reference for high-rho
#: bodies (``ResItem.high_rho``, e.g. ``startup.RPU``).
PPOLYF_U_1K_SHEET_RHO = 1000.0

#: Area/perimeter capacitance coefficients ``klt``'s gf180mcu extraction deck
#: reports the MIM capacitor's ``C`` at (klayout-tools#512's two-term law,
#: ``c_c0 = c_cox * A + c_capsw * P``, transcribed from the PDK's own
#: ``sm141064.ngspice`` ``cap_mim_2f0fF`` simulation model card): the
#: deck-nominal "2.0 fF/um^2" density label rounds two separate, more precise
#: coefficients -- the area term (0.5% below the rounded nominal) and a
#: previously-unmodelled perimeter/fringe term. Using a single rounded
#: 2.0e-15 F/um^2 area-only figure here (as this reference used to) left the
#: reference's own capacitance ~0.3% off the real extracted value for this
#: cap's aspect ratio -- small enough that klayout-tools' NetlistComparer's
#: default `C` tolerance absorbed it (no `run_lvs.py`-side mismatch), but
#: large enough that its stricter, tolerance-free device-parameter-equality
#: check flagged the device pair as "matched device parameters differ"
#: anyway (#159). See that deck's ``CapacitorDevice`` entry
#: (``area_cap_f_um2``/``perim_cap_f_um``) for the full derivation and
#: provenance.
MIM_CAP_AREA_F_PER_UM2 = 1.99e-15
MIM_CAP_PERIM_F_PER_UM = 2.383e-16


def res_geometry(item: ResItem) -> tuple[int, int, int]:
    """``(width, height, leg_length)`` of a folded ``ppolyf_u`` serpentine.

    ``leg`` is sized so the *drawn* recognised body area, divided by the
    drawn width (``res_body_area_nm2(item) / item.width_nm``), comes out to
    ``item.length_nm`` — i.e. so `klt extract`'s reported ``l_um`` matches
    the schematic's ``r_length`` (gf180-bandgap#86). That area is
    ``n * leg + (n - 1) * POLY_SP + 2 * IMPLANT_ENC`` (see
    ``res_body_area_nm2``'s docstring for the corner and pad-sliver terms),
    *not* ``n * pitch`` (``pitch = width + POLY_SP``): each fold's link box
    overlaps both legs it joins by a full leg width, so a link only
    contributes ``POLY_SP`` of new resistive length, not a whole pitch.
    Budgeting a full ``pitch`` per link (the pre-#86 formula) drew every
    folded resistor's body ``(n - 1) * width_nm`` short of its schematic
    length. ``pitch`` itself is still the correct *placement* stride between
    legs (used below for the returned footprint width) — only the
    length-budgeting per fold was wrong.
    """
    pitch = item.width_nm + POLY_SP
    n = item.segments
    leg = (item.length_nm - (n - 1) * POLY_SP - 2 * IMPLANT_ENC) // n
    if leg <= item.width_nm + 2 * (ENC_CT + CT):
        raise ValueError(f"{item.key}: {n} segments is too many for L={item.length_nm}")
    return (n - 1) * pitch + item.width_nm, leg, leg


def res_body_area_nm2(item: ResItem) -> int:
    """Area of the *recognised* resistor body of a drawn serpentine.

    ``klt extract`` reports a resistor's ``R`` as ``sheet_rho * A / W**2``,
    with ``A`` the area of ``Poly2 & RES_MK & SAB`` (plus ``Pplus`` for the
    base ``ppolyf_u`` flavour, or ``Resistor`` (62/0) instead for the
    high-rho ``ppolyf_u_1k`` flavour — see ``generate.draw_res``) and ``W``
    the smaller root of ``x**2 - (P/2)x + A`` (KLayout's own
    ``DeviceExtractorResistor``). For every resistor this layout draws that
    root is the drawn body width, so ``A`` is all the reference needs.

    ``A`` is *not* ``r_length * r_width``: a serpentine's ``n-1`` corner
    squares are shared between the legs they join, and the marker box's
    ``IMPLANT_ENC`` overhang clips a slice of each free-end contact pad into
    the body. Both terms are accounted for here — which is exactly what makes
    the comparison meaningful: a body drawn at the wrong length, width or
    fold count changes ``A`` and mismatches.
    """
    _, leg, _ = res_geometry(item)
    n = item.segments
    legs = n * item.width_nm * leg
    corners = (n - 1) * POLY_SP * item.width_nm
    pad_slivers = 2 * item.width_nm * IMPLANT_ENC
    return legs + corners + pad_slivers


def trim_unit_area_nm2(item: TrimLadderItem) -> int:
    """Area of one trim unit's recognised ``ppolyf_u`` body.

    A plain rectangle: ``draw_trim`` pulls ``RES_MK`` in to the unit's
    ``unit_length_nm`` centre (leaving the ``TRIM_PAD`` end pads unmarked, so
    they can act as the extractor's terminal regions) and ``Poly2`` sets the
    height.
    """
    return item.unit_length_nm * item.unit_width_nm


def trim_geometry(item: TrimLadderItem) -> tuple[int, int, int, int]:
    """``(width, height, unit_pitch, lower_sub_row_units)`` for the ladder."""
    unit_x = item.unit_length_nm + 2 * TRIM_PAD
    pitch = unit_x + POLY_SP
    lower = item.split_after_unit
    upper = item.units - lower
    width = max(lower, upper) * pitch + 2000
    height = 2 * item.unit_width_nm + 3600
    return width, height, pitch, lower


def pnp_size(item: PnpItem) -> tuple[int, int]:
    nwell = pnp_base_nwell_side_nm(item)
    coll_outer = nwell + 2 * (PNP_COL_GAP + PNP_RING)
    return coll_outer, coll_outer


def pnp_emitter_area_nm2(item: PnpItem) -> int:
    """Area of the drawn p+ emitter square (the deck's ``AE`` for the unit)."""
    emitter = int(item.emitter_um * 1000)
    return emitter * emitter


def pnp_emitter_perimeter_nm(item: PnpItem) -> int:
    """Perimeter of the drawn p+ emitter square (the deck's ``PE`` for the
    unit). Verified against a real ``klt extract`` run of the committed GDS
    (``20260804-143026-c876a0f.extracted.spice``, gf180-bandgap#111): every
    drawn unit's ``PE`` equals ``4 * sqrt(AE)`` exactly (``PE=20um`` at this
    layout's 5um/``AE=25um^2`` emitter)."""
    emitter = int(item.emitter_um * 1000)
    return 4 * emitter


def pnp_base_nwell_side_nm(item: PnpItem) -> int:
    """Side length of the drawn Nwell island enclosing one PNP unit.

    Exactly the ``L_NWELL`` box ``generate.draw_pnp`` draws (its own
    ``nwell`` local uses this same expression) — **not** the base ring's own
    annulus. Verified against a real ``klt extract`` run of the committed
    GDS (``20260804-143026-c876a0f.extracted.spice``, gf180-bandgap#111):
    every drawn unit's ``AB``/``PB`` *and* ``AC``/``PC`` equal this square's
    area/perimeter exactly (``AB=AC=108.16um^2``, ``PB=PC=41.6um`` at this
    layout's 5um emitter). The deck's vertical-BJT extractor has no drawn
    collector-region shape to measure (the collector is the undrawn
    substrate beneath the whole cell), so it reports this same
    enclosing-Nwell geometry for both the base and collector junction
    parameters.
    """
    emitter = int(item.emitter_um * 1000)
    base_outer = emitter + 2 * (PNP_GAP + PNP_RING)
    return base_outer + 2 * PNP_NW_ENC


def pnp_base_area_nm2(item: PnpItem) -> int:
    """Area of the recognised base region -- the deck's ``AB`` *and* ``AC``
    for the unit; see :func:`pnp_base_nwell_side_nm`."""
    side = pnp_base_nwell_side_nm(item)
    return side * side


def pnp_base_perimeter_nm(item: PnpItem) -> int:
    """Perimeter of the recognised base region -- the deck's ``PB`` *and*
    ``PC`` for the unit; see :func:`pnp_base_nwell_side_nm`."""
    return 4 * pnp_base_nwell_side_nm(item)


def mim_plate_area_nm2(cap: MimCapItem) -> int:
    """Area of the recognised ``FuseTop`` top plate of the MIM capacitor."""
    return (cap.width_nm - 2 * MIM_PLATE_INSET) * (cap.height_nm - 2 * MIM_PLATE_INSET)


def mim_plate_perimeter_nm(cap: MimCapItem) -> int:
    """Perimeter of the recognised ``FuseTop`` top plate of the MIM
    capacitor -- the same rectangle :func:`mim_plate_area_nm2` measures."""
    return 2 * (
        (cap.width_nm - 2 * MIM_PLATE_INSET) + (cap.height_nm - 2 * MIM_PLATE_INSET)
    )


def mim_cap_farads(cap: MimCapItem) -> float:
    """Capacitance ``klt extract`` reports for the MIM capacitor, in farads --
    the deck's own two-term area+perimeter law (see
    ``MIM_CAP_AREA_F_PER_UM2``/``MIM_CAP_PERIM_F_PER_UM``) applied to the same
    recognised plate rectangle :func:`mim_plate_area_nm2`/
    :func:`mim_plate_perimeter_nm` measure."""
    area_um2 = mim_plate_area_nm2(cap) / 1e6
    perim_um = mim_plate_perimeter_nm(cap) / 1e3
    return area_um2 * MIM_CAP_AREA_F_PER_UM2 + perim_um * MIM_CAP_PERIM_F_PER_UM


# --------------------------------------------------------------------------- #
# Plan construction
# --------------------------------------------------------------------------- #


def fingers(device: Device) -> int:
    """Drawn finger count for ``device`` (netlist ``nf``, or a layout fold)."""
    return LAYOUT_FOLDS.get(device.path, device.nf)


def _mos_fingers(flat: FlatNetlist, path: str) -> list[MosItem]:
    device = flat.get(path)
    count = fingers(device)
    if device.w_nm % count:
        raise ValueError(f"{path}: W={device.w_nm} does not divide into {count} fingers")
    per_finger = device.w_nm // count
    return [
        MosItem(
            key=f"{path}#{i}",
            kind=device.mos_kind,
            w_nm=per_finger,
            l_nm=device.l_nm,
            nets={"s": device.nets["s"], "g": device.nets["g"], "d": device.nets["d"]},
            device=path,
        )
        for i in range(count)
    ]


def _dummy(key: str, kind: str, l_nm: int, net: str) -> MosItem:
    return MosItem(
        key=key,
        kind=kind,
        w_nm=DUMMY_W_NM,
        l_nm=l_nm,
        nets={"s": net, "g": net, "d": net},
        dummy=True,
    )


def _centroid_pair(a: list[MosItem], b: list[MosItem]) -> list[MosItem]:
    """``A B B A`` / ``A B B A A B B A`` mirror-symmetric interleave of two
    equal-length finger lists."""
    if len(a) != len(b):
        raise ValueError("common-centroid pair needs equal finger counts")
    out: list[MosItem] = []
    for i in range(0, len(a), 2):
        out.extend([a[i], b[i]])
        if i + 1 < len(a):
            out.extend([b[i + 1], a[i + 1]])
    return out


def _centroid_triple(
    a: list[MosItem], b: list[MosItem], c: list[MosItem]
) -> list[MosItem]:
    """``(A B C C B A)`` x n/2 mirror-symmetric interleave of three devices.

    The emitted letter pattern is a palindrome for any even finger count, so
    all three devices share one centroid in both halves of the array.
    """
    if not (len(a) == len(b) == len(c)) or len(a) % 2:
        raise ValueError("common-centroid triple needs an equal, even finger count")
    out: list[MosItem] = []
    for i in range(0, len(a), 2):
        out.extend([a[i], b[i], c[i], c[i + 1], b[i + 1], a[i + 1]])
    return out


def trim_chain_nodes(units: list[Device]) -> list[str]:
    """Schematic net at each chain node of the trim ladder, node 0 first.

    Validates that ``units`` really is one series chain (``RU_i.n2`` is
    ``RU_{i+1}.n1``) rather than assuming it, so a schematic edit that
    re-topologises the ladder surfaces here instead of being silently
    absorbed into a wrong strap derivation.
    """
    nodes = [units[0].nets["n1"]]
    for device in units:
        if device.nets["n1"] != nodes[-1]:
            raise NetlistError(
                f"trim ladder is not a series chain at {device.path}: "
                f"n1={device.nets['n1']!r}, expected {nodes[-1]!r}"
            )
        nodes.append(device.nets["n2"])
    return nodes


def trim_strap_spans(
    flat: FlatNetlist, units: list[Device], trim_code: int
) -> tuple[tuple[int, int], ...]:
    """Chain-node spans the drawn Metal1 trim option shorts at ``trim_code``.

    ``design/bandgap_trim.sch`` implements the trim as six ideal ``RS*``
    straps, one per code bit, each shorting one binary-weighted group of unit
    segments (bit 0 -> 1 unit, bit 1 -> 2 units, ... bit 5 -> 32 units). This
    reads those straps back out of the flattened netlist, keeps the ones that
    are *closed* at ``trim_code`` (:func:`netlist_model.trim_strap_shorted`),
    and translates each one's two nets into chain-node indices.

    **Why one strap per closed bit, not one span across the whole group.**
    At ``trim_code`` 32 the closed straps are ``S0..S4``, which short chain
    nodes ``0-1``, ``1-3``, ``3-7``, ``7-15`` and ``15-31``. A single
    ``0-31`` span is *electrically* identical (both leave 32 units in series
    between the strapped node and ``vref``) but is a **different network**:
    it leaves nodes 1/3/7/15 as distinct nodes of one 31-unit loop, where the
    schematic has a self-loop plus 2-, 4-, 8- and 16-unit loops all hanging
    off one node. ``layout/lvs`` compares topology, so the layout has to draw
    the straps the schematic actually specifies — this is the mechanical
    derivation that makes that so.
    """
    node_index = {net: i for i, net in enumerate(trim_chain_nodes(units))}
    spans: list[tuple[int, int]] = []
    for device in flat.devices:
        if device.family != "ideal_res":
            continue
        if not trim_strap_shorted(device.model, trim_code):
            continue
        try:
            a = node_index[device.nets["n1"]]
            b = node_index[device.nets["n2"]]
        except KeyError as exc:  # pragma: no cover - schematic-shape guard
            raise NetlistError(
                f"{device.path}: trim strap touches net {exc.args[0]!r}, "
                "which is not a node of the trim ladder chain"
            ) from exc
        spans.append((min(a, b), max(a, b)))
    return tuple(sorted(spans))


def build_rows(flat: FlatNetlist) -> list[Row]:
    """Build the ordered (bottom-to-top) row plan."""
    rows: list[Row] = []

    # ---------------- start-up periphery (floorplan §1, §7) ----------------
    rows.append(
        Row(
            "XRPU",
            [
                ResItem(
                    key="startup.RPU",
                    width_nm=nm(flat.get("startup.RPU").params["r_width"]),
                    length_nm=nm(flat.get("startup.RPU").params["r_length"]),
                    segments=57,
                    nets=("startup.det", "vdd"),
                    devices=("startup.RPU",),
                    high_rho=flat.get("startup.RPU").model != "ppolyf_u",
                )
            ],
            note="start-up pull-up bleeder, folded serpentine (floorplan §7/§11.3)",
        )
    )

    rows.append(
        Row(
            "NBIAS",
            _mos_fingers(flat, "core.M5")
            + _mos_fingers(flat, "core.MNB")
            + _mos_fingers(flat, "startup.MSENSE")
            + _mos_fingers(flat, "startup.MKFB")
            + _mos_fingers(flat, "startup.MKCASC")
            + [TapItem("ptap.nbias", "psub", 6000, "vss")],
            note="core NMOS bias + start-up kick devices (no matching requirement)",
        )
    )

    rows.append(
        Row(
            "AMPNBIAS",
            _mos_fingers(flat, "amp.M5")
            + _mos_fingers(flat, "amp.MBN2")
            + _mos_fingers(flat, "amp.MBD1")
            + _mos_fingers(flat, "amp.MBD2")
            + [TapItem("ptap.ampn", "psub", 6000, "vss")],
            note="amp tail + cascode-bias NMOS (single instances, not matched)",
        )
    )

    mc1 = _mos_fingers(flat, "amp.MC1")
    mc2 = _mos_fingers(flat, "amp.MC2")
    rows.append(
        Row(
            "AMPNCASC",
            [_dummy("dum.ampncasc.l", "nfet", mc1[0].l_nm, "vss")]
            + _centroid_pair(mc1, mc2)
            + [_dummy("dum.ampncasc.r", "nfet", mc1[0].l_nm, "vss")],
            note="amp NMOS cascode pair, common-centroid A B B A + edge dummies",
        )
    )

    m1 = _mos_fingers(flat, "amp.M1")
    m2 = _mos_fingers(flat, "amp.M2")
    rows.append(
        Row(
            "AMPPAIR",
            [_dummy("dum.amppair.l", "nfet", m1[0].l_nm, "vss")]
            + _centroid_pair(m1, m2)
            + [_dummy("dum.amppair.r", "nfet", m1[0].l_nm, "vss")],
            note="amp input pair — floorplan §0 tier-1 matching, A B B A A B B A",
        )
    )

    # ---------------- PMOS band (one Nwell) --------------------------------
    amc3 = _mos_fingers(flat, "amp.MC3")
    amc4 = _mos_fingers(flat, "amp.MC4")
    rows.append(
        Row(
            "AMPPCASC",
            [_dummy("dum.amppcasc.l", "pfet", amc3[0].l_nm, "vdd")]
            + _centroid_pair(amc3, amc4)
            + [_dummy("dum.amppcasc.r", "pfet", amc3[0].l_nm, "vdd")],
            nwell=True,
            note="amp PMOS cascode pair, common-centroid A B B A + edge dummies",
        )
    )

    am3 = _mos_fingers(flat, "amp.M3")
    am4 = _mos_fingers(flat, "amp.M4")
    rows.append(
        Row(
            "AMPLOAD",
            [_dummy("dum.ampload.l", "pfet", am3[0].l_nm, "vdd")]
            + _centroid_pair(am3, am4)
            + [_dummy("dum.ampload.r", "pfet", am3[0].l_nm, "vdd")],
            nwell=True,
            note="amp PMOS mirror load — floorplan §0 tier-1 matching",
        )
    )

    rows.append(
        Row(
            "PBIAS",
            _mos_fingers(flat, "core.MCB")
            + _mos_fingers(flat, "amp.MBP1")
            + _mos_fingers(flat, "amp.MB1")
            + [TapItem("ntap.pbias", "nwell", 6000, "vdd")],
            nwell=True,
            note="cascode-bias PMOS (single instances, floorplan §5: not a matching group)",
        )
    )

    cm4 = _mos_fingers(flat, "core.M4")
    cmc4 = _mos_fingers(flat, "core.MC4")
    rows.append(
        Row(
            "COREIBIAS",
            [_dummy("dum.coreibias.l", "pfet", cm4[0].l_nm, "vdd")]
            + cm4
            + cmc4
            + [_dummy("dum.coreibias.r", "pfet", cm4[0].l_nm, "vdd")],
            nwell=True,
            note="core ibias leg (M4/MC4) — different W from M1-M3, own sub-array",
        )
    )

    cmc1 = _mos_fingers(flat, "core.MC1")
    cmc2 = _mos_fingers(flat, "core.MC2")
    cmc3 = _mos_fingers(flat, "core.MC3")
    rows.append(
        Row(
            "CORECASC",
            [_dummy("dum.corecasc.l", "pfet", cmc1[0].l_nm, "vdd")]
            + _centroid_triple(cmc1, cmc2, cmc3)
            + [_dummy("dum.corecasc.r", "pfet", cmc1[0].l_nm, "vdd")],
            nwell=True,
            note="core cascode MC1-MC3, common-centroid A B C C B A + edge dummies",
        )
    )

    cm1 = _mos_fingers(flat, "core.M1")
    cm2 = _mos_fingers(flat, "core.M2")
    cm3 = _mos_fingers(flat, "core.M3")
    rows.append(
        Row(
            "COREMIRROR",
            [_dummy("dum.coremirror.l", "pfet", cm1[0].l_nm, "vdd")]
            + _centroid_triple(cm1, cm2, cm3)
            + [_dummy("dum.coremirror.r", "pfet", cm1[0].l_nm, "vdd")],
            nwell=True,
            note="core mirror M1-M3 — floorplan §0 tier-1 matching",
        )
    )

    rows.append(
        Row(
            "NTAP",
            [TapItem("ntap.top", "nwell", 40000, "vdd")],
            nwell=True,
            note="Nwell body tie for the PMOS band",
        )
    )

    # ---------------- PNP array + resistor / trim strip --------------------
    rows.append(
        Row(
            "PNP",
            [
                PnpItem("dum.pnp.l", 5.0, "vss", "vss", dummy=True),
                PnpItem("core.Q3", 5.0, "core.e3", "vss", device="core.Q3"),
                PnpItem("core.Q2#0", 5.0, "core.e2", "vss", device="core.Q2"),
                PnpItem("core.Q2#1", 5.0, "core.e2", "vss", device="core.Q2"),
                PnpItem("core.Q1", 5.0, "sns1", "vss", device="core.Q1"),
                PnpItem("core.Q2#2", 5.0, "core.e2", "vss", device="core.Q2"),
                PnpItem("core.Q2#3", 5.0, "core.e2", "vss", device="core.Q2"),
                PnpItem("dum.pnp.r", 5.0, "vss", "vss", dummy=True),
            ],
            note="PNP array, D Q3 Q2 Q2 Q1 Q2 Q2 D (floorplan §4.1)",
        )
    )

    r1 = flat.get("core.R1")
    r2 = flat.get("core.R2")
    # `segments` co-scales with #69's `k=2` R1/R2 length rescale (14 -> 28,
    # 2 -> 4): folding into twice as many, half-as-long legs keeps each
    # resistor's drawn *leg height* near its pre-#69 value and spends the
    # extra length on width instead, which this row has to spare (RSTRIP is
    # never the block's width-limiting row -- see AREA.md Finding 3 / #70).
    # A row's height multiplies against the full block width, so leaving
    # `segments` fixed while length doubles blows the area budget; scaling
    # `segments` with length does not.
    rows.append(
        Row(
            "RSTRIP",
            [
                ResItem(
                    key="core.R2",
                    width_nm=nm(r2.params["r_width"]),
                    length_nm=nm(r2.params["r_length"]),
                    segments=4,
                    nets=("core.e2", "sns2"),
                    devices=("core.R2",),
                ),
                ResItem(
                    key="core.R1",
                    width_nm=nm(r1.params["r_width"]),
                    length_nm=nm(r1.params["r_length"]),
                    segments=28,
                    nets=("core.e3", "core.tn0"),
                    devices=("core.R1",),
                ),
            ],
            note="R2 (PTAP-setting) and R1 (output branch), identical unit width",
        )
    )

    trim_units = [d for d in flat.devices if d.path.startswith("core.trim.RU")]
    unit = trim_units[0]
    rows.append(
        Row(
            "TRIM",
            [
                TrimLadderItem(
                    key="core.trim",
                    unit_width_nm=nm(unit.params["r_width"]),
                    unit_length_nm=nm(unit.params["r_length"]),
                    units=len(trim_units),
                    sub_rows=2,
                    nets=("core.tn0", "vref"),
                    strap_spans=trim_strap_spans(flat, trim_units, DRAWN_TRIM_CODE),
                    split_after_unit=31,
                    devices=tuple(d.path for d in trim_units),
                )
            ],
            note="63-unit binary trim ladder, identical unit segments (floorplan §3.2)",
        )
    )

    return rows


def mim_cap(flat: FlatNetlist) -> MimCapItem:
    device = flat.get("amp.CC")
    return MimCapItem(
        key="amp.CC",
        width_nm=nm(device.params["c_width"]),
        height_nm=nm(device.params["c_length"]),
        # (bottom, top) = (p, n) -- resolves to ("vdd", "fb") for `amp.CC`;
        # see MimCapItem's docstring for why the via stack `generate.py`
        # draws for these two nets targets Metal4 (bottom/vdd) and FuseTop
        # (top/fb) specifically.
        nets=(device.nets["p"], device.nets["n"]),
        device="amp.CC",
    )


def routed_nets(rows: list[Row]) -> list[str]:
    """Every net that needs a corridor spine, in a stable, deterministic order."""
    seen: list[str] = []

    def add(net: str) -> None:
        if net not in seen:
            seen.append(net)

    for row in rows:
        for item in row.items:
            if isinstance(item, MosItem):
                for net in ("s", "g", "d"):
                    add(item.nets[net])
            elif isinstance(item, ResItem):
                add(item.nets[0])
                add(item.nets[1])
            elif isinstance(item, TrimLadderItem):
                add(item.nets[0])
                add(item.nets[1])
            elif isinstance(item, PnpItem):
                add(item.emitter_net)
                add(item.base_net)
            elif isinstance(item, TapItem):
                add(item.net)
    # Supplies first so they land closest to the device field.
    priority = ["vss", "vdd", "vref"]
    return [n for n in priority if n in seen] + [n for n in seen if n not in priority]


def load_plan() -> tuple[FlatNetlist, list[Row]]:
    flat = load()
    return flat, build_rows(flat)


if __name__ == "__main__":  # pragma: no cover
    flat, rows = load_plan()
    for row in rows:
        kinds: dict[str, int] = {}
        for item in row.items:
            kinds[type(item).__name__] = kinds.get(type(item).__name__, 0) + 1
        print(f"{row.name:12s} {len(row.items):3d} items  {kinds}")
    print("routed nets:", len(routed_nets(rows)))
    print(routed_nets(rows))
