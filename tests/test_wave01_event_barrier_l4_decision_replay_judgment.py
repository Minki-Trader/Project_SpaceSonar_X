from __future__ import annotations

from foundation.pipelines.judge_wave01_event_barrier_l4_decision_replay_results import (
    CLAIM_BOUNDARY,
    balance_delta,
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
    assert "validation_terminal_timed_out" in fields
    assert "prevention_memory" in fields
    assert "no_economics_pass" in CLAIM_BOUNDARY
