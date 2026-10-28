# bandgap_top DRC under klt 0.8.0: root-cause classification (#408, 2026-10-28)

Before: the committed `bandgap_top.gds` (and its generator output) reported
`status: violations`, 39,684 hits, under klt 0.8.0 / klayout 0.30.12 / deck
`0eb6df1b…`
(`reports/bandgap_top/20261028-064527-f32fe48.drc.json`). The last clean
envelope (`20260817-125327-972f6d5`) was klt 0.2.0 / deck `e2726af8…`. The
GDS did not regress; the deck gained rules. After: `status: clean`
(`reports/bandgap_top/20261028-065229-f32fe48.drc.json`).

| Rule family | Hits | Class | Fix |
|---|---:|---|---|
| `contact.width.1` | 8,023 | real geometry | deck 0.8.0 fixes the contact at exactly 0.22 x 0.22 um (`klt drc --list-rules`); `CT` was 240 -> 220 |
| `*.ongrid.1` (all layers) | ~31,000 | real geometry | new deck rule, 0.005 um grid. Sources: odd-nm resistor leg length (`//` floor), trim unit length 2772 nm, contact-column start. All snapped on the 5 nm grid at the source (`plan.snap_grid`, `GRID_NM`) |
| `pplus/nplus.enclosing.poly2.1` | 178 | real geometry | PP.5a/NP.5a want 0.23 um implant past a gate; MOS implants used 0.20 -> `GATE_IMPLANT_ENC = 230` |
| `pplus/nplus.space.1`, `sab.space.1` | 88 | real geometry | adjacent same-implant islands left a 40-100 nm implant sliver: merged (`_bridge_implants`); adjacent resistors (recognised bodies, must not merge) spaced `RES_ISLAND_GAP` apart |
| `comp.tap_distance.{nwell,psub}.lv.1` | 57 | real geometry | DF.13, 20 um at 3.3 V: four full-width body-tap strips between rows (`plan.tap_strip`; not inside matched arrays) |

No deck behaviour was waived and no tool defect was found. Side effects:
resistor legs / trim unit are snapped to the grid (R2 -0.04 %, RPU -0.005 %,
trim unit 2772 -> 2770 nm = -0.07 % of a unit; the LVS reference is generated
from the same plan, so it tracks), and the drawn area grows from 62,325 to
64,925 um^2 (still inside the interim 66,000 um^2 ceiling; the originally
ratified 50,000 um^2 target was already exceeded and stays escalated).
