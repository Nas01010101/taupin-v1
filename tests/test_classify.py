import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
from PIL import Image  # noqa: E402

from taupin import classify as C  # noqa: E402
from taupin.__main__ import main  # noqa: E402

FX = Path(__file__).parent / "fixtures"
LABELS = json.loads((FX / "model" / "labels.json").read_text())


def test_target_size_and_rounding():
    assert C.target_size(37, 53, 8) == (8, 11)
    assert C.target_size(4000, 3000, 224) == (298, 224)
    assert [C.round_half_even(v) for v in (0.5, 1.5, 2.5)] == [0, 2, 2]


def test_resize_kernel_matches_pil_bilinear():
    # The kernel claim in the docstring: same filter as PIL BILINEAR (PIL rounds to uint8 per pass).
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (90, 130, 3), dtype=np.uint8)
    lab = {**LABELS, "input_size": 32, "mean": [0, 0, 0], "std": [1, 1, 1]}
    ours = C.preprocess(img, lab)[0].transpose(1, 2, 0) * 255
    nw, nh = C.target_size(130, 90, 32)
    pil = np.asarray(Image.fromarray(img).resize((nw, nh), Image.BILINEAR), dtype=np.float64)
    left = C.round_half_even((nw - 32) / 2)
    assert np.abs(ours - pil[:, left:left + 32]).max() <= 2.0


def test_golden_tensor_is_current():
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("make_fixture", FX / "make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    golden_image = mod.golden_image
    g = json.loads((FX / "preprocess_golden.json").read_text())
    x = C.preprocess(golden_image(), LABELS).ravel()
    assert np.abs(x - np.array(g["x"])).max() < 1e-5


def test_softmax_and_abstain():
    p = C.softmax([2.0, 0.0, 0.0])
    assert abs(sum(p) - 1) < 1e-12 and C.softmax([2.0, 0.0, 0.0], 4.0)[0] < p[0]
    assert C.decide([0.7, 0.2, 0.1], LABELS)["unclear"] is False
    r = C.decide([0.5, 0.3, 0.2], LABELS)
    assert r["unclear"] and C.format_answer(r).startswith(C.UNCLEAR)
    assert C.format_answer(C.decide([0.9, 0.05, 0.05], LABELS)) == "Red test bug (90.0 %), pest"


@pytest.mark.parametrize("rgb,cls", [((230, 20, 20), "red_bug"), ((20, 20, 230), "blue_bug")])
def test_classify_fixture_model(tmp_path, rgb, cls):
    pytest.importorskip("onnxruntime")
    photo = tmp_path / "bug.png"
    Image.new("RGB", (40, 30), rgb).save(photo)
    assert C.classify(photo, FX / "model")["id"] == cls


def test_cli_prints_answer(tmp_path, capsys):
    pytest.importorskip("onnxruntime")
    photo = tmp_path / "grey.png"
    Image.new("RGB", (16, 16), (128, 128, 128)).save(photo)
    assert main(["classify", str(photo), "--model", str(FX / "model")]) == 0
    assert capsys.readouterr().out.strip().startswith("grey.png: unclear: send to the lab")


def test_cli_reports_missing_model(tmp_path, capsys):
    assert main(["classify", "x.jpg", "--model", str(tmp_path)]) == 2
    assert "model not installed" in capsys.readouterr().err
