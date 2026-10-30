#!/usr/bin/env bash
# Run the layout/ unit tests (stdlib only, PDK-free, klayout-optional).
# Layout dirs are not packages, so discover runs once per directory that
# holds tests. Fails if any test fails or if zero tests are collected.
#
# --require-no-skips  also fail when any unittest summary reports `skipped=`.
#   Use it only where klayout and klt are installed (the CI `signoff` job), so
#   a klayout/klt-gated test that silently skips cannot go unnoticed. The
#   PDK-free `test` job runs without it and lets those tests skip.
set -euo pipefail

require_no_skips=0
for arg in "$@"; do
  case "$arg" in
    --require-no-skips) require_no_skips=1 ;;
    *) echo "usage: $0 [--require-no-skips]" >&2; exit 2 ;;
  esac
done

cd "$(git rev-parse --show-toplevel)"

mapfile -t dirs < <(git ls-files 'layout/**/test_*.py' | xargs -r -n1 dirname | sort -u)
if [ "${#dirs[@]}" -eq 0 ]; then
  echo "::error::no layout test files found (git ls-files 'layout/**/test_*.py')" >&2
  exit 1
fi

total=0
failed=()
for d in "${dirs[@]}"; do
  echo "== $d"
  log="$(mktemp)"
  # A failing directory must not hide the rest: record it and keep going.
  rc=0
  python3 -m unittest discover -s "$d" -p 'test_*.py' 2>&1 | tee "$log" || rc=$?
  n="$(sed -n 's/^Ran \([0-9]*\) test.*/\1/p' "$log" | tail -1)"
  skipped="$(grep -cE '^(OK|FAILED) \(.*skipped=' "$log" || true)"
  rm -f "$log"
  if [ -z "$n" ] || [ "$n" -eq 0 ]; then
    echo "::error::zero tests collected in $d" >&2
    failed+=("$d")
    continue
  fi
  if [ "$rc" -ne 0 ]; then
    echo "::error::tests failed in $d" >&2
    failed+=("$d")
  fi
  if [ "$require_no_skips" -eq 1 ] && [ "$skipped" -gt 0 ]; then
    echo "::error::tests skipped in $d (--require-no-skips)" >&2
    failed+=("$d")
  fi
  total=$((total + n))
done
echo "layout unit tests: $total run across ${#dirs[@]} directories"
if [ "${#failed[@]}" -gt 0 ]; then
  echo "::error::layout tests failed in: ${failed[*]}" >&2
  exit 1
fi
