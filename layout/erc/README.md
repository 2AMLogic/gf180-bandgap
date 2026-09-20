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
  erc-supply-spec.json                 the supply read           <- SIGNOFF
  erc-supply-spec.negative-control.json  proves the rules fire   <- control
  erc-tie-spec.known-gap.json          reproduces klayout-tools#2169 <- control
  reports/bandgap_top/
    <record-id>.erc.{json,txt}                    the signoff report
    <record-id>.erc-negative-control.{json,txt}   the control's report
    <record-id>.erc-tie-known-gap.{json,txt}      the #2169 reproduction
```

Each spec's own `_comment` block justifies every `stackup` entry, every
`label_layer`, every `vias[]` bridge and every `nets[]` declaration inline —
that is the primary documentation, not this file.

## Reproducing

```bash
# 1. the item-11 signoff read (exits nonzero if the verdict regresses)
python3 layout/erc/run_erc.py

# 2. the negative control -- a CLEAN result here is the regression
python3 layout/erc/run_erc.py \
    --spec layout/erc/erc-supply-spec.negative-control.json \
    --suffix erc-negative-control --expect findings

# 3. the klayout-tools#2169 reproduction -- NOT signoff evidence
python3 layout/erc/run_erc.py \
    --spec layout/erc/erc-tie-spec.known-gap.json \
    --suffix erc-tie-known-gap --expect findings

# 4. run_erc.py's own unit tests
python3 -m unittest discover -s layout/erc -t layout/erc -v
```

Reports are **append-only** (`CLAUDE.md`; `layout/README.md`, "Reports are
append-only evidence"): every run mints a new `<YYYYMMDD>-<HHMMSS>-<sha>`
record id and never overwrites an existing one.

## The run

`klt 0.5.0+gd5893304afc2` (klayout-tools `d589330`), `klayout 0.30.12`,
gf180mcu layer numbers from `gf180mcuD` (`open_pdks
f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`). Input
`layout/bandgap_top/bandgap_top.gds`,
`sha256:3e1af18ef32dd461172a9d9d00a62ade323725de9a0f90ded08161237dcc1ae0`
— pinned in every report's own `provenance.input.content_hash` and
re-checked against the file on disk by `run_erc.py` on every run.

| Read | Report | Result |
| --- | --- | --- |
| Supply read (signoff) | `.erc.json` | 10 gate nets, `erc_finding_count: 0`, **zero** `erc.unconnected_net`, **zero** `erc.supply_short` |
| Negative control | `.erc-negative-control.json` | 1 finding — `erc.unconnected_net` on the bogus `no_such_rail`, and *only* on it |
| `#2169` reproduction | `.erc-tie-known-gap.json` | design collapses to 1 gate net, 3 **false** shorts |

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
signoff spec verbatim plus one rail that does not exist, and it comes back
with exactly one `erc.unconnected_net` naming that rail and nothing else.
The rules fire; the zero means what it says.

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
**klayout-tools#2179**.

### The LVS half of item 11

Item 11's Analog column additionally requires item 4's own LVS report to
have carried the supplies, *"so the supplies were part of the compare
rather than absent from it: every declared supply net appears in that
report's `net_correspondence` paired to a reference-side net"*. It does —
`layout/lvs/reports/bandgap_top/20260819-070132-1e66285.lvs.json`:

| `net_correspondence` | layout | reference | `pin` |
| --- | --- | --- | --- |
| supply | `vdd` | `VDD` | `true` |
| supply | `vss` | `VSS` | `true` |
| substrate | `vsubs` | `VSUBS` | `true` |
| output | `vref` | `VREF` | `true` |

with `status: "match"` over 92/92 nets, 164/164 devices and 4/4 pins. The
reference is a SPICE netlist (`layout/lvs/bandgap_top.ref.spice`), which
satisfies this clause by construction — it is the signal-only
`gate-level-verilog` reference that does not, which is why the Digital
column asks for `power_connectivity` instead.

## What is NOT verified here: `erc.missing_tie`

**`erc.missing_tie` is NOT COMPUTED by the signoff report.**
`erc-supply-spec.json` deliberately declares no `ties[]`, and klayout-tools
`docs/cli/erc.md` is explicit that omitting the section means the rule is
never computed. Its zero count in that report is an **absence of evidence,
not evidence of absence**, and must not be cited as a well-tie verdict.

Two independent reasons it is omitted, both measured:

1. **klayout-tools#2169** — declaring any `ties[]` entry collapses the
   whole design into one electrical island and reports **false** shorts.
   `erc-tie-spec.known-gap.json` + its committed report are the
   reproduction on this block: `gate_count` 10 → 1, and all three declared
   nets (`vdd`, `vss`, `vref`) report as shorted to each other. The gap was
   first isolated in `gf180-drone-fc`'s FRICTION F-034 on a routed
   *standard-cell* design; this block is hand-drawn analog with no standard
   cells and no PDN, and collapses the same way — so the gap is not
   specific to a P&R'd cell array.
2. **A p-substrate tie cannot be expressed at all**, separately from
   #2169: `ties[].well_layer` needs a *drawn* well/tub layer, and this
   block sits in the native p-substrate with no `LVPWELL` (204/0) anywhere
   in the GDS. Even a fixed #2169 would only ever grade the n-well half.

### What stands in for it, and how far that reaches

Nothing here is a substitute *verdict*. These are the admissible facts:

1. **The taps are drawn, and are generated rather than hand-placed.**
   `layout/bandgap_top/plan.py` declares four explicit `TapItem` bars — two
   `psub` taps (`ptap.nbias`, `ptap.ampn`, Comp under Pplus) strapped to
   `vss`, and two `nwell` taps (`ntap.pbias`, `ntap.top`, Comp under Nplus
   inside the PMOS band's Nwell) strapped to `vdd` — plus a p+ guard ring
   around the whole block tied to `vss` (`layout/floorplan.md` §9).
   `generate.py` draws each as Comp + implant + a Contact row + a Metal1
   bar, byte-for-byte deterministically.
2. **Those tap straps are on the supply islands the ERC read resolved.**
   The Metal1 bar of every tap is part of the same connectivity graph this
   directory's signoff report traces, and that report resolves `vdd` and
   `vss` to exactly one island each. So the tap *straps* provably reach
   their declared supply.
3. **DRC is clean** against the current gf180mcu deck
   (`layout/drc/reports/bandgap_top/`), which covers the Nwell / Comp /
   Pplus / Nplus / Contact rules the taps are drawn under — the tap
   geometry is DRM-legal.

**And the honest limit, which is the important part:** the LVS report does
**not** stand in for `erc.missing_tie` here, and this repo must not claim
it does. That same report carries two `device.body_unverified` warnings
saying so in its own words —

> *"42 NMOS device body terminal(s) were compared against the 'vsubs'
> deck-synthesized substrate net, not a real schematic net — no drawn
> substrate-tap geometry resolved these device(s)' body terminal to a real
> net"*
>
> *"47 PMOS device body terminal(s) were compared against an anonymous,
> deck-synthesized well net, not a real schematic net — this deck has no
> distinct well-tap layer"*

— i.e. the LVS compare matched bulk terminals against nets the extraction
*synthesized*, not against nets it traced from the drawn taps. The
`vsubs`↔`VSUBS` pin correspondence in the table above is a pin-list match,
not a tie verdict.

So: **no tool in this flow currently returns a well/substrate-tie verdict
for this block.** Items (1)–(3) say the taps exist, are legal, and are
strapped onto the right rails; none of them says every well and every
substrate region *reaches* one. That gap closes when klayout-tools#2169 is
fixed and `ties[]` becomes usable — and, for the substrate half, only if
`ties[]` grows a way to name an undrawn native substrate.

## Friction filed

| Upstream | What |
| --- | --- |
| [klayout-tools#2169](https://github.com/2AMLogic/klayout-tools/issues/2169) | `ties[]` collapses a design to one island (false `erc.supply_short`). Reproduced here on a hand-drawn analog layout — see `erc-tie-spec.known-gap.json`. |
| [klayout-tools#2179](https://github.com/2AMLogic/klayout-tools/issues/2179) | `klt erc --pdk` has no antenna-ratio table outside sky130, so every non-sky130 run is `status: "not_checked"` / exit 4 even when its connectivity rules ran clean. |

Per `CLAUDE.md`'s friction protocol, both are filed against the tool as
generic tool gaps, with no design-specific detail from this repo.
