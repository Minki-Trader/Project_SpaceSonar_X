from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


LABEL_RECIPE_ID = "label_wave01_event_barrier_path_v0"


@dataclass(frozen=True)
class LabelSchema:
    label_recipe_id: str
    label_surface: str
    horizon_bars: int
    timeout_bars: int
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


def _future_first_touch(
    frame: pd.DataFrame,
    *,
    upper_distance: pd.Series,
    lower_distance: pd.Series,
    horizon_bars: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    close = frame["close"].astype(float)
    highs = pd.concat(
        [frame["high"].astype(float).shift(-step).rename(step) for step in range(1, horizon_bars + 1)],
        axis=1,
    )
    lows = pd.concat(
        [frame["low"].astype(float).shift(-step).rename(step) for step in range(1, horizon_bars + 1)],
        axis=1,
    )
    up_hits = highs.ge(close + upper_distance, axis=0)
    down_hits = lows.le(close - lower_distance, axis=0)
    any_up = up_hits.any(axis=1)
    any_down = down_hits.any(axis=1)
    up_step = up_hits.idxmax(axis=1).astype(float)
    down_step = down_hits.idxmax(axis=1).astype(float)
    up_step = up_step.where(any_up, np.nan)
    down_step = down_step.where(any_down, np.nan)
    first_direction = pd.Series(0.0, index=frame.index)
    first_direction = first_direction.mask(any_up & ~any_down, 1.0)
    first_direction = first_direction.mask(any_down & ~any_up, -1.0)
    first_direction = first_direction.mask(any_up & any_down & (up_step < down_step), 1.0)
    first_direction = first_direction.mask(any_up & any_down & (down_step < up_step), -1.0)
    first_direction = first_direction.mask(any_up & any_down & (up_step == down_step), 0.0)
    first_step = pd.concat([up_step, down_step], axis=1).min(axis=1)
    first_step = first_step.where(any_up | any_down, np.nan)
    ambiguous_same_bar = (any_up & any_down & (up_step == down_step)).astype(float)
    return first_direction, first_step, ambiguous_same_bar


def _causal_atr(frame: pd.DataFrame, window: int = 48) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return true_range.rolling(window, min_periods=12).mean()


def _barrier_distances(
    frame: pd.DataFrame,
    *,
    barrier_unit: str,
    upper_barrier: float,
    lower_barrier: float,
) -> tuple[pd.Series, pd.Series, pd.Series, str]:
    atr = _causal_atr(frame)
    if barrier_unit == "atr_multiplier":
        base_distance = atr
        source = "causal_atr_48"
    elif barrier_unit == "price_range_ratio":
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        base_distance = (high - low).rolling(48, min_periods=12).mean()
        source = "causal_rolling_high_low_range_48"
    elif barrier_unit == "mfe_mae_ratio":
        base_distance = atr
        source = "causal_atr_48_for_mfe_mae_ratio_proxy"
    else:
        raise ValueError(f"unsupported Wave01 barrier_unit: {barrier_unit}")
    return base_distance, base_distance * upper_barrier, base_distance * lower_barrier, source


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for Wave01 label horizon boundary")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def _surface_targets(
    label_surface: str,
    *,
    up_progress: pd.Series,
    down_progress: pd.Series,
    path_quality: pd.Series,
    no_touch: pd.Series,
    any_touch: pd.Series,
    first_direction: pd.Series,
    first_step: pd.Series,
    future_abs_return_atr: pd.Series,
) -> tuple[pd.Series, pd.Series, str]:
    direction_score = up_progress - down_progress
    binary: pd.Series
    if label_surface == "symmetric_barrier_touch_or_timeout":
        continuous = direction_score
        binary = (first_direction > 0.0).astype(float).where(any_touch.astype(bool), np.nan)
        boundary = "symmetric_atr_barrier_first_touch_or_timeout_same_split_role_rows"
    elif label_surface == "asymmetric_upside_breakout_barrier":
        continuous = up_progress - 0.5 * down_progress
        binary = (up_progress >= 1.0).astype(float)
        boundary = "asymmetric_upside_breakout_barrier_same_split_role_rows"
    elif label_surface == "mfe_mae_path_quality_ratio":
        continuous = path_quality
        binary = np.nan * path_quality
        boundary = "future_mfe_mae_path_quality_same_split_role_rows"
    elif label_surface == "time_to_event_or_no_touch":
        continuous = no_touch - _safe_div(first_step.fillna(0.0), first_step.fillna(0.0).rolling(1).mean().fillna(1.0) + 1.0)
        binary = no_touch.astype(float)
        boundary = "event_timeout_or_no_touch_same_split_role_rows"
    elif label_surface == "failed_breakout_reversal_barrier":
        continuous = down_progress - up_progress
        binary = (first_direction < 0.0).astype(float).where(any_touch.astype(bool), np.nan)
        boundary = "failed_breakout_reversal_barrier_same_split_role_rows"
    elif label_surface == "compression_then_expansion_barrier":
        continuous = pd.concat([up_progress, down_progress], axis=1).max(axis=1)
        binary = any_touch.astype(float)
        boundary = "compression_then_expansion_any_barrier_touch_same_split_role_rows"
    elif label_surface == "volatility_shock_continuation":
        continuous = future_abs_return_atr
        binary = np.nan * future_abs_return_atr
        boundary = "volatility_shock_continuation_abs_move_same_split_role_rows"
    elif label_surface == "session_transition_barrier_touch":
        continuous = direction_score
        binary = any_touch.astype(float)
        boundary = "session_transition_barrier_touch_same_split_role_rows"
    elif label_surface == "low_volatility_no_touch_regime":
        continuous = no_touch.astype(float)
        binary = no_touch.astype(float)
        boundary = "low_volatility_no_touch_regime_same_split_role_rows"
    elif label_surface == "pullback_to_barrier_mean_reversion":
        continuous = down_progress - 0.75 * up_progress
        binary = (first_direction < 0.0).astype(float).where(any_touch.astype(bool), np.nan)
        boundary = "pullback_to_barrier_mean_reversion_same_split_role_rows"
    elif label_surface == "range_edge_acceptance_rejection":
        continuous = direction_score.abs()
        binary = any_touch.astype(float)
        boundary = "range_edge_acceptance_rejection_same_split_role_rows"
    elif label_surface == "extreme_timeout_path_quality":
        continuous = path_quality - no_touch.astype(float)
        binary = np.nan * path_quality
        boundary = "extreme_timeout_path_quality_same_split_role_rows"
    else:
        raise ValueError(f"unsupported Wave01 label_surface: {label_surface}")
    return continuous.astype(float), binary.astype(float), boundary


def build_wave01_labels(frame: pd.DataFrame, label_contract: dict[str, Any]) -> tuple[pd.DataFrame, LabelSchema]:
    required = {"high", "low", "close", "primary_split_role"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns for Wave01 labels: {sorted(missing)}")

    label_surface = str(label_contract["label_surface"])
    horizon_bars = int(label_contract["horizon_bars"])
    timeout_bars = int(label_contract.get("timeout_bars", horizon_bars))
    upper_barrier = float(label_contract["upper_barrier"])
    lower_barrier = float(label_contract["lower_barrier"])
    barrier_unit = str(label_contract.get("barrier_unit", "atr_multiplier"))
    if horizon_bars <= 0 or timeout_bars <= 0:
        raise ValueError("Wave01 horizon_bars and timeout_bars must be positive")

    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    base_distance, upper_distance, lower_distance, barrier_distance_source = _barrier_distances(
        frame,
        barrier_unit=barrier_unit,
        upper_barrier=upper_barrier,
        lower_barrier=lower_barrier,
    )
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    up_move = future_high - close
    down_move = close - future_low
    up_progress = _safe_div(up_move, upper_distance)
    down_progress = _safe_div(down_move, lower_distance)
    any_touch = (up_progress >= 1.0) | (down_progress >= 1.0)
    no_touch = ~any_touch
    first_direction, first_step, ambiguous_same_bar = _future_first_touch(
        frame,
        upper_distance=upper_distance,
        lower_distance=lower_distance,
        horizon_bars=horizon_bars,
    )
    path_quality = up_progress - down_progress.clip(lower=0.0) * 0.75
    future_abs_return_atr = _safe_div(future_return.abs(), _safe_div(base_distance, close))
    same_role = same_role_horizon_mask(frame, horizon_bars)

    continuous, binary, boundary = _surface_targets(
        label_surface,
        up_progress=up_progress,
        down_progress=down_progress,
        path_quality=path_quality,
        no_touch=no_touch,
        any_touch=any_touch,
        first_direction=first_direction,
        first_step=first_step,
        future_abs_return_atr=future_abs_return_atr,
    )

    result = pd.DataFrame(index=frame.index)
    result["future_return"] = future_return
    result["future_abs_return"] = future_return.abs()
    result["future_up_move_barrier_base"] = _safe_div(up_move, base_distance)
    result["future_down_move_barrier_base"] = _safe_div(down_move, base_distance)
    result["upper_barrier_atr_multiple"] = upper_barrier
    result["lower_barrier_atr_multiple"] = lower_barrier
    result["barrier_base_distance"] = base_distance
    result["up_barrier_distance_price"] = upper_distance
    result["down_barrier_distance_price"] = lower_distance
    result["up_barrier_progress"] = up_progress
    result["down_barrier_progress"] = down_progress
    result["first_touch_direction"] = first_direction
    result["first_touch_step"] = first_step
    result["ambiguous_same_bar_touch"] = ambiguous_same_bar
    result["any_barrier_touch"] = any_touch.astype(float)
    result["no_touch"] = no_touch.astype(float)
    result["path_quality_score"] = path_quality
    result["target_continuous"] = continuous
    result["target_binary_raw"] = binary
    result["same_role_horizon_ok"] = same_role.astype(bool)
    result["label_end_primary_split_role"] = frame["primary_split_role"].shift(-horizon_bars)
    result = result.replace([np.inf, -np.inf], np.nan)

    columns = list(result.columns)
    schema_payload = {
        "label_recipe_id": LABEL_RECIPE_ID,
        "label_surface": label_surface,
        "horizon_bars": horizon_bars,
        "timeout_bars": timeout_bars,
        "barrier_unit": barrier_unit,
        "barrier_distance_source": barrier_distance_source,
        "upper_barrier": upper_barrier,
        "lower_barrier": lower_barrier,
        "target_columns": columns,
        "boundary": boundary,
    }
    schema = LabelSchema(
        label_recipe_id=LABEL_RECIPE_ID,
        label_surface=label_surface,
        horizon_bars=horizon_bars,
        timeout_bars=timeout_bars,
        target_columns=columns,
        label_schema_hash=_hash_json(schema_payload),
        boundary=boundary,
    )
    return result[columns], schema
