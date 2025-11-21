'''
This module introduces the Amplitude class which collects methods for
calculating, adding and displaying.

https://github.com/kmein/vu-meter/
'''

import math
import struct
from decimal import Decimal

# RATE = 44100
# INPUT_BLOCK_TIME = 0.05
# INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)
SHORT_NORMALIZE = 1.0 / 32768.0

class Amplitude(object):
    ''' an abstraction for Amplitudes (with an underlying float value)
    that packages a display function and many more '''

    def __init__(self, value=0):
        self.value = value

    def __add__(self, other):
        return Amplitude(self.value + other.value)

    def __sub__(self, other):
        return Amplitude(self.value - other.value)

    def __gt__(self, other):
        return self.value > other.value

    def __lt__(self, other):
        return self.value < other.value

    def __eq__(self, other):
        return self.value == other.value

    def to_int(self, scale=8):
        ''' convert an amplitude to an integer given a scale such that one can
        choose the precision of the resulting integer '''
        # return int(round(Decimal(self.value * scale), 0))
        return int(self.value * scale)

    def __int__(self):
        return self.to_int()

    def __str__(self):
        return self.value + " dB"

    @staticmethod
    def from_data(block):
        ''' generate an Amplitude object based on a block of audio input data '''
        count = len(block) / 2
        # print(count)
        shorts = struct.unpack("%dh" % count, block)
        sum_squares = sum(s**2 * SHORT_NORMALIZE**2 for s in shorts)
        # print(sum_squares)
        # print(math.sqrt(sum_squares / count))
        return Amplitude(math.sqrt(sum_squares / count))
    
    def get_values(self, maximal, scale=8):
        ''' get an amplitude and another (marked) maximal Amplitude
        graphically '''
        int_val = self.to_int(scale)
        maximal_val = maximal.to_int(scale)
        delta = abs(int_val - maximal_val)
        return (int_val, maximal_val, delta)

    def display(self, maximal, scale=8):
        ''' display an amplitude and another (marked) maximal Amplitude
        graphically '''
        int_val, maximal_val, delta = self.get_values(maximal, scale)
        print(int_val * '*', (delta-1) * ' ', '|')
        