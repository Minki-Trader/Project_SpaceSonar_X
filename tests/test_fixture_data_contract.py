from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from foundation.labels.fixture_labels import HORIZON_BARS
from foundation.pipelines.minimal_onnx_mt5_plumbing_slice import (
    build_fixture_split,
    durable_command_argv,
    export_mt5_bars,
)


def test_fixture_split_purges_horizon_rows_before_validation_fit() -> None:
    row_count = 100
    combined = pd.DataFrame(
        {
            "us100_bar_close_time": pd.date_range("2024-01-01", periods=row_count, freq="5min", tz="UTC"),
        }
    )
    combined["label_end_time"] = combined["us100_bar_close_time"].shift(-HORIZON_BARS)
    combined = combined.dropna().reset_index(drop=True)

    split = build_fixture_split(combined)

    assert split.train_candidate_rows == int(len(combined) * 0.70)
    assert split.purged_rows == HORIZON_BARS
    assert split.train_fit_rows == split.train_candidate_rows - HORIZON_BARS
    assert split.boundary_status == "passed_label_end_time_lt_first_validation_time"

    max_train_label_end = pd.Timestamp(split.max_train_label_end_time)
    first_validation_time = pd.Timestamp(split.first_validation_time)
    assert max_train_label_end < first_validation_time


def test_minimal_fixture_rejects_non_us100_before_mt5_export() -> None:
    with pytest.raises(ValueError, match="fixed to US100"):
        export_mt5_bars("BTCUSD", pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2024-01-02", tz="UTC"))


def test_durable_command_argv_uses_repo_relative_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "foundation" / "pipelines" / "minimal_onnx_mt5_plumbing_slice.py"

    argv = durable_command_argv([str(script), "--requested-branch", "codex/test"], repo_root)

    assert argv == [
        "foundation/pipelines/minimal_onnx_mt5_plumbing_slice.py",
        "--requested-branch",
        "codex/test",
    ]
