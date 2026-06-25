from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from foundation.pipelines.prepare_wave0_l4_mt5_attempts import (
    CLAIM_BOUNDARY,
    COMMON_REL_ROOT,
    REPO_ROOT,
    build_tester_config_text,
    build_attempt_rows_and_manifests,
    required_l4_periods,
)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def test_required_l4_periods_use_validation_and_research_oos_only() -> None:
    profile = load_yaml(REPO_ROOT / "configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")

    periods = required_l4_periods(profile, "split_base_anchor_v0_research_l4")

    assert [period["period_role"] for period in periods] == ["validation", "research_oos"]
    assert periods[0]["from_date"] == "2024.06.05"
    assert periods[1]["to_date"] == "2025.11.21"
    assert "locked_final_oos" not in {period["period_role"] for period in periods}


def test_tester_config_uses_semicolon_feature_delimiter_and_l4_probe_ea() -> None:
    bundle = {
        "bundle_id": "bundle_test_l4_onnx_export_v0",
        "feature_schema_contract": {
            "feature_columns": ["ret_1", "rolling_ret_mean_12"],
            "input_family": "price_only_m5_returns_ranges_volatility",
        },
        "decision_surface": {
            "decision_family": "abstain_capable_long_short",
            "score_low_threshold": 0.25,
            "score_high_threshold": 0.75,
        },
    }
    execution_profile = load_yaml(REPO_ROOT / "configs/mt5/tester_execution_profile_v0.yaml")

    text = build_tester_config_text(
        attempt_id="attempt_test_l4_validation_v0",
        bundle=bundle,
        period={"period_role": "validation", "from_date": "2024.06.05", "to_date": "2025.03.10"},
        execution_profile=execution_profile,
    )

    assert "SpaceSonar_ONNX_L4_ScoreProbe.ex5" in text
    assert "InpFeatureColumns=ret_1;rolling_ret_mean_12" in text
    assert f"InpFeatureColumnsPath={COMMON_REL_ROOT}\\bundle_test_l4_onnx_export_v0\\feature_columns.txt" in text
    assert "InpFeatureColumns=ret_1|rolling_ret_mean_12" not in text
    assert f"InpOnnxPath={COMMON_REL_ROOT}\\bundle_test_l4_onnx_export_v0\\model.onnx" in text
    assert "InpFixedLot=0.02" in text


def test_build_attempt_plan_creates_two_l4_roles_per_exported_bundle_without_writing() -> None:
    first_model = (
        REPO_ROOT
        / "runtime/packages/bundle_wave0_cell_001_l4_onnx_export_v0/artifacts/model.onnx"
    )
    if not first_model.exists():
        pytest.skip(f"exported ONNX bundle artifact is local evidence not present in this checkout: {first_model}")
    before = set((REPO_ROOT / "runtime" / "mt5_attempts").glob("attempt_wave0_cell_*_l4_*_v0/tester_config.ini"))

    summary, rows, manifests, configs = build_attempt_rows_and_manifests(
        REPO_ROOT,
        copy_common_files=False,
        command_argv=["python", "foundation/pipelines/prepare_wave0_l4_mt5_attempts.py"],
        created_at_utc="2026-06-21T00:00:00Z",
    )

    after = set((REPO_ROOT / "runtime" / "mt5_attempts").glob("attempt_wave0_cell_*_l4_*_v0/tester_config.ini"))
    assert before == after
    assert summary["counts"]["exported_bundle_count"] == 12
    assert summary["counts"]["prepared_attempt_count"] == 24
    assert summary["runtime_contract_binding"]["required_period_roles"] == ["validation", "research_oos"]
    assert summary["runtime_contract_binding"]["locked_final_oos_b"] == "excluded_forbidden_by_default"
    assert len(rows) == 24
    assert len(manifests) == 24
    assert len(configs) == 24
    assert {row["period_role"] for row in rows} == {"validation", "research_oos"}
    assert all(row["claim_boundary"] == CLAIM_BOUNDARY for row in rows)
    assert all("pending_write" == manifest["artifact_identity"]["tester_config"]["status"] for manifest in manifests.values())
    assert all("feature_columns.txt" in manifest["artifact_identity"]["common_files"] for manifest in manifests.values())


def test_generated_attempt_records_match_index_when_present() -> None:
    index_path = (
        REPO_ROOT
        / "lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/l4_attempt_preparation_index.csv"
    )
    if not index_path.exists():
        return

    with index_path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 24
    assert {row["period_role"] for row in rows} == {"validation", "research_oos"}
    assert all(row["runtime_period_set_id"] == "split_base_anchor_v0_research_l4" for row in rows)

    for row in rows:
        manifest_path = REPO_ROOT / row["attempt_manifest_path"]
        tester_config_path = REPO_ROOT / row["tester_config_path"]
        assert manifest_path.exists()
        assert tester_config_path.exists()
        manifest = load_yaml(manifest_path)
        config_text = tester_config_path.read_text(encoding="utf-8")
        assert manifest["attempt_id"] == row["attempt_id"]
        assert manifest["period_identity"]["period_role"] == row["period_role"]
        assert manifest["period_identity"]["locked_final_oos_b"] == "excluded_forbidden_by_default"
        execution_state = manifest.get("execution_state") or {}
        missing_gates = manifest["required_gate_coverage"]["missing"]
        passed_gates = manifest["required_gate_coverage"]["passed"]
        if execution_state.get("runtime_probe_complete"):
            assert missing_gates == []
            assert "Strategy_Tester_terminal_execution" in passed_gates
            assert "score_telemetry_csv" in passed_gates
            assert "L4_period_role_completed_report" in passed_gates
            assert "tester_report_hash" in passed_gates
        else:
            assert missing_gates
        if str(manifest.get("status", "")).startswith("completed_"):
            assert "Strategy_Tester_terminal_execution" not in missing_gates
            assert "score_telemetry_csv" not in missing_gates
        else:
            if execution_state.get("terminal_launched"):
                assert "Strategy_Tester_terminal_execution" not in missing_gates
                assert any(
                    item in missing_gates
                    for item in ["L4_period_role_completed_report", "tester_report_hash"]
                ) or execution_state.get("runtime_probe_complete")
            else:
                assert "Strategy_Tester_terminal_execution" in missing_gates
        assert f"FromDate={row['from_date']}" in config_text
        assert f"ToDate={row['to_date']}" in config_text
        assert "InpFeatureColumnsPath=SpaceSonar\\l4_score_probe" in config_text
        assert "2025.12.02" not in config_text
        assert "2026.06.18" not in config_text
