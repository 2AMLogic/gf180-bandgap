v {xschem version=3.4.7 file_version=1.2
* Environment-bootstrap smoke test (issue #18) -- NOT a bandgap design.
*
* A throwaway RC + single gf180mcu nfet_03v3 structure used only to prove
* the xschem -> ngspice -> gf180mcu toolchain works end to end:
*   VDD (3.3V) -- R1 (10k) -- vout -- C1 (1p) -- GND
*   vout is also the drain of a single gf180mcu 3.3V nfet (nfet_03v3_dss),
*   gate biased at 1.5V via VG, source/bulk grounded.
* See sim/smoke_test/run_smoke_test.sh for how this gets netlisted and run.
}
G {}
K {}
V {}
S {}
E {}
N 0 -60 0 -30 {}
N 0 30 0 60 {}
N 200 -60 200 -30 {}
N 200 30 200 60 {}
N 400 -60 400 -30 {}
N 400 30 400 60 {}
N 600 -60 600 -30 {}
N 600 30 600 60 {}
C {vsource.sym} 0 0 0 0 {name=VDD value="dc 3.3"}
C {lab_pin.sym} 0 -60 0 0 {name=p1 lab=vdd}
C {lab_pin.sym} 0 60 0 0 {name=p2 lab=0}
C {vsource.sym} 200 0 0 0 {name=VG value="dc 1.5"}
C {lab_pin.sym} 200 -60 0 0 {name=p3 lab=vg}
C {lab_pin.sym} 200 60 0 0 {name=p4 lab=0}
C {res.sym} 400 0 0 0 {name=R1 value=10k footprint=1206 device=resistor m=1}
C {lab_pin.sym} 400 -60 0 0 {name=p5 lab=vdd}
C {lab_pin.sym} 400 60 0 0 {name=p6 lab=vout}
C {capa.sym} 600 0 0 0 {name=C1 value=1p footprint=1206 device="ceramic capacitor" m=1}
C {lab_pin.sym} 600 -60 0 0 {name=p7 lab=vout}
C {lab_pin.sym} 600 60 0 0 {name=p8 lab=0}
C {code_shown.sym} 800 0 0 0 {name=s1 only_toplevel=false value="
* pdk_include.spice is generated at run time by run_smoke_test.sh from
* $PDK_ROOT / $PDK -- kept out of this schematic so it has no hardcoded,
* machine-specific path (see docs/environment-setup.md).
.include pdk_include.spice
X1 vout vg 0 0 nfet_03v3_dss w=10u l=1u

.control
op
print v(vdd) v(vg) v(vout)
quit
.endc
"}
