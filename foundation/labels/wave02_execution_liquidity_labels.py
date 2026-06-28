from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ExecutionLiquidityLabelSchema:
    label_recipe_id: str
    label_variant: str
    label_family: str
    horizon_bars: int
    target_columns: list[str]
    label_schema_hash: str
    boundary: str


LABEL_FAMILY_BY_VARIANT = {
    "session_liquidity_tradeable_h6": "session_liquidity_tradeability",
    "high_spread_abstain_h8": "high_spread_abstain_tradeability",
    "open_failed_prevention_h6": "open_failed_prevention_tradeability",
    "session_transition_close_h10": "session_transition_close_tradeability",
    "volatility_liquidity_gate_h12": "volatility_liquidity_gate_tradeability",
    "low_liquidity_timeout_h6": "low_liquidity_timeout_tradeability",
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


def _ny_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for Wave02 execution/liquidity labels")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for Wave02 execution/liquidity label boundary")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def _session_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    cash_open = 9.5 * 60.0
    cash_close = 16.0 * 60.0
    return {
        "cash": (minute >= cash_open) & (minute <= cash_close),
        "cash_edge": (minute.sub(cash_open).abs() <= 60.0) | (minute.sub(cash_close).abs() <= 60.0),
        "cash_close_edge": minute.sub(cash_close).abs() <= 75.0,
    }


def build_wave02_execution_liquidity_labels(
    frame: pd.DataFrame,
    label_recipe_id: str,
    label_variant: str,
) -> tuple[pd.DataFrame, ExecutionLiquidityLabelSchema]:
    label_family = LABEL_FAMILY_BY_VARIANT.get(label_variant)
    if label_family is None:
        raise ValueError(f"unsupported Wave02 execution/liquidity label_variant: {label_variant}")
    horizon_bars = _horizon_from_variant(label_variant)
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    spread = frame["spread_points"].astype(float)
    tick_volume = frame["tick_volume"].astype(float)
    atr = _true_range(frame).rolling(48, min_periods=12).mean()
    atr_pct = _safe_div(atr, close)
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    up_progress = _safe_div(future_high - close, atr)
    down_progress = _safe_div(close - future_low, atr)
    direction_score = up_progress - down_progress
    adverse_progress = pd.concat([up_progress, down_progress], axis=1).min(axis=1)
    future_abs_return_atr = _safe_div(future_return.abs(), atr_pct)
    cost_return_proxy = _safe_div(spread / 100.0, close)
    cost_adjusted_abs_return = future_return.abs() - cost_return_proxy
    any_barrier_touch = (up_progress >= 1.0) | (down_progress >= 1.0)
    same_role = same_role_horizon_mask(frame, horizon_bars)
    sessions = _session_masks(frame)
    spread_rank = spread.rolling(144, min_periods=36).rank(pct=True)
    volume_rank = tick_volume.rolling(144, min_periods=36).rank(pct=True)
    volatility_rank = atr_pct.rolling(144, min_periods=36).rank(pct=True)
    low_spread = spread_rank <= 0.70
    high_spread = spread_rank >= 0.70
    liquid_enough = volume_rank >= 0.25
    low_liquidity = volume_rank <= 0.35
    moderate_vol = volatility_rank.between(0.20, 0.88)

    if label_family == "session_liquidity_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct)
        binary = ((future_abs_return_atr >= 0.60) & low_spread.fillna(False) & liquid_enough.fillna(False)).astype(float)
        active = same_role & sessions["cash"].fillna(False) & low_spread.fillna(False) & liquid_enough.fillna(False)
        boundary = "cash_session_low_spread_liquid_tradeability_same_split_role"
    elif label_family == "high_spread_abstain_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct) - spread_rank.fillna(0.5) * 0.35
        binary = ((future_abs_return_atr >= 0.70) & (~high_spread.fillna(False))).astype(float)
        active = same_role
        boundary = "high_spread_abstain_adjusted_tradeability_same_split_role"
    elif label_family == "open_failed_prevention_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct) - spread_rank.fillna(0.5) * 0.25 + volume_rank.fillna(0.5) * 0.10
        binary = ((future_abs_return_atr >= 0.62) & low_spread.fillna(False) & liquid_enough.fillna(False)).astype(float)
        active = same_role & low_spread.fillna(False) & liquid_enough.fillna(False)
        boundary = "open_failed_prevention_spread_liquidity_filtered_tradeability_same_split_role"
    elif label_family == "session_transition_close_tradeability":
        continuous = direction_score.abs() - adverse_progress.abs() * 0.20
        binary = ((direction_score.abs() >= 0.75) & sessions["cash_close_edge"].fillna(False)).astype(float)
        active = same_role & sessions["cash_edge"].fillna(False)
        boundary = "session_transition_close_directional_progress_same_split_role"
    elif label_family == "volatility_liquidity_gate_tradeability":
        continuous = direction_score.abs() - volatility_rank.fillna(0.5) * 0.15 - spread_rank.fillna(0.5) * 0.15
        binary = ((direction_score.abs() >= 0.75) & moderate_vol.fillna(False) & liquid_enough.fillna(False)).astype(float)
        active = same_role & moderate_vol.fillna(False) & liquid_enough.fillna(False)
        boundary = "volatility_liquidity_gated_directional_progress_same_split_role"
    elif label_family == "low_liquidity_timeout_tradeability":
        continuous = _safe_div(cost_adjusted_abs_return, atr_pct) - low_liquidity.fillna(False).astype(float) * 0.30
        binary = ((future_abs_return_atr >= 0.58) & (~low_liquidity.fillna(False))).astype(float)
        active = same_role
        boundary = "low_liquidity_timeout_abstain_adjusted_tradeability_same_split_role"
    else:
        raise ValueError(f"unsupported Wave02 execution/liquidity label_family: {label_family}")

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
    schema = ExecutionLiquidityLabelSchema(
        label_recipe_id=label_recipe_id,
        label_variant=label_variant,
        label_family=label_family,
        horizon_bars=horizon_bars,
        target_columns=columns,
        label_schema_hash=_hash_json(payload),
        boundary=boundary,
    )
    return result[columns], schema
