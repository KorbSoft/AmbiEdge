"""Where each LED sits around the screen, and the order the strip is wired in.

Positions are numbered in a clockwise "loop" (as seen from the front of the screen) that starts
at the bottom-left corner: up the left side, across the top, down the right side, then right to
left along the bottom. A layout maps that loop onto the strip's own order, which depends on the
corner the strip starts at and which way it runs.
"""

import numpy as np

CORNERS = ("bottom-left", "top-left", "top-right", "bottom-right")


class Layout:
    def __init__(self, left, top, right, bottom=0, bottom_gap=0,
                 start_corner="bottom-left", clockwise=True, shift=0):
        self.left, self.top, self.right, self.bottom = (max(0, int(n)) for n in (left, top, right, bottom))
        self.bottom_gap = max(0, int(bottom_gap))
        self.total = self.left + self.top + self.right + self.bottom
        n = self.total
        if n == 0:
            self.order = np.zeros(0, dtype=int)
            return
        corner = {
            "bottom-left": 0,
            "top-left": self.left,
            "top-right": self.left + self.top,
            "bottom-right": self.left + self.top + self.right,
        }.get(start_corner, 0)
        steps = np.arange(n)
        if clockwise:
            order = (corner + steps) % n
        else:
            order = (corner - 1 - steps) % n
        # shift > 0: LED 1 sits that many positions further along the strip than the corner.
        self.order = np.roll(order, -int(shift) % n)

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg["left"], cfg["top"], cfg["right"], cfg["bottom"], cfg["bottom_gap"],
                   cfg["start_corner"], cfg["clockwise"], cfg["shift"])

    @property
    def key(self):
        """Changes whenever the LED positions or order change."""
        return (self.left, self.top, self.right, self.bottom, self.bottom_gap, self.order.tobytes())

    @staticmethod
    def loop_from_edges(left, top, right, bottom):
        """Edge colors (sides top->bottom, top/bottom left->right) to clockwise loop order."""
        return np.concatenate([left[::-1], top, right, bottom[::-1]], axis=0)

    def to_chain(self, loop_colors):
        """Loop order -> strip order (index 0 is LED 1)."""
        return np.asarray(loop_colors)[self.order]

    def to_loop(self, chain_colors):
        """Strip order -> loop order."""
        chain_colors = np.asarray(chain_colors)
        out = np.zeros_like(chain_colors)
        out[self.order] = chain_colors
        return out

    def bottom_split(self):
        """(LEDs left of the gap, LEDs right of the gap) on the bottom edge."""
        right_part = self.bottom // 2 if self.bottom_gap else 0
        return self.bottom - right_part, right_part


def test_pattern(layout, blink_on=True):
    """Left red, top green, right blue, bottom yellow, in loop order.

    The first LED of each edge going clockwise is white, so the corners are easy to see, and
    LED 1 blinks so you can tell where the strip starts.
    """
    L, T, R, B = layout.left, layout.top, layout.right, layout.bottom
    loop = np.concatenate([
        np.tile([255, 0, 0], (L, 1)),
        np.tile([0, 255, 0], (T, 1)),
        np.tile([0, 0, 255], (R, 1)),
        np.tile([255, 160, 0], (B, 1)),
    ]).astype(np.float32).reshape(-1, 3)
    for start, count in ((0, L), (L, T), (L + T, R), (L + T + R, B)):
        if count:
            loop[start] = 255
    if layout.total:
        loop[layout.order[0]] = 255 if blink_on else 0
    return loop
