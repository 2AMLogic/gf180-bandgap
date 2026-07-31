v {xschem version=3.4.7 file_version=1.2
* bandgap_amp -- provisional 5-transistor OTA (issue #8)
*
* Real-device 5T single-stage OTA used ONLY to close the bandgap_core servo
* loop for schematic entry / smoke-test purposes. Sizing is PROVISIONAL --
* final offset-budgeted sizing is #10's scope (see
* design/bandgap_operating_point.md). Input pair and mirror load sized
* 10um/4um to match the MOS-mismatch characterization geometry in
* sim/device-mos-mismatch (record 20260731-031718-8fb0ea6), so the amp's
* own input-referred offset can be cited directly from that record without
* re-measurement.
*
* Deliberately real devices (nfet_03v3 / pfet_03v3), not a behavioral E/G
* source: the tail current is mirrored from bandgap_core's own bias network
* via the tail_bias pin, so if the core sits in its zero-current degenerate
* state (no startup circuit yet -- #11), tail_bias relaxes toward 0V, M5
* turns off, and this amp goes to zero current right along with it. An
* idealized VCVS/behavioral amp would mask that degenerate state instead of
* reproducing it.
*
* Pins: vdd, vss, in_p, in_n, out, tail_bias
}
G {}
K {}
V {}
S {}
E {}
C {symbols/nfet_03v3.sym} 0 0 0 0 {name=M1 model=nfet_03v3 W=10u L=4u nf=1 m=1}
N 20 -30 20 -50 {}
C {lab_pin.sym} 20 -50 0 0 {name=l1 lab=nd1}
N -20 0 -40 0 {}
C {lab_pin.sym} -40 0 0 0 {name=l2 lab=in_p}
N 20 30 20 50 {}
C {lab_pin.sym} 20 50 0 0 {name=l3 lab=tail}
N 20 0 40 0 {}
C {lab_pin.sym} 40 0 0 0 {name=l4 lab=vss}
C {symbols/nfet_03v3.sym} 250 0 0 0 {name=M2 model=nfet_03v3 W=10u L=4u nf=1 m=1}
N 270 -30 270 -50 {}
C {lab_pin.sym} 270 -50 0 0 {name=l5 lab=out}
N 230 0 210 0 {}
C {lab_pin.sym} 210 0 0 0 {name=l6 lab=in_n}
N 270 30 270 50 {}
C {lab_pin.sym} 270 50 0 0 {name=l7 lab=tail}
N 270 0 290 0 {}
C {lab_pin.sym} 290 0 0 0 {name=l8 lab=vss}
C {symbols/pfet_03v3.sym} 0 250 0 0 {name=M3 model=pfet_03v3 W=10u L=4u nf=1 m=1}
N 20 280 20 300 {}
C {lab_pin.sym} 20 300 0 0 {name=l9 lab=nd1}
N -20 250 -40 250 {}
C {lab_pin.sym} -40 250 0 0 {name=l10 lab=nd1}
N 20 220 20 200 {}
C {lab_pin.sym} 20 200 0 0 {name=l11 lab=vdd}
N 20 250 40 250 {}
C {lab_pin.sym} 40 250 0 0 {name=l12 lab=vdd}
C {symbols/pfet_03v3.sym} 250 250 0 0 {name=M4 model=pfet_03v3 W=10u L=4u nf=1 m=1}
N 270 280 270 300 {}
C {lab_pin.sym} 270 300 0 0 {name=l13 lab=out}
N 230 250 210 250 {}
C {lab_pin.sym} 210 250 0 0 {name=l14 lab=nd1}
N 270 220 270 200 {}
C {lab_pin.sym} 270 200 0 0 {name=l15 lab=vdd}
N 270 250 290 250 {}
C {lab_pin.sym} 290 250 0 0 {name=l16 lab=vdd}
C {symbols/nfet_03v3.sym} 125 -250 0 0 {name=M5 model=nfet_03v3 W=10u L=4u nf=1 m=1}
N 145 -280 145 -300 {}
C {lab_pin.sym} 145 -300 0 0 {name=l17 lab=tail}
N 105 -250 85 -250 {}
C {lab_pin.sym} 85 -250 0 0 {name=l18 lab=tail_bias}
N 145 -220 145 -200 {}
C {lab_pin.sym} 145 -200 0 0 {name=l19 lab=vss}
N 145 -250 165 -250 {}
C {lab_pin.sym} 165 -250 0 0 {name=l20 lab=vss}
C {iopin.sym} -150 250 0 0 {name=p1 lab=vdd}
C {iopin.sym} -150 -250 0 0 {name=p2 lab=vss}
C {iopin.sym} -150 60 0 0 {name=p3 lab=in_p}
C {iopin.sym} -150 -60 0 0 {name=p4 lab=in_n}
C {iopin.sym} 450 60 0 0 {name=p5 lab=out}
C {iopin.sym} -150 -400 0 0 {name=p5b lab=tail_bias}
