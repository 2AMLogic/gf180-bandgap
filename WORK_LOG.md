# Work Log

Chronological record of recently merged pull requests and closed issues, maintained by the Loom Guide role. Newest entries appear first.

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
