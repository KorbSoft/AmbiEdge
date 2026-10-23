"""Screen capture and edge-color sampling."""

import logging
import sys

import numpy as np

log = logging.getLogger(__name__)

# Work on a downscaled frame about this wide; plenty for averaging edges.
TARGET_WIDTH = 480

CAPTURE_METHODS = ("auto", "dxcam", "mss")


class Capture:
    """Grabs full frames as BGRA numpy arrays.

    On Windows it prefers DXGI desktop duplication (dxcam), which is fast and also sees
    borderless-fullscreen games. Elsewhere, or if that fails, it uses mss (GDI / X11 / Quartz).
    """

    def __init__(self, monitor=0, method="auto"):
        self.monitor = monitor
        self.method = method
        self.backend = None
        self._cam = None
        self._mss = None
        self._last = None
        if method in ("auto", "dxcam") and sys.platform == "win32":
            try:
                import dxcam
                self._cam = dxcam.create(output_idx=monitor, output_color="BGRA")
                if self._cam is None:
                    raise RuntimeError("dxcam returned no camera")
                self.backend = "dxcam"
                return
            except Exception as e:
                if method == "dxcam":
                    raise
                log.info("dxcam unavailable (%s), using mss", e)
        import mss
        self._mss = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        if monitor + 1 >= len(self._mss.monitors):
            self.close()
            raise RuntimeError(f"there is no monitor #{monitor}")
        self.backend = "mss"

    def grab(self):
        if self._cam is not None:
            frame = self._cam.grab()
            if frame is not None:  # None means the screen hasn't changed
                self._last = frame
        else:
            self._last = np.asarray(self._mss.grab(self._mss.monitors[self.monitor + 1]))
        return self._last

    def close(self):
        if self._cam is not None:
            try:
                self._cam.release()
            except Exception:
                pass
            del self._cam
            self._cam = None
        if self._mss is not None:
            self._mss.close()
            self._mss = None


def _content_bounds(img, threshold=18, max_frac=0.25):
    """Find letterbox/pillarbox black bars. Returns (top, bottom, left, right) bounds of content."""
    h, w, _ = img.shape
    lum = img.max(axis=2)
    rows = np.nonzero(lum.max(axis=1) > threshold)[0]
    cols = np.nonzero(lum.max(axis=0) > threshold)[0]
    if rows.size == 0 or cols.size == 0:
        return 0, h, 0, w
    top = min(rows[0], int(h * max_frac))
    bottom = max(rows[-1] + 1, h - int(h * max_frac))
    left = min(cols[0], int(w * max_frac))
    right = max(cols[-1] + 1, w - int(w * max_frac))
    return top, bottom, left, right


def _segment_means(band, n, axis):
    """Split band into n segments along axis and return (n, 3) mean colors.

    Works even when n is larger than the band (segments then share pixels).
    """
    if n <= 0:
        return np.zeros((0, 3), np.float32)
    length = band.shape[axis]
    other = 1 - axis
    line = band.sum(axis=other)  # (length, 3)
    cs = np.concatenate([np.zeros((1, 3), line.dtype), np.cumsum(line, axis=0)])
    starts = np.minimum((np.arange(n) * length) // n, length - 1)
    ends = np.maximum((np.arange(1, n + 1) * length) // n, starts + 1)
    counts = (ends - starts) * band.shape[other]
    return (cs[ends] - cs[starts]) / counts[:, None]


def sample_edges(frame, layout, depth=0.12, skip_black_bars=True):
    """Average colors along the screen edges for a Layout.

    Returns (left, top, right, bottom) float arrays of RGB, ordered top->bottom for the sides
    and left->right for the top and bottom.
    """
    h, w = frame.shape[:2]
    step = max(1, w // TARGET_WIDTH)
    img = frame[::step, ::step, 2::-1].astype(np.float32)  # BGRA -> RGB
    if skip_black_bars:
        t, b, l, r = _content_bounds(img)
        img = img[t:b, l:r]
    sh, sw = img.shape[:2]
    d = max(1, int(min(sh, sw) * depth))
    left = _segment_means(img[:, :d], layout.left, axis=0)
    top = _segment_means(img[:d, :], layout.top, axis=1)
    right = _segment_means(img[:, sw - d:], layout.right, axis=0)
    bottom = _segment_means(img[sh - d:, :], layout.bottom + layout.bottom_gap, axis=1)
    if layout.bottom_gap:
        # Drop the samples in the gap (e.g. where a monitor stand is) between the two halves.
        left_part, right_part = layout.bottom_split()
        bottom = np.concatenate([bottom[:left_part], bottom[len(bottom) - right_part:]])
    return left, top, right, bottom
