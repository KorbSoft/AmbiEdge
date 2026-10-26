"""The app icon, drawn in code so there are no image files to ship.

A dark screen with a glow around it: rainbow when the lights are on, gray when they're off.
"""

import struct
import zlib

import numpy as np


def _hsv_to_rgb(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    v = np.broadcast_to(v, h.shape)
    p = np.broadcast_to(p, h.shape)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def render(size, active=True):
    """(size, size, 4) uint8 RGBA icon."""
    s = float(size)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) + 0.5
    cx = cy = s / 2
    hw, hh, radius = s * 0.30, s * 0.21, s * 0.05
    qx = np.abs(x - cx) - (hw - radius)
    qy = np.abs(y - cy) - (hh - radius)
    dist = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius

    angle = (np.arctan2(y - cy, x - cx) / (2 * np.pi)) % 1.0
    if active:
        glow_rgb = _hsv_to_rgb(angle, 0.8, 1.0) * 255
    else:
        glow_rgb = np.full(angle.shape + (3,), 150.0)
    glow_a = np.clip(1 - dist / (s * 0.2), 0, 1) ** 1.5 * (dist > 0)

    screen_a = np.clip(0.5 - dist * (64 / s), 0, 1)
    border = np.clip(1 - np.abs(dist + s * 0.02) / (s * 0.025), 0, 1)[..., None]
    screen_rgb = np.array([28, 30, 36], np.float32) * (1 - border) + np.array([90, 94, 104], np.float32) * border

    sa = screen_a[..., None]
    rgb = screen_rgb * sa + glow_rgb * (1 - sa)
    alpha = screen_a + glow_a * (1 - screen_a)
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha * 255, 0, 255)])
    return out.round().astype(np.uint8)


def png_bytes(rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[row].tobytes() for row in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico_bytes(sizes=(16, 24, 32, 48, 64, 128, 256)):
    images = [png_bytes(render(n)) for n in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for n, data in zip(sizes, images):
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(images)


if __name__ == "__main__":
    # python -m ambiedge.icon AmbiEdge.ico for Windows, or AmbiEdge.png (1024 px, which PyInstaller
    # turns into the .icns of the macOS app when Pillow is installed).
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "AmbiEdge.ico"
    with open(path, "wb") as f:
        f.write(png_bytes(render(1024)) if path.lower().endswith(".png") else ico_bytes())
