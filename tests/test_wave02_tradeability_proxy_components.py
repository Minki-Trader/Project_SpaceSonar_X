from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foundation.features.wave02_tradeability_features import FEATURE_FAMILY_BY_RECIPE, build_wave02_tradeability_features
from foundation.labels.wave02_tradeability_labels import LABEL_CONFIGS, build_wave02_tradeability_labels


def _synthetic_closed_bar_frame(rows: int = 240) -> pd.DataFrame:
    timestamp = pd.date_range("2024-01-02T13:30:00Z", periods=rows, freq="5min")
    idx = np.arange(rows, dtype=float)
    close = 16000.0 + idx * 0.75 + np.sin(idx / 4.0) * 12.0 + np.where((idx % 47) < 4, idx % 5, 0.0)
    open_ = close - np.cos(idx / 5.0) * 2.0
    high = np.maximum(open_, close) + 4.0 + (idx % 7) * 0.2
    low = np.minimum(open_, close) - 4.0 - (idx % 5) * 0.2
    role = np.where(idx < 120, "train", np.where(idx < 180, "validation", "research_oos_a"))
    return pd.DataFrame(
        {
            "model_row_key": [f"row_{int(item):04d}" for item in idx],
            "primary_split_role": role,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": 1000.0 + (idx % 19) * 11.0,
            "spread_points": 12.0 + (idx % 3),
            "real_volume": np.zeros(rows),
            "row_seq": idx.astype(int),
            "time_open_unix": (timestamp.view("int64") // 1_000_000_000).astype(int),
            "time_close_unix": (timestamp.view("int64") // 1_000_000_000 + 300).astype(int),
            "us100_bar_close_time_utc_rendered": timestamp.astype(str),
        }
    )


@pytest.mark.parametrize("feature_recipe_id", sorted(FEATURE_FAMILY_BY_RECIPE))
def test_wave02_feature_recipes_emit_declared_schema(feature_recipe_id: str) -> None:
    frame = _synthetic_closed_bar_frame()

    features, schema = build_wave02_tradeability_features(frame, feature_recipe_id)

    assert schema.feature_recipe_id == feature_recipe_id
    assert schema.feature_family == FEATURE_FAMILY_BY_RECIPE[feature_recipe_id]
    assert schema.feature_columns == list(features.columns)
    assert schema.boundary == "right_aligned_closed_bar_us100_wave02_tradeability_features_no_aux_symbols"
    assert len(schema.feature_schema_hash) == 64
    assert features.notna().any().any()


@pytest.mark.parametrize("label_recipe_id", sorted(LABEL_CONFIGS))
def test_wave02_label_recipes_respect_same_role_horizon(label_recipe_id: str) -> None:
    frame = _synthetic_closed_bar_frame()
    horizon = LABEL_CONFIGS[label_recipe_id][1]

    labels, schema = build_wave02_tradeability_labels(frame, label_recipe_id)

    assert schema.label_recipe_id == label_recipe_id
    assert schema.horizon_bars == horizon
    assert schema.target_columns == list(labels.columns)
    assert len(schema.label_schema_hash) == 64
    assert int(labels["same_role_horizon_ok"].sum()) > 0
    eligible_with_target = labels["same_role_horizon_ok"] & labels["target_continuous"].notna()
    assert int(eligible_with_target.sum()) > 0
    assert labels.loc[eligible_with_target, "target_binary_raw"].notna().all()
    assert labels.loc[119 - horizon + 1 : 119, "same_role_horizon_ok"].eq(False).all()
