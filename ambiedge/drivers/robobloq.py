"""Robobloq SyncLight LED controller (USB HID 1A86:FE07).

Protocol worked out for interoperability from Robobloq's SyncLight 3.8.28 app:
- Every packet is split into 64-byte chunks, each sent as an HID output
  report with report ID 0.
- Command packets: "RB", length, sequence id, action, payload..., checksum.
- Screen-sync packets (firmware > 1.0.2): "SC", uint16 BE length, sequence
  id, 0x80, then 5-byte tuples (first_led, r, g, b, last_led), checksum.
  LED numbers are 1-based and inclusive.
- Checksum is the sum of all preceding bytes mod 256.
"""

import subprocess
import sys
import threading
import time

from .base import DeviceNotFound, Driver, Found

VID = 0x1A86
PID = 0xFE07
VENDOR_USAGE_PAGE = 0xFF00
CHUNK = 64

ACTION_SYNC_SCREEN = 0x80
ACTION_READ_INFO = 0x82
ACTION_SET_SECTION_LED = 0x86


def _hid():
    try:
        import hid
    except ImportError as e:
        raise DeviceNotFound(f"The hidapi package isn't installed ({e}).") from e
    return hid


def init_hid_on_main_thread():
    """Call once from the main thread at startup (macOS only, harmless elsewhere).

    On macOS, hidapi attaches its device manager to the run loop of the thread that first uses
    it. Device searches run on short-lived background threads; once the first of them exits, its
    run loop is freed and the next search crashes the process inside IOKit. Doing the first call
    on the main thread, which lives as long as the app, avoids that.
    """
    if sys.platform != "darwin":
        return
    try:
        import hid
        hid.enumerate(0xFFFF, 0xFFFF)  # no such device; just initializes hidapi
    except Exception:
        pass


def _find_paths(hid):
    return [d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == VENDOR_USAGE_PAGE]


def synclight_running():
    """True if Robobloq's own app is running; it would fight us over the lights."""
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SyncLight.exe", "/NH"], capture_output=True,
                             text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "synclight.exe" in out.lower()


def _checksum(buf):
    return sum(buf) % 256


def sc_packet(seq, ranges):
    """Screen-sync packet for ranges of (first_led, last_led, r, g, b)."""
    body = bytearray()
    for first, last, r, g, b in ranges:
        body += bytes((first, r, g, b, last))
    pkt = bytearray(b"SC") + (7 + len(body)).to_bytes(2, "big") + bytes([seq, ACTION_SYNC_SCREEN]) + body + b"\x00"
    pkt[-1] = _checksum(pkt)
    return bytes(pkt)


def rb_packet(seq, action, payload=b""):
    pkt = bytearray(b"RB") + bytes([6 + len(payload), seq, action]) + bytes(payload) + b"\x00"
    pkt[-1] = _checksum(pkt)
    return bytes(pkt)


def color_ranges(colors):
    """Merge runs of identical colors into (first_led, last_led, r, g, b) ranges."""
    rows = [tuple(c) for c in colors.tolist()]
    ranges = []
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i] != rows[start]:
            ranges.append((start + 1, i, *rows[start]))
            start = i
    return ranges


class RobobloqDriver(Driver):
    key = "robobloq"
    label = "Robobloq SyncLight (USB)"
    max_leds = 255  # LED numbers are single bytes in the protocol

    def __init__(self, options):
        super().__init__(options)
        self._dev = None
        self._seq = 1
        self._lock = threading.Lock()
        self._firmware = (0, 0, 0)

    @classmethod
    def discover(cls):
        hid = _hid()
        return [Found(f"Robobloq SyncLight on USB ({VID:04X}:{PID:04X})", {"driver": cls.key})
                for _ in _find_paths(hid)[:1]]

    def open(self):
        hid = _hid()
        paths = _find_paths(hid)
        if not paths:
            raise DeviceNotFound("No Robobloq controller found (USB 1A86:FE07). Is it plugged in?")
        self._dev = hid.device()
        try:
            self._dev.open_path(paths[0])
        except OSError as e:
            self._dev = None
            raise DeviceNotFound(f"Found the Robobloq controller but couldn't open it ({e}).") from e
        self._dev.set_nonblocking(True)
        info = self._read_info()
        if info:
            self._firmware = info["firmware"]
            self.led_count = info["lamps"] or None
            fw = ".".join(map(str, self._firmware))
            self.description = f"Robobloq SyncLight, firmware {fw}"
        else:
            self.description = "Robobloq SyncLight (didn't answer the info request)"
        if synclight_running():
            self.description += ". Warning: Robobloq's SyncLight app is running and will fight over the lights; close it"

    def close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            finally:
                self._dev = None

    def _next_seq(self):
        self._seq = 1 if self._seq >= 254 else self._seq + 1
        return self._seq

    def _write(self, packet):
        with self._lock:
            for i in range(0, len(packet), CHUNK):
                if self._dev.write(b"\x00" + packet[i:i + CHUNK]) < 0:
                    raise OSError("write to the LED controller failed (unplugged?)")

    def _read_info(self):
        while self._dev.read(CHUNK):  # drop stale replies
            pass
        self._write(rb_packet(self._next_seq(), ACTION_READ_INFO))
        deadline = time.time() + 1.0
        resp = b""
        while time.time() < deadline and len(resp) < 24:
            r = self._dev.read(CHUNK)
            if r:
                resp += bytes(r)
            else:
                time.sleep(0.01)
        if len(resp) < 24 or resp[:2] != b"RB":
            return None
        return {"lamps": resp[11], "firmware": tuple(resp[21:24])}

    def _send_ranges(self, ranges):
        if self._firmware > (1, 0, 2):
            self._write(sc_packet(self._next_seq(), ranges))
        else:
            # Old firmware: section packets, at most 11 tuples each.
            body = b"".join(bytes((first, r, g, b, last)) for first, last, r, g, b in ranges)
            for i in range(0, len(body), 55):
                self._write(rb_packet(self._next_seq(), ACTION_SET_SECTION_LED, body[i:i + 55]))
                time.sleep(0.02)

    def send(self, colors):
        if len(colors):
            self._send_ranges(color_ranges(colors[:self.max_leds]))

    def off(self, count):
        # Clear every LED the controller has, not just the ones in the layout.
        n = min(self.max_leds, max(count, self.led_count or 0) or self.max_leds)
        self._send_ranges([(1, n, 0, 0, 0)])
