# Final-DUT fleet evidence run (#239) — index and caveats

Execution record for the schematic-signoff evidence run of parent #211 / #203.
Everything here was dispatched to the batch fleet (`klt sim --backend batch`,
runner klt 0.7.0, `runner_compatibility: match`); no grid ran on the shared
worker. **Status: NOT complete** — the Iq row has no ingested record (below),
so the suite summary reports it missing and no schematic-signoff claim is made.

## Frozen identity

- DUT `sim/dut/bandgap_top.spice` sha256
  `9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`
  (last touched at `aeaca90e`; unchanged by this work).
- Startup keeps its embedded, lumped-R1 core (`sim/startup-embedded-core-sync.md`):
  its record states the canonical DUT hash and the frozen embedded-deck hashes
  separately. It is **not** a simulation of the canonical netlist itself
  (lumped R1 is exact at tt/27 C only; -0.18 % / +0.27 % at -40 / 125 C;
  res_ff/res_ss not exercised).

## Gated records (new, append-only)

| Bench | Record | Fleet jobs | Ingest verdict |
|---|---|---|---|
| output-voltage-tc (TC + accuracy corner leg) | `sim/output-voltage-tc/records/20261016-010723-ee8a503.md` | `klt-sim-0c69cf4d5380` | PASS, 27/27 units |
| mc-untrimmed (mismatch leg, N=300 x 4 groups x 3 T) | `sim/mc-untrimmed/records/20261016-013258-999e5cf.md` | 12 jobs, see below | PASS, 12/12 (group, T) |
| psrr-dc | `sim/psrr-dc/records/20261016-013458-999e5cf.md` | `klt-sim-610ff16ed2e5` (ac), `klt-sim-a41bfd33698c` (op) | PASS, 81/81 |
| line-regulation | `sim/line-regulation/records/20261016-013457-999e5cf.md` | `klt-sim-6bd92f45e204` | PASS, 27/27 |
| startup | `sim/startup/records/20261016-013501-999e5cf.md` | `klt-sim-65f1d9a69c86` (2.97 V), `klt-sim-ab314a07cded` (3.30 V), `klt-sim-ac4f1a288f92` (3.63 V) | PASS, 81/81 |

MC jobs: ctrl `61e2ee276ffb`(27C) `2ec4ccc1703b`(-40C) `209c174715cb`(125C);
res `f90e30212a59`(27C) `95ec28f7189f`(-40C) `93812e3b65a9`(125C);
fetbjt `4e61cc3445e8`(27C) `2b451ac216e8`(-40C) `31be9d43cf08`(125C);
all `84d1d0309d42`(27C) `b5799a789b7e`(-40C) `9969549de217`(125C)
(all `klt-sim-` prefixed).

Combined two-legged accuracy verdict, records pinned explicitly:
`sim/suite/combined/20261016-013300-999e5cf.md` — **PASS**, 0 of 81 corners
fail; tightest margin 1.356 mV (bjt_ff / 125 C / 3.63 V). The report itself
flags that the `par_r` x2 sensitivity case flips 3 corners at 125 C, so the
coefficient needs validating before the verdict is final. Ratified limits were
not touched.

Suite roll-up over exactly these records (no simulation started):
`sim/suite/summaries/20261016-013600-999e5cf.md` — 5/5 gated lines with
evidence pass; **not simulation-complete** because Iq is missing.

## Iq — raw only, no verdict

`sim/iq/fleet-raw/20261016-klt-sim-ec2e1a1364c1/` archives the final-DUT iq run
(27/27 units returned; worst Iq 33.84 uA at ff / 3.63 V / 125 C vs the 50 uA
limit). It is **raw, un-ingested evidence**: there is no iq ingestion adapter,
so no completeness or limit check was applied by tooling. It must not be read
as a gated PASS.

## Not performed

- Iq ingestion/record (adapter missing; follow-up).
- Fleet reruns of the six diagnostic benches that embed `bandgap_core`
  (`sim/embedded-core-inventory.md`). Those are diagnostic/reference evidence,
  never gated rows. `sim/tools/check_embedded_cores.py` (static) reports
  10/10 embedded cores in sync with the canonical DUT.
- Noise and Load remain unclaimed (operator-owned thresholds).
- Handoff to #204: not done — it requires complete schematic evidence.

## Tooling defects found and fixed on the way

Each of these only surfaced on the first real fleet run and would otherwise
have produced invalid or unlintable evidence:

1. `mk_klt_request.py iq` used a one-point `dc temp 27 27 1` sweep; ngspice 46
   rejects `FIND ... AT=` on it (every unit errored, locally too). It also
   covered only 27 C although the spec binds at 125 C. Now sweeps -40..125 C.
2. `fleet_ingest.py` cross-checked `.meas` prints at 7 digits; the fleet's
   ngspice 46 prints 6, which marked every line-regulation unit invalid.
   Tolerance widened to one unit in the 6th digit; gated values still come
   from the waveform.
3. `fleet_ingest.py` wrote `corners/<record>/series/` and per-request
   `netlist-snapshots/<record>.<name>.spice`, both rejected by
   `sim/check_records.py` (the ratified layout is flat). Now flat, with one
   `netlist-snapshots/<record>.spice` and per-request decks under `corners/`.

## Fleet history (nothing hidden)

- Probe `klt-sim-f7c59498005d` (iq, one-point sweep): 27/27 units errored — defect 1.
- Earlier blocker `klt-sim-981a3e6e3e40` (runner klt 0.5.0): recorded in
  `sim/fleet-blockers/20261009-issue-239-runner-version-mismatch/`; the runner
  is now 0.7.0 and matches.
- Several submits were refused for fleet capacity (`BATCH_MAX_CONCURRENT_INSTANCES=8`,
  then shared `BATCH_MAX_VCPU=224`); they were resubmitted to the fleet, never run
  locally.
- `klt-sim-48e2a2da3ef7` is an intermediate iq run (27 C only) superseded by the
  full-span run above.
