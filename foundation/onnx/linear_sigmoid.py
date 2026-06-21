from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def build_linear_sigmoid_onnx(
    *,
    feature_count: int,
    coefficients: np.ndarray,
    intercept: float,
    feature_mean: np.ndarray,
    feature_scale: np.ndarray,
    output_path: Path,
    opset: int = 13,
) -> None:
    """Create a compact ONNX graph: sigmoid(sum(((x-mean)/scale)*coef)+intercept)."""
    coefficients = np.asarray(coefficients, dtype=np.float32).reshape(feature_count)
    feature_mean = np.asarray(feature_mean, dtype=np.float32).reshape(feature_count)
    feature_scale = np.asarray(feature_scale, dtype=np.float32).reshape(feature_count)
    safe_scale = np.where(feature_scale == 0.0, 1.0, feature_scale).astype(np.float32)

    input_tensor = helper.make_tensor_value_info("features", TensorProto.FLOAT, [feature_count])
    output_tensor = helper.make_tensor_value_info("probability", TensorProto.FLOAT, [1])

    nodes = [
        helper.make_node("Sub", ["features", "feature_mean"], ["centered"], name="center_features"),
        helper.make_node("Div", ["centered", "feature_scale"], ["scaled"], name="scale_features"),
        helper.make_node("Mul", ["scaled", "coefficients"], ["weighted"], name="apply_coefficients"),
        helper.make_node("ReduceSum", ["weighted", "reduce_axes"], ["logit_sum"], name="sum_logit", keepdims=1),
        helper.make_node("Add", ["logit_sum", "intercept"], ["logit"], name="add_intercept"),
        helper.make_node("Sigmoid", ["logit"], ["probability"], name="sigmoid_probability"),
    ]
    initializers = [
        numpy_helper.from_array(feature_mean, name="feature_mean"),
        numpy_helper.from_array(safe_scale, name="feature_scale"),
        numpy_helper.from_array(coefficients, name="coefficients"),
        numpy_helper.from_array(np.asarray([intercept], dtype=np.float32), name="intercept"),
        numpy_helper.from_array(np.asarray([0], dtype=np.int64), name="reduce_axes"),
    ]

    graph = helper.make_graph(
        nodes,
        "spacesonar_fixture_linear_sigmoid_v0",
        [input_tensor],
        [output_tensor],
        initializer=initializers,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", opset)])
    model.ir_version = 7
    onnx.checker.check_model(model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, output_path)
