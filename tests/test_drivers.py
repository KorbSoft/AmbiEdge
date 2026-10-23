import socket
import struct
import threading

import numpy as np

from ambiedge import drivers
from ambiedge.config import DEFAULTS
from ambiedge.drivers import adalight, openrgb, robobloq, wled


def colors(*rows):
    return np.array(rows, np.uint8).reshape(-1, 3)


def test_every_driver_option_has_a_default():
    for key in drivers.DEVICE_KEYS:
        assert key in DEFAULTS


def test_robobloq_ranges_and_packet():
    ranges = robobloq.color_ranges(colors([1, 2, 3], [1, 2, 3], [9, 9, 9]))
    assert ranges == [(1, 2, 1, 2, 3), (3, 3, 9, 9, 9)]
    pkt = robobloq.sc_packet(5, ranges)
    assert pkt[:2] == b"SC" and int.from_bytes(pkt[2:4], "big") == len(pkt)
    assert pkt[4:6] == bytes((5, 0x80)) and pkt[6:11] == bytes((1, 1, 2, 3, 2))
    assert pkt[-1] == sum(pkt[:-1]) % 256
    rb = robobloq.rb_packet(3, 0x82)
    assert rb == bytes((0x52, 0x42, 6, 3, 0x82, (0x52 + 0x42 + 6 + 3 + 0x82) % 256))


def test_adalight_frame():
    data = adalight.frame(colors(*[[1, 2, 3]] * 300))
    hi, lo = 299 >> 8, 299 & 0xFF
    assert data[:6] == b"Ada" + bytes((hi, lo, hi ^ lo ^ 0x55))
    assert len(data) == 6 + 900 and data[6:9] == bytes((1, 2, 3))


def test_wled_packets_split():
    pkts = list(wled.packets(colors(*[[4, 5, 6]] * 500)))
    assert len(pkts) == 2
    assert pkts[0][:4] == bytes((4, 2, 0, 0)) and len(pkts[0]) == 4 + 489 * 3
    assert pkts[1][:4] == bytes((4, 2, 489 >> 8, 489 & 0xFF)) and len(pkts[1]) == 4 + 11 * 3


def _s(text):
    raw = text.encode() + b"\x00"
    return struct.pack("<H", len(raw)) + raw


def controller_data(name="Test Strip", leds=5):
    """A protocol-0 controller description with one mode and one zone."""
    body = struct.pack("<i", 0) + _s(name) + _s("desc") + _s("1.0") + _s("SN") + _s("loc")
    body += struct.pack("<Hi", 1, 0)
    body += _s("Direct") + struct.pack("<iIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 1) + struct.pack("<H", 1) + b"\x00" * 4
    body += struct.pack("<H", 1) + _s("Zone") + struct.pack("<iIII", 1, 0, leds, leds) + struct.pack("<H", 0)
    body += struct.pack("<H", leds) + b"".join(_s(f"LED {i}") + struct.pack("<I", i) for i in range(leds))
    body += struct.pack("<H", leds) + b"\x00" * 4 * leds
    return struct.pack("<I", len(body) + 4) + body


def test_openrgb_parse_controller():
    info = openrgb.parse_controller(controller_data())
    assert info == {"name": "Test Strip", "leds": 5, "zones": [("Zone", 5)]}


def test_openrgb_update_leds_data():
    data = openrgb.update_leds_data(colors([1, 2, 3], [4, 5, 6]))
    assert data == struct.pack("<IH", 14, 2) + bytes((1, 2, 3, 0, 4, 5, 6, 0))


def test_openrgb_driver_against_fake_server():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    received = []

    def serve():
        conn, _ = server.accept()
        with conn:
            def recv(n):
                buf = b""
                while len(buf) < n:
                    chunk = conn.recv(n - len(buf))
                    if not chunk:
                        raise ConnectionError
                    buf += chunk
                return buf
            try:
                while True:
                    header = recv(16)
                    dev, pid, size = struct.unpack("<III", header[4:])
                    data = recv(size)
                    received.append((pid, dev, data))
                    if pid == openrgb.REQUEST_CONTROLLER_COUNT:
                        reply = struct.pack("<I", 1)
                    elif pid == openrgb.REQUEST_CONTROLLER_DATA:
                        reply = controller_data()
                    else:
                        continue
                    # An unrelated notification first, which the client must skip.
                    conn.sendall(b"ORGB" + struct.pack("<III", 0, 100, 0))
                    conn.sendall(b"ORGB" + struct.pack("<III", dev, pid, len(reply)) + reply)
            except ConnectionError:
                pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    d = openrgb.OpenRGBDriver(dict(DEFAULTS, openrgb_port=port))
    d.open()
    assert d.led_count == 5 and "Test Strip" in d.description
    d.send(colors(*[[9, 8, 7]] * 8))  # more than the device has; must be trimmed
    d.close()
    t.join(2)
    server.close()
    ids = [pid for pid, _, _ in received]
    assert ids == [openrgb.SET_CLIENT_NAME, openrgb.REQUEST_CONTROLLER_COUNT, openrgb.REQUEST_CONTROLLER_DATA,
                   openrgb.SET_CUSTOM_MODE, openrgb.UPDATE_LEDS]
    assert received[-1][2] == openrgb.update_leds_data(colors(*[[9, 8, 7]] * 5))


def test_wled_driver_sends_udp():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(2)
    d = wled.WledDriver(dict(DEFAULTS, wled_host="127.0.0.1", wled_port=rx.getsockname()[1]))
    d.open()
    d.send(colors([1, 2, 3]))
    assert rx.recv(2048) == bytes((4, 2, 0, 0, 1, 2, 3))
    d.close()
    rx.close()


def test_missing_settings_raise_device_not_found():
    for cls in (adalight.AdalightDriver, wled.WledDriver):
        try:
            cls(dict(DEFAULTS)).open()
        except drivers.DeviceNotFound:
            pass
        else:
            raise AssertionError(f"{cls.__name__} opened without settings")
