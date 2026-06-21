from __future__ import annotations

import pandas as pd

from foundation.features.wave01_event_barrier_features import build_wave01_features
from foundation.labels.wave01_event_barrier_labels import build_wave01_labels
from foundation.training.wave01_event_barrier_models import build_model_target


def sample_frame(rows: int = 80) -> pd.DataFrame:
    close = pd.Series([100.0 + index * 0.1 for index in range(rows)])
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.6,
            "low": close - 0.5,
            "close": close,
            "tick_volume": [100 + index for index in range(rows)],
            "spread_points": [160 for _ in range(rows)],
            "primary_split_role": ["train" for _ in range(rows)],
            "us100_bar_close_time_utc_rendered": pd.date_range("2024-01-01", periods=rows, freq="5min", tz="UTC").astype(str),
        }
    )


def test_wave01_features_are_variable_by_family() -> None:
    frame = sample_frame()

    compact, compact_schema = build_wave01_features(frame, "price_return_range_volatility_context")
    multiscale, multiscale_schema = build_wave01_features(frame, "multiscale_price_range_volatility_context")

    assert len(compact.columns) > 5
    assert len(multiscale.columns) > len(compact.columns)
    assert compact_schema.feature_order_hash != multiscale_schema.feature_order_hash
    assert compact_schema.feature_family == "price_return_range_volatility_context"


def test_wave01_label_contract_keeps_horizon_boundary_and_train_target() -> None:
    frame = sample_frame()
    labels, schema = build_wave01_labels(
        frame,
        {
            "label_surface": "symmetric_barrier_touch_or_timeout",
            "horizon_bars": 6,
            "timeout_bars": 6,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 0.8,
            "lower_barrier": 0.8,
        },
    )
    train_mask = labels["same_role_horizon_ok"].astype(bool)
    target, task_kind, target_name, threshold = build_model_target(
        labels,
        train_mask,
        label_surface="symmetric_barrier_touch_or_timeout",
        model_family="logistic_or_linear_rank_scout",
        model_task="three_class_event_touch_timeout",
    )

    assert schema.label_surface == "symmetric_barrier_touch_or_timeout"
    assert labels["same_role_horizon_ok"].sum() == len(frame) - 6
    assert task_kind == "classification"
    assert target_name in {"target_binary_raw", "target_continuous_train_q60"}
    assert threshold is None or isinstance(threshold, float)
    assert target.notna().any()


def test_wave01_label_supports_non_atr_barrier_units_from_specs() -> None:
    frame = sample_frame()

    for barrier_unit in ["price_range_ratio", "mfe_mae_ratio"]:
        labels, schema = build_wave01_labels(
            frame,
            {
                "label_surface": "mfe_mae_path_quality_ratio",
                "horizon_bars": 6,
                "timeout_bars": 6,
                "barrier_unit": barrier_unit,
                "upper_barrier": 1.0,
                "lower_barrier": 1.0,
            },
        )

        assert schema.label_surface == "mfe_mae_path_quality_ratio"
        assert "barrier_base_distance" in labels.columns
        assert labels["target_continuous"].notna().any()
