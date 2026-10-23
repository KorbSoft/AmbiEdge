"""Start with Windows, via the current user's Run registry key (no admin rights needed)."""

import os
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AmbiEdge"

supported = sys.platform == "win32"


def command():
    if getattr(sys, "frozen", False):  # PyInstaller build
        args = [sys.executable]
    else:
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AmbiEdge.pyw")
        args = [exe, script] if os.path.exists(script) else [exe, "-m", "ambiedge"]
    return subprocess.list2cmdline(args + ["--minimized"])


def is_enabled():
    if not supported:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
