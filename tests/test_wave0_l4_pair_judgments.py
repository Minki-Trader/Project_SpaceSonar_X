from __future__ import annotations

from foundation.pipelines.aggregate_wave0_l4_pair_judgments import (
    CLAIM_BOUNDARY,
    classify_proxy_runtime,
    l5_routing_decision,
    pair_index_fieldnames,
    parse_args,
)


def test_pair_aggregator_defaults_do_not_update_control_records() -> None:
    args = parse_args([])

    assert args.write_control_records is False


def test_classify_proxy_runtime_keeps_preserved_clue_boundary() -> None:
    assert classify_proxy_runtime("preserved_clue", True) == "proxy_preserved_clue_runtime_score_observed"
    assert classify_proxy_runtime("inconclusive", True) == "proxy_inconclusive_runtime_score_observed"
    assert classify_proxy_runtime("preserved_clue", False) == "proxy_observed_runtime_score_missing_or_partial"


def test_l5_routing_does_not_promote_non_trading_score_probe() -> None:
    status, next_action = l5_routing_decision(
        both_observed=True,
        tester_reports_observed=False,
        decision_family="abstain_capable_direction_agnostic_tradeability",
        proxy_judgment="preserved_clue",
    )

    assert status == "no_l5_yet_requires_trading_or_sparse_decision_tester_adapter"
    assert "score telemetry alone is not economics evidence" in next_action


def test_l5_routing_keeps_diagnostic_surfaces_out_of_candidate_path() -> None:
    status, next_action = l5_routing_decision(
        both_observed=True,
        tester_reports_observed=False,
        decision_family="diagnostic_rank_only",
        proxy_judgment="inconclusive",
    )

    assert status == "no_l5_diagnostic_score_probe_only"
    assert "rotate" in next_action


def test_pair_index_has_claim_and_next_action_fields() -> None:
    fields = pair_index_fieldnames()

    assert "claim_boundary" in fields
    assert "next_action" in fields
    assert "l5_routing_status" in fields
    assert "no_runtime_authority" in CLAIM_BOUNDARY
