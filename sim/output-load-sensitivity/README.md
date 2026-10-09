# sim/output-load-sensitivity: characterization only

This bench measures how far `v(vref)` of the canonical `bandgap_top` moves
when a DC current is drawn from `vref`. It provides evidence for two open
operator decisions (issue #269):

- **A7, the Load row**: either "max DC load + load regulation" with a
  buffered output, or "explicit unbuffered, high-Z load only".
- **A4, the PSRR load condition**, which depends on the A7 answer.

Both are described in [`spec/tbd-row-evidence.md`](../../spec/tbd-row-evidence.md)
Row 3 and Row 1.

**What this bench does not do.** It has no spec threshold. It does not rate a
load, allocate an accuracy budget, select an output stage or close A7/A4.
`sim/suite/spec.py` keeps the Load row in `NOT_CLAIMED_HERE`. This slug is not
a suite line and is never graded. A run ends **COMPLETE** or **INCOMPLETE**,
never PASS or FAIL.

**The sweep span is an exploratory measurement range, not a supported-load
rating.** A current inside the range does not mean the block may be loaded
that hard. A current outside it does not mean the block may not.

## What is measured

| Item | Definition (authoritative copy: `testbench/tb.json` → `load_sweep`) |
|---|---|
| Load element | An ideal DC current source `iload nl 0` behind a 0 V ammeter `vlsense vref nl` (`testbench/tb_output_load.spice`). |
| Direction | **Positive = current sunk out of `vref` into `vss`**, so the load draws current. Negative = current sourced into `vref`. |
| Sign/units check | `i(vlsense)` must equal the swept value at every point. A reversed or mis-scaled current invalidates the corner. |
| Exploratory range | −1 µA … +2 µA in 10 nA steps (301 points), swept inside the testbench (`dc iload -1u 2u 10n`). |
| Unloaded baseline | `vref_unloaded_v` = `v(vref)` at the grid point where `iload` is exactly 0 A. It is never interpolated. If that point is missing, the corner is invalid. |
| Signed shift | `shift_mv_<sink\|source>_<I>` = (`v(vref)(I)` − baseline) × 1000 at ±100 nA, ±500 nA, ±1 µA and +2 µA. Negative means `vref` fell. |
| Slope at zero load | `slope_mv_per_ua` = central difference about 0 A over one grid step (dV/dI_sink, in mV/µA, which is numerically kΩ). `zout_kohm` = −slope. |
| Step-size check | Central differences over 1, 2 and 4 grid steps must agree within 1 %, reported as `slope_step_spread_pct`. If they do not, the slope is not resolved and the corner is invalid. |
| Nonlinearity | `nonlin_max_mv` is the largest departure from the zero-load tangent over the sweep. `slope_sink_side_*` and `slope_source_side_*` are the one-sided slopes. These are recorded, not gated. |
| PVT | 9 process corners (`full`) × −40/27/125 °C × 2.97/3.30/3.63 V gives 81 corners. The supply is set with `alter vsup`, and `v(vdd)` is checked against it. |

The range was chosen from one local tt / 27 °C / 3.3 V operating-point probe
of the current DUT. It is wide enough to show curvature, and fine enough to
resolve the slope at 0 A. It encodes no requirement.

## How to run (fleet; never a local grid)

```bash
python3 sim/tools/mk_klt_fleet_request.py output-load-sensitivity WORK            # 1. request (not dispatched)
klt sim --backend batch -o "$PWD/WORK/sweep/out" WORK/sweep/request.json \
    --format json > WORK/sweep/report.json                                         # 2. Spot fleet
python3 sim/tools/load_ingest.py WORK --dry-run                                    # 3. check
python3 sim/tools/load_ingest.py WORK                                              # 4. mint the record
```

Pass an **absolute** `-o`. With a relative output directory, `klt sim` reports
every measurement as "produced no value" (2AMLogic/klayout-tools#2892).
`mk_klt_fleet_request.py` prints absolute paths.

**Extracted DUT.** When a regenerated layout netlist is available, add
`--dut layout/netlist/<file>.spice` to steps 1 and 3. The plan and the record
label it `extracted`, and record its path and sha256. Schematic and extracted
runs are separate records. The committed extracted netlist predates the
current schematic (`spec/tbd-row-evidence.md`), so a run against it describes
that netlist only. A DUT that `.include`s other files is refused, because the
fleet stages only the single inlined deck.

### Validity rules

`sim/tools/load_ingest.py` checks the rules below; `sim/tests/test_load_ingest.py`
exercises them with synthetic fixtures. A corner that breaks any of them is
INVALID: its log gets the harness `INVALID POINT` trailer and the run is
INCOMPLETE.

- The waveform has the sweep axis, `v(vref)`, `v(vdd)` and `i(vlsense)`, all
  finite and of equal length.
- The axis is the manifest's grid: point count, uniform step and endpoints. A
  short sweep is reported as an *incomplete sweep*.
- A 0 A baseline point exists.
- There are at least 8 points on each side of 0 A. Otherwise the result is
  *insufficient resolution*.
- The sense current matches the sweep (sign and units).
- `v(vdd)` matches the corner's supply.
- The slope at 0 A is stable under step refinement.
- The fleet `.meas` min/max of `v(vref)` agree with the waveform to ngspice's
  print precision.

Run-level problems refuse the record outright, and nothing is written. These
are: a DUT, testbench, `tb.json` or deck hash that differs from the plan; a
DUT path or provenance-class mismatch; a submitting/worker klt version
mismatch; a report that is not a fleet run; or a manifest that has gained a
threshold. Such a record could not name the exact DUT and scope it describes.
Missing or invalid corners alone are recorded, marked INCOMPLETE, so a failed
attempt stays visible.

Records are append-only (`sim/README.md`). A re-run mints a new record-id and
uses `--supersedes`.

## How the numbers inform the A7 / A4 decision

The current circuit has no output buffer. `vref` is the drain of the cascoded
mirror leg feeding the R1 / trim / Q3 branch (`spec/tbd-row-evidence.md`
Row 3), so DC load current is taken from that branch. Use the record as
follows. The operator makes the judgement and sets any numbers in a decision
record.

- **"Explicitly unbuffered, high-Z load only" (A7 option 1).** "High-Z" can
  be quantified from `zout_kohm`. If the operator picks a tolerable Vref shift
  ΔV, then within the linear region the matching load bound is about
  ΔV / max-over-corners(`zout_kohm`). An equivalent minimum load resistance is
  about `vref` / I. `nonlin_max_mv` and the one-sided slopes show whether the
  linear estimate holds at that current. The record's per-corner table shows
  which corner sets the bound. An estimate outside the exploratory range is
  an extrapolation. Re-measure with a widened range before relying on it.
- **"Buffered: max DC load + load regulation" (A7 option 2).** Suppose the
  shift per µA is large compared with any budget a plausible consumer needs.
  That is evidence for a buffer, but this bench does not design one. After a
  buffer is added, this bench describes the buffer's input node only, and a
  new load-regulation bench on the buffered output is needed.
- **PSRR load condition (A4).** If A7 picks high-Z, A4 can be evaluated at
  "the high-Z test load", and this record identifies a load at which the DC
  operating point is essentially unchanged. The bench measures **DC only**.
  It does not measure loaded PSRR, capacitive load, load steps or
  mismatch-driven spread, so it cannot tell how ripple rejection changes
  under load. That remains `psrr-dc` work once A4 states a load.

The unloaded records (PSRR, TC, accuracy) still say nothing about loaded
behaviour. This bench adds the DC sensitivity only.
