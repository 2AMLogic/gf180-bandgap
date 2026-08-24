# bandgap comp data (generated, public-sources-only)

Generated 2026-08-24 from the upstream comp library's `bandgap.md` entry by an internal, private-repo-only tool. This is a derived, filtered copy — regenerate rather than hand-edit. Every row below cites a public vendor datasheet or a public distributor pricing page; nothing internal survived extraction.

## Comparable parts

| Vendor | Part | Type | Output | Accuracy | Temp coefficient | Iq | Package | Source |
|---|---|---|---|---|---|---|---|---|
| Texas Instruments | LM4040 | Shunt (2-terminal) reference | 2.048/2.5/3.0/4.096/5.0/8.192/10 V fixed options | 0.1% max (A grade) to 1.0% max (D grade) | 100 ppm/°C max (A/B/C), 150 ppm/°C max (D) | 45 µA typ minimum operating current (up to 15 mA) | SOT-23-3 / SC70-5 / TO-92-3 | Datasheet: [ti.com/lit/ds/symlink/lm4040.pdf](https://www.ti.com/lit/ds/symlink/lm4040.pdf) (SLOS456Q) |
| Texas Instruments | TL431 / TL432 | Adjustable shunt regulator/reference | V_ref ≈ 2.5 V to 36 V via external divider | 0.5% (B grade), 1% (A), 2% (Standard) | not separately headlined (temp drift 6–14 mV typical, C/I/Q temp) | not applicable (sink current 1–100 mA) | SOT-23-3/5, SOIC-8, PDIP-8, SOP-8 | Datasheet: [ti.com/lit/ds/symlink/tl431.pdf](https://www.ti.com/lit/ds/symlink/tl431.pdf) (SLVS543S) |
| Texas Instruments | REF2030 (REF20xx family) | Series (3-terminal) dual-output reference | V_REF + V_REF/2, e.g. 3.0 V + 1.5 V | ±0.05% max initial | 8 ppm/°C max (−40…125 °C) | 360 µA typ | SOT-23-5 | Datasheet: [ti.com/lit/ds/symlink/ref2030.pdf](https://www.ti.com/lit/ds/symlink/ref2030.pdf) (SBOS600E) |

## Sources

| URL | Establishes | Fetched |
|---|---|---|
| https://www.ti.com/lit/ds/symlink/lm4040.pdf | LM4040 accuracy grades, temp coefficient, Iq range, package | 2026-08-20 |
| https://www.ti.com/lit/ds/symlink/tl431.pdf | TL431/TL432 accuracy grades, output range, package | 2026-08-20 |
| https://www.ti.com/lit/ds/symlink/ref2030.pdf | REF2030 accuracy, temp coefficient, Iq, package | 2026-08-20 |

