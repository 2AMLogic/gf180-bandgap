# layout/erc — structural power delivery (T1 item 11)

The evidence half of **T1 item 11, "Power delivery (structural)"**
(klayout-tools `docs/design-evidence-tiers.md`) for `bandgap_top`
([#192](https://github.com/2AMLogic/gf180-bandgap/issues/192)). This
directory holds the `klt erc` specs that read the committed GDS, the
committed reports those specs produce, and the one script that regenerates
all of it.

`bandgap_top` is an **analog** block, so item 11's *Analog* column applies:
the `klt erc` supply read below, **plus** item 4's own LVS report having
actually carried the supply nets in its `net_correspondence`. The *Digital*
column's `klt place-and-route` `power.pdn` / `power.tapcell_master` /
`power_connectivity` requirements do not apply — there is no P&R step, no
standard-cell library and no PDN in this flow.

```
layout/erc/
  README.md                            this file
  run_erc.py                           regenerates every report below
  test_run_erc.py                      unit tests for run_erc.py's verdict helpers
  erc-supply-spec.json                 the supply + ties read    <- SIGNOFF
  erc-supply-spec.negative-control.json  proves the net rules fire <- control
  erc-tie-spec.known-gap.json          reproduces klayout-tools#2169 <- control
  erc-tie-spec.pinned.json             the ties[] derivation probe (#441) <- probe
  erc-tie-spec.negative-control.json   proves the tie rule fires <- control
  reports/bandgap_top/
    <record-id>.erc.{json,txt}                    the signoff report
    <record-id>.erc-negative-control.{json,txt}   the net control's report
    <record-id>.erc-tie-known-gap.{json,txt}      the #2169 reproduction
    <record-id>.erc-tie-pinned.{json,txt}         known-gap.json re-run on the pin
    <record-id>.erc-tie-classed.{json,txt}        pinned.json on the pin
    <record-id>.erc-tie-negative-control.{json,txt} the tie control's report
```

Each spec's own `_comment` block justifies every `stackup` entry, every
`label_layer`, every `vias[]` bridge and every `nets[]` declaration inline —
that is the primary documentation, not this file.

## Reproducing

```bash
# 1. the item-11 signoff read (exits nonzero if the verdict regresses)
python3 layout/erc/run_erc.py

# 2. the net negative control -- a CLEAN result here is the regression
python3 layout/erc/run_erc.py \
    --spec layout/erc/erc-supply-spec.negative-control.json \
    --suffix erc-negative-control --expect findings

# 3. the klayout-tools#2169 reproduction -- NOT signoff evidence
python3 layout/erc/run_erc.py \
    --spec layout/erc/erc-tie-spec.known-gap.json \
    --suffix erc-tie-known-gap --expect findings

# 4. the pinned-klt tie probe -- records what the PIN computes (#441).
#    Historical: this is the run that derived the ties[] the signoff
#    spec now carries. See "The tie negative control" below.
python3 layout/erc/run_erc.py \
    --spec layout/erc/erc-tie-spec.pinned.json \
    --suffix erc-tie-classed --expect any

# 5. the tie negative control -- a CLEAN result here is the regression
python3 layout/erc/run_erc.py \
    --spec layout/erc/erc-tie-spec.negative-control.json \
    --suffix erc-tie-negative-control --expect findings

# 6. run_erc.py's own unit tests
python3 -m unittest discover -s layout/erc -t layout/erc -v
```

Steps 1-4 call whatever `klt` is first on `PATH`, and the version matters:
every report above was made at the pin in `signoff/klt-pin.txt`. If the host
`klt` is not that version, put the pin first on `PATH` from a throwaway
environment rather than changing the host tool:

```bash
uv venv /tmp/klt-pin && VIRTUAL_ENV=/tmp/klt-pin uv pip install \
    "klayout-tools==$(grep -v '^#' signoff/klt-pin.txt | tr -d '[:space:]')"
export PATH=/tmp/klt-pin/bin:$PATH
```

Confirm it took: every report's own `provenance.klt_version` records the
version that actually ran.

Reports are **append-only** (`CLAUDE.md`; `layout/README.md`, "Reports are
append-only evidence"): every run mints a new `<YYYYMMDD>-<HHMMSS>-<sha>`
record id and never overwrites an existing one.

## The run

`klt 0.8.0` (klayout-tools PyPI pin in `signoff/klt-pin.txt`), `klayout
0.30.13`, gf180mcu layer numbers from `gf180mcuD` (`open_pdks
f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`). Input
`layout/bandgap_top/bandgap_top.gds`,
`sha256:e2004ef6f909d8391078f2aaa48bcddd0af378aff08fd307ebd625d25a16660a`
— pinned in every report's own `provenance.input.content_hash` and
re-checked against the file on disk by `run_erc.py` on every run. (The
September runs below read the pre-2026-11-17 GDS,
`sha256:3e1af18e…dcc1ae0`; the #441 probe runs read
`sha256:97944732…edf055c` — each report's own provenance says which.)

| Read | Report | Result |
| --- | --- | --- |
| Supply + ties (signoff) | `.erc.json` | 10 gate nets, `erc_finding_count: 0`, **zero** `erc.unconnected_net`, **zero** `erc.supply_short`, **zero** `erc.missing_tie`, all three tie checks **computed** (`erc_coverage.skipped` empty) |
| Net negative control | `.erc-negative-control.json` | 1 finding — `erc.unconnected_net` on the bogus `no_such_rail`, and *only* on it |
| `#2169` reproduction | `.erc-tie-known-gap.json` | design collapses to 1 gate net, 3 **false** shorts (kept as history; the collapse does not recur on the pin — see `*.erc-tie-pinned.*`) |
| Tie probe (`#441`, historical) | `.erc-tie-classed.json` | same three ties, zero findings, on the 2026-11-13 GDS |
| Tie negative control | `.erc-tie-negative-control.json` | 10 findings — `erc.missing_tie` for **every** tap class (`nwell_tap_pmos` 1×, `nwell_base_pnp` 8×, `psub_tap` 1×), and nothing else |

### Reading the supply verdict

**Zero findings *is* the verdict, not an absence of one.**
`erc.unconnected_net` fires when a declared net matches **zero** islands
(nothing carries that label) **or more than one** (the rail is split into
pieces that never touch); `erc.supply_short` fires when two
`"kind": "supply"` nets resolve to the same island. Declaring `vdd` and
`vss` and getting neither finding is therefore exactly *"each supply
resolves to exactly one electrical island, and the two are distinct"* —
which is what item 11 asks for.

**The negative control is what makes that zero readable.** A zero is
produced identically by "the rule ran and found nothing" and by "the rule
never ran" (a dropped `nets[]` section, a `label_layer` that resolves to
nothing, a schema change). `erc-supply-spec.negative-control.json` is the
signoff spec's `nets[]` half plus one rail that does not exist, and it
comes back with exactly one `erc.unconnected_net` naming that rail and
nothing else. The rules fire; the zero means what it says. (`ties[]` has
its own control — see "The tie negative control" below.)

### Why the report's `status` is `not_checked`, and why that is not a failure

Item 11 grades the supply-net finding rules above — explicitly **not** the
report's overall `status` (`design-evidence-tiers.md`, item 11: *"Those are
the rules this item grades, not the report's overall `status`"*; an antenna
verdict or a floating-gate finding in the same report is a real defect but
is not this item's subject, klayout-tools#1994).

On gf180mcu that distinction is load-bearing rather than theoretical:
`klt erc --pdk` ships an antenna-ratio limit table for **sky130 only**, so
no antenna level on a gf180mcu layout is ever graded, and the shared
coverage contract (klayout-tools#2134) therefore refuses to call the run a
pass — `status: "not_checked"`, exit `4`, on *every* gf180mcu `klt erc`
run regardless of how clean its connectivity is. `run_erc.py` accepts exit
`4` alongside `0` and `3` for exactly this reason and gates on the finding
rules instead. Filed upstream as a tool gap:
**klayout-tools#2179** (closed 2026-09-20).

### The LVS half of item 11

Item 11's Analog column additionally requires item 4's own LVS report to
have carried the supplies, *"so the supplies were part of the compare
rather than absent from it: every declared supply net appears in that
report's `net_correspondence` paired to a reference-side net"*. It does —
the report the manifest cites for both items,
`layout/lvs/reports/bandgap_top/20261117-162205-92475fa.lvs.json`:

| `net_correspondence` | layout | reference | `pin` |
| --- | --- | --- | --- |
| supply | `vdd` | `VDD` | `true` |
| supply | `vss` | `VSS` | `true` |
| output | `vref` | `VREF` | `true` |

with `status: "match"` over 82/82 nets, 164/164 devices and 3/3 pins. The
reference is a SPICE netlist (`layout/lvs/bandgap_top.ref.spice`), which
satisfies this clause by construction — it is the signal-only
`gate-level-verilog` reference that does not, which is why the Digital
column asks for `power_connectivity` instead. Read it as a *participation
test, not a second opinion* (klayout-tools issue #2495): the pairing is
implied by any `match` and destroyed by any `mismatch`, and it is gated on
item 4 passing — which it is, at the same pinned GDS hash.

## What is and is NOT verified here

**`erc.missing_tie` IS computed by the signoff report, and it is zero from
checks that actually ran.** That is the state since gf180-bandgap#526
(2026-11-20): `erc-supply-spec.json` carries the `ties[]` declaration,
`erc_coverage.skipped` is empty in the committed report, and the item-11
citation in `signoff/block-manifest.json` rests on exactly that report.
Before #526 the spec declared no `ties[]` at all, which made the rule's
zero an absence of evidence rather than a verdict; before #441
(2026-11-13) the tool could not have computed it honestly at all.

### How the ties got here (the #441 derivation)

Both historical reasons for omitting `ties[]` are gone at the pin,
measured (gf180-bandgap#441, `klt 0.8.0` / `klayout 0.30.13`):

1. **klayout-tools#2169 is fixed.** It used to collapse the whole design
   into one electrical island on any `ties[]` entry and report **false**
   shorts (`gate_count` 10 → 1; `vdd`, `vss` and `vref` all mutually
   shorted). `erc-tie-spec.known-gap.json` is that reproduction, kept
   byte-for-byte as history. Re-running **that same file unchanged** on the
   pin — report `*.erc-tie-pinned.*` — gives `gate_count` **10**, each
   declared net on **exactly one** island, and **zero** `erc.supply_short`.
   The collapse does not recur.
2. **A p-substrate tie can be expressed.** `ties[].well_layer` needs a
   *drawn* well/tub layer, and this block sits in the native p-substrate
   with no `LVPWELL` (204/0) anywhere in the GDS. `klt 0.8.0`'s
   `ties[].well_complement_of` (klayout-tools#3750) names the substrate as
   *the top-cell extent minus* `Nwell`, which follows the layout instead of
   going stale.

Two corrections the declaration needed, both discovered by measurement and
both the tool's documented schema working as designed:

- **The tap must be narrowed** — `tap_layer: "22/0"` (`Comp`) plus
  `tap_requires`: `Comp ∩ Nplus` for an n-well tap, `Comp ∩ Pplus` for a
  substrate tap. gf180mcu has no dedicated tap layer; declaring the implant
  alone (`tap_layer: "32/0"`) narrows nothing and klt 0.8.0 correctly
  refuses it as `erc_coverage.skipped` reason `degenerate_tap_declaration`.
- **`Nwell` carries two bias classes here, and one `ties[]` entry claims
  every shape on its well layer.** Declaring a single n-well tie to `vdd`
  reports **8** `erc.missing_tie` findings, and all 8 are the
  vertical-PNP base islands (`PnpItem` in `plan.py`, each a 10.40 µm
  square, every one declaring `base_net: "vss"` — the `Nwell` *is* the PNP
  base terminal, so tying it to `vdd` would be the defect). Splitting the
  classes on the `DRC_BJT` (127/5) marker `draw_pnp` already draws —
  `well_excludes` for the PMOS band, `well_requires` for the PNP bases —
  is what klt's own rule asks for ("each bias class is declared as its own
  `ties[]` entry with its own `net`").

`erc-tie-spec.pinned.json` is that derivation frozen as a probe, with its
own committed reports (`*.erc-tie-classed.*`). **#526 merged its `ties[]`
into `erc-supply-spec.json` rather than making the probe file the signoff
spec** — the smaller diff, since every consumer (run_erc.py's default,
the manifest's history, this README) already names the supply spec — which
is the choice the curator asked to have recorded here. The probe file
stays unchanged as history.

### The tie negative control

A zero `erc.missing_tie` is only meaningful if the rule that produces it
can fire. `erc-tie-spec.negative-control.json` is the signoff spec
verbatim with each of the three `ties[].net` values flipped (`vdd` ↔
`vss`); the taps drawn in this layout strap each well class to its real
rail, so asking for the other rail must report every class untied. The
committed report does exactly that — 10 findings, all
`erc.missing_tie`, naming each class in its `layer` field:

| class | net asked for | findings |
| --- | --- | --- |
| `nwell_tap_pmos` | `vss` (flipped) | 1 — the one PMOS-band well region |
| `nwell_base_pnp` | `vdd` (flipped) | 8 — one per vertical-PNP base island |
| `psub_tap` | `vdd` (flipped) | 1 — the one substrate region |

and nothing else: zero `erc.supply_short`, zero `erc.unconnected_net` —
the supply-island verdicts hold while the tie question fails, which is
what keeps the two halves of the item separately legible. If a class ever
stops firing in this control, the signoff report's zero for that class has
stopped meaning anything and the item-11 claim must be withdrawn until
explained. The unconnected-net control
(`erc-supply-spec.negative-control.json`) keeps proving the supply rules
fire; it covers the `nets[]` half the same way this one covers `ties[]`.

### What is still NOT verified here

1. **The citation is against the pre-DR-0007 layout.** The signoff report
   reads the committed GDS (`sha256:e2004ef6…16660a`), *not* the layout
   [#204](https://github.com/2AMLogic/gf180-bandgap/issues/204) will
   regenerate. The manifest pins the GDS hash, so the moment #204 lands,
   `klt signoff` renders the citation `stale_evidence` and item 11 drops
   back to `unmet` until the report is re-minted — the re-run that
   [#358](https://github.com/2AMLogic/gf180-bandgap/issues/358) keeps.
2. **`psub_tap` is weaker evidence than the other two classes.** The
   report itself says so, listing it under
   `erc_coverage.checked_by_well_assertion` and in the graded citation's
   `power_delivery.ties_checked_by_well_assertion`: its region is
   *derived* by complement (top-cell extent minus `Nwell`) rather than
   read off drawn geometry. That is a computed check with a falsifiable
   region — the negative control fires it like any other class — but it
   is not the same as a drawn tub layer, and should be stated that way
   rather than flattened into "the substrate is verified".
3. **The spec's own layer coverage is partial, disclosed here rather than
   graded.** `erc_coverage.layers_in_stream_without_declaration` in the
   cited report names six drawn layers the spec declares nowhere:
   `49/0` (`SAB`), `62/0` (`RESISTOR_MK`), `75/0` (`FuseTop`), `110/5`
   (`RES_MK`), `117/5` (`CAP_MK`), `117/10` (`MIM_MK`) — the salicide,
   resistor and capacitor recognition markers, plus the MIM top plate.
   None is a routing level (the supply lives on Metal1–Metal3, all
   declared; every layer the `ties[]` and stackup name is counted as
   declared), so the connectivity model is not silently narrower than the
   supply's routing — but a future edit that *moves* supply routing onto
   an undeclared level would grade clean from a narrower model, so this
   list travels with the claim (klayout-tools issue #2389 makes it
   claimant-enforced, exactly like item 3's deck-scope disclosure).
4. **What the LVS half is not.** Item 11's LVS clause is a *participation
   test* on item 4's own report (the supplies appear, paired, in
   `net_correspondence` of a `match`) — not an independent tie verdict and
   not a substitute for `erc.missing_tie`. The MOS-body question is item
   4's own subject (`body_verification` in the cited envelope).

## Friction filed

| Upstream | Status | What |
| --- | --- | --- |
| [klayout-tools#2169](https://github.com/2AMLogic/klayout-tools/issues/2169) | closed 2026-09-20; **fix confirmed here 2026-11-13** | `ties[]` collapses a design to one island (false `erc.supply_short`). Reproduced here on a hand-drawn analog layout — see `erc-tie-spec.known-gap.json`. Re-running that spec unchanged on `klt 0.8.0` no longer collapses (`*.erc-tie-pinned.*`, gf180-bandgap#441). |
| [klayout-tools#2179](https://github.com/2AMLogic/klayout-tools/issues/2179) | closed 2026-09-20 | `klt erc --pdk` has no antenna-ratio table outside sky130, so every non-sky130 run is `status: "not_checked"` / exit 4 even when its connectivity rules ran clean. |

Per `CLAUDE.md`'s friction protocol, both were filed against the tool as
generic tool gaps, with no design-specific detail from this repo.

**No new upstream issue was filed for #441**, because neither trigger
survived measurement: the `ties[]` collapse does not recur at the pin, and a
native p-substrate tie *is* expressible there
(`well_complement_of`). The two corrections
`erc-tie-spec.pinned.json` needed — narrowing the tap with `tap_requires`,
and splitting `Nwell`'s two bias classes into separate entries — are the
tool's documented schema working as designed, each with its own named
`erc_coverage` skip reason pointing at the fix, not tool gaps. `klt 0.8.0`
refusing an unfalsifiable declaration (`degenerate_tap_declaration`) instead
of returning a clean pass is the behaviour this repo's friction reports
asked for.
