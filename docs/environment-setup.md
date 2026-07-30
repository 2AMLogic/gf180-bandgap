# Environment Setup: xschem + ngspice + gf180mcu (macOS / Homebrew)

Bootstrap steps for the open-source design/sim flow described in
[`CLAUDE.md`](../CLAUDE.md): xschem (schematic capture / netlisting) +
ngspice (simulation) against the gf180mcu PDK (fetched via
[volare](https://github.com/efabless/volare)).

This doc is intended to be followed **verbatim, from a clean shell**, on any
fresh machine or agent session (this repo's sister canary repos reuse it as
the reference bootstrap).

Recorded on macOS (Darwin, arm64) with Homebrew. If you are on a different
OS, the `xschem` source build steps are the same; substitute your platform's
package manager for the Homebrew dependency installs.

## 1. Versions used to validate this doc (2026-07-29)

| Tool | Version | Source |
|---|---|---|
| xschem | **3.4.7** (tag `3.4.7`, commit `92dd8fe5f4d5c1057489710d8a22f18fdc9d7ed0`) | built from source, see §2 |
| ngspice | **46_1** | Homebrew (`ngspice`) |
| volare | **0.20.6** | Homebrew / pip (`volare`) |
| gf180mcu PDK | commit hash **`c6d73a35f524070e85faff4a6a9eef49553ebc2b`** | `volare fetch`, fetched **2026-07-29** |
| Build deps | `cairo` 1.18.4, `tcl-tk@8` 8.6.18, `xorgproto` 2025.1, XQuartz (cask) 2.8.5, `bison` (GNU Bison) 2.3, `flex` 2.6.4 (system, not Homebrew) | Homebrew / macOS system tools |

The gf180mcu hash above is the one every sister gf180 canary repo should
reuse verbatim (pinned, not "latest" -- re-running `volare ls-remote` later
will show newer hashes; do not silently switch to them without updating this
doc and re-validating the smoke test).

## 2. Build xschem from source

`xschem` has **no Homebrew formula** on macOS (`brew search xschem` / `brew
info xschem` both come back empty; there is no relevant tap, and there is no
MacPorts `port` binary either as a fallback). Build it from the upstream
[xschem](https://github.com/StefanSchippers/xschem) repository:

```bash
# Build dependencies (Homebrew + macOS system tools):
brew install cairo tcl-tk@8 xorgproto
brew install --cask xquartz   # provides /opt/X11 (X11 headers/libs)
# bison and flex ship with the macOS command line tools (/usr/bin/bison,
# /usr/bin/flex) -- no separate install needed on a machine with Xcode CLT.

# Clone the exact tag this doc was validated against:
git clone --branch 3.4.7 https://github.com/StefanSchippers/xschem.git
cd xschem
git rev-parse HEAD   # expect 92dd8fe5f4d5c1057489710d8a22f18fdc9d7ed0

# tcl-tk@8 is keg-only on Homebrew -- point configure/make at it explicitly:
export PATH="/opt/homebrew/opt/tcl-tk@8/bin:$PATH"
export PKG_CONFIG_PATH="/opt/homebrew/opt/tcl-tk@8/lib/pkgconfig:$PKG_CONFIG_PATH"
export LDFLAGS="-L/opt/homebrew/opt/tcl-tk@8/lib"
export CPPFLAGS="-I/opt/homebrew/opt/tcl-tk@8/include"

./configure --prefix=/opt/homebrew
make -j4
make install PREFIX=/opt/homebrew
```

(On Intel Macs, substitute `/usr/local` for `/opt/homebrew` throughout.)

Verify the headless netlist mode works against a trivial schematic (no GUI,
no PDK needed for this check):

```bash
xschem -n -x -q -r /opt/homebrew/share/doc/xschem/examples/lm317.sch -o /tmp
# no "Error:" lines expected; produces /tmp/lm317.spice
```

`-n` (netlist), `-x`/`--no_x` (headless, no X11 window), `-q` (quit after),
`-r`/`--no_readline` (safe for non-interactive/redirected stdin+stdout).

### A note on `~/.xschem/xschemrc` (machine-specific gotcha)

xschem loads, in order: the system-wide `xschemrc`, then
`~/.xschem/xschemrc` (**user**-level, overrides the system one), then a
project-local `./xschemrc` in the current working directory (overrides
both) -- **or** whatever file `--rcfile <path>` points at, if given.

If a machine already has a stale/unrelated `~/.xschem/xschemrc` (e.g. left
over from a prior, unrelated project), it can silently override
`XSCHEM_LIBRARY_PATH` and break even the generic `devices/` symbol library
(`l_s_d(): Symbol not found: ...` for every basic symbol). This repo does
**not** rely on `~/.xschem/xschemrc` being correct -- see
[`design/xschemrc`](../design/xschemrc), a project-local rc file that resets
`XSCHEM_LIBRARY_PATH` explicitly. Always invoke xschem for this repo with
`--rcfile design/xschemrc` (see §4) so behavior does not depend on
whatever is (or isn't) in any given machine's user-level dotfile.

## 3. Fetch the gf180mcu PDK via volare

```bash
volare --version                              # expect 0.20.6 (or record whatever is installed)
volare ls-remote --pdk gf180mcu               # lists available commit hashes, newest first
volare fetch  --pdk gf180mcu c6d73a35f524070e85faff4a6a9eef49553ebc2b
volare enable --pdk gf180mcu c6d73a35f524070e85faff4a6a9eef49553ebc2b
volare output --pdk gf180mcu                  # confirm: c6d73a35f524070e85faff4a6a9eef49553ebc2b
```

This creates `~/.volare/gf180mcuA` / `gf180mcuB` / `gf180mcuC` / `gf180mcuD`
(symlinks into `~/.volare/volare/gf180mcu/versions/<hash>/...`) -- one
directory per gf180mcu voltage/rule-deck variant. Per `CLAUDE.md`, this repo
uses the **3.3V flavor**, which is variant **`gf180mcuD`**.

## 4. `PDK_ROOT` / `PDK` environment convention

```bash
export PDK_ROOT="$(volare path)"   # -> ~/.volare (volare's PDK root)
export PDK="gf180mcuD"             # the 3.3V variant this repo targets
```

So `$PDK_ROOT/$PDK` resolves to `~/.volare/gf180mcuD`, and the ngspice
models live under `$PDK_ROOT/$PDK/libs.tech/ngspice/`.

Add this as a small sourceable snippet rather than a one-off manual export,
e.g. append to your shell profile:

```bash
# gf180-bandgap: xschem/ngspice/gf180mcu env (see docs/environment-setup.md)
export PDK_ROOT="$(volare path)"
export PDK="gf180mcuD"
```

Demonstrate it survives a fresh shell:

```bash
$ echo $PDK_ROOT $PDK
/Users/you/.volare gf180mcuD
```

## 5. Smoke test: xschem netlist -> ngspice sim, referencing gf180mcu models

[`design/smoke_test.sch`](../design/smoke_test.sch) is a throwaway circuit
(RC network + one gf180mcu 3.3V nfet, `nfet_03v3_dss`) -- **not** bandgap
content, just enough to exercise the full toolchain:
`VDD --R1(10k)-- vout --C1(1p)-- GND`, with `vout` also driving the drain of
a single `nfet_03v3_dss` instance (gate biased via `VG`, source/bulk
grounded).

The gf180mcu model include is deliberately **not** hardcoded into the
schematic (no machine-specific `$PDK_ROOT` path baked into version-controlled
files) -- [`sim/smoke_test/run_smoke_test.sh`](../sim/smoke_test/run_smoke_test.sh)
generates a small `sim/smoke_test/pdk_include.spice` shim from the
`PDK_ROOT`/`PDK` environment variables at run time (gitignored: it is a
derived artifact, regenerated on every run, not committed evidence), then:

1. Netlists `design/smoke_test.sch` with `xschem -n -x -q -r --rcfile
   design/xschemrc -o sim/smoke_test design/smoke_test.sch`, producing
   `sim/smoke_test/smoke_test.spice` (committed -- this file has no
   hardcoded paths and is portable/reproducible as-is).
2. Runs `ngspice -b smoke_test.spice` from `sim/smoke_test/`, computing the
   operating point (`v(vdd)`, `v(vg)`, `v(vout)`).

Run it (after §3/§4 are done):

```bash
export PDK_ROOT="$(volare path)"
export PDK="gf180mcuD"
sim/smoke_test/run_smoke_test.sh
```

Expected: exits 0, no `Error:` lines, and `sim/smoke_test/smoke_test.log`
(committed, append-only -- each run appends a new dated section rather than
overwriting prior runs, per `CLAUDE.md`'s "`sim/` results are append-only
evidence") ends with the three operating-point voltages, e.g.:

```
v(vdd) = 3.300000e+00
v(vg) = 1.500000e+00
v(vout) = 3.494946e-01
ngspice-46 done
```

## 6. Reproducibility checklist

- [ ] From a **new terminal** (nothing pre-sourced from a prior session),
      confirm `xschem --version` reports `XSCHEM V3.4.7` and `ngspice -v`
      reports `ngspice-46`.
- [ ] Confirm `echo $PDK_ROOT $PDK` resolves correctly after sourcing your
      shell profile snippet from §4 (not just in the shell where you first
      set it).
- [ ] Confirm the gf180mcu hash in use is the **pinned** one recorded in §1
      (`volare output --pdk gf180mcu`), not silently "whatever `ls-remote`
      shows as newest today."
- [ ] Run `sim/smoke_test/run_smoke_test.sh` and confirm it exits 0 with no
      `Error:` lines in its output.
