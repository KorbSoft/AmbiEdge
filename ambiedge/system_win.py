"""Windows integration: display, lock and sleep notifications, the tray icon, and the app in front.

Everything here uses plain ctypes so the app needs no extra packages. On platforms without their
own module (Linux), these functions return neutral values and SystemMonitor reports the PC as
always in use. Import ambiedge.system rather than this module; it picks the right one.
"""

import ctypes
import logging
import os
import sys
import threading
import uuid

log = logging.getLogger(__name__)

supported = sys.platform == "win32"

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000
WM_POWERBROADCAST = 0x0218
WM_WTSSESSION_CHANGE = 0x02B1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_APP = 0x8000
TRAY_CALLBACK = WM_APP + 1
TRAY_REFRESH = WM_APP + 2
TRAY_BALLOON = WM_APP + 3

PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_POWERSETTINGCHANGE = 0x8013
WTS_SESSION_LOCK = 7
WTS_SESSION_UNLOCK = 8

GUID_CONSOLE_DISPLAY_STATE = uuid.UUID("6fe69556-704a-47a0-8f24-c28d936fda47").bytes_le

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10

MF_STRING, MF_GRAYED, MF_CHECKED, MF_POPUP, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x10, 0x800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100

if supported:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                    ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                    ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]

    def _sig(fn, restype, *argtypes):
        fn.restype = restype
        fn.argtypes = argtypes

    _sig(user32.DefWindowProcW, LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _sig(user32.RegisterClassW, wintypes.ATOM, ctypes.POINTER(WNDCLASSW))
    _sig(user32.CreateWindowExW, wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
         wintypes.HINSTANCE, wintypes.LPVOID)
    _sig(user32.DestroyWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.GetMessageW, wintypes.BOOL, ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    _sig(user32.TranslateMessage, wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
    _sig(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wintypes.MSG))
    _sig(user32.PostMessageW, wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _sig(user32.SendMessageW, LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _sig(user32.PostQuitMessage, None, ctypes.c_int)
    _sig(user32.RegisterWindowMessageW, wintypes.UINT, wintypes.LPCWSTR)
    _sig(user32.RegisterPowerSettingNotification, wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD)
    _sig(user32.UnregisterPowerSettingNotification, wintypes.BOOL, wintypes.HANDLE)
    _sig(user32.OpenInputDesktop, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _sig(user32.GetUserObjectInformationW, wintypes.BOOL, wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    _sig(user32.CloseDesktop, wintypes.BOOL, wintypes.HANDLE)
    _sig(user32.CreatePopupMenu, wintypes.HMENU)
    _sig(user32.AppendMenuW, wintypes.BOOL, wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
    _sig(user32.SetMenuDefaultItem, wintypes.BOOL, wintypes.HMENU, wintypes.UINT, wintypes.UINT)
    _sig(user32.TrackPopupMenu, wintypes.BOOL, wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
         ctypes.c_int, wintypes.HWND, ctypes.c_void_p)
    _sig(user32.DestroyMenu, wintypes.BOOL, wintypes.HMENU)
    _sig(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
    _sig(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.GetForegroundWindow, wintypes.HWND)
    _sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _sig(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
    _sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
    _sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
    _sig(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
    _sig(user32.CreateIconIndirect, wintypes.HICON, ctypes.POINTER(ICONINFO))
    _sig(user32.DestroyIcon, wintypes.BOOL, wintypes.HICON)
    _sig(user32.GetDC, wintypes.HDC, wintypes.HWND)
    _sig(user32.ReleaseDC, ctypes.c_int, wintypes.HWND, wintypes.HDC)
    _sig(gdi32.CreateDIBSection, wintypes.HBITMAP, wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
         ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
    _sig(gdi32.CreateBitmap, wintypes.HBITMAP, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p)
    _sig(gdi32.DeleteObject, wintypes.BOOL, wintypes.HGDIOBJ)
    _sig(shell32.Shell_NotifyIconW, wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
    _sig(wtsapi32.WTSRegisterSessionNotification, wintypes.BOOL, wintypes.HWND, wintypes.DWORD)
    _sig(wtsapi32.WTSUnRegisterSessionNotification, wintypes.BOOL, wintypes.HWND)
    _sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _sig(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
         ctypes.POINTER(wintypes.DWORD))
    _sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
    _sig(kernel32.GetModuleHandleW, wintypes.HMODULE, wintypes.LPCWSTR)


def _process_name(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return None
    finally:
        kernel32.CloseHandle(handle)


def foreground_app():
    """File name of the program whose window is in front (e.g. 'vlc.exe'), or None."""
    if not supported:
        return None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _process_name(pid.value) if pid.value else None


def windowed_apps():
    """File names of programs that currently have a visible window, excluding this one."""
    if not supported:
        return []
    names = set()
    own = os.getpid()

    @WNDENUMPROC
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value and pid.value != own:
                name = _process_name(pid.value)
                if name:
                    names.add(name)
        return True

    user32.EnumWindows(visit, 0)
    return sorted(names - {"explorer.exe", "applicationframehost.exe", "textinputhost.exe"})


def _session_locked():
    """True if the lock screen (or another secure desktop) is showing."""
    desk = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not desk:
        return True
    try:
        buf = ctypes.create_unicode_buffer(64)
        if user32.GetUserObjectInformationW(desk, 2, buf, ctypes.sizeof(buf), None):  # UOI_NAME
            return buf.value.lower() != "default"
        return False
    finally:
        user32.CloseDesktop(desk)


def _make_hicon(rgba):
    """HICON from an (h, w, 4) uint8 RGBA array."""
    h, w, _ = rgba.shape
    bih = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h,  # top-down
                           biPlanes=1, biBitCount=32, biCompression=0)
    bits = ctypes.c_void_p()
    hdc = user32.GetDC(None)
    color = gdi32.CreateDIBSection(hdc, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
    user32.ReleaseDC(None, hdc)
    bgra = rgba[:, :, [2, 1, 0, 3]].copy()
    ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)
    mask = gdi32.CreateBitmap(w, h, 1, 1, None)
    info = ICONINFO(fIcon=True, hbmMask=mask, hbmColor=color)
    icon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(color)
    gdi32.DeleteObject(mask)
    return icon


class SystemMonitor:
    """A hidden window that tracks whether the PC is in use and, optionally, shows a tray icon.

    display_on / locked / suspended are updated from Windows notifications. Tray clicks and menu
    choices call on_tray(event) from the monitor's own thread, where event is "open" or a menu
    item id; menu_items() is called (also from that thread) to build the right-click menu as a
    list of (label, id_or_submenu_list, checked, enabled) tuples, with None for a separator.
    """

    def __init__(self, on_tray=None, menu_items=None):
        self.display_on = True
        self.locked = False
        self.suspended = False
        self._on_tray = on_tray
        self._menu_items = menu_items
        self._hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._icon = None
        self._tray_added = False
        self._tray_image = None
        self._tray_tip = "AmbiEdge"
        self._balloon = None
        self._lock = threading.Lock()

    @property
    def has_tray(self):
        return self._hwnd is not None

    @property
    def in_use(self):
        return self.display_on and not self.locked and not self.suspended

    @property
    def reason(self):
        """Why the PC isn't in use, or None."""
        if self.suspended:
            return "the PC is going to sleep"
        if not self.display_on:
            return "the display is off"
        if self.locked:
            return "the PC is locked"
        return None

    def start(self):
        if not supported:
            return self
        self._thread = threading.Thread(target=self._run, name="ambiedge-system", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self

    def stop(self):
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(3)

    # ---- tray (safe to call from any thread) ---------------------------------
    def set_tray(self, rgba, tooltip):
        with self._lock:
            self._tray_image, self._tray_tip = rgba, tooltip[:127]
        if self._hwnd:
            user32.PostMessageW(self._hwnd, TRAY_REFRESH, 0, 0)

    def balloon(self, title, text):
        with self._lock:
            self._balloon = (title[:63], text[:255])
        if self._hwnd:
            user32.PostMessageW(self._hwnd, TRAY_BALLOON, 0, 0)

    # ---- window thread -----------------------------------------------------
    def _run(self):
        try:
            self._create_window()
        except Exception:
            log.exception("couldn't create the notification window")
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _create_window(self):
        self._proc = WNDPROC(self._wndproc)  # keep a reference so it isn't garbage collected
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = f"AmbiEdgeMonitor{id(self)}"
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName=cls_name)
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        # A normal (never shown) top-level window, so it also gets broadcast power messages.
        self._hwnd = user32.CreateWindowExW(0, cls_name, "AmbiEdge", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self._hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        guid = (ctypes.c_ubyte * 16).from_buffer_copy(GUID_CONSOLE_DISPLAY_STATE)
        self._power_handle = user32.RegisterPowerSettingNotification(self._hwnd, ctypes.byref(guid), 0)
        wtsapi32.WTSRegisterSessionNotification(self._hwnd, 0)  # NOTIFY_FOR_THIS_SESSION
        self.locked = _session_locked()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            result = self._handle(hwnd, msg, wparam, lparam)
            if result is not None:
                return result
        except Exception:
            log.exception("error handling window message %#x", msg)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle(self, hwnd, msg, wparam, lparam):
        if msg == WM_POWERBROADCAST:
            if wparam == PBT_POWERSETTINGCHANGE and lparam:
                if ctypes.string_at(lparam, 16) == GUID_CONSOLE_DISPLAY_STATE:
                    state = ctypes.c_uint32.from_address(lparam + 20).value  # 0 off, 1 on, 2 dimmed
                    self.display_on = state != 0
                    log.info("display %s", "on" if self.display_on else "off")
            elif wparam == PBT_APMSUSPEND:
                self.suspended = True
                log.info("PC going to sleep")
            elif wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                self.suspended = False
                log.info("PC woke up")
            return 1
        if msg == WM_WTSSESSION_CHANGE:
            if wparam in (WTS_SESSION_LOCK, WTS_SESSION_UNLOCK):
                self.locked = wparam == WTS_SESSION_LOCK
                log.info("session %s", "locked" if self.locked else "unlocked")
            return 0
        if msg == TRAY_REFRESH:
            self._update_tray()
            return 0
        if msg == TRAY_BALLOON:
            self._show_balloon()
            return 0
        if msg == TRAY_CALLBACK:
            event = lparam & 0xFFFF
            if event == WM_LBUTTONUP and self._on_tray:
                self._on_tray("open")
            elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            return 0
        if self._tray_added is not None and msg == getattr(self, "_taskbar_created", None):
            self._tray_added = False  # Explorer restarted; add the icon again
            self._update_tray()
            return 0
        if msg == WM_DESTROY:
            self._remove_tray()
            user32.UnregisterPowerSettingNotification(self._power_handle)
            wtsapi32.WTSUnRegisterSessionNotification(hwnd)
            user32.PostQuitMessage(0)
            return 0
        return None

    def _nid(self, flags=0):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = flags
        return nid

    def _update_tray(self):
        with self._lock:
            image, tip = self._tray_image, self._tray_tip
        if image is None:
            return
        old, self._icon = self._icon, _make_hicon(image)
        nid = self._nid(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        nid.uCallbackMessage = TRAY_CALLBACK
        nid.hIcon = self._icon
        nid.szTip = tip
        if not self._tray_added:
            self._tray_added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        else:
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        if old:
            user32.DestroyIcon(old)

    def _show_balloon(self):
        with self._lock:
            note, self._balloon = self._balloon, None
        if not note or not self._tray_added:
            return
        nid = self._nid(NIF_INFO)
        nid.szInfoTitle, nid.szInfo = note
        nid.dwInfoFlags = 0x1  # NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _remove_tray(self):
        if self._tray_added:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))
            self._tray_added = False
        if self._icon:
            user32.DestroyIcon(self._icon)
            self._icon = None

    def _build_menu(self, items):
        menu = user32.CreatePopupMenu()
        for item in items:
            if item is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                continue
            label, target, checked, enabled = item
            flags = (MF_CHECKED if checked else 0) | (0 if enabled else MF_GRAYED)
            if isinstance(target, list):
                user32.AppendMenuW(menu, MF_POPUP | flags, self._build_menu(target), label)
            else:
                user32.AppendMenuW(menu, MF_STRING | flags, target, label)
        return menu

    def _show_menu(self):
        if not self._menu_items:
            return
        menu = self._build_menu(self._menu_items())
        try:
            user32.SetMenuDefaultItem(menu, 0, True)  # first item in bold
            pos = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pos))
            # Needed so the menu closes when you click elsewhere (a Windows quirk).
            user32.SetForegroundWindow(self._hwnd)
            choice = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                           pos.x, pos.y, 0, self._hwnd, None)
            user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)  # also destroys submenus
        if choice and self._on_tray:
            self._on_tray(int(choice))


def small_icon_size():
    return user32.GetSystemMetrics(49) if supported else 16  # SM_CXSMICON


def bring_to_front():
    pass  # Tk's focus_force is enough on Windows


def screen_capture_allowed():
    """Windows doesn't ask for permission to capture the screen."""
    return True


def request_screen_capture():
    pass
