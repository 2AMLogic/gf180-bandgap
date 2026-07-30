# design — schematics and netlists

Schematic capture is xschem; simulation is ngspice via the corner runner in
[`../sim/`](../sim/README.md).

```
design/
  xschemrc     repo xschem config: resolves the PDK, adds repo symbol libraries
  symbols/     repo-local .sym files (created when the first one exists)
  netlist/     xschem-generated .spice netlists (created on first netlist)
```

## Running xschem

```bash
source sim/env.sh     # exports PDK_ROOT / PDK / XSCHEM_USER_LIBRARY_PATH
cd design && xschem   # xschem reads ./xschemrc from the working directory
```

`design/xschemrc` finds the gf180mcu install by the same rules as the harness
(`GF180_PDK_PATH`, then `PDK_ROOT`+`PDK`, then the usual prefixes — see
`sim/README.md`), sources the PDK's own xschemrc so the gf180mcu device symbols
are on the library path, and adds `design/`, `design/symbols/` and `sim/tb/`.
Netlists are written to `design/netlist/` so they are reviewable in git rather
than landing in a scratch directory.

## Getting a schematic into the corner runner

The corner runner consumes netlist *fragments*: devices and sources only, no
`.include`, `.lib`, `.temp`, `.control` or `.end` (the harness supplies those
per PVT point). Netlist the schematic from xschem, strip any simulator
directives, and point a `sim/tb/<name>/tb.json` at the result. The runner does
not care whether a fragment was generated or typed by hand.
