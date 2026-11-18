#!/usr/bin/env bash
# Guard lint.sh's --base-ref fail-closed contract (#518).
#
#   .github/scripts/test_lint_args.sh
#
# Why this exists. lint.sh's --base-ref exists so the append-only evidence
# gates never diff against an unknown base (issue #516). Before #518 an
# explicitly given but *empty* value -- `--base-ref ""` (the empty string is
# a second token, so the argc guard does not fire) or `--base-ref=` (strips
# to "") -- sailed past the parser's `[ -n "$BASE_REF" ]` append test and was
# silently dropped, so the gates fell back to $GITHUB_BASE_REF/origin/main
# with a green gate. ci.yml pre-checks its own MG_BASE, but that guard lives
# in one caller; the option itself must fail closed so every future caller
# that builds `--base-ref "$VAR"` from an unset variable inherits the
# invariant instead of silently re-opening the gap.
#
# What is pinned here:
#   - both empty spellings exit 1 with the non-empty-value message, before
#     any check runs (stdout carries no `== N/10` banner);
#   - the pre-existing missing-value error (`--base-ref` as the last
#     argument) still fires;
#   - a non-empty value is forwarded to both gates, pinned by the
#     `clean against the merge base with <ref>` signature the gates print
#     when they diffed against that ref -- HEAD resolves at any checkout
#     depth, so the signature is deterministic on every runner;
#   - a whitespace-only value is non-empty, so the parser accepts it and the
#     gate it reaches decides (never a silent fall-back to the default base).
#
# Assertions match signature lines rather than lint.sh's overall exit code
# where possible: this test is about the option, not repo lint health, which
# the `lint` CI job gates separately.
#
# Zero dependencies beyond python3, matching the repo's stdlib-only rule.
# Exit codes: 0 pass, 1 a check failed.

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

LINT=".github/scripts/lint.sh"
status=0
fail() {
  echo "::error::$1" >&2
  status=1
}

# One lint.sh invocation: stdout in `out`, stderr in `err`, exit code in `rc`.
out="$(mktemp)"
err="$(mktemp)"
trap 'rm -f "${out}" "${err}"' EXIT
run_lint() {
  rc=0
  bash "${LINT}" "$@" >"${out}" 2>"${err}" || rc=$?
}

echo "== 1/3 given-but-empty values are rejected before any check runs =="
check_empty() {
  local spelling="$1"; shift
  run_lint "$@"
  if [ "${rc}" -ne 1 ]; then
    fail "${spelling}: expected exit 1, got ${rc}"
  elif ! grep -q 'option --base-ref needs a non-empty value' "${err}"; then
    fail "${spelling}: stderr lacks the non-empty-value message (got: $(cat "${err}"))"
  elif grep -q '^== ' "${out}"; then
    fail "${spelling}: checks ran despite the rejected value"
  else
    echo "   ok ${spelling}: rejected, no checks ran"
  fi
}
check_empty '--base-ref ""' --base-ref ""
check_empty '--base-ref=' --base-ref=

echo
echo "== 2/3 the pre-existing missing-value error still fires =="
run_lint --base-ref
if [ "${rc}" -ne 1 ]; then
  fail "--base-ref as last argument: expected exit 1, got ${rc}"
elif ! grep -q 'option --base-ref needs a value' "${err}"; then
  fail "--base-ref as last argument: stderr lacks the needs-a-value message (got: $(cat "${err}"))"
else
  echo "   ok --base-ref with no value: rejected"
fi

echo
echo "== 3/3 non-empty values are accepted and forwarded to the gates =="
check_forwarded() {
  local spelling="$1"; shift
  run_lint "$@"
  if grep -q 'clean against the merge base with HEAD' "${out}" && \
     ! grep -q 'needs a non-empty value' "${err}"; then
    echo "   ok ${spelling}: both gates diffed against HEAD"
  else
    fail "${spelling}: gates did not report diffing against HEAD"
  fi
}
check_forwarded '--base-ref HEAD' --base-ref HEAD
check_forwarded '--base-ref=HEAD' --base-ref=HEAD
run_lint --base-ref " "
if grep -q 'needs a non-empty value' "${err}"; then
  fail '--base-ref " ": rejected as empty -- a whitespace-only value is non-empty; the gate it reaches decides, not the parser'
elif ! grep -q '^== 1/10' "${out}"; then
  fail '--base-ref " ": checks did not run'
else
  echo '   ok --base-ref " ": accepted by the parser, checks ran'
fi

echo
if [ "${status}" -eq 0 ]; then
  echo "lint.sh --base-ref argument handling: all cases pass"
else
  echo "::error::lint.sh --base-ref argument handling failed" >&2
fi
exit "${status}"
