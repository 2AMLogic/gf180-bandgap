v {xschem version=3.4.7 file_version=1.2
* bandgap_trim -- 6-bit binary-weighted, unit-segment trim ladder for the
* Brokaw cell's output-branch summing resistor (issue #14)
*
* Ratified mechanism: DR-0001's "minimal resistor-trim network -- a small
* number of binary-weighted trim resistor segments, switched in via probe-pad
* straps or a simple fuse/metal-option selection at test".
* Ratified numbers: README.md's Trim row -- 1-point resistor trim, range
* >= +/-5%, resolution <= 0.25%/step (>=5 bits equivalent), magnitude only,
* performed at 27 C. Sizing derivation: design/bandgap_trim_network.md.
*
* Pins: bot (to bandgap_core's fixed base R1), top (to vref), sub (vss).
*
* STRUCTURE. 63 IDENTICAL ppolyf_u unit segments (W=2u, L=2.771871u) in one
* series string from bot to top, tapped after 1, 3, 7, 15, 31 units so that
* the six groups hold 1, 2, 4, 8, 16 and 32 units -- weights 2^0..2^5. Each
* group is shunted by one strap RS<b>. The trim code counts unit segments
* left in circuit:
*
*   Rtrim(trim_code) = trim_code * R_unit,   trim_code = 0..63
*
* WHY UNIT SEGMENTS AND NOT SIX DIFFERENT-LENGTH RESISTORS. A gf180mcu
* ppolyf_u instance is a compound device: body resistance proportional to
* drawn length PLUS a fixed per-instance terminal/contact resistance
* (measured on this PDK at W=2u: R = 179.547*L_um + 61.382 ohm at tt/27 C).
* Six single instances sized to hit exact 2^b ratios at tt/27 C do NOT hold
* those ratios anywhere else, because the LSB instance is ~11% terminal
* resistance while the MSB instance is ~0.2%, and the two terms skew
* differently over process. That was measured, not assumed: an earlier
* six-instance version of this ladder read an MSB weight of 58.6 to 68.9 LSBs
* across the 81-point PVT grid instead of 64.0, which at the high end opens a
* ~14 mV UNREACHABLE gap at the code-31/32 transition -- a trim ladder with a
* dead zone. Identical unit segments cannot do that: every group is an
* integer number of the same physical device, so the 2^b ratios are exact by
* construction at every corner and the ladder is monotonic by construction.
* The cost is a higher aggregate contact-resistance fraction in the summing
* resistor (63 terminal pairs instead of one), quantified in
* design/bandgap_trim_network.md.
*
* RS0..RS5 ARE NOT FABRICATED DEVICES. Each models the presence (link drawn,
* ~0 ohm -> that group shorted out) or absence (no link, open -> that group
* in circuit) of one metal-option/probe-pad strap. Values decode from the
* subcircuit-local parameter `trim_code` (0..63, default 32 = MSB only):
*
*   bit_b  = floor(trim_code/2^b) - 2*floor(trim_code/2^(b+1))
*   RS<b>  = 1e-3 ohm  when bit_b = 0  (strap closed, group shorted out)
*          = 1e12 ohm  when bit_b = 1  (strap open, group in circuit)
*
* A testbench sweeps the code with `alterparam bandgap_trim trim_code = <n>`
* followed by `reset` (see sim/trim-coverage/). Every other bench sees the
* default code and therefore the pre-trim nominal operating point.
*
* UNIT-SEGMENT RESIZE (issue #61) -- L=1.215u -> L=2.771871u, i.e. R_unit
* 279.53 -> 559.06 ohm at tt/27 C, exactly 2x. This is NOT a change to the
* trim ladder's own sizing argument: #61 co-scales bandgap_core's R1 and R2
* by k = 2 to halve the block's design current, and a trim step's value in
* VOLTS is I*R_unit. Halving I without doubling R_unit would halve the LSB
* and the code-0..63 span with it, shrinking the ratified >= +/-5% trim
* range by 2x. Scaling R_unit by the same k holds the step and the span
* where sim/trim-coverage/ measured them, which is what the ratified Trim
* row is written against.
*
* Because ppolyf_u is a compound device (body + fixed terminal resistance,
* fit above), a 2x RESISTANCE is not a 2x LENGTH: L is solved from
* R = 179.547*L_um + 61.382, giving 2.771871u, not 2.430u. The same
* solve-don't-scale rule is applied to R1 and R2 in bandgap_core.sch.
* One incidental benefit: the per-instance terminal-resistance fraction
* halves (~22% -> ~11% of a unit segment), so the corner-tracking argument
* above only gets stronger.
}
G {}
K {}
V {}
S {}
E {}
C {devices/code.sym} -400 -100 0 0 {name=TRIMCODE only_toplevel=false place=header value=".param trim_code=32"}
C {iopin.sym} -400 0 0 0 {name=pb lab=bot}
C {iopin.sym} -400 100 0 0 {name=pt lab=top}
C {iopin.sym} -400 200 0 0 {name=ps lab=sub}
C {symbols/ppolyf_u.sym} 0 200 0 0 {name=RU0 model=ppolyf_u W=2u L=2.771871u m=1}
N 0 170 0 150 {}
C {lab_pin.sym} 0 150 0 0 {name=lu0a lab=tn1}
N 0 230 0 250 {}
C {lab_pin.sym} 0 250 0 0 {name=lu0b lab=bot}
N -20 200 -40 200 {}
C {lab_pin.sym} -40 200 0 0 {name=lu0c lab=sub}
C {devices/res.sym} -200 200 0 0 {name=RS0 value="{1e-3 + 1e12*(floor(trim_code/1)-2*floor(trim_code/2))\}" m=1}
N -200 170 -200 150 {}
C {lab_pin.sym} -200 150 0 0 {name=ls0a lab=tn1}
N -200 230 -200 250 {}
C {lab_pin.sym} -200 250 0 0 {name=ls0b lab=bot}
C {symbols/ppolyf_u.sym} 0 400 0 0 {name=RU1 model=ppolyf_u W=2u L=2.771871u m=1}
N 0 370 0 350 {}
C {lab_pin.sym} 0 350 0 0 {name=lu1a lab=u1_0}
N 0 430 0 450 {}
C {lab_pin.sym} 0 450 0 0 {name=lu1b lab=tn1}
N -20 400 -40 400 {}
C {lab_pin.sym} -40 400 0 0 {name=lu1c lab=sub}
C {symbols/ppolyf_u.sym} 100 400 0 0 {name=RU2 model=ppolyf_u W=2u L=2.771871u m=1}
N 100 370 100 350 {}
C {lab_pin.sym} 100 350 0 0 {name=lu2a lab=tn2}
N 100 430 100 450 {}
C {lab_pin.sym} 100 450 0 0 {name=lu2b lab=u1_0}
N 80 400 60 400 {}
C {lab_pin.sym} 60 400 0 0 {name=lu2c lab=sub}
C {devices/res.sym} -200 400 0 0 {name=RS1 value="{1e-3 + 1e12*(floor(trim_code/2)-2*floor(trim_code/4))\}" m=1}
N -200 370 -200 350 {}
C {lab_pin.sym} -200 350 0 0 {name=ls1a lab=tn2}
N -200 430 -200 450 {}
C {lab_pin.sym} -200 450 0 0 {name=ls1b lab=tn1}
C {symbols/ppolyf_u.sym} 0 600 0 0 {name=RU3 model=ppolyf_u W=2u L=2.771871u m=1}
N 0 570 0 550 {}
C {lab_pin.sym} 0 550 0 0 {name=lu3a lab=u2_0}
N 0 630 0 650 {}
C {lab_pin.sym} 0 650 0 0 {name=lu3b lab=tn2}
N -20 600 -40 600 {}
C {lab_pin.sym} -40 600 0 0 {name=lu3c lab=sub}
C {symbols/ppolyf_u.sym} 100 600 0 0 {name=RU4 model=ppolyf_u W=2u L=2.771871u m=1}
N 100 570 100 550 {}
C {lab_pin.sym} 100 550 0 0 {name=lu4a lab=u2_1}
N 100 630 100 650 {}
C {lab_pin.sym} 100 650 0 0 {name=lu4b lab=u2_0}
N 80 600 60 600 {}
C {lab_pin.sym} 60 600 0 0 {name=lu4c lab=sub}
C {symbols/ppolyf_u.sym} 200 600 0 0 {name=RU5 model=ppolyf_u W=2u L=2.771871u m=1}
N 200 570 200 550 {}
C {lab_pin.sym} 200 550 0 0 {name=lu5a lab=u2_2}
N 200 630 200 650 {}
C {lab_pin.sym} 200 650 0 0 {name=lu5b lab=u2_1}
N 180 600 160 600 {}
C {lab_pin.sym} 160 600 0 0 {name=lu5c lab=sub}
C {symbols/ppolyf_u.sym} 300 600 0 0 {name=RU6 model=ppolyf_u W=2u L=2.771871u m=1}
N 300 570 300 550 {}
C {lab_pin.sym} 300 550 0 0 {name=lu6a lab=tn3}
N 300 630 300 650 {}
C {lab_pin.sym} 300 650 0 0 {name=lu6b lab=u2_2}
N 280 600 260 600 {}
C {lab_pin.sym} 260 600 0 0 {name=lu6c lab=sub}
C {devices/res.sym} -200 600 0 0 {name=RS2 value="{1e-3 + 1e12*(floor(trim_code/4)-2*floor(trim_code/8))\}" m=1}
N -200 570 -200 550 {}
C {lab_pin.sym} -200 550 0 0 {name=ls2a lab=tn3}
N -200 630 -200 650 {}
C {lab_pin.sym} -200 650 0 0 {name=ls2b lab=tn2}
C {symbols/ppolyf_u.sym} 0 800 0 0 {name=RU7 model=ppolyf_u W=2u L=2.771871u m=1}
N 0 770 0 750 {}
C {lab_pin.sym} 0 750 0 0 {name=lu7a lab=u3_0}
N 0 830 0 850 {}
C {lab_pin.sym} 0 850 0 0 {name=lu7b lab=tn3}
N -20 800 -40 800 {}
C {lab_pin.sym} -40 800 0 0 {name=lu7c lab=sub}
C {symbols/ppolyf_u.sym} 100 800 0 0 {name=RU8 model=ppolyf_u W=2u L=2.771871u m=1}
N 100 770 100 750 {}
C {lab_pin.sym} 100 750 0 0 {name=lu8a lab=u3_1}
N 100 830 100 850 {}
C {lab_pin.sym} 100 850 0 0 {name=lu8b lab=u3_0}
N 80 800 60 800 {}
C {lab_pin.sym} 60 800 0 0 {name=lu8c lab=sub}
C {symbols/ppolyf_u.sym} 200 800 0 0 {name=RU9 model=ppolyf_u W=2u L=2.771871u m=1}
N 200 770 200 750 {}
C {lab_pin.sym} 200 750 0 0 {name=lu9a lab=u3_2}
N 200 830 200 850 {}
C {lab_pin.sym} 200 850 0 0 {name=lu9b lab=u3_1}
N 180 800 160 800 {}
C {lab_pin.sym} 160 800 0 0 {name=lu9c lab=sub}
C {symbols/ppolyf_u.sym} 300 800 0 0 {name=RU10 model=ppolyf_u W=2u L=2.771871u m=1}
N 300 770 300 750 {}
C {lab_pin.sym} 300 750 0 0 {name=lu10a lab=u3_3}
N 300 830 300 850 {}
C {lab_pin.sym} 300 850 0 0 {name=lu10b lab=u3_2}
N 280 800 260 800 {}
C {lab_pin.sym} 260 800 0 0 {name=lu10c lab=sub}
C {symbols/ppolyf_u.sym} 400 800 0 0 {name=RU11 model=ppolyf_u W=2u L=2.771871u m=1}
N 400 770 400 750 {}
C {lab_pin.sym} 400 750 0 0 {name=lu11a lab=u3_4}
N 400 830 400 850 {}
C {lab_pin.sym} 400 850 0 0 {name=lu11b lab=u3_3}
N 380 800 360 800 {}
C {lab_pin.sym} 360 800 0 0 {name=lu11c lab=sub}
C {symbols/ppolyf_u.sym} 500 800 0 0 {name=RU12 model=ppolyf_u W=2u L=2.771871u m=1}
N 500 770 500 750 {}
C {lab_pin.sym} 500 750 0 0 {name=lu12a lab=u3_5}
N 500 830 500 850 {}
C {lab_pin.sym} 500 850 0 0 {name=lu12b lab=u3_4}
N 480 800 460 800 {}
C {lab_pin.sym} 460 800 0 0 {name=lu12c lab=sub}
C {symbols/ppolyf_u.sym} 600 800 0 0 {name=RU13 model=ppolyf_u W=2u L=2.771871u m=1}
N 600 770 600 750 {}
C {lab_pin.sym} 600 750 0 0 {name=lu13a lab=u3_6}
N 600 830 600 850 {}
C {lab_pin.sym} 600 850 0 0 {name=lu13b lab=u3_5}
N 580 800 560 800 {}
C {lab_pin.sym} 560 800 0 0 {name=lu13c lab=sub}
C {symbols/ppolyf_u.sym} 700 800 0 0 {name=RU14 model=ppolyf_u W=2u L=2.771871u m=1}
N 700 770 700 750 {}
C {lab_pin.sym} 700 750 0 0 {name=lu14a lab=tn4}
N 700 830 700 850 {}
C {lab_pin.sym} 700 850 0 0 {name=lu14b lab=u3_6}
N 680 800 660 800 {}
C {lab_pin.sym} 660 800 0 0 {name=lu14c lab=sub}
C {devices/res.sym} -200 800 0 0 {name=RS3 value="{1e-3 + 1e12*(floor(trim_code/8)-2*floor(trim_code/16))\}" m=1}
N -200 770 -200 750 {}
C {lab_pin.sym} -200 750 0 0 {name=ls3a lab=tn4}
N -200 830 -200 850 {}
C {lab_pin.sym} -200 850 0 0 {name=ls3b lab=tn3}
C {symbols/ppolyf_u.sym} 0 1000 0 0 {name=RU15 model=ppolyf_u W=2u L=2.771871u m=1}
N 0 970 0 950 {}
C {lab_pin.sym} 0 950 0 0 {name=lu15a lab=u4_0}
N 0 1030 0 1050 {}
C {lab_pin.sym} 0 1050 0 0 {name=lu15b lab=tn4}
N -20 1000 -40 1000 {}
C {lab_pin.sym} -40 1000 0 0 {name=lu15c lab=sub}
C {symbols/ppolyf_u.sym} 100 1000 0 0 {name=RU16 model=ppolyf_u W=2u L=2.771871u m=1}
N 100 970 100 950 {}
C {lab_pin.sym} 100 950 0 0 {name=lu16a lab=u4_1}
N 100 1030 100 1050 {}
C {lab_pin.sym} 100 1050 0 0 {name=lu16b lab=u4_0}
N 80 1000 60 1000 {}
C {lab_pin.sym} 60 1000 0 0 {name=lu16c lab=sub}
C {symbols/ppolyf_u.sym} 200 1000 0 0 {name=RU17 model=ppolyf_u W=2u L=2.771871u m=1}
N 200 970 200 950 {}
C {lab_pin.sym} 200 950 0 0 {name=lu17a lab=u4_2}
N 200 1030 200 1050 {}
C {lab_pin.sym} 200 1050 0 0 {name=lu17b lab=u4_1}
N 180 1000 160 1000 {}
C {lab_pin.sym} 160 1000 0 0 {name=lu17c lab=sub}
C {symbols/ppolyf_u.sym} 300 1000 0 0 {name=RU18 model=ppolyf_u W=2u L=2.771871u m=1}
N 300 970 300 950 {}
C {lab_pin.sym} 300 950 0 0 {name=lu18a lab=u4_3}
N 300 1030 300 1050 {}
C {lab_pin.sym} 300 1050 0 0 {name=lu18b lab=u4_2}
N 280 1000 260 1000 {}
C {lab_pin.sym} 260 1000 0 0 {name=lu18c lab=sub}
C {symbols/ppolyf_u.sym} 400 1000 0 0 {name=RU19 model=ppolyf_u W=2u L=2.771871u m=1}
N 400 970 400 950 {}
C {lab_pin.sym} 400 950 0 0 {name=lu19a lab=u4_4}
N 400 1030 400 1050 {}
C {lab_pin.sym} 400 1050 0 0 {name=lu19b lab=u4_3}
N 380 1000 360 1000 {}
C {lab_pin.sym} 360 1000 0 0 {name=lu19c lab=sub}
C {symbols/ppolyf_u.sym} 500 1000 0 0 {name=RU20 model=ppolyf_u W=2u L=2.771871u m=1}
N 500 970 500 950 {}
C {lab_pin.sym} 500 950 0 0 {name=lu20a lab=u4_5}
N 500 1030 500 1050 {}
C {lab_pin.sym} 500 1050 0 0 {name=lu20b lab=u4_4}
N 480 1000 460 1000 {}
C {lab_pin.sym} 460 1000 0 0 {name=lu20c lab=sub}
C {symbols/ppolyf_u.sym} 600 1000 0 0 {name=RU21 model=ppolyf_u W=2u L=2.771871u m=1}
N 600 970 600 950 {}
C {lab_pin.sym} 600 950 0 0 {name=lu21a lab=u4_6}
N 600 1030 600 1050 {}
C {lab_pin.sym} 600 1050 0 0 {name=lu21b lab=u4_5}
N 580 1000 560 1000 {}
C {lab_pin.sym} 560 1000 0 0 {name=lu21c lab=sub}
C {symbols/ppolyf_u.sym} 700 1000 0 0 {name=RU22 model=ppolyf_u W=2u L=2.771871u m=1}
N 700 970 700 950 {}
C {lab_pin.sym} 700 950 0 0 {name=lu22a lab=u4_7}
N 700 1030 700 1050 {}
C {lab_pin.sym} 700 1050 0 0 {name=lu22b lab=u4_6}
N 680 1000 660 1000 {}
C {lab_pin.sym} 660 1000 0 0 {name=lu22c lab=sub}
C {symbols/ppolyf_u.sym} 800 1000 0 0 {name=RU23 model=ppolyf_u W=2u L=2.771871u m=1}
N 800 970 800 950 {}
C {lab_pin.sym} 800 950 0 0 {name=lu23a lab=u4_8}
N 800 1030 800 1050 {}
C {lab_pin.sym} 800 1050 0 0 {name=lu23b lab=u4_7}
N 780 1000 760 1000 {}
C {lab_pin.sym} 760 1000 0 0 {name=lu23c lab=sub}
C {symbols/ppolyf_u.sym} 900 1000 0 0 {name=RU24 model=ppolyf_u W=2u L=2.771871u m=1}
N 900 970 900 950 {}
C {lab_pin.sym} 900 950 0 0 {name=lu24a lab=u4_9}
N 900 1030 900 1050 {}
C {lab_pin.sym} 900 1050 0 0 {name=lu24b lab=u4_8}
N 880 1000 860 1000 {}
C {lab_pin.sym} 860 1000 0 0 {name=lu24c lab=sub}
C {symbols/ppolyf_u.sym} 1000 1000 0 0 {name=RU25 model=ppolyf_u W=2u L=2.771871u m=1}
N 1000 970 1000 950 {}
C {lab_pin.sym} 1000 950 0 0 {name=lu25a lab=u4_10}
N 1000 1030 1000 1050 {}
C {lab_pin.sym} 1000 1050 0 0 {name=lu25b lab=u4_9}
N 980 1000 960 1000 {}
C {lab_pin.sym} 960 1000 0 0 {name=lu25c lab=sub}
C {symbols/ppolyf_u.sym} 1100 1000 0 0 {name=RU26 model=ppolyf_u W=2u L=2.771871u m=1}
N 1100 970 1100 950 {}
C {lab_pin.sym} 1100 950 0 0 {name=lu26a lab=u4_11}
N 1100 1030 1100 1050 {}
C {lab_pin.sym} 1100 1050 0 0 {name=lu26b lab=u4_10}
N 1080 1000 1060 1000 {}
C {lab_pin.sym} 1060 1000 0 0 {name=lu26c lab=sub}
C {symbols/ppolyf_u.sym} 1200 1000 0 0 {name=RU27 model=ppolyf_u W=2u L=2.771871u m=1}
N 1200 970 1200 950 {}
C {lab_pin.sym} 1200 950 0 0 {name=lu27a lab=u4_12}
N 1200 1030 1200 1050 {}
C {lab_pin.sym} 1200 1050 0 0 {name=lu27b lab=u4_11}
N 1180 1000 1160 1000 {}
C {lab_pin.sym} 1160 1000 0 0 {name=lu27c lab=sub}
C {symbols/ppolyf_u.sym} 1300 1000 0 0 {name=RU28 model=ppolyf_u W=2u L=2.771871u m=1}
N 1300 970 1300 950 {}
C {lab_pin.sym} 1300 950 0 0 {name=lu28a lab=u4_13}
N 1300 1030 1300 1050 {}
C {lab_pin.sym} 1300 1050 0 0 {name=lu28b lab=u4_12}
N 1280 1000 1260 1000 {}
C {lab_pin.sym} 1260 1000 0 0 {name=lu28c lab=sub}
C {symbols/ppolyf_u.sym} 1400 1000 0 0 {name=RU29 model=ppolyf_u W=2u L=2.771871u m=1}
N 1400 970 1400 950 {}
C {lab_pin.sym} 1400 950 0 0 {name=lu29a lab=u4_14}
N 1400 1030 1400 1050 {}
C {lab_pin.sym} 1400 1050 0 0 {name=lu29b lab=u4_13}
N 1380 1000 1360 1000 {}
C {lab_pin.sym} 1360 1000 0 0 {name=lu29c lab=sub}
C {symbols/ppolyf_u.sym} 1500 1000 0 0 {name=RU30 model=ppolyf_u W=2u L=2.771871u m=1}
N 1500 970 1500 950 {}
C {lab_pin.sym} 1500 950 0 0 {name=lu30a lab=tn5}
N 1500 1030 1500 1050 {}
C {lab_pin.sym} 1500 1050 0 0 {name=lu30b lab=u4_14}
N 1480 1000 1460 1000 {}
C {lab_pin.sym} 1460 1000 0 0 {name=lu30c lab=sub}
C {devices/res.sym} -200 1000 0 0 {name=RS4 value="{1e-3 + 1e12*(floor(trim_code/16)-2*floor(trim_code/32))\}" m=1}
N -200 970 -200 950 {}
C {lab_pin.sym} -200 950 0 0 {name=ls4a lab=tn5}
N -200 1030 -200 1050 {}
C {lab_pin.sym} -200 1050 0 0 {name=ls4b lab=tn4}
C {symbols/ppolyf_u.sym} 0 1200 0 0 {name=RU31 model=ppolyf_u W=2u L=2.771871u m=1}
N 0 1170 0 1150 {}
C {lab_pin.sym} 0 1150 0 0 {name=lu31a lab=u5_0}
N 0 1230 0 1250 {}
C {lab_pin.sym} 0 1250 0 0 {name=lu31b lab=tn5}
N -20 1200 -40 1200 {}
C {lab_pin.sym} -40 1200 0 0 {name=lu31c lab=sub}
C {symbols/ppolyf_u.sym} 100 1200 0 0 {name=RU32 model=ppolyf_u W=2u L=2.771871u m=1}
N 100 1170 100 1150 {}
C {lab_pin.sym} 100 1150 0 0 {name=lu32a lab=u5_1}
N 100 1230 100 1250 {}
C {lab_pin.sym} 100 1250 0 0 {name=lu32b lab=u5_0}
N 80 1200 60 1200 {}
C {lab_pin.sym} 60 1200 0 0 {name=lu32c lab=sub}
C {symbols/ppolyf_u.sym} 200 1200 0 0 {name=RU33 model=ppolyf_u W=2u L=2.771871u m=1}
N 200 1170 200 1150 {}
C {lab_pin.sym} 200 1150 0 0 {name=lu33a lab=u5_2}
N 200 1230 200 1250 {}
C {lab_pin.sym} 200 1250 0 0 {name=lu33b lab=u5_1}
N 180 1200 160 1200 {}
C {lab_pin.sym} 160 1200 0 0 {name=lu33c lab=sub}
C {symbols/ppolyf_u.sym} 300 1200 0 0 {name=RU34 model=ppolyf_u W=2u L=2.771871u m=1}
N 300 1170 300 1150 {}
C {lab_pin.sym} 300 1150 0 0 {name=lu34a lab=u5_3}
N 300 1230 300 1250 {}
C {lab_pin.sym} 300 1250 0 0 {name=lu34b lab=u5_2}
N 280 1200 260 1200 {}
C {lab_pin.sym} 260 1200 0 0 {name=lu34c lab=sub}
C {symbols/ppolyf_u.sym} 400 1200 0 0 {name=RU35 model=ppolyf_u W=2u L=2.771871u m=1}
N 400 1170 400 1150 {}
C {lab_pin.sym} 400 1150 0 0 {name=lu35a lab=u5_4}
N 400 1230 400 1250 {}
C {lab_pin.sym} 400 1250 0 0 {name=lu35b lab=u5_3}
N 380 1200 360 1200 {}
C {lab_pin.sym} 360 1200 0 0 {name=lu35c lab=sub}
C {symbols/ppolyf_u.sym} 500 1200 0 0 {name=RU36 model=ppolyf_u W=2u L=2.771871u m=1}
N 500 1170 500 1150 {}
C {lab_pin.sym} 500 1150 0 0 {name=lu36a lab=u5_5}
N 500 1230 500 1250 {}
C {lab_pin.sym} 500 1250 0 0 {name=lu36b lab=u5_4}
N 480 1200 460 1200 {}
C {lab_pin.sym} 460 1200 0 0 {name=lu36c lab=sub}
C {symbols/ppolyf_u.sym} 600 1200 0 0 {name=RU37 model=ppolyf_u W=2u L=2.771871u m=1}
N 600 1170 600 1150 {}
C {lab_pin.sym} 600 1150 0 0 {name=lu37a lab=u5_6}
N 600 1230 600 1250 {}
C {lab_pin.sym} 600 1250 0 0 {name=lu37b lab=u5_5}
N 580 1200 560 1200 {}
C {lab_pin.sym} 560 1200 0 0 {name=lu37c lab=sub}
C {symbols/ppolyf_u.sym} 700 1200 0 0 {name=RU38 model=ppolyf_u W=2u L=2.771871u m=1}
N 700 1170 700 1150 {}
C {lab_pin.sym} 700 1150 0 0 {name=lu38a lab=u5_7}
N 700 1230 700 1250 {}
C {lab_pin.sym} 700 1250 0 0 {name=lu38b lab=u5_6}
N 680 1200 660 1200 {}
C {lab_pin.sym} 660 1200 0 0 {name=lu38c lab=sub}
C {symbols/ppolyf_u.sym} 800 1200 0 0 {name=RU39 model=ppolyf_u W=2u L=2.771871u m=1}
N 800 1170 800 1150 {}
C {lab_pin.sym} 800 1150 0 0 {name=lu39a lab=u5_8}
N 800 1230 800 1250 {}
C {lab_pin.sym} 800 1250 0 0 {name=lu39b lab=u5_7}
N 780 1200 760 1200 {}
C {lab_pin.sym} 760 1200 0 0 {name=lu39c lab=sub}
C {symbols/ppolyf_u.sym} 900 1200 0 0 {name=RU40 model=ppolyf_u W=2u L=2.771871u m=1}
N 900 1170 900 1150 {}
C {lab_pin.sym} 900 1150 0 0 {name=lu40a lab=u5_9}
N 900 1230 900 1250 {}
C {lab_pin.sym} 900 1250 0 0 {name=lu40b lab=u5_8}
N 880 1200 860 1200 {}
C {lab_pin.sym} 860 1200 0 0 {name=lu40c lab=sub}
C {symbols/ppolyf_u.sym} 1000 1200 0 0 {name=RU41 model=ppolyf_u W=2u L=2.771871u m=1}
N 1000 1170 1000 1150 {}
C {lab_pin.sym} 1000 1150 0 0 {name=lu41a lab=u5_10}
N 1000 1230 1000 1250 {}
C {lab_pin.sym} 1000 1250 0 0 {name=lu41b lab=u5_9}
N 980 1200 960 1200 {}
C {lab_pin.sym} 960 1200 0 0 {name=lu41c lab=sub}
C {symbols/ppolyf_u.sym} 1100 1200 0 0 {name=RU42 model=ppolyf_u W=2u L=2.771871u m=1}
N 1100 1170 1100 1150 {}
C {lab_pin.sym} 1100 1150 0 0 {name=lu42a lab=u5_11}
N 1100 1230 1100 1250 {}
C {lab_pin.sym} 1100 1250 0 0 {name=lu42b lab=u5_10}
N 1080 1200 1060 1200 {}
C {lab_pin.sym} 1060 1200 0 0 {name=lu42c lab=sub}
C {symbols/ppolyf_u.sym} 1200 1200 0 0 {name=RU43 model=ppolyf_u W=2u L=2.771871u m=1}
N 1200 1170 1200 1150 {}
C {lab_pin.sym} 1200 1150 0 0 {name=lu43a lab=u5_12}
N 1200 1230 1200 1250 {}
C {lab_pin.sym} 1200 1250 0 0 {name=lu43b lab=u5_11}
N 1180 1200 1160 1200 {}
C {lab_pin.sym} 1160 1200 0 0 {name=lu43c lab=sub}
C {symbols/ppolyf_u.sym} 1300 1200 0 0 {name=RU44 model=ppolyf_u W=2u L=2.771871u m=1}
N 1300 1170 1300 1150 {}
C {lab_pin.sym} 1300 1150 0 0 {name=lu44a lab=u5_13}
N 1300 1230 1300 1250 {}
C {lab_pin.sym} 1300 1250 0 0 {name=lu44b lab=u5_12}
N 1280 1200 1260 1200 {}
C {lab_pin.sym} 1260 1200 0 0 {name=lu44c lab=sub}
C {symbols/ppolyf_u.sym} 1400 1200 0 0 {name=RU45 model=ppolyf_u W=2u L=2.771871u m=1}
N 1400 1170 1400 1150 {}
C {lab_pin.sym} 1400 1150 0 0 {name=lu45a lab=u5_14}
N 1400 1230 1400 1250 {}
C {lab_pin.sym} 1400 1250 0 0 {name=lu45b lab=u5_13}
N 1380 1200 1360 1200 {}
C {lab_pin.sym} 1360 1200 0 0 {name=lu45c lab=sub}
C {symbols/ppolyf_u.sym} 1500 1200 0 0 {name=RU46 model=ppolyf_u W=2u L=2.771871u m=1}
N 1500 1170 1500 1150 {}
C {lab_pin.sym} 1500 1150 0 0 {name=lu46a lab=u5_15}
N 1500 1230 1500 1250 {}
C {lab_pin.sym} 1500 1250 0 0 {name=lu46b lab=u5_14}
N 1480 1200 1460 1200 {}
C {lab_pin.sym} 1460 1200 0 0 {name=lu46c lab=sub}
C {symbols/ppolyf_u.sym} 1600 1200 0 0 {name=RU47 model=ppolyf_u W=2u L=2.771871u m=1}
N 1600 1170 1600 1150 {}
C {lab_pin.sym} 1600 1150 0 0 {name=lu47a lab=u5_16}
N 1600 1230 1600 1250 {}
C {lab_pin.sym} 1600 1250 0 0 {name=lu47b lab=u5_15}
N 1580 1200 1560 1200 {}
C {lab_pin.sym} 1560 1200 0 0 {name=lu47c lab=sub}
C {symbols/ppolyf_u.sym} 1700 1200 0 0 {name=RU48 model=ppolyf_u W=2u L=2.771871u m=1}
N 1700 1170 1700 1150 {}
C {lab_pin.sym} 1700 1150 0 0 {name=lu48a lab=u5_17}
N 1700 1230 1700 1250 {}
C {lab_pin.sym} 1700 1250 0 0 {name=lu48b lab=u5_16}
N 1680 1200 1660 1200 {}
C {lab_pin.sym} 1660 1200 0 0 {name=lu48c lab=sub}
C {symbols/ppolyf_u.sym} 1800 1200 0 0 {name=RU49 model=ppolyf_u W=2u L=2.771871u m=1}
N 1800 1170 1800 1150 {}
C {lab_pin.sym} 1800 1150 0 0 {name=lu49a lab=u5_18}
N 1800 1230 1800 1250 {}
C {lab_pin.sym} 1800 1250 0 0 {name=lu49b lab=u5_17}
N 1780 1200 1760 1200 {}
C {lab_pin.sym} 1760 1200 0 0 {name=lu49c lab=sub}
C {symbols/ppolyf_u.sym} 1900 1200 0 0 {name=RU50 model=ppolyf_u W=2u L=2.771871u m=1}
N 1900 1170 1900 1150 {}
C {lab_pin.sym} 1900 1150 0 0 {name=lu50a lab=u5_19}
N 1900 1230 1900 1250 {}
C {lab_pin.sym} 1900 1250 0 0 {name=lu50b lab=u5_18}
N 1880 1200 1860 1200 {}
C {lab_pin.sym} 1860 1200 0 0 {name=lu50c lab=sub}
C {symbols/ppolyf_u.sym} 2000 1200 0 0 {name=RU51 model=ppolyf_u W=2u L=2.771871u m=1}
N 2000 1170 2000 1150 {}
C {lab_pin.sym} 2000 1150 0 0 {name=lu51a lab=u5_20}
N 2000 1230 2000 1250 {}
C {lab_pin.sym} 2000 1250 0 0 {name=lu51b lab=u5_19}
N 1980 1200 1960 1200 {}
C {lab_pin.sym} 1960 1200 0 0 {name=lu51c lab=sub}
C {symbols/ppolyf_u.sym} 2100 1200 0 0 {name=RU52 model=ppolyf_u W=2u L=2.771871u m=1}
N 2100 1170 2100 1150 {}
C {lab_pin.sym} 2100 1150 0 0 {name=lu52a lab=u5_21}
N 2100 1230 2100 1250 {}
C {lab_pin.sym} 2100 1250 0 0 {name=lu52b lab=u5_20}
N 2080 1200 2060 1200 {}
C {lab_pin.sym} 2060 1200 0 0 {name=lu52c lab=sub}
C {symbols/ppolyf_u.sym} 2200 1200 0 0 {name=RU53 model=ppolyf_u W=2u L=2.771871u m=1}
N 2200 1170 2200 1150 {}
C {lab_pin.sym} 2200 1150 0 0 {name=lu53a lab=u5_22}
N 2200 1230 2200 1250 {}
C {lab_pin.sym} 2200 1250 0 0 {name=lu53b lab=u5_21}
N 2180 1200 2160 1200 {}
C {lab_pin.sym} 2160 1200 0 0 {name=lu53c lab=sub}
C {symbols/ppolyf_u.sym} 2300 1200 0 0 {name=RU54 model=ppolyf_u W=2u L=2.771871u m=1}
N 2300 1170 2300 1150 {}
C {lab_pin.sym} 2300 1150 0 0 {name=lu54a lab=u5_23}
N 2300 1230 2300 1250 {}
C {lab_pin.sym} 2300 1250 0 0 {name=lu54b lab=u5_22}
N 2280 1200 2260 1200 {}
C {lab_pin.sym} 2260 1200 0 0 {name=lu54c lab=sub}
C {symbols/ppolyf_u.sym} 2400 1200 0 0 {name=RU55 model=ppolyf_u W=2u L=2.771871u m=1}
N 2400 1170 2400 1150 {}
C {lab_pin.sym} 2400 1150 0 0 {name=lu55a lab=u5_24}
N 2400 1230 2400 1250 {}
C {lab_pin.sym} 2400 1250 0 0 {name=lu55b lab=u5_23}
N 2380 1200 2360 1200 {}
C {lab_pin.sym} 2360 1200 0 0 {name=lu55c lab=sub}
C {symbols/ppolyf_u.sym} 2500 1200 0 0 {name=RU56 model=ppolyf_u W=2u L=2.771871u m=1}
N 2500 1170 2500 1150 {}
C {lab_pin.sym} 2500 1150 0 0 {name=lu56a lab=u5_25}
N 2500 1230 2500 1250 {}
C {lab_pin.sym} 2500 1250 0 0 {name=lu56b lab=u5_24}
N 2480 1200 2460 1200 {}
C {lab_pin.sym} 2460 1200 0 0 {name=lu56c lab=sub}
C {symbols/ppolyf_u.sym} 2600 1200 0 0 {name=RU57 model=ppolyf_u W=2u L=2.771871u m=1}
N 2600 1170 2600 1150 {}
C {lab_pin.sym} 2600 1150 0 0 {name=lu57a lab=u5_26}
N 2600 1230 2600 1250 {}
C {lab_pin.sym} 2600 1250 0 0 {name=lu57b lab=u5_25}
N 2580 1200 2560 1200 {}
C {lab_pin.sym} 2560 1200 0 0 {name=lu57c lab=sub}
C {symbols/ppolyf_u.sym} 2700 1200 0 0 {name=RU58 model=ppolyf_u W=2u L=2.771871u m=1}
N 2700 1170 2700 1150 {}
C {lab_pin.sym} 2700 1150 0 0 {name=lu58a lab=u5_27}
N 2700 1230 2700 1250 {}
C {lab_pin.sym} 2700 1250 0 0 {name=lu58b lab=u5_26}
N 2680 1200 2660 1200 {}
C {lab_pin.sym} 2660 1200 0 0 {name=lu58c lab=sub}
C {symbols/ppolyf_u.sym} 2800 1200 0 0 {name=RU59 model=ppolyf_u W=2u L=2.771871u m=1}
N 2800 1170 2800 1150 {}
C {lab_pin.sym} 2800 1150 0 0 {name=lu59a lab=u5_28}
N 2800 1230 2800 1250 {}
C {lab_pin.sym} 2800 1250 0 0 {name=lu59b lab=u5_27}
N 2780 1200 2760 1200 {}
C {lab_pin.sym} 2760 1200 0 0 {name=lu59c lab=sub}
C {symbols/ppolyf_u.sym} 2900 1200 0 0 {name=RU60 model=ppolyf_u W=2u L=2.771871u m=1}
N 2900 1170 2900 1150 {}
C {lab_pin.sym} 2900 1150 0 0 {name=lu60a lab=u5_29}
N 2900 1230 2900 1250 {}
C {lab_pin.sym} 2900 1250 0 0 {name=lu60b lab=u5_28}
N 2880 1200 2860 1200 {}
C {lab_pin.sym} 2860 1200 0 0 {name=lu60c lab=sub}
C {symbols/ppolyf_u.sym} 3000 1200 0 0 {name=RU61 model=ppolyf_u W=2u L=2.771871u m=1}
N 3000 1170 3000 1150 {}
C {lab_pin.sym} 3000 1150 0 0 {name=lu61a lab=u5_30}
N 3000 1230 3000 1250 {}
C {lab_pin.sym} 3000 1250 0 0 {name=lu61b lab=u5_29}
N 2980 1200 2960 1200 {}
C {lab_pin.sym} 2960 1200 0 0 {name=lu61c lab=sub}
C {symbols/ppolyf_u.sym} 3100 1200 0 0 {name=RU62 model=ppolyf_u W=2u L=2.771871u m=1}
N 3100 1170 3100 1150 {}
C {lab_pin.sym} 3100 1150 0 0 {name=lu62a lab=top}
N 3100 1230 3100 1250 {}
C {lab_pin.sym} 3100 1250 0 0 {name=lu62b lab=u5_30}
N 3080 1200 3060 1200 {}
C {lab_pin.sym} 3060 1200 0 0 {name=lu62c lab=sub}
C {devices/res.sym} -200 1200 0 0 {name=RS5 value="{1e-3 + 1e12*(floor(trim_code/32)-2*floor(trim_code/64))\}" m=1}
N -200 1170 -200 1150 {}
C {lab_pin.sym} -200 1150 0 0 {name=ls5a lab=top}
N -200 1230 -200 1250 {}
C {lab_pin.sym} -200 1250 0 0 {name=ls5b lab=tn5}
