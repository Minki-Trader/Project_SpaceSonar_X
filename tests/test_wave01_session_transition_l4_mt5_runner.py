from __future__ import annotations

from pathlib import Path

import foundation.pipelines.run_wave0_l4_mt5_attempts as base
from foundation.pipelines.run_wave01_session_transition_l4_mt5_attempts import (
    CLAIM_BOUNDARY,
    OUTPUT_DIR,
    PREP_INDEX,
    RUNTIME_INDEX,
    RUNTIME_SUMMARY,
    configure_base,
    normalize_attempt_outputs,
    normalize_summary,
    parse_args,
)


def test_wave01_runner_defaults_to_bounded_single_attempt_without_taskkill() -> None:
    args = parse_args([])

    assert args.limit == 1
    assert args.terminate_existing_terminal is False
    assert args.no_main_mode_fallback is False


def test_wave01_runner_configures_wave01_paths_without_wave0_outputs() -> None:
    original = {
        "WORK_ITEM_ID": base.WORK_ITEM_ID,
        "SUBWORK_ID": base.SUBWORK_ID,
        "CAMPAIGN_ID": base.CAMPAIGN_ID,
        "SWEEP_ID": base.SWEEP_ID,
        "OUTPUT_DIR": base.OUTPUT_DIR,
        "PREP_INDEX": base.PREP_INDEX,
        "RUNTIME_SUMMARY": base.RUNTIME_SUMMARY,
        "RUNTIME_INDEX": base.RUNTIME_INDEX,
        "CLAIM_BOUNDARY": base.CLAIM_BOUNDARY,
    }
    try:
        configure_base()

        assert base.OUTPUT_DIR == OUTPUT_DIR
        assert base.PREP_INDEX == PREP_INDEX
        assert base.RUNTIME_SUMMARY == RUNTIME_SUMMARY
        assert base.RUNTIME_INDEX == RUNTIME_INDEX
        assert "campaign_us100_session_transition" in base.OUTPUT_DIR.as_posix()
        assert "wave0_broad_surface_scout" not in base.SWEEP_ID
        assert base.CLAIM_BOUNDARY == CLAIM_BOUNDARY
    finally:
        for key, value in original.items():
            setattr(base, key, value)


def test_normalize_summary_rewrites_wave01_identity() -> None:
    summary = {
        "version": "wave0_l4_runtime_execution_summary_v1",
        "summary_id": "wave0_l4_runtime_execution_summary_v0",
        "work_item_id": "old",
        "subwork_item_id": "old",
        "active_goal_id": "old",
        "campaign_id": "old",
        "sweep_id": "old",
        "claim_boundary": "old",
        "artifact_outputs": {
            "runtime_execution_summary": "old",
            "runtime_execution_index": "old",
        },
        "judgment": {
            "runtime_probe_completed_for_all_prepared_attempts": True,
            "next_action": "old",
        },
    }

    normalized = normalize_summary(summary)

    assert normalized["version"] == "wave01_session_transition_l4_runtime_execution_summary_v1"
    assert normalized["summary_id"] == "wave01_session_transition_l4_runtime_execution_summary_v0"
    assert normalized["campaign_id"] == "campaign_us100_session_transition_regime_surface_v0"
    assert normalized["artifact_outputs"]["runtime_execution_summary"] == RUNTIME_SUMMARY.as_posix()
    assert "Wave01" in normalized["judgment"]["next_action"]


def test_normalize_attempt_outputs_removes_wave0_runtime_scope(tmp_path: Path) -> None:
    attempt_id = "attempt_wave01_st_cell_001_l4_validation_v0"
    attempt_root = tmp_path / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True)
    manifest_path = attempt_root / "attempt_manifest.yaml"
    terminal_path = attempt_root / "terminal_run_summary.yaml"
    score_path = attempt_root / "score_telemetry_summary.yaml"
    terminal_path.write_text("version: wave0_l4_terminal_run_summary_v1\n", encoding="utf-8")
    score_path.write_text("version: wave0_l4_score_telemetry_summary_v1\nclaim_boundary: old\n", encoding="utf-8")
    manifest_path.write_text(
        "runtime_probe_routing:\n"
        "  routing_scope: wave0_l4_split_runtime_score_probe_execution\n"
        "proxy_runtime_parity: {}\n"
        "artifact_identity: {}\n",
        encoding="utf-8",
    )
    row = {
        "attempt_id": attempt_id,
        "attempt_manifest_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
        "period_role": "validation",
    }
    execution_row = {"telemetry_observed": True}

    normalize_attempt_outputs(tmp_path, row, execution_row)

    terminal = base.load_yaml(terminal_path)
    score = base.load_yaml(score_path)
    manifest = base.load_yaml(manifest_path)
    assert terminal["version"] == "wave01_session_transition_l4_terminal_run_summary_v1"
    assert score["version"] == "wave01_session_transition_l4_score_telemetry_summary_v1"
    assert score["claim_boundary"] == CLAIM_BOUNDARY
    assert manifest["runtime_probe_routing"]["routing_scope"] == "wave01_session_transition_l4_split_runtime_score_probe_execution"
    assert "Wave01 L4 runner normalizes" in manifest["proxy_runtime_parity"]["prevention_memory"][0]
    assert manifest["terminal_run_summary"]["version"] == "wave01_session_transition_l4_terminal_run_summary_v1"
    assert manifest["score_telemetry_summary"]["version"] == "wave01_session_transition_l4_score_telemetry_summary_v1"
    assert any("session-transition L4 uses EA-side" in item for item in manifest["proxy_runtime_parity"]["prevention_memory"])


def test_l4_score_probe_adapter_declares_wave01_base_features() -> None:
    source = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5").read_text(encoding="utf-8")

    for feature_name in ["ret_2", "true_range_pct", "atr_12_pct", "atr_48_pct", "body_to_range"]:
        assert f'column == "{feature_name}"' in source
    assert "TrueRangeAt" in source
    assert "MeanTrueRange" in source


def test_l4_score_probe_adapter_declares_session_transition_features() -> None:
    source = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5").read_text(encoding="utf-8")

    for feature_name in [
        "ny_minute_sin",
        "ny_minute_cos",
        "ny_dow_sin",
        "ny_dow_cos",
        "minutes_from_cash_open_scaled",
        "minutes_to_cash_close_scaled",
        "minutes_from_midday_scaled",
        "is_pre_cash",
        "is_cash_session",
        "is_after_cash",
        "is_cash_open_transition",
        "is_cash_close_transition",
        "is_midday_block",
        "is_monday",
        "is_friday",
    ]:
        assert f'column == "{feature_name}"' in source
    assert "IsNewYorkDstUtcLike" in source
    assert "InpBarTimeToUtcOffsetHours" in source


def test_l4_score_probe_adapter_declares_local_context_features() -> None:
    source = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5").read_text(encoding="utf-8")

    for token in [
        '"local_ret_"',
        '"local_range_mean_"',
        "local_range_ratio_12_48",
        '"local_ret_abs_mean_"',
        "local_ret_abs_ratio_12_48",
        '"local_tick_volume_z_"',
        "local_spread_scaled",
    ]:
        assert token in source
    assert "MeanAbsRet" in source
    assert "LocalContextFeature" in source

