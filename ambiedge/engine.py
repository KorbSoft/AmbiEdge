"""Background thread that captures the screen and drives the lights."""

import logging
import threading
import time

import numpy as np

from . import drivers
from .layout import Layout, test_pattern
from .processing import ColorProcessor
from .sampler import Capture, sample_edges

log = logging.getLogger(__name__)

# Unchanged colors are still resent this often, so controllers with a timeout (WLED) stay on.
RESEND_INTERVAL = 1.0


class _Reconnect(Exception):
    """The device settings changed; reopen the controller."""


class SyncEngine:
    def __init__(self, get_config, on_status):
        self._get_config = get_config
        self._on_status = on_status
        self._thread = None
        self._stop = threading.Event()
        self._sent_count = 0
        self.mode = None      # "sync" | "test"
        self.preview = None   # (Layout, colors in loop order) for the UI
        self.device = None    # the open driver, for the UI

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, mode):
        self.stop()
        self.mode = mode
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(mode,), daemon=True)
        self._thread.start()

    def stop(self):
        if self.running:
            self._stop.set()
            self._thread.join(timeout=5)
        self._thread = None
        self.mode = None

    def _status(self, text, routine=False):
        (log.debug if routine else log.info)(text)
        self._on_status(text)

    def _run(self, mode):
        try:
            while not self._stop.is_set():
                cfg = self._get_config()
                driver = drivers.create(cfg)
                try:
                    driver.open()
                    self.device = driver
                    if mode == "test":
                        self._test_loop(driver)
                    else:
                        self._sync_loop(driver)
                except _Reconnect:
                    self._status("Device settings changed, reconnecting...")
                except drivers.DeviceNotFound as e:
                    self._status(f"{e} Retrying...")
                    self._stop.wait(3)
                except OSError as e:
                    self._status(f"Lost the connection to the lights ({e}). Reconnecting...")
                    self._stop.wait(2)
                finally:
                    self.device = None
                    self._shutdown(driver)
        except Exception as e:
            log.exception("sync engine crashed")
            self._status(f"Stopped: {e}")
        finally:
            self.preview = None
            if not self._stop.is_set():
                self.mode = None
                self._on_status(None)

    def _shutdown(self, driver):
        try:
            driver.off(self._sent_count)
        except Exception:
            pass
        try:
            driver.close()
        except Exception:
            pass

    def _check_device(self, cfg, opened):
        if any(cfg[k] != opened[k] for k in drivers.DEVICE_KEYS):
            raise _Reconnect()

    def _device_note(self, driver, layout):
        text = driver.description
        if driver.led_count and driver.led_count != layout.total:
            text += f". Note: it reports {driver.led_count} LEDs but the layout has {layout.total}"
        if layout.total > driver.max_leds:
            text += f". Only the first {driver.max_leds} LEDs can be driven"
        return text

    def _send(self, driver, colors):
        driver.send(colors)
        self._sent_count = max(self._sent_count, len(colors))

    def _test_loop(self, driver):
        opened = self._get_config()
        proc = ColorProcessor()
        blink = True
        layout_key = None
        while not self._stop.is_set():
            cfg = self._get_config()
            self._check_device(cfg, opened)
            layout = Layout.from_config(cfg)
            if layout.key != layout_key:
                layout_key = layout.key
                self._status(f"Test pattern on: {self._device_note(driver, layout)}. Left should be red, "
                             "top green, right blue, bottom yellow, with a white LED where each edge "
                             "starts (going clockwise). The blinking LED is LED 1.")
            out, shown = proc.process(layout.to_chain(test_pattern(layout, blink)),
                                      dict(cfg, smoothing=0.0, saturation=1.0))
            self.preview = (layout, layout.to_loop(shown))
            self._send(driver, out)
            blink = not blink
            self._stop.wait(0.4)

    def _sync_loop(self, driver):
        opened = self._get_config()
        proc = ColorProcessor()
        capture = None
        frame = None
        last_sent, last_send_time = None, 0.0
        frames, t0 = 0, time.perf_counter()
        next_frame = t0
        announced = False
        try:
            while not self._stop.is_set():
                cfg = self._get_config()
                self._check_device(cfg, opened)
                if capture is None or (capture.monitor, capture.method) != (cfg["monitor"], cfg["capture"]):
                    if capture is not None:
                        capture.close()
                        capture = None
                    try:
                        capture = Capture(cfg["monitor"], cfg["capture"])
                    except Exception as e:
                        self._status(f"Can't capture monitor {cfg['monitor']} ({e}). Retrying...")
                        self._stop.wait(2)
                        continue
                    announced = False
                try:
                    grabbed = capture.grab()
                except Exception as e:
                    # Resolution changes, the lock screen and UAC prompts interrupt DXGI capture.
                    log.warning("capture failed: %s", e)
                    capture.close()
                    capture = None
                    self._status("Screen capture was interrupted, retrying...")
                    self._stop.wait(1)
                    continue
                if grabbed is not None:
                    frame = grabbed

                layout = Layout.from_config(cfg)
                if frame is not None and layout.total:
                    edges = sample_edges(frame, layout, cfg["depth"], cfg["skip_black_bars"])
                    out, shown = proc.process(layout.to_chain(Layout.loop_from_edges(*edges)), cfg)
                    self.preview = (layout, layout.to_loop(shown))
                    now = time.perf_counter()
                    if last_sent is None or now - last_send_time >= RESEND_INTERVAL or not np.array_equal(out, last_sent):
                        self._send(driver, out)
                        last_sent, last_send_time = out, now

                frames += 1
                now = time.perf_counter()
                if not announced or now - t0 >= 2:
                    rate = f" at {frames / (now - t0):.0f} fps" if announced else ""
                    self._status(f"Syncing monitor {cfg['monitor']} ({capture.backend}){rate}. "
                                 f"{self._device_note(driver, layout)}.", routine=announced)
                    announced = True
                    frames, t0 = 0, now
                # time.sleep is high-resolution on Windows (Python 3.11+); Event.wait rounds to ~16 ms.
                next_frame = max(next_frame + 1.0 / max(1, cfg["fps"]), now)
                time.sleep(max(0.0, next_frame - time.perf_counter()))
        finally:
            if capture is not None:
                capture.close()
