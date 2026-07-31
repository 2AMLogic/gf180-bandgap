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

## Target specification (DRAFT — engineering to ratify, see issue #1)

| Parameter | Target | Stretch |
|---|---|---|
| Output reference | 1.20 V ±1% untrimmed | ±0.5% with trim |
| Temp coefficient (−40…125 °C) | < 50 ppm/°C | < 20 ppm/°C |
| PSRR @ DC | > 60 dB | > 70 dB |
| Supply | 3.3 V ±10% | also 5 V flavor |
| Quiescent current | < 50 µA | < 20 µA |
| Area | < 0.05 mm² | — |
| Startup | self-starting, < 1 ms | — |

**Status**: simulation-complete → layout DRC/LVS-clean → measured silicon
over temperature. Currently in simulation: device characterization and PVT
corner sweeps are recorded as append-only evidence under `sim/` (see
[`sim/README.md`](sim/README.md) for the record format). Layout has not
started; tapeout is not yet scheduled.

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

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
