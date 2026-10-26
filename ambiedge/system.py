"""Operating system integration: whether the PC is in use, the tray / menu bar icon, and the app in front.

This picks the implementation for the current platform. Every one offers the same names:

- supported: True if this platform has an implementation.
- SystemMonitor(on_tray=None, menu_items=None): tracks display, lock and sleep state and,
  optionally, shows the tray icon. See system_win.SystemMonitor for the full contract.
- foreground_app(), windowed_apps(): app names used to switch profiles automatically.
- small_icon_size(): pixel size to render the tray icon at.
- bring_to_front(): make the app active, so its window shows in front of other apps.
- screen_capture_allowed(), request_screen_capture(): the macOS Screen Recording permission.
- TRAY: what the platform calls the place the icon lives, for messages.
"""

import logging
import sys

log = logging.getLogger(__name__)

__all__ = ["SystemMonitor", "TRAY", "bring_to_front", "foreground_app", "request_screen_capture",
           "screen_capture_allowed", "small_icon_size", "supported", "windowed_apps"]

TRAY = "tray"

if sys.platform == "darwin":
    try:
        from .system_mac import (SystemMonitor, bring_to_front, foreground_app, request_screen_capture,  # noqa: F401
                                 screen_capture_allowed, small_icon_size, supported, windowed_apps)
        TRAY = "menu bar"
    except ImportError as e:  # PyObjC not installed: run without the integration
        log.warning("macOS integration unavailable (%s); install pyobjc-framework-Quartz", e)
        from .system_win import (SystemMonitor, bring_to_front, foreground_app, request_screen_capture,  # noqa: F401
                                 screen_capture_allowed, small_icon_size, supported, windowed_apps)
else:
    from .system_win import (SystemMonitor, bring_to_front, foreground_app, request_screen_capture,  # noqa: F401
                             screen_capture_allowed, small_icon_size, supported, windowed_apps)
