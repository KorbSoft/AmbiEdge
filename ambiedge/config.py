"""Settings: defaults, validation and the JSON file they're saved in."""

import copy
import json
import logging
import os
import sys

from . import mood, schedule
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
    # Look: these mirror the profile being edited (see LOOK_KEYS)
    "brightness": 1.0,
    "saturation": 1.2,
    "smoothing": 0.5,
    "depth": 0.12,
    "gamma": 1.0,
    "vivid": 0.6,
    "skip_black_bars": True,
    "profile": "Desktop",
    "auto_profile": True,
    "profiles": {},  # filled from DEFAULT_PROFILES
    # Mood light
    "mood_color": "#ff8c3c",
    "mood_effect": "solid",
    "mood_brightness": 0.6,
    # Schedule and startup
    "off_when_idle": True,
    "schedule_enabled": False,
    "schedule_on": "18:00",
    "schedule_off": "01:00",
    "start_mode": "none",
    "close_to_tray": True,
    # Advanced
    "fps": 30,
    "monitor": 0,
    "capture": "auto",
    "group": 1,
    "max_power": 255,
    "white_r": 1.0,
    "white_g": 1.0,
    "white_b": 1.0,
    "notice_shown": False,
    "tray_hint_shown": False,
    "reported_leds": 0,  # LED count the controller last reported, for "Fit layout"
}

# Settings each profile has its own copy of.
LOOK_KEYS = ("brightness", "saturation", "smoothing", "depth", "gamma", "vivid", "skip_black_bars")

DEFAULT_PROFILES = {
    "Desktop": {"brightness": 1.0, "saturation": 1.2, "smoothing": 0.5, "depth": 0.12, "gamma": 1.0,
                "vivid": 0.6, "skip_black_bars": True, "apps": []},
    "Movie": {"brightness": 1.0, "saturation": 1.3, "smoothing": 0.75, "depth": 0.1, "gamma": 1.0,
              "vivid": 0.7, "skip_black_bars": True,
              "apps": ["vlc.exe", "mpc-hc64.exe", "mpc-be64.exe", "potplayermini64.exe", "mpv.exe",
                       "kodi.exe", "plex.exe", "plexamp.exe", "stremio.exe"]},
    "Game": {"brightness": 1.0, "saturation": 1.25, "smoothing": 0.3, "depth": 0.12, "gamma": 1.0,
             "vivid": 0.6, "skip_black_bars": False, "apps": []},
}
DEFAULTS["profiles"] = DEFAULT_PROFILES
MAX_PROFILE_NAME = 32

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
    "vivid": (0.0, 1.0),
    "mood_brightness": (0.0, 1.0),
    "reported_leds": (0, 65535),
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
    "mood_effect": mood.EFFECTS,
    "start_mode": ("none", "sync", "mood"),
}

# Text settings that must match a pattern.
PATTERNS = {
    "mood_color": mood.HEX_COLOR,
    "schedule_on": schedule.TIME,
    "schedule_off": schedule.TIME,
}


def config_dir():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "ambiedge")


def default_path():
    return os.path.join(config_dir(), "config.json")


def _clean_value(key, value, default):
    """value converted to the default's type and checked; raises ValueError if it's unusable."""
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError
    elif isinstance(default, int):
        value = int(value)
    elif isinstance(default, float):
        value = float(value)
    else:
        value = str(value)
    if key in RANGES:
        lo, hi = RANGES[key]
        value = type(default)(min(max(value, lo), hi))
    if key in CHOICES and value not in CHOICES[key]:
        raise ValueError
    if key in PATTERNS and not PATTERNS[key].match(value):
        raise ValueError
    return value


def _clean_profiles(raw):
    profiles = {}
    if isinstance(raw, dict):
        for name, p in raw.items():
            name = str(name).strip()[:MAX_PROFILE_NAME]
            if not name or not isinstance(p, dict):
                continue
            clean_p = {}
            for key in LOOK_KEYS:
                try:
                    clean_p[key] = _clean_value(key, p.get(key, DEFAULTS[key]), DEFAULTS[key])
                except (TypeError, ValueError):
                    clean_p[key] = DEFAULTS[key]
            apps = p.get("apps", [])
            clean_p["apps"] = sorted({str(a).strip().lower() for a in apps if str(a).strip()}) if isinstance(apps, list) else []
            profiles[name] = clean_p
    return profiles


def clean(raw):
    """Defaults merged with valid values from raw; bad or out-of-range values are fixed."""
    cfg = copy.deepcopy(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in raw or key == "profiles":
            continue
        try:
            cfg[key] = _clean_value(key, raw[key], default)
        except (TypeError, ValueError):
            log.warning("ignoring bad setting %s=%r", key, raw[key])
    if raw.get("autostart_sync") is True and "start_mode" not in raw:  # setting from 1.0.0
        cfg["start_mode"] = "sync"

    profiles = _clean_profiles(raw.get("profiles"))
    if not profiles:
        # No profiles yet (new or 1.0.0 settings): start from the defaults, keeping the
        # look settings the user already had as their Desktop profile.
        profiles = copy.deepcopy(DEFAULT_PROFILES)
        profiles["Desktop"].update({k: cfg[k] for k in LOOK_KEYS})
        cfg["profile"] = "Desktop"
    if cfg["profile"] not in profiles:
        cfg["profile"] = next(iter(profiles))
    cfg["profiles"] = profiles
    cfg.update({k: profiles[cfg["profile"]][k] for k in LOOK_KEYS})
    return cfg


def copy_config(cfg):
    """A copy that's safe to read from another thread while the original is edited."""
    out = dict(cfg)
    out["profiles"] = {name: dict(p, apps=list(p["apps"])) for name, p in cfg["profiles"].items()}
    return out


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
