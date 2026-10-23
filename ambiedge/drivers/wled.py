"""WLED (ESP8266 / ESP32) over the network, using its UDP realtime protocol.

Sends DNRGB packets to port 21324: 0x04, timeout seconds, start index (uint16 BE), then RGB
for up to 489 LEDs. WLED returns to its normal effect `timeout` seconds after packets stop.
"""

import json
import socket
import urllib.request

from .base import DeviceNotFound, Driver

DNRGB = 4
MAX_PER_PACKET = 489
TIMEOUT_SECONDS = 2


def packets(colors, timeout=TIMEOUT_SECONDS):
    for start in range(0, len(colors), MAX_PER_PACKET):
        chunk = colors[start:start + MAX_PER_PACKET]
        yield bytes((DNRGB, timeout, start >> 8, start & 0xFF)) + chunk.tobytes()


def fetch_info(host, timeout=1.5):
    with urllib.request.urlopen(f"http://{host}/json/info", timeout=timeout) as r:
        return json.load(r)


class WledDriver(Driver):
    key = "wled"
    label = "WLED (Wi-Fi / Ethernet)"
    option_keys = ("wled_host", "wled_port")

    def __init__(self, options):
        super().__init__(options)
        self._sock = None
        self._addr = None

    def open(self):
        host = self.options["wled_host"].strip()
        if not host:
            raise DeviceNotFound("Enter the WLED device's IP address or hostname on the Device tab.")
        port = int(self.options["wled_port"])
        try:
            family, _, _, _, addr = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)[0]
        except OSError as e:
            raise DeviceNotFound(f"Can't find '{host}' on the network ({e}).") from e
        try:
            info = fetch_info(host)
            self.led_count = int(info["leds"]["count"]) or None
            self.description = f"WLED '{info.get('name', host)}' at {host}, version {info.get('ver', '?')}"
        except Exception:
            # UDP works without the web API, so keep going, but say we couldn't confirm it.
            self.description = f"WLED at {host} (no answer from its web API; check the address)"
        self._sock = socket.socket(family, socket.SOCK_DGRAM)
        self._addr = addr

    def send(self, colors):
        for pkt in packets(colors[:self.max_leds]):
            self._sock.sendto(pkt, self._addr)

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None
