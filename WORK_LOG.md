# Work Log

Chronological record of recently merged pull requests and closed issues, maintained by the Loom Guide role. Newest entries appear first.

### 2026-10-09

- **PR #273**: feat(sim): characterization-only output-load sensitivity bench with fleet request and ingestion
- **PR #272**: sim: extract run_device_experiment and record_stamp (#267)
- **PR #271**: DR-0007: #239 fleet evidence run BLOCKED (runner klt version mismatch)
- **Issue #269** (closed): sim: characterize current-DUT output-load sensitivity before A7 ratification
- **Issue #267** (closed): sim device benches: extract the shared main() driver and record_stamp() helper

- **PR #266**: lint: check spec.py limits against README spec table
- **PR #265**: spec: lint decision records (status vocabulary, index, ratified immutability)
- **PR #263**: DR-0007: fleet Monte Carlo mismatch request and ingestion for untrimmed accuracy (#238)
- **PR #260**: test(signoff): exercise signoff validator rejection paths without klt or PDK
- **PR #259**: feat(lint): enforce append-only on signoff/reports (#257)
- **PR #256**: test(sim): unit-cover klt request builders and measure_lumped_r1
- **PR #255**: test(sim): unit tests for device bench extract/build_record
- **PR #254**: test(sim): unit-test dctable/fmt; stop interp_at silently clamping (#249)
- **PR #253**: docs(spec): evidence packet and operator questions for the TBD rows
- **PR #248**: test(sim): unit tests for postlayout_delta
- **PR #247**: feat(sim): fleet adapters + ingestion for psrr-dc, line-regulation, startup
- **PR #246**: ci: run the layout/ unit tests in CI (#245)
- **PR #240**: docs: trim README Status to durable facts
- **Issue #264** (closed): Guard telemetry: retain shared-stash creation protection
- **Issue #262** (closed): lint: check sim/suite/spec.py limits against the ratified README spec table
- **Issue #261** (closed): spec: lint decision records (status vocabulary, index consistency, ratified-record immutability)
- **Issue #258** (closed): tests: exercise signoff validator rejection paths without klt or PDK
- **Issue #257** (closed): signoff: enforce append-only history for committed verdict reports
- **Issue #251** (closed): tests: unit-cover klt request builders and measure_lumped_r1 (request/expected-points invariant)
- **Issue #250** (closed): tests: unit-cover extract/build_record in the five device-* bench run scripts
- **Issue #249** (closed): sim/harness: unit-test dctable/fmt and stop interp_at silently clamping out-of-range sweeps
- **Issue #245** (closed): ci: run the layout/ unit tests in CI (currently only sim/tests run)
- **Issue #242** (closed): sim: add unit tests for postlayout_delta (verdict-bearing, currently untested)
- **Issue #238** (closed): DR-0007: fleet Monte Carlo mismatch request and ingestion for untrimmed accuracy
- **Issue #237** (closed): DR-0007: fleet request and ingestion adapters for startup, PSRR and line regulation
- **Issue #235** (closed): docs: trim README Status paragraph to durable facts; point at signoff/ and WORK_PLAN.md for live state
- **Issue #234** (closed): spec: prepare evidence and ranked operator questions for the three TBD rows

- **Issue #210** (closed): DR-0007: synchronize active embedded benches with final core sizing

- **PR #233**: test: unit tests for mk_dut convert/validate
- **Issue #231** (closed): Add unit tests for sim/tools/mk_dut.py convert and validate
- **PR #232**: sim: sync embedded startup-bench cores to DR-0007 final core (#228)
- **Issue #228** (closed): DR-0007: synchronize embedded startup experiment cores
- **PR #230**: sim: sync embedded diagnostic cores to the DR-0007 final core (#227)
- **Issue #227** (closed): DR-0007: synchronize embedded loop and sensitivity diagnostic cores

### 2026-10-08

- **PR #224**: tests: unit-cover pure helpers in run_mc_untrimmed.py
- **Issue #223** (closed): tests: unit-cover the pure netlist/parse helpers in sim/mc-untrimmed/run_mc_untrimmed.py
- **PR #222**: DR-0007: retune canonical R2/R1 from measured array evidence (#209)
- **Issue #209** (closed): DR-0007: retune canonical R2 and R1 from measured array evidence
- **PR #218**: sim/harness: reject simulator errors even when every PVT measurement parsed
- **Issue #216** (closed): Reject simulator error diagnostics even when all PVT measurements are present
- **PR #217**: Suite completion must require all benches and complete gated measurements
- **Issue #215** (closed): Suite completion must require all benches and complete gated measurements
- **PR #213**: sim: record equal-Ie Q2 array ratio on the gf180 fleet (DR-0007 item 1)
- **Issue #208** (closed): DR-0007: record equal-Ie Q2 array ratio on the gf180 fleet

### 2026-10-03

- **PR #201**: design: Q2 as 4x unit PNP array, rescale R2, ratify DR-0007 (#87)

### 2026-09-24

- **Issue #156** (closed): bandgap_top.gds is 58.5% over the ratified 0.05 mm^2 area budget (stale committed GDS masked it)
- **PR #177**: spec: narrow interim area ceiling to 0.066mm² (DR-0006, ratification-via-PR)
- **Issue #191** (closed): main worktree stuck dirty: uncommitted resync (0.19.172) diverged from origin's merged resync (0.19.168)

### 2026-09-23

- **Issue #200** (closed): README: embed the fleet burndown chart (one line)

### 2026-09-22

- **Issue #193** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **Issue #196** (closed): Decide: does signoff/ (PR #194) supersede, coexist with, or fold into docs/t1-gap.md (merged via #195)?
- **PR #194**: feat(signoff): commit a klt signoff block manifest as the T1 verdict of record
- **Issue #197** (closed): 2am: reuse rule 9 — in-tree bandgap amplifier duplicates sibling canary gf180-opamp — add reuse.lock.json in_tree entry (evaluate), then adopt or record
- **PR #199**: chore(reuse): record bandgap_amp in_tree entry against sibling gf180-opamp

### 2026-09-20

- **Issue #192** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo
- **PR #195**: feat(erc): add the klt erc supply read for structural power delivery

### 2026-09-15

- **PR #190**: spec: DR-0007 proposes the 4x unit-PNP array for core.Q2 (Option A)

### 2026-09-10

- **Issue #188** (closed): Output-noise characterization bench `sim/output-noise/`: 0.1–10 Hz integrated + spot noise, full PVT, schematic and extracted provenance (evidence for open item A6)
- **PR #189**: feat: add output-noise characterization bench
