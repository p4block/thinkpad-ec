#!/usr/bin/env python3
# SPDX-License-Identifier: WTFPL
"""Record three-axis evdev frames, or verify six stationary base orientations."""
import argparse
import fcntl
import json
import math
import os
import select
import statistics
import struct
import time

EVENT = struct.Struct('@llHHi')


def abs_value(fd, axis):
    data = bytearray(24)
    fcntl.ioctl(fd, 0x80184540 + axis, data)  # EVIOCGABS(axis)
    return struct.unpack('@6i', data)[0]


def frames(fd, seconds):
    # Discard queued events left over from the preceding physical pose.
    while select.select([fd], [], [], 0)[0]:
        os.read(fd, EVENT.size * 64)
    axes = [abs_value(fd, i) for i in range(3)]
    deadline = time.monotonic() + seconds
    heartbeat = False
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], max(0, min(4, deadline - time.monotonic())))[0]:
            break
        block = os.read(fd, EVENT.size * 64)
        if not block or len(block) % EVENT.size:
            raise RuntimeError('Disconnected device or incomplete input event')
        for _, _, kind, code, value in EVENT.iter_unpack(block):
            if kind == 3 and code < 3:
                axes[code] = value
            elif kind == 4 and code == 5:
                heartbeat = True
            elif kind == 0 and code == 3:
                raise RuntimeError('Input overflow; repeat the stationary measurement')
            elif kind == 0 and code == 0 and heartbeat:
                heartbeat = False
                yield axes.copy()


def check_poses(points):
    """Require three independent, roughly equal gravity response vectors."""
    vectors = [[points[2*i][j] - points[2*i+1][j] for j in range(3)]
               for i in range(3)]
    lengths = [math.sqrt(sum(x*x for x in v)) for v in vectors]
    if min(lengths) < 100 or max(lengths) > 1.3 * min(lengths):
        raise ValueError('Missing/unequal axis response; repeat all six perpendicular poses')
    a, b, c = vectors
    volume = abs(a[0]*(b[1]*c[2]-b[2]*c[1]) -
                 a[1]*(b[0]*c[2]-b[2]*c[0]) +
                 a[2]*(b[0]*c[1]-b[1]*c[0])) / math.prod(lengths)
    if volume < 0.85:
        raise ValueError('Responses are not three independent perpendicular axes')
    centers = [[(points[2*i][j] + points[2*i+1][j])/2 for j in range(3)]
               for i in range(3)]
    if any(max(c[j] for c in centers) - min(c[j] for c in centers) > min(lengths)*0.1
           for j in range(3)):
        raise ValueError('Opposite poses disagree on the zero-g center')
    return {'opposite_pose_spans': lengths, 'normalized_volume': volume,
            'center': [statistics.mean(c[j] for c in centers) for j in range(3)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='/dev/input/thinkpad-ec-accel')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--six-poses', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 3:
        parser.error('--seconds must be finite and at least 3')
    fd = os.open(args.device, os.O_RDONLY | os.O_NONBLOCK)
    try:
        name = bytearray(256)
        fcntl.ioctl(fd, 0x81004506, name)  # EVIOCGNAME(256)
        if name.split(b'\0', 1)[0] != b'ThinkPad EC accelerometer':
            raise RuntimeError('Unexpected input device')
        caps = bytearray(8)
        fcntl.ioctl(fd, 0x80084523, caps)  # EVIOCGBIT(EV_ABS, 8)
        if caps[0] & 7 != 7:
            raise RuntimeError('Device does not advertise ABS_X/Y/Z; load the updated T480 driver')
        if not args.six_poses:
            count = 0
            for xyz in frames(fd, args.seconds):
                print('X=%d Y=%d Z=%d' % tuple(xyz), flush=True)
                count += 1
            if count < 3:
                raise RuntimeError('Insufficient fresh frames')
            return
        points = []
        for pose in ['base horizontal, keyboard facing up',
                     'base horizontal, keyboard facing down',
                     'base vertical, left edge down',
                     'base vertical, right edge down',
                     'base vertical, front (touchpad) edge down',
                     'base vertical, rear (hinge) edge down']:
            input(f'Hold the {pose}; press Enter, then keep still: ')
            # Allow motion/filter settling and drain startup samples.
            list(frames(fd, 2))
            samples = list(frames(fd, args.seconds))
            if len(samples) < 4:
                raise RuntimeError('Insufficient fresh frames; check module last_error')
            if any(max(s[j] for s in samples) - min(s[j] for s in samples) > 20
                   for j in range(3)):
                raise RuntimeError('Base moved during capture; repeat the check')
            point = [statistics.median(s[j] for s in samples) for j in range(3)]
            print('Median XYZ:', point)
            points.append(point)
        result = check_poses(points)
        print(json.dumps({'poses': points, **result}, indent=2))
        print('PASS: three independent axes respond to gravity in opposite physical poses.')
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error))
