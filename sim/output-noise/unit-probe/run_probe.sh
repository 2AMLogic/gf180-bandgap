#!/usr/bin/env bash
# Run the unit probe once per mode (single point, no grid). `-n` skips every
# .spiceinit (user/cwd) so startup config cannot change the units.
# Usage: run_probe.sh [outdir]   (default: ./out next to this script)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/out}"; mkdir -p "$out"
ngspice -v | sed -n 1,3p > "$out/version.txt"
for mode in default sqrnoise; do
  case $mode in default) line="unset sqrnoise";; sqrnoise) line="set sqrnoise";; esac
  sed "s/^SQRNOISE_MODE\$/$line/" "$here/resistor_noise_probe.spice" > "$out/deck_$mode.cir"
  ( cd "$out" && HOME="$out" ngspice -n -b -o "log_$mode.txt" "deck_$mode.cir" )
done
