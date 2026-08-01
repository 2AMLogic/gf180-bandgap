# sim/harness — the PVT corner runner

Reproducible ngspice simulation against the gf180mcu PDK. This document covers
**how to run** the harness and **how to write a testbench**.

The *output* of a run — directory layout, record-id format, the summary record
field set, and the append-only rule — is defined by
[`sim/README.md`](../README.md), not here. That convention is authoritative;
this harness exists to produce records that conform to it.

```
sim/
  run_corners.py            CLI entry point (stdlib python3, no venv)
  run_suite.py              run every spec-line bench + per-spec-line summary
  env.sh                    `source sim/env.sh` to export the same PDK to your shell
  selftest.sh               harness acceptance test (unit tests + end-to-end PVT run)
  pdk.json                  committed PDK defaults (variant, extra search roots)
  harness/                  the runner itself (this directory)
  suite/                    the spec-line suite -- see sim/suite/README.md
  dut/                      swappable DUT netlists -- see sim/dut/README.md
  tools/                    helper scripts (mk_dut.py, devchar.py)
  tests/                    harness unit tests (no PDK, no ngspice required)
  .work/                    generated ngspice decks (git-ignored, disposable)

  <experiment-slug>/        one per claim under test -- see sim/README.md
    testbench/              tb.json + netlist fragment      <- you write these
    netlist-snapshots/      frozen netlist per record       <- the harness writes these
    corners/<record-id>/    raw <corner-id>.log per PVT point
    records/<record-id>.md  append-only summary record
```

## Quick start

```bash
python3 sim/run_corners.py --check-env     # is ngspice + the PDK present?
python3 sim/run_corners.py --list          # experiments, corners, corner sets
python3 sim/run_corners.py smoke-bias      # run the full PVT grid, mint a record
bash sim/selftest.sh                       # prove the harness works (writes nothing)
python3 sim/run_suite.py                   # every spec-line bench + pass/fail summary
```

One experiment at a time is this runner's job; running *the whole spec-line
suite* and judging each ratified spec row is
[`sim/run_suite.py`](../suite/README.md), which drives this runner per slug.

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| `ngspice` | simulation | `brew install ngspice` / `apt-get install ngspice` |
| gf180mcu PDK | device models | `pip install volare && volare enable --pdk gf180mcu <hash>` |
| `xschem` | schematic capture (optional for simulation) | `brew install xschem` / distro package |
| python3 ≥ 3.9 | the harness | stdlib only, no packages |

The harness never hardcodes a PDK path. It resolves one, in order:

1. `GF180_PDK_PATH` — the *variant* directory, e.g. `~/.volare/gf180mcuD`
   (the one containing `libs.tech/`).
2. `PDK_ROOT` (+ `PDK`, default `gf180mcuD`) — the open_pdks / OpenLane convention.
3. `sim/pdk.local.json` — machine-local, git-ignored.
4. `sim/pdk.json` — committed defaults.
5. Built-in search roots: `~/.volare`, `~/.ciel`, `/usr/share/pdk`,
   `/usr/local/share/pdk`, `~/share/pdk`, `/opt/pdk`.

If nothing is found the runner exits 3 with install instructions rather than
producing a misleading result. `sim/run_corners.py --print-env` emits the
resolved paths as shell exports; `source sim/env.sh` applies them so that an
interactive ngspice or xschem session uses the identical PDK.

## The PVT grid

`CLAUDE.md` requires PVT corners on every recorded result. The defaults are
baked into `corners.py` and are what a testbench gets unless its manifest says
otherwise:

- **Temperature**: −40, 27, 125 °C
- **Voltage**: nominal ±10 % (3.3 V flavor → 2.97 / 3.3 / 3.63 V)
- **Process**: see below

gf180mcu has no single global corner switch — each device family carries its
own `.lib` section in `sm141064.ngspice`, so a named corner here is a bundle of
six sections (MOS, resistor, BJT, diode, MOS cap, MIM cap):

| Corner | Meaning |
|---|---|
| `tt` | everything typical |
| `ff` / `ss` | every device family fast / slow |
| `fs` / `sf` | fast-N/slow-P and slow-N/fast-P, passives typical |
| `res_ff` / `res_ss` | resistor sheet rho skewed, rest typical |
| `bjt_ff` / `bjt_ss` | BJT skewed, rest typical |

Corner sets: `tt` (1), `mos` (5, the default), `full` (9 — use this for
anything whose accuracy rides on resistors or BJTs, i.e. a bandgap).
`full` × 3 temperatures × 3 supplies = 81 operating points, a few seconds.

Each point becomes one `<corner-id>` — `<process>_<temp>c_<supply>v`, the
naming `sim/README.md` ratifies — and one raw log under
`corners/<record-id>/`.

Override any axis from the command line:

```bash
python3 sim/run_corners.py smoke-bias --corner-set full -j 8
python3 sim/run_corners.py smoke-bias --corners tt res_ss --temps -40 125
python3 sim/run_corners.py smoke-bias --supply 5.0 --supply-tol 0.10   # 5 V flavor
```

**Subsets need a reason.** `sim/README.md` requires every record's *Corner
matrix run* field to be the full mandated matrix "unless the record states why
a subset was used". The runner enforces that: if the grid you asked for is
missing a mandated temperature, a mandated supply, or has fewer than three
process corners, it refuses to write a record unless you supply
`--subset-reason '<why>'` (which is copied verbatim into the record), or pass
`--no-write` because you are only debugging.

```bash
# debugging: runs, records nothing
python3 sim/run_corners.py smoke-bias --corners tt --temps 27 --supply-tol 0 --no-write

# a deliberate, justified subset: runs and records, with the reason on the record
python3 sim/run_corners.py smoke-bias --corners tt --temps 27 \
    --subset-reason "nominal-only mismatch sweep; distribution claim, see Statistical convention"
```

## Writing a testbench

Create `sim/<experiment-slug>/testbench/` with a manifest and a netlist
fragment. The slug is the experiment directory from `sim/README.md`: one per
distinct claim under test, kebab-case.

`tb.json`:

```json
{
  "name": "my-experiment",
  "description": "one line, shows up in --list and in the record",
  "claim": "spec/bandgap.md#output-voltage-tc",
  "netlist": "my_tb.spice",
  "dut": "sim/dut/bandgap_top.spice",
  "nominal_supply_v": 3.3,
  "supply_tolerance": 0.1,
  "temperatures_c": [-40, 27, 125],
  "corners": ["full"],
  "analyses": ["op"],
  "params": {"iload": "10u"},
  "options": ["reltol=1e-5"],
  "measure": {"vref": "v(vref)", "iq_ua": "-i(vsup)*1e6"},
  "checks": {"vref": {"min": 1.15, "max": 1.25, "max_spread_pct": 2.0}}
}
```

`claim` is the default for the record's **Claim** field — the ratified spec
line this experiment substantiates. `--claim` overrides it per run.

`dut` (optional) names the **device under test**: a second fragment holding
nothing but subcircuit definitions, `.include`d ahead of the testbench. That
indirection is what lets several testbenches share one netlist, and what lets
the *same* testbench re-run unedited against a different one:

```bash
python3 sim/run_corners.py iq --dut sim/dut/frozen/bandgap_top-20260801.spice
python3 sim/run_corners.py iq --dut layout/netlist/bandgap_top_extracted.spice
```

The DUT path, its sha256 and its provenance class (`schematic` /
`frozen schematic` / `extracted`, derived from the path) land in the record's
**Netlist provenance** field, and its contents are copied into that record's
frozen `netlist-snapshots/<record-id>.spice` — so a record identifies the
exact circuit it measured, not just the stimulus around it. A DUT file may
not carry `.end`, `.control`, `.endc`, `.temp` or `.lib` (an xschem export
does: convert it with `sim/tools/mk_dut.py`); it *may* carry `.include`,
which an extracted netlist needs. See [`sim/dut/README.md`](../dut/README.md).

`subset_reason` (optional) pre-declares why this experiment's grid is a
deliberate subset of the mandated PVT matrix — for a testbench that sweeps an
axis internally, say. `--subset-reason` still overrides it, and either way the
text is copied verbatim onto the record, which is where `sim/README.md` wants
the justification to live.

The netlist is a **fragment**, not a complete deck. It must not contain
`.include`, `.lib`, `.temp`, `.control`, `.endc` or `.end` — the harness owns
all of those, which is what lets one netlist sweep the whole grid unedited.
The loader rejects fragments that break this rule instead of silently pinning
every corner to 27 °C. The harness hands the fragment:

| Parameter | Value |
|---|---|
| `vdd_val` | supply for this PVT point |
| `vdd_nom` | nominal supply, for ratio measurements |
| `temp_c` | temperature for this PVT point (also applied via `.temp`) |

Each `measure` entry becomes `let m_<name> = <expr>` followed by `print` inside
the control block, so the expression must reduce to a **scalar**: fine for
`op`; for `tran`/`ac` reduce with `maximum()`, `mean()`, `v(out)[0]`, etc.

`checks` are evaluated after the sweep:

| Key | Applies to | Meaning |
|---|---|---|
| `min` / `max` | every point | hard limit; failure names the offending corner-id |
| `max_spread_pct` | the grid | `(max−min)/\|mean\|` must stay under the limit |
| `min_spread_pct` | the grid | must *exceed* it — asserts the sweep really moved |

`min_spread_pct` is a harness-integrity check: if `.temp` or a `.lib` section
silently failed to apply, a strongly PVT-sensitive measurement would come back
flat, and this catches that instead of reporting a suspiciously perfect result.

## What a run writes

One run mints one `<record-id>` (`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`) and
writes, under `sim/<experiment-slug>/`:

| Path | Contents |
|---|---|
| `records/<record-id>.md` | the append-only summary record (the nine fields from `sim/README.md`, plus an Environment section with PDK / ngspice / harness / git provenance and the per-corner model sections) |
| `netlist-snapshots/<record-id>.spice` | verbatim frozen copy of the testbench fragment, with its sha256 |
| `corners/<record-id>/<corner-id>.log` | raw ngspice output, one file per PVT point |

Nothing is ever overwritten: the runner refuses to write over an existing
record or snapshot, and mints a later record-id if one is somehow already
taken. Corrections and re-runs get a new record-id and reference the prior one
with `--supersedes <record-id>`. Do not edit or delete anything under
`records/`, `netlist-snapshots/` or `corners/` — see the append-only rule in
`sim/README.md`.

A run taken against a dirty working tree says so in the record's **Netlist
provenance** field and is not citable as a clean-tree result.

Exit codes: `0` pass · `1` a check failed · `2` a simulation failed or did not
converge · `3` environment problem (no ngspice, no PDK, bad manifest,
unjustified PVT subset).

Generated decks land in `sim/.work/<experiment-slug>/<record-id>/` and are
git-ignored, so a failing corner can be reproduced by hand with
`ngspice -b sim/.work/<slug>/<record-id>/<corner-id>.spice`.

## smoke-bias

`sim/smoke-bias/` is the harness acceptance test, not a circuit deliverable and
not a spec claim. Three independent branches, each proving a different part of
the plumbing:

1. an ideal resistor divider — must read exactly 0.5·vdd at all 81 points,
   proving parameter substitution and measurement parsing;
2. a PDK `ppolyf_u` resistor into a diode-connected `nfet_03v3` — proves the
   MOS and resistor `.lib` sections load and actually change between corners;
3. a diode-connected `npn_10p00x10p00` at 10 µA — Vbe is strongly CTAT, so it
   proves `.temp` and the BJT corner take effect.

### `sim/smoke-bias/` vs `sim/smoke_test/` — two different jobs

The repo has two things with "smoke" in the name. They are deliberately
distinct and neither replaces the other:

| | `sim/smoke_test/` (issue #24) | `sim/smoke-bias/` (issue #2) |
|---|---|---|
| Question it answers | "is my *install* correct?" | "is the *harness* correct?" |
| Scope | one point (tt, 27 °C, nominal) | the full 81-point PVT grid |
| Path exercised | xschem netlisting → `$PDK_ROOT/$PDK` shim → ngspice | `sim/run_corners.py` → corner shim → ngspice → record writer |
| Run it | `sim/smoke_test/run_smoke_test.sh` | `bash sim/selftest.sh` |
| Output | `sim/smoke_test/smoke_test.log` (evidence of an install) | an append-only record under `sim/smoke-bias/records/` |
| Owns | `docs/environment-setup.md`'s acceptance step | this harness's acceptance criteria |

`sim/smoke_test/` is the first thing to run on a fresh machine: it proves
xschem, the PDK install and ngspice work together at all, and it is the
acceptance check `docs/environment-setup.md` ends with. `sim/smoke-bias/` runs
*after* that passes and proves this harness's own machinery — corner
substitution, `.lib`/`.temp` plumbing, measurement parsing, the append-only
record writer — actually does what it claims across every PVT point. A green
`smoke_test` with a red `smoke-bias` means the harness is broken; the reverse
cannot happen, because `smoke-bias` cannot run without a working install.

## xschem

`design/xschemrc` resolves the PDK the same way the harness does and sources
the PDK's own xschemrc, so gf180mcu symbols and this repo's `design/`,
`design/symbols/` and every `sim/<experiment-slug>/testbench/` are all on the
library path:

```bash
source sim/env.sh
cd design && xschem
```

Schematic netlists are written to `design/netlist/`. To simulate a schematic,
strip it to a fragment (or netlist a testbench schematic without its
`.control`/`.end` block) and point a `tb.json` at it — the corner runner is
agnostic about whether the fragment was typed or generated.

Note: xschem itself is not required to run any of the above; the corner runner
only needs ngspice and the PDK.
