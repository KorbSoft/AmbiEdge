"""Start when the user signs in, without admin rights.

Windows: the current user's Run registry key. macOS: a LaunchAgent in ~/Library/LaunchAgents.
"""

import os
import plistlib
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AmbiEdge"
LAUNCH_AGENT_LABEL = "com.korbsoft.ambiedge"

supported = sys.platform in ("win32", "darwin")


def arguments():
    """The program and arguments that start AmbiEdge hidden in the tray / menu bar."""
    if getattr(sys, "frozen", False):  # PyInstaller build (AmbiEdge.exe, or the binary inside AmbiEdge.app)
        args = [sys.executable]
    else:
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AmbiEdge.pyw")
        args = [exe, script] if os.path.exists(script) else [exe, "-m", "ambiedge"]
    return args + ["--minimized"]


def command():
    return subprocess.list2cmdline(arguments())


def launch_agent_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist")


def launch_agent():
    """Contents of the macOS LaunchAgent file."""
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": arguments(),
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",  # only in a graphical login, not over ssh
        "ProcessType": "Interactive",
    }


def is_enabled():
    if sys.platform == "darwin":
        return os.path.exists(launch_agent_path())
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
    if sys.platform == "darwin":
        _set_launch_agent(enabled)
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def _set_launch_agent(enabled):
    # launchd reads the file at the next login, so there's no need to load it now (that would
    # start a second copy of the app straight away).
    path = launch_agent_path()
    if enabled:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            plistlib.dump(launch_agent(), f)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
