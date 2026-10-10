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

## 7. Next: the PVT corner harness

Everything above establishes the *install*. The evidence-producing harness
sits on top of it and resolves the same PDK by a superset of the same rules
(`GF180_PDK_PATH` -> `PDK_ROOT` + `PDK` -> `sim/pdk.local.json` ->
`sim/pdk.json` -> the usual install prefixes, volare first), so the
`PDK_ROOT`/`PDK` exports from §4 are all it needs:

```bash
python3 sim/run_corners.py --check-env   # what the harness resolved, or how to fix it
python3 sim/run_corners.py --print-env   # shell exports for the resolved PDK
source sim/env.sh                        # same exports, for xschem and ad-hoc ngspice
bash sim/selftest.sh                     # unit tests + an 81-point PVT smoke run
```

`design/xschemrc` follows that same resolution order, so xschem and the
corner runner never disagree about which PDK is in use; compare
`sim/run_corners.py --print-env` against the path xschem reports if you ever
suspect they have drifted apart.

The full harness reference -- PDK resolution, corner definitions, how to
write a testbench manifest, and why `sim/smoke_test/` (this document's
install check) and `sim/smoke-bias/` (the harness's own acceptance test) are
two different things -- is [`sim/harness/README.md`](../sim/harness/README.md).
The record format it writes into is [`sim/README.md`](../sim/README.md).

## 8. Troubleshooting: Loom guard denies an evidence copy

Agents running under Loom have a Bash `PreToolUse` guard
(`.loom/hooks/guard-destructive-generic.sh`) that confines writes to the
issue worktree. A copy of probe artifacts into `sim/` can be denied with a
message like `write target '$E/probe.raw' is an unexpanded shell variable
from the path root down`
(logged as `worktree-write-confinement-unresolved-var` in
`.loom/logs/guard-decisions.log`). The denial is deliberate fail-closed
behaviour: if the guard cannot tell where a write lands, it refuses. Do not
disable the guard or its isolation setting; use one of the recipes below.

Replace `/literal/worktree` with the actual absolute path of the issue
worktree (e.g. `<checkout>/.loom/worktrees/issue-NNN`).

```bash
# 1. Explicit literal destination (preferred)
cp /tmp/probe.raw /literal/worktree/sim/probe.raw

# 2. Direct literal assignment in the same command
E=/literal/worktree/sim; cp /tmp/probe.raw "$E/probe.raw"
```

This form is **not** resolved by the installed single-pass resolver, because
`E` is derived from another variable:

```bash
W=/literal/worktree; E=$W/sim; cp /tmp/probe.raw "$E/probe.raw"   # denied
```

Unknown variables, destinations in the main checkout, and the historical
operations that wrote into shared klayout-tools installs or removed caches
outside the checkout remain denied (and should be). Evidence under `sim/` is
append-only; follow the record rules in [`sim/README.md`](../sim/README.md).

### Minimal hook-only reproduction

This stages the guard in a throwaway git repository and feeds it the command
strings as Bash `PreToolUse` JSON. The commands are only data in the JSON;
nothing is copied, and nothing in this repository (including `sim/`) is
touched. Requires only `bash`, `git` and `jq`. Literal temporary paths are
used on purpose: building the fixture with chained shell variables is itself
subject to the same guard.

```bash
# Run from the root of this repository (or an issue worktree of it).
mkdir -p /tmp/loom-repro/.loom/hooks /tmp/loom-repro/.loom/scripts/lib \
         /tmp/loom-repro/.loom/worktrees/issue-1 /tmp/loom-repro/sim
cp .loom/hooks/guard-destructive-generic.sh /tmp/loom-repro/.loom/hooks/
cp .loom/scripts/lib/config-resolver.sh .loom/scripts/lib/canonical-path.sh \
   /tmp/loom-repro/.loom/scripts/lib/
touch /tmp/loom-repro/.loom/worktrees/issue-1/.loom-managed
git init -q /tmp/loom-repro

cat > /tmp/loom-repro/check.sh <<'SCRIPT'
#!/usr/bin/env bash
# usage: check.sh '<command string>'  -- prints the hook decision only
jq -n --arg c "$1" --arg d /tmp/loom-repro/.loom/worktrees/issue-1 \
  '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' \
  | (cd /tmp/loom-repro/.loom/worktrees/issue-1 \
     && bash /tmp/loom-repro/.loom/hooks/guard-destructive-generic.sh) 2>/dev/null \
  | jq -r '.hookSpecificOutput // {} | "\(.permissionDecision) \(.permissionDecisionReason)"' \
  | cut -c1-200
SCRIPT

WT=/tmp/loom-repro/.loom/worktrees/issue-1
bash /tmp/loom-repro/check.sh "cp /tmp/probe.raw $WT/sim/probe.raw"                          # literal
bash /tmp/loom-repro/check.sh "E=$WT/sim; cp /tmp/probe.raw \"\$E/probe.raw\""               # direct
bash /tmp/loom-repro/check.sh "W=$WT; E=\$W/sim; cp /tmp/probe.raw \"\$E/probe.raw\""        # chained
bash /tmp/loom-repro/check.sh 'cp /tmp/probe.raw "$UNKNOWN/probe.raw"'                       # unknown var
bash /tmp/loom-repro/check.sh "cp /tmp/probe.raw /tmp/loom-repro/sim/probe.raw"              # main checkout
rm -rf /tmp/loom-repro
```

Observed with the guard from Loom v0.19.1009 (2026-10-10):

| Command shape | Decision |
| --- | --- |
| literal destination in the worktree | no output (allowed) |
| `E=/literal/worktree/sim; cp ... "$E/probe.raw"` | no output (allowed) |
| `W=/literal/worktree; E=$W/sim; cp ... "$E/probe.raw"` | `deny`, unresolved write target `$E/probe.raw` |
| `cp ... "$UNKNOWN/probe.raw"` | `deny`, unresolved write target `$UNKNOWN/probe.raw` |
| literal destination in the main checkout | `deny`, resolves to the main checkout |

The chained-assignment case looks like a resolver limitation rather than an
unsafe command, but resolving it is a change to the generated guard, which
belongs upstream and is not made in this repository. Related upstream parser
work: [rjwalters/loom#11113](https://github.com/rjwalters/loom/issues/11113).
That issue is an umbrella for shared parser weaknesses; it is not a confirmed
fix for, and does not name, this assignment-chain case. Until upstream
changes, use the literal forms above.
