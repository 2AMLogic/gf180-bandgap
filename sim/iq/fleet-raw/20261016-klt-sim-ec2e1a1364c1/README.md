# iq fleet run (raw, not ingested) — #239

Raw, append-only archive of a final-DUT `iq` run on the batch fleet. **This is
not a sim record and carries no gated verdict**: no iq ingestion adapter exists
yet (`tc_ingest.py` covers output-voltage-tc only), so nothing here has been
through completeness or limit checks by tooling.

- Fleet job: `klt-sim-ec2e1a1364c1` (runner klt 0.7.0, `runner_compatibility: match`)
- Request: `sim/tools/mk_klt_request.py iq` (9 process corners x 2.97/3.30/3.63 V,
  internal `dc temp -40 125 1` sweep, `.meas` at -40/27/125 C)
- DUT: `sim/dut/bandgap_top.spice` sha256
  `9ef5f8c5ab2a61b518befd347c84d7ef0ffe3ea429e94ec3465f66d209ea4560`
- Raw outcome: 27/27 units returned all six measurements (81 isup, 81 vref points).
  Largest Iq 33.84 uA at ff / 3.63 V / 125 C; smallest 13.57 uA at ss / 2.97 V / -40 C;
  Vref over all points 1.18859..1.21109 V. Ratified limit is Iq < 50 uA.
- Rawfiles (`*.raw`) are omitted; logs, decks, request and report are kept.
