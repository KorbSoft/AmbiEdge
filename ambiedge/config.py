"""Settings: defaults, validation and the JSON file they're saved in."""

import json
import logging
import os
import sys

from .drivers import DRIVERS
from .layout import CORNERS
from .processing import COLOR_ORDERS
from .sampler import CAPTURE_METHODS

APP_NAME = "AmbiEdge"

log = logging.getLogger(__name__)

DEFAULTS = {
    # Device
    "driver": "virtual",
    "serial_port": "",
    "serial_baud": 115200,
    "wled_host": "",
    "wled_port": 21324,
    "openrgb_host": "127.0.0.1",
    "openrgb_port": 6742,
    "openrgb_device": 0,
    # Layout
    "left": 20,
    "top": 38,
    "right": 20,
    "bottom": 0,
    "bottom_gap": 0,
    "start_corner": "bottom-left",
    "clockwise": True,
    "shift": 0,
    "color_order": "RGB",
    # Look
    "brightness": 1.0,
    "saturation": 1.2,
    "smoothing": 0.5,
    "depth": 0.12,
    "gamma": 1.0,
    "skip_black_bars": True,
    # Advanced
    "fps": 30,
    "monitor": 0,
    "capture": "auto",
    "group": 1,
    "max_power": 255,
    "white_r": 1.0,
    "white_g": 1.0,
    "white_b": 1.0,
    "autostart_sync": False,
    "notice_shown": False,
}

RANGES = {
    "serial_baud": (300, 4000000),
    "wled_port": (1, 65535),
    "openrgb_port": (1, 65535),
    "openrgb_device": (0, 255),
    "left": (0, 500),
    "top": (0, 500),
    "right": (0, 500),
    "bottom": (0, 500),
    "bottom_gap": (0, 500),
    "shift": (-2000, 2000),
    "brightness": (0.0, 1.0),
    "saturation": (0.0, 3.0),
    "smoothing": (0.0, 0.95),
    "depth": (0.01, 0.5),
    "gamma": (0.5, 3.0),
    "fps": (1, 120),
    "monitor": (0, 15),
    "group": (1, 50),
    "max_power": (0, 765),
    "white_r": (0.0, 1.0),
    "white_g": (0.0, 1.0),
    "white_b": (0.0, 1.0),
}

CHOICES = {
    "driver": tuple(DRIVERS),
    "start_corner": CORNERS,
    "color_order": COLOR_ORDERS,
    "capture": CAPTURE_METHODS,
}


def config_dir():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "ambiedge")


def default_path():
    return os.path.join(config_dir(), "config.json")


def clean(raw):
    """Defaults merged with valid values from raw; bad or out-of-range values are fixed."""
    cfg = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in raw:
            continue
        value = raw[key]
        try:
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise ValueError
            elif isinstance(default, int):
                value = int(value)
            elif isinstance(default, float):
                value = float(value)
            else:
                value = str(value)
        except (TypeError, ValueError):
            log.warning("ignoring bad setting %s=%r", key, value)
            continue
        if key in RANGES:
            lo, hi = RANGES[key]
            value = type(default)(min(max(value, lo), hi))
        if key in CHOICES and value not in CHOICES[key]:
            log.warning("ignoring unknown %s=%r", key, value)
            continue
        cfg[key] = value
    return cfg


def _legacy_settings():
    """Settings from Screen LED Sync, this app's earlier name, if they exist."""
    path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ScreenLedSync", "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        return None
    old["driver"] = "robobloq"
    if old.pop("reverse", False):
        old.update(start_corner="bottom-right", clockwise=False)
    log.info("imported settings from %s", path)
    return old


def load_config(path=None):
    path = path or default_path()
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("not a JSON object")
    except FileNotFoundError:
        raw = (_legacy_settings() if path == default_path() else None) or {}
    except (OSError, ValueError) as e:
        log.warning("couldn't read %s (%s); using defaults", path, e)
        raw = {}
    return clean(raw)


def save_config(cfg, path=None):
    path = path or default_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)  # never leave a half-written file behind
