# gf180-bandgap — agent instructions

Open-source canary block: a bandgap voltage reference on the gf180mcu PDK,
designed and verified by AI agents. First canary block.

- **PDK**: gf180mcu (open PDK), 3.3V flavor primary. Open-source flow:
  xschem + ngspice for design/sim, klayout-tools (`klt`) for layout work.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue
  at `2AMLogic/klayout-tools` describing the tool gap generically — that
  tracker is scoped to the tool, so keep design-specific detail (spec
  values, this repo's content) out of it and describe the gap, not the
  design.
- **Verification is the product**: no claim without a testbench. PVT
  corners (−40/27/125 °C, ±10% supply, process corners) on every result
  that gets recorded. `sim/` results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not
  relax the ratified spec to make results pass.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) v0.7.0 installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->
