#!/usr/bin/env python
# encoding: utf-8
#
# test_ffs.py
#
# Created by José Sánchez-Gallego on 15 Feb 2017.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import numpy
import unittest

from tcc.utils import ffs


class TestFFS(unittest.TestCase):

    def test_ffs_altitude(self):

        values = ffs.telescope_alt
        measured = ffs.ffs_alt
        interpolated = [ffs.get_ffs_altitude(value)[0] for value in values]
        numpy.testing.assert_allclose(measured, interpolated, atol=2)

    def test_minimum_altitude(self):

        ffs_altitude, is_ffs_at_minimum = ffs.get_ffs_altitude(40)
        self.assertEqual(ffs_altitude, ffs.ffs_alt_limit)
        self.assertTrue(is_ffs_at_minimum)
