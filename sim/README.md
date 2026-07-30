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
- **`<corner-id>`** — `<process-corner>_<temp>c_<supply>v.log`, e.g.
  `ss_-40c_2.97v.log`, `tt_27c_3.3v.log`, `ff_125c_3.63v.log`.
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
