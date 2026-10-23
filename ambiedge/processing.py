"""Turns sampled screen colors into the values sent to the strip."""

import numpy as np

COLOR_ORDERS = ("RGB", "RBG", "GRB", "GBR", "BRG", "BGR")


class ColorProcessor:
    def __init__(self):
        self._state = None

    def reset(self):
        self._state = None

    def process(self, colors, cfg):
        """colors: (n, 3) RGB in strip order. Returns (to_send, preview).

        to_send is uint8 in the strip's color order; preview is the same colors as RGB.
        """
        c = np.asarray(colors, dtype=np.float32).reshape(-1, 3)
        saturation = cfg["saturation"]
        if saturation != 1.0:
            gray = c.mean(axis=1, keepdims=True)
            c = gray + (c - gray) * saturation
        c = np.clip(c * cfg["brightness"], 0, 255)
        c[c.sum(axis=1) < cfg.get("black_level", 20)] = 0

        # smoothing 0 = instant, 0.95 = very slow fade
        if self._state is None or self._state.shape != c.shape:
            self._state = c
        else:
            alpha = 1.0 - min(max(cfg["smoothing"], 0.0), 0.95)
            self._state = self._state + (c - self._state) * alpha
        out = self._state.copy()

        gamma = cfg.get("gamma", 1.0)
        if gamma != 1.0:
            out = 255.0 * (out / 255.0) ** gamma
        out *= np.array([cfg["white_r"], cfg["white_g"], cfg["white_b"]], np.float32)

        # Power limit per LED: caps R+G+B so a USB-powered strip doesn't overload its supply.
        total = out.sum(axis=1)
        over = total > cfg["max_power"]
        out[over] *= (cfg["max_power"] / total[over])[:, None]

        group = max(1, int(cfg["group"]))
        if group > 1:
            for start in range(0, len(out), group):
                out[start:start + group] = out[start:start + group].mean(axis=0)

        preview = np.clip(out, 0, 255).astype(np.uint8)
        order = cfg["color_order"]
        if order != "RGB" and order in COLOR_ORDERS:
            return preview[:, ["RGB".index(ch) for ch in order]], preview
        return preview, preview
