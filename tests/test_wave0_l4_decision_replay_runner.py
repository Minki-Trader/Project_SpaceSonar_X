from __future__ import annotations

from pathlib import Path

from foundation.pipelines.run_wave0_l4_decision_replay_attempts import (
    execution_index_fieldnames,
    merge_execution_rows,
    normalize_decision_terminal_summary,
    parse_args,
    parse_execution_telemetry,
    parse_tester_log_summary,
)


def test_decision_replay_runner_defaults_to_bounded_single_attempt_without_taskkill() -> None:
    args = parse_args([])

    assert args.limit == 1
    assert args.terminate_existing_terminal is False
    assert args.no_main_mode_fallback is False


def test_parse_execution_telemetry_summarizes_sparse_actions(tmp_path: Path) -> None:
    telemetry = tmp_path / "execution_telemetry.csv"
    telemetry.write_text(
        "bar_close_time,symbol,period,decision_family,direction_policy,score,source_decision,execution_signal,action,spread_points\n"
        "2024.06.05 00:05:00,US100,PERIOD_M5,family,momentum_ret_1,0.80,long,long,open_long,100\n"
        "2024.06.05 00:10:00,US100,PERIOD_M5,family,momentum_ret_1,0.82,long,long,hold_same_direction,120\n"
        "2024.06.05 00:15:00,US100,PERIOD_M5,family,momentum_ret_1,0.20,flat,flat,close_flat,110\n",
        encoding="utf-8",
    )

    parsed = parse_execution_telemetry(telemetry)

    assert parsed["status"] == "execution_telemetry_observed"
    assert parsed["row_count"] == 3
    assert parsed["action_counts"]["open_long"] == 1
    assert parsed["trade_action_counts"]["open_action_count"] == 1
    assert parsed["trade_action_counts"]["close_action_count"] == 1
    assert parsed["score_stats"]["finite_count"] == 3
    assert parsed["spread_points_stats"]["max"] == 120.0


def test_decision_terminal_summary_normalization_removes_fixed_fixture_claim_text() -> None:
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

    normalized = normalize_decision_terminal_summary(summary)

    assert normalized["attempt_claim_boundary"] == "local_decision_replay_main_mode_fallback_only_no_runtime_authority"
    assert "fixed_fixture" not in normalized["terminal_mode_policy"]["claim_effect"]
    assert normalized["terminal_mode_policy"]["fallback_reason"] == "portable_attempt_did_not_produce_decision_replay_execution_telemetry"


def test_parse_tester_log_summary_extracts_final_balance_and_orders(tmp_path: Path) -> None:
    attempt_id = "attempt_wave0_cell_008_l4_decision_replay_validation_momentum_ret_1_v0"
    tester_config = tmp_path / "runtime" / "mt5_attempts" / attempt_id / "tester_config.ini"
    tester_config.parent.mkdir(parents=True)
    tester_config.write_text("[Tester]\n", encoding="utf-8")
    log = tmp_path / "20260622.log"
    log.write_text(
        f'AA\t0\t05:56:55.924\tStartup\tsuccessfully initialized from start config "{tester_config}"\n'
        "BB\t0\t05:57:29.892\tCore 01\tfinal balance 280.87 USD\n"
        "CC\t0\t05:57:29.892\tCore 01\t2025.03.07 23:54:59   SpaceSonar score replay deinit reason=1 rows_loaded=53554 rows_observed=53554 orders_attempted=7251\n"
        "DD\t0\t05:57:29.892\tCore 01\tUS100,M5: 63218445 ticks, 53554 bars generated. Test passed in 0:00:26.858 (including ticks preprocessing 0:00:03.453).\n"
        f'EE\t0\t05:57:29.892\tCore 01\tlog file "{tmp_path}\\Agent\\logs\\20260622.log" written\n'
        'FF\t0\t05:57:30.255\tTester\tlast test passed with result "successfully finished" in 0:00:26.858\n',
        encoding="utf-16",
    )

    parsed = parse_tester_log_summary(log_path=log, tester_config=tester_config, attempt_id=attempt_id)

    assert parsed["status"] == "tester_log_observed"
    assert parsed["final_balance"] == 280.87
    assert parsed["final_balance_currency"] == "USD"
    assert parsed["orders_attempted"] == 7251
    assert parsed["rows_observed"] == 53554
    assert parsed["terminal_finished_result"] == "successfully finished"


def test_merge_decision_execution_rows_preserves_prep_order(tmp_path: Path) -> None:
    prep_index = (
        tmp_path
        / "lab"
        / "campaigns"
        / "campaign_us100_task_surface_scout_v0"
        / "synthesis"
        / "decision_replay_adapter_preparation_index.csv"
    )
    runtime_index = prep_index.with_name("decision_replay_runtime_execution_index.csv")
    prep_index.parent.mkdir(parents=True)
    prep_index.write_text(
        "attempt_id,source_attempt_id,run_id,bundle_id,cell_id,period_role,direction_policy,hold_bars,from_date,to_date,"
        "status,attempt_manifest_path,tester_config_path,source_score_telemetry_common_path,execution_telemetry_common_path,"
        "decision_family,score_high_threshold,runtime_period_set_id,tester_execution_profile_id,claim_boundary\n"
        "attempt_a,source_a,run_a,bundle_a,cell_a,validation,momentum_ret_1,6,2024.06.05,2025.03.10,prepared,a.yaml,a.ini,src_a,out_a,family,0.5,set,profile,boundary\n"
        "attempt_b,source_b,run_b,bundle_b,cell_b,research_oos,momentum_ret_1,6,2025.04.03,2025.11.21,prepared,b.yaml,b.ini,src_b,out_b,family,0.5,set,profile,boundary\n",
        encoding="utf-8",
    )
    runtime_index.write_text(
        ",".join(execution_index_fieldnames())
        + "\n"
        + "attempt_b,source_b,run_b,bundle_b,cell_b,research_oos,momentum_ret_1,2025.04.03,2025.11.21,completed,"
        + "runtime_probe,True,True,10,1,1,0,False,main,0,False,b_terminal.yaml,b_exec.yaml,b.csv,,boundary,next\n",
        encoding="utf-8",
    )

    merged = merge_execution_rows(
        tmp_path,
        [
            {
                "attempt_id": "attempt_a",
                "source_attempt_id": "source_a",
                "run_id": "run_a",
                "bundle_id": "bundle_a",
                "cell_id": "cell_a",
                "period_role": "validation",
                "direction_policy": "momentum_ret_1",
                "from_date": "2024.06.05",
                "to_date": "2025.03.10",
                "status": "completed",
            }
        ],
    )

    assert [row["attempt_id"] for row in merged] == ["attempt_a", "attempt_b"]
