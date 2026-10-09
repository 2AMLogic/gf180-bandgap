#!/usr/bin/env bash
# Run the layout/ unit tests (stdlib only, PDK-free, klayout-optional).
# Layout dirs are not packages, so discover runs once per directory that
# holds tests. Fails if any test fails or if zero tests are collected.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

mapfile -t dirs < <(git ls-files 'layout/**/test_*.py' | xargs -r -n1 dirname | sort -u)
if [ "${#dirs[@]}" -eq 0 ]; then
  echo "::error::no layout test files found (git ls-files 'layout/**/test_*.py')" >&2
  exit 1
fi

total=0
for d in "${dirs[@]}"; do
  echo "== $d"
  log="$(mktemp)"
  python3 -m unittest discover -s "$d" -p 'test_*.py' 2>&1 | tee "$log"
  n="$(sed -n 's/^Ran \([0-9]*\) test.*/\1/p' "$log" | tail -1)"
  rm -f "$log"
  if [ -z "$n" ] || [ "$n" -eq 0 ]; then
    echo "::error::zero tests collected in $d" >&2
    exit 1
  fi
  total=$((total + n))
done
echo "layout unit tests: $total run across ${#dirs[@]} directories"
