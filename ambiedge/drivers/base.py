"""The interface every LED controller driver implements."""

from collections import namedtuple

import numpy as np

# A controller found by Driver.discover(): text for the UI and the settings that select it.
Found = namedtuple("Found", "label options")


class DeviceNotFound(Exception):
    """The controller isn't connected or can't be reached. The app keeps retrying."""


class Driver:
    """One LED controller.

    `options` is the whole app config; each driver reads the keys it lists in `option_keys`.
    Raise DeviceNotFound from open() when the device isn't there, and OSError from send()
    when the connection drops; the engine reconnects in both cases.
    """

    key = ""             # value of the "driver" setting
    label = ""           # name shown in the UI
    option_keys = ()     # settings this driver reads; changing one reconnects
    max_leds = 65535

    def __init__(self, options):
        self.options = options
        self.description = self.label
        self.led_count = None  # LEDs the device says it has, when it can tell

    def open(self):
        pass

    def send(self, colors):
        """colors: (n, 3) uint8 array in strip order, already in the strip's color order."""
        raise NotImplementedError

    def off(self, count):
        """Turn the lights off before closing."""
        n = max(count, self.led_count or 0)
        if n:
            self.send(np.zeros((min(n, self.max_leds), 3), np.uint8))

    def close(self):
        pass

    @classmethod
    def discover(cls):
        """Return a list of Found for devices of this type that can be detected automatically."""
        return []
