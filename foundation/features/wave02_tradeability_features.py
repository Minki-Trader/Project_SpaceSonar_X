from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class FeatureSchema:
    feature_recipe_id: str
    feature_family: str
    feature_columns: list[str]
    feature_order_hash: str
    feature_schema_hash: str
    boundary: str


FEATURE_FAMILY_BY_RECIPE = {
    "feature_wave02_session_range_tradeability_v0": "session_range_tradeability",
    "feature_wave02_range_compression_release_v0": "range_compression_release",
    "feature_wave02_session_transition_range_v0": "session_transition_range",
    "feature_wave02_multiscale_path_quality_v0": "multiscale_path_quality",
    "feature_wave02_event_session_range_v0": "event_session_range",
}


FEATURE_GROUPS = {
    "session_range_tradeability": [
        "session_",
        "ret_",
        "range_",
        "atr_",
        "volume_",
        "spread_",
        "position_",
    ],
    "range_compression_release": [
        "ret_",
        "range_",
        "atr_",
        "compression_",
        "breakout_",
        "position_",
    ],
    "session_transition_range": [
        "session_",
        "transition_",
        "range_",
        "atr_",
        "ret_",
        "position_",
    ],
    "multiscale_path_quality": [
        "ret_",
        "path_",
        "range_",
        "atr_",
        "position_",
        "volume_",
    ],
    "event_session_range": [
        "event_",
        "session_",
        "transition_",
        "ret_",
        "range_",
        "atr_",
        "volume_",
    ],
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


def _ny_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for Wave02 features")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def _session_features(frame: pd.DataFrame) -> pd.DataFrame:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    dow = timestamp.dt.dayofweek.astype(float)
    cash_open = 9.5 * 60.0
    cash_close = 16.0 * 60.0
    midday = 12.5 * 60.0
    result = pd.DataFrame(index=frame.index)
    result["session_minute_sin"] = np.sin(2.0 * np.pi * minute / 1440.0)
    result["session_minute_cos"] = np.cos(2.0 * np.pi * minute / 1440.0)
    result["session_dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    result["session_dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    result["session_minutes_from_cash_open"] = (minute - cash_open) / 390.0
    result["session_minutes_to_cash_close"] = (cash_close - minute) / 390.0
    result["session_is_pre_cash"] = ((minute >= 4.0 * 60.0) & (minute < cash_open)).astype(float)
    result["session_is_cash"] = ((minute >= cash_open) & (minute <= cash_close)).astype(float)
    result["session_is_after_cash"] = ((minute > cash_close) & (minute <= 20.0 * 60.0)).astype(float)
    result["transition_cash_open_60m"] = (minute.sub(cash_open).abs() <= 60.0).astype(float)
    result["transition_cash_close_60m"] = (minute.sub(cash_close).abs() <= 60.0).astype(float)
    result["transition_midday_90m"] = (minute.sub(midday).abs() <= 90.0).astype(float)
    return result


def _base_features(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    open_ = frame["open"].astype(float)
    tick_volume = frame["tick_volume"].astype(float)
    spread = frame["spread_points"].astype(float)
    true_range = _true_range(frame)
    atr_48 = true_range.rolling(48, min_periods=12).mean()

    result = pd.DataFrame(index=frame.index)
    for window in [1, 3, 6, 12, 24, 48, 96]:
        result[f"ret_{window}"] = close.pct_change(window)
        min_periods = min(window, max(1, max(2, window // 4)))
        result[f"path_abs_ret_mean_{window}"] = result["ret_1"].abs().rolling(window, min_periods=min_periods).mean()
    result["range_pct"] = _safe_div(high - low, close)
    result["range_body_pct"] = _safe_div((close - open_).abs(), close)
    result["range_upper_wick_pct"] = _safe_div(high - pd.concat([open_, close], axis=1).max(axis=1), close)
    result["range_lower_wick_pct"] = _safe_div(pd.concat([open_, close], axis=1).min(axis=1) - low, close)
    for window in [12, 48, 144]:
        result[f"range_mean_{window}"] = result["range_pct"].rolling(window, min_periods=max(3, window // 4)).mean()
        result[f"range_std_{window}"] = result["range_pct"].rolling(window, min_periods=max(3, window // 4)).std()
    result["atr_48_pct"] = _safe_div(atr_48, close)
    result["compression_range_12_vs_48"] = _safe_div(result["range_mean_12"], result["range_mean_48"])
    result["compression_range_48_vs_144"] = _safe_div(result["range_mean_48"], result["range_mean_144"])
    result["volume_z_48"] = _safe_div(tick_volume - tick_volume.rolling(48, min_periods=12).mean(), tick_volume.rolling(48, min_periods=12).std())
    result["spread_scaled"] = spread / 1000.0
    high_48 = high.rolling(48, min_periods=12).max()
    low_48 = low.rolling(48, min_periods=12).min()
    result["position_close_in_48_range"] = _safe_div(close - low_48, high_48 - low_48)
    result["breakout_up_48"] = _safe_div(close - high_48.shift(1), atr_48)
    result["breakout_down_48"] = _safe_div(low_48.shift(1) - close, atr_48)
    result["event_abs_ret_3_z_96"] = _safe_div(result["ret_3"].abs() - result["ret_3"].abs().rolling(96, min_periods=24).mean(), result["ret_3"].abs().rolling(96, min_periods=24).std())
    result["event_range_z_96"] = _safe_div(result["range_pct"] - result["range_pct"].rolling(96, min_periods=24).mean(), result["range_pct"].rolling(96, min_periods=24).std())
    return result


def build_wave02_tradeability_features(frame: pd.DataFrame, feature_recipe_id: str) -> tuple[pd.DataFrame, FeatureSchema]:
    feature_family = FEATURE_FAMILY_BY_RECIPE.get(feature_recipe_id)
    if not feature_family:
        raise ValueError(f"unsupported Wave02 feature_recipe_id: {feature_recipe_id}")
    features = pd.concat([_base_features(frame), _session_features(frame)], axis=1)
    prefixes = FEATURE_GROUPS[feature_family]
    columns = [column for column in features.columns if any(column.startswith(prefix) for prefix in prefixes)]
    features = features[columns].replace([np.inf, -np.inf], np.nan)
    boundary = "right_aligned_closed_bar_us100_wave02_tradeability_features_no_aux_symbols"
    payload = {
        "feature_recipe_id": feature_recipe_id,
        "feature_family": feature_family,
        "feature_columns": columns,
        "boundary": boundary,
        "feature_count_policy": "declared_per_run_no_fixed_legacy_count",
    }
    schema = FeatureSchema(
        feature_recipe_id=feature_recipe_id,
        feature_family=feature_family,
        feature_columns=columns,
        feature_order_hash=hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
        feature_schema_hash=_hash_json(payload),
        boundary=boundary,
    )
    return features, schema
