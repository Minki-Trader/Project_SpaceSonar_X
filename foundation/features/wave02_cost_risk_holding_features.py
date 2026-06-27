from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CostRiskHoldingFeatureSchema:
    feature_recipe_id: str
    feature_variant: str
    feature_family: str
    feature_columns: list[str]
    feature_order_hash: str
    feature_schema_hash: str
    boundary: str


FEATURE_VARIANT_PREFIXES = {
    "cost_context_basic": ["ret_", "range_", "atr_", "spread_", "cost_", "session_"],
    "cost_context_session": ["ret_", "range_", "atr_", "spread_", "cost_", "session_", "transition_"],
    "range_reversal_context": ["ret_", "range_", "atr_", "path_", "position_", "reversal_"],
    "execution_failure_context": ["ret_", "range_", "atr_", "spread_", "cost_", "execution_", "session_"],
    "session_cost_risk_context": ["ret_", "range_", "atr_", "spread_", "cost_", "session_", "transition_"],
    "volatility_stop_context": ["ret_", "range_", "atr_", "volatility_", "path_", "position_", "spread_"],
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
        raise ValueError("missing us100_bar_close_time_utc_rendered for Wave02 cost/risk/holding features")
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
    result["session_is_cash"] = ((minute >= cash_open) & (minute <= cash_close)).astype(float)
    result["session_is_edge"] = ((minute.sub(cash_open).abs() <= 45.0) | (minute.sub(cash_close).abs() <= 45.0)).astype(float)
    result["transition_cash_open_60m"] = (minute.sub(cash_open).abs() <= 60.0).astype(float)
    result["transition_cash_close_60m"] = (minute.sub(cash_close).abs() <= 60.0).astype(float)
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
    atr_pct = _safe_div(atr_48, close)

    result = pd.DataFrame(index=frame.index)
    for window in [1, 3, 6, 12, 24, 48]:
        result[f"ret_{window}"] = close.pct_change(window)
        min_periods = min(window, max(1, window // 4))
        result[f"path_abs_ret_mean_{window}"] = result["ret_1"].abs().rolling(window, min_periods=min_periods).mean()
    result["range_pct"] = _safe_div(high - low, close)
    result["range_body_pct"] = _safe_div((close - open_).abs(), close)
    result["range_upper_wick_pct"] = _safe_div(high - pd.concat([open_, close], axis=1).max(axis=1), close)
    result["range_lower_wick_pct"] = _safe_div(pd.concat([open_, close], axis=1).min(axis=1) - low, close)
    for window in [12, 48, 144]:
        result[f"range_mean_{window}"] = result["range_pct"].rolling(window, min_periods=max(3, window // 4)).mean()
        result[f"range_std_{window}"] = result["range_pct"].rolling(window, min_periods=max(3, window // 4)).std()
    result["atr_48_pct"] = atr_pct
    result["volatility_atr_48_pct"] = atr_pct
    result["spread_scaled"] = spread / 1000.0
    result["cost_spread_return_proxy"] = _safe_div(spread / 100.0, close)
    result["cost_to_atr_proxy"] = _safe_div(spread / 100.0, atr_48)
    result["execution_spread_z_48"] = _safe_div(spread - spread.rolling(48, min_periods=12).mean(), spread.rolling(48, min_periods=12).std())
    result["execution_range_cost_ratio"] = _safe_div(high - low, spread / 100.0)
    result["volume_z_48"] = _safe_div(tick_volume - tick_volume.rolling(48, min_periods=12).mean(), tick_volume.rolling(48, min_periods=12).std())
    high_48 = high.rolling(48, min_periods=12).max()
    low_48 = low.rolling(48, min_periods=12).min()
    result["position_close_in_48_range"] = _safe_div(close - low_48, high_48 - low_48)
    result["reversal_pressure_12"] = -np.sign(result["ret_12"]) * result["position_close_in_48_range"].sub(0.5).abs()
    return result


def build_wave02_cost_risk_holding_features(
    frame: pd.DataFrame,
    feature_recipe_id: str,
    feature_variant: str,
) -> tuple[pd.DataFrame, CostRiskHoldingFeatureSchema]:
    prefixes = FEATURE_VARIANT_PREFIXES.get(feature_variant)
    if prefixes is None:
        raise ValueError(f"unsupported Wave02 cost/risk/holding feature_variant: {feature_variant}")
    features = pd.concat([_base_features(frame), _session_features(frame)], axis=1)
    columns = [column for column in features.columns if any(column.startswith(prefix) for prefix in prefixes)]
    features = features[columns].replace([np.inf, -np.inf], np.nan)
    boundary = "right_aligned_closed_bar_us100_wave02_cost_risk_holding_features_no_aux_symbols"
    payload = {
        "feature_recipe_id": feature_recipe_id,
        "feature_variant": feature_variant,
        "feature_family": "cost_risk_holding_surface",
        "feature_columns": columns,
        "boundary": boundary,
    }
    schema = CostRiskHoldingFeatureSchema(
        feature_recipe_id=feature_recipe_id,
        feature_variant=feature_variant,
        feature_family="cost_risk_holding_surface",
        feature_columns=columns,
        feature_order_hash=hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
        feature_schema_hash=_hash_json(payload),
        boundary=boundary,
    )
    return features, schema
