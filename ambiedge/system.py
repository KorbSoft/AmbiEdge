"""Operating system integration: whether the PC is in use, the tray / menu bar icon, and the app in front.

This picks the implementation for the current platform. Every one offers the same names:

- supported: True if this platform has an implementation.
- SystemMonitor(on_tray=None, menu_items=None): tracks display, lock and sleep state and,
  optionally, shows the tray icon. See system_win.SystemMonitor for the full contract.
- foreground_app(), windowed_apps(): app names used to switch profiles automatically.
- small_icon_size(): pixel size to render the tray icon at.
- bring_to_front(): make the app active, so its window shows in front of other apps.
- set_dock_icon(visible): macOS, show or hide the Dock icon (hidden while only in the menu bar).
- screen_capture_allowed(), request_screen_capture(), open_screen_capture_settings(): the macOS
  Screen Recording permission.
- can_relaunch(), relaunch(): start a fresh copy once this one has quit (macOS only applies a
  newly granted Screen Recording permission to a new process).
- TRAY: what the platform calls the place the icon lives, for messages.
"""

import logging
import sys

log = logging.getLogger(__name__)

__all__ = ["SystemMonitor", "TRAY", "bring_to_front", "can_relaunch", "foreground_app",
           "open_screen_capture_settings", "relaunch", "request_screen_capture",
           "screen_capture_allowed", "set_dock_icon", "small_icon_size", "supported", "windowed_apps"]

TRAY = "tray"

if sys.platform == "darwin":
    try:
        from . import system_mac as _impl
        TRAY = "menu bar"
    except ImportError as e:  # PyObjC not installed: run without the integration
        log.warning("macOS integration unavailable (%s); install pyobjc-framework-Quartz", e)
        from . import system_win as _impl
else:
    from . import system_win as _impl

supported = _impl.supported
SystemMonitor = _impl.SystemMonitor
foreground_app = _impl.foreground_app
windowed_apps = _impl.windowed_apps
small_icon_size = _impl.small_icon_size
bring_to_front = _impl.bring_to_front
set_dock_icon = _impl.set_dock_icon
screen_capture_allowed = _impl.screen_capture_allowed
request_screen_capture = _impl.request_screen_capture
open_screen_capture_settings = _impl.open_screen_capture_settings
can_relaunch = _impl.can_relaunch
relaunch = _impl.relaunch
