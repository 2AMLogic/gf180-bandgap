# Why item 4's LVS `match` stopped reproducing (gf180-bandgap#378)

**Verdict: not a layout short. A deck change in klt (klayout-tools#1084, first
released in 0.3.0) made the extractor recognise well/substrate ties; the
committed reference still encodes the old deck's blindness to them.**

## Evidence (all on the unchanged GDS, sha256 `3e1af18e…`)

| klt | deck hash | result vs committed `bandgap_top.ref.spice` |
|---|---|---|
| historical `20260819-070132-1e66285` (dev build labelled 0.2.0, schema 2) | `e2726af8…` | `match`, 92/92 nets, 164/164 devices |
| 0.2.0 release (PyPI; klayout 0.30.10 and 0.30.12) | `1256c45b…` (= `_history.json` v0.2.0) | `mismatch`, 90/92 nets, 1 `device.property` (a different, pre-#1084 deck) |
| 0.3.0, 0.4.0, 0.5.0, 0.6.0, 0.7.0, pin `67e684ed`, `d5893304` | differ per release | `mismatch`, 82 layout nets, 111/164 devices, 10 `net.merged` |
| 0.3.0 with only `tap_nplus`/`tap_pplus` set to `None` (scratch copy, not committed) | `bac57e65…` | `match`, 92/92 nets, 164/164 devices, same categories as the historical envelope |

The historical envelope is therefore not reproducible by any released klt: its
deck hash matches no entry in klt's `decks/_history.json`. The switch is
between 0.2.0 and 0.3.0, and removing the #1084 derived tap region alone
restores it.

## What the "merges" are

The ten reference nets that collapse are exactly the old-deck stand-ins for
ties the layout really draws:

* `vsubs` (separate substrate pin) -> `vss`
* `nwl` (PMOS band Nwell, floating) -> `vdd`
* eight `nw_<unit>` (each PNP's Nwell/base, floating) -> `vss`

`design/netlist/bandgap_top.spice` draws every PNP as `XQn vss vss <emitter>`
(base and collector on `vss`), which is what the tie-aware extraction now
returns. `make_reference.py` says as much in its own comments ("the extraction
deck never connects Nwell to Contact").

## Proof the layout is otherwise unchanged

`tie_reference.py` applies only those three aliases to the committed reference
(and drops the now-redundant `vsubs` pin). Against that
`bandgap_top.ref-tied.spice`, the **same GDS** gives `match` (82/82 nets,
164/164 devices, 3/3 pins) under klt 0.3.0, 0.4.0, 0.5.0, 0.6.0, 0.7.0, host
0.7.1.dev2573, pin `d5893304` and the current `signoff/klt-pin.txt` pin
`67e684ed`. The appended envelope is
`reports/bandgap_top/20261024-031858-5f771e3.lvs-tied*` (pin `67e684ed`,
klayout 0.30.12).

## Caveats

* The old `20260819-070132-1e66285.*` envelope is untouched.
* `match` with `topology` warnings (6) and, on newer klt,
  `device.geometry_not_compared` (3) is the same status class the historical
  envelope reported (it carried 12 topology warnings); no error-severity item remains.
* `make_reference.py` / `run_lvs.py` still emit and use the old-deck reference;
  moving them to the tie-aware form is a separate change.
* Resistor values (`Rcore_R1`/`R2`) in the committed reference were not
  re-derived here; they are not flagged by the comparison.
