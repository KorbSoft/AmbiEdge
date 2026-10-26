import ctypes
import struct
import sys

import pytest

from ambiedge import system_win as system

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _display_state(mon, state):
    buf = ctypes.create_string_buffer(system.GUID_CONSOLE_DISPLAY_STATE + struct.pack("<II", 4, state))
    system.user32.SendMessageW(mon._hwnd, system.WM_POWERBROADCAST, system.PBT_POWERSETTINGCHANGE,
                               ctypes.addressof(buf))


def test_monitor_tracks_display_lock_and_sleep():
    mon = system.SystemMonitor().start()
    try:
        assert mon._hwnd
        _display_state(mon, 0)
        assert not mon.display_on and mon.reason == "the display is off"
        _display_state(mon, 2)  # dimmed counts as on
        assert mon.display_on
        system.user32.SendMessageW(mon._hwnd, system.WM_WTSSESSION_CHANGE, system.WTS_SESSION_LOCK, 0)
        assert mon.locked and not mon.in_use
        system.user32.SendMessageW(mon._hwnd, system.WM_WTSSESSION_CHANGE, system.WTS_SESSION_UNLOCK, 0)
        system.user32.SendMessageW(mon._hwnd, system.WM_POWERBROADCAST, system.PBT_APMSUSPEND, 0)
        assert mon.suspended
        system.user32.SendMessageW(mon._hwnd, system.WM_POWERBROADCAST, system.PBT_APMRESUMEAUTOMATIC, 0)
        assert mon.in_use and mon.reason is None
    finally:
        mon.stop()
    assert not mon._thread.is_alive()


def test_foreground_and_windowed_apps_dont_crash():
    app = system.foreground_app()
    assert app is None or app.endswith(".exe")
    assert all(name.endswith(".exe") for name in system.windowed_apps())
