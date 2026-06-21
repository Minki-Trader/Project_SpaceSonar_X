from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LabelSchema:
    label_recipe_id: str
    target_family: str
    horizon_bars: int
    target_columns: list[str]
    label_schema_hash: str
    boundary: str


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.astype(float) / denominator.replace(0.0, np.nan).astype(float)


def _future_extreme(series: pd.Series, horizon_bars: int, reducer: str) -> pd.Series:
    shifted = [series.shift(-step) for step in range(1, horizon_bars + 1)]
    future = pd.concat(shifted, axis=1)
    if reducer == "max":
        return future.max(axis=1)
    if reducer == "min":
        return future.min(axis=1)
    raise ValueError(f"unsupported reducer: {reducer}")


def _causal_atr_scaled(frame: pd.DataFrame, window: int = 48) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=12).mean()


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for horizon boundary mask")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def build_wave0_labels(frame: pd.DataFrame, target_family: str, horizon_bars: int) -> tuple[pd.DataFrame, LabelSchema]:
    required = {"high", "low", "close", "primary_split_role"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns for Wave0 labels: {sorted(missing)}")
    if horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")

    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    atr = _causal_atr_scaled(frame)
    atr_pct = _safe_div(atr, close)
    up_move_atr = _safe_div(future_high - close, atr)
    down_move_atr = _safe_div(close - future_low, atr)
    path_quality = up_move_atr - 0.75 * down_move_atr
    tradeability_score = _safe_div(future_return.abs(), atr_pct)
    same_role = same_role_horizon_mask(frame, horizon_bars)

    result = pd.DataFrame(index=frame.index)
    result["future_return"] = future_return
    result["future_abs_return"] = future_return.abs()
    result["future_up_move_atr"] = up_move_atr
    result["future_down_move_atr"] = down_move_atr
    result["path_quality_score"] = path_quality
    result["tradeability_score"] = tradeability_score
    result["same_role_horizon_ok"] = same_role.astype(bool)
    result["label_end_primary_split_role"] = frame["primary_split_role"].shift(-horizon_bars)

    if target_family == "future_return_rank_or_quantile":
        result["target_continuous"] = future_return
        result["target_binary_raw"] = (future_return > 0.0).astype(float)
        boundary = "future_return_over_declared_horizon_same_primary_role_rows_only"
    elif target_family == "atr_scaled_barrier_event":
        signed_barrier = up_move_atr - down_move_atr
        result["target_continuous"] = signed_barrier
        result["target_binary_raw"] = ((up_move_atr >= down_move_atr) & (up_move_atr >= 0.5)).astype(float)
        boundary = "atr_scaled_future_path_barrier_over_declared_horizon_same_primary_role_rows_only"
    elif target_family == "path_quality_mfe_mae_payoff_suitability":
        result["target_continuous"] = path_quality
        result["target_binary_raw"] = (path_quality > 0.0).astype(float)
        boundary = "future_mfe_mae_path_quality_over_declared_horizon_same_primary_role_rows_only"
    elif target_family == "tradeability_or_no_trade_regime":
        result["target_continuous"] = tradeability_score
        result["target_binary_raw"] = np.nan
        boundary = "future_abs_return_vs_causal_atr_tradeability_score_same_primary_role_rows_only"
    else:
        raise ValueError(f"unsupported Wave0 target_family: {target_family}")

    result = result.replace([np.inf, -np.inf], np.nan)
    columns = list(result.columns)
    schema_payload = {
        "label_recipe_id": "label_wave0_surface_grid_v0",
        "target_family": target_family,
        "horizon_bars": horizon_bars,
        "target_columns": columns,
        "boundary": boundary,
    }
    schema = LabelSchema(
        label_recipe_id="label_wave0_surface_grid_v0",
        target_family=target_family,
        horizon_bars=horizon_bars,
        target_columns=columns,
        label_schema_hash=_hash_json(schema_payload),
        boundary=boundary,
    )
    return result[columns], schema
