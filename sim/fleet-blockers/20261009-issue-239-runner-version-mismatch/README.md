# Issue #239 fleet dispatch blocked: runner/client klt version mismatch (2026-10-09)

Diagnostic record only. It is NOT a gated evidence record and no analog
result is claimed. Spec limits are unchanged.

- Frozen DUT: `sim/dut/bandgap_top.spice` sha256
  `9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`,
  source commit `4d3b0c59321dfdfef87c13c0ee150a353c443b17`.
- Submitting client: `klt 0.7.0+gb82427b30c96`, `KLT_SIM_BACKEND=batch`.
- Fleet runner (worker image) klt: `0.5.0`.

Probes (each `klt sim --backend batch ... --format json`):

| bench | job id | result |
|---|---|---|
| iq (27 corner units) | `klt-sim-ff7b46643204` | all 27 `batch_job_failed`, exit 87, `runner_compatibility: mismatch` |
| MC mm_all_27c (300 samples) | `klt-sim-ab32333126ca` | all 300 `batch_job_failed`, exit 87, `runner_compatibility: mismatch` |

The runner's preflight (`batch_runner_version_mismatch`) rejected the request
before any simulation ran. Nothing was run locally as a substitute. Submitting
with the matching `klayout-tools==0.5.0` is not possible: 0.5.0 has no `batch`
backend (only `local`, `local-parallel`, `remote`) and predates the
`monte_carlo` request field. Overriding `runner_version_check` was not done: it
would let the 0.5.0 runner silently ignore request options, which would
corrupt the evidence.

Fix required outside this repo: rebake the batch runner image with a klt pin
matching the client (see 2am `infra/aws/batch-image-pins.env`). The remaining
plans (tc, psrr-dc ac/op, line-regulation, startup x3, 12 MC requests) were
generated successfully but not dispatched, since the same preflight rejects
all of them.
