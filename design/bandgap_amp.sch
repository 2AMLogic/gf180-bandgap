v {xschem version=3.4.7 file_version=1.2
* bandgap_amp -- telescopic-cascode OTA with explicit dominant-pole
* compensation (issue #42; replaces the 5T single-stage OTA of #10)
*
* Closes the two ratified-spec shortfalls #10 recorded and escalated
* (design/bandgap_error_budget.md Sec 5): untrimmed accuracy and PSRR.
* Both needed a topology change, not more area -- see
* design/bandgap_error_budget.md Sec 2 and Sec 3 for the full derivation,
* the measurements, and why #10's own attempts failed.
*
* ---------------------------------------------------------------- topology
*   M1/M2    NMOS input pair (in_p = core sns2, in_n = core sns1)
*   MC1/MC2  NMOS cascodes on the input pair's drains, gate = ncasc
*   M3/M4    PMOS mirror load (M3 diode side via MC3, M4 output side)
*   MC3/MC4  PMOS cascodes on the mirror load, gate = pbias
*   M5       NMOS tail, gate = tail_bias (bandgap_core.ibias), unchanged
*   MBN2     ground-referenced current sink off tail_bias
*   MBP1     PMOS diode fed by MBN2 -- generates the vdd-referenced
*            cascode-bias rail `pbias` (also the gate bias for MB1)
*   MB1      PMOS current source (mirrors MBP1) feeding the ncasc stack
*   MBD1/2   two stacked NMOS diodes -- generate the ground-referenced
*            NMOS cascode bias `ncasc` = Vgs(MBD1) + Vgs(MBD2)
*   CC       60 um x 60 um MIM (~7.2 pF) from `out` to *vdd*
*
* ----------------------------------------------- why the NMOS cascode (PSRR)
* The core's four PMOS mirror legs have their sources on vdd and their
* gates on this amp's `out` node, so supply rejection requires `out` to
* track vdd 1:1 -- what matters is u = out - vdd, not out itself. For a
* mirror-loaded OTA the amp's supply-referred input error works out to
* exactly 1/(gm1 * Ro,nmos-branch): it depends only on the *NMOS* side's
* output impedance and is independent of the PMOS load's ro. That is why
* #10's attempt at cascoding the *mirror load* could not help and in fact
* made PSRR worse (design/bandgap_error_budget.md Sec 3.4), and why
* cascoding the NMOS side is the fix. Measured: +45.7 dB of worst-corner
* PSRR over #10's sizing.
*
* The NMOS cascode's bias `ncasc` must be *ground*-referenced for this to
* work (a supply-following cascode gate re-introduces the very Vds
* modulation the cascode removes), hence the MBD1/MBD2 diode stack rather
* than a copy of the core's own vdd-referenced MCB/MNB generator.
*
* -------------------------------------------- why the PMOS cascode (offset)
* The offset budget needs the mirror load's input-referred mismatch
* contribution, sigma(M3/M4) * gm3/gm1, driven down. In strong inversion
* that contribution scales as 1/L3 at constant W3, so L3 goes 4 um -> 16 um
* and W3 40 um -> 20 um: lower gm3 (measured gm3/gm1 0.689 -> 0.229) *and*
* more gate area. Lower gm3 means a larger Vov3, which needs the mirror to
* stay saturated with less Vsd headroom -- the wide-swing PMOS cascode
* (MC3/MC4 off `pbias`) is what buys that headroom back, and it also
* removes the systematic Vsd(M3) != Vsd(M4) mirror error the uncascoded
* load had. The input pair grows 100 um -> 200 um (nf=4; a single finger
* tops out at 100 um in this width-binned PDK, and 200/4 = 50 um stays
* inside the same bin as #10's 100/2). Together: 3-sigma amp offset
* 25.06 mV -> 12.6 mV referred to Vref.
*
* --------------------------------------------------- why the explicit cap
* Cascoding buys ~50 dB of extra DC loop gain, which #10's compensation
* (none -- the loop was held together by a parasitic Cgd feedthrough zero)
* cannot absorb: without CC the loop's Nyquist locus crosses the positive
* real axis at |T| = +33 dB, i.e. it encircles the +1 critical point of
* this topology's 1-T characteristic equation, and the startup transient
* oscillates. CC is a real dominant-pole compensation capacitor sized so
* that crossing lands at |T| <= -7 dB at every PVT corner.
*
* CC returns to *vdd*, not vss, deliberately: `out` must track vdd for the
* supply-rejection reason above, and a cap to vss would fight that at
* exactly the frequencies the ratified PSRR row cares about.
*
* Model note: gf180mcu names its MIM capacitor per metal-stack option; the
* 5LM default option is cap_mim_2f0_m4m5_noshield (2 fF/um^2). The older
* `cap_mim_2f0fF` name in the xschem symbol's own template lives in a
* .LIB section (cap_mim) that the corner runner does not load -- see
* sim/harness/corners.py -- so the model attribute is set explicitly here.
*
* --------------------------------------------------------------- bias order
* Every bias node in this amp still collapses with the core in the
* degenerate zero-current state (no independent reference anywhere), which
* is what makes #11's startup circuit do real work rather than being
* masked. The bias chain is deliberately ordered tail_bias -> MBN2 ->
* pbias -> MB1 -> ncasc so that it *cannot latch*: an earlier revision of
* this design took MB1's gate from `nd1`, which rails to vdd when the amp
* is off, so MB1 never turned on and the amp had a second, self-sustaining
* dead state that the startup kick could not clear. tail_bias is driven by
* the core's Mn5 diode, which the startup circuit forces, so the chain
* always comes up.
*
* Deliberately real devices (nfet_03v3 / pfet_03v3), not a behavioral E/G
* source -- see design/bandgap_operating_point.md Sec 4.2.
*
* Pins: vdd, vss, in_p, in_n, out, tail_bias (unchanged from #10, so
* design/bandgap_top.sch and bandgap_amp.sym need no edit)
}
G {}
K {}
V {}
S {}
E {}
C {symbols/pfet_03v3.sym} 0 -400 0 0 {name=M3 model=pfet_03v3 W=20u L=16u nf=1 m=1}
N 20 -430 20 -450 {}
C {lab_pin.sym} 20 -450 0 0 {name=l1 lab=vdd}
N -20 -400 -40 -400 {}
C {lab_pin.sym} -40 -400 0 0 {name=l2 lab=nd1}
N 20 -370 20 -350 {}
C {lab_pin.sym} 20 -350 0 0 {name=l3 lab=a3}
N 20 -400 40 -400 {}
C {lab_pin.sym} 40 -400 0 0 {name=l4 lab=vdd}
C {symbols/pfet_03v3.sym} 250 -400 0 0 {name=M4 model=pfet_03v3 W=20u L=16u nf=1 m=1}
N 270 -430 270 -450 {}
C {lab_pin.sym} 270 -450 0 0 {name=l5 lab=vdd}
N 230 -400 210 -400 {}
C {lab_pin.sym} 210 -400 0 0 {name=l6 lab=nd1}
N 270 -370 270 -350 {}
C {lab_pin.sym} 270 -350 0 0 {name=l7 lab=a4}
N 270 -400 290 -400 {}
C {lab_pin.sym} 290 -400 0 0 {name=l8 lab=vdd}
C {symbols/pfet_03v3.sym} 0 -250 0 0 {name=MC3 model=pfet_03v3 W=40u L=16u nf=1 m=1}
N 20 -280 20 -300 {}
C {lab_pin.sym} 20 -300 0 0 {name=l9 lab=a3}
N -20 -250 -40 -250 {}
C {lab_pin.sym} -40 -250 0 0 {name=l10 lab=pbias}
N 20 -220 20 -200 {}
C {lab_pin.sym} 20 -200 0 0 {name=l11 lab=nd1}
N 20 -250 40 -250 {}
C {lab_pin.sym} 40 -250 0 0 {name=l12 lab=vdd}
C {symbols/pfet_03v3.sym} 250 -250 0 0 {name=MC4 model=pfet_03v3 W=40u L=16u nf=1 m=1}
N 270 -280 270 -300 {}
C {lab_pin.sym} 270 -300 0 0 {name=l13 lab=a4}
N 230 -250 210 -250 {}
C {lab_pin.sym} 210 -250 0 0 {name=l14 lab=pbias}
N 270 -220 270 -200 {}
C {lab_pin.sym} 270 -200 0 0 {name=l15 lab=out}
N 270 -250 290 -250 {}
C {lab_pin.sym} 290 -250 0 0 {name=l16 lab=vdd}
C {symbols/nfet_03v3.sym} 0 -100 0 0 {name=MC1 model=nfet_03v3 W=20u L=16u nf=1 m=1}
N 20 -130 20 -150 {}
C {lab_pin.sym} 20 -150 0 0 {name=l17 lab=nd1}
N -20 -100 -40 -100 {}
C {lab_pin.sym} -40 -100 0 0 {name=l18 lab=ncasc}
N 20 -70 20 -50 {}
C {lab_pin.sym} 20 -50 0 0 {name=l19 lab=n1}
N 20 -100 40 -100 {}
C {lab_pin.sym} 40 -100 0 0 {name=l20 lab=vss}
C {symbols/nfet_03v3.sym} 250 -100 0 0 {name=MC2 model=nfet_03v3 W=20u L=16u nf=1 m=1}
N 270 -130 270 -150 {}
C {lab_pin.sym} 270 -150 0 0 {name=l21 lab=out}
N 230 -100 210 -100 {}
C {lab_pin.sym} 210 -100 0 0 {name=l22 lab=ncasc}
N 270 -70 270 -50 {}
C {lab_pin.sym} 270 -50 0 0 {name=l23 lab=n2}
N 270 -100 290 -100 {}
C {lab_pin.sym} 290 -100 0 0 {name=l24 lab=vss}
C {symbols/nfet_03v3.sym} 0 50 0 0 {name=M1 model=nfet_03v3 W=200u L=4u nf=4 m=1}
N 20 20 20 0 {}
C {lab_pin.sym} 20 0 0 0 {name=l25 lab=n1}
N -20 50 -40 50 {}
C {lab_pin.sym} -40 50 0 0 {name=l26 lab=in_p}
N 20 80 20 100 {}
C {lab_pin.sym} 20 100 0 0 {name=l27 lab=tail}
N 20 50 40 50 {}
C {lab_pin.sym} 40 50 0 0 {name=l28 lab=vss}
C {symbols/nfet_03v3.sym} 250 50 0 0 {name=M2 model=nfet_03v3 W=200u L=4u nf=4 m=1}
N 270 20 270 0 {}
C {lab_pin.sym} 270 0 0 0 {name=l29 lab=n2}
N 230 50 210 50 {}
C {lab_pin.sym} 210 50 0 0 {name=l30 lab=in_n}
N 270 80 270 100 {}
C {lab_pin.sym} 270 100 0 0 {name=l31 lab=tail}
N 270 50 290 50 {}
C {lab_pin.sym} 290 50 0 0 {name=l32 lab=vss}
C {symbols/nfet_03v3.sym} 125 200 0 0 {name=M5 model=nfet_03v3 W=10u L=4u nf=1 m=1}
N 145 170 145 150 {}
C {lab_pin.sym} 145 150 0 0 {name=l33 lab=tail}
N 105 200 85 200 {}
C {lab_pin.sym} 85 200 0 0 {name=l34 lab=tail_bias}
N 145 230 145 250 {}
C {lab_pin.sym} 145 250 0 0 {name=l35 lab=vss}
N 145 200 165 200 {}
C {lab_pin.sym} 165 200 0 0 {name=l36 lab=vss}
C {symbols/nfet_03v3.sym} 600 200 0 0 {name=MBN2 model=nfet_03v3 W=2u L=16u nf=1 m=1}
N 620 170 620 150 {}
C {lab_pin.sym} 620 150 0 0 {name=l37 lab=pbias}
N 580 200 560 200 {}
C {lab_pin.sym} 560 200 0 0 {name=l38 lab=tail_bias}
N 620 230 620 250 {}
C {lab_pin.sym} 620 250 0 0 {name=l39 lab=vss}
N 620 200 640 200 {}
C {lab_pin.sym} 640 200 0 0 {name=l40 lab=vss}
C {symbols/pfet_03v3.sym} 600 -400 0 0 {name=MBP1 model=pfet_03v3 W=1u L=50u nf=1 m=1}
N 620 -430 620 -450 {}
C {lab_pin.sym} 620 -450 0 0 {name=l41 lab=vdd}
N 580 -400 560 -400 {}
C {lab_pin.sym} 560 -400 0 0 {name=l42 lab=pbias}
N 620 -370 620 -350 {}
C {lab_pin.sym} 620 -350 0 0 {name=l43 lab=pbias}
N 620 -400 640 -400 {}
C {lab_pin.sym} 640 -400 0 0 {name=l44 lab=vdd}
C {symbols/pfet_03v3.sym} 850 -400 0 0 {name=MB1 model=pfet_03v3 W=5u L=50u nf=1 m=1}
N 870 -430 870 -450 {}
C {lab_pin.sym} 870 -450 0 0 {name=l45 lab=vdd}
N 830 -400 810 -400 {}
C {lab_pin.sym} 810 -400 0 0 {name=l46 lab=pbias}
N 870 -370 870 -350 {}
C {lab_pin.sym} 870 -350 0 0 {name=l47 lab=ncasc}
N 870 -400 890 -400 {}
C {lab_pin.sym} 890 -400 0 0 {name=l48 lab=vdd}
C {symbols/nfet_03v3.sym} 850 -100 0 0 {name=MBD1 model=nfet_03v3 W=1u L=4u nf=1 m=1}
N 870 -130 870 -150 {}
C {lab_pin.sym} 870 -150 0 0 {name=l49 lab=ncasc}
N 830 -100 810 -100 {}
C {lab_pin.sym} 810 -100 0 0 {name=l50 lab=ncasc}
N 870 -70 870 -50 {}
C {lab_pin.sym} 870 -50 0 0 {name=l51 lab=nb1}
N 870 -100 890 -100 {}
C {lab_pin.sym} 890 -100 0 0 {name=l52 lab=vss}
C {symbols/nfet_03v3.sym} 850 50 0 0 {name=MBD2 model=nfet_03v3 W=1u L=4u nf=1 m=1}
N 870 20 870 0 {}
C {lab_pin.sym} 870 0 0 0 {name=l53 lab=nb1}
N 830 50 810 50 {}
C {lab_pin.sym} 810 50 0 0 {name=l54 lab=nb1}
N 870 80 870 100 {}
C {lab_pin.sym} 870 100 0 0 {name=l55 lab=vss}
N 870 50 890 50 {}
C {lab_pin.sym} 890 50 0 0 {name=l56 lab=vss}
C {symbols/cap_mim_2f0fF.sym} 1100 -250 0 0 {name=CC model=cap_mim_2f0_m4m5_noshield W=60u L=60u m=1}
N 1100 -280 1100 -300 {}
C {lab_pin.sym} 1100 -300 0 0 {name=l57 lab=vdd}
N 1100 -220 1100 -200 {}
C {lab_pin.sym} 1100 -200 0 0 {name=l58 lab=out}
C {iopin.sym} -300 -400 0 0 {name=p1 lab=vdd}
C {iopin.sym} -300 250 0 0 {name=p2 lab=vss}
C {iopin.sym} -300 50 0 0 {name=p3 lab=in_p}
C {iopin.sym} -300 -50 0 0 {name=p4 lab=in_n}
C {iopin.sym} -300 -150 0 0 {name=p5 lab=out}
C {iopin.sym} -300 200 0 0 {name=p5b lab=tail_bias}
