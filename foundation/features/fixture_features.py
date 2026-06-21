from __future__ import annotations

import pandas as pd


FEATURE_COLUMNS = [
    "ret_1",
    "range_pct",
    "body_pct",
    "spread_scaled",
]


def build_fixture_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a tiny provisional closed-bar feature surface for plumbing checks."""
    required = {"open", "high", "low", "close", "spread_points"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns for fixture features: {sorted(missing)}")

    result = pd.DataFrame(index=frame.index)
    result["ret_1"] = frame["close"].pct_change()
    result["range_pct"] = (frame["high"] - frame["low"]) / frame["close"].replace(0.0, pd.NA)
    result["body_pct"] = (frame["close"] - frame["open"]) / frame["open"].replace(0.0, pd.NA)
    result["spread_scaled"] = frame["spread_points"].astype(float) / 1000.0
    return result[FEATURE_COLUMNS]
