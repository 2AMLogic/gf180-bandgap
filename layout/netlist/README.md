# layout/netlist — post-layout parasitic extraction (#17)

`run_extract.py` produces a parasitic-extracted SPICE netlist of
`bandgap_top` via `klt extract --parasitics`, and `mk_extracted_dut.py` turns
that report into the `sim/dut`-ready netlist #17's post-layout suite re-run
takes as `--dut`. This directory holds that tooling and its append-only
reports.

```
layout/netlist/
  README.md                       this file
  run_extract.py                  reproducible klt extract --parasitics invocation -> committed report
  mk_extracted_dut.py             extraction report -> simulatable .subckt bandgap_top (see below)
  verify_mim_routing.py           proves both MiM plates are physically wired to vdd/fb
  bandgap_top_extracted.spice     GENERATED sim/dut-ready DUT (subckt form)
  bandgap_top_extracted_flat.spice  GENERATED, same cards with no subckt wrapper (sim/mc-untrimmed)
  reports/
    bandgap_top/                  <record-id>.{extract.json,extracted.spice}
```

Current state, against `main`'s `bandgap_top.gds` (post-#88) and the current
klayout-tools deck:

```
extracted devices: 156 {'bjt': 8, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65,
                        'ppolyf_u_1k': 1}
net_count        : 92
lvs status       : match   (156/156 devices, 92/92 nets)
drc status       : clean, 0 violations -- the MiM top-plate routing tab that
                   used to draw mim.enclosing.fusetop.1 (gf180-bandgap#82) is
                   gone, redrawn DRM-legal by gf180-bandgap#88
parasitics       : 82 R / 82 C, 209.2 kohm and 2479.2 fF total
```

Taken at `20260803-054749-8d21bf1` (extract) / `20260803-054735-8d21bf1`
(LVS) / `20260803-054725-8d21bf1` (DRC), i.e. the first regeneration since
[gf180-bandgap#88](https://github.com/2AMLogic/gf180-bandgap/issues/88)
redrew the `fb` top-plate contact. `net_count` moved 93 → 92 because the top
plate no longer extracts as its own isolated net (it now resolves onto the
same `fb` net every other `fb`-connected terminal already shares). Older
report sets in `reports/` (`…-9e558e6` and earlier) were taken against the
pre-#88 tab geometry and, further back, against the pre-#91 fold-length
budget bug; both are kept because layout reports are append-only. The
pre-#91 sets' three folded resistors are not the ones this layout draws now:

| Device | pre-#91 `l_um` | at #91 `l_um` | current `l_um` | schematic `r_length` |
|---|---|---|---|---|
| `core.R1` (`$95`) | 407.08 | 460.70 | **436.70** (#96/#88, see below) | 436.705296 µm |
| `core.R2` (`$91`) | 30.74 | 36.34 | 36.34 (unchanged) | 36.341871 µm |
| `startup.RPU` (`$156`) | 3888.36 | 3999.96 | 3999.96 (unchanged) | 4000 µm |

so at #91 the drawn PTAT ratio `(R1+trim)/R2` was 15.118 again, not the
16.128 the pre-fix reports measured. `core.R2` and `startup.RPU` are
unaffected by everything below; only `core.R1` moves again, for the
unrelated reason the next paragraph explains.

**A second, unrelated `core.R1` change lands in the same regeneration
(#88).** [gf180-bandgap#96](https://github.com/2AMLogic/gf180-bandgap/issues/96)/PR#102
re-nulled `core.R1`'s *schematic* value (`460.701871 µm` → `436.705296 µm`,
78470.5 Ω → a lower value at the drawn `W`) to close the TC and
accuracy-window rows, and merged to `main` immediately before #88's branch
point — but nothing regenerated `bandgap_top.gds` between that merge and
#88, so the committed layout still drew the pre-#96 `core.R1` length. #88's
`_mim_cap` redraw requires running the same `generate.py` pipeline that
draws every other row, and that pipeline always sizes `core.R1` from the
*current* schematic `r_length` (`plan.res_geometry`, schematic-driven, no
coupling to the MiM cap) — so regenerating for #88 necessarily also
resyncs `core.R1` to #96's already-ratified value. This is not a #88 change
in its own right, and #88's own diff touches nothing resistor-related; it is
main's first layout regeneration since #96 merged, so this is the first
point that staleness surfaces. `layout/lvs/bandgap_top.ref.spice`'s
`Rcore_R1` value (`80622.5` → `76423.2` Ω) drops with it (predicted from the
same schematic-driven formula), so LVS stays self-consistent throughout —
confirmed: `20260803-054735-8d21bf1.lvs.json` reports `status: match`,
156/156 devices, 92/92 nets, no resistor-value mismatch.

## `mk_extracted_dut.py` — extraction report to simulatable DUT

`klt extract`'s own SPICE output is a *topology* netlist, not a simulatable
deck. `mk_extracted_dut.py` converts it, and the conversion is deliberately
auditable rather than convenient: every transform is a numbered entry
(`T1`…`T9`) echoed into the generated file's header, and every net-level
back-annotation (`BA1`…`BA3`) is **asserted against the extracted structure
before it is applied**, so a back-annotation whose precondition has gone away
is a hard error rather than a silent no-op. Read that header before treating
any number taken against this netlist as post-layout evidence — it is the
complete list of every place the simulated netlist departs from what the
extractor literally measured.

The three back-annotations, and why each exists (a fourth, BA4, existed
until #88 — see the note below the table):

| | Terminal | Asserted to | Why the deck cannot resolve it |
|---|---|---|---|
| BA1 | deck-synthesised `vsubs` | `vss` | gf180mcu draws no distinct p-substrate tap layer, so the deck synthesises a substrate net (`klt lvs` reports this itself as `device.body_unverified`). The drawn guard ring is a Pplus/COMP ring on the `vss` rail. |
| BA2 | all 47 PMOS bodies | `vdd` | no well-tap layer in the deck, so every PMOS body lands on one anonymous well net reaching nothing. |
| BA3 | 8 PNP base nets | `vss` | a recognised bipolar's base region is Nwell, not a connectivity metal — the same gap `klayout-tools#314` closed for capacitor plates, still open for `BipolarDevice` (documented upstream as `klayout-tools#336`). The layout draws an Nplus base-tie ring on `vss` around every unit. |

**BA4 is gone as of [gf180-bandgap#88](https://github.com/2AMLogic/gf180-bandgap/issues/88).**
It used to back-annotate the MiM cap's top plate onto `fb`, because the drawn
`Via4` landed on a `FuseTop` routing tab held outside `CAP_MK` — a **layout**
defect (gf180-bandgap#82), not a tool gap, unlike BA1–BA3. #88 redrew that
contact: the `Via4` now lands directly inside the recognised top plate, which
`klayout-tools#364`/PR #368 made safe to extract without shorting the two
plates together, so the top plate now extracts on the real `fb` net with no
back-annotation. `mk_extracted_dut.py`'s `build_back_annotations()` asserts
this directly — neither plate net is isolated, and the top plate pairs with
schematic `fb` — so a regression back to the floating-top-plate state is a
hard error, not a silent BA4 re-add.

Everything else — device existence, class, connectivity, drawn resistor
`L`/`W`, drawn plate area, drawn finger and PNP-unit counts, and the per-net
RC parasitics — is measured, not asserted.

`--flat` emits the same cards with no `.subckt bandgap_top` wrapper, for
`sim/mc-untrimmed`, whose deck includes its DUT at top level and whose `.ic`
seeds name top-level nodes.

## `verify_mim_routing.py` — the one connection no tool can check

**Historical note, superseded by [gf180-bandgap#88](https://github.com/2AMLogic/gf180-bandgap/issues/88).**
Before #88, `klt extract`/`klt lvs` could not confirm that the compensation
cap's top plate reaches `fb`, because the `fb` up-hop `Via4` landed on a
`FuseTop` routing tab held outside `CAP_MK`/`MIM_L_MK` (a workaround for
`klayout-tools#364`, which read a DRM-legal on-plate via as a `vdd`/`fb`
short) — so the deck's own connectivity graph never saw that via touch the
*recognised* top plate. #17's Test Plan required verifying the connection by
layer inspection instead, via two checks (Check A: merge the `FuseTop`
shapes and assert the recognised plate and the tab the `Via4` landed on are
one polygon; Check B: re-extract a scratch copy of the GDS with
`CAP_MK`/`MIM_L_MK` widened to cover the tab, and confirm the resulting
top-plate net matches `fb` via `klt lvs`).

**Current state.** `klayout-tools#364`/PR #368 fixed the underlying tool
limitation, and #88 redrew the contact: the `fb` up-hop `Via4` now lands
directly inside the recognised top-plate region (see
`layout/bandgap_top/generate.py`'s `_mim_cap` docstring), so `klt
extract`/`klt lvs` confirm this connection themselves — no marker widening,
no layer-inspection workaround. `layout/lvs/make_reference.py` step 9 models
the top plate as `fb` directly, and the committed `klt lvs` report is
`status: match`. `verify_mim_routing.py`'s Check A is kept as a cheap
regression guard (it now takes its `NOTE A` "already on-plate" branch and
passes trivially); Check B's widened-marker re-extraction is retired, since
it no longer proves anything an ordinary `klt extract`/`klt lvs` run of the
committed GDS does not already prove more directly.

```bash
uv run --with klayout python3 layout/netlist/verify_mim_routing.py
```

## Install / version used

Per #17's own Test Plan ("confirm the installed `klt` version actually
includes the resistor/BJT/MIM-cap device-class merges from
klayout-tools#222/#223/#225 before relying on it"):

```bash
uv tool install --force git+https://github.com/2AMLogic/klayout-tools
klt --version
```

Verified against a checkout of `2AMLogic/klayout-tools` at commit
`3b86194` (2026-08-02), which is at or after all three merges:

- `klayout-tools#217` (`klt extract --parasitics`) — merged, closed.
- `klayout-tools#222` (resistor device-class recognition) — merged via
  `klayout-tools#228` (commit `37a1e53`).
- `klayout-tools#223` (bipolar/BJT device-class recognition) — merged
  (already present at the previously-installed revision this repo's `klt`
  had cached; re-confirmed present at `3b86194`).
- `klayout-tools#225` (MiM-capacitor device-class recognition) — merged
  (same).

The `klt` binary this repo had installed prior to this issue (reported
`klt --version` → `0.1.0`, a static string that does not track upstream
commits) predated commit `37a1e53` (`#228`, resistor recognition) by 6
commits — i.e. it did **not** yet include the resistor merge #17's own
dependency history claims is "shipped". Builders re-running this script
should reinstall from a fresh `klayout-tools` checkout (`uv tool install
--force git+https://github.com/2AMLogic/klayout-tools`) rather than trust a
cached `klt` install's `--version` string, which does not change between
releases of this pre-1.0 tool.

**#17's own run** (the suite re-run, delta summary and records) was taken at
klayout-tools commit `e6e46e8` (2026-08-02, upstream `main` at the time),
which is what `uv tool install --force git+…` resolves to. `--version` is
still `0.1.0`; the commit is recorded because the string is not. How to check
what is actually installed, rather than trusting the string:

```bash
python3 -c "import json,pathlib,sysconfig; \
  print(json.loads(pathlib.Path(\
    '$HOME/.local/share/uv/tools/klayout-tools/lib/python3.14/site-packages/'\
    'klayout_tools-0.1.0.dist-info/direct_url.json').read_text())['vcs_info']['commit_id'])"
```

Every `klt` report this repo commits also carries the deck's own content hash
in its `provenance.deck.content_hash` field, which is the more robust check:
two reports with the same deck hash were produced by the same extraction rules
regardless of what `--version` said. #17's reports carry
`sha256:be1a89e0f899a68c60baeeedffe1b4d76b965bd763e1b16beed1c85937872b1d`.

Two deck-behaviour changes landed upstream between the last `origin/main`
report set and this one, and both are visible in the numbers:

- **`klayout-tools#314`** joins a recognised capacitor plate to the ordinary
  metal stack. The MiM cap's bottom plate now extracts on the real `vdd` net
  instead of a floating node of its own, which took `net_count` from 94 to 93
  and required `layout/lvs/make_reference.py`'s step 9 to model that terminal
  on the cap's real net; without that update `klt lvs` reports `mismatch`
  (155/156 devices, 91/94 nets). That un-updated-reference mismatch was filed
  as [gf180-bandgap#89](https://github.com/2AMLogic/gf180-bandgap/issues/89)
  (against the follow-on `klayout-tools#329`) and fixed on `main` by
  [#93](https://github.com/2AMLogic/gf180-bandgap/pull/93); `klt lvs` reports
  `match` again, which is the state every number above was taken in.
- **`klayout-tools#318`** fixed `enclosing_check` silently passing when the
  enclosed shape lies *entirely* outside the enclosing layer. `klt drc` now
  reports the MiM top-plate tab's `mim.enclosing.fusetop.1` violation
  (gf180-bandgap#82) that every earlier `clean` verdict on this same GDS was a
  false negative on. The drawn geometry has not changed since PR #81.

## Reproducing

```bash
python3 layout/netlist/run_extract.py layout/bandgap_top/bandgap_top.gds
```

This runs `klt extract layout/bandgap_top/bandgap_top.gds --deck gf180mcu
--top bandgap_top --parasitics --pdk gf180mcuD -o
layout/netlist/reports/bandgap_top/<record-id>.extracted.spice`. `--pdk
gf180mcuD` (the 3.3V-flavor variant CLAUDE.md names as primary) makes `klt
extract` bind each extracted MOS device to the real gf180mcu
`nfet_03v3`/`pfet_03v3` subcircuit (`X$1 ... nfet_03v3 L=2U W=2.5U`)
instead of the deck's generic `nfet`/`pfet` class token, which is not a
simulatable model name on its own.

## #17's extracted verification suite, re-run against the #88 redraw

Per #17's own Test Plan (re-run the full post-layout suite whenever the
extracted netlist changes) and #88's acceptance criteria, the full suite ran
against the redrawn `bandgap_top_extracted.spice`/`bandgap_top_extracted_flat.spice`:

```bash
python3 sim/run_suite.py --dut layout/netlist/bandgap_top_extracted.spice --only output-voltage-tc psrr-dc line-regulation iq
PDK_ROOT=~/.volare PDK=gf180mcuD python3 sim/mc-untrimmed/run_mc_untrimmed.py --dut layout/netlist/bandgap_top_extracted_flat.spice
python3 sim/run_corners.py startup-extracted
python3 sim/run_corners.py startup-state-search-extracted
python3 sim/run_combined_accuracy.py
```

(`sim/run_suite.py`'s default index also wires in the plain `startup` slug,
which cannot take `--dut` — it taps a series ammeter inside a
`bandgap_startup` subcircuit instance, and an extracted netlist is flat, per
`sim/startup-extracted/testbench/tb.json`'s own docstring — so it is excluded
via `--only` here, the same way the last full extracted re-run before this
one did. `startup-extracted`/`startup-state-search-extracted` are the
post-layout form of that row and are run directly instead.)

**Result: PSRR, line regulation, quiescent current, and both extracted
startup benches PASS.** `startup-extracted` and `startup-state-search-extracted`
each pass 81/81 corners (records `20260803-055559-31e5efc`). **The combined
untrimmed-accuracy row (output reference + TC) still FAILs** —
`sim/suite/combined/20260803-064856-31e5efc.md`, 80/80 corners, worst margin
-44.032 mV at `bjt_ss_125c_3.30v` — but this is **not a #88 regression**:

- It is the same three ratified rows that have FAILed at extracted level
  since #17's original post-layout re-run (`sim/postlayout-delta.md`), rooted
  in [gf180-bandgap#87](https://github.com/2AMLogic/gf180-bandgap/issues/87)
  (still **open**) — the drawn `core.Q2` array's 4x unit-`pnp_05p00x05p00`
  realisation gives an effective dVBE ratio of 4.03 against the schematic's
  single `pnp_10p00x10p00` at 3.63, a first-order Vref error `_mim_cap`'s
  redraw does not touch.
- **Every number improved, none regressed**, relative to the last committed
  extracted evidence
  (`sim/suite/summaries/20260803-014641-feab5b5.md`, taken pre-#96/pre-#88):
  worst TC `151.016` → `90.2239` ppm/degC, worst Vref `1.28321` → `1.25187` V.
  The improvement is [gf180-bandgap#96](https://github.com/2AMLogic/gf180-bandgap/issues/96)/PR#102's
  already-ratified `core.R1` re-null reaching the layout for the first time
  (see the `core.R1` resync note above) — `#88`'s own diff touches nothing
  PNP- or resistor-related.
- The anchor cross-check between `mc-untrimmed`'s deterministic control group
  and `output-voltage-tc`'s own `tt`/3.30 V corner agrees to within 0.5 µV
  (well inside the 100 µV tolerance), so this is a genuine measured result,
  not a harness disagreement.

**`sim/postlayout-delta.md` is intentionally not regenerated by this PR.**
It pairs a schematic-provenance record with an extracted one; the newest
committed schematic-provenance record for these benches
(`20260802-064729-75ca562`) predates #96's `core.R1` re-null, so pairing it
against this PR's post-#96/#88 extracted records would attribute #96's
already-known, already-ratified schematic-level improvement to this PR's
layout redraw — a misleading delta. Regenerating it correctly needs a fresh
schematic-provenance suite re-run against the current `core.R1` value,
tracked separately as
[gf180-bandgap#104](https://github.com/2AMLogic/gf180-bandgap/issues/104).

## RESOLVED (#73): the layout now draws the resistor/MiM-cap recognition markers

The original finding below (kept verbatim as the append-only record of what
was discovered and why) reported that `layout/bandgap_top/generate.py` drew
`Pplus` around every `ppolyf_u` resistor body and `MIM_L_MK` on the
compensation cap's top plate, but not the additional marker layers
(`RES_MK`/`SAB`/`CAP_MK`) the deck's resistor/MiM-capacitor recognisers also
require — so every resistor extracted as a short and the cap as absent.
[gf180-bandgap#73](https://github.com/2AMLogic/gf180-bandgap/issues/73) drew
those markers (plus a from-scratch check of the resulting geometry against
what KLayout's native `DeviceExtractorResistor` actually requires — see that
PR's `generate.py` diff for the two things a literal "just add the marker
boxes" reading of the finding above would have missed):

- **A contact landing *inside* a RES_MK-marked body does not recognise the
  device.** `DeviceExtractorResistor` needs its two-terminal ("C") region to
  *directly abut* the marked ("R") body — a contact that only reaches the
  body via a Metal1 bridge (this layout's original `draw_res`/`draw_trim`
  free-end design) leaves the extractor logging "Expected two polygons on
  contacts interacting with one resistor shape (found 0)" and the body still
  extracting as a short, even with every marker layer present. `draw_res`
  now draws a small unmarked poly pad directly past each resistor's true
  free edge (`RES_PAD`, kept outside the marker box); `draw_trim`'s `TRIM_PAD`
  contact-pad allowance at each unit's ends already had exactly this
  property once `RES_MK` itself was narrowed to the unit's `unit_length_nm`
  centre (it was previously drawn to the pad-inclusive full footprint,
  covering the very contacts it needed to stay clear of).
- **`startup.RPU` must *not* pick up the *base* `ppolyf_u` recogniser's
  `Pplus` marker.** `RPU`'s schematic model is `ppolyf_u_1k` (a
  high-sheet-rho flavor this deck's `resistors` list had no entry for at the
  time — klayout-tools#299), not the base `ppolyf_u` this repo's other
  resistors use. Marking its body identically to a base-flavor body would
  have gotten it recognised as a *base* `ppolyf_u` device at the wrong
  (350 Ω/□ vs. its real ~1000 Ω/□) sheet resistance — silently wrong, worse
  than the then-current documented-short status quo. `generate.py`'s
  `ResItem.high_rho` flag (set from the schematic's own `Device.model`) made
  `draw_res` mark `RPU`'s body with `Resistor` (62/0) instead of `Pplus` —
  one of `ResistorDevice.excludes` for the base flavor — so it extracted as
  a short, exactly as klayout-tools#299 said it should at the time.
  **Superseded by [gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78)**:
  klayout-tools#299 is now resolved and the deck carries a `ppolyf_u_1k`
  entry recognised by `SAB` + `Resistor` (62/0) + `RES_MK` — deliberately
  *not* `Pplus` — so `generate.py` now also marks `RPU`'s body with `RES_MK`,
  and it extracts as a real `ppolyf_u_1k` device at 1000 Ω/□ instead of a
  short.

**Current coverage**, from `<record-id>` `20260802-172927-741c4ae`'s
committed report (regenerated by #75, whose trim-strap fix merged four
formerly-distinct ladder nodes — `net_count` was 97 before it):

```
extracted devices: 163 {'bjt': 16, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65}
net_count        : 93   (pin_count 4: vdd, vref, vss, vsubs)
warning          : 213 poly-layer shapes not part of any recognised
                   nfet/pfet gate touch contact at 2+ separate points (the
                   resistor-body signature) and carry no resistor-marker
                   layer at all; ... -- see docs/cli/extract.md's 'Known
                   limitation: unmodelled device geometry'.
```

- **Resistor (`ppolyf_u`) — 65/65 recognised**: `core.R1`, `core.R2`, and all
  63 trim-ladder segments, each a real `DeviceExtractorResistorWithBulk`
  device with drawn `L`/`W` (`r_ohm`/`l_um`/`w_um`/`area_um2` params).
  `startup.RPU` is *not* among them at this record-id — see above — and was
  at the time exactly the kind of shape the remaining warning (213 shapes,
  down from the pre-#73 finding's 279) flags: real drawn poly this deck had
  no device extractor for. **As of #78, `RPU` also extracts as a real
  `ppolyf_u_1k` device** (device count 164, not 163 — see "RESOLVED (#78)"
  below); this block's counts are the #73/#75-era snapshot, kept verbatim.
- **MiM capacitor (`cap_mim_2f0_m4m5_noshield`) — 1/1 recognised**: the
  compensation cap now extracts as a real `DeviceExtractorCapacitor` device
  instead of absent/disconnected plates.
- **Bipolar (`bjt`) — 16/16, unchanged by #73** (already recognised before
  this issue; see the original finding below).
- **MOS — 81/81, unchanged by #73.**

## RESOLVED (#75): `layout/lvs`'s connectivity check is solid end-to-end again

Between #73 and #75, `layout/lvs/run_lvs.py` reported `mismatch`. That was
**not** caused by #73's layout changes: `layout/lvs/make_reference.py`'s
reference netlist was mechanically derived, under #62/PR#66, on the premise
that `klt`'s gf180mcu extraction deck "recognises only `nfet`/`pfet`" — a
premise already false by the time #73 reinstalled `klt` (bipolar
recognition, klayout-tools#223, was merged upstream), and reproducibly false
against the then-`main` GDS *before* any of #73's own changes (`mismatch`,
27 entries, 81/81 devices matched, 18/23 nets — the 16 recognised `bjt`
devices/nets the MOS-only reference didn't model). #73's own fix made the
same structural gap larger (65 `ppolyf_u` + 1 MiM cap more), but did not
create it.

[gf180-bandgap#75](https://github.com/2AMLogic/gf180-bandgap/issues/75)
closed it by teaching `make_reference.py` to emit `ppolyf_u`/`bjt`/MiM-cap
reference cards from the same `plan.py` rows/items `generate.py` draws from
(mirroring how it already did this for MOS), including the device
*parameters* `klt lvs` compares — `R` and `AE` are predicted from the drawn
marker geometry, which is what the extractor measures. Current verdict:

```
extracted devices: 163 {'bjt': 16, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65}
lvs status       : match
devices matched  : 163 / 163
nets matched     : 93 / 93
```

Two things worth carrying forward from that work:

- **A real layout/schematic deviation surfaced and was fixed**: the drawn
  trim strap shorted ladder chain node 0 to node 31 in one span, where the
  schematic's `S0..S4` (closed at `DRAWN_TRIM_CODE = 32`) short nodes 0, 1,
  3, 7, 15 and 31 together. Electrically identical, topologically
  different — invisible while every resistor was a short. `generate.py` now
  derives its straps from the schematic's own `RS*` expressions
  (`plan.trim_strap_spans`).
- **`startup.RPU` still collapsed to a short on both sides at this
  record-id**, by design — see "RESOLVED (#73)" above. klayout-tools#299 has
  since been resolved upstream; see "RESOLVED (#78)" below for the current
  status.

**#17's remaining scope is therefore no longer blocked on `layout/lvs`.**
One thing to settle before running #12/#13 against the extracted netlist:
the compensation MIM capacitor still extracts with two *floating* plates,
because `klt extract`'s recognised cap plates are their own connectivity
nodes, never joined to the ordinary metal stack, regardless of how the
layout routes them (`decks.CapacitorDevice`'s "Known limitation" — see
`layout/README.md`). Since
[gf180-bandgap#77](https://github.com/2AMLogic/gf180-bandgap/issues/77) the
layout *does* draw a real via stack from both plates down to the Metal1
`vdd`/`fb` routing (`generate._mim_cap`), but that connection is still
invisible to `klt extract` for the reason above, so a parasitic-extraction
consumer working from this netlist directly still needs to be told the
compensation cap is present but disconnected — a stability/phase-margin
re-run against a netlist with no compensation cap in the loop is not
representative.

> **Fully resolved (2026-08-03, #88).**
> [`klayout-tools#314`](https://github.com/2AMLogic/klayout-tools/issues/314)
> joined a recognised plate to the ordinary metal stack, and it worked for
> the **bottom** plate first: its drawn Via3 lands inside the `Metal4` plate
> box, so that terminal extracts on the real `vdd` net (which is why
> `net_count` dropped from 94 to 93, and why `make_reference.py` step 9
> models it as `vdd`). The **top** plate stayed isolated for a while
> afterward, but for a layout reason rather than a tool one — its Via4
> landed on a `FuseTop` routing tab held outside `CAP_MK`, a workaround for
> `klayout-tools#364` (a DRM-legal on-plate via read as a `vdd`/`fb` short).
> `mk_extracted_dut.py`'s BA4 used to back-annotate it to `fb`, and
> `verify_mim_routing.py` proved that annotation was the drawn circuit
> rather than an assumption. **klayout-tools#364/PR #368 fixed the
> connectivity-graph gap, and
> [gf180-bandgap#88](https://github.com/2AMLogic/gf180-bandgap/issues/88)
> redrew the contact against it**: the `fb` up-hop `Via4` now lands directly
> inside the recognised top plate, `net_count` dropped again (93 → 92), the
> top plate extracts on the real `fb` net with no back-annotation, and BA4
> is deleted. The compensation cap **is** in the loop in every #17 record,
> now for real rather than via an asserted back-annotation.

**RESOLVED (#88): the `fb` plate's own contact geometry is now DRM-legal.**
The paragraph below is kept verbatim as the append-only record of a real,
already-shipped manufacturability finding — a consumer of an earlier
extracted-netlist record built from a pre-#88 GDS should still read it as an
accurate description of *that* record's geometry:

- The FuseTop routing tab that used to carry `fb` off the top plate extended
  0.8 µm past the `Metal4` bottom plate's edge with **zero** bottom-plate
  overlap there, against `MIMTM.3`'s 0.6 µm minimum bottom-plate overlap of
  the top plate (transcribed in the deck as `mim.enclosing.fusetop.1`, and
  honoured by `MIM_PLATE_INSET` on the other three edges of the same box).
- The `Via4` that hopped up onto that tab had **zero** `Metal4` overlap,
  against `MIMTM.2`'s 0.4 µm minimum bottom-plate overlap of `Via4`.
  `MIMTM.2` is not transcribed into the deck at all, so that half had no
  rule to be checked by.
- **The block as drawn was therefore not manufacturable at that contact.**
  It was not a "standard MiM-cap top-plate routing technique"; it was a
  workaround for `klt extract`'s dielectric-blind connectivity graph, which
  read the DRM-legal contact (a `Via4` landing inside the bottom-plate
  footprint) as a `vdd`/`fb` short.
- **`klt drc`'s `clean` verdict on that geometry was a false negative, not a
  passing check.** `mim.enclosing.fusetop.1` maps onto KLayout's
  `Region.enclosing_check`, which reports nothing when a shape lies *entirely*
  outside the enclosing layer — filed upstream as
  [klayout-tools#318](https://github.com/2AMLogic/klayout-tools/issues/318).

**Current geometry (#88).** The `fb` up-hop `Via4` now lands directly inside
the recognised top plate, well inside the `Metal4` bottom-plate footprint —
DRM-legal per `MIMTM.2` by a wide margin, not merely the 0.4 µm minimum (see
the asserts in `generate._mim_cap`) — and `klt drc` reports `status: clean`,
`violation_count: 0`. Full geometry trace: `generate._mim_cap`'s docstring
and `layout/README.md` § "Findings and escalations".

## RESOLVED (#78): `startup.RPU` now extracts as a real `ppolyf_u_1k` device

klayout-tools#299 — the gap noted in "RESOLVED (#73)" above, that the deck's
`resistors` list covered only the base `ppolyf_u` sheet-rho flavor — is now
resolved upstream: the deck carries a `ppolyf_u_1k` `ResistorDevice` entry
(`SAB (49/0)` + `Resistor (62/0)` + `RES_MK (110/5)`, deliberately *not*
`Pplus`, at 1000 Ω/□) alongside the base entry.
[gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78) took
it up: `generate.py`'s `draw_res` now also draws `RES_MK` on a `high_rho`
body (it already drew `SAB`/`Resistor`), so `startup.RPU` matches the new
recogniser instead of being marked with only `Resistor` as an *exclude* for
the base one. `netlist_model.EXTRACTED_RES_MODELS` gained `ppolyf_u_1k` so
`reduce_nets` stops merging `RPU`'s two terminal nets, and
`layout/lvs/make_reference.py` predicts its `R` from the drawn marker area
at 1000 Ω/□ (`plan.PPOLYF_U_1K_SHEET_RHO`) instead of collapsing it to a
short. Current verdict:

```
extracted devices: 164 {'bjt': 16, 'cap_mim_2f0_m4m5_noshield': 1,
                        'nfet': 34, 'pfet': 47, 'ppolyf_u': 65,
                        'ppolyf_u_1k': 1}
lvs status       : match
devices matched  : 164 / 164
nets matched     : 94 / 94
```

`net_count` moved from 93 to 94: `RPU`'s `vdd`/`det` terminals are no longer
union-found into one net now that `ppolyf_u_1k` is in
`EXTRACTED_RES_MODELS`. No other device class's counts moved — this change
is additive/local to `startup.RPU`.

## Original finding (#17): this layout did not draw the marker geometry the new recognisers require

Re-running `klt extract --parasitics --deck gf180mcu --pdk gf180mcuD` against
the `bandgap_top.gds` committed at the time (see #62/PR#66) confirmed:

- **Bipolar: works.** 16 real `bjt` devices recognised with drawn
  `AE`/`PE`/etc. — a genuine improvement over the MOS-only extraction #62
  used.
- **Resistor: 0 recognised.** `klt extract` warns: "279 poly-layer shapes
  not part of any recognised nfet/pfet gate touch contact at 2+ separate
  points (the resistor-body signature) ... absorbed into ordinary
  interconnect as an unintended short." Every discrete `ppolyf_u` resistor
  (`core.R1`, `core.R2`, all 63 trim-ladder segments) extracts as a 0 ohm
  short between its two heads.
- **MiM capacitor: 0 recognised.** The compensation cap's plates extract as
  disconnected/absent rather than a device.

This was **not** a klayout-tools defect — the deck's resistor/capacitor
recognisers require specific marker geometry, and `layout/bandgap_top/generate.py`
did not draw all of it:

- `klayout_tools.decks.gf180mcu.EXTRACTION_DECK.resistors`'s `ppolyf_u`
  entry recognises `Poly2 & RES_MK (110/5)`, requiring `Pplus (31/0)` +
  `SAB (49/0)` over that same segment. `generate.py`'s `draw_res`/`draw_trim`
  **already drew `Pplus`** around every resistor body (correctly modeling
  the unsalicided p+ poly device) but drew neither `RES_MK` nor `SAB`.
  Without the `RES_MK` marker specifically, the deck had no segment to
  intersect against `Pplus`/`SAB` at all, so the resistor bodies of
  `core.R1`, `core.R2` and all 63 trim-ladder segments extracted as ordinary
  Poly2 interconnect — i.e. a dead short between each resistor's two heads.
- `klayout_tools.decks.gf180mcu.EXTRACTION_DECK.capacitors` requires **both**
  `CAP_MK (117/5)` and `MIM_L_MK (117/10)` on the MiM cap's `FuseTop` top
  plate. `generate.py`'s `_mim_cap` drew `MIM_L_MK` already but not
  `CAP_MK`, so the compensation cap's plates extracted as
  unconnected/absent rather than a recognised device.
- Separately: `startup.RPU` uses the `ppolyf_u_1k` high-sheet-rho poly
  resistor variant (schematic: `XRPU det vdd vss ppolyf_u_1k ...`), which
  has **no** entry in `EXTRACTION_DECK.resistors` at all (only the base
  `ppolyf_u` flavor is wired) — even after the marker-layer fix, `RPU` still
  extracts as a short, by design (see "RESOLVED (#73)" above). This half
  **is** a klayout-tools coverage gap (the deck's resistor list covers one
  sheet-rho flavor per PDK, not the full family), reported upstream
  generically (see "Friction filed" below).

**Why this blocked a meaningful full-PVT extracted-netlist re-run**: a
bandgap reference's entire PTAT/CTAT combination, feedback network and trim
mechanism is resistor-mediated. A netlist where `R1`/`R2`/the trim ladder
are literal 0 Ω shorts and the compensation cap is absent does not
represent the real drawn circuit — it is a different, almost certainly
non-functional topology. Running #12's spec-line suite against it would not
be a valid post-layout re-verification (it would demonstrate that a
short-circuited bandgap fails, which is not an informative result), and
reporting such numbers under `Netlist provenance: extracted` would violate
CLAUDE.md's "no claim without a testbench" / no-relaxation rule by
presenting a non-representative circuit's results as this block's
post-layout behavior.

**#17's remaining scope (full #12 suite re-run over the full PVT matrix,
#13 Monte Carlo re-run, the schematic-vs-extracted delta summary, and the
#11 startup re-check) was blocked on this** — first on the marker-layer gap
#73 closed, then on the `layout/lvs` reference staleness #75 closed. See
"RESOLVED (#75)" above for the current status and the one remaining
representativeness caveat (the unwired compensation cap, #77).

## Known additional fidelity gaps

Worth recording now so a future increment does not re-discover them:

- The `X`-card MOS binding (`--pdk`) does not carry `AS`/`AD`/`PS`/`PD`
  (source/drain area/perimeter) — a real fidelity loss relative to the
  schematic, which #65/PR#72 specifically corrected `nf` for so those
  junction capacitances would be geometry-accurate. `klt extract`'s own
  docs mark this as a deliberate scope limit of the PDK-model-binding
  feature (schematic-equivalent, no-parasitics scope), not a bug.
- Now that `RES_MK`/`SAB`/`CAP_MK` are drawn (#73), `DeviceExtractorResistor`
  still emits a **linear, value-only** `R` card (`R = L/W · sheet_rho`, a
  single ohms figure) — not a call into the real `ppolyf_u` SPICE subcircuit
  the schematic uses, which carries its own temperature-coefficient and
  mismatch modeling. This is a real fidelity gap the extracted netlist
  carries going forward; not something this repo's layout can fix, since
  the extraction engine's resistor recognizer is defined upstream to write
  a bare `R` card.
- The extracted top-level pin list is `vdd vref vss vsubs` (four pins) vs.
  `sim/dut/README.md`'s three-pin (`vdd`, `vss`, `vref`) convention — a
  `sim/dut`-ready wrapper will need to tie `vsubs` to `vss` (or expose it)
  before this netlist can be handed to `sim/run_corners.py --dut`.
  **Handled**: `mk_extracted_dut.py`'s T9 emits the three-pin form and BA1
  aliases `vsubs` to `vss`.
- **The extracted parasitic `R` is a shunt element, so it affects nothing.**
  `--parasitics` emits, per net, `R <net> <net>__par` in series with
  `C <net>__par <substrate>`. The capacitance loads the net correctly (its
  isolating pole sits above 100 MHz for every net here), but the resistance's
  only other terminal is that capacitor's plate: it carries no DC current and
  sits between no driver and any receiver. IR drop on the supply/ground/bias
  distribution and series resistance in a matched path — the two mechanisms a
  precision-analog post-layout re-run is usually reached for — are therefore
  structurally absent from this netlist, not merely approximated. There is
  also no net-to-net coupling capacitance. Filed generically upstream as
  [`klayout-tools#338`](https://github.com/2AMLogic/klayout-tools/issues/338).
  Practical consequence for #17's records: every DC-domain result
  (`vref`, `tc_ppm`, `linereg`, `iq`) is a **device-geometry** delta against
  the schematic, not a parasitic-resistance one; the extracted capacitance is
  what moves the AC-domain results.

## Friction filed (klayout-tools tracker)

Per CLAUDE.md's friction protocol (tool gap, described generically, no
design specifics):

- **gf180mcu extraction deck's resistor device-class list covers only one
  sheet-rho flavor of the PDK's poly-resistor family** — a PDK commonly
  ships several selectable sheet-rho variants of the same physical poly
  resistor (distinguished by an additional exclude-style marker layer), and
  the curated deck wires device recognition for only the base flavor, so
  any drawn instance of another flavor still collapses to a short even once
  the base flavor's marker geometry is drawn correctly. Filed as
  [`klayout-tools#299`](https://github.com/2AMLogic/klayout-tools/issues/299)
  — **resolved upstream** 2026-08-02; this repo took up the new entry for
  `startup.RPU` in
  [gf180-bandgap#78](https://github.com/2AMLogic/gf180-bandgap/issues/78)
  (see "RESOLVED (#78)" above).
- **A bipolar recogniser keyed on a bare diffusion layer counts a
  base-contact ring as a second emitter** — a curated deck that models no
  implant layers could not tell the base-contact ring of a standard vertical
  bipolar unit cell apart from the emitter it surrounds, so every drawn unit
  extracted as two devices of the bipolar class sharing one base net. Filed
  as [`klayout-tools#302`](https://github.com/2AMLogic/klayout-tools/issues/302)
  (found while closing #75) — **resolved upstream** 2026-08-02 by
  [`klayout-tools#304`](https://github.com/2AMLogic/klayout-tools/issues/304),
  which excludes the n+ implant layer from the emitter region so the tie ring
  is dropped and each drawn unit extracts as one device.
  **This repo has taken it up**
  ([gf180-bandgap#84](https://github.com/2AMLogic/gf180-bandgap/issues/84)):
  `make_reference.py`'s step 8 now emits one `bjt` card per drawn PNP unit,
  and the committed LVS evidence was regenerated against the current
  (post-#304) deck (`gf180mcu.py` content hash `sha256:90a7f0ef…`) — 8 `bjt`,
  156/156 devices, `status: match` — see `layout/README.md` § "Findings and
  escalations".
- **First-order lumped-RC parasitics put the whole net resistance in series
  with the net's own ground capacitance** — so the extracted R sits between no
  driver and any receiver, carries no DC current, and cannot represent IR drop
  or series resistance in a matched path; net-to-net coupling capacitance is
  not extracted either. Filed as
  [`klayout-tools#338`](https://github.com/2AMLogic/klayout-tools/issues/338)
  (found by #17). Open.
- **A PDK model binding that covers MOS only** — `--pdk` rebinds recognised
  MOS devices to the PDK's own device subcircuits (which is what makes an
  extracted MOS meaningful), but a recognised resistor, bipolar or capacitor
  still emits a bare primitive card carrying the deck's class token, so it is
  not callable and loses the PDK model's temperature/voltage coefficients,
  edge-bias corrections and per-instance mismatch hooks. Every consuming block
  repository has to write the same geometry-to-model rebinding layer by hand
  (here: `mk_extracted_dut.py`'s T3–T7). Filed as
  [`klayout-tools#339`](https://github.com/2AMLogic/klayout-tools/issues/339)
  (found by #17). Open.
