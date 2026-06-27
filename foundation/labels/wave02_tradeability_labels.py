from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class LabelSchema:
    label_recipe_id: str
    label_family: str
    horizon_bars: int
    target_columns: list[str]
    label_schema_hash: str
    boundary: str


LABEL_CONFIGS = {
    "label_wave02_tradeability_side_abstain_h6_v0": ("side_abstain_tradeability", 6, 0.65),
    "label_wave02_tradeability_side_abstain_h12_v0": ("side_abstain_tradeability", 12, 0.85),
    "label_wave02_range_break_tradeability_v0": ("range_break_tradeability", 12, 0.90),
    "label_wave02_session_open_tradeability_v0": ("session_open_tradeability", 6, 0.60),
    "label_wave02_no_trade_filter_v0": ("no_trade_filter", 6, 0.35),
    "label_wave02_side_quality_v0": ("side_quality", 12, 0.75),
    "label_wave02_event_continuation_tradeability_v0": ("event_continuation_tradeability", 12, 0.45),
    "label_wave02_adverse_move_avoidance_v0": ("adverse_move_avoidance", 6, 0.50),
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


def _ny_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for Wave02 labels")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for Wave02 label boundary")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def _session_open_mask(frame: pd.DataFrame) -> pd.Series:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    cash_open = 9.5 * 60.0
    return minute.sub(cash_open).abs() <= 60.0


def _event_mask(frame: pd.DataFrame) -> pd.Series:
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    ret_3 = close.pct_change(3).abs()
    range_pct = _safe_div(high - low, close)
    return (ret_3 >= ret_3.rolling(96, min_periods=24).quantile(0.70)) | (
        range_pct >= range_pct.rolling(96, min_periods=24).quantile(0.70)
    )


def _targets(
    label_family: str,
    threshold: float,
    *,
    future_return: pd.Series,
    future_abs_return_atr: pd.Series,
    up_progress: pd.Series,
    down_progress: pd.Series,
    any_touch: pd.Series,
    no_touch: pd.Series,
    current_event_side: pd.Series,
) -> tuple[pd.Series, pd.Series, str]:
    direction_score = up_progress - down_progress
    if label_family == "side_abstain_tradeability":
        continuous = future_abs_return_atr
        binary = (future_abs_return_atr >= threshold).astype(float)
        boundary = "future_abs_return_atr_tradeability_same_split_role"
    elif label_family == "range_break_tradeability":
        continuous = pd.concat([up_progress, down_progress], axis=1).max(axis=1)
        binary = any_touch.astype(float)
        boundary = "future_range_break_touch_same_split_role"
    elif label_family == "session_open_tradeability":
        continuous = future_abs_return_atr
        binary = (future_abs_return_atr >= threshold).astype(float)
        boundary = "cash_open_future_tradeability_same_split_role"
    elif label_family == "no_trade_filter":
        continuous = -future_abs_return_atr
        binary = no_touch.astype(float)
        boundary = "low_future_movement_no_trade_filter_same_split_role"
    elif label_family == "side_quality":
        continuous = direction_score.abs()
        binary = ((direction_score.abs() >= threshold) & any_touch).astype(float)
        boundary = "future_side_quality_progress_same_split_role"
    elif label_family == "event_continuation_tradeability":
        continuous = current_event_side * future_return
        binary = ((current_event_side * future_return > 0.0) & (future_abs_return_atr >= threshold)).astype(float)
        boundary = "event_direction_continuation_same_split_role"
    elif label_family == "adverse_move_avoidance":
        continuous = -pd.concat([up_progress, down_progress], axis=1).min(axis=1)
        binary = (future_abs_return_atr <= threshold).astype(float)
        boundary = "adverse_move_avoidance_same_split_role"
    else:
        raise ValueError(f"unsupported Wave02 label family: {label_family}")
    return continuous.astype(float), binary.astype(float), boundary


def build_wave02_tradeability_labels(frame: pd.DataFrame, label_recipe_id: str) -> tuple[pd.DataFrame, LabelSchema]:
    config = LABEL_CONFIGS.get(label_recipe_id)
    if not config:
        raise ValueError(f"unsupported Wave02 label_recipe_id: {label_recipe_id}")
    label_family, horizon_bars, threshold = config
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    atr = _true_range(frame).rolling(48, min_periods=12).mean()
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    up_progress = _safe_div(future_high - close, atr)
    down_progress = _safe_div(close - future_low, atr)
    future_abs_return_atr = _safe_div(future_return.abs(), _safe_div(atr, close))
    any_touch = (up_progress >= 1.0) | (down_progress >= 1.0)
    no_touch = ~any_touch
    current_event_side = np.sign(close.pct_change(3)).replace(0.0, np.nan).fillna(1.0)
    same_role = same_role_horizon_mask(frame, horizon_bars)
    active_mask = pd.Series(True, index=frame.index)
    if label_family == "session_open_tradeability":
        active_mask = _session_open_mask(frame)
    elif label_family == "event_continuation_tradeability":
        active_mask = _event_mask(frame)
    eligible = same_role & active_mask
    continuous, binary, boundary = _targets(
        label_family,
        threshold,
        future_return=future_return,
        future_abs_return_atr=future_abs_return_atr,
        up_progress=up_progress,
        down_progress=down_progress,
        any_touch=any_touch,
        no_touch=no_touch,
        current_event_side=current_event_side,
    )
    side_label = np.sign(future_return).replace(0.0, np.nan)
    result = pd.DataFrame(index=frame.index)
    result["future_return"] = future_return
    result["future_abs_return"] = future_return.abs()
    result["future_abs_return_atr"] = future_abs_return_atr
    result["up_barrier_progress"] = up_progress
    result["down_barrier_progress"] = down_progress
    result["any_barrier_touch"] = any_touch.astype(float)
    result["no_touch"] = no_touch.astype(float)
    result["side_label"] = side_label
    result["label_active_mask"] = active_mask.astype(float)
    result["target_continuous"] = continuous.where(eligible, np.nan)
    result["target_binary_raw"] = binary.where(eligible, np.nan)
    result["same_role_horizon_ok"] = eligible.astype(bool)
    result["label_end_primary_split_role"] = frame["primary_split_role"].shift(-horizon_bars)
    result = result.replace([np.inf, -np.inf], np.nan)
    columns = list(result.columns)
    payload = {
        "label_recipe_id": label_recipe_id,
        "label_family": label_family,
        "horizon_bars": horizon_bars,
        "target_columns": columns,
        "boundary": boundary,
        "threshold": threshold,
    }
    schema = LabelSchema(
        label_recipe_id=label_recipe_id,
        label_family=label_family,
        horizon_bars=horizon_bars,
        target_columns=columns,
        label_schema_hash=_hash_json(payload),
        boundary=boundary,
    )
    return result[columns], schema
