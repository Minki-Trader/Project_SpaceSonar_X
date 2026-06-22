from __future__ import annotations

from pathlib import Path

from foundation.pipelines.run_wave0_l4_mt5_attempts import (
    common_relative_to_path,
    execution_index_fieldnames,
    merge_execution_rows,
    normalize_l4_terminal_summary,
    parse_args,
    parse_score_telemetry,
    selected_attempt_rows,
    upsert_ini_line,
)


def test_runner_defaults_to_bounded_single_attempt_without_taskkill() -> None:
    args = parse_args([])

    assert args.limit == 1
    assert args.terminate_existing_terminal is False
    assert args.no_main_mode_fallback is False


def test_selected_attempt_rows_filters_period_role_and_limit(tmp_path: Path) -> None:
    attempt_a = tmp_path / "runtime" / "mt5_attempts" / "attempt_a" / "attempt_manifest.yaml"
    attempt_b = tmp_path / "runtime" / "mt5_attempts" / "attempt_b" / "attempt_manifest.yaml"
    attempt_a.parent.mkdir(parents=True)
    attempt_b.parent.mkdir(parents=True)
    attempt_a.write_text("status: prepared_pending_terminal_execution\n", encoding="utf-8")
    attempt_b.write_text("status: completed_l4_score_telemetry_observed\n", encoding="utf-8")
    rows = [
        {
            "attempt_id": "attempt_a",
            "period_role": "validation",
            "attempt_manifest_path": "runtime/mt5_attempts/attempt_a/attempt_manifest.yaml",
        },
        {
            "attempt_id": "attempt_b",
            "period_role": "validation",
            "attempt_manifest_path": "runtime/mt5_attempts/attempt_b/attempt_manifest.yaml",
        },
        {
            "attempt_id": "attempt_c",
            "period_role": "research_oos",
            "attempt_manifest_path": "runtime/mt5_attempts/attempt_c/attempt_manifest.yaml",
        },
    ]

    selected = selected_attempt_rows(
        rows,
        repo_root=tmp_path,
        attempt_ids=None,
        period_roles={"validation"},
        limit=1,
        include_completed=False,
    )

    assert [row["attempt_id"] for row in selected] == ["attempt_a"]


def test_common_relative_to_path_rejects_escape(tmp_path: Path) -> None:
    try:
        common_relative_to_path("..\\escape.csv", root=tmp_path)
    except RuntimeError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_parse_score_telemetry_summarizes_rows(tmp_path: Path) -> None:
    telemetry = tmp_path / "score_telemetry.csv"
    telemetry.write_text(
        "bar_close_time,symbol,period,input_family,decision_family,feature_count,score,decision,spread_points,tick_volume\n"
        "2024.06.05 00:05:00,US100,PERIOD_M5,family,abstain_capable_long_short,13,0.20,short,100,10\n"
        "2024.06.05 00:10:00,US100,PERIOD_M5,family,abstain_capable_long_short,13,0.80,long,120,0\n",
        encoding="utf-8",
    )

    parsed = parse_score_telemetry(telemetry)

    assert parsed["status"] == "telemetry_observed"
    assert parsed["row_count"] == 2
    assert parsed["decision_counts"] == {"long": 1, "short": 1}
    assert parsed["score_stats"]["finite_count"] == 2
    assert parsed["spread_points_stats"]["max"] == 120.0
    assert parsed["tick_volume_nonzero_count"] == 1


def test_parse_score_telemetry_empty_csv_is_not_observed(tmp_path: Path) -> None:
    telemetry = tmp_path / "score_telemetry.csv"
    telemetry.write_text(
        "bar_close_time,symbol,period,input_family,decision_family,feature_count,score,decision,spread_points,tick_volume\n",
        encoding="utf-8",
    )

    parsed = parse_score_telemetry(telemetry)

    assert parsed == {"row_count": 0, "status": "empty_telemetry"}


def test_l4_terminal_summary_normalization_removes_fixed_fixture_claim_text() -> None:
    summary = {
        "mode": "main_mode_config_fallback",
        "attempt_claim_boundary": "local_fixed_fixture_fallback_only_no_runtime_authority",
        "terminal_attempts": [
            {"mode": "main_mode_config_fallback", "attempt_claim_boundary": "local_fixed_fixture_fallback_only_no_runtime_authority"}
        ],
        "terminal_mode_policy": {
            "main_mode_fallback_used": True,
            "fallback_reason": "portable_attempt_did_not_produce_mt5_probe_telemetry",
            "claim_effect": "fixed_fixture_micro_probe_only_no_runtime_authority",
        },
    }

    normalized = normalize_l4_terminal_summary(summary)

    assert normalized["attempt_claim_boundary"] == "local_l4_main_mode_fallback_only_no_runtime_authority"
    assert "fixed_fixture" not in normalized["terminal_mode_policy"]["claim_effect"]
    assert normalized["terminal_mode_policy"]["fallback_reason"] == "portable_attempt_did_not_produce_l4_score_telemetry"


def test_merge_execution_rows_preserves_existing_attempts_in_prep_order(tmp_path: Path) -> None:
    prep_index = (
        tmp_path
        / "lab"
        / "campaigns"
        / "campaign_us100_task_surface_scout_v0"
        / "l4_follow_through"
        / "l4_attempt_preparation_index.csv"
    )
    runtime_index = prep_index.with_name("l4_runtime_execution_index.csv")
    prep_index.parent.mkdir(parents=True)
    prep_index.write_text(
        "attempt_id,run_id,bundle_id,cell_id,period_role,from_date,to_date,status,attempt_manifest_path,tester_config_path,"
        "common_model_path,common_model_copy_status,telemetry_common_path,feature_count,decision_family,"
        "runtime_period_set_id,tester_execution_profile_id,claim_boundary\n"
        "attempt_a,run_a,bundle_a,cell_a,validation,2024.06.05,2025.03.10,prepared,a.yaml,a.ini,,,,,,set,profile,boundary\n"
        "attempt_b,run_b,bundle_b,cell_b,research_oos,2025.04.03,2025.11.21,prepared,b.yaml,b.ini,,,,,,set,profile,boundary\n",
        encoding="utf-8",
    )
    runtime_index.write_text(
        ",".join(execution_index_fieldnames())
        + "\n"
        + "attempt_b,run_b,bundle_b,cell_b,research_oos,2025.04.03,2025.11.21,completed,runtime_probe,True,10,False,"
        + "main,0,False,b_terminal.yaml,b_score.yaml,b.csv,,boundary,next\n",
        encoding="utf-8",
    )

    merged = merge_execution_rows(
        tmp_path,
        [
            {
                "attempt_id": "attempt_a",
                "run_id": "run_a",
                "bundle_id": "bundle_a",
                "cell_id": "cell_a",
                "period_role": "validation",
                "from_date": "2024.06.05",
                "to_date": "2025.03.10",
                "status": "completed",
            }
        ],
    )

    assert [row["attempt_id"] for row in merged] == ["attempt_a", "attempt_b"]


def test_upsert_ini_line_inserts_feature_columns_path_after_inline_columns() -> None:
    text = "[TesterInputs]\nInpFeatureColumns=a;b;c\nInpFeatureCount=3\n"

    updated = upsert_ini_line(
        text,
        "InpFeatureColumnsPath",
        "SpaceSonar\\l4_score_probe\\bundle\\feature_columns.txt",
        after_key="InpFeatureColumns",
    )

    assert "InpFeatureColumns=a;b;c\nInpFeatureColumnsPath=SpaceSonar\\l4_score_probe\\bundle\\feature_columns.txt\n" in updated
