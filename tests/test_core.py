import json

import numpy as np
import pytest

from ambiedge.config import DEFAULTS, clean, load_config, save_config
from ambiedge.layout import Layout, test_pattern as make_test_pattern
from ambiedge.processing import ColorProcessor
from ambiedge.sampler import sample_edges


def ids(layout):
    """Loop positions in strip order, as a list."""
    return layout.order.tolist()


def test_layout_clockwise_from_bottom_left():
    assert ids(Layout(2, 3, 2)) == [0, 1, 2, 3, 4, 5, 6]


def test_layout_counter_clockwise_from_bottom_right_matches_old_reverse():
    # Old "strip runs the other way": up the right side, across the top right->left, down the left.
    lay = Layout(2, 3, 2, start_corner="bottom-right", clockwise=False)
    assert ids(lay) == [6, 5, 4, 3, 2, 1, 0]


def test_layout_with_bottom_and_shift():
    lay = Layout(1, 2, 1, 2, start_corner="top-left")
    assert ids(lay) == [1, 2, 3, 4, 5, 0]
    assert ids(Layout(1, 2, 1, 2, start_corner="top-left", shift=1)) == [2, 3, 4, 5, 0, 1]
    ccw = Layout(1, 2, 1, 2, start_corner="bottom-left", clockwise=False)
    assert ids(ccw) == [5, 4, 3, 2, 1, 0]


def test_layout_round_trip_and_empty():
    lay = Layout(3, 4, 3, 2, start_corner="top-right", clockwise=False, shift=2)
    loop = np.arange(lay.total * 3).reshape(-1, 3)
    assert np.array_equal(lay.to_loop(lay.to_chain(loop)), loop)
    assert Layout(0, 0, 0).total == 0


def test_test_pattern_marks_led1():
    lay = Layout(2, 2, 2, start_corner="top-left")
    on, off = make_test_pattern(lay, True), make_test_pattern(lay, False)
    first = lay.order[0]
    assert on[first].tolist() == [255, 255, 255] and off[first].tolist() == [0, 0, 0]


def synthetic_frame():
    # 4K BGRA: left half red, right half blue, top 10% green, bottom 10% white.
    f = np.zeros((2160, 3840, 4), np.uint8)
    f[:, :1920, 2] = 255
    f[:, 1920:, 0] = 255
    f[:216, :, :3] = (0, 255, 0)
    f[-216:, :, :3] = 255
    return f


def test_sample_edges():
    lay = Layout(20, 38, 20, 10)
    left, top, right, bottom = sample_edges(synthetic_frame(), lay, depth=0.05)
    assert [a.shape for a in (left, top, right, bottom)] == [(20, 3), (38, 3), (20, 3), (10, 3)]
    assert left[10].round().tolist() == [255, 0, 0]
    assert right[10].round().tolist() == [0, 0, 255]
    assert top[5].round().tolist() == [0, 255, 0]
    assert bottom[3].round().tolist() == [255, 255, 255]


def test_sample_edges_more_leds_than_pixels_and_gap():
    frame = np.full((90, 160, 4), 128, np.uint8)
    lay = Layout(300, 300, 300, 6, bottom_gap=4)
    left, top, right, bottom = sample_edges(frame, lay)
    assert left.shape == (300, 3) and bottom.shape == (6, 3)
    assert np.allclose(left, 128) and np.allclose(bottom, 128)


def cfg(**kw):
    return dict(DEFAULTS, **kw)


def test_processing_power_limit_and_color_order():
    proc = ColorProcessor()
    out, preview = proc.process([[255, 255, 255], [255, 0, 0]], cfg(saturation=1.0, max_power=255, color_order="GRB"))
    assert out.dtype == np.uint8
    assert preview[0].sum() <= 255 and abs(int(preview[0][0]) - 85) <= 1
    assert out[1].tolist() == [0, 255, 0]  # red sent in GRB order


def test_processing_smoothing_and_grouping():
    proc = ColorProcessor()
    c = cfg(saturation=1.0, smoothing=0.5, max_power=765)
    proc.process([[0, 0, 0]], c)
    _, preview = proc.process([[200, 0, 0]], c)
    assert preview[0][0] == 100
    _, grouped = ColorProcessor().process([[200, 0, 0], [0, 0, 0], [0, 200, 0]], cfg(saturation=1.0, max_power=765, group=2, black_level=0))
    assert grouped[0].tolist() == grouped[1].tolist() == [100, 0, 0]


def test_config_clean_fixes_bad_values():
    c = clean({"left": "40", "top": -5, "fps": "fast", "driver": "nope", "clockwise": "yes", "brightness": 9})
    assert c["left"] == 40 and c["top"] == 0 and c["fps"] == DEFAULTS["fps"]
    assert c["driver"] == DEFAULTS["driver"] and c["clockwise"] is True and c["brightness"] == 1.0


def test_config_round_trip(tmp_path):
    path = str(tmp_path / "sub" / "config.json")
    save_config(cfg(left=7), path)
    assert load_config(path)["left"] == 7
    (tmp_path / "bad.json").write_text("{not json")
    assert load_config(str(tmp_path / "bad.json")) == DEFAULTS
    (tmp_path / "list.json").write_text(json.dumps([1, 2]))
    assert load_config(str(tmp_path / "list.json")) == DEFAULTS


@pytest.mark.parametrize("key", ["left", "top", "right", "bottom"])
def test_zero_edges(key):
    lay = Layout(**{"left": 3, "top": 3, "right": 3, "bottom": 3, key: 0})
    edges = sample_edges(synthetic_frame(), lay)
    assert Layout.loop_from_edges(*edges).shape == (lay.total, 3)
