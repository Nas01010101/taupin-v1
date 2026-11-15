"""Tests for preprocessing, calibration, thresholds, licence filter and split helpers.

    uv run --no-project --with pytest --with numpy --with pillow pytest train/tests -q
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evalutil import (fit_temperature, headline, macro_f1, pick_threshold, preprocess, resize_crop,  # noqa: E402
                      softmax)
from fetch_ood import ILLUSTRATION, commons_thumb, is_open  # noqa: E402
from split import user_split  # noqa: E402


def test_resize_crop_short_side_and_centre():
    im = Image.new("RGB", (448, 300), (0, 0, 0))
    im.paste((255, 0, 0), (0, 0, 60, 300))  # red strip on the far left is cropped away
    out = resize_crop(im, 224)
    assert out.size == (224, 224)
    assert out.getpixel((0, 112))[0] < 50


def test_preprocess_layout_and_normalisation():
    im = Image.new("RGB", (300, 300), (255, 0, 0))
    x = preprocess(im, 224, mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
    assert x.shape == (3, 224, 224) and x.dtype == np.float32
    assert np.allclose(x[0], 1.0) and np.allclose(x[1], -1.0) and np.allclose(x[2], -1.0)


def test_temperature_recovers_scale():
    rng = np.random.default_rng(0)
    true = rng.normal(size=(4000, 5))
    y = np.array([rng.choice(5, p=p) for p in softmax(true)])
    t = fit_temperature(true * 3.0, y)  # logits 3x too sharp -> temperature near 3
    assert 2.5 < t < 3.5


def test_threshold_meets_target_and_maximises_coverage():
    prob = np.array([[0.9, 0.1], [0.8, 0.2], [0.6, 0.4], [0.55, 0.45]])
    y = np.array([0, 0, 1, 0])
    thr, met = pick_threshold(prob, y, target=0.9, min_coverage=0.0)
    assert met and thr == 0.8
    h = headline(prob, y, thr, 2)
    assert h["coverage_at_threshold"] == 0.5 and h["accuracy_at_threshold"] == 1.0


def test_macro_f1_ignores_absent_classes():
    y = np.array([0, 0, 1, 1])
    assert macro_f1(y, y, 3) == 1.0


def test_licence_filter():
    assert is_open("http://creativecommons.org/licenses/by/4.0/")
    assert is_open("CC0") and is_open("Public domain") and is_open("CC BY 2.0")
    for bad in ["http://creativecommons.org/licenses/by-nc/4.0/", "CC BY-SA 4.0", "CC BY-ND 3.0",
                "Copyright by the creator.", "", None]:
        assert not is_open(bad)


def test_illustration_filter_and_split_determinism():
    assert ILLUSTRATION.search("File:Agriotes.lineatus.-.calwer.26.19.jpg")
    assert not ILLUSTRATION.search("File:Lumbricus terrestris in soil.jpg")
    assert user_split("inat-user-1") == user_split("inat-user-1")
    assert {user_split(f"inat-user-{i}") for i in range(200)} == {"train", "val", "test"}


def test_commons_thumb_url():
    u = "https://upload.wikimedia.org/wikipedia/commons/0/01/Earthworm_cocoons.jpg?utm_source=commons"
    assert commons_thumb(u) == ("https://upload.wikimedia.org/wikipedia/commons/thumb/0/01/Earthworm_cocoons.jpg/"
                                "960px-Earthworm_cocoons.jpg")
