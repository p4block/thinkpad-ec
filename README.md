# thinkpad-ec

Linux drivers for ThinkPad embedded-controller sensors and the base accelerometer.
Currently verified on **X230 / G2HT35WW** and **T480 / N24HT37W**, with coreboot
ACPI providing `\_SB.PCI0.LPCB.EC.ECLK`. Shared EC hardware is not proof that
another model or firmware revision is compatible.

- `thinkpad_ec_hwmon`: board/battery temperatures; X230 additionally has battery
  current and charger telemetry. Optional cell-group reads on X230 and T480 stay disabled
  unless explicitly enabled and require exact firmware/battery guards. T480
  additionally supports opt-in USB-C negotiated voltage for both ports.
- `thinkpad_ec_accel`: raw X/Y (X230) or X/Y/Z (T480) input, fresh-frame
  heartbeats, acquisition on first open and shutdown on last close. One implementation, checked firmware
  profiles. No EC debug unlock is used for acceleration or ordinary telemetry.

Desktop rotation lives in [thinkpad-rotate](https://github.com/p4block/thinkpad-rotate).
This repository has no desktop daemon or rotation dependency.

## More models and firmware

Reports of partial or complete support are welcome. Run `python3 tools/report.py`
and open a compatibility issue. [Adding support](docs/adding-support.md) covers
explicit candidate-profile testing, schematic/firmware mapping, and validation.

`profiles.h` separates reusable protocol/sensor maps from exact model/EC matches.
A new firmware revision can reuse a verified profile; a different board map can
be added without forking the driver. Temperature and motion support are tracked
independently. Unknown hardware never silently inherits X230 behavior.

## NixOS

Import `module.nix` or the flake's `nixosModules.default`:

```nix
hardware.thinkpadEc = {
  enable = true;
  accelerometer = true;
  # T480 / N24HT37W, optional:
  pdContract = true;
  # Supported battery models only, optional:
  cellVoltages = true;
};
```

Telemetry defaults on; accelerometer defaults off. `probeOnly = true` makes
acceleration a status-only diagnostic. `cellVoltages = true` opts into the
experimental debug feature: X230 SANYO LNV-45N1023 or T480 internal
LGC LNV-01AV420. See [T480 cell-group voltages](docs/t480-cells.md).
`pdContract = true` independently enables T480 USB-C contract reads; both
features can enable a volatile EC debug permission. Neither changes charging
policy. Keep these options omitted on unsupported firmware or battery models.

With PD telemetry enabled, `sensors t480_ec-isa-0000` includes:

```text
USB-C PD0 negotiated: 20.00 V
USB-C PD1 negotiated:     N/A
```

PD0 is the lower **Thunderbolt** port; PD1 is the upper USB-C port. These are
negotiated fixed-PDO voltages, not measured VBUS voltages or actual watts.
Disconnected ports show `N/A`; readings refresh once per second. See
[PD implementation and limits](docs/t480-pd.md).

The module builds against your configured kernel, loads the selected drivers,
and grants the active local session access to `/dev/input/thinkpad-ec-accel`.
It keeps the sensor out of libinput. No `input` group membership is needed.

For the old repositories, remove their imports and module packages first.
The kernel module names changed from `x230_ec_hwmon`, `x230_ec_accel` and
`t480_ec_accel`; reboot or stop consumers and unload those before loading the
new modules. Never run two accelerometer drivers against the same mailbox.

## Build and inspect

```sh
nix build
nix flake check
# Or, with matching kernel headers, from a path without spaces:
make -C /lib/modules/$(uname -r)/build M="$PWD" modules
sudo insmod thinkpad_ec_hwmon.ko
sudo insmod thinkpad_ec_accel.ko probe_only=1
sensors
```

`probe_only=0` registers the accelerometer. Loading it alone does not start
acquisition. Its name is `ThinkPad EC accelerometer`, with ABS_X/ABS_Y,
ABS_Z on T480, and MSC_TIMESTAMP. Raw counts need per-machine calibration in the consumer.
`active`, `last_error` and `samples` are readable module parameters.

T480 acceleration uses the firmware three-axis command with X/Y converted to
the existing coordinate system and scale; rotation calibration remains usable.
`python3 tools/accel_xyz.py` displays all three axes; add `--six-poses` for
physical validation. The new three-axis path is firmware-traced, tested
offline and physically validated in six opposite base orientations
(see the investigation doc).

T480 temperature channels unavailable at registration are hidden. Reload hwmon to discover
a newly attached battery. Visible channels that lose data return ENODATA.
Temperatures are cached for ten seconds; firmware cache age is unknown.
Both modules expose `selected_profile`, `firmware` and `verified` parameters.

## Evidence and limits

[Protocol](docs/protocol.md), [compatibility](docs/compatibility.md),
[T480 temperatures and board mapping](docs/t480.md),
[complete thermal circuit audit](docs/t480-thermal-audit.md),
[T480 cell-group voltages](docs/t480-cells.md),
[T480 USB-C contracts](docs/t480-pd.md),
[T480 accelerometer trace](docs/t480-accelerometer.md).

Driver build, mailbox/page failure tests and live T480 coexistence checks pass.
X230 behavior is preserved from the previously tested driver; the consolidated
build has not been retested on physical X230 hardware. Suspend/resume and stock
Lenovo BIOS remain unverified for this release. No firmware, board files,
private dumps or personal calibration are distributed.

[WTFPL](LICENSE). GPL-compatible kernel module tags are retained. Development
included AI-assisted firmware analysis, with hardware validation as documented.
