#! /usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

#   Geekworks RPi Power Pack Hat Monitor Service
#   Copyright (C) 2018 by Xose Pérez <xose.perez@gmail.com>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import signal
import threading
import time
import argparse

from lib.smbus import SMBus
from lib.config import Config
from lib.utils import ServiceExit, service_shutdown, write_pid_file
from lib.utils import printd, Level, Color, clr, set_debug_level

# ------------------------------------------------------------------------------

class Battery(threading.Thread):

    bus = SMBus(1)
    address = 0x62
    capacity = 50
    state = 1
    count = 0
    flag = False

    def __init__(self, interval, threshold, mincount):
        threading.Thread.__init__(self)
        self.interval = interval
        self.threshold = threshold
        self.mincount = mincount
        self.shutdown_flag = threading.Event()
        self.bus.write_byte_data(self.address, 0x0A, 0x00)

    def run(self):

        while not self.shutdown_flag.is_set():

            # Calculate current charge
            msb = int(self.bus.read_byte_data(self.address, 0x04))
            lsb = int(self.bus.read_byte_data(self.address, 0x05))
            capacity = msb + lsb / 255.0

            # Calculate tendency
            if (self.capacity > capacity):
                state = 0
            if (self.capacity < capacity):
                state = 1
            if (self.state != state):
                self.count = 0
                self.state = state
            self.capacity = capacity
            self.count = self.count + 1

            # Debug
            printd(clr(Color.LIGHT_GREY, "Battery capacity: %6.2f%% (%s)" % (self.capacity, "charging" if self.state == 1 else "discharging")), Level.DEBUG)

            # Alerts
            if not self.flag and self.state == 0 and self.capacity < self.threshold and self.count > self.mincount:
                self.flag = True
                message = "Shutting down system in 60 seconds due to critical battery level"
                printd(clr(Color.GREEN, message), Level.INFO)
                os.system("sudo shutdown -h +1 %s" % message)
            if self.flag and self.state == 1:
                self.flag = False
                message = "Battery charging: shutdown cancelled"
                printd(clr(Color.GREEN, message), Level.INFO)
                os.system("sudo shutdown -c")

            # Check again in X seconds
            time.sleep(self.interval)

# ------------------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", dest="config", action="store", help="configuration file", default="config.yml")
    parser.add_argument("-v", dest="verbose", action="count", help="verbose mode", default=0)
    arg = parser.parse_args(sys.argv[1:])

    # set debug level
    set_debug_level(Level.INFO if 0 == arg.verbose else Level.DEBUG)

    # Welcome message
    printd(clr(Color.WHITE, "\nGeekworm Hat Battery Monitor\n"), Level.INFO)

    # Load configuration
    config = Config(arg.config)
    config.load();

    # Configuration values
    check_interval = config.get("battery", "check_interval", 10)
    charge_threshold = config.get("battery", "charge_threshold", 25)
    threshold_count = config.get("battery", "threshold_count", 6)

    try:

        # Init job and signal callbacks
        signal.signal(signal.SIGTERM, service_shutdown)
        signal.signal(signal.SIGINT, service_shutdown)
        job = Battery(check_interval, charge_threshold, threshold_count)
        job.start()

        # Keep on running
        while True:
            time.sleep(1)

    except ServiceExit:
        job.shutdown_flag.set()
        None

if __name__ == '__main__':
    main()