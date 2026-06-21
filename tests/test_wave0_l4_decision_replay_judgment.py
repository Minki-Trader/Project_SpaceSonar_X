from __future__ import annotations

from foundation.pipelines.judge_wave0_l4_decision_replay_results import (
    CLAIM_BOUNDARY,
    balance_delta,
    classify_decision_pair,
    judgment_index_fieldnames,
    parse_args,
)


def test_decision_replay_judgment_defaults_do_not_update_control_records() -> None:
    args = parse_args([])

    assert args.write_control_records is False


def test_loss_in_both_periods_becomes_negative_without_l5() -> None:
    result = classify_decision_pair(280.87, 389.87)

    assert result["final_balance_pair_class"] == "loss_in_validation_and_research_oos"
    assert result["result_judgment"] == "negative"
    assert result["l5_routing_status"] == "no_l5_decision_replay_loss_observed"
    assert "do not continue" in result["next_action"]


def test_missing_balance_stays_inconclusive_not_negative() -> None:
    result = classify_decision_pair(None, 389.87)

    assert result["result_judgment"] == "inconclusive"
    assert result["l5_routing_status"] == "no_l5_missing_tester_log_balance"


def test_balance_delta_uses_current_tester_deposit_baseline() -> None:
    assert balance_delta(280.87) == -219.13
    assert balance_delta(500.0) == 0.0


def test_decision_judgment_index_tracks_claim_and_prevention_memory() -> None:
    fields = judgment_index_fieldnames()

    assert "claim_boundary" in fields
    assert "prevention_memory" in fields
    assert "l5_routing_status" in fields
    assert "no_economics_pass" in CLAIM_BOUNDARY
