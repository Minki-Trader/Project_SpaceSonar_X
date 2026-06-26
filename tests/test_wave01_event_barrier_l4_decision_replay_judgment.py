from __future__ import annotations

from pathlib import Path

from foundation.pipelines.judge_wave01_event_barrier_l4_decision_replay_results import (
    CLAIM_BOUNDARY,
    balance_delta,
    build_judgment_rows,
    classify_decision_pair,
    judgment_index_fieldnames,
    parse_args,
)


def test_wave01_decision_replay_judgment_defaults_do_not_update_control_records() -> None:
    args = parse_args([])

    assert args.write_control_records is False


def test_score_band_loss_in_both_periods_becomes_negative_without_l5() -> None:
    result = classify_decision_pair(
        375.39,
        424.62,
        tester_report_pair_observed=False,
        open_failed_count=12,
    )

    assert result["final_balance_pair_class"] == "loss_in_validation_and_research_oos"
    assert result["result_judgment"] == "negative"
    assert result["l5_routing_status"] == "no_l5_decision_replay_loss_observed"
    assert "do not continue" in result["next_action"]


def test_non_loss_without_reports_or_open_failed_audit_is_not_auto_candidate() -> None:
    result = classify_decision_pair(
        520.0,
        510.0,
        tester_report_pair_observed=False,
        open_failed_count=1,
    )

    assert result["result_judgment"] == "preserved_clue"
    assert result["l5_routing_status"] == "l5_review_required_report_equity_or_open_failed_audit"


def test_missing_balance_stays_inconclusive_not_negative() -> None:
    result = classify_decision_pair(
        None,
        424.62,
        tester_report_pair_observed=False,
        open_failed_count=0,
    )

    assert result["result_judgment"] == "inconclusive"
    assert result["l5_routing_status"] == "no_l5_missing_tester_log_balance"


def test_balance_delta_uses_current_tester_deposit_baseline() -> None:
    assert balance_delta(375.39) == -124.61
    assert balance_delta(500.0) == 0.0


def test_wave01_decision_judgment_index_tracks_runtime_friction_fields() -> None:
    fields = judgment_index_fieldnames()

    assert "total_open_failed_count" in fields
    assert "validation_report_total_trades" in fields
    assert "research_oos_report_profit_factor" in fields
    assert "validation_terminal_timed_out" in fields
    assert "prevention_memory" in fields
    assert "no_economics_pass" in CLAIM_BOUNDARY


def test_judgment_rows_parse_tester_report_kpis_when_reports_exist(tmp_path: Path) -> None:
    campaign_root = tmp_path / "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through"
    decision_root = campaign_root / "decision_replay"
    decision_root.mkdir(parents=True)
    (campaign_root / "l4_pair_judgment_index.csv").write_text(
        "cell_id,decision_family,proxy_judgment\n"
        "wave01_eb_cell_002,breakout_entry_abstain_timeout_exit,preserved_clue\n",
        encoding="utf-8",
    )
    fixture = Path("tests/fixtures/mt5_strategy_tester_report_minimal.html").read_text(encoding="utf-8")
    rows = []
    for role in ["validation", "research_oos"]:
        attempt_id = f"attempt_{role}"
        report_path = tmp_path / f"runtime/mt5_attempts/{attempt_id}/reports/tester_report.htm"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(fixture, encoding="utf-8")
        rows.append(
            {
                "attempt_id": attempt_id,
                "run_id": "run_demo_v0",
                "bundle_id": "bundle_demo_v0",
                "cell_id": "wave01_eb_cell_002",
                "period_role": role,
                "direction_policy": "score_band_side",
                "tester_final_balance": "490.00",
                "open_action_count": "1",
                "close_action_count": "1",
                "open_failed_count": "0",
                "execution_telemetry_observed": "True",
                "tester_log_observed": "True",
                "tester_report_observed": "True",
                "terminal_timed_out": "False",
                "tester_report_path": f"runtime/mt5_attempts/{attempt_id}/reports/tester_report.htm",
                "terminal_run_summary_path": "",
                "execution_telemetry_summary_path": "",
                "tester_log_summary_path": "",
            }
        )
    fieldnames = list(rows[0])
    decision_root.joinpath("runtime_execution_index.csv").write_text(
        ",".join(fieldnames) + "\n" + "\n".join(",".join(row[field] for field in fieldnames) for row in rows) + "\n",
        encoding="utf-8",
    )

    [row] = build_judgment_rows(tmp_path)

    assert row["tester_report_pair_observed"] == "true"
    assert row["validation_report_total_trades"] == "1"
    assert row["research_oos_report_profit_factor"] == "1"
    assert "tester_report_missing" not in row["missing_evidence"]
    assert "pf_dd_trade_list_metrics_missing" not in row["missing_evidence"]
