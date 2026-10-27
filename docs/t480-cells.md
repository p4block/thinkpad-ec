# T480 internal battery cell-group voltages

Opt-in support for **ThinkPad T480 / N24HT37W / internal LGC LNV-01AV420**.
No external-pack vendor layout is authorized by this implementation.

```nix
hardware.thinkpadEc.cellVoltages = true;
```

Or load `thinkpad_ec_hwmon` with `cell_voltages=1`. This adds three
`Battery0 group A/B/C (experimental)` voltage channels to `sensors`.
Use `sensors -u t480_ec-isa-0000` for millivolt detail: ordinary text output
rounds voltage channels to two decimal places. Cache refresh is ten seconds;
the EC updates its battery cache separately.

On the tested 3S1P pack, each series group is one cell. With parallel cells,
group voltage cannot distinguish cells within the group. A/B/C are vendor
field order; physical pouch locations have not been mapped.

## Firmware and live evidence

Same verified N24HT37W image/hash as [the accelerometer investigation](t480-accelerometer.md).
Battery records begin at `0x800fd4`, stride `0x108`. Firmware SBS response
dispatcher `0x231d8` stores command `0x23` ManufacturerData at record `+0x84`.
Manufacturer is at `+0x54`, model at `+0x64`, pack voltage at `+0x30`.
The tested vendor block begins `05 67 01 67 00 00`; three little-endian
millivolt words follow at `+0x8a`, `+0x8c`, `+0x8e`.

Live captures on 2026-10-27:

| State | Pack mV | Current mA | A mV | B mV | C mV | Spread mV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Light load | 12090 | -289 | 4031 | 4028 | 4031 | 3 |
| One CPU thread active | 12017 | -823 | 4006 | 3997 | 4006 | 9 |
| One CPU thread active | 12003 | -1000 | 4006 | 4002 | 4004 | 4 |

A separate quiet capture returned 4033/4032/4032 mV against pack 12087 mV.
The fields change with load, are in cell-voltage range, and sum close to
pack voltage. This supports interpreting them as series-group voltages.
Vendor ordering and underlying gauge hardware are not independently mapped.
These are EC-cached values, not simultaneous raw ADC samples.

A load-transition snapshot differed from pack voltage by 137 mV. The driver
rejects discrepancies exceeding 100 mV against either bracketing pack read,
returning unavailable rather than publishing a misleading cell snapshot.
It also reads the vendor block twice, requires agreement, checks cache validity
before and after, and validates exact manufacturer/model and format prefix.

## Access and compatibility

Uses the existing EC `0x90=0x95` read32 request protocol. N24HT37W dispatcher
`0x199xx` handles opcode `0x15`; `0x0fea8` reads allowed RAM. Response bytes
are big-endian representations of native little-endian RAM words. Denied reads
can return zero on this firmware, unlike the X230 sentinel behaviour.

If required, authentication uses slot 1 via `0x3d=0xc1` and the public
N24HT37W key `7a41b149fe2101cf`, also present in coreboot's T480 configuration.
The key occurs at firmware offset `0x1ea89`. This enables a volatile debug
permission; it is not a user password and remains enabled after unloading.
No target-memory write, charging-policy change, or firmware flash is used.
Only the fixed battery-cache address list is read. All transactions hold ECLK;
request buffers are restored, except when a timeout may leave a command active.

X230 retains its existing addresses, key, battery identity and decoding.
Unverified profiles cannot enable debug channels. T480 charger/power channels
remain hidden. Suspend/resume and other battery models are untested.

## Interpreting a worn pack

A small spread at roughly two-thirds charge does not identify a failed cell.
Watch the readings during ordinary discharge, particularly at lower charge:
a cell that consistently falls lower under comparable load is a candidate for
the pack's limiting cell. Cells can also age together and lose capacity while
remaining well balanced. One brief load test cannot establish cell health.
