"""Command line entry point. With no options it opens the window."""

import argparse
import logging
import logging.handlers
import os
import sys
import threading

from . import __version__
from .config import config_dir, load_config


def _setup_logging(debug):
    os.makedirs(config_dir(), exist_ok=True)
    handlers = [logging.handlers.RotatingFileHandler(os.path.join(config_dir(), "ambiedge.log"),
                                                     maxBytes=1_000_000, backupCount=1, encoding="utf-8")]
    if sys.stderr is not None:  # None under pythonw / the windowed build
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _already_running(gui):
    text = "AmbiEdge is already running. Only one copy can drive the lights at a time."
    if gui:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("AmbiEdge", text)
        root.destroy()
    else:
        print(text, file=sys.stderr)


def _headless(cfg, mode):
    from .engine import SyncEngine
    from .system import SystemMonitor

    stopped = threading.Event()

    def status(text):
        if text is None:
            stopped.set()
        else:
            print(text, flush=True)

    monitor = SystemMonitor().start()  # so the lights still go off with the display
    engine = SyncEngine(lambda: cfg, status, monitor)
    engine.start(mode)
    try:
        while not stopped.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        monitor.stop()


def main(argv=None):
    p = argparse.ArgumentParser(prog="ambiedge", description="Screen-reactive bias lighting for PC LED strips.")
    p.add_argument("--headless", action="store_true", help="sync without a window, using the saved settings (Ctrl+C stops)")
    p.add_argument("--mood", action="store_true", help="with --headless, show the mood light instead")
    p.add_argument("--test-pattern", action="store_true", help="with --headless, show the layout test pattern instead")
    p.add_argument("--list-devices", action="store_true", help="list detected controllers and exit")
    p.add_argument("--config", metavar="PATH", help="settings file to use instead of the default")
    p.add_argument("--minimized", action="store_true", help="start hidden in the tray or menu bar (or minimized)")
    p.add_argument("--debug", action="store_true", help="verbose logging")
    p.add_argument("--version", action="version", version=f"AmbiEdge {__version__}")
    args = p.parse_args(argv)

    _setup_logging(args.debug)
    log = logging.getLogger("ambiedge")
    log.info("AmbiEdge %s starting", __version__)

    if args.list_devices:
        from .drivers import discover_all
        found = discover_all()
        for item in found:
            print(f"{item.label}\n    settings: {item.options}")
        if not found:
            print("No controllers detected. WLED devices aren't auto-detected; set wled_host instead.")
        return

    from .instance import InstanceLock
    lock = InstanceLock(os.path.join(config_dir(), "ambiedge.lock"))
    if not lock.acquire():
        _already_running(gui=not args.headless)
        sys.exit(1)
    try:
        cfg = load_config(args.config)
        if args.headless:
            _headless(cfg, "test" if args.test_pattern else "mood" if args.mood else "sync")
        else:
            from .gui import run
            run(cfg, args.config, args.minimized)
    except Exception:
        log.exception("AmbiEdge crashed")
        raise
    finally:
        lock.release()


if __name__ == "__main__":
    main()
