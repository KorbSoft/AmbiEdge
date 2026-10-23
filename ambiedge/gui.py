"""The settings window."""

import ctypes
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import __version__, autostart, drivers
from .config import DEFAULTS, RANGES, save_config
from .drivers.adalight import BAUD_RATES, list_ports
from .engine import SyncEngine
from .layout import Layout
from .processing import COLOR_ORDERS

REPO_URL = "https://github.com/KorbSoft/AmbiEdge"

LAYOUT_KEYS = ("left", "top", "right", "bottom", "bottom_gap", "start_corner", "clockwise", "shift")

FIRST_RUN_NOTICE = (
    "AmbiEdge is free for non-commercial use and comes with no warranty. Use it at your own risk.\n\n"
    "- Fast-changing colors can affect people with photosensitive epilepsy. Raise Smoothing or "
    "lower Brightness if that's a concern.\n"
    "- LED strips can draw a lot of current. Keep Max power at its default for USB-powered strips "
    "and only raise it if the strip has a power supply rated for it.\n"
    "- Close your strip's own app first, or the two will fight over the lights."
)


class App:
    def __init__(self, root, cfg, config_path=None):
        self.root = root
        root.title(f"AmbiEdge {__version__}")
        root.resizable(False, False)
        # Sizes below are in pixels at 100% display scaling.
        self.dpi = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.pw, self.ph, self.pp = self.px(400), self.px(210), self.px(26)
        self.cfg = cfg
        self.config_path = config_path
        self._cfg_lock = threading.Lock()
        self._status_queue = queue.Queue()
        self._save_job = None
        self._preview_key = None
        self._preview_items = []
        self.vars = {}
        self._choice_labels = {}
        self.engine = SyncEngine(self.get_config, self._status_queue.put)
        self._build()
        self._poll()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if not cfg["notice_shown"]:
            root.after(200, self._first_run)
        elif cfg["autostart_sync"]:
            root.after(300, self.toggle_sync)

    def px(self, n):
        return int(round(n * self.dpi))

    # ---- config plumbing -------------------------------------------------
    def get_config(self):
        with self._cfg_lock:
            return dict(self.cfg)

    def _set(self, key, value):
        with self._cfg_lock:
            if self.cfg.get(key) == value:
                return
            self.cfg[key] = value
        if key in LAYOUT_KEYS:
            self._update_total()
        if key == "driver":
            self._show_driver_frame()
        self._save_soon()

    def _save_soon(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._save)

    def _save(self):
        self._save_job = None
        try:
            save_config(self.get_config(), self.config_path)
        except OSError as e:
            self.status.set(f"Couldn't save settings: {e}")

    def _bind(self, key, var):
        kind = type(DEFAULTS[key])
        var.set(self.cfg[key])

        def changed(*_):
            try:
                value = kind(var.get())
            except (tk.TclError, ValueError):
                return  # half-typed number
            if key in RANGES:
                lo, hi = RANGES[key]
                value = kind(min(max(value, lo), hi))
            self._set(key, value)

        var.trace_add("write", changed)
        self.vars[key] = var
        return var

    def _bind_choice(self, key, choices):
        """Combobox variable showing labels for (value, label) choices. Returns (var, labels)."""
        labels = dict(choices)
        values = {label: value for value, label in choices}
        var = tk.StringVar(value=labels.get(self.cfg[key], choices[0][1]))
        var.trace_add("write", lambda *_: var.get() in values and self._set(key, values[var.get()]))
        self.vars[key] = var
        self._choice_labels[key] = labels
        return var, [label for _, label in choices]

    def _apply(self, options):
        for key, value in options.items():
            if key in self._choice_labels:
                self.vars[key].set(self._choice_labels[key][value])
            elif key in self.vars:
                self.vars[key].set(value)

    # ---- UI --------------------------------------------------------------
    def _build(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.grid(sticky="nsew")
        self.canvas = tk.Canvas(outer, width=self.pw, height=self.ph, bg="#161616", highlightthickness=0)
        self.canvas.grid(row=0, column=0, pady=(0, 8))

        nb = ttk.Notebook(outer)
        nb.grid(row=1, column=0, sticky="ew")
        for build, title in ((self._device_tab, "Device"), (self._layout_tab, "Layout"),
                             (self._look_tab, "Look"), (self._advanced_tab, "Advanced")):
            tab = ttk.Frame(nb, padding=10)
            build(tab)
            nb.add(tab, text=title)

        btns = ttk.Frame(outer)
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.sync_btn = ttk.Button(btns, text="Start sync", command=self.toggle_sync, width=14)
        self.sync_btn.grid(row=0, column=0, padx=(0, 6))
        self.test_btn = ttk.Button(btns, text="Test layout", command=self.toggle_test, width=14)
        self.test_btn.grid(row=0, column=1)

        hint = ("Pick your controller on the Device tab, check the layout with Test layout, then Start sync."
                if self.cfg["driver"] == "virtual" else "Ready.")
        self.status = tk.StringVar(value=hint)
        ttk.Label(outer, textvariable=self.status, wraplength=self.pw, foreground="#444",
                  justify="left").grid(row=3, column=0, sticky="w", pady=(8, 0))

        foot = ttk.Frame(outer)
        foot.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(foot, text="Free for non-commercial use. No warranty: use at your own risk.",
                  foreground="gray").grid(row=0, column=0, sticky="w")
        link = ttk.Label(foot, text="Help", foreground="#0a64c8", cursor="hand2")
        link.grid(row=0, column=1, sticky="e", padx=(12, 0))
        link.bind("<Button-1>", lambda _: webbrowser.open(REPO_URL))
        foot.columnconfigure(0, weight=1)

    def _note(self, parent, text, row, columnspan=4):
        ttk.Label(parent, text=text, foreground="gray", wraplength=self.pw - self.px(20), justify="left").grid(
            row=row, column=0, columnspan=columnspan, sticky="w", pady=(6, 0))

    def _spin(self, parent, key, row, col, label, width=6, increment=1):
        lo, hi = RANGES[key]
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="e", padx=(0, 4), pady=2)
        ttk.Spinbox(parent, from_=lo, to=hi, increment=increment, width=width,
                    textvariable=self._bind(key, tk.IntVar())).grid(row=row, column=col + 1, sticky="w", padx=(0, 12), pady=2)

    def _entry(self, parent, key, row, label, width=24):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=(0, 4), pady=2)
        ttk.Entry(parent, width=width, textvariable=self._bind(key, tk.StringVar())).grid(
            row=row, column=1, sticky="w", pady=2)

    def _slider(self, parent, key, row, label, lo, hi):
        ttk.Label(parent, text=label, width=13).grid(row=row, column=0, sticky="w")
        var = self._bind(key, tk.DoubleVar())
        ttk.Scale(parent, from_=lo, to=hi, variable=var, length=self.px(250)).grid(row=row, column=1, pady=1)
        val = ttk.Label(parent, width=5)
        val.grid(row=row, column=2, padx=(6, 0))
        var.trace_add("write", lambda *_: val.config(text=f"{var.get():.2f}"))
        val.config(text=f"{var.get():.2f}")

    def _device_tab(self, f):
        ttk.Label(f, text="Controller").grid(row=0, column=0, sticky="w", padx=(0, 6))
        var, labels = self._bind_choice("driver", [(k, d.label) for k, d in drivers.DRIVERS.items()])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=44).grid(row=0, column=1, sticky="w")
        ttk.Button(f, text="Find devices...", command=self.find_devices).grid(row=1, column=1, sticky="w", pady=(6, 0))

        holder = ttk.Frame(f)
        holder.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self._driver_frames = {}
        for key in drivers.DRIVERS:
            frame = ttk.Frame(holder)
            getattr(self, f"_options_{key}")(frame)
            self._driver_frames[key] = frame
        self._show_driver_frame()

        self.device_info = tk.StringVar(value="Not connected.")
        ttk.Label(f, textvariable=self.device_info, wraplength=self.pw - self.px(20), justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _show_driver_frame(self):
        for key, frame in self._driver_frames.items():
            if key == self.cfg["driver"]:
                frame.grid(row=0, column=0, sticky="w")
            else:
                frame.grid_remove()

    def _options_virtual(self, f):
        self._note(f, "No lights: the preview above shows what the LEDs would do. "
                      "Handy for trying the app or planning a layout before buying a strip.", 0)

    def _options_robobloq(self, f):
        self._note(f, "Plug the controller into a USB port. Close Robobloq's SyncLight app first, "
                      "or the two will fight over the lights.", 0)

    def _options_adalight(self, f):
        ttk.Label(f, text="Port").grid(row=0, column=0, sticky="e", padx=(0, 4))
        port = ttk.Combobox(f, width=12, textvariable=self._bind("serial_port", tk.StringVar()))
        port.grid(row=0, column=1, sticky="w")

        def refresh():
            port["values"] = [p.device for p in list_ports()]
        refresh()
        ttk.Button(f, text="Refresh", command=refresh).grid(row=0, column=2, padx=6)
        ttk.Label(f, text="Baud").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=(4, 0))
        ttk.Combobox(f, width=12, values=BAUD_RATES,
                     textvariable=self._bind("serial_baud", tk.IntVar())).grid(row=1, column=1, sticky="w", pady=(4, 0))
        self._note(f, "The baud rate must match the board's firmware. 115200 baud carries about "
                      "120 LEDs at 30 fps; use a higher rate for longer strips.", 2)

    def _options_wled(self, f):
        self._entry(f, "wled_host", 0, "IP / hostname")
        self._spin(f, "wled_port", 1, 0, "UDP port")
        self._note(f, "Use the address shown in the WLED app, for example 192.168.1.50. WLED's own LED "
                      "count, color order and power limit settings still apply.", 2)

    def _options_openrgb(self, f):
        self._entry(f, "openrgb_host", 0, "Host", width=16)
        self._spin(f, "openrgb_port", 1, 0, "Port")
        self._spin(f, "openrgb_device", 2, 0, "Device #", width=4)
        self._note(f, "Start OpenRGB, open its SDK Server tab and click Start Server. "
                      "Find devices lists the device numbers.", 3)

    def _layout_tab(self, f):
        self._spin(f, "left", 0, 0, "Left")
        self._spin(f, "top", 0, 2, "Top")
        self._spin(f, "right", 1, 0, "Right")
        self._spin(f, "bottom", 1, 2, "Bottom")
        self._spin(f, "bottom_gap", 2, 2, "Bottom gap")
        self.total_var = tk.StringVar()
        ttk.Label(f, textvariable=self.total_var).grid(row=2, column=0, columnspan=2, sticky="w")
        self._update_total()

        ttk.Label(f, text="LED 1 is at").grid(row=3, column=0, sticky="e", padx=(0, 4), pady=(8, 2))
        var, labels = self._bind_choice("start_corner", [(c, c.capitalize()) for c in
                                                         ("bottom-left", "top-left", "top-right", "bottom-right")])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=12).grid(row=3, column=1, sticky="w", pady=(8, 2))
        ttk.Label(f, text="Going").grid(row=3, column=2, sticky="e", padx=(0, 4), pady=(8, 2))
        var, labels = self._bind_choice("clockwise", [(True, "Clockwise"), (False, "Counter-clockwise")])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=16).grid(row=3, column=3, sticky="w", pady=(8, 2))
        self._spin(f, "shift", 4, 0, "Shift start by")
        ttk.Label(f, text="Color order").grid(row=4, column=2, sticky="e", padx=(0, 4))
        ttk.Combobox(f, width=6, state="readonly", values=COLOR_ORDERS,
                     textvariable=self._bind("color_order", tk.StringVar())).grid(row=4, column=3, sticky="w")
        self._note(f, "Count the LEDs on each edge as seen from the front of the screen. 'Bottom gap' is "
                      "the number of LEDs that would fit in a gap in the middle of the bottom (for a stand). "
                      "Use 'Shift start by' if LED 1 isn't exactly at a corner. Click Test layout to check: "
                      "if red shows as green, change Color order.", 5)

    def _look_tab(self, f):
        self._slider(f, "brightness", 0, "Brightness", 0.05, 1.0)
        self._slider(f, "saturation", 1, "Color boost", 0.0, 2.5)
        self._slider(f, "smoothing", 2, "Smoothing", 0.0, 0.95)
        self._slider(f, "depth", 3, "Edge depth", 0.03, 0.4)
        self._slider(f, "gamma", 4, "Gamma", 0.5, 3.0)
        ttk.Checkbutton(f, text="Ignore black bars (letterboxed movies)",
                        variable=self._bind("skip_black_bars", tk.BooleanVar())).grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._note(f, "Smoothing: higher fades more slowly and flickers less. Edge depth: how far into the "
                      "screen each LED looks. Gamma above 1 deepens dim colors, which suits many WS2812 strips.", 6, 3)

    def _advanced_tab(self, f):
        self._spin(f, "fps", 0, 0, "FPS", width=4)
        self._spin(f, "monitor", 0, 2, "Monitor #", width=4)
        ttk.Label(f, text="Capture").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=2)
        var, labels = self._bind_choice("capture", [("auto", "Automatic"), ("dxcam", "DXGI (Windows)"), ("mss", "GDI / mss")])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=14).grid(row=1, column=1, sticky="w")
        self._spin(f, "group", 1, 2, "LEDs per zone", width=4)
        self._spin(f, "max_power", 2, 0, "Max power", width=5, increment=5)
        ttk.Label(f, text="per LED (R+G+B, 765 = no limit)", foreground="gray").grid(row=2, column=2, columnspan=2, sticky="w")

        wb = ttk.LabelFrame(f, text="White balance", padding=6)
        wb.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._slider(wb, "white_r", 0, "Red", 0.0, 1.0)
        self._slider(wb, "white_g", 1, "Green", 0.0, 1.0)
        self._slider(wb, "white_b", 2, "Blue", 0.0, 1.0)

        ttk.Checkbutton(f, text="Start syncing when the app opens",
                        variable=self._bind("autostart_sync", tk.BooleanVar())).grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._login_var = tk.BooleanVar(value=autostart.is_enabled())
        ttk.Checkbutton(f, text="Start AmbiEdge when I sign in to Windows (minimized)", variable=self._login_var,
                        command=self._toggle_login, state="normal" if autostart.supported else "disabled").grid(
            row=5, column=0, columnspan=4, sticky="w")
        self._note(f, "Max power 255 keeps a strip powered from USB within safe limits. Raise it only if the "
                      "strip has its own power supply rated for it. If the wrong screen is used, try another "
                      "Monitor #. Use White balance if white looks blue or green.", 6)

    def _toggle_login(self):
        try:
            autostart.set_enabled(self._login_var.get())
        except OSError as e:
            self._login_var.set(autostart.is_enabled())
            messagebox.showerror("AmbiEdge", f"Couldn't change the startup setting: {e}")

    def _update_total(self):
        layout = Layout.from_config(self.cfg)
        self.total_var.set(f"Total LEDs: {layout.total}")

    # ---- preview ---------------------------------------------------------
    def _led_positions(self, layout):
        """Canvas (x, y) of each LED, in loop order."""
        x0, y0, x1, y1 = self.pp, self.pp, self.pw - self.pp, self.ph - self.pp
        w, h, off = x1 - x0, y1 - y0, self.px(11)
        pts = []
        pts += [(x0 - off, y1 - (i + 0.5) * h / layout.left) for i in range(layout.left)]
        pts += [(x0 + (i + 0.5) * w / layout.top, y0 - off) for i in range(layout.top)]
        pts += [(x1 + off, y0 + (i + 0.5) * h / layout.right) for i in range(layout.right)]
        slots = layout.bottom + layout.bottom_gap
        left_part, _ = layout.bottom_split()
        keep = [j for j in range(slots) if j < left_part or j >= left_part + layout.bottom_gap]
        pts += [(x0 + (j + 0.5) * w / slots, y1 + off) for j in reversed(keep)]
        return pts

    def _draw_preview(self, layout, colors):
        c = self.canvas
        if layout.key != self._preview_key:
            self._preview_key = layout.key
            c.delete("all")
            c.create_rectangle(self.pp, self.pp, self.pw - self.pp, self.ph - self.pp,
                               outline="#555", fill="#222")
            c.create_text(self.pw / 2, self.ph / 2, text="screen (front view)", fill="#666")
            pts = self._led_positions(layout)
            longest = max(layout.left, layout.right, 1) / (self.ph - 2 * self.pp)
            longest = max(longest, max(layout.top, layout.bottom + layout.bottom_gap, 1) / (self.pw - 2 * self.pp))
            r = max(1.0, min(self.px(4.5), 0.4 / longest))
            self._preview_items = [c.create_oval(x - r, y - r, x + r, y + r, outline="") for x, y in pts]
            # Label the first and last LED so the strip's direction is visible.
            for led, text in ((0, "1"), (layout.total - 1, str(layout.total)))[:layout.total]:
                x, y = pts[layout.order[led]]
                d = self.px(10)
                if x < self.pp:
                    x -= d
                elif x > self.pw - self.pp:
                    x += d
                elif y < self.pp:
                    y -= d
                else:
                    y += d
                c.create_text(x, y, text=text, fill="#ccc", font=("Segoe UI", 7))
        for item, rgb in zip(self._preview_items, colors):
            r, g, b = (int(v) for v in rgb)
            c.itemconfig(item, fill=f"#{r:02x}{g:02x}{b:02x}")

    # ---- engine ------------------------------------------------------------
    def _poll(self):
        try:
            while True:
                text = self._status_queue.get_nowait()
                if text is not None:
                    self.status.set(text)
                self._refresh_buttons()
        except queue.Empty:
            pass
        preview = self.engine.preview if self.engine.mode else None
        if preview is not None:
            self._draw_preview(*preview)
        else:
            layout = Layout.from_config(self.cfg)
            self._draw_preview(layout, [(70, 70, 70)] * layout.total)
        dev = self.engine.device
        if dev is not None:
            count = f", reports {dev.led_count} LEDs" if dev.led_count else ""
            self.device_info.set(f"Connected: {dev.description}{count}.")
        elif not self.engine.mode:
            self.device_info.set("Not connected.")
        self.root.after(66, self._poll)

    def _refresh_buttons(self):
        mode = self.engine.mode
        self.sync_btn.config(text="Stop sync" if mode == "sync" else "Start sync")
        self.test_btn.config(text="Stop test" if mode == "test" else "Test layout")

    def _toggle(self, mode):
        if self.engine.mode == mode and self.engine.running:
            self.engine.stop()
            self.status.set("Stopped.")
        else:
            self.status.set("Connecting...")
            self.engine.start(mode)
        self._refresh_buttons()

    def toggle_sync(self):
        self._toggle("sync")

    def toggle_test(self):
        self._toggle("test")

    def find_devices(self):
        win = tk.Toplevel(self.root)
        win.title("Find devices")
        win.transient(self.root)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=10)
        frm.grid()
        msg = tk.StringVar(value="Searching...")
        ttk.Label(frm, textvariable=msg, wraplength=self.px(480), justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        lb = tk.Listbox(frm, width=72, height=8)
        lb.grid(row=1, column=0, columnspan=2, pady=8)
        found = []
        results = queue.Queue()

        def use():
            sel = lb.curselection()
            if sel:
                self._apply(found[sel[0]].options)
                win.destroy()

        use_btn = ttk.Button(frm, text="Use selected", command=use, state="disabled")
        use_btn.grid(row=2, column=0, sticky="w")
        ttk.Button(frm, text="Close", command=win.destroy).grid(row=2, column=1, sticky="e")
        lb.bind("<Double-Button-1>", lambda _: use())

        def check():
            try:
                found.extend(results.get_nowait())
            except queue.Empty:
                win.after(100, check)
                return
            for item in found:
                lb.insert("end", item.label)
            if found:
                msg.set("Pick your controller. Serial ports can't be identified automatically, so if "
                        "there are several, try each one (unplugging the controller shows which port disappears). "
                        "WLED devices aren't listed: enter their IP address instead.")
                use_btn.config(state="normal")
                lb.selection_set(0)
            else:
                msg.set("Nothing found. Check the USB cable, try another port, and close the strip's own app. "
                        "For WLED, enter the device's IP address on the Device tab.")

        threading.Thread(target=lambda: results.put(drivers.discover_all()), daemon=True).start()
        check()

    def _first_run(self):
        messagebox.showinfo("Welcome to AmbiEdge", FIRST_RUN_NOTICE, parent=self.root)
        self._set("notice_shown", True)
        if self.cfg["autostart_sync"]:
            self.toggle_sync()

    def on_close(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save()
        self.engine.stop()
        self.root.destroy()


def run(cfg, config_path=None, minimized=False):
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled displays
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root, cfg, config_path)
    if minimized:
        root.iconify()
    root.mainloop()
