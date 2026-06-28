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
    "label_wave03_compression_break_reversal_h6_v0": ("compression_break_reversal", 6, 0.25),
    "label_wave03_compression_break_reversal_h8_v0": ("compression_break_reversal", 8, 0.30),
    "label_wave03_compression_release_continuation_h6_v0": ("compression_release_continuation", 6, 0.25),
    "label_wave03_compression_release_continuation_h12_v0": ("compression_release_continuation", 12, 0.35),
    "label_wave03_expansion_exhaustion_reversal_h8_v0": ("expansion_exhaustion_reversal", 8, 0.30),
    "label_wave03_expansion_exhaustion_reversal_h12_v0": ("expansion_exhaustion_reversal", 12, 0.35),
    "label_wave03_expansion_followthrough_h6_v0": ("expansion_followthrough", 6, 0.25),
    "label_wave03_expansion_followthrough_h12_v0": ("expansion_followthrough", 12, 0.35),
    "label_wave03_vol_state_tradeability_h8_v0": ("vol_state_tradeability", 8, 0.65),
    "label_wave03_vol_state_tradeability_h12_v0": ("vol_state_tradeability", 12, 0.75),
    "label_wave03_range_expansion_adverse_move_h6_v0": ("range_expansion_adverse_move", 6, 0.45),
    "label_wave03_range_expansion_adverse_move_h8_v0": ("range_expansion_adverse_move", 8, 0.55),
    "label_wave03_session_open_reversal_h6_v0": ("session_open_reversal", 6, 0.25),
    "label_wave03_session_open_continuation_h8_v0": ("session_open_continuation", 8, 0.30),
    "label_wave03_low_vol_breakout_h6_v0": ("low_vol_breakout", 6, 0.75),
    "label_wave03_low_vol_false_break_reversal_h8_v0": ("low_vol_false_break_reversal", 8, 0.30),
    "label_wave03_high_vol_mean_revert_h12_v0": ("high_vol_mean_revert", 12, 0.35),
    "label_wave03_high_vol_momentum_h12_v0": ("high_vol_momentum", 12, 0.35),
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
        raise ValueError("missing us100_bar_close_time_utc_rendered for Wave03 labels")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for Wave03 label boundary")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def _session_open_mask(frame: pd.DataFrame) -> pd.Series:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    cash_open = 9.5 * 60.0
    return minute.sub(cash_open).abs() <= 90.0


def _volatility_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    true_range = _true_range(frame)
    atr_48 = true_range.rolling(48, min_periods=12).mean()
    atr_pct = _safe_div(atr_48, close)
    range_pct = _safe_div(high - low, close)
    ret_3_abs = close.pct_change(3).abs()
    range_mean_12 = range_pct.rolling(12, min_periods=4).mean()
    range_mean_48 = range_pct.rolling(48, min_periods=12).mean()
    compression_ratio = _safe_div(range_mean_12, range_mean_48)
    atr_rank = atr_pct.rolling(288, min_periods=72).rank(pct=True)
    expansion = (range_pct >= range_pct.rolling(96, min_periods=24).quantile(0.65)) | (
        ret_3_abs >= ret_3_abs.rolling(96, min_periods=24).quantile(0.65)
    )
    return {
        "compression": compression_ratio <= 0.95,
        "expansion": expansion,
        "low_vol": atr_rank <= 0.40,
        "high_vol": atr_rank >= 0.60,
        "all_vol_state": pd.Series(True, index=frame.index),
    }


def _active_mask(label_family: str, frame: pd.DataFrame) -> pd.Series:
    masks = _volatility_masks(frame)
    if label_family.startswith("compression_"):
        return masks["compression"]
    if label_family.startswith("expansion_") or label_family.startswith("range_expansion_"):
        return masks["expansion"]
    if label_family.startswith("session_open_"):
        return _session_open_mask(frame)
    if label_family.startswith("low_vol_"):
        return masks["low_vol"]
    if label_family.startswith("high_vol_"):
        return masks["high_vol"]
    return masks["all_vol_state"]


def _targets(
    label_family: str,
    threshold: float,
    *,
    future_return: pd.Series,
    future_abs_return_atr: pd.Series,
    up_progress: pd.Series,
    down_progress: pd.Series,
    any_touch: pd.Series,
    current_side: pd.Series,
) -> tuple[pd.Series, pd.Series, str]:
    future_return_atr = np.sign(future_return).replace(0.0, np.nan).fillna(0.0) * future_abs_return_atr
    continuation_atr = current_side * future_return_atr
    reversal_atr = -current_side * future_return_atr
    range_break_progress = pd.concat([up_progress, down_progress], axis=1).max(axis=1)

    if label_family in {
        "compression_break_reversal",
        "expansion_exhaustion_reversal",
        "session_open_reversal",
        "low_vol_false_break_reversal",
        "high_vol_mean_revert",
    }:
        continuous = reversal_atr
        binary = (reversal_atr >= threshold).astype(float)
        boundary = f"{label_family}_future_reversal_same_split_role"
    elif label_family in {
        "compression_release_continuation",
        "expansion_followthrough",
        "session_open_continuation",
        "high_vol_momentum",
    }:
        continuous = continuation_atr
        binary = (continuation_atr >= threshold).astype(float)
        boundary = f"{label_family}_future_continuation_same_split_role"
    elif label_family == "vol_state_tradeability":
        continuous = future_abs_return_atr
        binary = (future_abs_return_atr >= threshold).astype(float)
        boundary = "volatility_state_future_abs_return_tradeability_same_split_role"
    elif label_family == "range_expansion_adverse_move":
        continuous = -future_abs_return_atr
        binary = (future_abs_return_atr <= threshold).astype(float)
        boundary = "range_expansion_adverse_move_avoidance_same_split_role"
    elif label_family == "low_vol_breakout":
        continuous = range_break_progress
        binary = ((range_break_progress >= threshold) | any_touch).astype(float)
        boundary = "low_vol_future_range_breakout_same_split_role"
    else:
        raise ValueError(f"unsupported Wave03 label family: {label_family}")
    return continuous.astype(float), binary.astype(float), boundary


def build_wave03_volatility_state_labels(frame: pd.DataFrame, label_recipe_id: str) -> tuple[pd.DataFrame, LabelSchema]:
    config = LABEL_CONFIGS.get(label_recipe_id)
    if not config:
        raise ValueError(f"unsupported Wave03 label_recipe_id: {label_recipe_id}")
    label_family, horizon_bars, threshold = config
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    atr = _true_range(frame).rolling(48, min_periods=12).mean()
    atr_pct = _safe_div(atr, close)
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    up_progress = _safe_div(future_high - close, atr)
    down_progress = _safe_div(close - future_low, atr)
    future_abs_return_atr = _safe_div(future_return.abs(), atr_pct)
    any_touch = (up_progress >= 1.0) | (down_progress >= 1.0)
    current_side = np.sign(close.pct_change(3)).replace(0.0, np.nan).fillna(1.0)
    same_role = same_role_horizon_mask(frame, horizon_bars)
    active_mask = _active_mask(label_family, frame)
    eligible = same_role & active_mask
    continuous, binary, boundary = _targets(
        label_family,
        threshold,
        future_return=future_return,
        future_abs_return_atr=future_abs_return_atr,
        up_progress=up_progress,
        down_progress=down_progress,
        any_touch=any_touch,
        current_side=current_side,
    )
    side_label = np.sign(future_return).replace(0.0, np.nan)
    result = pd.DataFrame(index=frame.index)
    result["future_return"] = future_return
    result["future_abs_return"] = future_return.abs()
    result["future_abs_return_atr"] = future_abs_return_atr
    result["up_barrier_progress"] = up_progress
    result["down_barrier_progress"] = down_progress
    result["any_barrier_touch"] = any_touch.astype(float)
    result["current_transition_side"] = current_side.astype(float)
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
