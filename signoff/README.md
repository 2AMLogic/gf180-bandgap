# T1 signoff — the graded verdict of record

This block's position on the klayout-tools **design-evidence ladder** is not
prose in this file. It is
[`block-manifest.json`](block-manifest.json) — what this block claims, and the
evidence envelope backing each claim — graded mechanically by `klt signoff
--manifest`, with the graded output committed under
[`reports/`](reports/) as append-only evidence.

Read the newest record in `reports/` for the current per-item verdict. Nothing
in this file restates it, on purpose: a hand-maintained checkbox list goes
stale the moment either the evidence or the checklist moves, and both move.
(The checklist itself grew an eleventh item — power delivery (structural) — on
2026-09-17, 2AMLogic/klayout-tools#2025, which invalidated every hand-read T1
claim in the fleet at a stroke.)

```bash
bash signoff/regenerate.sh --dry-run      # render the report, write nothing
bash signoff/regenerate.sh                # mint a new record under reports/
python3 signoff/check_signoff.py          # offline: pins + record consistency
python3 signoff/check_signoff.py --run-klt  # + re-grade and diff vs the record
```

`klt signoff --manifest` exits **3** when the block is not yet T1 and **0**
only at full T1 — both mean the report rendered. Exit 1/2 mean no report was
produced. The scripts above encode that distinction; a caller of `klt` that
treats 3 as failure cannot run on a block that is not already finished.

- **Checklist** (the item skeleton, parsed at run time):
  `klayout-tools/docs/design-evidence-tiers.md`
- **Grader contract** (manifest shape, reasons, what is and is not graded):
  `klayout-tools/docs/cli/signoff.md`
- **klt revision this repo grades against**: pinned in
  [`klt-pin.txt`](klt-pin.txt) — floating `main` would make the committed
  record disagree with a re-run for reasons unrelated to this block's evidence.

## Block kind: `analog`

Confirmed against the block, not assumed: every device in `design/*.sch` is
hand-captured analog (bandgap core, error amplifier, startup, trim network),
the netlist is derived from those schematics rather than synthesized, and
`layout/bandgap_top/` is a generated hand-floorplanned GDS, not P&R output.
There is no RTL, no gate-level netlist, no partition boundary to declare — so
this is a single-kind `analog` manifest, graded against the Analog column of
the per-kind items (1, 2, 5, 7 and 11), not a `mixed-signal` one.

Consequence worth stating: for an analog partition, **item 7 accepts a `klt
pex` report and nothing else**. A clean DRC or a pre-layout corner sweep
renders `wrong_kind`, not `met`.

## What the manifest cites, and what it deliberately does not

Two items are cited today (3 and 4). Everything else is uncited and renders
`no_evidence` — an accurate machine-readable statement that no `klt`-gradable
check backs that claim in this repo yet. That is the honest result, not a
placeholder: citing a passing envelope that does not actually support an item
would turn a row green while proving nothing.

**Items 1, 2, 9 and 10 are uncited on purpose.** They have no `klt` verb
behind them, so the grader scores them on "some passing envelope was cited at
all", never on topical relevance — citing the DRC report for "Repo hygiene"
would render `MET` and the tool would have no basis to object. This repo does
have the artifacts those items describe (schematics + regenerated netlists,
a committed generated GDS, 16 manifest-driven testbenches with a documented
cold-start invocation and a pinned PDK, a README/license/CI), but asserting
them through an unrelated citation would make the record say something it did
not check. `klayout-tools/docs/cli/signoff.md` recommends exactly this
default.

**Items 5, 6 and 8 are uncited because this repo's evidence is not in a
gradable shape.** `sim/` holds append-only Markdown records (per
`sim/README.md`), not `klt sim` / `klt yield` JSON envelopes, and the
characterization summaries under `sim/suite/summaries/` are Markdown too —
item 8 would need the opt-in `generic` envelope wrapper (`"kind": "generic"`,
the only item that kind may satisfy) built around one. Separately, items 5/6
have a substantive gap of their own: the extracted-provenance records
currently FAIL the output-reference and TC rows, attributed to #87 (see
`sim/postlayout-delta.md`), so those rows would not grade `met` even once the
evidence is in envelope form.

**Item 7 has no citation because this repo has produced no `klt pex` report.**
There is a post-layout delta write-up (`sim/postlayout-delta.md`,
`sim/postlayout_delta.py`) driving extracted-netlist re-runs, but it is not
the artifact item 7 accepts. Because no `pex` report exists, there is also no
`body_bias` block to read — so this claim makes **no statement** about whether
post-layout numbers were measured on a properly body-biased extracted netlist.
Absence of that field never means "every device body was biased"; here it
means the question has not been asked with the tool that answers it.

**Item 11 (power delivery, structural) has no citation**, though — unlike
items 5/6/7/8 above — this repo *does* have a `klt erc` supply spec and a
`klt erc` report (`layout/erc/erc-supply-spec.json`,
`layout/erc/reports/bandgap_top/`, established by
[#192](https://github.com/2AMLogic/gf180-bandgap/issues/192)). The reason for
the non-citation is `erc.missing_tie`: it is a required rule for this item
and it is **not computed** on this block's run, because declaring the
well/substrate `ties[]` the rule needs collapses the layout into a single
false-shorted electrical island (klayout-tools#2169). A citation that omits a
required rule is not a partial `met`; `klt signoff` would have no basis to
distinguish "computed and passing" from "never asked", so the item stays
uncited rather than asserting a verdict the grader cannot actually check.
Full detail — the negative control that proves the supply-short/unconnected
rules do fire, and exactly what the drawn taps and their LVS coverage do and
do not stand in for — is in
[`layout/erc/README.md`](../layout/erc/README.md), "What is NOT verified
here". **Read that file's own text for the current state, not this
paragraph**, since a hand-restated summary is exactly the kind of copy this
repo has already had to retire once (see "How this is kept from rotting"
below).

## Disclosures that travel with the claim (claimant-enforced, not graded)

### Item 3 — DRC coverage

`klt signoff` grades item 3 on `status: "clean"` alone. A `met` verdict is
**not** evidence that the deck's gaps were disclosed, so they are disclosed
here, quoted from the cited envelope's own `coverage` block
(`layout/drc/reports/bandgap_top/20260817-125327-972f6d5.drc.json`, and
reported verbatim in the committed record's `citation.coverage`):

- `layers_in_stream_without_rules` (8) — layers drawn in this stream the deck
  has no rule for: `31/0`, `32/0`, `34/10`, `49/0`, `62/0`, `110/5`, `117/5`,
  `117/10`.
- `rules_skipped` (3) — rules the deck carries that this run did not evaluate:
  `metaltop.space.1`, `metaltop.width.1`, `pad.enclosing.metal5.1`.
- `deck_scope` (10) — the DRM chapters this deck transcribes at all: 7.4
  Nwell, 7.5 Comp, 7.7 Poly2, 7.12 Contact, 7.13 Metaln, 7.14 Vian, 7.15
  MetalTop, 9.1 Bond Pad, 10.4.2 MIM Option B, 10.7 DRC_BJT Mark Layer.

"Clean" means clean *inside that scope*. Every DRM chapter not listed above
was not checked by this run.

### Item 4 — why a `match` renders `unmet`

The cited envelope
(`layout/lvs/reports/bandgap_top/20260819-070132-1e66285.lvs.json`) reports
`status: "match"`, engine `klayout`, 92/92 nets and 164/164 devices — and the
manifest still renders item 4 `unmet` with `reason: "stale_evidence"`. That is
correct, and it is the reason this manifest exists:

- The envelope was produced by `klt` 0.2.0, which left `provenance.input`
  `null`. `klt signoff`'s staleness gate reads exactly that field, so a pinned
  `content_hash` cannot be matched against anything and the citation cannot be
  proven fresh **by the grader**.
- The run *was* in fact made against the current committed layout — the same
  envelope's `environment.layout_sha256` is
  `3e1af18ef32dd461172a9d9d00a62ade323725de9a0f90ded08161237dcc1ae0`, which is
  today's `layout/bandgap_top/bandgap_top.gds`. But a field the grader does not
  read is not evidence the grader can use, and dropping the pin to force a
  `met` would assert freshness no tool checked. The pin stays; the row stays
  `unmet` until the LVS is re-run with a `klt` new enough to record
  `provenance.input` (klayout-tools#1969).
- Independent of freshness: the second engine on that same run
  (`…-1e66285.lvs-netgen.json`) reports `status: "mismatch"` — 2
  `device.body_unverified` warnings (the deck-synthesized substrate/well nets,
  a standing deck-coverage caveat klayout carries too) plus 1
  `device.property` entry whose per-parameter detail netgen's output did not
  parse into. So item 4's "a second, independent engine's concurring verdict"
  strengthening does **not** hold today.
- Both engines' `body_verification` is `unchecked`, which is not `verified`.

### Item 5 — full corner verification: what is actually still open

`no_evidence` here is uncited-for-shape (above), not "nothing has been run".
Against the spec ratified 2026-07-31
(`spec/decision-records/0003-target-spec-ratification.md`, the table in
`README.md`): the latest suite summary,
`sim/suite/summaries/20260816-142719-1ca1c95.md`, reads **6/6 claimed spec
lines PASS** across 81/81/27/81 PVT corners plus startup. What is left open,
disclosed here because no envelope carries it: three spec rows are still
`TBD` by ratification itself (PSRR load condition, output-noise threshold,
the load row — amendments A4/A6/A7 from #35, carried through verbatim rather
than invented), and the summary's own text says one line is still pending a
bench. An output-noise bench has since landed
(`sim/output-noise/records/`, #189) but no re-run suite summary carries it
yet — so "6/6 claimed lines pass" is accurate as written and is not the same
statement as "the ratified table's full row set passes".

### Item 6 — Monte Carlo evidence exists, in a form the grader can't read

`sim/mc-untrimmed/records/` carries an N≥300 local-mismatch distribution of
`vref` per temperature, combined with (not instead of) process corners — see
`sim/suite/summaries/`, "Output reference (untrimmed accuracy, both legs)".
That is the substance item 6 asks for. What is missing is the artifact
shape: there is no `klt yield` envelope (seed, sample count, deterministic
negative control, Cpk/sigma-to-spec, `docs/cli/signoff.md`'s expected shape
for this item), so this is a hand-assembled record rather than the
machine-checkable one `klt signoff` grades on. A claim reading "item 6 met"
from this repo's evidence today would be reading substance the tool has not
verified the shape of.

### Item 7 — post-layout verification: a real regression, not just a missing artifact

Two separate reasons this item is `unmet`, and only one of them is a missing
artifact. **No `klt pex` report exists** — the delta below is built from
`klt extract`'s netlist via `sim/postlayout_delta.py`, not the `klt pex`
JSON envelope item 7 requires, so there is no `body_bias` block and this
claim makes no statement about whether the post-layout numbers were measured
on a properly body-biased extracted netlist. **Separately, and the part that
would not go away even with a `klt pex` report**: the extracted-netlist
re-run already shows a measured regression against the schematic-level
result, on the exact rows item 7 exists to catch. From
[`sim/postlayout-delta.md`](../sim/postlayout-delta.md) (full per-corner
table there; these are the worst-case deltas):

| Spec row | Ratified limit | Schematic | Extracted | Delta |
|---|---|---|---|---|
| Output reference (`vref >= 1.176 V`) | 1.176 V | 1.18142 V (PASS) | 1.2219 V (**FAIL**) | +3.43% |
| Output reference (`vref <= 1.224 V`) | 1.224 V | 1.20185 V (PASS) | 1.25187 V (**FAIL**) | +4.16% |
| Temp coefficient (`tc_ppm <= 50 ppm/°C`) | 50 ppm/°C | 29.8447 ppm/°C (PASS) | 90.2239 ppm/°C (**FAIL**) | +202.31% |

Five rows FAIL post-layout that pass pre-layout in total (the two supply-swept
`vref` bounds move the same way as the standalone `vref` bounds above; see the
linked file for the full nine-row table and every corner). This is attributed
to the drawn PNP array's 4.03 effective dVBE ratio versus the schematic's
3.63 — a design-level gap between the drawn devices and the schematic's
assumption, not a layout drafting error or an extraction defect — tracked in
[#87](https://github.com/2AMLogic/gf180-bandgap/issues/87), currently
blocked on a spec decision record. **This is the one item on this page that
is a design defect, not a tooling or evidence-shape gap**, and it is the
reason tapeout is not scheduled (see the status paragraph in `README.md` and
[#94](https://github.com/2AMLogic/gf180-bandgap/issues/94)).

### Item 8 — characterization report exists, just not `klt`-native

`sim/suite/summaries/<record-id>.md` is the aggregated per-spec-row artifact
this item asks for, naming the evidence record behind every verdict. It is a
committed Markdown report rather than a `klt`-native JSON envelope — which
item 8 explicitly permits: it is the one T1 item the opt-in `"kind":
"generic"` envelope may satisfy (`klayout-tools/docs/cli/signoff.md`,
"Generic evidence"). No such envelope has been built around it yet, which is
why this item is `no_evidence` rather than `met`; wrapping the existing
summary would close it without any new measurement. Its currency is bounded
by item 5's gap above — a wrapped envelope would only be as current as the
suite summary it cites.

## How this is kept from rotting

`klt signoff` compares a manifest pin against the *cited envelope's own*
recorded input hash. It never opens the repo artifact that hash is supposed to
be the hash **of** — so a pin can go stale in a way the grader structurally
cannot see: the layout is regenerated, the envelope and its pin still agree
with each other, and the pair now describes a revision the repo no longer
contains. [`pinned-inputs.json`](pinned-inputs.json) names the artifact behind
every pin and `check_signoff.py` re-hashes it, which closes that gap.

CI runs both halves (`.github/workflows/ci.yml`):

| Check | Where | Needs |
|---|---|---|
| Manifest shape, pins vs. committed artifacts, record consistency | `lint` job, via `.github/scripts/lint.sh` | python3 only |
| Re-grade with the pinned `klt` and diff against the committed record | `signoff` job | network (installs `klt` at `klt-pin.txt`'s revision) |

So a manifest citing an artifact that has since changed, a record that no
longer matches what `klt` would say today, and a mis-keyed evidence entry that
`klt` would silently ignore all fail a PR instead of rotting quietly.

## Fleet roll-up

`block` is required in this manifest (klt itself calls it optional) because it
is how this block's row is identified in the fleet roll-up, 2AMLogic/2am#956,
which consumes this exact file via `klt signoff --fleet`.
