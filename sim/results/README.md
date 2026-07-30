# sim/results — append-only evidence

One subdirectory per testbench; one JSON + one CSV per run, named
`<UTC-timestamp>-<git-short-sha>[-dirty].{json,csv}`.

**Append-only.** Do not edit, rename or delete anything in here. A result that
turned out to be wrong is superseded by a newer run, not removed — the record
of what was believed, and when, is part of the evidence. The writer itself
never overwrites: a name collision takes the next free `.2`, `.3`, ... suffix.

Every JSON record is self-describing and re-runnable: PDK variant and open_pdks
commit, ngspice version, harness version, git commit and dirty flag, the exact
model `.lib` sections per corner, the netlist SHA-256, per-point measurements,
summary statistics and the verdict on every check.

A run whose git state is `-dirty` was taken against uncommitted sources. That is
fine while iterating; anything cited as a result should come from a clean tree.
