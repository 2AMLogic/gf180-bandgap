v {xschem version=3.4.7 file_version=1.2
* bandgap_core -- Brokaw-cell core + cascoded current-mode bias/output stage
* (issue #8)
*
* Ratified topology: DR-0001 (spec/decision-records/0001-bandgap-topology-selection.md).
* Device choices grounded in design/device-characterization.md (issue #4,
* record IDs cited in design/bandgap_operating_point.md).
*
* Two vertical PNPs, diode-connected (base tied to collector tied to vss --
* gf180mcu's vertical PNP collector is the substrate, which must be grounded;
* see design/device-characterization.md section 1 and
* sim/device-pnp-vbe/testbench/tb_pnp_vbe.spice for the same convention),
* biased from four legs of a CASCODED PMOS mirror whose common lower-device
* gate ("fb") is driven by the servo op-amp (bandgap_amp, external -- see
* bandgap_top.sch) and whose common cascode gate ("casc") comes from the
* wide-swing cascode-bias generator below:
*
*   Q1 (pnp_05p00x05p00, unit)      -- branch 1, sensed at sns1
*   Q2 (pnp_10p00x10p00, 4x drawn)  -- branch 2, through PTAT resistor R2,
*                                      sensed at sns2
*   Q3 (pnp_05p00x05p00, unit)      -- output branch, through R1, taps vref
*
* Each leg is M<n> (mirror device, source=vdd, gate=fb) in series with
* MC<n> (cascode device, gate=casc), so every branch node (sns1, sns2, vref,
* ibias) is driven from the cascode drain rather than directly from the
* mirror drain. This is DR-0001's "cascoded current-mode output/bias stage":
* the cascode holds all four mirror drains (d1..d4) at essentially the same
* potential regardless of what the branch node itself sits at, so the
* non-servoed legs (Q3 output branch, bias branch) track the servoed pair
* far more closely than an uncascoded mirror's finite output impedance
* allows, and the reference node is driven from a much higher output
* impedance -- the PSRR win DR-0001 asks for.
*
* The amp forces sns1 = sns2, which forces the PTAT current
* I = dVBE(Q1,Q2) / R2 through every mirror leg. vref = VEB(Q3) + I*R1,
* the classic Brokaw sum.
*
* Cascode-bias generator (MCB + MNB): MCB is a diode-connected PMOS from vdd
* whose current is set by MNB, an NMOS sinking a scaled copy of the core's
* own bias current (gate = ibias). casc = vdd - Vsg(MCB); MCB's W/L and
* MNB's current are scaled (relative to the mirror devices and M5) so that
* Vsg(MCB) ~ Vth + 2*Vov, the classic wide-swing cascode bias point, leaving
* each mirror device roughly one Vov of Vsd -- enough for saturation with
* margin, without wasting the headroom the 3.3V flavor gives us (DR-0001:
* "we can spend that headroom on a cascoded current-mode output stage purely
* for PSRR"). This generator is deliberately self-biased off ibias rather
* than an independent reference, for the same reason the amp's tail is (see
* below): in the degenerate zero-current state the cascode bias collapses
* with the rest of the loop instead of artificially propping it up.
* Sizing here is PROVISIONAL (like the amp's) -- #10 owns the final
* offset/headroom-budgeted sizing pass.
*
* M4 + M5 mirror a copy of the same bias current into a diode-connected
* NMOS (ibias) that the external amp's tail transistor mirrors from --
* self-biased, so that in the startup-less zero-current degenerate state
* (fb ~ vdd, all PMOS off), ibias relaxes toward 0V and the amp's own tail
* current (and therefore its loop gain) collapses right along with the
* core's, rather than an independent bias artificially keeping the amp alive
* in a state the real circuit cannot self-start out of (see
* design/bandgap_operating_point.md, degenerate-state caveat; startup
* circuit itself is #11's scope).
*
* Pins: vdd, vss, fb, sns1, sns2, vref, ibias, casc
*
* "casc" (the wide-swing cascode-bias node driving MC1-MC4's gates) is
* exposed here for issue #11's startup circuit: the degenerate
* (zero-current) state collapses BOTH fb (relaxes toward vdd) and casc
* (relaxes toward vdd) together (see the M4/M5/MCB/MNB self-biasing
* comment above), so a kick branch that only pulls fb low cannot start the
* loop -- MC1-MC4 stay off (Vsg(MCn) = d<n> - casc = 0) and no current
* reaches sns1/sns2/vref/ibias even if M1-M4 turn on. bandgap_startup.sch
* pulls both fb and casc low during startup for exactly this reason. This
* is an internal-wiring addition only -- bandgap_top's external pin set
* (vdd, vss, vref) is unchanged.
*
* TRIM LADDER (issue #14) -- DR-0001's ratified "minimal resistor-trim
* network ... a small number of binary-weighted trim resistor segments,
* switched in via probe-pad straps or a simple fuse/metal-option selection
* at test", sized against README.md's ratified Trim row (1-point resistor
* trim, range >= +/-5%, resolution <= 0.25%/step, >=5 bits equivalent,
* magnitude only, performed at 27 C). Full sizing derivation and the
* coverage argument: design/bandgap_trim_network.md.
*
* The output-branch summing resistor is no longer one device. It is a fixed
* base R1 (e3 -> tn0) in series with XTRIM, a 6-bit binary-weighted unit-
* segment ladder (bandgap_trim.sch, tn0 -> vref). Trim acts on vref alone:
* vref = VEB(Q3) + I*(R1 + Rtrim) and the PTAT current I = dVBE/R2 is set
* entirely by the R2/Q1/Q2 loop, independent of what sits in the output
* branch. Adding series resistance here therefore moves the reference
* MAGNITUDE ONLY, as the ratified Trim row requires -- and the trim curve is
* exactly linear in the selected segment resistance, which
* sim/trim-coverage/ measures rather than assumes.
*
* tn0 is the reserved base tap point; the ladder's own six taps are internal
* to bandgap_trim.sch. No active device is added to the reference path.
*
* THE DEFAULT CODE IS THE MID CODE (32 of 0..63), NOT the code that centres
* vref on 1.200 V: R1 + 32 trim units reproduces the pre-trim drawn 280 um
* summing resistor to within 0.04 ohm (under 1 ppm), so the default
* schematic is electrically the #8/#10/#11 circuit and every record taken
* against it stays valid. Picking the code that lands nearest 1.200 V on a
* given die IS the 1-point trim, and that is a wafer-probe step, not a
* schematic default -- see design/bandgap_trim_network.md.
}
G {}
K {}
V {}
S {}
E {}
C {symbols/pfet_03v3.sym} 0 300 0 0 {name=M1 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 20 330 20 350 {}
C {lab_pin.sym} 20 350 0 0 {name=l1 lab=d1}
C {symbols/pfet_03v3.sym} 0 600 0 0 {name=MC1 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 20 570 20 550 {}
C {lab_pin.sym} 20 550 0 0 {name=lc1a lab=d1}
N -20 600 -40 600 {}
C {lab_pin.sym} -40 600 0 0 {name=lc1b lab=casc}
N 20 600 40 600 {}
C {lab_pin.sym} 40 600 0 0 {name=lc1c lab=vdd}
N 20 630 20 650 {}
C {lab_pin.sym} 20 650 0 0 {name=lc1d lab=sns1}
N -20 300 -40 300 {}
C {lab_pin.sym} -40 300 0 0 {name=l2 lab=fb}
N 20 270 20 250 {}
C {lab_pin.sym} 20 250 0 0 {name=l3 lab=vdd}
N 20 300 40 300 {}
C {lab_pin.sym} 40 300 0 0 {name=l4 lab=vdd}
C {symbols/pnp_05p00x05p00.sym} 0 0 0 0 {name=Q1 model=pnp_05p00x05p00 m=1}
N 20 30 20 50 {}
C {lab_pin.sym} 20 50 0 0 {name=l5 lab=vss}
N -20 0 -40 0 {}
C {lab_pin.sym} -40 0 0 0 {name=l6 lab=vss}
N 20 -30 20 -50 {}
C {lab_pin.sym} 20 -50 0 0 {name=l7 lab=sns1}
C {symbols/pfet_03v3.sym} 300 300 0 0 {name=M2 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 320 330 320 350 {}
C {lab_pin.sym} 320 350 0 0 {name=l8 lab=d2}
C {symbols/pfet_03v3.sym} 300 600 0 0 {name=MC2 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 320 570 320 550 {}
C {lab_pin.sym} 320 550 0 0 {name=lc2a lab=d2}
N 280 600 260 600 {}
C {lab_pin.sym} 260 600 0 0 {name=lc2b lab=casc}
N 320 600 340 600 {}
C {lab_pin.sym} 340 600 0 0 {name=lc2c lab=vdd}
N 320 630 320 650 {}
C {lab_pin.sym} 320 650 0 0 {name=lc2d lab=sns2}
N 280 300 260 300 {}
C {lab_pin.sym} 260 300 0 0 {name=l9 lab=fb}
N 320 270 320 250 {}
C {lab_pin.sym} 320 250 0 0 {name=l10 lab=vdd}
N 320 300 340 300 {}
C {lab_pin.sym} 340 300 0 0 {name=l11 lab=vdd}
C {symbols/ppolyf_u.sym} 300 90 0 0 {name=R2 model=ppolyf_u W=2u L=18u m=1}
N 300 60 300 40 {}
C {lab_pin.sym} 300 40 0 0 {name=l12 lab=sns2}
N 300 120 300 140 {}
C {lab_pin.sym} 300 140 0 0 {name=l13 lab=e2}
N 280 90 260 90 {}
C {lab_pin.sym} 260 90 0 0 {name=l14 lab=vss}
C {symbols/pnp_10p00x10p00.sym} 300 -60 0 0 {name=Q2 model=pnp_10p00x10p00 m=1}
N 320 -30 320 -10 {}
C {lab_pin.sym} 320 -10 0 0 {name=l15 lab=vss}
N 280 -60 260 -60 {}
C {lab_pin.sym} 260 -60 0 0 {name=l16 lab=vss}
N 320 -90 320 -110 {}
C {lab_pin.sym} 320 -110 0 0 {name=l17 lab=e2}
C {symbols/pfet_03v3.sym} 600 300 0 0 {name=M3 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 620 330 620 350 {}
C {lab_pin.sym} 620 350 0 0 {name=l18 lab=d3}
C {symbols/pfet_03v3.sym} 600 600 0 0 {name=MC3 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 620 570 620 550 {}
C {lab_pin.sym} 620 550 0 0 {name=lc3a lab=d3}
N 580 600 560 600 {}
C {lab_pin.sym} 560 600 0 0 {name=lc3b lab=casc}
N 620 600 640 600 {}
C {lab_pin.sym} 640 600 0 0 {name=lc3c lab=vdd}
N 620 630 620 650 {}
C {lab_pin.sym} 620 650 0 0 {name=lc3d lab=vref}
N 580 300 560 300 {}
C {lab_pin.sym} 560 300 0 0 {name=l19 lab=fb}
N 620 270 620 250 {}
C {lab_pin.sym} 620 250 0 0 {name=l20 lab=vdd}
N 620 300 640 300 {}
C {lab_pin.sym} 640 300 0 0 {name=l21 lab=vdd}
C {symbols/ppolyf_u.sym} 600 90 0 0 {name=R1 model=ppolyf_u W=2u L=230.180u m=1}
N 600 60 600 40 {}
C {lab_pin.sym} 600 40 0 0 {name=l22 lab=tn0}
N 600 120 600 140 {}
C {lab_pin.sym} 600 140 0 0 {name=l23 lab=e3}
N 580 90 560 90 {}
C {lab_pin.sym} 560 90 0 0 {name=l24 lab=vss}
C {symbols/pnp_05p00x05p00.sym} 600 -60 0 0 {name=Q3 model=pnp_05p00x05p00 m=1}
N 620 -30 620 -10 {}
C {lab_pin.sym} 620 -10 0 0 {name=l25 lab=vss}
N 580 -60 560 -60 {}
C {lab_pin.sym} 560 -60 0 0 {name=l26 lab=vss}
N 620 -90 620 -110 {}
C {lab_pin.sym} 620 -110 0 0 {name=l27 lab=e3}
C {symbols/pfet_03v3.sym} 900 300 0 0 {name=M4 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 920 330 920 350 {}
C {lab_pin.sym} 920 350 0 0 {name=l28 lab=d4}
C {symbols/pfet_03v3.sym} 900 600 0 0 {name=MC4 model=pfet_03v3 W=20u L=2u nf=1 m=1}
N 920 570 920 550 {}
C {lab_pin.sym} 920 550 0 0 {name=lc4a lab=d4}
N 880 600 860 600 {}
C {lab_pin.sym} 860 600 0 0 {name=lc4b lab=casc}
N 920 600 940 600 {}
C {lab_pin.sym} 940 600 0 0 {name=lc4c lab=vdd}
N 920 630 920 650 {}
C {lab_pin.sym} 920 650 0 0 {name=lc4d lab=ibias}
N 880 300 860 300 {}
C {lab_pin.sym} 860 300 0 0 {name=l29 lab=fb}
N 920 270 920 250 {}
C {lab_pin.sym} 920 250 0 0 {name=l30 lab=vdd}
N 920 300 940 300 {}
C {lab_pin.sym} 940 300 0 0 {name=l31 lab=vdd}
C {symbols/nfet_03v3.sym} 900 0 0 0 {name=M5 model=nfet_03v3 W=20u L=2u nf=1 m=1}
N 920 -30 920 -50 {}
C {lab_pin.sym} 920 -50 0 0 {name=l32 lab=ibias}
N 880 0 860 0 {}
C {lab_pin.sym} 860 0 0 0 {name=l33 lab=ibias}
N 920 30 920 50 {}
C {lab_pin.sym} 920 50 0 0 {name=l34 lab=vss}
N 920 0 940 0 {}
C {lab_pin.sym} 940 0 0 0 {name=l35 lab=vss}
C {symbols/pfet_03v3.sym} 1200 300 0 0 {name=MCB model=pfet_03v3 W=4u L=12u nf=1 m=1}
N 1220 270 1220 250 {}
C {lab_pin.sym} 1220 250 0 0 {name=lb1 lab=vdd}
N 1220 300 1240 300 {}
C {lab_pin.sym} 1240 300 0 0 {name=lb2 lab=vdd}
N 1180 300 1160 300 {}
C {lab_pin.sym} 1160 300 0 0 {name=lb3 lab=casc}
N 1220 330 1220 350 {}
C {lab_pin.sym} 1220 350 0 0 {name=lb4 lab=casc}
C {symbols/nfet_03v3.sym} 1200 600 0 0 {name=MNB model=nfet_03v3 W=5u L=2u nf=1 m=1}
N 1220 570 1220 550 {}
C {lab_pin.sym} 1220 550 0 0 {name=lb5 lab=casc}
N 1180 600 1160 600 {}
C {lab_pin.sym} 1160 600 0 0 {name=lb6 lab=ibias}
N 1220 630 1220 650 {}
C {lab_pin.sym} 1220 650 0 0 {name=lb7 lab=vss}
N 1220 600 1240 600 {}
C {lab_pin.sym} 1240 600 0 0 {name=lb8 lab=vss}
C {bandgap_trim.sym} 600 -250 0 0 {name=XTRIM}
N 600 -290 600 -310 {}
C {lab_pin.sym} 600 -310 0 0 {name=ltrt lab=vref}
N 600 -210 600 -190 {}
C {lab_pin.sym} 600 -190 0 0 {name=ltrb lab=tn0}
N 560 -250 540 -250 {}
C {lab_pin.sym} 540 -250 0 0 {name=ltrs lab=vss}
C {iopin.sym} -200 300 0 0 {name=p1 lab=vdd}
C {iopin.sym} -200 -60 0 0 {name=p2 lab=vss}
C {iopin.sym} -200 500 0 0 {name=p3 lab=fb}
C {iopin.sym} -200 200 0 0 {name=p4 lab=sns1}
C {iopin.sym} -200 100 0 0 {name=p5 lab=sns2}
C {iopin.sym} 1100 300 0 0 {name=p6 lab=vref}
C {iopin.sym} 1100 100 0 0 {name=p7 lab=ibias}
C {iopin.sym} 1100 -100 0 0 {name=p8 lab=casc}
