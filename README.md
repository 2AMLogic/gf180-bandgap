# gf180-bandgap

**First canary block (wave 1, block 1) from 2AM Logic.**

A bandgap voltage reference on GlobalFoundries gf180mcu (open PDK, 3.3V
primary flavor), designed end to end by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source analog flow — xschem + ngspice for design and simulation,
klayout-tools for layout. Every stage from spec decision records through
PVT-swept simulation evidence is agent-authored and version-controlled in
this repo; nothing here is hand-waved past a testbench.

This block is also a **forcing function** for the open-source tooling it
depends on: every place klayout-tools is awkward, missing a capability, or
wrong for what an agent-driven analog flow needs becomes a friction issue
filed generically on the public
[klayout-tools tracker](https://github.com/2AMLogic/klayout-tools/issues).
The bandgap topology was chosen first because the analog-PMU category is
well understood at 180nm-class nodes and the gf180mcu PDK is uncontested —
a good first target for proving out an agent-native, open-source-only path
from spec to measured silicon.

## Target specification (RATIFIED 2026-07-31, see issue #1 and #35)

Ratified by the operator conditional on the amendments in #35 (spec-review
opinion, klayout-tools #124 — see
[issue #1's ratification comment](https://github.com/2AMLogic/gf180-bandgap/issues/1#issuecomment-5147916639)).
Recorded in
[`spec/decision-records/0003-target-spec-ratification.md`](spec/decision-records/0003-target-spec-ratification.md);
this table supersedes the prior DRAFT.

| Parameter | Target | Stretch | Corner binding |
|---|---|---|---|
| Output reference | 1.20 V ±2% untrimmed (3σ, mismatch MC N≥300 + process corners, −40…125 °C) | ±0.5% trimmed (3σ, 1-point trim) | temperature extremes (−40…125 °C) + mismatch MC + process corners |
| Trim | 1-point resistor trim (binary-weighted segments per DR-0001), range ≥ ±5%, resolution ≤ 0.25%/step (≥5 bits equiv.), magnitude only | — | performed at 27 °C |
| Temp coefficient (−40…125 °C) | < 50 ppm/°C (box method, −40…125 °C) | < 20 ppm/°C (requires curvature correction) | full −40…125 °C box, process corners; PTAT-gain and trim resistor ratios must share one resistor flavor (`ppolyf_u` recommended, see `sim/device-resistor-tc/`) |
| PSRR | > 60 dB DC–1 kHz | > 30 dB @ 1 MHz | load condition TBD — to be fixed when the output stage is designed (see DR-0001) |
| Line regulation | < 1 mV/V (DC, 2.97–3.63 V) | — | full supply range, DC |
| Output noise | not yet quantified — band: 0.1–10 Hz integrated µVrms (threshold TBD; add a spot-noise point if a later wave feeds an ADC) | — | n/a |
| Supply | 3.3 V ±10% | also 5 V flavor | headroom binds at SS / −40 °C / 2.97 V (see `sim/device-pnp-vbe/`, `sim/device-mos-vth/`) |
| Quiescent current | < 50 µA | < 20 µA | binds at FF / 125 °C / 3.63 V (leakage + fastest devices) |
| Load | TBD — pending output-stage design (DR-0001): either max DC load + load regulation, or explicit unbuffered — high-Z load only | — | n/a |
| Area | < 0.066 mm² (interim ceiling, DR-0006) | — | n/a (not a PVT line) |
| Startup | self-starting at all corners (incl. SS / −40 °C / 2.97 V), < 1 ms to within 1% of final value | — | binds at SS / −40 °C / 2.97 V |
| Long-term drift | not specified (canary block) | — | n/a |

Rows marked TBD (PSRR load condition, output noise threshold, load-row option)
are amendments A4/A6/A7 from #35 carried through verbatim as open items — the
spec review proposed the row *shape* without a numeric decision, so no number
is invented here; each will be closed out as its own future decision record
when the relevant design work (output stage, #10) resolves it.

The Area row was originally ratified at `< 0.05 mm²` (DR-0003); the drawn
layout has since measured over that target twice — `< 0.085 mm²`
([DR-0005](spec/decision-records/0005-area-target-overrun.md), superseded)
and now `< 0.066 mm²`
([DR-0006](spec/decision-records/0006-area-target-narrowed-post-166.md)) —
both driven by real, already-ratified device-sizing/routing work rather than
a relaxation for its own sake; see those records for the full evidence and
`layout/bandgap_top/AREA.md` for the measured history.

**Status**: simulation-complete → layout DRC/LVS-clean → measured silicon
over temperature. Device characterization and PVT corner sweeps are
recorded as append-only evidence under `sim/` (see
[`sim/README.md`](sim/README.md) for the record format). A full block layout
is drawn and verified — DRC-clean (0 violations) and LVS-matching against the
schematic netlist on both comparators (`klt lvs` and an independent `netgen`
cross-check), with committed reports under `layout/` (see
[`layout/README.md`](layout/README.md), including what that LVS verdict does
and does not cover). Post-layout extracted re-verification **has** run — see
[`sim/postlayout-delta.md`](sim/postlayout-delta.md): the schematic-level
record passes the full spec-line suite, but the parasitic-extracted record
currently fails the output-reference and temperature-coefficient rows. That
gap is attributed to the drawn PNP array's 4.03 effective dVBE ratio versus
the schematic's 3.63
([#87](https://github.com/2AMLogic/gf180-bandgap/issues/87), blocked on a
spec decision record), not to a layout or extraction defect. Tapeout is not
scheduled; it is pending that decision and a subsequent passing
extracted-netlist re-run (tracked in
[#94](https://github.com/2AMLogic/gf180-bandgap/issues/94)).

## Layout

```
spec/          ratified spec + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

## Environment Setup

Before running xschem/ngspice against the gf180mcu PDK, follow
[`docs/environment-setup.md`](docs/environment-setup.md) — xschem
build-from-source steps (no Homebrew formula exists), the pinned gf180mcu
PDK hash fetched via `volare`, the `PDK_ROOT`/`PDK` env convention, and an
end-to-end smoke test (`sim/smoke_test/run_smoke_test.sh`).

## Getting set up

```bash
brew install ngspice                          # or apt-get install ngspice
pip install volare
volare enable --pdk gf180mcu <version-hash>   # volare ls-remote --pdk gf180mcu

python3 sim/run_corners.py --check-env        # confirm ngspice + PDK are visible
bash sim/selftest.sh                          # prove the harness runs end to end
python3 sim/run_corners.py smoke-bias         # 81-point PVT sweep, records evidence
```

The harness is stdlib python3 — no virtualenv, no packages. It never hardcodes
a PDK path. See [`sim/README.md`](sim/README.md) for the ratified evidence
record format (directory layout, record ids, the append-only rule), and
[`sim/harness/README.md`](sim/harness/README.md) for PDK resolution, the corner
definitions and how to write a testbench. For schematic capture see
[`design/README.md`](design/README.md).

## Verifying the spec

```bash
python3 sim/run_suite.py --list               # ratified spec row -> testbench index
python3 sim/run_suite.py                      # every bench, full PVT, pass/fail per row
```

One testbench per sim-verifiable row of the ratified table above, each run
through the PVT corner runner, each landing an append-only record. A run of
`sim/run_suite.py` where every row of the summary reads PASS is the
operational definition of **simulation-complete**; the summary also lists the
rows the suite deliberately does not claim (mismatch Monte Carlo, trim, area,
and the table's open items). See [`sim/suite/README.md`](sim/suite/README.md)
for the index and the measurement conventions, and
[`sim/dut/README.md`](sim/dut/README.md) for the swappable-DUT convention that
lets the same benches re-run unedited against a post-layout extracted netlist.

## Continuous integration

Every PR and every push to `main` runs
[`.github/workflows/ci.yml`](.github/workflows/ci.yml): lint
(shellcheck + python/json well-formedness) and the PDK-free half of the
harness self-test (40 unit tests, testbench-manifest loading). It needs
nothing but python3, so no PR waits on a PDK download.

The PDK-dependent half — the 81-point PVT smoke run against ngspice and the
pinned gf180mcu models — runs nightly and on demand in
[`.github/workflows/sim-pdk.yml`](.github/workflows/sim-pdk.yml). Neither
workflow writes evidence records; those are minted deliberately, never by CI.

```bash
npm run lint        # same lint the CI lint job runs
npm run check:ci    # lint + harness self-test (the whole PR gate, locally)
```

## History

This repository was developed privately from 2026-07-28 and opened to the
public on 2026-07-31. The full history — including the early private-era
commits — is preserved intact rather than rewritten: the evidence records
under `sim/*/records/` cite commit SHAs as provenance, and rewriting history
would break the chain that makes those results checkable.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
