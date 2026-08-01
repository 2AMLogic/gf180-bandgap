#!/usr/bin/env bash
# test-gh-cached-repo-scope.sh - Repo-scoping tests for .loom/scripts/gh-cached (#46)
#
# The wrapper used to key cache entries on the joined `gh` argv alone, while
# storing every entry in one shared, unnamespaced directory. Two repos on the
# same host running an identical read (the Judge/Sweep/Champion polling shape
# `gh pr list --label=... --state=open`) collided on one entry and silently
# served each other's results.
#
# These tests pin the fix without touching the network: a fake `gh` on PATH
# echoes a per-repo marker, so a leaked cache entry shows up as repo A's marker
# appearing in repo B's stdout.
#
# Cases:
#   1. identical argv in two different repos -> different cache dirs, no leak
#   2. repeated read in one repo -> cache HIT (caching still works)
#   3. two linked worktrees of the SAME repo -> shared cache (a hit, not a miss)
#   4. --clear-cache in repo A leaves repo B's entries intact
#   5. -R owner/repo and GH_REPO override the cwd's repo
#   6. non-git directory -> stable cwd-scoped key, no crash
#   7. --cache-stats / --version / --no-cache still behave
#
# Usage:
#   ./.loom/scripts/tests/test-gh-cached-repo-scope.sh
#
#   # point at another copy (e.g. the pre-fix one, to confirm it fails):
#   GH_CACHED_BIN=/tmp/gh-cached-old ./.loom/scripts/tests/test-gh-cached-repo-scope.sh

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

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/test-gh-cached.XXXXXX")"
# shellcheck disable=SC2317,SC2329  # invoked indirectly via the EXIT trap below
cleanup() { rm -rf "$WORKDIR" 2>/dev/null || true; }
trap cleanup EXIT

export GIT_AUTHOR_NAME="test" GIT_AUTHOR_EMAIL="test@example.com"
export GIT_COMMITTER_NAME="test" GIT_COMMITTER_EMAIL="test@example.com"

# --- fake gh -----------------------------------------------------------------
# Prints the value of $FAKE_GH_MARKER, so identical argv produces *different*
# output per repo. Any cross-repo leak is therefore visible in stdout.
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

# Shared cache root for every case below — the whole point is that repos are
# isolated *within* one root, exactly as they are on a real multi-repo host.
export GH_CACHE_DIR="$WORKDIR/gh-cache"
unset GH_REPO GH_CACHE_DISABLE GH_CACHE_DEBUG 2>/dev/null || true

# make_repo <path> <remote-url>
make_repo() {
    mkdir -p "$1"
    git -C "$1" init -q
    git -C "$1" remote add origin "$2"
    git -C "$1" commit -q --allow-empty -m "init"
}

# The hottest cached read shape in Loom — the exact call that poisoned #46.
POLL_ARGS=(pr list --label=loom:review-requested --state=open --limit 500)

REPO_A="$WORKDIR/repo-a"
REPO_B="$WORKDIR/repo-b"
make_repo "$REPO_A" "https://github.com/2AMLogic/repo-a.git"
make_repo "$REPO_B" "git@github.com:2AMLogic/repo-b.git"

echo "=== gh-cached repo scoping ==="

# --- 1. identical argv in two repos must not share an entry -------------------
out_a="$(cd "$REPO_A" && FAKE_GH_MARKER="FROM-REPO-A" "$GH_CACHED" "${POLL_ARGS[@]}")"
out_b="$(cd "$REPO_B" && FAKE_GH_MARKER="FROM-REPO-B" "$GH_CACHED" "${POLL_ARGS[@]}")"

if [ "$out_a" = "FROM-REPO-A" ] && [ "$out_b" = "FROM-REPO-B" ]; then
    pass "identical argv in two repos returns each repo's own result"
else
    fail "identical argv in two repos leaked across repos" "A=$out_a B=$out_b"
fi

key_a="$(cd "$REPO_A" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-A" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null | sed -n 's/.*key=\([0-9a-f]*\).*/\1/p' | head -1)"
key_b="$(cd "$REPO_B" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-B" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null | sed -n 's/.*key=\([0-9a-f]*\).*/\1/p' | head -1)"
if [ -n "$key_a" ] && [ -n "$key_b" ] && [ "$key_a" != "$key_b" ]; then
    pass "cache keys differ across repos (A=$key_a B=$key_b)"
else
    fail "cache keys did not differ across repos" "A=$key_a B=$key_b"
fi

ns_count="$(find "$GH_CACHE_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
if [ "$ns_count" = "2" ]; then
    pass "each repo got its own cache namespace directory"
else
    fail "expected 2 namespace directories, found $ns_count" \
        "$(find "$GH_CACHE_DIR" -mindepth 1 -maxdepth 1 | tr '\n' ' ')"
fi

root_entries="$(find "$GH_CACHE_DIR" -maxdepth 1 -name '*.json' -type f | wc -l | tr -d ' ')"
if [ "$root_entries" = "0" ]; then
    pass "no unscoped entries written to the cache root"
else
    fail "found $root_entries unscoped entries in the cache root"
fi

# --- 2. caching still works within one repo -----------------------------------
debug_out="$(cd "$REPO_A" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-A" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null)"
if grep -q "HIT key=" <<<"$debug_out"; then
    pass "repeated read in the same repo is a cache HIT"
else
    fail "repeated read in the same repo did not hit the cache" "$debug_out"
fi

# A second, *different* invocation in repo A must still miss (TTL/keying intact).
if (cd "$REPO_A" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-A" \
        "$GH_CACHED" issue view 42 --json labels 2>&1 >/dev/null) | grep -q "MISS key="; then
    pass "a different command in the same repo still misses"
else
    fail "a different command in the same repo did not miss"
fi

# --- 3. linked worktrees of the same repo share one cache ---------------------
git -C "$REPO_A" worktree add -q -b wt-test "$WORKDIR/repo-a-wt" >/dev/null 2>&1
wt_debug="$(cd "$WORKDIR/repo-a-wt" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-A" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null)"
if grep -q "HIT key=" <<<"$wt_debug"; then
    pass "a linked worktree shares the parent repo's cache"
else
    fail "a linked worktree did not share the parent repo's cache" "$wt_debug"
fi

# --- 4. --clear-cache is repo-scoped ------------------------------------------
before_b="$(find "$GH_CACHE_DIR" -name '*.json' -type f | wc -l | tr -d ' ')"
(cd "$REPO_A" && "$GH_CACHED" --clear-cache >/dev/null 2>&1)
after_all="$(find "$GH_CACHE_DIR" -name '*.json' -type f | wc -l | tr -d ' ')"
b_hit="$(cd "$REPO_B" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-B" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null)"
if grep -q "HIT key=" <<<"$b_hit"; then
    pass "--clear-cache in repo A left repo B's entries intact ($before_b -> $after_all files)"
else
    fail "--clear-cache in repo A wiped repo B's entries" "$b_hit"
fi

a_miss="$(cd "$REPO_A" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-REPO-A" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null)"
if grep -q "MISS key=" <<<"$a_miss"; then
    pass "--clear-cache did clear the invoking repo's own entries"
else
    fail "--clear-cache did not clear the invoking repo's entries" "$a_miss"
fi

# --- 5. -R / GH_REPO override the cwd -----------------------------------------
# The scope must follow the repo gh will actually talk to, not the cwd. Read
# the resolved context straight out of the debug log.
ctx_of() {
    local dir="$1"; shift
    (cd "$dir" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="ctx-probe" "$GH_CACHED" "$@" 2>&1 >/dev/null) \
        | sed -n 's/^\[gh-cached\] CONTEXT \([^ ]*\).*/\1/p' | head -1
}

ctx_b_cwd="$(ctx_of "$REPO_B" "${POLL_ARGS[@]}")"
ctx_r_sep="$(ctx_of "$REPO_A" -R 2AMLogic/repo-b "${POLL_ARGS[@]}")"
ctx_r_eq="$(ctx_of "$REPO_A" --repo=2AMLogic/repo-b "${POLL_ARGS[@]}")"
ctx_r_join="$(ctx_of "$REPO_A" -R2AMLogic/repo-b "${POLL_ARGS[@]}")"
ctx_env="$( (cd "$REPO_A" && GH_CACHE_DEBUG=1 GH_REPO=2AMLogic/repo-b FAKE_GH_MARKER="ctx-probe" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null) \
    | sed -n 's/^\[gh-cached\] CONTEXT \([^ ]*\).*/\1/p' | head -1)"

if [ "$ctx_b_cwd" = "repo:github.com/2amlogic/repo-b" ] \
    && [ "$ctx_r_sep" = "$ctx_b_cwd" ] \
    && [ "$ctx_r_eq" = "$ctx_b_cwd" ] \
    && [ "$ctx_r_join" = "$ctx_b_cwd" ] \
    && [ "$ctx_env" = "$ctx_b_cwd" ]; then
    pass "-R X / -RX / --repo=X / GH_REPO=X all scope to X, overriding cwd"
else
    fail "-R / --repo= / GH_REPO scoping mismatch" \
        "cwd=$ctx_b_cwd -R=$ctx_r_sep --repo==$ctx_r_eq -RX=$ctx_r_join GH_REPO=$ctx_env"
fi

# ssh-form and https-form remotes for the same repo normalize identically.
ctx_a_cwd="$(ctx_of "$REPO_A" "${POLL_ARGS[@]}")"
if [ "$ctx_a_cwd" = "repo:github.com/2amlogic/repo-a" ]; then
    pass "https:// remote normalizes to host/owner/repo ($ctx_a_cwd)"
else
    fail "https:// remote did not normalize as expected" "$ctx_a_cwd"
fi
if [ "$ctx_b_cwd" = "repo:github.com/2amlogic/repo-b" ]; then
    pass "git@host: remote normalizes to host/owner/repo ($ctx_b_cwd)"
else
    fail "git@host: remote did not normalize as expected" "$ctx_b_cwd"
fi

# GH_REPO=repo-b run from repo A's directory must be served repo B's entry
# (same query, same repo) — proving the override beats the cwd.
env_out="$(cd "$REPO_A" && GH_REPO=2AMLogic/repo-b FAKE_GH_MARKER="SHOULD-NOT-APPEAR" \
    "$GH_CACHED" "${POLL_ARGS[@]}")"
if [ "$env_out" = "FROM-REPO-B" ]; then
    pass "GH_REPO override is served repo B's entry, not repo A's"
else
    fail "GH_REPO override did not resolve to repo B's cache" "$env_out"
fi

# ...and the cwd-scoped read in repo A is unaffected by any of the above.
cwd_out="$(cd "$REPO_A" && FAKE_GH_MARKER="FROM-REPO-A-AGAIN" "$GH_CACHED" "${POLL_ARGS[@]}")"
if [ "$cwd_out" != "FROM-REPO-B" ] && [ "$cwd_out" != "SHOULD-NOT-APPEAR" ]; then
    pass "an overridden-scope entry is never served to a cwd-scoped read"
else
    fail "an overridden-scope entry leaked into a cwd-scoped read" "$cwd_out"
fi

# --- 6. non-git directory ------------------------------------------------------
NONGIT="$WORKDIR/plain"
mkdir -p "$NONGIT"
ng1="$(cd "$NONGIT" && FAKE_GH_MARKER="FROM-NONGIT" "$GH_CACHED" "${POLL_ARGS[@]}" 2>/dev/null)"
ng_dbg="$(cd "$NONGIT" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="FROM-NONGIT" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>&1 >/dev/null)"
if [ "$ng1" = "FROM-NONGIT" ] && grep -q "HIT key=" <<<"$ng_dbg"; then
    pass "non-git directory produces a stable cwd-scoped key"
else
    fail "non-git directory did not cache stably" "out=$ng1 dbg=$ng_dbg"
fi

# --- 7. preserved behaviour ----------------------------------------------------
if (cd "$REPO_A" && "$GH_CACHED" --cache-stats 2>&1 >/dev/null) | grep -q "Hit rate:"; then
    pass "--cache-stats still reports hit rate"
else
    fail "--cache-stats output changed"
fi

if [ "$(cd "$REPO_A" && "$GH_CACHED" --version 2>/dev/null)" = "gh version 0.0.0-fake" ]; then
    pass "--version passes through to gh"
else
    fail "--version did not pass through to gh"
fi

nc="$(cd "$REPO_A" && GH_CACHE_DEBUG=1 FAKE_GH_MARKER="NO-CACHE-RUN" \
    "$GH_CACHED" --no-cache "${POLL_ARGS[@]}" 2>/dev/null)"
if [ "$nc" = "NO-CACHE-RUN" ]; then
    pass "--no-cache bypasses the cache"
else
    fail "--no-cache did not bypass the cache" "$nc"
fi

dis="$(cd "$REPO_A" && GH_CACHE_DISABLE=1 FAKE_GH_MARKER="DISABLED-RUN" \
    "$GH_CACHED" "${POLL_ARGS[@]}" 2>/dev/null)"
if [ "$dis" = "DISABLED-RUN" ]; then
    pass "GH_CACHE_DISABLE=1 degrades to plain gh"
else
    fail "GH_CACHE_DISABLE=1 did not degrade to plain gh" "$dis"
fi

# --- 8. legacy unscoped entries are purged ------------------------------------
rm -rf "$GH_CACHE_DIR"
mkdir -p "$GH_CACHE_DIR"
printf '{"time":0,"accessed":0,"ttl":30,"stdout":"stale","returncode":0,"args":[]}\n' \
    >"$GH_CACHE_DIR/deadbeefdeadbeef.json"
(cd "$REPO_A" && FAKE_GH_MARKER="AFTER-PURGE" "$GH_CACHED" "${POLL_ARGS[@]}" >/dev/null 2>&1)
if [ ! -f "$GH_CACHE_DIR/deadbeefdeadbeef.json" ]; then
    pass "pre-namespacing entries in the cache root are purged"
else
    fail "pre-namespacing entries in the cache root were left behind"
fi

# --- 9. cache root is created at mode 0700, not the umask default (#50) -------
# Recreate the whole cache root from scratch (simulates post-reboot / /tmp
# clean) and confirm the *root* itself — not just the per-repo leaf — lands at
# 0700. os.makedirs only applies `mode` to the leaf dir it creates, so the
# root must be created explicitly.
rm -rf "$GH_CACHE_DIR"
(umask 022; cd "$REPO_A" && FAKE_GH_MARKER="ROOT-PERM-CHECK" "$GH_CACHED" "${POLL_ARGS[@]}" >/dev/null 2>&1)
root_mode="$(stat -f '%Lp' "$GH_CACHE_DIR" 2>/dev/null || stat -c '%a' "$GH_CACHE_DIR" 2>/dev/null)"
if [ "$root_mode" = "700" ]; then
    pass "cache root is created at mode 700 regardless of umask"
else
    fail "cache root was not created at mode 700" "got mode $root_mode"
fi

# --- 10. -R false-positive rejection (#50) -------------------------------------
# A value belonging to another flag (e.g. --search "-Reopened") must not be
# misread as a `-R` repo override — it should fall through to the real
# git-remote-derived context instead.
ctx_false_positive="$(ctx_of "$REPO_A" issue list --search "-Reopened")"
if [ "$ctx_false_positive" = "repo:github.com/2amlogic/repo-a" ]; then
    pass "-R false positive (--search \"-Reopened\") does not hijack repo scope"
else
    fail "-R false positive was misread as a repo override" "ctx=$ctx_false_positive"
fi

# Regression guard: a legitimate joined short-flag override must still work.
ctx_legit_join="$(ctx_of "$REPO_A" -R2AMLogic/repo-b "${POLL_ARGS[@]}")"
if [ "$ctx_legit_join" = "repo:github.com/2amlogic/repo-b" ]; then
    pass "legitimate -Rowner/repo joined short-flag override still resolves"
else
    fail "legitimate -Rowner/repo override regressed" "ctx=$ctx_legit_join"
fi

echo
echo "Tests run: $TESTS_RUN, passed: $TESTS_PASSED, failed: $TESTS_FAILED"
[ "$TESTS_FAILED" -eq 0 ] || exit 1
exit 0
