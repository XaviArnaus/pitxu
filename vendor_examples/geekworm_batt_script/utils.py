import os
import re
import sys
import glob
from time import sleep
from threading import Thread

# ------------------------------------------------------------------------------
# USB
# ------------------------------------------------------------------------------

def find_devices(vendor_id = None, product_id = None):
    """
    Looks for USB devices
    optionally filtering by with the provided vendor and product IDs
    """
    devices = []

    for dn in glob.glob('/sys/bus/usb/devices/*'):
        try:
            vid = int(open(os.path.join(dn, "idVendor" )).read().strip(), 16)
            pid = int(open(os.path.join(dn, "idProduct")).read().strip(), 16)
            if ((vendor_id is None) or (vid == vendor_id)) and ((product_id is None) or (pid == product_id)):
                dns = glob.glob(os.path.join(dn, os.path.basename(dn) + "*"))
                for sdn in dns:
                    for fn in glob.glob(os.path.join(sdn, "*")):
                        if  re.search(r"\/ttyUSB[0-9]+$", fn):
                            devices.append(os.path.join("/dev", os.path.basename(fn)))
                        pass
                    pass
                pass
            pass
        except ( ValueError, TypeError, AttributeError, OSError, IOError ):
            pass
        pass

    return devices

# ------------------------------------------------------------------------------
# TIMER
# ------------------------------------------------------------------------------

class IntervalTimer(Thread):

    def __init__(self, interval, callback, c_kwargs={}):
        Thread.__init__(self)
        self.interval = interval
        self.callback = callback
        self.c_kwargs = c_kwargs
        self.daemon = True
        self.running = True
        self.start()

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            self.callback(**self.c_kwargs)
            sleep(self.interval)

# ------------------------------------------------------------------------------
# EXCEPTIONS
# ------------------------------------------------------------------------------

class ServiceExit(Exception):
    """
    Custom exception which is used to trigger the clean exit
    of all running threads and the main program.
    """
    pass

def service_shutdown(signum, frame):
    print('Caught signal %d' % signum)
    raise ServiceExit

# ------------------------------------------------------------------------------
# PID
# ------------------------------------------------------------------------------

def write_pid_file(name):
    pid = str(os.getpid())
    h = open("/tmp/%s.pid" % name, "w")
    h.write(pid)
    h.close()

# ------------------------------------------------------------------------------
# DEBUG
# ------------------------------------------------------------------------------

class Level(object):
    CRITICAL = 0
    WARNING = 1
    INFO = 2
    DEBUG = 3
    BLOAT = 4

VERBOSITY = Level.INFO

def printd(string, level):
    if VERBOSITY >= level:
        print(string)

def set_debug_level(lvl):
    global VERBOSITY
    VERBOSITY = lvl

# ------------------------------------------------------------------------------
# OTHER
# ------------------------------------------------------------------------------

def isRPi():
    return (os.uname()[4] == 'armv7l')

class Color(object):
    BLACK = '\x1b[1;30m'
    RED = '\x1b[1;31m'
    GREEN = '\x1b[1;32m'
    YELLOW = '\x1b[1;33m'
    BLUE = '\x1b[1;34m'
    MAGENTA = '\x1b[1;35m'
    CYAN = '\x1b[1;36m'
    WHITE = '\x1b[1;37m'
    LIGHT_GREY = '\x1b[0;30m'
    LIGHT_RED = '\x1b[0;31m'
    LIGHT_GREEN = '\x1b[0;32m'
    LIGHT_YELLOW = '\x1b[0;33m'
    LIGHT_BLUE = '\x1b[0;34m'
    LIGHT_MAGENTA = '\x1b[0;35m'
    LIGHT_CYAN = '\x1b[0;36m'
    LIGHT_WHITE = '\x1b[0;37m'

def clr(color, text):
    return color + str(text) + '\x1b[0m'

def check_root():
    if not os.geteuid() == 0:
        printd(clr(Color.RED, "Run as root."), Level.CRITICAL)
        exit(1)

def hex_offset_to_string(byte_array):
    temp = byte_array.replace("\n", "")
    temp = temp.replace(" ", "")
    return temp.decode("hex")

def mac_to_bytes(mac):
    return ''.join(chr(int(x, 16)) for x in mac.split(':'))

def bytes_to_mac(byte_array):
    return ':'.join("{:02x}".format(ord(byte)) for byte in byte_array)