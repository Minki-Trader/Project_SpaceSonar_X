from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureSchema:
    feature_recipe_id: str
    input_family: str
    feature_columns: list[str]
    feature_order_hash: str
    feature_schema_hash: str
    boundary: str


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.astype(float) / denominator.replace(0.0, np.nan).astype(float)


def _base_features(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    spread = frame["spread_points"].astype(float)
    tick_volume = frame["tick_volume"].astype(float)

    result = pd.DataFrame(index=frame.index)
    result["ret_1"] = close.pct_change(1)
    result["ret_3"] = close.pct_change(3)
    result["ret_6"] = close.pct_change(6)
    result["hl_range_pct"] = _safe_div(high - low, close)
    result["body_pct"] = _safe_div(close - open_, open_)
    result["upper_wick_pct"] = _safe_div(high - pd.concat([open_, close], axis=1).max(axis=1), close)
    result["lower_wick_pct"] = _safe_div(pd.concat([open_, close], axis=1).min(axis=1) - low, close)
    result["spread_scaled"] = spread / 1000.0
    result["tick_volume_log1p"] = np.log1p(tick_volume.clip(lower=0.0))
    result["rolling_ret_mean_12"] = result["ret_1"].rolling(12, min_periods=6).mean()
    result["rolling_ret_std_12"] = result["ret_1"].rolling(12, min_periods=6).std()
    result["rolling_range_mean_12"] = result["hl_range_pct"].rolling(12, min_periods=6).mean()
    result["rolling_spread_mean_12"] = result["spread_scaled"].rolling(12, min_periods=6).mean()
    return result


def _add_multiscale_features(base: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    result = base.copy()
    close = frame["close"].astype(float)
    range_pct = base["hl_range_pct"]
    ret_1 = base["ret_1"]
    tick_volume = frame["tick_volume"].astype(float)
    for window in (12, 24, 48, 96, 288):
        result[f"ret_{window}"] = close.pct_change(window)
        result[f"ret_mean_{window}"] = ret_1.rolling(window, min_periods=max(6, window // 4)).mean()
        result[f"ret_std_{window}"] = ret_1.rolling(window, min_periods=max(6, window // 4)).std()
        result[f"range_mean_{window}"] = range_pct.rolling(window, min_periods=max(6, window // 4)).mean()
        sma = close.rolling(window, min_periods=max(6, window // 4)).mean()
        result[f"close_to_sma_{window}"] = _safe_div(close - sma, sma)
        vol_mean = tick_volume.rolling(window, min_periods=max(6, window // 4)).mean()
        vol_std = tick_volume.rolling(window, min_periods=max(6, window // 4)).std()
        result[f"tick_volume_z_{window}"] = _safe_div(tick_volume - vol_mean, vol_std)
    return result


def _add_regime_features(base: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    result = base.copy()
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    ret_1 = base["ret_1"]
    range_pct = base["hl_range_pct"]
    for window in (48, 96, 288, 576):
        rolling_close = close.rolling(window, min_periods=max(12, window // 6))
        mean = rolling_close.mean()
        std = rolling_close.std()
        result[f"close_z_{window}"] = _safe_div(close - mean, std)
        result[f"drawdown_from_roll_high_{window}"] = _safe_div(close - high.rolling(window, min_periods=max(12, window // 6)).max(), close)
        result[f"drawup_from_roll_low_{window}"] = _safe_div(close - low.rolling(window, min_periods=max(12, window // 6)).min(), close)
        result[f"volatility_{window}"] = ret_1.rolling(window, min_periods=max(12, window // 6)).std()
        result[f"range_regime_{window}"] = range_pct.rolling(window, min_periods=max(12, window // 6)).mean()
    result["volatility_ratio_48_288"] = _safe_div(result["volatility_48"], result["volatility_288"])
    result["range_ratio_48_288"] = _safe_div(result["range_regime_48"], result["range_regime_288"])
    result["trend_ratio_48_288"] = _safe_div(close.pct_change(48), close.pct_change(288).abs())
    return result


def _rendered_clock_features(frame: pd.DataFrame) -> pd.DataFrame:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for rendered clock features")
    timestamp = pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True)
    minute_of_day = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    day_of_week = timestamp.dt.dayofweek.astype(float)
    result = pd.DataFrame(index=frame.index)
    result["rendered_minute_sin"] = np.sin(2.0 * np.pi * minute_of_day / 1440.0)
    result["rendered_minute_cos"] = np.cos(2.0 * np.pi * minute_of_day / 1440.0)
    result["rendered_dow_sin"] = np.sin(2.0 * np.pi * day_of_week / 7.0)
    result["rendered_dow_cos"] = np.cos(2.0 * np.pi * day_of_week / 7.0)
    result["rendered_hour"] = timestamp.dt.hour.astype(float)
    result["rendered_is_monday"] = (day_of_week == 0).astype(float)
    result["rendered_is_friday"] = (day_of_week == 4).astype(float)
    result["spread_scaled"] = frame["spread_points"].astype(float) / 1000.0
    result["tick_volume_log1p"] = np.log1p(frame["tick_volume"].astype(float).clip(lower=0.0))
    return result


def build_wave0_features(frame: pd.DataFrame, input_family: str) -> tuple[pd.DataFrame, FeatureSchema]:
    required = {"open", "high", "low", "close", "tick_volume", "spread_points"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns for Wave0 features: {sorted(missing)}")

    base = _base_features(frame)
    if input_family == "price_only_m5_returns_ranges_volatility":
        features = base
        boundary = "right_aligned_closed_bar_price_only_current_and_past_bars"
    elif input_family == "multiscale_us100_m5_aggregates":
        features = _add_multiscale_features(base, frame)
        boundary = "right_aligned_closed_bar_multiscale_us100_only_current_and_past_bars"
    elif input_family == "causal_rolling_regime_context":
        features = _add_regime_features(_add_multiscale_features(base, frame), frame)
        boundary = "right_aligned_closed_bar_rolling_regime_current_and_past_bars"
    elif input_family == "session_calendar_state":
        features = _rendered_clock_features(frame)
        boundary = "rendered_clock_state_only_no_verified_us_session_semantics_claim"
    else:
        raise ValueError(f"unsupported Wave0 input_family: {input_family}")

    features = features.replace([np.inf, -np.inf], np.nan)
    columns = list(features.columns)
    schema_payload = {
        "feature_recipe_id": "feature_wave0_us100_closedbar_price_session_regime_v0",
        "input_family": input_family,
        "feature_columns": columns,
        "boundary": boundary,
    }
    schema = FeatureSchema(
        feature_recipe_id="feature_wave0_us100_closedbar_price_session_regime_v0",
        input_family=input_family,
        feature_columns=columns,
        feature_order_hash=hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
        feature_schema_hash=_hash_json(schema_payload),
        boundary=boundary,
    )
    return features[columns], schema
