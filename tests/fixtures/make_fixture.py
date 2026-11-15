"""Write the tiny test model and its labels: logits = global-average RGB x 10 per class.

A red image scores class 0, green class 1, blue class 2. Used by tests/test_classify.py and
web/test/*.test.mjs. Regenerate with:  uv run python tests/fixtures/make_fixture.py
"""
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

HERE = Path(__file__).parent
S = 8
LABELS = {
    "classes": [{"id": "red_bug", "name": "Red test bug", "pest": True},
                {"id": "green_bug", "name": "Green test bug", "pest": False},
                {"id": "blue_bug", "name": "Blue <b>test</b> bug", "pest": False}],
    "input_size": S, "mean": [0.5, 0.5, 0.5], "std": [0.25, 0.25, 0.25],
    "temperature": 1.0, "abstain_below": 0.6, "version": "fixture-1",
}


def golden_image(w=37, h=53):
    """Deterministic RGB pattern, reproduced in web/test/classify.test.mjs."""
    y, x = np.mgrid[0:h, 0:w]
    return np.stack([(x * 7 + y * 3) % 256, (x * y) % 256, (x + 2 * y) % 256], -1).astype(np.uint8)


def main():
    w = numpy_helper.from_array((np.eye(3) * 10).astype(np.float32), "W")
    b = numpy_helper.from_array(np.zeros(3, np.float32), "B")
    graph = helper.make_graph(
        [helper.make_node("GlobalAveragePool", ["image"], ["gap"]),
         helper.make_node("Flatten", ["gap"], ["flat"]),
         helper.make_node("Gemm", ["flat", "W", "B"], ["logits"])],
        "taupin_fixture",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, S, S])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 3])],
        [w, b])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, HERE / "model" / "taupin.onnx")
    (HERE / "model" / "labels.json").write_text(json.dumps(LABELS, indent=1))

    import sys
    sys.path.insert(0, str(HERE.parents[1] / "src"))
    from taupin.classify import preprocess
    x = preprocess(golden_image(), LABELS)
    (HERE / "preprocess_golden.json").write_text(json.dumps({"w": 37, "h": 53, "x": np.round(x.ravel(), 6).tolist()}))


if __name__ == "__main__":
    main()
