# Gap to T1 — `bandgap_top`

Where this repo stands against the **T1 ("sim-validated") checklist** in
klayout-tools `docs/design-evidence-tiers.md`, item by item, with the
committed artifact each row rests on.

- **Block kind**: `analog`. The checklist's items 1, 2, 5, 7 and 11 are
  kind-dependent; only the *Analog* column applies to this block. Items 3,
  4, 6, 8, 9 and 10 are kind-independent.
- **Read the tier doc's own item text, not this table, for what an item
  requires.** This file records *this repo's position*; it is not a second
  copy of the checklist and must not be used as one.
- **Assessed against**: klayout-tools `docs/design-evidence-tiers.md` as of
  `f2f1d14e` (2026-09-20), the revision that carries **eleven** items. The
  eleventh — *Power delivery (structural)* — was added 2026-09-17 as
  klayout-tools#2025. Every "gap to T1" read taken in this repo before that
  date was taken against a ten-item checklist that no longer exists.
- **Verdicts here are claimant-asserted, not tool-graded.** No `klt signoff
  --manifest` run backs this table yet; each row cites the artifact a
  reviewer should open.

## The table

| # | Item | Status | Evidence / what is missing |
|---|------|--------|----------------------------|
| 1 | Design sources (*Analog*) | **met** | `design/*.sch` + `design/*.sym` (xschem) and the derived `design/netlist/*.spice`. `sim/dut/bandgap_top.spice` is regenerated from the netlist and its staleness is a CI check (`.github/scripts/lint.sh` step 5/5). |
| 2 | Layout (*Analog*) | **met** | `layout/bandgap_top/bandgap_top.gds`, drawn by `layout/bandgap_top/generate.py` byte-for-byte deterministically from the committed netlist (`layout/README.md`, "How the layout is built"). |
| 3 | DRC clean | **met, with the coverage gaps disclosed** | `layout/drc/reports/bandgap_top/` — `status: clean`, `violation_count: 0`. The disclosure item 3 demands is quoted from the report's own `coverage` block in `layout/README.md`, "The gf180mcu DRC deck: coverage": 10 `deck_scope` chapters, 8 `layers_in_stream_without_rules`, 3 `rules_skipped`. A clean verdict is bounded by that scope. |
| 4 | LVS clean | **met on `status`; `power_connectivity` absent, body terminals unverified** | `layout/lvs/reports/bandgap_top/` — `status: "match"`, 92/92 nets, 164/164 devices, 4/4 pins, engine `klayout`, cross-checked by an independent `netgen` run. `power_connectivity` is `null` (not `"mismatch"`), which satisfies the item's literal wording. **But** the same report carries two `device.body_unverified` warnings: 42 NMOS bodies compared against the deck-synthesized `vsubs` net and 47 PMOS bodies against an anonymous deck-synthesized well net. `body_verification` is `null`, i.e. not `"verified"` — which the tier doc's item 7 note calls out as the upstream condition to read. |
| 5 | Full corner verification vs a ratified spec (*Analog*) | **partial** | Spec ratified 2026-07-31 (`spec/decision-records/0003-*`, table in `README.md`). Latest suite summary `sim/suite/summaries/20260816-142719-1ca1c95.md`: **6/6 claimed spec lines PASS** over 81/81/27/81 PVT corners, plus startup. Gaps: three spec rows are still `TBD` by ratification (PSRR load condition, output-noise threshold, load row) and the summary itself says *"1 line still pending a bench"*. An output-noise bench has since landed (`sim/output-noise/records/`, #189) but no re-run suite summary carries it yet. |
| 6 | Statistical claims carry Monte Carlo evidence | **met for the rows that are statistical** | `sim/mc-untrimmed/records/` — N≥300 local-mismatch distribution of `vref` per temperature, combined with (not instead of) process corners in `sim/suite/summaries/`, "Output reference (untrimmed accuracy, both legs)". No `klt yield` envelope exists, so this is a hand-assembled record rather than the machine-checkable artifact the item names. |
| 7 | Post-layout verification (*Analog*) | **NOT met — a real regression, not a missing artifact** | `sim/postlayout-delta.md` pairs schematic and extracted runs per spec row. Five rows **FAIL** post-layout that pass pre-layout: both `vref` bounds (+3.4% / +4.2%), `tc_ppm` (+202%), and both supply-swept `vref` bounds. No `klt pex` report exists either — the delta is built from `klt extract`'s netlist, so the item's own required evidence kind is absent as well as failing. |
| 8 | Characterization report | **met in substance** | `sim/suite/summaries/<record-id>.md` is the aggregated per-spec-row artifact, naming the evidence record behind every verdict. It is a committed Markdown report, not a `klt`-native envelope — which item 8 explicitly permits (it is the one item a `"kind": "generic"` envelope may satisfy). Currency is bounded by item 5's gap above. |
| 9 | Testbenches shipped | **met** | Every bench ships its own `sim/<slug>/testbench/`, `corners/` and `netlist-snapshots/` beside its records, with `sim/README.md`'s cold-start invocation. The PDK variant is pinned in `sim/pdk.json` (`gf180mcuD`) and every record stamps the exact `open_pdks` revision it ran against; `.github/workflows/sim-pdk.yml` fetches a pinned PDK and runs the harness self-test in CI. |
| 10 | Repo hygiene | **met** | `README.md` (what the block is, the ratified spec table, reproduction), `LICENSE`, and CI (`.github/workflows/ci.yml`) that keeps the harness, the evidence-record schema and the append-only rule valid (`sim/check_records.py`). |
| 11 | **Power delivery (structural)** (*Analog*) | **met on the supply read; `erc.missing_tie` NOT COMPUTED** | `layout/erc/` — see below. |

## Item 11 in full

Added to the checklist 2026-09-17 (klayout-tools#2025); established in this
repo by [#192](https://github.com/2AMLogic/gf180-bandgap/issues/192). Item
11's *Analog* column has two halves, and this repo satisfies them
asymmetrically.

**The `klt erc` supply read — met.**
`layout/erc/reports/bandgap_top/<record-id>.erc.json`, against
`layout/erc/erc-supply-spec.json`, with
`provenance.input.content_hash` pinning the committed
`layout/bandgap_top/bandgap_top.gds`:

- `erc.unconnected_net`: **0**. `vdd` and `vss` each resolve to exactly one
  electrical island — that rule fires on zero islands *and* on more than
  one, so zero is the positive verdict.
- `erc.supply_short`: **0**. The two supplies are distinct islands.
- A negative control (`erc-supply-spec.negative-control.json`) confirms the
  rules actually fire, so those zeros are readable as verdicts rather than
  as silence.

Not graded on the report's overall `status`, per the item's own text. That
status is `"not_checked"` (exit 4) on **every** gf180mcu `klt erc` run,
because `klt erc --pdk` ships an antenna table for sky130 only — filed as
klayout-tools#2179.

**The LVS half — met.** Item 11's Analog column also requires item 4's own
LVS report to have carried the supplies in `net_correspondence`. It does:
`vdd`↔`VDD` and `vss`↔`VSS`, both `pin: true`, in a SPICE-reference compare
that returns `status: "match"`.

**`erc.missing_tie` — NOT COMPUTED, and nothing in this flow replaces it.**
`erc-supply-spec.json` declares no `ties[]`, because declaring one collapses
this layout into a single electrical island and reports false shorts
(klayout-tools#2169, reproduced here by `erc-tie-spec.known-gap.json`:
`gate_count` 10 → 1, three false shorts). Per `klt erc`'s own contract,
omitting `ties[]` means the rule is **never computed** — its zero in the
committed report is an absence of evidence, not evidence of absence.

What stands in for it, and how far that reaches, is spelled out in
`layout/erc/README.md`, "What is NOT verified here". In short: the taps are
drawn and generated (`plan.py`'s four `TapItem` bars plus a `vss` guard
ring), their Metal1 straps provably sit on the supply islands the ERC read
resolved, and the tap geometry is DRC-clean — but the LVS report does
**not** stand in, because its own `device.body_unverified` warnings say the
bulk terminals were compared against deck-synthesized nets rather than nets
traced from the drawn taps. **No tool in this flow currently returns a
well/substrate-tie verdict for this block.**

## Summary of what is actually blocking T1

| Blocker | Item | Kind |
|---|---|---|
| Post-layout `vref` / `tc_ppm` regression (5 failing spec rows) | 7 | **Design defect** — must be fixed, not documented away |
| No `klt pex` report at all | 7 | Missing artifact |
| Three spec rows still `TBD`; no suite summary carrying the output-noise bench | 5 | Missing artifact |
| `erc.missing_tie` unsatisfiable (klayout-tools#2169) | 11 | **Tool gap** — cannot be closed in this repo |
| Device body terminals unverified by LVS | 4 (and 7's caveat) | Tool/deck coverage |
| `status: "not_checked"` on every gf180mcu ERC run (klayout-tools#2179) | 11 | Tool gap — does not block the item, but blocks machine grading |

Items 1, 2, 3, 6, 8, 9 and 10 are met; 11 is met on everything it can
currently be met on. **Item 7 is the one substantive design blocker.**

## Maintaining this file

- When klayout-tools adds or renumbers a checklist item, update the
  "Assessed against" line **and** re-read every row — an item count change
  invalidates prior "gap to T1" reads wholesale, which is exactly what
  happened when item 11 landed.
- A row's status may only be raised by pointing at a committed artifact.
  `CLAUDE.md`: no claim without a testbench, and the ratified spec is not
  relaxed to make a result pass.
