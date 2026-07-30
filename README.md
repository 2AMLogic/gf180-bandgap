# gf180-bandgap

**PRIVATE — 2AM Logic proprietary IP. First canary block (wave 1, block 1).**

A bandgap voltage reference on GlobalFoundries gf180mcu (open PDK, 3.3V/5V
flavor), designed by agents driving [klayout-tools](https://github.com/2AMLogic/klayout-tools)
and the open-source analog flow. Dual purpose, per the canary model:

1. **Catalog inventory** — a licensable, eventually silicon-measured
   bandgap for gf180mcu (chosen first because the analog-PMU category is
   incumbent-validated at 180nm-class nodes, the node is uncontested, and
   wafer.space gives the cheapest measured-silicon path of any open PDK).
2. **Tool forcing-function** — every place the tools bind or fall short
   becomes a friction issue filed on the public klayout-tools tracker.

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

Maturity ladder for this block: simulation-complete → layout DRC/LVS-clean
→ shuttle seat (wafer.space) → measured silicon over temperature.

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
python3 sim/run_corners.py smoke_bias         # 81-point PVT sweep, records evidence
```

The harness is stdlib python3 — no virtualenv, no packages. It never hardcodes
a PDK path; see [`sim/README.md`](sim/README.md) for PDK resolution, the corner
definitions, how to write a testbench, and the append-only evidence format.
For schematic capture see [`design/README.md`](design/README.md).
