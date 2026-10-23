"""Background thread that captures the screen and drives the lights."""

import datetime
import logging
import threading
import time

import numpy as np

from . import drivers, mood, schedule, system
from .config import LOOK_KEYS
from .layout import Layout, test_pattern
from .processing import ColorProcessor
from .sampler import Capture, sample_edges

log = logging.getLogger(__name__)

# Unchanged colors are still resent this often, so controllers with a timeout (WLED) stay on,
# and stay dark while paused instead of falling back to their own effect.
RESEND_INTERVAL = 1.0
FADE_SECONDS = 1.0
MOOD_FPS = 25
PROFILE_CHECK_INTERVAL = 1.0


class _Reconnect(Exception):
    """The device settings changed; reopen the controller."""


class SyncEngine:
    """Runs one mode at a time: "sync" (screen), "mood" (mood light) or "test" (layout pattern).

    `system_monitor` (a system.SystemMonitor, optional) says whether the PC is in use, so the
    lights can fade out when the display sleeps or the PC locks.
    """

    def __init__(self, get_config, on_status, system_monitor=None):
        self._get_config = get_config
        self._on_status = on_status
        self._system = system_monitor
        self._thread = None
        self._stop = threading.Event()
        self._sent_count = 0
        self._last_status = None
        self.mode = None            # "sync" | "mood" | "test"
        self.preview = None         # (Layout, colors in loop order) for the UI
        self.device = None          # the open driver, for the UI
        self.paused = None          # why the lights are paused, or None
        self.active_profile = None  # profile in use while syncing
        self.profile_app = None     # app that selected it, if it was picked automatically
        self._fg_app, self._fg_checked = None, 0.0

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
        self.paused = None

    def _status(self, text, routine=False):
        (log.debug if routine or text == self._last_status else log.info)(text)
        self._last_status = text
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
                        self._output_loop(driver, mode)
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
            self.paused = None
            self.active_profile = self.profile_app = None
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

    def pause_reason(self, cfg, now=None):
        """Why the lights should be off right now, or None."""
        if cfg["off_when_idle"] and self._system is not None and not self._system.in_use:
            return self._system.reason
        if cfg["schedule_enabled"] and not schedule.is_on(cfg["schedule_on"], cfg["schedule_off"],
                                                          now or datetime.datetime.now()):
            return f"outside the schedule ({cfg['schedule_on']} to {cfg['schedule_off']})"
        return None

    def resolve_profile(self, cfg, now):
        """cfg with the look settings of the profile to use. Sets active_profile / profile_app."""
        name, app = cfg["profile"], None
        if cfg["auto_profile"]:
            if now - self._fg_checked >= PROFILE_CHECK_INTERVAL:
                self._fg_app, self._fg_checked = system.foreground_app(), now
            if self._fg_app:
                for pname, p in cfg["profiles"].items():
                    if self._fg_app in p["apps"]:
                        name, app = pname, self._fg_app
                        break
        self.active_profile, self.profile_app = name, app
        look = cfg["profiles"].get(name)
        return dict(cfg, **{k: look[k] for k in LOOK_KEYS}) if look else cfg

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

    def _output_loop(self, driver, mode):
        opened = self._get_config()
        proc = ColorProcessor()
        capture = None
        frame = None
        out = shown = None
        level = 0.0  # fades 0 -> 1 when starting or resuming, 1 -> 0 when pausing
        last_sent, last_send_time = None, 0.0
        frames, t0 = 0, time.perf_counter()
        prev = next_frame = t0
        announced = False
        try:
            while not self._stop.is_set():
                cfg = self._get_config()
                self._check_device(cfg, opened)
                layout = Layout.from_config(cfg)
                now = time.perf_counter()
                dt, prev = now - prev, now

                reason = self.pause_reason(cfg)
                if reason != self.paused:
                    self.paused = reason
                    if reason:
                        self._status(f"Lights off: {reason}. They'll come back on by themselves.")
                    announced = False
                target = 0.0 if reason else 1.0
                step = dt / FADE_SECONDS
                level = min(target, level + step) if level < target else max(target, level - step)

                if reason and level == 0.0:
                    # Fully off: release the screen and just keep the strip dark.
                    if capture is not None:
                        capture.close()
                        capture = None
                    if layout.total and (last_sent is None or last_sent.any() or now - last_send_time >= RESEND_INTERVAL):
                        last_sent, last_send_time = np.zeros((layout.total, 3), np.uint8), now
                        self._send(driver, last_sent)
                    self.preview = (layout, np.zeros((layout.total, 3), np.uint8))
                    self._stop.wait(0.25)
                    prev = next_frame = time.perf_counter()
                    continue

                if mode == "sync":
                    look = self.resolve_profile(cfg, now)
                    if not reason:  # while fading out, keep showing the last colors
                        capture, grabbed = self._grab(capture, cfg)
                        if capture is None:
                            continue
                        if grabbed is not None:
                            frame = grabbed
                    if frame is not None and layout.total and not reason:
                        edges = sample_edges(frame, layout, look["depth"], look["skip_black_bars"], look["vivid"])
                        out, shown = proc.process(layout.to_chain(Layout.loop_from_edges(*edges)), look)
                    fps = cfg["fps"]
                else:
                    if layout.total:
                        loop = mood.render(cfg["mood_effect"], cfg["mood_color"], now, layout.total)
                        out, shown = proc.process(layout.to_chain(loop), dict(
                            cfg, brightness=cfg["mood_brightness"], saturation=1.0, smoothing=0.0, black_level=0))
                    fps = MOOD_FPS

                if out is not None and len(out) == layout.total:
                    if level < 1.0:
                        out_now = (out * level).astype(np.uint8)
                        shown_now = (shown * level).astype(np.uint8)
                    else:
                        out_now, shown_now = out, shown
                    self.preview = (layout, layout.to_loop(shown_now))
                    if last_sent is None or now - last_send_time >= RESEND_INTERVAL or not np.array_equal(out_now, last_sent):
                        self._send(driver, out_now)
                        last_sent, last_send_time = out_now, now

                frames += 1
                now = time.perf_counter()
                if not reason and (not announced or now - t0 >= 2):
                    rate = f" at {frames / (now - t0):.0f} fps" if announced else ""
                    if mode == "sync":
                        what = f"Syncing monitor {cfg['monitor']} ({capture.backend}){rate}, profile {self.active_profile}"
                        if self.profile_app:
                            what += f" (because {self.profile_app} is in front)"
                    else:
                        what = f"Mood light on: {mood.EFFECT_LABELS.get(cfg['mood_effect'], cfg['mood_effect'])}"
                    self._status(f"{what}. {self._device_note(driver, layout)}.", routine=announced)
                    announced = True
                    frames, t0 = 0, now
                # time.sleep is high-resolution on Windows (Python 3.11+); Event.wait rounds to ~16 ms.
                next_frame = max(next_frame + 1.0 / max(1, fps), now)
                time.sleep(max(0.0, next_frame - time.perf_counter()))
        finally:
            if capture is not None:
                capture.close()

    def _grab(self, capture, cfg):
        """(capture, frame). Opens or reopens the capture as needed; capture is None after a failure."""
        if capture is not None and (capture.monitor, capture.method) != (cfg["monitor"], cfg["capture"]):
            capture.close()
            capture = None
        if capture is None:
            try:
                capture = Capture(cfg["monitor"], cfg["capture"])
            except Exception as e:
                self._status(f"Can't capture monitor {cfg['monitor']} ({e}). Retrying...")
                self._stop.wait(2)
                return None, None
        try:
            return capture, capture.grab()
        except Exception as e:
            # Resolution changes, the lock screen and UAC prompts interrupt DXGI capture.
            log.warning("capture failed: %s", e)
            capture.close()
            self._status("Screen capture was interrupted, retrying...")
            self._stop.wait(1)
            return None, None
