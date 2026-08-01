v {xschem version=3.4.7 file_version=1.2
* bandgap_top -- top-level wrapper for the testbench suite (issue #8),
* now with the issue #11 startup circuit instantiated.
*
* Instantiates bandgap_core (Brokaw core + cascoded current-mode
* bias/output stage, per DR-0001), bandgap_amp (provisional 5T servo
* op-amp) and bandgap_startup (issue #11's current-sensing, self-disabling
* startup circuit), closing the loop and kicking it out of the degenerate
* (zero-current) state:
*
*   core.fb      <- amp.out
*   core.sns1    -> amp.in_n
*   core.sns2    -> amp.in_p
*   core.ibias   -> amp.tail_bias
*   startup.fb   -> core.fb    (kicks the mirror gate low during startup)
*   startup.casc -> core.casc  (kicks the cascode-bias gate low too -- see
*                               bandgap_core.sch's comment on why both are
*                               needed)
*   startup.ibias<- core.ibias (senses whether the core's bias current has
*                               been established, to self-disable)
*
* Exposed pins (minimum set #12's testbench suite needs): vdd, vss, vref --
* UNCHANGED by issue #11. Internal nodes (fb, sns1, sns2, ibias, and the
* core's cascode nodes casc / d1..d4) are deliberately NOT exposed at this
* level -- see design/bandgap_operating_point.md if a future testbench
* needs to probe them; add pins there rather than routing around this file.
*
* No trim network yet (#14). The degenerate-state caveat #8 documented for
* any DC operating-point sweep of this wrapper is resolved by the startup
* circuit below -- see design/bandgap_operating_point.md's startup section
* and sim/startup/, sim/startup-slow-ramp/, sim/startup-state-search/,
* sim/startup-disabled-control/ for the verifying evidence.
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
N 40 -30 60 -30 {}
C {lab_pin.sym} 60 -30 0 0 {name=l14 lab=casc}
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
C {bandgap_startup.sym} 0 -300 0 0 {name=x3}
N -30 -276 -50 -276 {}
C {lab_pin.sym} -50 -276 0 0 {name=l15 lab=vdd}
N -30 -326 -50 -326 {}
C {lab_pin.sym} -50 -326 0 0 {name=l16 lab=vss}
N 30 -266 50 -266 {}
C {lab_pin.sym} 50 -266 0 0 {name=l17 lab=fb}
N 30 -300 50 -300 {}
C {lab_pin.sym} 50 -300 0 0 {name=l18 lab=casc}
N 30 -334 50 -334 {}
C {lab_pin.sym} 50 -334 0 0 {name=l19 lab=ibias}
