# layout — DRC/LVS flow (klayout-tools)

Layout verification for this repo is driven by
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`), per
`CLAUDE.md`. This directory stands up the **DRC** half of that flow, proves
it on a trivial single-device layout, and records where the flow currently
stops (LVS bring-up is deferred — see "LVS: deferred" below).

No real block layout exists yet (`sim/` is where the design lives today —
this repo is still in the simulation-complete phase; see the root
`README.md` maturity ladder). This directory currently holds only the
DRC bring-up scaffolding and its proof fixture.

```
layout/
  README.md          this file
  drc/
    run_drc.py        reproducible klt drc invocation -> committed report
    fixtures/
      trivial_poly_res/
        generate.py            builds the fixture GDS (klayout.db API)
        trivial_poly_res.gds   committed fixture GDS
    reports/
      trivial_poly_res/
        <record-id>.drc.json   committed klt drc --format json output
        <record-id>.drc.txt    companion --format text output
```

## Install `klt`

No PyPI release yet — install from the klayout-tools git repo:

```bash
uv tool install git+https://github.com/2AMLogic/klayout-tools
# or: pip install git+https://github.com/2AMLogic/klayout-tools

klt --version
klt drc --help
```

`klt drc` runs fully headless: it drives the pip `klayout` package's native
`klayout.db.Region` check primitives directly, with **no dependency on the
standalone KLayout GUI/application binary or its `.drc`/`.lydrc` script
runner** (klayout-tools `docs/cli/drc.md`). Confirmed for this bring-up: the
commands below ran to completion in a shell with no KLayout application
installed, no `DISPLAY`, and no Qt.

## Running DRC

```bash
python3 layout/drc/run_drc.py layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds
```

This is a thin wrapper around:

```bash
klt drc layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds --deck gf180mcu --format json
klt drc layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds --deck gf180mcu --format text
```

`--format json` is the committed, stable-contract report (klayout-tools
treats JSON as the API and text as a courtesy view — `docs/cli/drc.md`);
the `--format text` capture is kept alongside purely for human skimming.
`run_drc.py` writes both under `layout/drc/reports/<fixture>/<record-id>.*`
and never overwrites an existing report — mirroring the append-only
evidence convention `sim/README.md` documents for `sim/` (CLAUDE.md:
"`sim/` results are append-only evidence"; this repo applies the same rule
to `layout/` DRC reports). A re-run mints a new `<record-id>`
(`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`) rather than clobbering the last one.

**Limitation carried from klayout-tools:** DRC is whole-layout, flattened
per top cell — there is no `--top <cell>` filter to scope a check to one
cell inside a larger layout (`docs/cli/drc.md` § "Limitation: whole-layout,
flattened"). Fine for the single-cell fixture here; will matter once a
real, hierarchical block layout exists.

## The gf180mcu deck: coverage

The `gf180mcu` deck (`klayout-tools/src/klayout_tools/decks/gf180mcu.py`)
is a **curated starter subset**, not the full GlobalFoundries 180nm MCU
Design Rule Manual. It covers 10 width/spacing/enclosure rules across
exactly four layers:

| Layer     | GDS layer/datatype |
| --------- | ------------------- |
| `Poly2`   | 30/0 |
| `Comp`    | 22/0 |
| `Contact` | 33/0 |
| `Metal1`  | 34/0 |

No well/tap rules, no BJT-specific rules, no HV/5V-variant rules, no
Metal2–4. This block's real design uses devices outside that coverage (a
vertical PNP substrate device, multiple poly resistor flavors) — expect
the deck to grow incrementally as this and other blocks surface real gaps.
See "Friction filed" below for the coverage-gap issue this bring-up
already identified.

## Trivial proof fixture: `trivial_poly_res`

`klt` has no layout-generation/write capability yet (klayout-tools Phase 3,
"write", has not started) — the fixture GDS is built directly with the
`klayout.db` (`pya`-compatible) Python API, mirroring the construction
pattern in klayout-tools' own worked example
(`klayout-tools/examples/drc/generate.py`): a `kdb.Layout`, layer/datatype
pairs matching the deck, boxes inserted directly, `layout.write(path)`.

`layout/drc/fixtures/trivial_poly_res/generate.py` builds a trivial
single-device layout — a `Poly2` resistor with two `Contact`-and-`Metal1`
terminals — with **one seeded rule violation**: the resistor body is drawn
100 dbu (0.10 um) wide, narrower than the `poly2.width.1` rule's 180 dbu
(0.18 um) minimum. Everything else in the fixture (contact sizing, poly2
enclosure of each contact, metal1 pad sizing) is drawn clean, so the report
proves the deck catches a real violation without drowning it in incidental
ones — mirroring the seeded-violation pattern in klayout-tools' own sky130
worked example.

Regenerate the fixture (deterministic — same output every run):

```bash
uv run --with klayout python3 layout/drc/fixtures/trivial_poly_res/generate.py
```

The committed `trivial_poly_res.gds` and its `layout/drc/reports/`
snapshot are the frozen input/output pair for this bring-up. If the deck's
rules change upstream, regenerate the GDS and re-run `run_drc.py` to mint a
new report rather than editing an existing one in place.

## LVS: deferred

**`klt lvs` does not exist.** LVS is klayout-tools Roadmap Phase 4
("extract & verify"); as of this bring-up the project is still in Phase
1/2 (read + DRC). This is not a gap this repo can close — there is nothing
to "stand up" until the upstream verb exists. LVS bring-up for this repo
is explicitly deferred until it does; when `klt lvs` ships, a follow-on
issue picks up LVS bring-up proper, most likely reusing `trivial_poly_res`
(or a comparable trivial fixture) as its own first proof point, the same
way this issue used it for DRC.

## Friction filed (klayout-tools tracker)

Per CLAUDE.md's friction protocol, every klayout-tools gap this bring-up
surfaced is tracked generically (tool capability, never this design's
specifics) on the public
[klayout-tools issue tracker](https://github.com/2AMLogic/klayout-tools/issues):

- **Missing `klt lvs` / extraction capability** — already tracked upstream:
  [`2AMLogic/klayout-tools#54`](https://github.com/2AMLogic/klayout-tools/issues/54)
  (the original friction marker) and
  [`2AMLogic/klayout-tools#153`](https://github.com/2AMLogic/klayout-tools/issues/153)
  (the phased epic that supersedes it, which already references this
  repo's DRC/LVS bring-up as one of the consumers waiting on it). No new
  issue was filed for this gap — it was already open and current.
- **`gf180mcu` deck coverage gap (well/tap, BJT-specific rules)** —
  [`2AMLogic/klayout-tools#157`](https://github.com/2AMLogic/klayout-tools/issues/157):
  filed from this bring-up, described generically (deck coverage
  characteristic, no design specifics).

## Verifying this bring-up

```bash
# 1. Regenerate the fixture and confirm it matches the committed GDS
uv run --with klayout python3 layout/drc/fixtures/trivial_poly_res/generate.py
git diff --stat layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds   # should be empty

# 2. Re-run DRC and confirm the same single violation reproduces
python3 layout/drc/run_drc.py layout/drc/fixtures/trivial_poly_res/trivial_poly_res.gds
# -> status: violations, violation_count: 1, rule_counts: {"poly2.width.1": 1}
```
