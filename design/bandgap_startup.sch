v {xschem version=3.4.7 file_version=1.2
* bandgap_startup -- current-sensing, self-disabling startup circuit
* (issue #11), per DR-0001 (spec/decision-records/0001-bandgap-topology-selection.md).
*
* DR-0001 rejects a voltage-detect startup (chicken-and-egg: the reference
* it would compare against isn't valid until startup completes) and a
* continuously-conducting bleeder (Iq cost) in favor of a current-sensing,
* self-disabling branch. This circuit senses bandgap_core's own bias
* current via the "ibias" node (the diode-connected NFET M5's Vgs inside
* bandgap_core -- ~0V in the degenerate zero-current state, ~0.75V once the
* core's ~10uA/branch design point is established, design/bandgap_operating_point.md
* section 3) and, while that current has not yet been established, kicks
* BOTH bandgap_core's mirror gate ("fb") and its cascode-bias gate ("casc")
* low to force the PMOS mirror and cascode devices on -- see
* bandgap_core.sch's comment on why both nodes need a kick, not just fb.
*
* Four devices:
*   XRPU     ppolyf_u_1k resistor, vdd -> det. Always-on pull-up (per
*            device-characterization.md section 2's explicit recommendation
*            to use ppolyf_u_1k "for non-ratio-critical bulk resistance
*            (start-up bleeder, ...)"). Sized ~2 Mohm so its own steady-state
*            current (once MSENSE clamps det low) is a few uA at most --
*            this IS the startup circuit's itemized residual Iq contribution
*            (see design/bandgap_operating_point.md's startup section), not
*            the "continuously-conducting bleeder into the core" DR-0001
*            rejects: it never injects current into the core's own bias
*            nodes, only into this local detect node.
*   XMSENSE  nfet_03v3, gate=ibias, drain=det, source=vss. Deliberately
*            sized to REPLICATE bandgap_core's own M5 (W=20u L=2u) so it
*            turns on at essentially the same ibias (i.e. the same Vgs)
*            that M5 itself needs to carry the core's design current --
*            once the core is running, MSENSE conducts far more strongly
*            than XRPU can source, clamping det to a few mV, deep below
*            MKFB/MKCASC's threshold.
*   MKFB     nfet_03v3, gate=det, drain=fb, source=vss. Kicks fb low while
*            det is high (degenerate state).
*   MKCASC   nfet_03v3, gate=det, drain=casc, source=vss. Kicks casc low
*            while det is high, for the same reason.
*
* Self-starting: at power-up (ibias=0, MSENSE off), XRPU pulls det toward
* vdd, turning MKFB/MKCASC on -- fail-safe default is "try to kick", not
* "never kick". Self-disabling: once ibias rises past MSENSE's own
* threshold, MSENSE overpowers XRPU and clamps det low, turning MKFB/MKCASC
* off -- their only remaining contribution is subthreshold leakage. Sized
* and verified (sim/startup/, sim/startup-slow-ramp/,
* sim/startup-state-search/, sim/startup-disabled-control/) against the
* full PVT matrix, not just nominal -- see those experiments' records for
* the corner-by-corner startup-time, residual-current and no-other-stable-
* state evidence this schematic's sizing is grounded in.
*
* Pins: vdd, vss, fb, casc, ibias
}
G {}
K {}
V {}
S {}
E {}
C {symbols/nfet_03v3.sym} 0 0 0 0 {name=MSENSE model=nfet_03v3 W=20u L=2u nf=1 m=1}
N 20 -30 20 -50 {}
C {lab_pin.sym} 20 -50 0 0 {name=l1 lab=det}
N -20 0 -40 0 {}
C {lab_pin.sym} -40 0 0 0 {name=l2 lab=ibias}
N 20 30 20 50 {}
C {lab_pin.sym} 20 50 0 0 {name=l3 lab=vss}
N 20 0 40 0 {}
C {lab_pin.sym} 40 0 0 0 {name=l4 lab=vss}
C {symbols/ppolyf_u_1k.sym} 0 -250 0 0 {name=RPU model=ppolyf_u_1k W=2u L=4000u m=1}
N 0 -280 0 -300 {}
C {lab_pin.sym} 0 -300 0 0 {name=l5 lab=vdd}
N 0 -220 0 -200 {}
C {lab_pin.sym} 0 -200 0 0 {name=l6 lab=det}
N -20 -250 -40 -250 {}
C {lab_pin.sym} -40 -250 0 0 {name=l7 lab=vss}
C {symbols/nfet_03v3.sym} 300 0 0 0 {name=MKFB model=nfet_03v3 W=2u L=2u nf=1 m=1}
N 320 -30 320 -50 {}
C {lab_pin.sym} 320 -50 0 0 {name=l8 lab=fb}
N 280 0 260 0 {}
C {lab_pin.sym} 260 0 0 0 {name=l9 lab=det}
N 320 30 320 50 {}
C {lab_pin.sym} 320 50 0 0 {name=l10 lab=vss}
N 320 0 340 0 {}
C {lab_pin.sym} 340 0 0 0 {name=l11 lab=vss}
C {symbols/nfet_03v3.sym} 600 0 0 0 {name=MKCASC model=nfet_03v3 W=2u L=2u nf=1 m=1}
N 620 -30 620 -50 {}
C {lab_pin.sym} 620 -50 0 0 {name=l12 lab=casc}
N 580 0 560 0 {}
C {lab_pin.sym} 560 0 0 0 {name=l13 lab=det}
N 620 30 620 50 {}
C {lab_pin.sym} 620 50 0 0 {name=l14 lab=vss}
N 620 0 640 0 {}
C {lab_pin.sym} 640 0 0 0 {name=l15 lab=vss}
C {iopin.sym} -200 0 0 0 {name=p1 lab=vdd}
C {iopin.sym} -200 -250 0 0 {name=p2 lab=vss}
C {iopin.sym} 900 -50 0 0 {name=p3 lab=fb}
C {iopin.sym} 900 0 0 0 {name=p4 lab=casc}
C {iopin.sym} 900 50 0 0 {name=p5 lab=ibias}
