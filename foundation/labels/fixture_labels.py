from __future__ import annotations

import pandas as pd


LABEL_ID = "label_fixture_next_m5_up_v0"
HORIZON_BARS = 1


def build_fixture_label(frame: pd.DataFrame) -> pd.Series:
    """Build a provisional one-bar direction label for fixture plumbing only."""
    if "close" not in frame.columns:
        raise ValueError("missing close column for fixture label")
    forward_return = frame["close"].shift(-HORIZON_BARS) / frame["close"] - 1.0
    return (forward_return > 0.0).astype("int64")
