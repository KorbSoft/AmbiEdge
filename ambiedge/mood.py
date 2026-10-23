"""Mood light: a plain color or a slow effect instead of screen sync."""

import colorsys
import math
import re

import numpy as np

EFFECTS = ("solid", "breathe", "cycle", "rainbow")
EFFECT_LABELS = {
    "solid": "Solid color",
    "breathe": "Breathe (slow pulse)",
    "cycle": "Color cycle",
    "rainbow": "Rainbow",
}

# Kept slow on purpose: nothing here flashes faster than once every few seconds.
BREATHE_PERIOD = 6.0
CYCLE_PERIOD = 60.0
RAINBOW_PERIOD = 30.0

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_color(text):
    """'#rrggbb' -> (r, g, b); anything else -> warm white."""
    if not isinstance(text, str) or not HEX_COLOR.match(text):
        return (255, 140, 60)
    return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


def render(effect, color, t, n):
    """Colors for n LEDs in loop order at time t (seconds), as float RGB."""
    base = np.array(parse_color(color), np.float32)
    if n <= 0:
        return np.zeros((0, 3), np.float32)
    if effect == "breathe":
        level = 0.3 + 0.7 * (0.5 - 0.5 * math.cos(2 * math.pi * t / BREATHE_PERIOD))
        return np.tile(base * level, (n, 1))
    if effect in ("cycle", "rainbow"):
        h, s, v = colorsys.rgb_to_hsv(*(base / 255.0))
        s = max(s, 0.6)  # a gray base color would otherwise show no change
        if effect == "cycle":
            rgb = colorsys.hsv_to_rgb((h + t / CYCLE_PERIOD) % 1.0, s, v)
            return np.tile(np.array(rgb, np.float32) * 255, (n, 1))
        hues = (h + t / RAINBOW_PERIOD + np.arange(n) / n) % 1.0
        return np.array([colorsys.hsv_to_rgb(x, s, v) for x in hues], np.float32) * 255
    return np.tile(base, (n, 1))
