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

**Item 11 (power delivery, structural) has no citation** — this repo has no
`klt erc` supply spec and no `klt erc` report. Tracked in
[#192](https://github.com/2AMLogic/gf180-bandgap/issues/192).

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
