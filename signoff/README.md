# T1 signoff — the graded verdict of record

This block's position on the klayout-tools **design-evidence ladder** is not
prose in this file. It is
[`block-manifest.json`](block-manifest.json) — what this block claims, and the
evidence envelope backing each claim — graded mechanically by `klt signoff
--manifest`, with the graded output committed under
[`reports/`](reports/) as append-only evidence. The PR gate enforces that:
`sim/harness/evidence_lint.py` (run by `.github/scripts/lint.sh`, strict in
CI) rejects any modification, deletion or rename/move of a report already
present at the merge base; new reports are fine. The manifest, pins and this
file are mutable and outside that rule.

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
  `check_signoff.py --run-klt` resolves that revision through `uvx` (as
  `regenerate.sh` does) and ignores any `klt` on `PATH`; it fails clearly if
  `uvx` or the pin is missing. `KLT_SIGNOFF_CMD` (e.g. `klt`) is the explicit
  override — whoever sets it owns revision selection. CI sets it after
  installing `klt` at the pin.

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

Four items are cited today (3, 4, 9 and 10). Everything else is uncited and
renders `no_evidence` — an accurate machine-readable statement that no
`klt`-gradable check backs that claim in this repo yet. That is the honest
result, not a placeholder: citing a passing envelope that does not actually
support an item would turn a row green while proving nothing.

**Items 9 and 10 are cited through `klt signoff --attest`.** They have no
dedicated `klt` verb, so the grader's artifact-anchored generic envelope
(klayout-tools#2718) is the only way to grade them, and the envelope is
**tool-produced** rather than hand-written
(klayout-tools#2844): `klt` runs the checks a versioned inventory declares and
derives the envelope's `status` from them.

| Item | Inventory | Envelope (cited in the manifest) | Checks it runs |
|---|---|---|---|
| 9 Testbenches shipped | [`inventories/item9.json`](inventories/item9.json) | [`attestations/item9.json`](attestations/item9.json) | every file under `sim/*/testbench/` exists; the PDK-free cold start (`sim/run_corners.py --list`, failing on any `!!` manifest-load marker) exits 0; PDK and tool pins are declared |
| 10 Repo hygiene | [`inventories/item10.json`](inventories/item10.json) | [`attestations/item10.json`](attestations/item10.json) | README, LICENSE and the CI workflow exist; `.github/scripts/lint.sh` and the `signoff/tests` unit tests exit 0 |

The cold start is deliberately the list/manifest-load form: a full
simulation needs ngspice and the PDK, which the attest producer runs on a bare
runner, and appends evidence records. It proves every manifest loads, **not**
that the testbenches simulate — that is items 5/6, not this one. Never loosen
a command to make an attestation pass; an unmet check is recorded as unmet.

To refresh after changing an inventoried file or an inventory:

```bash
klt signoff --attest 9  --inventory signoff/inventories/item9.json  -o signoff/attestations/item9.json
klt signoff --attest 10 --inventory signoff/inventories/item10.json -o signoff/attestations/item10.json
# if an inventory itself changed, first put its new sha256 into block-manifest.json
# (the envelope's provenance.input.content_hash) -- the lint audit in item 10 runs
# check_signoff.py, which fails on a stale pin -- then run the two commands above.
python3 signoff/check_signoff.py
bash signoff/regenerate.sh
```

The envelope pins the *inventory*; the files the inventory lists are covered
by the per-file hashes recorded inside the envelope. `check_signoff.py`
re-hashes those in the offline lint job (and requires item 9's inventory to
list every tracked testbench file), and `--run-klt` re-runs
`klt signoff --attest N --inventory … --check` in the CI `signoff` job, which
re-executes the commands and fails on any drifted file or flipped outcome.

**Items 1 and 2 are uncited on purpose, and wait for
[#204](https://github.com/2AMLogic/gf180-bandgap/issues/204)** (DR-0007 phase
B), which regenerates the schematic, netlist and GDS they bind to. Attesting
them now would pin artifacts that are about to change. Item 1 will then use
`klt signoff --attest 1` the same way; item 2 is **not** attestable
(`--attest` accepts only 1, 9 and 10), so it needs an artifact-anchored
envelope of the other kinds `klt signoff` accepts for the committed GDS.

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
(`layout/drc/reports/bandgap_top/20261028-065229-f32fe48.drc.json`, and
reported verbatim in the committed record's `citation.coverage`):

- `layers_in_stream_without_rules` (1) — layers drawn in this stream the deck
  has no rule for: `34/10`.
- `rules_skipped` (32) — rules the deck carries that this run did not
  evaluate. The same envelope's `coverage.inapplicable` gives a reason for
  every one of the 32: 30 `no_applicable_geometry` and 2
  `inapplicable_empty_checked_region` (`comp.tap_distance.nwell.mv.1`,
  `comp.tap_distance.psub.mv.1`). They are the medium-voltage, ESD,
  guard-ring, dual-gate, fuse, deep-nwell, pad and MetalTop rules — this
  block draws none of that geometry. `coverage.skipped` is empty and
  `coverage.unknown` is empty, so no rule was skipped for an unexplained
  reason. The three rules this file used to list (`metaltop.space.1`,
  `metaltop.width.1`, `pad.enclosing.metal5.1`) are still among the 32.
- `deck_scope` (16) — the DRM chapters this deck transcribes at all: 7.4
  Nwell, 7.5 Comp, 7.7 Poly2, 7.8 Nplus, 7.9 Pplus, 7.12 Contact, 7.13
  Metaln, 7.14 Vian, 7.15 MetalTop, 9.1 Bond Pad, 10.4.2 MIM Option B, 10.7
  DRC_BJT Mark Layer, ESD, GR, OFFGRID, SB.

"Clean" means clean *inside that scope*. Every DRM chapter not listed above
was not checked by this run. The envelope is explicit about the size of that
gap in its own terms: `coverage.unmodeled_rules` names **97** DRM rule IDs
that this deck does not transcribe at all, and so no run against it can ever
evaluate. Those 97 are exactly ten groups: the medium-voltage `*_MV`
variants (35), the via `V[1-4].*` enclosure variants (16), `MT30.*` (9), the
metal-slotting `MSLOT.*` set (8), `ESD.*` (8), `DV.1/3/6/7/8/9` (6), `GR.*`
(5), the metal `M[1-5].2b` variants (5), `MT.2b`/`MT.3`/`MT.4` (3) and the
contact pair `CO.6a`/`CO.6b` (2). `violation_count` is 0 over the 82 rules
in `coverage.rules_checked`.

### Item 4 — what the cited LVS run did and did not compare

The cited envelope
(`layout/lvs/reports/bandgap_top/20261028-065214-f32fe48.lvs.json`) reports
`status: "match"`, engine `klayout` (klt 0.8.0, KLayout 0.30.12), with
`counts` of 82/82 nets, 164/164 devices and 3/3 pins. Its
`provenance.input.content_hash` is populated and equals the manifest's pin for
this item, so the grader can prove the citation fresh — the freshness gate
that the August run failed (history below). The newest record,
`signoff/reports/20261028-065240-f32fe48.signoff.json`, carries
`input_verified: true` and `check_status: "match"` for this citation. Per the
rule at the top of this file, that record, not this paragraph, is the verdict.

What the `match` does and does not assert, read off the same envelope:

- **No second engine ran.** `environment.netgen_binary` is `null`, and no
  `*.lvs-netgen.json` exists for this record id — `layout/lvs/reports/bandgap_top/`
  carries netgen reports only for the `20260804-*` runs and for
  `20260819-070132-1e66285`. So item 4's "a second, independent engine's
  concurring verdict" strengthening is **not** part of this citation. The
  `match` is klayout's alone.
- **`body_verification` reads `verified`.** The block in full:
  `{"status": "verified", "reason": null, "device_classes": [],
  "device_count": 0, "findings": [], "finding_count": 0}`. Read it against the
  grader contract rather than at face value: in `klt lvs`'s response schema
  (klayout-tools `docs/cli/lvs.md` at the pinned 0.8.0, "The same condition,
  machine-checkable"), `device_classes` and `device_count` count the devices
  whose bodies came out **unverified**, and are specified to be empty and `0`
  for a `verified` verdict. So `device_count: 0` is not "no devices were
  looked at" — `"verified"` is defined there as *a deck was given and every
  MOS body terminal in the layout's top circuit resolved to a real
  drawn/derived net*. There are 89 MOS bodies for that to be a statement
  about: `20261028-065214-f32fe48.extract.json`'s `device_counts` reads 42
  `nfet` and 47 `pfet` (plus 8 `bjt`, 66 poly resistors and 1 MIM cap, which
  this field does not cover — it is a MOS-body check). The committed request
  (`20261028-065214-f32fe48.lvs-request.json`) is the one-request
  `layout.file` + `layout.deck` form, not the two-step `layout.netlist` form
  whose `body_verification` verdict that same document tells callers not to
  rely on (klayout-tools#3177).
- **A `match` still leaves device sizing uncompared.** `mismatch_count` is
  **9** against `error_count: 0`: all nine are `severity: "warning"`, which by
  contract never moves `status`. Three are `device.geometry_not_compared` —
  KLayout declares a resistor class's `L`/`W`/`A`/`P` and a capacitor class's
  `A`/`P` *secondary*, so `NetlistComparer` compared only `R` (for the 65
  `ppolyf_u` and 1 `ppolyf_u_1k`) and `C` (for the 1
  `cap_mim_2f0_m4m5_noshield`). **The drawn geometry of those 67 devices could
  differ from the reference netlist by any amount and this run would still
  report `match`.** The remaining six are `topology`: net pairs the comparer
  resolved structurally because the pairing was ambiguous by name (layout
  `$27`, `$29`, `$30`, `$36`, `$37`, `$51` against `CORE_TRIM_U2_0`,
  `CORE_TRIM_U2_2`, `CORE_TRIM_U3_0`, `CORE_TRIM_U3_6`, `CORE_TRIM_U4_0`,
  `CORE_TRIM_U4_14`); a `hints.same_nets` entry would pin them down instead.

**History — why the manifest pins inputs at all (August 2026).** The manifest
previously cited `20260819-070132-1e66285.lvs.json`, which also reported
`status: "match"` (92/92 nets, 164/164 devices) and was nonetheless rendered
`unmet` with `reason: "stale_evidence"`: it was produced by `klt` 0.2.0, which
left `provenance.input` `null`, so the staleness gate had nothing to match the
pinned `content_hash` against and could not prove the citation fresh — even
though that run *had* been made against the committed layout
(`environment.layout_sha256` agreed with it). Dropping the pin to force a
`met` would have asserted a freshness no tool checked, so the pin stayed and
the row stayed `unmet` until the re-run above (klayout-tools#1969). Neither
August envelope carries a `body_verification` field at all — both were
written by klt 0.2.0, and no envelope from that version or earlier in this
repo has one — so nothing on that run verified device bodies, which is a
weaker statement than the `verified` above, not a comparable one. The netgen
side reported `status: "mismatch"` (2 `device.body_unverified` warnings on
the deck-synthesized substrate/well nets, plus 1 `device.property` entry
whose per-parameter detail netgen's output did not parse into).
[`layout/README.md`](../layout/README.md) and
[`layout/erc/README.md`](../layout/erc/README.md) still describe that run.

### Item 5 — full corner verification: what is actually still open

`no_evidence` here is uncited-for-shape (above), not "nothing has been run".
Against the spec ratified 2026-07-31
(`spec/decision-records/0003-target-spec-ratification.md`, the table in
`README.md`): the newest suite summary,
[`sim/suite/summaries/20261016-015258-1c4f2a2.md`](../sim/suite/summaries/20261016-015258-1c4f2a2.md)
(2026-10-16, final DUT; dispatched to the batch fleet and indexed with its
caveats in
[`sim/suite/fleet-evidence-239.md`](../sim/suite/fleet-evidence-239.md)),
calls itself **simulation-complete**: all **6** spec lines in its index PASS
against the ratified table at every corner, and the two-legged
untrimmed-accuracy row passes at every corner. Its per-row table also carries
Startup as PASS on that bench's own verdict — the suite wires that bench in by
slug and deliberately does not re-evaluate it. Corners behind those rows, from
the summary's own bench table: 81 (`output-voltage-tc`), 81 (`psrr-dc`), 27
(`line-regulation`), 81 (`iq`), 81 (`startup`), plus the `mc-untrimmed`
mismatch leg (N=300 x 4 groups x 3 temperatures) that the two-legged
output-reference row is ratified on.

What is left open, disclosed here because no envelope carries it:

- **Rows the ratified table carries that this suite does not claim**, from the
  summary's own "Ratified rows this suite does not claim" table: Trim (no trim
  segments in the schematic yet, #14); **Output noise** — a bench now exists
  (`sim/output-noise/`, #189: 0.1–10 Hz integrated plus 1/10/100 kHz spot
  density over full PVT) and the summary names it, but the *numeric limit* is
  still open item A6; **Load** — still **no bench yet**, condition open item
  A7; Area (a layout claim, #15/#16); and long-term drift (not specified for a
  canary block). PSRR is measured unloaded because its load condition is open
  item A4. A4/A6/A7 are amendments from #35, TBD by ratification itself and
  carried through verbatim rather than invented. So "6/6 indexed lines pass"
  is accurate as written and is not the same statement as "the ratified
  table's full row set passes".
- **Startup is not a simulation of the canonical netlist.**
  `sim/suite/fleet-evidence-239.md` records that the startup bench keeps its
  embedded, lumped-R1 core (`sim/startup-embedded-core-sync.md`): lumped R1 is
  exact at tt/27 °C only (−0.18 % / +0.27 % at −40 / 125 °C), and res_ff /
  res_ss are not exercised by it.
- **The combined accuracy coefficient is not yet validated.** The same index
  records that the combined two-legged accuracy report
  (`sim/suite/combined/20261016-013300-999e5cf.md`, PASS with a tightest
  margin of 1.356 mV at bjt_ff / 125 °C / 3.63 V) flags that the `par_r` ×2
  sensitivity case **flips 3 corners at 125 °C**, so that coefficient needs
  validating before the combined verdict is final.

Both of those caveats predate and are unchanged by #344's Iq roll-up, which
produced the summary cited above without running any new simulation.

The existing evidence for the TBD rows, their provenance and coverage gaps,
and one ranked operator question per row are collected in
[`spec/tbd-row-evidence.md`](../spec/tbd-row-evidence.md). That packet only
prepares decisions: it changes no verdict here, ratifies no row, and reserves
no decision-record number.

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
| Attested files vs. the hashes in `attestations/*.json` (item 9 also: inventory lists every tracked testbench) | `lint` job, via `.github/scripts/lint.sh` | python3 only |
| Re-grade with the pinned `klt` and diff against the committed record; `klt signoff --attest N --check` for each attestation | `signoff` job | network (installs `klt` at `klt-pin.txt`'s revision; runs it via `KLT_SIGNOFF_CMD=klt`) |

So a manifest citing an artifact that has since changed, a record that no
longer matches what `klt` would say today, and a mis-keyed evidence entry that
`klt` would silently ignore all fail a PR instead of rotting quietly.

## Fleet roll-up

`block` is required in this manifest (klt itself calls it optional) because it
is how this block's row is identified in the fleet roll-up, 2AMLogic/2am#956,
which consumes this exact file via `klt signoff --fleet`.
