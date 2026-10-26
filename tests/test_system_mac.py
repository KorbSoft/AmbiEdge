import sys
import threading

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


@pytest.fixture
def mac():
    from ambiedge import system_mac
    return system_mac


def test_dispatcher_uses_the_mac_module(mac):
    from ambiedge import system
    assert system.supported and system.SystemMonitor is mac.SystemMonitor and system.TRAY == "menu bar"


def test_apps_dont_crash(mac):
    app = mac.foreground_app()
    assert app is None or (isinstance(app, str) and app == app.lower())
    apps = mac.windowed_apps()
    assert all(isinstance(name, str) and name == name.lower() for name in apps)
    assert "dock" not in apps and "window server" not in apps


def test_state_can_be_read(mac):
    assert mac._displays_awake() in (True, False, None)
    assert mac._session_locked() in (True, False, None)
    assert isinstance(mac.screen_capture_allowed(), bool)


def test_monitor_without_menu_bar_icon(mac):
    mon = mac.SystemMonitor().start()
    try:
        assert not mon.has_tray
        mon.locked = True
        assert not mon.in_use and mon.reason == "the Mac is locked"
        mon.locked = False
        mon.suspended = True
        assert mon.reason == "the Mac is going to sleep"
        mon.suspended = False
        mon.balloon("AmbiEdge test", "ignore me")  # mustn't raise
    finally:
        mon.stop()
    assert not mon._thread.is_alive()


def test_menu_is_built_from_items_and_reports_clicks(mac):
    from AppKit import NSMenu, NSOnState

    clicks = []
    items = [
        ("Open", 1, False, True),
        None,
        ("Brightness", [("100%", 20, True, True), ("50%", 21, False, False)], False, True),
        ("Quit", 5, False, True),
    ]
    mon = mac.SystemMonitor(on_tray=clicks.append, menu_items=lambda: items)
    mon._helper = mac.AmbiEdgeMonitorHelper.alloc().initWithMonitor_(mon)
    menu = NSMenu.alloc().init()
    mon._helper.menuNeedsUpdate_(menu)
    assert menu.numberOfItems() == 4
    assert menu.itemAtIndex_(1).isSeparatorItem()
    sub = menu.itemAtIndex_(2).submenu()
    assert sub.numberOfItems() == 2
    assert sub.itemAtIndex_(0).state() == NSOnState and not sub.itemAtIndex_(1).isEnabled()
    quit_item = menu.itemAtIndex_(3)
    assert quit_item.target() is mon._helper and quit_item.action() == b"itemClicked:"
    mon._helper.itemClicked_(quit_item)
    assert clicks == [5]
    mon._helper.menuNeedsUpdate_(menu)  # rebuilding replaces the old items
    assert menu.numberOfItems() == 4


def test_monitor_starts_off_the_main_thread_without_icon(mac):
    result = {}

    def run():
        mon = mac.SystemMonitor(menu_items=lambda: []).start()
        result["tray"] = mon.has_tray
        mon.stop()

    t = threading.Thread(target=run)
    t.start()
    t.join(10)
    assert result == {"tray": False}
