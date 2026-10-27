# T480 EC accelerometer investigation

2026-09-27. This is an adaptation of an X230 G2HT35WW driver.
The T480 code is restricted to model T480 / ThinkPad T480 and EC ID N24HT37W.
The MEC1653 hardware shares the historical coreboot h8 interface; the h8 name
alone was not used as evidence for mailbox compatibility.

## Firmware evidence

Source: https://download.lenovo.com/pccbbs/mobiles/n24ur39w.iso
Lenovo release history: https://download.lenovo.com/pccbbs/mobiles/n24ur39w.html
The ISO contains FLASH/N24ET77W/$0AN2400.FL2. Remove its 32-byte `_EC` header
for the EC address space (286720 bytes). SHA256 of that payload:
`befcb425b9f2a83b959c0ef3ee490420b7c5e5ffa2a792fda821d0ff355e77cf`.
Firmware ID at payload offset 0x240: N24HT37W.
Saved running-machine boot logs also report N24HT37W-3.36.

Disassembled with GNU binutils 2.46, ARC600 little endian. First wrap in an
ELF with a code section, otherwise objdump treats the raw binary as data:

```
objcopy -I binary -O elf32-littlearc -B ARC600 \
  --rename-section .data=.text,alloc,load,readonly,code,contents ec.bin ec.elf
objdump -d ec.elf
```

Addresses below refer to the stripped payload, not the update container.

- 0x2c488 sets up mailbox device 0, port 0x1610, enabled=1 via 0xfa64.
  Constant pool: 0x2c7f4 holds 0x1610; table 0x304d4 maps device 0 to
  register 0xff3364. Code 0xfb10 constructs `(port << 16) | 0x8000 | enable`,
  therefore BAR value 0x16108001, matching the X230 mailbox mapping.
- 0x2c5dc dispatches the command byte in EC MMIO 0xff0100. It reads the
  argument at +0x10 and clears +0x14 through +0x2c.
- Jump table 0x2c998 maps command 0x10 to 0x2c9ae, 0x11 to 0x2c9e2,
  0x14 to 0x2cb02, and 0x17 to 0x2cb34.
- 0x10 calls 0x1d654: low 16 bits select rate, byte 2 selects the averaging
  count (clamped 1..8). Nonzero rate requests sampling; zero requests stop.
  The existing 0x0a0200c8 argument gives 200 Hz and averaging count 2.
- 0x11 calls 0x1d62c -> 0x1d39c with max 5 records. Its handler constructs
  the response without consuming payload arguments. Records are X/Y little
  endian 16-bit values plus a byte per record (stride 5). Code 0x1d592 adds
  an offset of 512 after axis mapping/scaling. This is the legacy two-axis
  output path, even though firmware also has a three-axis path (0x19).
- 0x14 takes boolean argument 0/1 and calls 0x1d728, which requests sensor
  power state through task 0x1b. Check the full result word at reply +28.
- 0x17/0x82 calls 0x1d770: status bit 0 is active sampling, bit 1 pending
  start, bit 3 self-test/pending self-test; subsequent bytes expose rate and
  filter. Status errors occupy reply byte 31.
- Completion 0x2cfd0 writes 0xff to the EC command register, then the command
  echo to MMIO +4. Host-side completion/ack follows the supplied X230 code;
  confirmed by successful live status and sampling transactions.

## Coreboot path

The current board's LPC decode includes 0x1600..0x167f. ACPI has ECLK and a
TWRI reservation for 0x1610..0x161f. Claiming just 0x1610..0x1611 avoids EC3
at 0x1618. No EC debug unlock, GPIO change, or firmware flash is needed.
The other `ECGS` reservation (0x1602/0x1606) is not this mailbox.

## Validation status

Kernel module builds against the installed NixOS kernel 7.2.7.
Live status query succeeded: status=00, rate=200, filter=2, error=00.
An 8-second read delivered 15 frames near X=515, Y=513. A second 30-second
read delivered 58 frames while the owner tilted left/right and forward/back
twice, then put the laptop on the desk. X ranged 306..722 and Y 310..729;
values returned near 512 when flat. Both closes reported active=N, last_error=0.
The two tests accumulated 73 samples.
The default `probe_only=1` mode only queries 0x17/0x82 and registers no input
sensor. It still performs a mailbox transaction, including argument/index
writes and acknowledgement; it is not electrically read-only.

Acquisition, physical axis response, and close/shutdown are verified.
The owner subsequently confirmed calibrated Sway rotation works with all four
poses calibrated near vertical. Suspend/resume remains unverified. Stock Lenovo
BIOS is untested and may lack the required ACPI ECLK mutex. Do not widen the
firmware guard based on shared EC family alone. The calibration tool requires physical poses before rotation.


## Three-axis path (2026-10-27)

Rechecked the local N24HT37W payload against the SHA256 above and the saved
ARC instruction listing and decompilation. This establishes the firmware
protocol and three-component acquisition. The owner subsequently completed
the physical six-pose test documented below.

- Command dispatch table at 0x2c998 routes command `0x19` to 0x2cbc6.
  The handler calls 0x1d634 with maximum count 4 and destination stack+9;
  its returned count goes at stack+8. It copies all 32 reply bytes from
  stack+8 into the host response. It consumes no request payload arguments.
- Wrapper 0x1d634 sets both r2 and r3 to 1 before tail-calling 0x1d39c.
  In contrast, the legacy wrapper 0x1d62c sets both to zero. These select
  three-component records and native signed output respectively.
- The response is byte 0 = count (0..4), followed by four possible records
  of **signed little-endian A, B, C (16 bits each), then one metadata byte**
  (stride 7). Byte 29 is remaining available records, byte 30 contains
  flags, byte 31 is zero in this handler. None of the trailing metadata
  is an axis. Zero count is no fresh frame, not a zero vector.
- The acquisition task at 0x1db7a passes three separate output pointers
  (stack, stack+2, stack+4) to the selected sensor read callback; on success
  it loads all three signed words and calls 0x1d924 at 0x1db98.
  That routine stores all three components in the ring at 0x800d08,
  eight-byte stride. Getter 0x1d39c averages and maps those three independent
  words. The third component is neither padding nor inferred from X/Y.
- Legacy formatter 0x1d592..0x1d5be converts mapped native A/B/C to
  `X = 512 + trunc(-C/80)`, `Y = 512 + trunc(-A/80)`, and
  `Z = 512 + trunc(B/80)`, but the legacy command omits Z. The updated
  driver applies that conversion per record before host averaging, retaining
  the established X/Y calibration and adding the actual third component.
  These are offset sensor counts, not SI units; native precision is reduced
  to preserve the existing input ABI. Physical axis signs and counts per g
  were subsequently measured in the six-pose check below. Four records rather than five also changes the
  averaging window slightly.

The T480 profile now uses output-only command 0x19 and advertises ABS_Z.
X230 retains command 0x11 and only ABS_X/ABS_Y. No additional sensor start,
power, debug, or configuration command is introduced. Mailbox error handling,
locking, warmup, freshness heartbeats and ownership cleanup remain in place.

### Physical validation

Build/install against the **running kernel**, then stop rotation and any other
input consumers before unloading the old module. With the NixOS module enabled,
rebuilding the system normally installs the driver for its configured kernel;
a reboot selects that kernel and module together. For a manual build using
matching kernel development headers:

```sh
make -C /path/to/matching/kernel/build M="$PWD" modules
systemctl --user stop thinkpad-rotate
sudo modprobe -r thinkpad_ec_accel
sudo insmod ./thinkpad_ec_accel.ko probe_only=0
python3 tools/accel_xyz.py --six-poses
cat /sys/module/thinkpad_ec_accel/parameters/{active,last_error,samples}
systemctl --user start thinkpad-rotate
```

The tool verifies device identity and advertised X/Y/Z support, accepts only
fresh heartbeat frames, rejects input overflow and moving captures, and asks
for six opposite orientations of the **base**. It checks nonzero response,
roughly equal spans, opposite-pose centers and three independent perpendicular
gravity response vectors. It prints measured medians and a PASS only if these
checks succeed. Failure may indicate an incorrect pose, motion, or a protocol
problem; preserve the output for investigation. It opens the normal input
interface and closes it on completion/error; no direct EC transactions are used.

Offline checks cover signed extremes, four seven-byte records, per-record
legacy rounding, metadata exclusion, malformed/error/empty frames, the existing
five-record X230 decoder, and output-only mailbox handling for command 0x19.
The six-pose checker rejects a constant or duplicated Z. The driver translation
unit compiles with Linux 7.3.0 exported kernel headers.

### Live validation (2026-10-27)

On T480 / N24HT37W with Linux 7.3.0, the updated accelerometer was built and
loaded alongside the existing local battery-current extension. An eight-second
capture delivered 14 fresh XYZ frames, roughly X=512..515, Y=512..514,
Z=718..721 with the base resting flat. Closing the reader returned active=N
and last_error=0. Rotation was restarted; EC temperatures and battery-current
readings remained available. Physical six-pose validation passed as documented
below. Suspend/resume remains untested.

### Six-pose physical validation (2026-10-27)

The owner ran `python3 tools/accel_xyz.py --six-poses` with the updated driver
and reported the following stationary medians:

| Base orientation | X | Y | Z |
| --- | ---: | ---: | ---: |
| Keyboard up | 513 | 512 | 720 |
| Keyboard down | 533 | 519 | 314.5 |
| Left edge down | 513 | 311 | 515 |
| Right edge down | 515 | 718 | 516 |
| Front/touchpad edge down | 717 | 513 | 524 |
| Rear/hinge edge down | 310 | 514 | 522 |

All three opposite-pose spans agree closely: 406.0533, 407.0061 and 407.0061
counts (approximately 203 counts/g). The normalized response-vector volume is
0.99890365, close to the ideal 1 for three perpendicular independent axes.
The check passed. This physically validates a genuine third acceleration axis.

Measured signs: X increases with the front edge down, Y increases with the
right edge down, and Z increases with the keyboard facing up. The estimated
zero-g center is [516.8333, 514.5, 518.5833]. These are approximate measurements,
not a new calibration applied by the driver; small alignment errors and sensor
bias remain. Suspend/resume is still untested.
