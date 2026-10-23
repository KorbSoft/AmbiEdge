"""OpenRGB SDK server (TCP, default port 6742).

OpenRGB (https://openrgb.org) talks to motherboard ARGB headers, RGB controllers and many
branded strips. With its SDK server running, this driver sends colors to one of its devices.

Packets: "ORGB", device index, packet id, data size (uint32 LE each), then data. This client
uses protocol version 0, which every OpenRGB server still accepts and which has the simplest
controller-data layout.
"""

import socket
import struct

import numpy as np

from .base import DeviceNotFound, Driver, Found

MAGIC = b"ORGB"
REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
SET_CLIENT_NAME = 50
UPDATE_LEDS = 1050
SET_CUSTOM_MODE = 1100


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("controller data ended early")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def string(self):
        return self.take(self.u16()).rstrip(b"\x00").decode("utf-8", "replace")


def parse_controller(data):
    """Name, LED count and zones from a protocol-0 controller data reply."""
    r = _Reader(data)
    r.u32()  # data size
    r.u32()  # device type
    name = r.string()
    for _ in range(4):  # description, version, serial, location
        r.string()
    num_modes = r.u16()
    r.u32()  # active mode
    for _ in range(num_modes):
        r.string()
        r.take(4 * 9)  # value, flags, speed min/max, colors min/max, speed, direction, color mode
        r.take(4 * r.u16())  # mode colors
    zones = []
    for _ in range(r.u16()):
        zone_name = r.string()
        r.take(4 * 3)  # type, leds min, leds max
        count = r.u32()
        r.take(r.u16())  # matrix map
        zones.append((zone_name, count))
    return {"name": name, "leds": r.u16(), "zones": zones}


class OpenRGBClient:
    def __init__(self, host, port, timeout=2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.send(0, SET_CLIENT_NAME, b"AmbiEdge\x00")

    def send(self, device, packet_id, data=b""):
        self.sock.sendall(MAGIC + struct.pack("<III", device, packet_id, len(data)) + data)

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("OpenRGB closed the connection")
            buf += chunk
        return buf

    def request(self, device, packet_id, data=b""):
        self.send(device, packet_id, data)
        while True:  # skip unrelated notifications such as "device list updated"
            header = self._recv(16)
            if header[:4] != MAGIC:
                raise ConnectionError("unexpected reply from the OpenRGB server")
            _, reply_id, size = struct.unpack("<III", header[4:])
            body = self._recv(size)
            if reply_id == packet_id:
                return body

    def controller_count(self):
        return struct.unpack("<I", self.request(0, REQUEST_CONTROLLER_COUNT)[:4])[0]

    def controller(self, index):
        return parse_controller(self.request(index, REQUEST_CONTROLLER_DATA))

    def close(self):
        self.sock.close()


def update_leds_data(colors):
    n = len(colors)
    rgbx = np.zeros((n, 4), np.uint8)
    rgbx[:, :3] = colors
    return struct.pack("<IH", 6 + 4 * n, n) + rgbx.tobytes()


class OpenRGBDriver(Driver):
    key = "openrgb"
    label = "OpenRGB SDK server (motherboard ARGB, many brands)"
    option_keys = ("openrgb_host", "openrgb_port", "openrgb_device")

    def __init__(self, options):
        super().__init__(options)
        self._client = None
        self._index = 0

    @classmethod
    def discover(cls):
        try:
            client = OpenRGBClient("127.0.0.1", 6742, timeout=0.5)
        except OSError:
            return []
        try:
            found = []
            for i in range(client.controller_count()):
                c = client.controller(i)
                found.append(Found(f"OpenRGB device #{i}: {c['name']} ({c['leds']} LEDs)",
                                   {"driver": cls.key, "openrgb_host": "127.0.0.1",
                                    "openrgb_port": 6742, "openrgb_device": i}))
            return found
        finally:
            client.close()

    def open(self):
        host = self.options["openrgb_host"].strip() or "127.0.0.1"
        port = int(self.options["openrgb_port"])
        try:
            self._client = OpenRGBClient(host, port)
        except OSError as e:
            raise DeviceNotFound(f"Can't reach the OpenRGB SDK server at {host}:{port} ({e}). In OpenRGB, "
                                 "open the SDK Server tab and click Start Server.") from e
        self._index = int(self.options["openrgb_device"])
        count = self._client.controller_count()
        if self._index >= count:
            self.close()
            raise DeviceNotFound(f"OpenRGB has {count} device(s), so there is no device #{self._index}.")
        try:
            info = self._client.controller(self._index)
            self.led_count = info["leds"] or None
            self.description = f"OpenRGB: {info['name']}"
        except ValueError:
            self.description = f"OpenRGB device #{self._index}"
        self._client.send(self._index, SET_CUSTOM_MODE)  # direct / software-controlled mode

    def send(self, colors):
        if self.led_count:
            colors = colors[:self.led_count]  # the server ignores updates with too many colors
        self._client.send(self._index, UPDATE_LEDS, update_leds_data(colors))

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None
