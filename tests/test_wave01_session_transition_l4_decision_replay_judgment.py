from __future__ import annotations

from foundation.pipelines.judge_wave01_session_transition_l4_decision_replay_results import judge_pair


def test_session_transition_inverse_score_band_pair_loss_is_negative() -> None:
    rows = [
        {
            "cell_id": "wave01_st_cell_003",
            "period_role": "validation",
            "attempt_id": "validation_attempt",
            "execution_telemetry_observed": "True",
            "tester_final_balance": "373.44",
            "direction_policy": "score_band_inverse_side",
        },
        {
            "cell_id": "wave01_st_cell_003",
            "period_role": "research_oos",
            "attempt_id": "research_attempt",
            "execution_telemetry_observed": "True",
            "tester_final_balance": "429.89",
            "direction_policy": "score_band_inverse_side",
        },
    ]

    result = judge_pair("wave01_st_cell_003", rows, initial_deposit=500.0)

    assert result["result_judgment"] == "negative"
    assert result["l5_routing_status"] == "no_l5_decision_replay_log_balance_loss_observed"
    assert result["divergence_judgment"] == "mt5_decision_replay_negative_under_inverse_score_band_side"


def test_session_transition_pair_without_both_roles_is_inconclusive() -> None:
    rows = [
        {
            "cell_id": "wave01_st_cell_003",
            "period_role": "validation",
            "attempt_id": "validation_attempt",
            "execution_telemetry_observed": "True",
            "tester_final_balance": "373.44",
        }
    ]

    result = judge_pair("wave01_st_cell_003", rows, initial_deposit=500.0)

    assert result["result_judgment"] == "inconclusive"
    assert result["l5_routing_status"] == "no_l5_missing_period_role"

