import datetime
import time

import numpy as np

from ambiedge import drivers, engine, icon, mood, schedule
from ambiedge.config import DEFAULTS, LOOK_KEYS, clean, copy_config
from ambiedge.layout import Layout, fit_counts
from ambiedge.sampler import sample_edges


def at(hh, mm):
    return datetime.datetime(2026, 1, 1, hh, mm)


def test_schedule():
    assert schedule.parse("7:05") == 425 and schedule.parse("24:00") is None and schedule.parse("x") is None
    assert schedule.is_on("18:00", "23:00", at(20, 0)) and not schedule.is_on("18:00", "23:00", at(23, 0))
    assert schedule.is_on("18:00", "01:00", at(0, 30)) and not schedule.is_on("18:00", "01:00", at(12, 0))
    assert schedule.is_on("18:00", "18:00", at(3, 0))  # same time means always on
    assert schedule.is_on("bad", "01:00", at(12, 0))


def test_mood_effects():
    for effect in mood.EFFECTS:
        out = mood.render(effect, "#ff0000", 12.3, 10)
        assert out.shape == (10, 3) and out.min() >= 0 and out.max() <= 255.01
    assert mood.render("solid", "#102030", 0, 2).tolist() == [[16, 32, 48]] * 2
    low, high = mood.render("breathe", "#ffffff", 0, 1)[0, 0], mood.render("breathe", "#ffffff", 3, 1)[0, 0]
    assert low < high
    assert mood.parse_color("nope") == mood.parse_color(None)
    rainbow = mood.render("rainbow", "#ff0000", 0, 6)
    assert len({tuple(c) for c in rainbow.round().tolist()}) == 6


def test_fit_counts():
    assert fit_counts(78, 16, 9) == {"left": 21, "top": 36, "right": 21, "bottom": 0}
    four = fit_counts(100, 16, 9, ("left", "top", "right", "bottom"))
    assert sum(four.values()) == 100 and four["left"] == four["right"] and four["top"] >= four["bottom"]
    for n in (1, 2, 3, 7, 500):
        assert sum(fit_counts(n, 21, 9, ("left", "top", "right", "bottom")).values()) == n
    assert fit_counts(10, 16, 9, ("top",)) == {"left": 0, "top": 10, "right": 0, "bottom": 0}


def test_vivid_sampling_keeps_saturated_color():
    frame = np.full((1080, 1920, 4), 128, np.uint8)
    frame[:60, 900:1000, :3] = (0, 0, 255)  # small red logo (BGRA) on gray, at the top
    lay = Layout(0, 1, 0)
    plain = sample_edges(frame, lay, 0.12, False, 0.0)[1][0]
    vivid = sample_edges(frame, lay, 0.12, False, 1.0)[1][0]
    assert vivid[0] - vivid[1] > 3 * (plain[0] - plain[1])


def test_profiles_from_old_settings_keep_the_users_look():
    cfg = clean({"brightness": 0.4, "smoothing": 0.9, "autostart_sync": True})
    assert set(cfg["profiles"]) == {"Desktop", "Movie", "Game"}
    assert cfg["profiles"]["Desktop"]["brightness"] == 0.4 and cfg["brightness"] == 0.4
    assert cfg["start_mode"] == "sync"


def test_profiles_are_cleaned_and_mirrored():
    raw = {"profile": "Late", "brightness": 1.0, "profiles": {
        "Late": {"brightness": 0.2, "gamma": 99, "apps": ["VLC.exe ", "", 5]},
        "": {"brightness": 0.5},
        "Broken": "nope",
    }}
    cfg = clean(raw)
    assert list(cfg["profiles"]) == ["Late"]
    late = cfg["profiles"]["Late"]
    assert late["apps"] == ["5", "vlc.exe"] and late["gamma"] == 3.0
    assert cfg["brightness"] == 0.2 and all(k in late for k in LOOK_KEYS)
    assert clean({"profile": "Missing", "profiles": raw["profiles"]})["profile"] == "Late"
    copied = copy_config(cfg)
    copied["profiles"]["Late"]["apps"].append("x.exe")
    assert cfg["profiles"]["Late"]["apps"] == ["5", "vlc.exe"]


def test_bad_mood_and_schedule_values_fall_back():
    cfg = clean({"mood_color": "red", "schedule_on": "25:00", "mood_effect": "disco", "start_mode": "x"})
    for key in ("mood_color", "schedule_on", "mood_effect", "start_mode"):
        assert cfg[key] == DEFAULTS[key]


class FakeMonitor:
    def __init__(self):
        self.display_on = True

    @property
    def in_use(self):
        return self.display_on

    @property
    def reason(self):
        return None if self.display_on else "the display is off"


def test_profile_resolution(monkeypatch):
    cfg = clean({"profile": "Desktop"})
    eng = engine.SyncEngine(lambda: cfg, lambda _: None)
    monkeypatch.setattr(engine.system, "foreground_app", lambda: "vlc.exe")
    look = eng.resolve_profile(cfg, now=100.0)
    assert eng.active_profile == "Movie" and eng.profile_app == "vlc.exe"
    assert look["smoothing"] == cfg["profiles"]["Movie"]["smoothing"]
    cfg["auto_profile"] = False
    eng.resolve_profile(cfg, now=200.0)
    assert eng.active_profile == "Desktop" and eng.profile_app is None


def test_pause_reasons():
    mon = FakeMonitor()
    cfg = clean({"schedule_enabled": True, "schedule_on": "18:00", "schedule_off": "23:00"})
    eng = engine.SyncEngine(lambda: cfg, lambda _: None, mon)
    assert eng.pause_reason(cfg, at(19, 0)) is None
    assert "schedule" in eng.pause_reason(cfg, at(9, 0))
    mon.display_on = False
    assert eng.pause_reason(cfg, at(19, 0)) == "the display is off"
    assert eng.pause_reason(dict(cfg, off_when_idle=False), at(19, 0)) is None


class Recorder(drivers.Driver):
    key = "virtual"

    def __init__(self, options):
        super().__init__(options)
        self.frames = []

    def send(self, colors):
        self.frames.append(colors.copy())


def test_mood_fades_in_and_turns_off_with_the_display(monkeypatch):
    rec = Recorder({})
    monkeypatch.setattr(engine.drivers, "create", lambda cfg: rec)
    monkeypatch.setattr(engine, "FADE_SECONDS", 0.3)
    mon = FakeMonitor()
    cfg = clean({"left": 2, "top": 2, "right": 2, "mood_color": "#ff0000", "mood_brightness": 1.0,
                 "max_power": 765, "white_r": 1.0})
    eng = engine.SyncEngine(lambda: cfg, lambda _: None, mon)
    eng.start("mood")
    try:
        time.sleep(0.8)
        reds = [int(f[:, 0].max()) for f in rec.frames]
        assert reds[0] < 255 and reds[-1] == 255  # faded in
        mon.display_on = False
        time.sleep(0.9)
        assert eng.paused == "the display is off"
        assert not rec.frames[-1].any()  # faded out to black
        mon.display_on = True
        time.sleep(0.8)
        assert eng.paused is None and rec.frames[-1][:, 0].max() == 255
    finally:
        eng.stop()


def test_icon_files():
    png = icon.png_bytes(icon.render(32))
    assert png.startswith(b"\x89PNG") and b"IEND" in png
    ico = icon.ico_bytes((16, 32))
    assert ico[:6] == b"\x00\x00\x01\x00\x02\x00"
    assert icon.render(24, active=False).shape == (24, 24, 4)
