from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from foundation.features.wave01_event_barrier_features import build_wave01_features


FEATURE_RECIPE_ID = "feature_wave01_us100_session_transition_regime_v0"
NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class FeatureSchema:
    feature_recipe_id: str
    feature_family: str
    base_feature_family: str
    feature_columns: list[str]
    feature_order_hash: str
    feature_schema_hash: str
    boundary: str


BASE_FEATURE_FAMILY_BY_SESSION_FAMILY = {
    "session_state_price_range_context": "session_state_context",
    "compression_expansion_causal_context": "multiscale_price_range_volatility_context",
    "range_edge_reversal_context": "causal_regime_context",
    "causal_quiet_regime_context": "session_state_context",
    "causal_regime_transition_context": "causal_regime_context",
    "price_return_range_volatility_context": "price_return_range_volatility_context",
    "fast_transition_shock_context": "session_state_context",
    "range_acceptance_context": "causal_regime_context",
}


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.astype(float) / denominator.replace(0.0, np.nan).astype(float)


def _ny_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "us100_bar_close_time_utc_rendered" not in frame.columns:
        raise ValueError("missing us100_bar_close_time_utc_rendered for session-transition features")
    return pd.to_datetime(frame["us100_bar_close_time_utc_rendered"], utc=True).dt.tz_convert(NY_TZ)


def _session_transition_columns(frame: pd.DataFrame) -> pd.DataFrame:
    timestamp = _ny_timestamp(frame)
    minute = timestamp.dt.hour.astype(float) * 60.0 + timestamp.dt.minute.astype(float)
    dow = timestamp.dt.dayofweek.astype(float)
    cash_open = 9.5 * 60.0
    cash_close = 16.0 * 60.0
    midday = 12.5 * 60.0

    result = pd.DataFrame(index=frame.index)
    result["ny_minute_sin"] = np.sin(2.0 * np.pi * minute / 1440.0)
    result["ny_minute_cos"] = np.cos(2.0 * np.pi * minute / 1440.0)
    result["ny_dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    result["ny_dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    result["minutes_from_cash_open_scaled"] = (minute - cash_open) / 390.0
    result["minutes_to_cash_close_scaled"] = (cash_close - minute) / 390.0
    result["minutes_from_midday_scaled"] = (minute - midday) / 390.0
    result["is_pre_cash"] = ((minute >= 4.0 * 60.0) & (minute < cash_open)).astype(float)
    result["is_cash_session"] = ((minute >= cash_open) & (minute <= cash_close)).astype(float)
    result["is_after_cash"] = ((minute > cash_close) & (minute <= 20.0 * 60.0)).astype(float)
    result["is_cash_open_transition"] = (minute.sub(cash_open).abs() <= 60.0).astype(float)
    result["is_cash_close_transition"] = (minute.sub(cash_close).abs() <= 60.0).astype(float)
    result["is_midday_block"] = (minute.sub(midday).abs() <= 90.0).astype(float)
    result["is_monday"] = (dow == 0.0).astype(float)
    result["is_friday"] = (dow == 4.0).astype(float)
    return result


def _local_context_columns(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    tick_volume = frame["tick_volume"].astype(float)
    spread = frame["spread_points"].astype(float)

    result = pd.DataFrame(index=frame.index)
    result["local_ret_1"] = close.pct_change(1)
    result["local_ret_3"] = close.pct_change(3)
    result["local_ret_6"] = close.pct_change(6)
    result["local_range_pct"] = _safe_div(high - low, close)
    result["local_range_mean_12"] = result["local_range_pct"].rolling(12, min_periods=6).mean()
    result["local_range_mean_48"] = result["local_range_pct"].rolling(48, min_periods=12).mean()
    result["local_range_ratio_12_48"] = _safe_div(result["local_range_mean_12"], result["local_range_mean_48"])
    result["local_ret_abs_mean_12"] = result["local_ret_1"].abs().rolling(12, min_periods=6).mean()
    result["local_ret_abs_mean_48"] = result["local_ret_1"].abs().rolling(48, min_periods=12).mean()
    result["local_ret_abs_ratio_12_48"] = _safe_div(result["local_ret_abs_mean_12"], result["local_ret_abs_mean_48"])
    result["local_tick_volume_z_48"] = _safe_div(
        tick_volume - tick_volume.rolling(48, min_periods=12).mean(),
        tick_volume.rolling(48, min_periods=12).std(),
    )
    result["local_spread_scaled"] = spread / 1000.0
    return result


def build_wave01_session_transition_features(frame: pd.DataFrame, feature_family: str) -> tuple[pd.DataFrame, FeatureSchema]:
    if feature_family not in BASE_FEATURE_FAMILY_BY_SESSION_FAMILY:
        raise ValueError(f"unsupported Wave01 session-transition feature_family: {feature_family}")

    base_family = BASE_FEATURE_FAMILY_BY_SESSION_FAMILY[feature_family]
    base_features, base_schema = build_wave01_features(frame, base_family)
    session_features = _session_transition_columns(frame)
    local_features = _local_context_columns(frame)

    features = pd.concat([base_features, session_features, local_features], axis=1)
    features = features.loc[:, ~features.columns.duplicated()].replace([np.inf, -np.inf], np.nan)
    columns = list(features.columns)
    boundary = (
        "right_aligned_closed_bar_us100_price_session_transition_context_"
        "america_new_york_rendered_time_no_auxiliary_symbols"
    )
    schema_payload = {
        "feature_recipe_id": FEATURE_RECIPE_ID,
        "feature_family": feature_family,
        "base_feature_family": base_family,
        "base_feature_order_hash": base_schema.feature_order_hash,
        "feature_columns": columns,
        "boundary": boundary,
        "feature_count_policy": "variable_declared_per_run_no_fixed_count",
    }
    schema = FeatureSchema(
        feature_recipe_id=FEATURE_RECIPE_ID,
        feature_family=feature_family,
        base_feature_family=base_family,
        feature_columns=columns,
        feature_order_hash=hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
        feature_schema_hash=_hash_json(schema_payload),
        boundary=boundary,
    )
    return features[columns], schema
