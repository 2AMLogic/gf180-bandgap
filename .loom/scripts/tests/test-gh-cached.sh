#!/usr/bin/env bash
# test-gh-cached.sh - General (non-repo-scoping) tests for .loom/scripts/gh-cached
#
# Repo-scoping behaviour (context resolution, -R/GH_REPO overrides, cache
# namespacing) is covered separately in test-gh-cached-repo-scope.sh. This
# file covers wrapper-level degrade contracts that don't depend on multiple
# repos.
#
# Cases:
#   1. a deleted cwd degrades to plain `gh` instead of raising (#50, fix 3)
#
# Usage:
#   ./.loom/scripts/tests/test-gh-cached.sh
#
#   # point at another copy (e.g. the pre-fix one, to confirm it fails):
#   GH_CACHED_BIN=/tmp/gh-cached-old ./.loom/scripts/tests/test-gh-cached.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GH_CACHED="${GH_CACHED_BIN:-$(cd "$SCRIPT_DIR/.." && pwd)/gh-cached}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

pass() {
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: $1"
}

fail() {
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: $1"
    [ $# -gt 1 ] && echo "        $2"
}

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/test-gh-cached-general.XXXXXX")"
# shellcheck disable=SC2317,SC2329  # invoked indirectly via the EXIT trap below
cleanup() { rm -rf "$WORKDIR" 2>/dev/null || true; }
trap cleanup EXIT

# --- fake gh -------------------------------------------------------------------
FAKE_BIN="$WORKDIR/bin"
mkdir -p "$FAKE_BIN"
cat >"$FAKE_BIN/gh" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
    echo "gh version 0.0.0-fake"
    exit 0
fi
echo "${FAKE_GH_MARKER:-unset}"
EOF
chmod +x "$FAKE_BIN/gh"
export PATH="$FAKE_BIN:$PATH"

export GH_CACHE_DIR="$WORKDIR/gh-cache"
unset GH_REPO GH_CACHE_DISABLE GH_CACHE_DEBUG 2>/dev/null || true

echo "=== gh-cached general behaviour ==="

# --- 1. a deleted cwd degrades to plain gh instead of raising (#50, fix 3) ----
# Every local git probe fails once cwd is gone, so resolve_repo_context() falls
# all the way through to its final os.getcwd() fallback — which itself raises
# FileNotFoundError when cwd no longer exists. The wrapper's contract is to
# never raise; confirm it produces output and a clean exit instead of an
# uncaught traceback.
# Run `cd` + `rmdir` back-to-back in a throwaway `bash -c`, then invoke the
# wrapper with a genuinely-vanished cwd. Skip gracefully on platforms that
# refuse to let a process keep running once its cwd is gone.
result="$(bash -c '
    dir="$1"; shift
    mkdir -p "$dir"
    cd "$dir" || exit 99
    rmdir "$dir" 2>/dev/null || rm -rf "$dir" 2>/dev/null
    FAKE_GH_MARKER="DEGRADED-OK" "$@" issue list
    echo "RC=$?"
' bash "$WORKDIR/deleted-cwd-2" "$GH_CACHED" 2>&1)"

if [[ "$result" == *"RC=99"* ]]; then
    echo "  SKIP: platform would not allow invoking a process from a deleted cwd"
elif [[ "$result" == *"Traceback"* ]]; then
    fail "deleted cwd raised an uncaught traceback instead of degrading" "$result"
elif [[ "$result" == *"DEGRADED-OK"* ]] && [[ "$result" == *"RC=0"* ]]; then
    pass "deleted cwd degrades to plain gh (exit 0, no traceback)"
else
    fail "deleted cwd did not degrade as expected" "$result"
fi

echo
echo "Tests run: $TESTS_RUN, passed: $TESTS_PASSED, failed: $TESTS_FAILED"
[ "$TESTS_FAILED" -eq 0 ] || exit 1
exit 0
