# output-noise unit probe (issue #252)

PDK-free, single-point ngspice diagnostic that fixes the unit convention of the
`noise` analysis vectors the `output-noise` bench reads. It establishes
**simulator units only**; it says nothing about DUT performance.

Run: `./run_probe.sh [outdir]` (two short `ngspice -n -b` runs; no grid).
`-n` skips every `.spiceinit` and `HOME` is pinned to the output dir, so
startup configuration cannot change the result. Captured inputs/outputs of
the recorded run are in `evidence/` (version, both decks, both logs).

Deck: `vin in 0 ac 1; r1 in out 10k; r2 out 0 10k; .temp 27` -> output sees
Req = 5 kohm thermal noise (white). ngspice-42 (`/usr/bin/ngspice`, Debian
build 2024-03-31). Constants: k = 1.380649e-23 J/K, T = 300.15 K.
Sweeps: `dec 20 0.1 10` (41 pts, index 0 = 0.1 Hz, 40 = 10 Hz) and
`dec 20 0.1 100k` (indices 80/100/120 = 1/10/100 kHz).

Analytical references:

| Quantity | Formula | Value |
|---|---|---|
| PSD | 4kT Req | 8.2880e-17 V^2/Hz |
| density | sqrt(4kT Req) | 9.1039e-9 V/sqrt(Hz) |
| band RMS, 0.1-10 Hz | sqrt(4kT Req (10 - 0.1)) | 2.8645e-8 V |
| band mean-square | 4kT Req (10 - 0.1) | 8.2052e-16 V^2 |

Integration convention: the spectrum is white, so the integral over the swept
band is exact regardless of ngspice's trapezoid rule; reference uses
(f_hi - f_lo) = 9.9 Hz. Tolerance: 0.1 % relative (observed agreement better
than 1e-4).

Raw vectors (identical at every index, white spectrum):

| Vector | default (`unset sqrnoise`) | `set sqrnoise` |
|---|---|---|
| `onoise_spectrum[0,20,40]` (0.1 Hz band) | 9.1038635016e-09 | 8.2880330656e-17 |
| `onoise_spectrum[80,100,120]` (1k/10k/100k) | 9.1038635016e-09 | 8.2880330656e-17 |
| `onoise_total` (0.1-10 Hz) | 2.8644637779e-08 | 8.2051527349e-16 |

Conclusion (spectral and integrated vectors checked independently):

- Default mode: `onoise_spectrum` = V/sqrt(Hz) (matches sqrt(4kT R)),
  `onoise_total` = V rms (matches sqrt(4kT R * 9.9)).
- `set sqrnoise`: both are squared (V^2/Hz, V^2).
- The repo never set `sqrnoise`, so the pre-#252 `sqrt()` conversions in
  `tb.json` were a double square root. The bench now only scales
  (`*1e6` uVrms, `*1e9` nV/sqrt(Hz)) and forces default mode with
  `unset sqrnoise`.

Regression: `sim/tests/test_output_noise_units.py` re-runs this probe
(skipped if ngspice is absent) and checks the bench conversions.
