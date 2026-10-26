"""macOS integration: display sleep, lock and sleep detection, the menu bar icon, and the app in front.

Uses PyObjC (pyobjc-framework-Quartz, which pulls in the Cocoa bindings). Import ambiedge.system
rather than this module; it picks the right one and falls back if PyObjC is missing.

Display and lock state are polled once a second from a background thread with CoreGraphics
calls that work without a running Cocoa event loop, so they also work with --headless. Going to
sleep is a notification, which needs the event loop that the Tk window runs, so it's only seen
in the windowed app. The menu bar item has to be created and changed on the main thread; Tk's
event loop runs the Cocoa one, so its menu works while the Tk window's mainloop runs.
"""

import logging
import os
import subprocess
import threading

import objc
import Quartz
from AppKit import (NSApplication, NSImage, NSMenu, NSMenuItem, NSOffState, NSOnState, NSStatusBar,
                    NSVariableStatusItemLength, NSWorkspace, NSWorkspaceDidWakeNotification,
                    NSWorkspaceWillSleepNotification)
from Foundation import NSData, NSMakeSize, NSObject

from . import icon as _icon

log = logging.getLogger(__name__)

supported = True

POLL_INTERVAL = 1.0
ICON_POINTS = 18  # menu bar icons are 18 points tall; rendered at 2x for Retina screens

# Windows that belong to the system rather than an app someone would pick for a profile.
_SYSTEM_APPS = {"window server", "dock", "finder", "systemuiserver", "control center", "controlcenter",
                "notification center", "notificationcenter", "spotlight", "screenshot", "wallpaper"}


# ---- apps -------------------------------------------------------------------
def _app_windows():
    """(owner pid, lowercased app name) for normal on-screen windows, frontmost first."""
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    info = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    out = []
    for w in info:
        if w.get(Quartz.kCGWindowLayer, 1) != 0 or w.get(Quartz.kCGWindowAlpha, 1.0) <= 0:
            continue  # menu bar, Dock, overlays and invisible windows
        bounds = w.get(Quartz.kCGWindowBounds) or {}
        if bounds.get("Width", 0) < 50 or bounds.get("Height", 0) < 50:
            continue
        name = w.get(Quartz.kCGWindowOwnerName)
        if name:
            out.append((int(w.get(Quartz.kCGWindowOwnerPID, 0)), str(name).lower()))
    return out


def foreground_app():
    """Lowercased name of the app whose window is in front (e.g. 'iina' or 'vlc'), or None."""
    try:
        for _, name in _app_windows():
            if name not in ("window server", "dock"):
                return name
    except Exception:
        log.debug("couldn't read the window list", exc_info=True)
    return None


def windowed_apps():
    """Names of apps that currently have a visible window, excluding this one."""
    own = os.getpid()
    try:
        names = {name for pid, name in _app_windows() if pid != own}
    except Exception:
        log.debug("couldn't read the window list", exc_info=True)
        return []
    return sorted(names - _SYSTEM_APPS)


def small_icon_size():
    return ICON_POINTS * 2


def bring_to_front():
    """Activate the app, so a window shown from the menu bar comes in front of other apps."""
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass


# ---- Screen Recording permission -------------------------------------------
def screen_capture_allowed():
    """True if macOS lets this app capture other apps' windows (System Settings > Privacy & Security >
    Screen Recording). Without it, captures show only the wallpaper and the menu bar."""
    check = getattr(Quartz, "CGPreflightScreenCaptureAccess", None)
    try:
        return True if check is None else bool(check())
    except Exception:
        return True


def request_screen_capture():
    """Ask for the permission. The first time, macOS shows a prompt; after that it does nothing,
    and the user has to turn it on in System Settings (and restart the app)."""
    request = getattr(Quartz, "CGRequestScreenCaptureAccess", None)
    if request is not None:
        try:
            request()
        except Exception:
            log.debug("CGRequestScreenCaptureAccess failed", exc_info=True)


# ---- state polling ------------------------------------------------------------
def _displays_awake():
    """False if every connected display is asleep, None if that can't be told."""
    err, ids, count = Quartz.CGGetOnlineDisplayList(16, None, None)
    if err or not count:
        return None
    return any(not Quartz.CGDisplayIsAsleep(d) for d in list(ids)[:count])


def _session_locked():
    """True if the screen is locked or another user is at the login window, None if unknown."""
    session = Quartz.CGSessionCopyCurrentDictionary()
    if session is None:
        return None
    if session.get("CGSSessionScreenIsLocked"):
        return True
    return session.get("kCGSSessionOnConsoleKey", True) is False


class AmbiEdgeMonitorHelper(NSObject):
    """Objective-C side of the monitor: menu target, menu delegate and notification observer."""

    def initWithMonitor_(self, monitor):
        self = objc.super(AmbiEdgeMonitorHelper, self).init()
        if self is None:
            return None
        self.monitor = monitor
        return self

    # NSMenuDelegate: rebuild the menu each time it opens, like the Windows tray menu.
    def menuNeedsUpdate_(self, menu):
        self.monitor._fill_menu(menu)

    def itemClicked_(self, sender):
        self.monitor._clicked(int(sender.tag()))

    def refresh_(self, _):
        self.monitor._refresh_item()

    def willSleep_(self, _):
        self.monitor.suspended = True
        log.info("Mac going to sleep")

    def didWake_(self, _):
        self.monitor.suspended = False
        log.info("Mac woke up")


class SystemMonitor:
    """Tracks whether the Mac is in use and, optionally, shows a menu bar icon.

    Same interface as the Windows version: display_on / locked / suspended, in_use and reason;
    on_tray(event) is called with a menu item id when one is chosen (there's no separate click
    action on macOS, where clicking a menu bar icon opens its menu), and menu_items() is called
    to build the menu as (label, id_or_submenu_list, checked, enabled) tuples, None for a separator.
    Create and stop it on the main thread.
    """

    def __init__(self, on_tray=None, menu_items=None):
        self.display_on = True
        self.locked = False
        self.suspended = False
        self._on_tray = on_tray
        self._menu_items = menu_items
        self._helper = None
        self._item = None
        self._menu = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._tray_image = None
        self._tray_tip = "AmbiEdge"

    @property
    def has_tray(self):
        return self._item is not None

    @property
    def in_use(self):
        return self.display_on and not self.locked and not self.suspended

    @property
    def reason(self):
        """Why the Mac isn't in use, or None."""
        if self.suspended:
            return "the Mac is going to sleep"
        if not self.display_on:
            return "the display is off"
        if self.locked:
            return "the Mac is locked"
        return None

    def start(self):
        self._poll()
        self._thread = threading.Thread(target=self._run, name="ambiedge-system", daemon=True)
        self._thread.start()
        try:
            self._helper = AmbiEdgeMonitorHelper.alloc().initWithMonitor_(self)
            center = NSWorkspace.sharedWorkspace().notificationCenter()
            center.addObserver_selector_name_object_(self._helper, "willSleep:", NSWorkspaceWillSleepNotification, None)
            center.addObserver_selector_name_object_(self._helper, "didWake:", NSWorkspaceDidWakeNotification, None)
            if self._menu_items is not None:
                if threading.current_thread() is threading.main_thread():
                    self._create_item()
                else:
                    log.warning("the menu bar icon can only be created on the main thread")
        except Exception:
            log.exception("couldn't set up the menu bar icon")
            self._item = None
        return self

    def stop(self):
        self._stop.set()
        if self._helper is not None:
            try:
                NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self._helper)
            except Exception:
                pass
        if self._item is not None:
            try:
                NSStatusBar.systemStatusBar().removeStatusItem_(self._item)
            except Exception:
                pass
            self._item = None
        if self._thread is not None:
            self._thread.join(3)

    # ---- polling thread -------------------------------------------------------
    def _run(self):
        while not self._stop.wait(POLL_INTERVAL):
            self._poll()

    def _poll(self):
        try:
            awake = _displays_awake()
            if awake is not None and awake != self.display_on:
                self.display_on = awake
                log.info("display %s", "on" if awake else "off")
            locked = _session_locked()
            if locked is not None and locked != self.locked:
                self.locked = locked
                log.info("session %s", "locked" if locked else "unlocked")
        except Exception:
            log.debug("couldn't read the display or session state", exc_info=True)

    # ---- menu bar icon (set_tray and balloon are safe to call from any thread) -------
    def set_tray(self, rgba, tooltip):
        with self._lock:
            self._tray_image, self._tray_tip = rgba, tooltip
        if self._item is not None:
            self._helper.performSelectorOnMainThread_withObject_waitUntilDone_("refresh:", None, False)

    def balloon(self, title, text):
        # A notification without an app bundle or extra packages: AppleScript's display notification.
        # Passing the text as arguments avoids having to quote it for AppleScript.
        script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                  "-e", "end run"]
        try:
            subprocess.Popen(["osascript", *script, title, text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            log.debug("couldn't show a notification", exc_info=True)

    def _create_item(self):
        self._item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self._menu = NSMenu.alloc().init()
        self._menu.setAutoenablesItems_(False)
        self._menu.setDelegate_(self._helper)
        self._item.setMenu_(self._menu)
        self._refresh_item()

    def _refresh_item(self):
        if self._item is None:
            return
        with self._lock:
            rgba, tip = self._tray_image, self._tray_tip
        button = self._item.button()
        if rgba is not None:
            png = _icon.png_bytes(rgba)
            image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(png, len(png)))
            image.setSize_(NSMakeSize(ICON_POINTS, ICON_POINTS))
            button.setImage_(image)
        elif button.image() is None:
            button.setTitle_("AmbiEdge")
        button.setToolTip_(tip)

    def _fill_menu(self, menu, items=None):
        if items is None:
            try:
                items = self._menu_items()
            except Exception:
                log.exception("couldn't build the menu")
                return
        menu.removeAllItems()
        for item in items:
            if item is None:
                menu.addItem_(NSMenuItem.separatorItem())
                continue
            label, target, checked, enabled = item
            if isinstance(target, list):
                entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, None, "")
                sub = NSMenu.alloc().initWithTitle_(label)
                sub.setAutoenablesItems_(False)
                self._fill_menu(sub, target)
                entry.setSubmenu_(sub)
            else:
                entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, "itemClicked:", "")
                entry.setTarget_(self._helper)
                entry.setTag_(target)
            entry.setState_(NSOnState if checked else NSOffState)
            entry.setEnabled_(bool(enabled))
            menu.addItem_(entry)

    def _clicked(self, tag):
        if self._on_tray:
            self._on_tray(tag)
