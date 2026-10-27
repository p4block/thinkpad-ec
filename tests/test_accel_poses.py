# SPDX-License-Identifier: WTFPL
"""A six-pose check must reject a dead or duplicated third axis."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'accel_xyz', Path(__file__).parents[1] / 'tools' / 'accel_xyz.py')
xyz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xyz)


class Poses(unittest.TestCase):
    def test_independent_axes(self):
        points = [[512, 512, 712], [512, 512, 312],
                  [712, 512, 512], [312, 512, 512],
                  [512, 712, 512], [512, 312, 512]]
        self.assertAlmostEqual(xyz.check_poses(points)['normalized_volume'], 1)
        self.assertEqual(xyz.check_poses(points)['center'], [512, 512, 512])

    def test_dead_or_duplicated_z(self):
        for points in [
            [[512, 512, 512], [512, 512, 512],
             [712, 512, 512], [312, 512, 512],
             [512, 712, 512], [512, 312, 512]],
            [[712, 512, 712], [312, 512, 312],
             [512, 712, 512], [512, 312, 512],
             [712, 512, 712], [312, 512, 312]],
        ]:
            with self.assertRaises(ValueError):
                xyz.check_poses(points)
