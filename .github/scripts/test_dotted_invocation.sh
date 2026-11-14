#!/usr/bin/env bash
# Guard the own-directory `sys.path.insert` idiom (#479).
#
#   .github/scripts/test_dotted_invocation.sh                 PDK-free runner
#   .github/scripts/test_dotted_invocation.sh --with-klayout  klayout installed
#
# Why this exists. Several modules in this repo start with
#
#     sys.path.insert(0, <this module's own directory>)
#
# which reads as redundant -- Python does put a *script's* directory on
# sys.path. It does not under `python3 -m <dotted.module>`, where sys.path[0]
# is the CWD instead, and the sibling imports below the insert are then
# unresolvable. #478 proposed deleting 19 of these lines as provably inert and
# burned a full Builder cycle before measurement showed every one is
# load-bearing. Neither existing automated path can catch that: test_layout.sh
# runs `unittest discover -s <dir>`, and lint.sh step 9 runs
# `python3 sim/run_corners.py --list` as a script -- both supply the directory
# by another mechanism. One case fails *silently*:
# layout/common/test_klayout_builder.py imports inside try/except ImportError,
# so losing its insert sets HAVE_KLAYOUT=False and skips all 7 tests, exiting 0.
#
# This script closes that hole in two phases:
#
#   Phase 1 (comments)   Every own-directory insert in the tree is declared in
#                        the table below and carries the shared explanatory
#                        comment, whose last line names the `-m` form. Static,
#                        so it covers all 23 sites on every runner: delete one
#                        insert and the site count stops matching the table.
#   Phase 2 (behaviour)  Every declared target of the selected tier is actually
#                        run via `python3 -m` and must exit 0. Delete an insert
#                        and its target stops importing.
#
# --with-klayout  Assert that this runner has klayout and klt installed, as the
#   CI `signoff` job does. Two coupled effects, both meaning "klayout is here":
#   the 4 `klayout`-tier targets below are exercised (they import klayout.db at
#   module level, so they cannot run on a bare runner), and any unittest target
#   reporting `skipped=` fails. The second is what catches the silent-skip case
#   above, which exits 0 either way; it reuses test_layout.sh's `skipped=`
#   detection, and corresponds to that script's --require-no-skips. The flag is
#   deliberately one knob rather than two, because there is only one fact to
#   state about a runner.
#
# The dotted-target list is explicit on purpose. Deriving it by grepping for
# the idiom would re-introduce exactly the grep-based reasoning that produced
# #478's false premise. Phase 1 greps only to prove the declared list is
# *complete*, never to decide what to run.
#
# Zero dependencies beyond python3, matching the repo's stdlib-only rule.
# Exit codes: 0 pass, 1 a check failed, 2 bad usage.

set -uo pipefail

with_klayout=0
for arg in "$@"; do
  case "${arg}" in
    --with-klayout) with_klayout=1 ;;
    -h|--help) sed -n '2,48p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "usage: $0 [--with-klayout]" >&2; exit 2 ;;
  esac
done

cd "$(git rev-parse --show-toplevel)" || exit 1

# The own-directory idiom, in all three spellings used in this repo. Keep in
# sync with the table below; phase 1 fails if a match is not declared there.
OWN_DIR_RE='sys\.path\.insert\(0, *(str\(Path\(__file__\)\.resolve\(\)\.parent\)|str\(HERE\)|os\.path\.dirname\(os\.path\.abspath\(__file__\)\))\)'

# Files whose only match for OWN_DIR_RE is an *indented* usage example inside a
# module docstring -- prose, not a code site (#479 Out of Scope). The exclusion
# applies only while the match stays indented, so if one of these ever grows a
# real module-level insert, phase 1 starts demanding a comment for it.
DOCSTRING_EXAMPLE_FILES='
layout/common/klayout_builder.py
'

# Declared sites: <tier> <kind> <dotted-target> <source-file>
#
#   tier  base     runs on any runner; klayout  needs --with-klayout
#   kind  unittest run as `python3 -m unittest <dotted.test_module>`
#         help     run as `python3 -m <dotted.module> --help`
#
# 23 sites as measured on 2026-11-14 (#479): the 19 in #478's
# baseline-vs-removed matrix (all `base`) plus the four layout/bandgap_top/
# production modules its enumeration missed, each separately confirmed to stop
# importing under `-m` when its insert is deleted. Those four are `klayout`
# tier because they reach a module-level `import klayout.db` -- directly in
# generate.py, transitively in the other three -- so a bare runner cannot
# distinguish a missing insert from a missing klayout.
EXPECTED_SITES=23
SITES='
base    unittest layout.bandgap_top.test_plan            layout/bandgap_top/test_plan.py
base    unittest layout.bandgap_top.test_routing_budget  layout/bandgap_top/test_routing_budget.py
base    unittest layout.common.test_klayout_builder      layout/common/test_klayout_builder.py
base    unittest layout.common.test_report_id            layout/common/test_report_id.py
base    unittest layout.erc.test_run_erc                 layout/erc/test_run_erc.py
base    unittest layout.lvs.test_make_reference          layout/lvs/test_make_reference.py
base    unittest layout.lvs.test_run_lvs                 layout/lvs/test_run_lvs.py
base    unittest layout.netlist.test_mk_extracted_dut    layout/netlist/test_mk_extracted_dut.py
base    unittest sim.tests.test_evidence_store           sim/tests/test_evidence_store.py
base    help     sim.check_records                       sim/check_records.py
base    help     sim.run_combined_accuracy               sim/run_combined_accuracy.py
base    help     sim.run_corners                         sim/run_corners.py
base    help     sim.run_suite                           sim/run_suite.py
base    help     sim.tools.fleet_ingest                  sim/tools/fleet_ingest.py
base    help     sim.tools.load_ingest                   sim/tools/load_ingest.py
base    help     sim.tools.mc_fleet_ingest               sim/tools/mc_fleet_ingest.py
base    help     sim.tools.mk_klt_fleet_request          sim/tools/mk_klt_fleet_request.py
base    help     sim.tools.mk_klt_mc_request             sim/tools/mk_klt_mc_request.py
base    help     sim.tools.tc_ingest                     sim/tools/tc_ingest.py
klayout help     layout.bandgap_top.area_report          layout/bandgap_top/area_report.py
klayout help     layout.bandgap_top.generate             layout/bandgap_top/generate.py
klayout help     layout.bandgap_top.matching_report      layout/bandgap_top/matching_report.py
klayout help     layout.bandgap_top.routing_budget       layout/bandgap_top/routing_budget.py
'

status=0
fail() {
  echo "::error::$1" >&2
  status=1
}

declared_files="$(mktemp)"
trap 'rm -f "${declared_files}"' EXIT
printf '%s\n' "${SITES}" | awk 'NF == 4 { print $4 }' | sort -u >"${declared_files}"

declared_count="$(printf '%s\n' "${SITES}" | awk 'NF == 4' | wc -l | tr -d ' ')"
if [ "${declared_count}" -ne "${EXPECTED_SITES}" ]; then
  fail "declared ${declared_count} sites, expected ${EXPECTED_SITES} -- the table lost or gained a row; update EXPECTED_SITES deliberately"
fi
if [ "$(wc -l <"${declared_files}" | tr -d ' ')" -ne "${declared_count}" ]; then
  fail "the table declares a source file twice -- each file must hold exactly one own-directory insert"
fi

echo "== phase 1/2: every own-directory insert is declared and commented =="
code_sites=0
while IFS= read -r f; do
  while IFS= read -r lineno; do
    [ -z "${lineno}" ] && continue
    line="$(sed -n "${lineno}p" -- "${f}")"
    # An indented match in a docstring-example file is prose, not code.
    case "${line}" in
      [[:space:]]*)
        if printf '%s\n' "${DOCSTRING_EXAMPLE_FILES}" | grep -qxF -- "${f}"; then
          echo "   skip ${f}:${lineno} (indented docstring example, not a code site)"
          continue
        fi
        ;;
    esac
    code_sites=$((code_sites + 1))
    if ! grep -qxF -- "${f}" "${declared_files}"; then
      fail "${f}:${lineno} is an own-directory sys.path.insert that the SITES table does not declare -- add it (with a dotted target) and comment it, see #479"
      continue
    fi
    above="$(sed -n "$((lineno - 1))p" -- "${f}")"
    case "${above}" in
      *'#'*'-m'*) echo "     ok ${f}:${lineno}" ;;
      *) fail "${f}:${lineno} has no comment naming the \`-m\` form on the line above it (found: ${above}) -- see #479" ;;
    esac
  done < <(grep -nE -- "${OWN_DIR_RE}" "${f}" | cut -d: -f1)
done < <(git ls-files -- '*.py')

if [ "${code_sites}" -ne "${declared_count}" ]; then
  fail "found ${code_sites} own-directory insert code sites in the tree but the table declares ${declared_count} -- was an insert deleted? it is load-bearing under \`python3 -m\`, see #479"
fi
echo "own-directory insert code sites: ${code_sites} (all declared and commented)"

echo
echo "== phase 2/2: each declared target imports under \`python3 -m\` =="
if [ "${with_klayout}" -eq 1 ]; then
  echo "   --with-klayout: klayout-tier targets included; any skipped test fails"
  if ! python3 -c 'import klayout.db' 2>/dev/null; then
    fail "--with-klayout was passed but \`import klayout.db\` fails -- run this flag only where klayout and klt are installed (the CI signoff job)"
  fi
else
  echo "   PDK-free: klayout-tier targets deferred to the signoff job; skips allowed"
fi
ran_targets=0
skipped_targets=0
while read -r tier kind target src; do
  [ -z "${tier:-}" ] && continue
  if [ "${tier}" = "klayout" ] && [ "${with_klayout}" -eq 0 ]; then
    printf '   defer %-46s (klayout tier)\n' "${target}"
    skipped_targets=$((skipped_targets + 1))
    continue
  fi
  log="$(mktemp)"
  rc=0
  case "${kind}" in
    unittest)
      python3 -m unittest "${target}" >"${log}" 2>&1 || rc=$?
      n="$(sed -n 's/^Ran \([0-9]*\) test.*/\1/p' "${log}" | tail -1)"
      skipped="$(grep -cE '^(OK|FAILED) \(.*skipped=' "${log}" || true)"
      if [ "${rc}" -ne 0 ]; then
        tail -15 "${log}" >&2
        fail "python3 -m unittest ${target} exited ${rc} (${src} -- did it lose its own-directory sys.path.insert? see #479)"
      elif [ -z "${n}" ] || [ "${n}" -eq 0 ]; then
        fail "python3 -m unittest ${target} collected zero tests (${src})"
      elif [ "${with_klayout}" -eq 1 ] && [ "${skipped}" -gt 0 ]; then
        grep -E '^(OK|FAILED) \(' "${log}" >&2
        fail "python3 -m unittest ${target} skipped tests under --with-klayout (${src} -- a silent skip here is how losing the insert hides, see #479)"
      else
        printf '      ok %-46s %s tests\n' "-m unittest ${target}" "${n}"
      fi
      ;;
    help)
      python3 -m "${target}" --help >"${log}" 2>&1 || rc=$?
      if [ "${rc}" -ne 0 ]; then
        tail -15 "${log}" >&2
        fail "python3 -m ${target} --help exited ${rc} (${src} -- did it lose its own-directory sys.path.insert? see #479)"
      else
        printf '      ok %-46s\n' "-m ${target} --help"
      fi
      ;;
    *)
      fail "unknown kind '${kind}' in the SITES table (expected 'unittest' or 'help')"
      ;;
  esac
  rm -f "${log}"
  ran_targets=$((ran_targets + 1))
done <<EOF
${SITES}
EOF

if [ "$((ran_targets + skipped_targets))" -ne "${declared_count}" ]; then
  fail "ran ${ran_targets} and deferred ${skipped_targets} targets, which is not the ${declared_count} the table declares"
fi

echo
if [ "${status}" -eq 0 ]; then
  echo "PASS: ${ran_targets} dotted targets import under \`python3 -m\` (${skipped_targets} deferred); all ${code_sites} own-directory inserts declared and commented."
else
  echo "FAIL: the own-directory sys.path.insert guard found problems (see the errors above, and #479)."
fi
exit "${status}"
