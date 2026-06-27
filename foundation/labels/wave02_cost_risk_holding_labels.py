from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostRiskHoldingLabelSchema:
    label_recipe_id: str
    label_variant: str
    label_family: str
    horizon_bars: int
    target_columns: list[str]
    label_schema_hash: str
    boundary: str


LABEL_FAMILY_BY_VARIANT = {
    "cost_adjusted_h6": "cost_adjusted_tradeability",
    "cost_adjusted_h12": "cost_adjusted_tradeability",
    "adverse_excursion_h6": "adverse_excursion_tradeability",
    "open_failed_avoidance_h6": "open_failed_avoidance_tradeability",
    "session_cost_gate_h8": "session_cost_gate_tradeability",
    "volatility_stop_timeout_h10": "volatility_stop_timeout_tradeability",
}


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.astype(float) / denominator.replace(0.0, np.nan).astype(float)


def _true_range(frame: pd.DataFrame) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    prev_close = close.shift(1)
    return pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)


def _future_extreme(series: pd.Series, horizon_bars: int, reducer: str) -> pd.Series:
    future = pd.concat([series.shift(-step) for step in range(1, horizon_bars + 1)], axis=1)
    if reducer == "max":
        return future.max(axis=1)
    if reducer == "min":
        return future.min(axis=1)
    raise ValueError(f"unsupported reducer: {reducer}")


def _horizon_from_variant(label_variant: str) -> int:
    match = re.search(r"h(\d+)", label_variant)
    if not match:
        raise ValueError(f"label_variant does not name horizon: {label_variant}")
    return int(match.group(1))


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for Wave02 cost/risk/holding label boundary")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def build_wave02_cost_risk_holding_labels(
    frame: pd.DataFrame,
    label_recipe_id: str,
    label_variant: str,
) -> tuple[pd.DataFrame, CostRiskHoldingLabelSchema]:
    label_family = LABEL_FAMILY_BY_VARIANT.get(label_variant)
    if label_family is None:
        raise ValueError(f"unsupported Wave02 cost/risk/holding label_variant: {label_variant}")
    horizon_bars = _horizon_from_variant(label_variant)
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    spread = frame["spread_points"].astype(float)
    atr = _true_range(frame).rolling(48, min_periods=12).mean()
    atr_pct = _safe_div(atr, close)
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    up_progress = _safe_div(future_high - close, atr)
    down_progress = _safe_div(close - future_low, atr)
    adverse_progress = pd.concat([up_progress, down_progress], axis=1).min(axis=1)
    future_abs_return_atr = _safe_div(future_return.abs(), atr_pct)
    cost_return_proxy = _safe_div(spread / 100.0, close)
    cost_adjusted_abs_return = future_return.abs() - cost_return_proxy
    any_barrier_touch = (up_progress >= 1.0) | (down_progress >= 1.0)
    same_role = same_role_horizon_mask(frame, horizon_bars)

    spread_rank = spread.rolling(144, min_periods=36).rank(pct=True)
    volatility_rank = atr_pct.rolling(144, min_periods=36).rank(pct=True)
    low_cost = spread_rank <= 0.70
    moderate_vol = volatility_rank.between(0.20, 0.85)
    direction_score = up_progress - down_progress

    if label_family == "cost_adjusted_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct)
        binary = (continuous >= 0.55).astype(float)
        active = same_role
        boundary = "cost_adjusted_future_abs_return_same_split_role"
    elif label_family == "adverse_excursion_tradeability":
        continuous = direction_score.abs() - adverse_progress.abs() * 0.35
        binary = ((direction_score.abs() >= 0.85) & (adverse_progress.abs() <= 1.25)).astype(float)
        active = same_role
        boundary = "adverse_excursion_limited_directional_progress_same_split_role"
    elif label_family == "open_failed_avoidance_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct) - spread_rank.fillna(0.5) * 0.25
        binary = ((future_abs_return_atr >= 0.65) & low_cost).astype(float)
        active = same_role & low_cost.fillna(False)
        boundary = "cost_and_spread_filtered_tradeability_same_split_role"
    elif label_family == "session_cost_gate_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct)
        binary = ((future_abs_return_atr >= 0.60) & low_cost).astype(float)
        active = same_role & low_cost.fillna(False)
        boundary = "session_cost_gate_tradeability_same_split_role"
    elif label_family == "volatility_stop_timeout_tradeability":
        continuous = direction_score.abs() - volatility_rank.fillna(0.5) * 0.15
        binary = ((direction_score.abs() >= 0.75) & moderate_vol.fillna(False)).astype(float)
        active = same_role & moderate_vol.fillna(False)
        boundary = "volatility_stop_timeout_tradeability_same_split_role"
    else:
        raise ValueError(f"unsupported Wave02 cost/risk/holding label_family: {label_family}")

    result = pd.DataFrame(index=frame.index)
    result["future_return"] = future_return
    result["future_abs_return"] = future_return.abs()
    result["future_abs_return_atr"] = future_abs_return_atr
    result["cost_return_proxy"] = cost_return_proxy
    result["cost_adjusted_abs_return"] = cost_adjusted_abs_return
    result["up_barrier_progress"] = up_progress
    result["down_barrier_progress"] = down_progress
    result["adverse_progress"] = adverse_progress
    result["any_barrier_touch"] = any_barrier_touch.astype(float)
    result["side_label"] = np.sign(future_return).replace(0.0, np.nan)
    result["label_active_mask"] = active.astype(float)
    result["target_continuous"] = continuous.where(active, np.nan)
    result["target_binary_raw"] = binary.where(active, np.nan)
    result["same_role_horizon_ok"] = active.astype(bool)
    result["label_end_primary_split_role"] = frame["primary_split_role"].shift(-horizon_bars)
    result = result.replace([np.inf, -np.inf], np.nan)
    columns = list(result.columns)
    payload = {
        "label_recipe_id": label_recipe_id,
        "label_variant": label_variant,
        "label_family": label_family,
        "horizon_bars": horizon_bars,
        "target_columns": columns,
        "boundary": boundary,
    }
    schema = CostRiskHoldingLabelSchema(
        label_recipe_id=label_recipe_id,
        label_variant=label_variant,
        label_family=label_family,
        horizon_bars=horizon_bars,
        target_columns=columns,
        label_schema_hash=_hash_json(payload),
        boundary=boundary,
    )
    return result[columns], schema
