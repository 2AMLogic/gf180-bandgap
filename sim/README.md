# sim/ — evidence record format

This directory holds simulation testbenches and their results. Results are
**append-only evidence**: once a record is written, it is never edited or
deleted. A re-run — even one that corrects a mistake — mints a new record
with a new ID; a correction references the record it supersedes rather than
overwriting it in place.

This convention exists because CLAUDE.md commits this repo to two rules that
need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench. Every
  recorded result carries the full PVT corner matrix (−40/27/125 °C, ±10%
  supply, process corners) unless the record explicitly states why a subset
  was used.
- **`sim/` is append-only evidence.** Re-runs get new records; records are
  never edited or deleted.

**This file is the authoritative convention.** The corner runner that produces
records in this format — how to run it, how to write a testbench, PDK
resolution, corner definitions — is documented in
[`sim/harness/README.md`](harness/README.md). If the harness and this document
ever disagree, this document wins and the harness is the thing that gets fixed.

## Directory / naming convention

Each testbench topic gets its own experiment directory:

```
sim/
  <experiment-slug>/                 # e.g. output-voltage-tc, psrr-dc, startup, mc-untrimmed
    testbench/                       # testbench netlist(s) / xschem export used
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.log              # raw ngspice output per PVT point
                                      # e.g. ss_-40c_2.97v.log
    records/
      <record-id>.md                 # append-only summary record
```

- **`<experiment-slug>`** — short, descriptive, kebab-case name for what is
  being verified (`output-voltage-tc`, `psrr-dc`, `startup`, `mc-untrimmed`,
  ...). One directory per distinct claim being tested, not per run.
- **`<record-id>`** — unique and traceable:
  `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (e.g. `20260729-153000-1a7ef75`).
  Re-runs simply mint a new `<record-id>`; nothing under `records/` is ever
  edited in place. The same `<record-id>` ties together the netlist snapshot,
  the raw per-corner logs, and the summary record for one run.
- **`<corner-id>`** — `<process>_<temp>c_<supply>`, e.g. `ss_-40c_2.97v.log`,
  `tt_27c_3.30v.log`, `ff_125c_3.63v.log`. The three fields are separated by
  the **last two** underscores, so the process field may itself contain one:

  - **`<process>`** — one or more lowercase alphanumeric tokens joined by
    underscores. For a circuit-level run this is the harness corner name
    (`tt`, `ss`, `ff`, `fs`, `sf`, and the passive-skew corners `res_ff`,
    `bjt_ss`, ...). For a device-level testbench that exercises one device
    family it is the gf180mcu model-section name that testbench selects
    (`typical`, `bjt_typical`, `res_ff`, ...). The vocabulary is deliberately
    **open**: gf180mcu ships a `.lib` section per device family (see
    `sim/harness/corners.py`), so the set grows with the families a testbench
    touches, and pinning it to `tt|ss|ff` would misname most device runs.
  - **`<temp>`** — the junction temperature in °C, signed, suffixed `c`:
    `-40c`, `27c`, `125c`. A record may add intermediate points (`-10c`,
    `60c`, `90c`) but never fewer than the CLAUDE.md axis without a stated
    reason.
  - **`<supply>`** — one of:
    - `<volts>v` — the swept supply, e.g. `2.97v`, `3.30v`, `3.63v`;
    - `<node><volts>v` — when the swept rail is not the main supply and needs
      naming, e.g. `nwell2p97v`. `p` stands in for the decimal point so the
      field stays a single token with no underscore of its own;
    - `nosupply` — the testbench has no supply rail to sweep (a device
      testbench referred to its own source node and driven by an ideal
      source). This is one of the subset justifications the record's **Corner
      matrix run** field is required to spell out.
- **`testbench/`** is not versioned per record — it holds the current
  testbench netlist(s)/xschem export(s) used to generate records. If the
  testbench itself changes in a way that could affect comparability across
  records, note that in the new record's summary (e.g. under Claim or a
  free-text note).

## Summary record format

Each run produces one `records/<record-id>.md` file with the following
fields:

- **Record ID** — the `<record-id>` for this run (matches the filename and
  the corresponding `netlist-snapshots/` / `corners/` subdirectory).
- **Claim** — which spec parameter/line this record substantiates (reference
  the ratified spec, e.g. `spec/<file>.md#<anchor>`, once ratified specs
  exist — see #1).
- **Netlist provenance** — `schematic` (`design/...`) or `extracted`
  (post-layout, `layout/...`). Required so post-layout re-runs are
  distinguishable from the original schematic-level record.
- **Corner matrix run** — explicit list of (process corner, temperature,
  supply) points actually executed. Must be the full PVT matrix from
  CLAUDE.md (−40/27/125 °C, ±10% supply, process corners) unless the record
  states why a subset was used.
- **Statistical convention** (when applicable, e.g. Monte Carlo mismatch
  analysis) — N samples and sigma level reported. Used for distribution
  claims that are not a per-corner pass/fail (e.g. reporting a spread against
  the untrimmed spec).
- **Result** — per-corner pass/fail, plus an overall pass/fail against the
  ratified spec value.
- **Links** — paths to the testbench file(s), the frozen netlist snapshot,
  and the raw per-corner logs used to produce this record.
- **Timestamp / author** — when the record was created and who (human or
  agent) created it.
- **Supersedes** (optional) — the prior `<record-id>` this record supersedes,
  for corrections or for a post-layout extracted re-run that reports a
  schematic-vs-extracted delta against the schematic-level record. Mirrors
  the status/supersession language proposed for `spec/` decision records
  (see #6), so both conventions read as one house style.

## Append-only rule

`records/*.md` files are never edited or deleted after creation. A re-run or
a correction always creates a new record with a new `<record-id>`. If it
corrects or replaces a prior result, it references that prior record via
**Supersedes** rather than overwriting it. This applies even to typo fixes —
the append-only guarantee is what makes `sim/` usable as an evidence trail;
"fixing" an existing record in place would defeat that.

## Comparing two records: the post-layout delta summary

Two records for the same claim with different **Netlist provenance** are the
whole point of that field. `sim/postlayout-delta.md` is the standing
schematic-vs-extracted comparison for the ratified spec lines, generated by

```bash
python3 sim/postlayout_delta.py \
  --pair <slug>=<schematic-record-id>:<extracted-record-id> ... \
  --append <narrative fragment> -o sim/postlayout-delta.md
```

It reads committed records only — it runs no simulation and mints no record,
so it is not evidence and the append-only rule below does not govern it: it is
a *view* of evidence, regenerable at any time from the two record-ids it names,
and it takes its limits from `sim/suite/spec.py` so it can never disagree with
a suite summary about what the ratified number is. Regenerate it rather than
editing it.

## Enforcement

This convention is checked, not merely documented. `sim/check_records.py`
(implementation: `sim/harness/evidence_lint.py`) runs as step 4 of
`.github/scripts/lint.sh`, so `npm run lint` and the CI `lint` job both
execute it on every PR. It reads tracked files only, needs nothing but
`python3` and `git`, and fails on:

- a missing or empty one of the nine required fields above;
- a filename that is not a well-formed `<record-id>`, or a **Record ID**
  field that disagrees with its filename;
- a record with no `netlist-snapshots/<record-id>.spice` or no
  `corners/<record-id>/` logs — and, symmetrically, a snapshot or corner
  directory with no summary record to cite it;
- a `<corner-id>.log` name that does not parse under the grammar above;
- a **Supersedes** value that names a `<record-id>` with no record in the
  same experiment directory (write `(none)` when a record supersedes
  nothing);
- **append-only violations**: any file under `records/`,
  `netlist-snapshots/` or `corners/` modified, renamed, or deleted relative
  to the merge base with `origin/main`. Only additions are allowed.

The append-only half needs real git history; where the base ref does not
resolve (a shallow clone, say) it prints `SKIP` rather than passing silently,
and `--require-append-only` turns that skip into a failure — which is how CI
runs it.

If the checker and this document ever disagree, this document wins and the
checker is the thing that gets fixed. The evidence is never the thing that
gets fixed.

## Worked example

Directory layout for a temperature-coefficient claim on the output
reference, followed by a Monte Carlo re-check of the same claim, followed by
a post-layout extracted re-run:

```
sim/
  output-voltage-tc/
    testbench/
      tb_output_voltage_tc.spice
    netlist-snapshots/
      20260729-153000-1a7ef75.spice
      20260805-091200-7c2f9de.spice
    corners/
      20260729-153000-1a7ef75/
        tt_27c_3.30v.log
        ss_-40c_2.97v.log
        ff_125c_3.63v.log
        ...
      20260805-091200-7c2f9de/
        tt_27c_3.30v.log
        ss_-40c_2.97v.log
        ff_125c_3.63v.log
        ...
    records/
      20260729-153000-1a7ef75.md
      20260805-091200-7c2f9de.md
```

`records/20260729-153000-1a7ef75.md` (placeholder values — no ratified spec
values exist yet, see #1):

```markdown
# Record 20260729-153000-1a7ef75

- **Record ID**: 20260729-153000-1a7ef75
- **Claim**: `spec/bandgap.md#output-voltage-tc` — temperature coefficient of
  the output reference over −40…125 °C, TBD ppm/°C target (placeholder;
  ratified spec pending #1)
- **Netlist provenance**: schematic (`design/bandgap.sch`)
- **Corner matrix run**:
  - Process: tt, ss, ff
  - Temperature: −40 °C, 27 °C, 125 °C
  - Supply: 2.97 V, 3.30 V, 3.63 V (±10% of 3.3 V)
  - (9 corner points total — full process x temp matrix at nominal supply,
    plus supply sweep at tt/27C; see testbench for exact point list)
- **Statistical convention**: N/A (corner-matrix claim, not a distribution
  claim)
- **Result**:
  - tt/27C/3.30V: PASS (placeholder value)
  - ss/-40C/2.97V: PASS (placeholder value)
  - ff/125C/3.63V: PASS (placeholder value)
  - ... (remaining corners: PASS, placeholder values)
  - **Overall: PASS** (placeholder — pending ratified spec, #1)
- **Links**:
  - Testbench: `sim/output-voltage-tc/testbench/tb_output_voltage_tc.spice`
  - Netlist snapshot: `sim/output-voltage-tc/netlist-snapshots/20260729-153000-1a7ef75.spice`
  - Raw logs: `sim/output-voltage-tc/corners/20260729-153000-1a7ef75/`
- **Timestamp / author**: 2026-07-29T15:30:00Z, agent-builder
- **Supersedes**: (none — first record for this claim)
```

`records/20260805-091200-7c2f9de.md` — a later Monte Carlo mismatch check of
the same untrimmed claim (illustrates the Statistical convention field; this
is a distinct claim from the corner-matrix record above, not a correction of
it, so it does not use Supersedes):

```markdown
# Record 20260805-091200-7c2f9de

- **Record ID**: 20260805-091200-7c2f9de
- **Claim**: `spec/bandgap.md#output-voltage-untrimmed` — output reference
  spread under device mismatch, untrimmed (placeholder; ratified spec
  pending #1)
- **Netlist provenance**: schematic (`design/bandgap.sch`)
- **Corner matrix run**: nominal corner (tt/27C/3.30V) only — mismatch
  distribution is evaluated at nominal PVT; see Statistical convention
- **Statistical convention**: N = 500 Monte Carlo samples (mismatch only),
  distribution reported at ±3σ against the untrimmed spec target
- **Result**: ±3σ spread within untrimmed spec (placeholder value) —
  **Overall: PASS** (placeholder — pending ratified spec, #1)
- **Links**:
  - Testbench: `sim/output-voltage-tc/testbench/tb_output_voltage_mc.spice`
  - Netlist snapshot: `sim/output-voltage-tc/netlist-snapshots/20260805-091200-7c2f9de.spice`
  - Raw logs: `sim/output-voltage-tc/corners/20260805-091200-7c2f9de/`
- **Timestamp / author**: 2026-08-05T09:12:00Z, agent-builder
- **Supersedes**: (none — distinct claim from 20260729-153000-1a7ef75, not a
  correction of it)
```

A later post-layout extracted re-run of the original corner-matrix claim
would live under the same `output-voltage-tc/` experiment directory with its
own `<record-id>`, `Netlist provenance: extracted (layout/bandgap.gds ->
extracted netlist)`, and a `Supersedes: 20260729-153000-1a7ef75` field
carrying a schematic-vs-extracted delta summary in its Result section.
