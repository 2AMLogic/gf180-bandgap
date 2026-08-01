v {xschem version=3.4.7 file_version=1.2
* bandgap_amp -- offset-budgeted 5-transistor OTA (issue #10)
*
* Real-device 5T single-stage OTA closing the bandgap_core servo loop.
* Sizing here is the #10 offset-budget pass over #8's provisional
* placeholder: see design/bandgap_error_budget.md for the full derivation
* and design/bandgap_operating_point.md for the updated operating point.
*
* Input pair (M1/M2) is sized W=100um x nf=2 (100um total width, 2x50um
* fingers)/L=4um -- 10x the drawn gate area of #8's provisional 10um/4um
* pair. nf=2 is required, not a layout preference: gf180mcu's nfet_03v3
* model is width-binned and a single finger tops out at 100um (ngspice
* rejects any wider single-finger instance with "could not find a valid
* modelname" -- confirmed empirically), so 100um total width needs >=2
* fingers regardless of the offset budget. L=4um matches the characterized
* geometry in sim/device-mos-mismatch (record 20260731-031718-8fb0ea6) so
* the A_pair Pelgrom coefficient can be cited directly. Mirror load (M3/M4)
* sized W=40um/L=4um (single finger, under the 100um bin edge, 4x the
* provisional area) -- a smaller area increase than the input pair because
* its mismatch enters the input-referred offset scaled down by gm3/gm1
* (~0.64-0.69 measured on this circuit's own op point -- see
* design/bandgap_error_budget.md Sec 2), so it needs proportionally less
* matching area. Tail device (M5) is left at the provisional 10um/4um: its
* W/L sets the mirror ratio against bandgap_core's Mn5, and changing it
* would move the amp's quiescent current against the Iq budget without
* being the offset-budget's limiting term.
*
* THIS SIZING IS DELIBERATELY NOT PUSHED FURTHER, even though the offset
* budget (design/bandgap_error_budget.md Sec 2) shows the amp's own random
* offset alone is right at the edge of its RSS allocation at this size.
* Both directions tried during this issue's design pass -- growing L
* (L=6um on M1-M4) and growing W further while holding L (W=200-300um on
* M1/M2 alone, or with M3/M4 also grown to W=80um) -- were verified by
* simulation (sim/amp-loop-stability/, --no-write scratch sweeps, not
* separately recorded) to markedly erode phase margin at specific PVT
* corners (as low as single digits of degrees at some res_ss/fs/bjt
* corners), because the added Cgs/Cgd on these nodes interacts with this
* single-stage topology's parasitic Cgd feedthrough zero (see
* sim/amp-loop-stability/testbench/tb_loop_stability.spice's methodology
* header). This specific self-biased, cascoded-core topology's loop
* stability is unusually sensitive to amp device capacitance growth, so
* this sizing is a genuine, simulation-verified local optimum for THIS
* topology, not an unexamined stopping point -- closing the remaining
* offset-budget gap needs a compensation or topology change (a dedicated
* Miller/dominant-pole compensation scheme, or splitting gm and Cgs across
* more devices via a folded rather than telescopic structure), which is
* out of this issue's scope; see design/bandgap_error_budget.md Sec 2's
* escalation note.
*
* NOTE for #13 (circuit-level Monte Carlo): the gf180mcu nfet_03v3/
* pfet_03v3 subcircuit's local-mismatch variance is scaled by a `par`
* argument that is INDEPENDENT of `nf` (always 1 regardless of finger
* count) -- xschem's stock symbol format does not expose `par`, so M1/M2
* net-list here with the model's implicit par=1. design/bandgap_error_budget.md
* Sec 2 argues this is actually the *physically correct* Pelgrom
* prediction for a single logical device with this total gate area
* (finger count is a layout/parasitic choice, not a second independent
* device whose mismatch averages against the first, unless deliberately
* laid out as an interdigitated common-centroid pair of *separate* unit
* instances -- #16's job, not credited here) -- so the budget below does
* NOT assume any nf-driven bonus beyond plain area scaling.
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
C {symbols/nfet_03v3.sym} 0 0 0 0 {name=M1 model=nfet_03v3 W=100u L=4u nf=2 m=1}
N 20 -30 20 -50 {}
C {lab_pin.sym} 20 -50 0 0 {name=l1 lab=nd1}
N -20 0 -40 0 {}
C {lab_pin.sym} -40 0 0 0 {name=l2 lab=in_p}
N 20 30 20 50 {}
C {lab_pin.sym} 20 50 0 0 {name=l3 lab=tail}
N 20 0 40 0 {}
C {lab_pin.sym} 40 0 0 0 {name=l4 lab=vss}
C {symbols/nfet_03v3.sym} 250 0 0 0 {name=M2 model=nfet_03v3 W=100u L=4u nf=2 m=1}
N 270 -30 270 -50 {}
C {lab_pin.sym} 270 -50 0 0 {name=l5 lab=out}
N 230 0 210 0 {}
C {lab_pin.sym} 210 0 0 0 {name=l6 lab=in_n}
N 270 30 270 50 {}
C {lab_pin.sym} 270 50 0 0 {name=l7 lab=tail}
N 270 0 290 0 {}
C {lab_pin.sym} 290 0 0 0 {name=l8 lab=vss}
C {symbols/pfet_03v3.sym} 0 250 0 0 {name=M3 model=pfet_03v3 W=40u L=4u nf=1 m=1}
N 20 280 20 300 {}
C {lab_pin.sym} 20 300 0 0 {name=l9 lab=nd1}
N -20 250 -40 250 {}
C {lab_pin.sym} -40 250 0 0 {name=l10 lab=nd1}
N 20 220 20 200 {}
C {lab_pin.sym} 20 200 0 0 {name=l11 lab=vdd}
N 20 250 40 250 {}
C {lab_pin.sym} 40 250 0 0 {name=l12 lab=vdd}
C {symbols/pfet_03v3.sym} 250 250 0 0 {name=M4 model=pfet_03v3 W=40u L=4u nf=1 m=1}
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
