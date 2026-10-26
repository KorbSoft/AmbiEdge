"""The settings window and tray / menu bar icon."""

import base64
import ctypes
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import colorchooser, messagebox, simpledialog, ttk

from . import __version__, autostart, drivers, icon, mood, schedule, system
from .config import DEFAULTS, LOOK_KEYS, MAX_PROFILE_NAME, RANGES, copy_config, save_config
from .drivers.adalight import BAUD_RATES, list_ports
from .engine import SyncEngine
from .layout import EDGES, Layout, fit_counts
from .processing import COLOR_ORDERS

REPO_URL = "https://github.com/KorbSoft/AmbiEdge"

MAC = sys.platform == "darwin"
LOGIN_LABEL = "Start AmbiEdge when I log in to this Mac" if MAC else "Start AmbiEdge when I sign in to Windows"
STARTED_AT_LOGIN = "When started at login" if MAC else "When started with Windows"
APP_EXAMPLE = "iina or vlc" if MAC else "vlc.exe"
MULTI_SELECT_KEY = "Cmd" if MAC else "Ctrl"

LAYOUT_KEYS = ("left", "top", "right", "bottom", "bottom_gap", "start_corner", "clockwise", "shift")

MOOD_PRESETS = ("#ffb070", "#ff8c3c", "#ff2a1a", "#ff3c9a", "#8a3cff", "#2a5cff", "#18c8d8", "#2ad860")

# Tray menu item ids.
MENU_OPEN, MENU_SYNC, MENU_MOOD, MENU_OFF, MENU_QUIT, MENU_AUTO = 1, 2, 3, 4, 5, 6
MENU_BRIGHTNESS = 20  # + index into BRIGHTNESS_STEPS
MENU_PROFILE = 100    # + index into the profile list
BRIGHTNESS_STEPS = (1.0, 0.75, 0.5, 0.25, 0.1)

FIRST_RUN_NOTICE = (
    "AmbiEdge is free, open-source software (GPL-3.0) and comes with no warranty. Use it at your own risk.\n\n"
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
        self.pw, self.ph, self.pp = self.px(400), self.px(200), self.px(26)
        self.cfg = cfg
        self.config_path = config_path
        self._cfg_lock = threading.Lock()
        self._status_queue = queue.Queue()
        self._tray_events = queue.Queue()
        self._save_job = None
        self._preview_key = None
        self._preview_items = []
        self._tray_key = None
        self._closed = False
        self.vars = {}
        self._choice_labels = {}
        self._window_icon = tk.PhotoImage(data=base64.b64encode(icon.png_bytes(icon.render(64))))
        root.iconphoto(True, self._window_icon)

        self.monitor = None
        if system.supported:
            self.monitor = system.SystemMonitor(on_tray=self._tray_events.put, menu_items=self.tray_menu).start()
        self.tray = self.monitor is not None and self.monitor.has_tray
        self.engine = SyncEngine(self.get_config, self._status_queue.put, self.monitor)
        self._build()
        self._poll()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if MAC:
            # Clicking the Dock icon while the window is hidden brings it back, and Cmd+Q (or
            # Quit in the Dock menu) quits properly, turning the lights off first.
            root.createcommand("::tk::mac::ReopenApplication", self.show_window)
            root.createcommand("::tk::mac::Quit", self.quit)
        if not cfg["notice_shown"]:
            root.after(200, self._first_run)
        else:
            root.after(300, self._start_mode)

    def px(self, n):
        return int(round(n * self.dpi))

    # ---- config plumbing -------------------------------------------------
    def get_config(self):
        with self._cfg_lock:
            return copy_config(self.cfg)

    def _set(self, key, value):
        with self._cfg_lock:
            if self.cfg.get(key) == value:
                return
            self.cfg[key] = value
            if key in LOOK_KEYS:  # the look settings belong to the profile being edited
                self.cfg["profiles"][self.cfg["profile"]][key] = value
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
                             (self._look_tab, "Look"), (self._profiles_tab, "Profiles"),
                             (self._mood_tab, "Mood"), (self._schedule_tab, "Schedule"),
                             (self._advanced_tab, "Advanced")):
            tab = ttk.Frame(nb, padding=10)
            build(tab)
            nb.add(tab, text=title)

        btns = ttk.Frame(outer)
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.sync_btn = ttk.Button(btns, text="Start sync", command=self.toggle_sync, width=13)
        self.sync_btn.grid(row=0, column=0, padx=(0, 6))
        self.mood_btn = ttk.Button(btns, text="Mood light", command=self.toggle_mood, width=13)
        self.mood_btn.grid(row=0, column=1, padx=(0, 6))
        self.test_btn = ttk.Button(btns, text="Test layout", command=self.toggle_test, width=13)
        self.test_btn.grid(row=0, column=2)

        hint = ("Pick your controller on the Device tab, check the layout with Test layout, then Start sync."
                if self.cfg["driver"] == "virtual" else "Ready.")
        self.status = tk.StringVar(value=hint)
        ttk.Label(outer, textvariable=self.status, wraplength=self.pw, foreground="#444",
                  justify="left").grid(row=3, column=0, sticky="w", pady=(8, 0))

        foot = ttk.Frame(outer)
        foot.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(foot, text="Free and open source (GPL-3.0). No warranty: use at your own risk.",
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

    def _check(self, parent, key, row, text, columnspan=4, **grid):
        ttk.Checkbutton(parent, text=text, variable=self._bind(key, tk.BooleanVar())).grid(
            row=row, column=0, columnspan=columnspan, sticky="w", **grid)

    # Device ---------------------------------------------------------------
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
        # macOS port names are long, like /dev/cu.usbserial-1420.
        port = ttk.Combobox(f, width=26 if MAC else 12, textvariable=self._bind("serial_port", tk.StringVar()))
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

    # Layout ---------------------------------------------------------------
    def _layout_tab(self, f):
        self._spin(f, "left", 0, 0, "Left")
        self._spin(f, "top", 0, 2, "Top")
        self._spin(f, "right", 1, 0, "Right")
        self._spin(f, "bottom", 1, 2, "Bottom")
        self._spin(f, "bottom_gap", 2, 2, "Bottom gap")
        self.total_var = tk.StringVar()
        ttk.Label(f, textvariable=self.total_var).grid(row=2, column=0, columnspan=2, sticky="w")
        self._update_total()
        ttk.Button(f, text="Fit to LED count...", command=self.fit_layout).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        ttk.Label(f, text="LED 1 is at").grid(row=4, column=0, sticky="e", padx=(0, 4), pady=(8, 2))
        var, labels = self._bind_choice("start_corner", [(c, c.capitalize()) for c in
                                                         ("bottom-left", "top-left", "top-right", "bottom-right")])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=12).grid(row=4, column=1, sticky="w", pady=(8, 2))
        ttk.Label(f, text="Going").grid(row=4, column=2, sticky="e", padx=(0, 4), pady=(8, 2))
        var, labels = self._bind_choice("clockwise", [(True, "Clockwise"), (False, "Counter-clockwise")])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=16).grid(row=4, column=3, sticky="w", pady=(8, 2))
        self._spin(f, "shift", 5, 0, "Shift start by")
        ttk.Label(f, text="Color order").grid(row=5, column=2, sticky="e", padx=(0, 4))
        ttk.Combobox(f, width=6, state="readonly", values=COLOR_ORDERS,
                     textvariable=self._bind("color_order", tk.StringVar())).grid(row=5, column=3, sticky="w")
        self._note(f, "Count the LEDs on each edge as seen from the front of the screen, or use Fit to LED "
                      "count. 'Bottom gap' is how many LEDs would fit in a gap in the middle of the bottom "
                      "(for a stand). Click Test layout to check: if red shows as green, change Color order.", 6)

    def fit_layout(self):
        dev = self.engine.device
        count = (dev.led_count if dev is not None else None) or self.cfg["reported_leds"] or Layout.from_config(self.cfg).total
        count = simpledialog.askinteger(
            "Fit layout", "How many LEDs does the strip have?\n\nThey'll be split over the edges you use "
            "(left, top and right if none are set yet) to match the screen's shape. Check the result with "
            "Test layout and fine-tune if needed.", initialvalue=count, minvalue=1, maxvalue=2000, parent=self.root)
        if not count:
            return
        edges = [e for e in EDGES if self.cfg[e]]
        width, height = self._monitor_size()
        self._apply(fit_counts(count, width, height, edges))

    def _monitor_size(self):
        try:
            import mss
            with (mss.MSS() if hasattr(mss, "MSS") else mss.mss()) as m:
                mon = m.monitors[min(self.cfg["monitor"] + 1, len(m.monitors) - 1)]
                return mon["width"], mon["height"]
        except Exception:
            return 16, 9

    def _update_total(self):
        layout = Layout.from_config(self.cfg)
        self.total_var.set(f"Total LEDs: {layout.total}")

    # Look and profiles ------------------------------------------------------
    def _profile_picker(self, f, row):
        ttk.Label(f, text="Profile").grid(row=row, column=0, sticky="w")
        box = ttk.Combobox(f, textvariable=self.profile_var, state="readonly", width=18,
                           values=list(self.cfg["profiles"]))
        box.grid(row=row, column=1, sticky="w", pady=(0, 6))
        box.bind("<<ComboboxSelected>>", lambda _: self.select_profile(self.profile_var.get()))
        self._profile_boxes.append(box)

    def _look_tab(self, f):
        self.profile_var = tk.StringVar(value=self.cfg["profile"])
        self._profile_boxes = []
        self._profile_picker(f, 0)
        self._slider(f, "brightness", 1, "Brightness", 0.05, 1.0)
        self._slider(f, "saturation", 2, "Color boost", 0.0, 2.5)
        self._slider(f, "vivid", 3, "Vivid colors", 0.0, 1.0)
        self._slider(f, "smoothing", 4, "Smoothing", 0.0, 0.95)
        self._slider(f, "depth", 5, "Edge depth", 0.03, 0.4)
        self._slider(f, "gamma", 6, "Gamma", 0.5, 3.0)
        self._check(f, "skip_black_bars", 7, "Ignore black bars (letterboxed movies)", 3, pady=(6, 0))
        self._note(f, "Vivid colors favors bright, saturated parts of the screen over gray ones. Smoothing: "
                      "higher fades more slowly and flickers less. Edge depth: how far into the screen each "
                      "LED looks. These settings are saved in the selected profile.", 8, 3)

    def _profiles_tab(self, f):
        self._profile_picker(f, 0)
        btns = ttk.Frame(f)
        btns.grid(row=0, column=2, sticky="w", padx=(6, 0), pady=(0, 6))
        ttk.Button(btns, text="New...", command=self.new_profile, width=8).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(btns, text="Delete", command=self.delete_profile, width=8).grid(row=0, column=1)

        ttk.Label(f, text="Use this profile while these apps are in front:").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 2))
        self.apps_var = tk.StringVar(value=", ".join(self.cfg["profiles"][self.cfg["profile"]]["apps"]))
        self.apps_var.trace_add("write", lambda *_: self._set_apps(self.apps_var.get()))
        ttk.Entry(f, textvariable=self.apps_var, width=44).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Choose...", command=self.choose_apps).grid(row=2, column=2, sticky="w", padx=(6, 0))
        self._check(f, "auto_profile", 3, "Switch profiles automatically by the app in front", 3, pady=(8, 0))
        self.profile_info = tk.StringVar()
        ttk.Label(f, textvariable=self.profile_info).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._note(f, "Each profile has its own Look settings (pick a profile on the Look tab to edit it). "
                      f"Apps are program names such as {APP_EXAMPLE}, separated by commas; Choose lists the "
                      "programs that have a window open. When no listed app is in front, the selected "
                      "profile is used.", 5, 3)

    def select_profile(self, name):
        with self._cfg_lock:
            if name not in self.cfg["profiles"]:
                return
            self.cfg["profile"] = name
            look = dict(self.cfg["profiles"][name])
        self.profile_var.set(name)
        for key in LOOK_KEYS:
            self.vars[key].set(look[key])
        self.apps_var.set(", ".join(look["apps"]))
        self._save_soon()

    def _refresh_profile_boxes(self):
        for box in self._profile_boxes:
            box["values"] = list(self.cfg["profiles"])

    def _set_apps(self, text):
        apps = sorted({a.strip().lower() for a in text.replace(";", ",").split(",") if a.strip()})
        with self._cfg_lock:
            profile = self.cfg["profiles"][self.cfg["profile"]]
            if profile["apps"] == apps:
                return
            profile["apps"] = apps
        self._save_soon()

    def new_profile(self):
        name = simpledialog.askstring("New profile", "Name for the new profile (it starts as a copy "
                                      "of the current one):", parent=self.root)
        name = (name or "").strip()[:MAX_PROFILE_NAME]
        if not name:
            return
        with self._cfg_lock:
            if name in self.cfg["profiles"]:
                exists = True
            else:
                exists = False
                self.cfg["profiles"][name] = dict({k: self.cfg[k] for k in LOOK_KEYS}, apps=[])
        if exists:
            messagebox.showinfo("AmbiEdge", f"There's already a profile called {name}.", parent=self.root)
            return
        self._refresh_profile_boxes()
        self.select_profile(name)

    def delete_profile(self):
        name = self.cfg["profile"]
        if len(self.cfg["profiles"]) <= 1:
            messagebox.showinfo("AmbiEdge", "You need at least one profile.", parent=self.root)
            return
        if not messagebox.askyesno("AmbiEdge", f"Delete the profile {name}?", parent=self.root):
            return
        with self._cfg_lock:
            del self.cfg["profiles"][name]
            first = next(iter(self.cfg["profiles"]))
        self._refresh_profile_boxes()
        self.select_profile(first)

    def choose_apps(self):
        win = tk.Toplevel(self.root)
        win.title("Choose apps")
        win.transient(self.root)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=10)
        frm.grid()
        ttk.Label(frm, text=f"Programs with a window open. Select the ones that should use "
                            f"the {self.cfg['profile']} profile ({MULTI_SELECT_KEY}+click to pick several).",
                  wraplength=self.px(360), justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        lb = tk.Listbox(frm, width=40, height=12, selectmode="extended")
        lb.grid(row=1, column=0, columnspan=2, pady=8)
        apps = system.windowed_apps()
        for name in apps:
            lb.insert("end", name)

        def add():
            picked = [apps[i] for i in lb.curselection()]
            current = [a.strip() for a in self.apps_var.get().split(",") if a.strip()]
            self.apps_var.set(", ".join(sorted(set(current) | set(picked))))
            win.destroy()

        ttk.Button(frm, text="Add selected", command=add).grid(row=2, column=0, sticky="w")
        ttk.Button(frm, text="Cancel", command=win.destroy).grid(row=2, column=1, sticky="e")

    # Mood -------------------------------------------------------------------
    def _mood_tab(self, f):
        ttk.Label(f, text="Color").grid(row=0, column=0, sticky="w")
        self.mood_swatch = tk.Label(f, width=6, relief="groove", bg=self.cfg["mood_color"], cursor="hand2")
        self.mood_swatch.grid(row=0, column=1, sticky="w", padx=(6, 6))
        self.mood_swatch.bind("<Button-1>", lambda _: self.pick_mood_color())
        ttk.Button(f, text="Choose...", command=self.pick_mood_color).grid(row=0, column=2, sticky="w")
        presets = ttk.Frame(f)
        presets.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 4))
        for i, color in enumerate(MOOD_PRESETS):
            chip = tk.Label(presets, width=3, bg=color, relief="groove", cursor="hand2")
            chip.grid(row=0, column=i, padx=(0, 4))
            chip.bind("<Button-1>", lambda _, c=color: self._set_mood_color(c))
        ttk.Label(f, text="Effect").grid(row=2, column=0, sticky="w", pady=(8, 0))
        var, labels = self._bind_choice("mood_effect", list(mood.EFFECT_LABELS.items()))
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=22).grid(
            row=2, column=1, columnspan=3, sticky="w", padx=(6, 0), pady=(8, 0))
        slider = ttk.Frame(f)
        slider.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._slider(slider, "mood_brightness", 0, "Brightness", 0.05, 1.0)
        self._note(f, "Click Mood light below to turn it on. Effects change slowly on purpose. Mood light "
                      "follows the schedule and turns off with the display, like screen sync.", 4)

    def pick_mood_color(self):
        _, color = colorchooser.askcolor(color=self.cfg["mood_color"], parent=self.root, title="Mood light color")
        if color:
            self._set_mood_color(color)

    def _set_mood_color(self, color):
        self.mood_swatch.config(bg=color)
        self._set("mood_color", color.lower())

    # Schedule -----------------------------------------------------------
    def _schedule_tab(self, f):
        self._check(f, "off_when_idle", 0, "Turn the lights off while the display sleeps, the PC is locked\n"
                                          "or the PC is asleep", pady=(0, 6))
        self._check(f, "schedule_enabled", 1, "Only turn the lights on between")
        times = ttk.Frame(f)
        times.grid(row=2, column=0, columnspan=4, sticky="w", padx=(22, 0))
        for i, key in enumerate(("schedule_on", "schedule_off")):
            var = self._bind(key, tk.StringVar())
            ttk.Combobox(times, textvariable=var, values=schedule.CHOICES, width=7).grid(row=0, column=i * 2)
            if i == 0:
                ttk.Label(times, text="and").grid(row=0, column=1, padx=6)

        ttk.Label(f, text="When AmbiEdge opens").grid(row=3, column=0, sticky="w", pady=(12, 0))
        var, labels = self._bind_choice("start_mode", [("none", "Do nothing"), ("sync", "Start screen sync"),
                                                       ("mood", "Turn on mood light")])
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=20).grid(
            row=3, column=1, sticky="w", padx=(6, 0), pady=(12, 0))
        self._login_var = tk.BooleanVar(value=autostart.is_enabled())
        ttk.Checkbutton(f, text=LOGIN_LABEL, variable=self._login_var,
                        command=self._toggle_login, state="normal" if autostart.supported else "disabled").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        if self.tray:
            self._check(f, "close_to_tray", 5, f"Closing the window keeps AmbiEdge running in the {system.TRAY}")
        self._note(f, "Times are 24-hour (type any time, like 22:45). If the off time is earlier than the "
                      f"on time, the lights stay on past midnight. {STARTED_AT_LOGIN}, AmbiEdge "
                      f"opens in the {system.TRAY}.", 6)

    def _toggle_login(self):
        try:
            autostart.set_enabled(self._login_var.get())
        except OSError as e:
            self._login_var.set(autostart.is_enabled())
            messagebox.showerror("AmbiEdge", f"Couldn't change the startup setting: {e}")

    # Advanced -------------------------------------------------------------
    def _advanced_tab(self, f):
        self._spin(f, "fps", 0, 0, "FPS", width=4)
        self._spin(f, "monitor", 0, 2, "Monitor #", width=4)
        ttk.Label(f, text="Capture").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=2)
        if sys.platform == "win32":
            methods = [("auto", "Automatic"), ("dxcam", "DXGI (Windows)"), ("mss", "GDI / mss")]
        else:
            methods = [("auto", "Automatic"), ("mss", "mss")]
        var, labels = self._bind_choice("capture", methods)
        ttk.Combobox(f, textvariable=var, values=labels, state="readonly", width=14).grid(row=1, column=1, sticky="w")
        self._spin(f, "group", 1, 2, "LEDs per zone", width=4)
        self._spin(f, "max_power", 2, 0, "Max power", width=5, increment=5)
        ttk.Label(f, text="per LED (R+G+B, 765 = no limit)", foreground="gray").grid(row=2, column=2, columnspan=2, sticky="w")

        wb = ttk.LabelFrame(f, text="White balance", padding=6)
        wb.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._slider(wb, "white_r", 0, "Red", 0.0, 1.0)
        self._slider(wb, "white_g", 1, "Green", 0.0, 1.0)
        self._slider(wb, "white_b", 2, "Blue", 0.0, 1.0)
        self._note(f, "Max power 255 keeps a strip powered from USB within safe limits. Raise it only if the "
                      "strip has its own power supply rated for it. If the wrong screen is used, try another "
                      "Monitor #. Use White balance if white looks blue or green.", 4)

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

    # ---- engine and tray -------------------------------------------------------
    def _poll(self):
        try:
            while True:
                text = self._status_queue.get_nowait()
                if text is not None:
                    self.status.set(text)
                self._refresh_buttons()
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_tray(self._tray_events.get_nowait())
        except queue.Empty:
            pass
        if self._closed:
            return
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
            if dev.led_count and dev.led_count != self.cfg["reported_leds"]:
                self._set("reported_leds", min(dev.led_count, RANGES["reported_leds"][1]))
        elif not self.engine.mode:
            self.device_info.set("Not connected.")
        if self.engine.mode == "sync" and self.engine.active_profile:
            why = f", because {self.engine.profile_app} is in front" if self.engine.profile_app else ""
            self.profile_info.set(f"In use now: {self.engine.active_profile}{why}.")
        else:
            self.profile_info.set("")
        self._update_tray()
        self.root.after(66, self._poll)

    def _refresh_buttons(self):
        mode = self.engine.mode
        self.sync_btn.config(text="Stop sync" if mode == "sync" else "Start sync")
        self.mood_btn.config(text="Mood light off" if mode == "mood" else "Mood light")
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

    def toggle_mood(self):
        self._toggle("mood")

    def toggle_test(self):
        self._toggle("test")

    def lights_off(self):
        if self.engine.mode:
            self.engine.stop()
            self.status.set("Stopped.")
            self._refresh_buttons()

    def _update_tray(self):
        if not self.tray:
            return
        mode, paused = self.engine.mode, self.engine.paused
        key = (mode, paused, self.engine.active_profile)
        if key == self._tray_key:
            return
        self._tray_key = key
        if mode == "sync":
            tip = f"AmbiEdge: syncing ({self.engine.active_profile or self.cfg['profile']})"
        elif mode == "mood":
            tip = "AmbiEdge: mood light"
        elif mode == "test":
            tip = "AmbiEdge: test pattern"
        else:
            tip = "AmbiEdge: off"
        if paused:
            tip = f"AmbiEdge: paused, {paused}"
        size = max(16, system.small_icon_size())
        self.monitor.set_tray(icon.render(size, active=bool(mode) and not paused), tip)

    def _brightness_target(self):
        """(profile name or None for mood light, current brightness) that the tray menu controls."""
        if self.engine.mode == "mood":
            return None, self.cfg["mood_brightness"]
        name = self.engine.active_profile or self.cfg["profile"]
        return name, self.cfg["profiles"][name]["brightness"]

    def tray_menu(self):
        """Right-click menu for the tray icon. Called from the monitor thread."""
        mode = self.engine.mode
        _, level = self._brightness_target()
        names = list(self.cfg["profiles"])
        active = self.engine.active_profile or self.cfg["profile"]
        return [
            ("Open AmbiEdge", MENU_OPEN, False, True),
            None,
            ("Screen sync", MENU_SYNC, mode == "sync", True),
            ("Mood light", MENU_MOOD, mode == "mood", True),
            ("Off", MENU_OFF, mode is None, True),
            None,
            ("Brightness", [(f"{int(b * 100)}%", MENU_BRIGHTNESS + i, abs(level - b) < 0.02, True)
                            for i, b in enumerate(BRIGHTNESS_STEPS)], False, True),
            ("Profile", [(n, MENU_PROFILE + i, n == active, True) for i, n in enumerate(names)]
             + [None, ("Switch automatically by app", MENU_AUTO, self.cfg["auto_profile"], True)], False, True),
            None,
            ("Quit", MENU_QUIT, False, True),
        ]

    def _handle_tray(self, event):
        if event in ("open", MENU_OPEN):
            self.show_window()
        elif event == MENU_SYNC:
            if self.engine.mode != "sync":
                self.toggle_sync()
        elif event == MENU_MOOD:
            if self.engine.mode != "mood":
                self.toggle_mood()
        elif event == MENU_OFF:
            self.lights_off()
        elif event == MENU_QUIT:
            self.quit()
        elif event == MENU_AUTO:
            self.vars["auto_profile"].set(not self.cfg["auto_profile"])
        elif isinstance(event, int) and MENU_BRIGHTNESS <= event < MENU_BRIGHTNESS + len(BRIGHTNESS_STEPS):
            self._set_brightness(BRIGHTNESS_STEPS[event - MENU_BRIGHTNESS])
        elif isinstance(event, int) and event >= MENU_PROFILE:
            names = list(self.cfg["profiles"])
            if event - MENU_PROFILE < len(names):
                self.select_profile(names[event - MENU_PROFILE])

    def _set_brightness(self, value):
        name, _ = self._brightness_target()
        if name is None:
            self.vars["mood_brightness"].set(value)
        elif name == self.cfg["profile"]:
            self.vars["brightness"].set(value)
        else:
            with self._cfg_lock:
                self.cfg["profiles"][name]["brightness"] = value
            self._save_soon()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        system.bring_to_front()
        self.root.focus_force()

    # ---- dialogs, startup and shutdown ---------------------------------------
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
        self._start_mode()

    def _start_mode(self):
        if self.cfg["start_mode"] == "sync":
            self.toggle_sync()
        elif self.cfg["start_mode"] == "mood":
            self.toggle_mood()

    def on_close(self):
        """Window close button: hide to the tray if there is one, otherwise quit."""
        if self.tray and self.cfg["close_to_tray"]:
            self.root.withdraw()
            if not self.cfg["tray_hint_shown"]:
                if MAC:
                    hint = ("Click its icon in the menu bar to open it, turn the lights on or off, "
                            "change brightness, or quit.")
                else:
                    hint = ("Click the tray icon to open it. Right-click it to turn the lights "
                            "on or off, change brightness, or quit.")
                self.monitor.balloon("AmbiEdge is still running", hint)
                self._set("tray_hint_shown", True)
            return
        self.quit()

    def quit(self):
        self._closed = True
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save()
        self.engine.stop()
        if self.monitor is not None:
            self.monitor.stop()
        self.root.destroy()


def run(cfg, config_path=None, minimized=False):
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on scaled displays
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    app = App(root, cfg, config_path)
    if minimized:
        if app.tray:
            root.withdraw()
        else:
            root.iconify()
    root.mainloop()
