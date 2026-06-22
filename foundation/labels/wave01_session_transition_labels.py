from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


LABEL_RECIPE_ID = "label_wave01_session_transition_regime_v0"
NY_TZ = ZoneInfo("America/New_York")
BAR_MINUTES = 5.0


@dataclass(frozen=True)
class LabelSchema:
    label_recipe_id: str
    label_surface: str
    session_anchor: str
    transition_window_bars: str
    regime_label: str
    horizon_bars: int
    target_columns: list[str]
    label_schema_hash: str
    boundary: str


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.astype(float) / denominator.replace(0.0, np.nan).astype(float)


def _ny_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for session-transition labels")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def same_role_horizon_mask(frame: pd.DataFrame, horizon_bars: int) -> pd.Series:
    if "primary_split_role" not in frame.columns:
        raise ValueError("missing primary_split_role for Wave01 session-transition label boundary")
    role = frame["primary_split_role"].astype(str)
    return role.shift(-horizon_bars).eq(role)


def _future_extreme(series: pd.Series, horizon_bars: int, reducer: str) -> pd.Series:
    shifted = [series.shift(-step) for step in range(1, horizon_bars + 1)]
    future = pd.concat(shifted, axis=1)
    if reducer == "max":
        return future.max(axis=1)
    if reducer == "min":
        return future.min(axis=1)
    raise ValueError(f"unsupported reducer: {reducer}")


def _true_range(frame: pd.DataFrame) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    prev_close = close.shift(1)
    return pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)


def _parse_pre_post_window(window: str) -> tuple[int, int] | None:
    match = re.match(r"pre_(\d+)_to_post_(\d+)$", window)
    if match:
        return -int(match.group(1)), int(match.group(2))
    match = re.match(r"post_(\d+)_to_post_(\d+)$", window)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.match(r"post_expansion_(\d+)_to_(\d+)$", window)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.match(r"pre_close_(\d+)_to_close$", window)
    if match:
        return -int(match.group(1)), 0
    return None


def _session_mask(frame: pd.DataFrame, session_anchor: str, transition_window_bars: str) -> pd.Series:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    cash_open = 9.5 * 60.0
    cash_close = 16.0 * 60.0
    midday = 12.5 * 60.0

    if session_anchor == "none_session_blind_control":
        return pd.Series(True, index=frame.index)
    if session_anchor in {"ny_cash_open", "pre_to_cash_transition", "active_cash_transition", "post_cash_open"}:
        anchor = cash_open
    elif session_anchor == "ny_cash_close":
        anchor = cash_close
    elif session_anchor == "ny_mid_session":
        anchor = midday
    elif session_anchor == "overnight_to_pre_cash":
        return ((minute >= 4.0 * 60.0) & (minute < cash_open)).astype(bool)
    elif session_anchor == "any_major_transition":
        return ((minute.sub(cash_open).abs() <= 60.0) | (minute.sub(cash_close).abs() <= 60.0)).astype(bool)
    else:
        raise ValueError(f"unsupported session_anchor: {session_anchor}")

    parsed = _parse_pre_post_window(transition_window_bars)
    if parsed is None:
        if transition_window_bars == "cash_midday_block":
            return (minute.sub(midday).abs() <= 90.0).astype(bool)
        if transition_window_bars == "pre_session_block":
            return ((minute >= 4.0 * 60.0) & (minute < cash_open)).astype(bool)
        if transition_window_bars == "none":
            return pd.Series(True, index=frame.index)
        raise ValueError(f"unsupported transition_window_bars: {transition_window_bars}")
    start_bars, end_bars = parsed
    start_minute = anchor + start_bars * BAR_MINUTES
    end_minute = anchor + end_bars * BAR_MINUTES
    return ((minute >= start_minute) & (minute <= end_minute)).astype(bool)


def _surface_targets(
    label_surface: str,
    *,
    future_return: pd.Series,
    future_abs_return_atr: pd.Series,
    up_progress: pd.Series,
    down_progress: pd.Series,
    any_touch: pd.Series,
    no_touch: pd.Series,
) -> tuple[pd.Series, pd.Series, str]:
    direction_score = up_progress - down_progress
    if label_surface == "cash_open_transition_followthrough":
        continuous = future_return
        binary = (future_return > 0.0).astype(float)
        boundary = "cash_open_transition_future_return_same_split_role_session_window"
    elif label_surface == "pre_cash_compression_release":
        continuous = future_abs_return_atr
        binary = any_touch.astype(float)
        boundary = "pre_cash_compression_release_future_abs_move_same_split_role_session_window"
    elif label_surface == "cash_open_failed_breakout_reversion":
        continuous = -future_return
        binary = (future_return < 0.0).astype(float)
        boundary = "cash_open_failed_breakout_reversion_same_split_role_session_window"
    elif label_surface == "mid_session_no_trade_regime":
        continuous = -future_abs_return_atr
        binary = no_touch.astype(float)
        boundary = "mid_session_no_trade_low_movement_same_split_role_session_window"
    elif label_surface == "cash_close_transition_dislocation":
        continuous = direction_score
        binary = (future_return > 0.0).astype(float)
        boundary = "cash_close_transition_dislocation_same_split_role_session_window"
    elif label_surface == "overnight_to_pre_cash_state_shift":
        continuous = future_abs_return_atr
        binary = (future_abs_return_atr > 0.75).astype(float)
        boundary = "overnight_to_pre_cash_state_shift_tradeability_same_split_role_window"
    elif label_surface == "session_blind_control_same_horizon":
        continuous = future_return
        binary = (future_return > 0.0).astype(float)
        boundary = "session_blind_same_horizon_control_same_split_role"
    elif label_surface == "range_expansion_continuation_vs_exhaustion":
        continuous = future_return
        binary = (future_return > 0.0).astype(float)
        boundary = "fast_range_expansion_continuation_same_split_role_session_window"
    elif label_surface == "post_transition_range_acceptance":
        continuous = direction_score.abs()
        binary = any_touch.astype(float)
        boundary = "post_transition_range_acceptance_same_split_role_session_window"
    elif label_surface == "session_transition_volatility_decay":
        continuous = -future_abs_return_atr
        binary = no_touch.astype(float)
        boundary = "session_transition_volatility_decay_same_split_role_session_window"
    else:
        raise ValueError(f"unsupported session-transition label_surface: {label_surface}")
    return continuous.astype(float), binary.astype(float), boundary


def build_wave01_session_transition_labels(frame: pd.DataFrame, label_contract: dict[str, object]) -> tuple[pd.DataFrame, LabelSchema]:
    required = {"high", "low", "close", "primary_split_role"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns for Wave01 session-transition labels: {sorted(missing)}")

    label_surface = str(label_contract["label_surface"])
    session_anchor = str(label_contract["session_anchor"])
    transition_window_bars = str(label_contract["transition_window_bars"])
    regime_label = str(label_contract["regime_label"])
    horizon_bars = int(label_contract["horizon_bars"])
    if horizon_bars <= 0:
        raise ValueError("Wave01 session-transition horizon_bars must be positive")

    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    true_range = _true_range(frame)
    atr = true_range.rolling(48, min_periods=12).mean()
    future_close = close.shift(-horizon_bars)
    future_return = future_close / close - 1.0
    future_high = _future_extreme(high, horizon_bars, "max")
    future_low = _future_extreme(low, horizon_bars, "min")
    up_move = future_high - close
    down_move = close - future_low
    up_progress = _safe_div(up_move, atr)
    down_progress = _safe_div(down_move, atr)
    future_abs_return_atr = _safe_div(future_return.abs(), _safe_div(atr, close))
    any_touch = (up_progress >= 1.0) | (down_progress >= 1.0)
    no_touch = ~any_touch
    session_active = _session_mask(frame, session_anchor, transition_window_bars)
    same_role = same_role_horizon_mask(frame, horizon_bars)

    continuous, binary, boundary = _surface_targets(
        label_surface,
        future_return=future_return,
        future_abs_return_atr=future_abs_return_atr,
        up_progress=up_progress,
        down_progress=down_progress,
        any_touch=any_touch,
        no_touch=no_touch,
    )
    eligible = same_role & session_active
    continuous = continuous.where(eligible, np.nan)
    binary = binary.where(eligible, np.nan)

    result = pd.DataFrame(index=frame.index)
    result["future_return"] = future_return
    result["future_abs_return"] = future_return.abs()
    result["future_abs_return_atr"] = future_abs_return_atr
    result["up_barrier_progress"] = up_progress
    result["down_barrier_progress"] = down_progress
    result["any_barrier_touch"] = any_touch.astype(float)
    result["no_touch"] = no_touch.astype(float)
    result["session_anchor_active"] = session_active.astype(float)
    result["target_continuous"] = continuous
    result["target_binary_raw"] = binary
    result["same_role_horizon_ok"] = eligible.astype(bool)
    result["label_end_primary_split_role"] = frame["primary_split_role"].shift(-horizon_bars)
    result = result.replace([np.inf, -np.inf], np.nan)

    columns = list(result.columns)
    schema_payload = {
        "label_recipe_id": LABEL_RECIPE_ID,
        "label_surface": label_surface,
        "session_anchor": session_anchor,
        "transition_window_bars": transition_window_bars,
        "regime_label": regime_label,
        "horizon_bars": horizon_bars,
        "target_columns": columns,
        "boundary": boundary,
    }
    schema = LabelSchema(
        label_recipe_id=LABEL_RECIPE_ID,
        label_surface=label_surface,
        session_anchor=session_anchor,
        transition_window_bars=transition_window_bars,
        regime_label=regime_label,
        horizon_bars=horizon_bars,
        target_columns=columns,
        label_schema_hash=_hash_json(schema_payload),
        boundary=boundary,
    )
    return result[columns], schema
