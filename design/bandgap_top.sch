v {xschem version=3.4.7 file_version=1.2
* bandgap_top -- top-level wrapper for the testbench suite (issue #8)
*
* Instantiates bandgap_core (Brokaw core + bias/output stage) and
* bandgap_amp (provisional 5T servo op-amp), closing the loop:
*
*   core.fb    <- amp.out
*   core.sns1  -> amp.in_n
*   core.sns2  -> amp.in_p
*   core.ibias -> amp.tail_bias
*
* Exposed pins (minimum set #12's testbench suite needs): vdd, vss, vref.
* Internal nodes (fb, sns1, sns2, ibias) are deliberately NOT exposed at
* this level -- see design/bandgap_operating_point.md if a future testbench
* needs to probe them; add pins there rather than routing around this file.
*
* No startup circuit (#11) and no trim network (#14) -- see
* design/bandgap_operating_point.md for the degenerate-state caveat this
* implies for any DC operating-point sweep of this wrapper.
}
G {}
K {}
V {}
S {}
E {}
C {bandgap_core.sym} 0 0 0 0 {name=x1}
N -40 64 -60 64 {}
C {lab_pin.sym} -60 64 0 0 {name=l1 lab=vdd}
N -40 20 -60 20 {}
C {lab_pin.sym} -60 20 0 0 {name=l2 lab=sns1}
N -40 -6 -60 -6 {}
C {lab_pin.sym} -60 -6 0 0 {name=l3 lab=sns2}
N -40 -60 -60 -60 {}
C {lab_pin.sym} -60 -60 0 0 {name=l4 lab=vss}
N 40 64 60 64 {}
C {lab_pin.sym} 60 64 0 0 {name=l5 lab=fb}
N 40 20 60 20 {}
C {lab_pin.sym} 60 20 0 0 {name=l6 lab=vref}
N 40 -6 60 -6 {}
C {lab_pin.sym} 60 -6 0 0 {name=l7 lab=ibias}
C {bandgap_amp.sym} 600 300 0 0 {name=x2}
N 570 324 550 324 {}
C {lab_pin.sym} 550 324 0 0 {name=l8 lab=sns2}
N 570 296 550 296 {}
C {lab_pin.sym} 550 296 0 0 {name=l9 lab=sns1}
N 570 270 550 270 {}
C {lab_pin.sym} 550 270 0 0 {name=l10 lab=vss}
N 630 324 650 324 {}
C {lab_pin.sym} 650 324 0 0 {name=l11 lab=fb}
N 630 270 650 270 {}
C {lab_pin.sym} 650 270 0 0 {name=l12 lab=vdd}
N 600 240 600 220 {}
C {lab_pin.sym} 600 220 0 0 {name=l13 lab=ibias}
C {iopin.sym} -250 64 0 0 {name=p1 lab=vdd}
C {iopin.sym} -250 -60 0 0 {name=p2 lab=vss}
C {iopin.sym} 250 20 0 0 {name=p3 lab=vref}
