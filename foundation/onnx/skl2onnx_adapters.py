from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np
import onnx
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType


HIST_GRADIENT_BOOSTING_CAST_ADAPTER_ID = "skl2onnx_hgb_numpy_scalar_cast_v0"


@dataclass(frozen=True)
class OnnxConversionResult:
    model: onnx.ModelProto
    adapter_ids: list[str]


def _patched_hgb_tree_attributes(
    attr_pairs: dict[str, Any],
    is_classifier: bool,
    tree: Any,
    tree_id: int,
    tree_weight: float,
    weight_id_bias: int,
    leaf_weights_are_counts: bool,
    adjust_threshold_for_sklearn: bool = False,
    dtype: Any = None,
) -> None:
    from skl2onnx.common import tree_ensemble

    for index, node in enumerate(tree.nodes):
        node_id = int(index)
        weight = np.array([float(node["value"])], dtype=np.float64)

        if bool(node["is_leaf"]):
            mode = "LEAF"
            feature_id = 0
            threshold = 0.0
            left_child_id = 0
            right_child_id = 0
            missing_tracks_true = 0
        else:
            mode = "BRANCH_LEQ"
            feature_id = int(node["feature_idx"])
            try:
                threshold = float(node["threshold"])
            except ValueError:
                threshold = float(node["num_threshold"])
            left_child_id = int(node["left"])
            right_child_id = int(node["right"])
            missing_tracks_true = int(bool(node["missing_go_to_left"]))

        tree_ensemble.add_node(
            attr_pairs,
            is_classifier,
            int(tree_id),
            float(tree_weight),
            node_id,
            feature_id,
            mode,
            threshold,
            left_child_id,
            right_child_id,
            weight,
            int(weight_id_bias),
            leaf_weights_are_counts,
            adjust_threshold_for_sklearn=adjust_threshold_for_sklearn,
            dtype=dtype,
            nodes_missing_value_tracks_true=missing_tracks_true,
        )


@contextmanager
def _hist_gradient_boosting_adapter() -> Iterator[None]:
    import skl2onnx.common.tree_ensemble as tree_ensemble
    import skl2onnx.operator_converters.random_forest as random_forest

    original_tree = tree_ensemble.add_tree_to_attribute_pairs_hist_gradient_boosting
    original_rf = random_forest.add_tree_to_attribute_pairs_hist_gradient_boosting
    tree_ensemble.add_tree_to_attribute_pairs_hist_gradient_boosting = _patched_hgb_tree_attributes
    random_forest.add_tree_to_attribute_pairs_hist_gradient_boosting = _patched_hgb_tree_attributes
    try:
        yield
    finally:
        tree_ensemble.add_tree_to_attribute_pairs_hist_gradient_boosting = original_tree
        random_forest.add_tree_to_attribute_pairs_hist_gradient_boosting = original_rf


def convert_sklearn_pipeline_for_lab(
    model: Any,
    *,
    feature_count: int,
    task_kind: str,
    target_opset: int,
) -> OnnxConversionResult:
    options = {id(model): {"zipmap": False}} if task_kind == "classification" else None
    with _hist_gradient_boosting_adapter():
        converted = convert_sklearn(
            model,
            initial_types=[("features", FloatTensorType([None, feature_count]))],
            target_opset=target_opset,
            options=options,
        )
    onnx.checker.check_model(converted)
    adapter_ids = [HIST_GRADIENT_BOOSTING_CAST_ADAPTER_ID] if _uses_hist_gradient_boosting(model) else []
    return OnnxConversionResult(model=converted, adapter_ids=adapter_ids)


def _uses_hist_gradient_boosting(model: Any) -> bool:
    steps = getattr(model, "steps", [])
    raw_estimators = [step for _, step in steps] if steps else [model]
    return any(estimator.__class__.__name__.startswith("HistGradientBoosting") for estimator in raw_estimators)
