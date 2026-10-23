"""LED controller drivers.

To add a controller, subclass Driver (see base.py), add it to DRIVERS and give any new
settings a default in config.py.
"""

import logging

from .adalight import AdalightDriver
from .base import DeviceNotFound, Driver, Found
from .openrgb import OpenRGBDriver
from .robobloq import RobobloqDriver
from .virtual import VirtualDriver
from .wled import WledDriver

log = logging.getLogger(__name__)

DRIVERS = {d.key: d for d in (VirtualDriver, RobobloqDriver, AdalightDriver, WledDriver, OpenRGBDriver)}

# Settings that pick the device; when one changes while running, the engine reconnects.
DEVICE_KEYS = ("driver",) + tuple(k for d in DRIVERS.values() for k in d.option_keys)


def create(cfg):
    return DRIVERS.get(cfg["driver"], VirtualDriver)(cfg)


def discover_all():
    found = []
    for cls in DRIVERS.values():
        try:
            found += cls.discover()
        except Exception as e:
            log.debug("discovery failed for %s: %s", cls.key, e)
    return found


__all__ = ["DRIVERS", "DEVICE_KEYS", "DeviceNotFound", "Driver", "Found", "create", "discover_all"]
