# T480 NM-B501 thermal circuit audit

Schematic audit on 2026-10-27, compared with N24HT37W firmware and the
existing `t480_ec` channel map. This is a circuit/net audit, not a physical
population inspection or controlled local-heating validation.

## References and scope

LCFC Windu-2 / NM-B501 WD-2 Logic, rev 0.1, 2017-11-09, 104 sheets.
[Download page](https://www.alisaler.com/lenovo-thinkpad-t480-nm-b501-schematic-boardview/).
Local PDF SHA256:
`2b8348706bf9b4a1b592a451ea2de93024bbe59903f0617c17d9124e10d5c46c`.
Companion TVW SHA256:
`b023866a9f6c54fa397532d2d8ec54f2bba026817bad5f5ab933010a5378f8a0`.
The original files are not redistributed in this repository.

Inspected rendered sheets 55/56/66/67/68/97, the EC third symbol on sheet 57,
and searched all 104 sheets for thermal parts, temperature nets, ADC pins,
and ambient-light components. Component population and part substitutions
can differ on production boards; the schematic's placement labels describe
circuit locations rather than proving junction temperatures.

## Six external diode sensors: all already exposed

U23 is the MEC1653 EC. Sheet 56 explicitly labels DIODE0 as EC internal and
DIODE1..6 as the six board locations below. The external devices are
2SCR523MT2L NPN transistors used for temperature sensing, not NTC resistors.
Each transistor has collector (pin 1) strapped to base (pin 2); emitter
(pin 3) is the other sensing terminal.
The EC shares each pair of thermal terminals between oppositely oriented
sensors. DP/DN names encode both uses.

| Diode | Part | Placement | EC terminal pair | Base / emitter EC balls | Page 0x60 slot | Existing label |
| --- | --- | --- | --- | --- | ---: | --- |
| 1 | Q142 | CPU DC/DC, bottom | DP1_DN4 / DN1_DP4 | G13 / F13 | 2 | CPU VRM area |
| 2 | Q145 | WWAN, bottom | DP2_DN5 / DN2_DP5 | E13 / D13 | 10 | WWAN area |
| 3 | Q146 | WLAN, bottom | DP3_DN6 / DN3_DP6 | C13 / B13 | 13 | WLAN area |
| 4 | Q198 | Fan, bottom | DN1_DP4 / DP1_DN4 | F13 / G13 | 8 | Fan area |
| 5 | Q261 | dGPU DC/DC, bottom | DN2_DP5 / DP2_DN5 | D13 / E13 | 12 | dGPU VRM area |
| 6 | Q144 | DIMM, bottom | DN3_DP6 / DP3_DN6 | B13 / C13 | 9 | DIMM area |

EC-side filter capacitors are C6321/C6324/C6325 (2200 pF). Local 22 pF
capacitors are C6322/C6328/C6329 for diodes 1/2/3 and C2608/C9196/C6327
for diodes 4/5/6. They do not constitute additional sensors.

Firmware source tables at 0x30358/0x30374 select thermal getter 0x13acc
with indices 1..6 in the slot order above. Index 0 is selected at slot 1,
currently labeled `EC source 0`. Given the sheet's explicit DIODE0 = EC
internal assignment and matching indices for all six external diodes, the
strong interpretation is EC internal temperature. No new sensor would be
added by renaming this channel. The RAM pointer table used by getter 0x13acc
was not independently read in this audit, so the generic label remains.

Getter 0x13acc accepts an additional index 7 and applies a lookup conversion.
Neither active 14-entry source table selects index 7, and sheet 56 shows no
seventh external diode. Generic firmware support is not evidence of another
populated board sensor.

## Fifteen PTCs form one hardware protection chain

Sheet 66 contains **RT1..RT15**, specified as Murata PRF15BB541NB6RC
(540 ohm nominal, 30% in the drawing). Trace order is:

`U101B J3 TH_DET -> RT1 -> RT2 -> ... -> RT15 -> ground`

C954 (0.1 uF) shunts the TH_DET node to ground. U101 is the BD4178AGSW-ZE2
ThinkEngine power controller. These parts have no individually wired EC ADC
connections, multiplexer, or addressable digital interfaces in the drawing.
They provide an aggregate overheat-detection input, not fifteen independently
readable Celsius values. Murata documents the PRF family specifically for
[this type of series-connected multi-location overheat detection](https://www.murata.com/en-sg/products/thermistor/ptc/overview/lineup/prf).
No software calibration could recover fifteen unknown temperatures from that
single two-terminal chain.

| PTC | Schematic placement target |
| --- | --- |
| RT1 | VCCGFXCORE_D DrMOS, PQ601/PQ602 |
| RT2 | VCC3M switching FET, PQ203 |
| RT3 | VCC5M switching FET, PQ201 |
| RT4 | External battery switching FETs, PQ19/PQ20 |
| RT5 | VCCCPUCORE DrMOS, PU403 |
| RT6 | VCCCPUCORE DrMOS, PU402 |
| RT7 | VCCGFXCORE DrMOS, PU404 |
| RT8 | USB-C input FETs, PQ5/PQ6 |
| RT9 | Thunderbolt USB-C input FETs, PQ1/PQ2 |
| RT10 | Charger buck FET, PQ101 |
| RT11 | Internal battery switching FETs, PQ17/PQ18 |
| RT12 | Charger boost FET, PQ102 |
| RT13 | Battery charge/discharge FET, PQ103 |
| RT14 | TBD in the drawing |
| RT15 | CPU die location, U58 |

TH_DET is distinct from U101B D7 SHUTDWNIN#. The latter is connected to
`-SHUTDOWN` and, through zero-ohm R839, `-PWRSHUTDOWN`. Do not confuse the
chain's analogue input with a measured-temperature bus or with the EC's
E12 SYS_SHDN# input: sheet 56 connects E12 through R8782 to the separate
`-THRM` net.

## One additional PTC controls USB-C power cutoff

Sheet 67 has **PRT1**, also PRF15BB541NB6RC, explicitly placed near charger
buck FET PQ101. PRT1 is in a divider with PR19 (30.1 kohm), feeding **PU3
TL331 comparator pin 1 (IN-)**. The other comparator input uses PR20/PR25.
The output/diode/latch circuit drives `-TH_SHUTDOWN`, which feeds PQ4/PQ8
in the two USB-C input gate circuits. This is separate from the RT1..RT15
ThinkEngine chain. It adds another hardware overheat protection point, but
no direct EC analogue readout is wired to this divider in the schematic.

Thus the drawing contains **16 additional PTC thermal devices**, beyond the
six already exposed external diode sensors. Their presence does not imply
16 missing hwmon temperature channels.

## Battery analogue temperature/ID inputs: a real untraced lead

Sheet 68 routes connector pin 5 to a pulled-up analogue line for each pack:

| Pack | Connector | Net | Pull-up to VCC3M | Series resistor (sheet 55) | EC ball / function |
| --- | --- | --- | --- | --- | --- |
| Internal/main | PJ2 pin 5 | M_TEMP | PR26, 6.19 kohm | R439, 1 kohm | K3, ADC0/GPIO200 |
| External/secondary | PJ3 pin 5 | S_TEMP | PR33, 6.19 kohm | R282, 1 kohm | L4, ADC4/GPIO204 |

The pack-side temperature element/ID resistance is outside the motherboard
schematic. The net names and divider wiring identify analogue battery inputs;
they do not establish the pack's resistance-vs-temperature curve or guarantee
that every pack implements a thermistor rather than an identification value.
These are battery connector signals, not additional motherboard-area sensors.

Important distinction: the existing `Battery 0 source 1/2` temperature labels
must **not** be equated with these two analogue inputs without further evidence.
N24HT37W getter 0x21e8c reads battery-record +0x2e, populated from SBS command
0x08. Getter 0x22274 reads +0xb4, populated by vendor SBS command 0x3b in
dispatcher 0x231d8. Both getters convert decikelvin to integer Celsius by
subtracting 0xaaa and dividing by 10. Thus both existing paths are battery-bus
cache reads; neither getter directly reads ADC0/ADC4.

ADC acquisition helper 0xdc18 operates the block at 0xf06800, selects a
channel, starts conversion, and reads ten bits from `0xf06814 + 4*channel`.
Its GPIO descriptors are at 0x303a8. This is a possible research route for
M_TEMP/S_TEMP, but invoking it changes pin/conversion configuration, and its
busy loop has no bounded timeout in the firmware. This audit did not invoke
it, change pin muxes, or publish raw ADC values as Celsius. A safe interface,
actual firmware use/caching, and the pack-specific transfer function remain
unestablished.

## Remaining digital/platform paths

- Slot 0 uses the processor-temperature getter 0x2103c. PECI runs from EC ball
  B12 through R925 (43 ohm) to the CPU PECI net, sheets 56 and 6. It is already
  represented as `CPU (EC)` when available, alongside ordinary CPU sensors.
- Slot 3 is disabled in the first source table. The second selects type 9,
  flags 0x49, whose acquisition requests SMBus address 0x9e (7-bit 0x4f).
  This is an optional digital-sensor lead, not evidence that the UMA board
  has another sensor populated. No label is assigned here.
- Slot 11 is type 7, index 2, through platform getter 0x1ea98 and its cache
  at 0x800e1c. Physical source semantics remain unresolved; it is not a
  seventh diode input. It is currently unavailable, rather than filtered out
  as a duplicate known sensor.
- The optional dGPU has an EC SMBus path (`I2C_DATA_VIDEO`/`I2C_CLK_VIDEO`,
  EC J10/K10 through R2471/R2472), sheet 57; a GPIO threshold signal
  `-VIDEO_THERM_ALERT` returns to EC F9 through R10621, sheet 97. A dGPU-area
  diode reading does not imply a populated GPU. The dGPU THERMDN/THERMDP balls
  E12/F12 are shown without external connections on sheet 97.
- No ambient-light sensor, ALS net, or ambient-light circuit was found in
  the complete schematic. This does not inspect aftermarket display modules.

## Outcome

All six explicit external EC diode sensors are already mapped and exposed.
The newly identified motherboard PTCs serve hardware overheat protection;
individual readout is not wired. The useful remaining analogue investigation
is the battery connector M_TEMP/S_TEMP path, with no assumption that it gives
new calibrated temperatures. Slots 3/11 remain optional/platform leads.
No kernel module, thermal protection, charging setting, or live EC register
was changed for this schematic audit.
