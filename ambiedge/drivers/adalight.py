"""Adalight protocol over a serial (COM) port.

Used by Arduino / ESP boards running Adalight-compatible firmware (Adalight, FastLED
Adalight sketches, Prismatik's Adalight mode, many DIY and some ready-made kits).

Frame: "Ada", count-1 high byte, count-1 low byte, checksum (hi ^ lo ^ 0x55), then RGB bytes.
"""

import time

from .base import DeviceNotFound, Driver, Found

# Most Arduino boards reset when the port opens and need a moment before they listen.
RESET_DELAY = 2.0
BAUD_RATES = (115200, 230400, 460800, 500000, 921600, 1000000, 2000000)


def frame(colors):
    count = len(colors) - 1
    hi, lo = (count >> 8) & 0xFF, count & 0xFF
    return b"Ada" + bytes((hi, lo, hi ^ lo ^ 0x55)) + colors.tobytes()


def list_ports():
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return sorted(list_ports.comports(), key=lambda p: p.device)


class AdalightDriver(Driver):
    key = "adalight"
    label = "Adalight (Arduino / ESP over USB serial)"
    option_keys = ("serial_port", "serial_baud")

    def __init__(self, options):
        super().__init__(options)
        self._ser = None

    @classmethod
    def discover(cls):
        # Serial ports can't say what's listening, so list them all for the user to pick.
        return [Found(f"Serial port {p.device}: {p.description} (try Adalight)",
                      {"driver": cls.key, "serial_port": p.device})
                for p in list_ports()]

    def open(self):
        try:
            import serial
        except ImportError as e:
            raise DeviceNotFound(f"The pyserial package isn't installed ({e}).") from e
        port = self.options["serial_port"].strip()
        if not port:
            raise DeviceNotFound("Pick the controller's serial port on the Device tab.")
        baud = int(self.options["serial_baud"])
        try:
            self._ser = serial.Serial(port, baud, timeout=0, write_timeout=0.5)
        except (serial.SerialException, ValueError) as e:
            raise DeviceNotFound(f"Can't open {port} ({e}). Is another app using it?") from e
        time.sleep(RESET_DELAY)
        self.description = f"Adalight on {port} at {baud} baud"

    def send(self, colors):
        if not len(colors):
            return
        data = frame(colors[:self.max_leds])
        try:
            # If the link is slower than the frame rate, drop frames instead of queueing them.
            if self._ser.out_waiting > len(data):
                return
        except (AttributeError, OSError):
            pass
        self._ser.write(data)  # SerialException is an OSError, so the engine reconnects

    def close(self):
        if self._ser is not None:
            try:
                self._ser.flush()
                self._ser.close()
            except Exception:
                pass
            self._ser = None
