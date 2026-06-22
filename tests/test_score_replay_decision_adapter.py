from __future__ import annotations

from pathlib import Path

import yaml

from foundation.mt5.score_replay_decision_adapter import (
    ADAPTER_ID,
    CLAIM_BOUNDARY,
    attempt_id_for,
    decision_family_execution_kind,
    direction_from_policy,
    is_direct_trade_adapter_eligible,
    score_to_execution_signal,
)
from foundation.pipelines.prepare_wave0_l4_decision_replay_attempts import (
    EA_SOURCE,
    REPO_ROOT,
    build_attempt_rows_manifests_configs,
    build_tester_config_text,
)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def test_direction_agnostic_tradeability_requires_policy() -> None:
    signal = score_to_execution_signal(
        decision_family="abstain_capable_direction_agnostic_tradeability",
        source_decision="tradeable",
        score=0.9,
        score_high_threshold=0.8,
        direction_policy="momentum_ret_1",
        ret_1=-0.01,
    )

    assert signal.signal == "short"
    assert signal.reason == "direction_policy_momentum_ret_1"


def test_long_short_source_decision_is_preserved() -> None:
    signal = score_to_execution_signal(
        decision_family="abstain_capable_long_short",
        source_decision="long",
        score=0.51,
        score_high_threshold=0.75,
        direction_policy="short_only",
    )

    assert signal.signal == "long"
    assert signal.reason == "source_decision_long_short"


def test_diagnostic_surface_is_not_adapter_eligible() -> None:
    signal = score_to_execution_signal(
        decision_family="diagnostic_rank_only",
        source_decision="observe",
        score=1.0,
        score_high_threshold=0.0,
        direction_policy="long_only",
    )

    assert signal.signal == "flat"
    assert "diagnostic" in signal.reason


def test_wave01_score_band_directional_surface_maps_high_low_to_side() -> None:
    long_signal = score_to_execution_signal(
        decision_family="breakout_entry_abstain_timeout_exit",
        source_decision="unknown",
        score=0.81,
        score_low_threshold=0.25,
        score_high_threshold=0.80,
        direction_policy="score_band_side",
    )
    short_signal = score_to_execution_signal(
        decision_family="breakout_entry_abstain_timeout_exit",
        source_decision="unknown",
        score=0.24,
        score_low_threshold=0.25,
        score_high_threshold=0.80,
        direction_policy="score_band_side",
    )
    flat_signal = score_to_execution_signal(
        decision_family="breakout_entry_abstain_timeout_exit",
        source_decision="unknown",
        score=0.50,
        score_low_threshold=0.25,
        score_high_threshold=0.80,
        direction_policy="score_band_side",
    )

    assert long_signal.signal == "long"
    assert short_signal.signal == "short"
    assert flat_signal.signal == "flat"
    assert decision_family_execution_kind("breakout_entry_abstain_timeout_exit") == "score_band_directional"
    assert is_direct_trade_adapter_eligible("breakout_entry_abstain_timeout_exit") is True


def test_session_transition_failed_breakout_reversion_uses_inverse_score_band_side() -> None:
    short_signal = score_to_execution_signal(
        decision_family="failed_breakout_reversion_abstain_exit",
        source_decision="unknown",
        score=0.90,
        score_low_threshold=0.45,
        score_high_threshold=0.55,
        direction_policy="score_band_inverse_side",
    )
    long_signal = score_to_execution_signal(
        decision_family="failed_breakout_reversion_abstain_exit",
        source_decision="unknown",
        score=0.40,
        score_low_threshold=0.45,
        score_high_threshold=0.55,
        direction_policy="score_band_inverse_side",
    )

    assert short_signal.signal == "short"
    assert short_signal.reason == "score_at_or_above_high_threshold_inverse_side"
    assert long_signal.signal == "long"
    assert long_signal.reason == "score_at_or_below_low_threshold_inverse_side"


def test_wave01_no_trade_preserved_clue_requires_new_decision_surface() -> None:
    signal = score_to_execution_signal(
        decision_family="no_trade_regime_filter",
        source_decision="unknown",
        score=0.99,
        score_low_threshold=0.10,
        score_high_threshold=0.90,
        direction_policy="score_band_side",
    )

    assert signal.signal == "flat"
    assert is_direct_trade_adapter_eligible("no_trade_regime_filter") is False


def test_policy_and_attempt_id_are_stable() -> None:
    assert direction_from_policy("contrarian_ret_1", 0.01).signal == "short"
    assert attempt_id_for("wave0_cell_011", "validation", "momentum_ret_1") == (
        "attempt_wave0_cell_011_l4_decision_replay_validation_momentum_ret_1_v0"
    )
    assert attempt_id_for("wave01_eb_cell_002", "validation", "score_band_side") == (
        "attempt_wave01_eb_cell_002_l4_decision_replay_validation_score_band_side_v0"
    )
    assert ADAPTER_ID == "score_replay_sparse_decision_adapter_v0"
    assert "no_candidate" in CLAIM_BOUNDARY


def test_tester_config_uses_score_replay_ea_and_source_telemetry() -> None:
    execution_profile = load_yaml(REPO_ROOT / "configs/mt5/tester_execution_profile_v0.yaml")
    text = build_tester_config_text(
        attempt_id="attempt_wave0_cell_011_l4_decision_replay_validation_momentum_ret_1_v0",
        source_score_telemetry_common_path="SpaceSonar\\l4_score_probe\\attempt_wave0_cell_011_l4_validation_v0\\score_telemetry.csv",
        period={"from_date": "2024.06.05", "to_date": "2025.03.10"},
        execution_profile=execution_profile,
        decision_family="abstain_capable_direction_agnostic_tradeability",
        direction_policy="momentum_ret_1",
        score_high_threshold=0.62,
        hold_bars=6,
    )

    assert "SpaceSonar_L4_ScoreReplayDecisionProbe.ex5" in text
    assert "InpScoreTelemetryPath=SpaceSonar\\l4_score_probe\\attempt_wave0_cell_011_l4_validation_v0\\score_telemetry.csv" in text
    assert "InpDirectionPolicy=momentum_ret_1" in text
    assert "InpHoldBars=6" in text
    assert "not ONNX runtime authority" in text


def test_build_decision_replay_attempt_plan_uses_non_diagnostic_ingredients_only() -> None:
    summary, rows, manifests, configs = build_attempt_rows_manifests_configs(
        REPO_ROOT,
        direction_policies=["momentum_ret_1"],
        write_mode=False,
        created_at_utc="2026-06-21T00:00:00Z",
    )

    assert summary["counts"]["source_ingredient_count"] == 3
    assert summary["counts"]["prepared_attempt_count"] == 6
    assert summary["counts"]["period_role_counts"] == {"validation": 3, "research_oos": 3}
    assert set(row["cell_id"] for row in rows) == {"wave0_cell_008", "wave0_cell_011", "wave0_cell_012"}
    assert all(row["direction_policy"] == "momentum_ret_1" for row in rows)
    assert all(row["claim_boundary"] == CLAIM_BOUNDARY for row in rows)
    assert all("locked_final" not in row["period_role"] for row in rows)
    assert all(manifest["adapter_id"] == ADAPTER_ID for manifest in manifests.values())
    assert all("ScoreReplayDecisionProbe" in text for text in configs.values())


def test_score_replay_ea_source_is_trade_adapter_not_onnx_probe() -> None:
    source = (REPO_ROOT / EA_SOURCE).read_text(encoding="utf-8")

    assert "#include <Trade/Trade.mqh>" in source
    assert "InpScoreTelemetryPath" in source
    assert "InpDirectionPolicy" in source
    assert "InpScoreLow" in source
    assert "breakout_entry_abstain_timeout_exit" in source
    assert "failed_breakout_reversion_abstain_exit" in source
    assert "score_band_inverse_side" in source
    assert "score <= InpScoreLow" in source
    assert "ExtTrade.Buy" in source
    assert "ExtTrade.Sell" in source
    assert "OnnxRun" not in source
