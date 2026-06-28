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
    "feature_wave03_atr_compression_session_state_v0": "atr_compression_session_state",
    "feature_wave03_range_percentile_path_quality_v0": "range_percentile_path_quality",
    "feature_wave03_realized_vol_regime_transition_v0": "realized_vol_regime_transition",
    "feature_wave03_multiscale_compression_release_v0": "multiscale_compression_release",
    "feature_wave03_session_open_expansion_state_v0": "session_open_expansion_state",
    "feature_wave03_drawdown_rebound_vol_state_v0": "drawdown_rebound_vol_state",
}


FEATURE_GROUPS = {
    "atr_compression_session_state": [
        "atr_",
        "compression_",
        "session_",
        "ret_",
        "range_",
        "spread_",
    ],
    "range_percentile_path_quality": [
        "range_",
        "path_",
        "position_",
        "breakout_",
        "ret_",
        "volume_",
    ],
    "realized_vol_regime_transition": [
        "realized_vol_",
        "volatility_",
        "ret_",
        "range_",
        "session_",
        "atr_",
    ],
    "multiscale_compression_release": [
        "compression_",
        "breakout_",
        "range_",
        "ret_",
        "path_",
        "position_",
    ],
    "session_open_expansion_state": [
        "session_",
        "expansion_",
        "range_",
        "ret_",
        "atr_",
        "volume_",
    ],
    "drawdown_rebound_vol_state": [
        "drawdown_",
        "rebound_",
        "realized_vol_",
        "volatility_",
        "ret_",
        "range_",
        "atr_",
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


def _rolling_rank(series: pd.Series, window: int, *, min_periods: int) -> pd.Series:
    return series.rolling(window, min_periods=min_periods).rank(pct=True)


def _ny_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for Wave03 features")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def _session_features(frame: pd.DataFrame) -> pd.DataFrame:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    dow = timestamp.dt.dayofweek.astype(float)
    cash_open = 9.5 * 60.0
    cash_close = 16.0 * 60.0
    result = pd.DataFrame(index=frame.index)
    result["session_minute_sin"] = np.sin(2.0 * np.pi * minute / 1440.0)
    result["session_minute_cos"] = np.cos(2.0 * np.pi * minute / 1440.0)
    result["session_dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    result["session_dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    result["session_minutes_from_cash_open"] = (minute - cash_open) / 390.0
    result["session_minutes_to_cash_close"] = (cash_close - minute) / 390.0
    result["session_is_cash"] = ((minute >= cash_open) & (minute <= cash_close)).astype(float)
    result["session_is_open_60m"] = (minute.sub(cash_open).abs() <= 60.0).astype(float)
    result["session_is_open_90m"] = (minute.sub(cash_open).abs() <= 90.0).astype(float)
    result["session_is_close_60m"] = (minute.sub(cash_close).abs() <= 60.0).astype(float)
    return result


def _base_features(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    open_ = frame["open"].astype(float)
    tick_volume = frame["tick_volume"].astype(float)
    spread = frame["spread_points"].astype(float)
    true_range = _true_range(frame)
    atr_12 = true_range.rolling(12, min_periods=4).mean()
    atr_48 = true_range.rolling(48, min_periods=12).mean()
    atr_144 = true_range.rolling(144, min_periods=36).mean()

    result = pd.DataFrame(index=frame.index)
    result["ret_1"] = close.pct_change(1)
    for window in [3, 6, 8, 12, 24, 48, 96]:
        result[f"ret_{window}"] = close.pct_change(window)
        abs_path = result["ret_1"].abs().rolling(window, min_periods=max(2, window // 4)).sum()
        result[f"path_efficiency_{window}"] = _safe_div(result[f"ret_{window}"].abs(), abs_path)
        result[f"path_abs_ret_mean_{window}"] = result["ret_1"].abs().rolling(window, min_periods=max(2, window // 4)).mean()

    result["range_pct"] = _safe_div(high - low, close)
    result["range_body_pct"] = _safe_div((close - open_).abs(), close)
    result["range_upper_wick_pct"] = _safe_div(high - pd.concat([open_, close], axis=1).max(axis=1), close)
    result["range_lower_wick_pct"] = _safe_div(pd.concat([open_, close], axis=1).min(axis=1) - low, close)
    for window in [12, 48, 144, 288]:
        result[f"range_mean_{window}"] = result["range_pct"].rolling(window, min_periods=max(4, window // 4)).mean()
        result[f"range_std_{window}"] = result["range_pct"].rolling(window, min_periods=max(4, window // 4)).std()
        result[f"range_rank_{window}"] = _rolling_rank(result["range_pct"], window, min_periods=max(4, window // 4))

    result["atr_12_pct"] = _safe_div(atr_12, close)
    result["atr_48_pct"] = _safe_div(atr_48, close)
    result["atr_144_pct"] = _safe_div(atr_144, close)
    result["atr_12_vs_48"] = _safe_div(atr_12, atr_48)
    result["atr_48_vs_144"] = _safe_div(atr_48, atr_144)
    result["atr_rank_288"] = _rolling_rank(result["atr_48_pct"], 288, min_periods=72)

    result["compression_range_6_vs_48"] = _safe_div(result["range_pct"].rolling(6, min_periods=3).mean(), result["range_mean_48"])
    result["compression_range_12_vs_48"] = _safe_div(result["range_mean_12"], result["range_mean_48"])
    result["compression_range_48_vs_144"] = _safe_div(result["range_mean_48"], result["range_mean_144"])
    result["compression_atr_12_vs_48"] = _safe_div(atr_12, atr_48)
    result["compression_atr_48_vs_144"] = _safe_div(atr_48, atr_144)

    for window in [12, 48, 144]:
        result[f"realized_vol_{window}"] = result["ret_1"].rolling(window, min_periods=max(4, window // 4)).std()
    result["volatility_realized_12_vs_48"] = _safe_div(result["realized_vol_12"], result["realized_vol_48"])
    result["volatility_realized_48_vs_144"] = _safe_div(result["realized_vol_48"], result["realized_vol_144"])
    result["volatility_atr_rank_288"] = result["atr_rank_288"]

    range_mean_96 = result["range_pct"].rolling(96, min_periods=24).mean()
    range_std_96 = result["range_pct"].rolling(96, min_periods=24).std()
    ret_abs_3 = result["ret_3"].abs()
    result["expansion_range_z_96"] = _safe_div(result["range_pct"] - range_mean_96, range_std_96)
    result["expansion_abs_ret_3_z_96"] = _safe_div(
        ret_abs_3 - ret_abs_3.rolling(96, min_periods=24).mean(),
        ret_abs_3.rolling(96, min_periods=24).std(),
    )
    result["expansion_release_12"] = _safe_div(result["range_mean_12"] - result["range_mean_48"], result["range_std_48"])

    high_48 = high.rolling(48, min_periods=12).max()
    low_48 = low.rolling(48, min_periods=12).min()
    high_144 = high.rolling(144, min_periods=36).max()
    low_144 = low.rolling(144, min_periods=36).min()
    result["position_close_in_48_range"] = _safe_div(close - low_48, high_48 - low_48)
    result["position_close_in_144_range"] = _safe_div(close - low_144, high_144 - low_144)
    result["breakout_up_48"] = _safe_div(close - high_48.shift(1), atr_48)
    result["breakout_down_48"] = _safe_div(low_48.shift(1) - close, atr_48)
    result["breakout_up_144"] = _safe_div(close - high_144.shift(1), atr_144)
    result["breakout_down_144"] = _safe_div(low_144.shift(1) - close, atr_144)

    rolling_max_48 = close.rolling(48, min_periods=12).max()
    rolling_min_48 = close.rolling(48, min_periods=12).min()
    result["drawdown_from_48_high"] = _safe_div(close - rolling_max_48, close)
    result["rebound_from_48_low"] = _safe_div(close - rolling_min_48, close)
    result["drawdown_rebound_balance_48"] = result["rebound_from_48_low"] + result["drawdown_from_48_high"]

    result["volume_z_48"] = _safe_div(
        tick_volume - tick_volume.rolling(48, min_periods=12).mean(),
        tick_volume.rolling(48, min_periods=12).std(),
    )
    result["spread_scaled"] = spread / 1000.0
    return result


def build_wave03_volatility_state_features(frame: pd.DataFrame, feature_recipe_id: str) -> tuple[pd.DataFrame, FeatureSchema]:
    feature_family = FEATURE_FAMILY_BY_RECIPE.get(feature_recipe_id)
    if not feature_family:
        raise ValueError(f"unsupported Wave03 feature_recipe_id: {feature_recipe_id}")
    features = pd.concat([_base_features(frame), _session_features(frame)], axis=1)
    prefixes = FEATURE_GROUPS[feature_family]
    columns = [column for column in features.columns if any(column.startswith(prefix) for prefix in prefixes)]
    features = features[columns].replace([np.inf, -np.inf], np.nan)
    boundary = "right_aligned_closed_bar_us100_wave03_volatility_state_features_no_aux_symbols"
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
