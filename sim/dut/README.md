# sim/dut — the swappable device under test

Every bench in the spec-line suite simulates the *same* block. None of them
contains a copy of it: each `tb.json` names a DUT netlist, the corner runner
`.include`s that file ahead of the testbench, and the record says which
netlist it was taken against.

```json
{ "dut": "sim/dut/bandgap_top.spice" }
```

```bash
python3 sim/run_corners.py iq                                   # the manifest's DUT
python3 sim/run_corners.py iq --dut sim/dut/frozen/<pinned>.spice
python3 sim/run_suite.py --dut layout/netlist/bandgap_top_extracted.spice
```

That indirection exists for one concrete downstream reason: **#17 re-runs
this entire suite on the post-layout extracted netlist.** When it does, no
testbench, manifest or check may need editing — only `--dut` changes, and
the new record set is distinguished from the schematic-level one by its
**Netlist provenance** field, not by a fork of the benches.

## What lives here

| Path | Provenance class | What it is |
|---|---|---|
| `bandgap_top.spice` | `schematic` | generated from `design/netlist/bandgap_top.spice`, i.e. whatever `design/bandgap_top.sch` currently is |
| `frozen/<name>-<date>.spice` | `frozen schematic` | a pinned copy, so a record set stays reproducible after the schematic moves on |
| (`layout/...`) | `extracted` | post-layout, produced by #16/#17; not in this directory and not in this repo yet |

The provenance class is derived from the path (`layout/` ⇒ extracted,
`/frozen/` ⇒ frozen), so a post-layout re-run reports itself correctly with
no flag anyone can forget to pass.

## Regenerating `bandgap_top.spice`

It is generated, not hand-maintained. After any change to
`design/bandgap_top.sch` (and therefore to `design/netlist/bandgap_top.spice`
— #10's sized amp, #11's startup branch, #14's trim segments):

```bash
python3 sim/tools/mk_dut.py design/netlist/bandgap_top.spice sim/dut/bandgap_top.spice
python3 sim/tools/mk_dut.py design/netlist/bandgap_top.spice sim/dut/bandgap_top.spice --check
```

The tool performs exactly two mechanical edits to the xschem export —
uncomment the top cell's `**.subckt` / `**.ends` wrapper, drop the
deck-owning directives (`.end`, `.temp`, `.lib`, `.control`) — and refuses to
write anything that is not a clean set of subcircuit definitions. `--check`
is the same conversion without writing: it fails if the committed fragment
has drifted from the schematic export, which is how a stale DUT becomes
visible instead of silently producing records against last week's circuit.
The generated header records the source path and the source's sha256; the
runner records the *fragment's* sha256 on every record it mints.

## Freezing a DUT

The schematic is still moving. A frozen copy pins the exact netlist a record
set was taken against, so those records stay reproducible afterwards:

```bash
cp sim/dut/bandgap_top.spice sim/dut/frozen/bandgap_top-$(date +%Y%m%d)-schematic.spice
# then edit only the frozen file's header comment to say what it pins and why
```

Frozen files are inputs, not evidence: they live outside `records/`,
`netlist-snapshots/` and `corners/`, so the append-only rule in
`sim/README.md` does not govern them. Do not "update" one in place, though —
that would silently change what an existing record's `--dut` argument means.
Add a new one.

## What a DUT netlist may contain

Subcircuit definitions only. The harness rejects `.end`, `.control`,
`.endc`, `.temp` and `.lib` in a DUT file (`harness.testbench.validate_dut`):
those belong to the harness, which supplies a fresh set per PVT point. A
stray `.end` from an xschem export would truncate every generated deck right
after the DUT, and the resulting "no measurements" would look like a
convergence failure rather than the packaging mistake it is.

`.include` **is** allowed here — a post-layout extracted netlist routinely
pulls in sub-netlists of its own.

## Pin set

`bandgap_top` exposes `vdd`, `vss`, `vref`. Testbenches instantiate it as:

```spice
vsup vdd 0 dc {vdd_val}
Xdut vdd 0 vref bandgap_top
```

Internal nodes are reachable hierarchically (`v(xdut.fb)`,
`v(xdut.xx1.casc)`) and the benches use that for convergence seeding only.
Per `design/bandgap_operating_point.md` §5, a testbench that needs to *probe*
an internal node should get a new pin on `design/bandgap_top.sch` rather than
routing around the wrapper — so the wrapper's pin list stays the single
source of truth for what is testable from outside, on the schematic and on
the extracted netlist alike.
