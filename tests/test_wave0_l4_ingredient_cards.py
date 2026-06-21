from __future__ import annotations

from foundation.pipelines.materialize_wave0_l4_ingredient_cards import (
    CLAIM_BOUNDARY,
    clue_ids_by_run,
    do_not_repeat_for,
    ingredient_card_id,
    materialization_status,
    parse_args,
    source_clue_value,
)


def test_ingredient_card_ids_are_cell_scoped() -> None:
    assert ingredient_card_id("wave0_cell_011") == "ingredient_wave0_cell_011_l4_runtime_score_observed_v0"


def test_clue_ids_by_run_expands_axis_review_preserved_clues() -> None:
    axis_review = {
        "preserved_clues": [
            {"clue_id": "clue_a", "run_ids": ["run_1", "run_2"]},
            {"clue_id": "clue_b", "run_ids": ["run_2"]},
        ]
    }

    assert clue_ids_by_run(axis_review) == {"run_1": ["clue_a"], "run_2": ["clue_a", "clue_b"]}


def test_materialization_status_keeps_diagnostic_controls_out_of_candidate_path() -> None:
    assert materialization_status("diagnostic_rank_only", "no_l5_diagnostic_score_probe_only") == (
        "ingredient_ready_diagnostic_runtime_score_control"
    )
    assert materialization_status(
        "abstain_capable_direction_agnostic_tradeability",
        "no_l5_yet_requires_trading_or_sparse_decision_tester_adapter",
    ) == "ingredient_ready_requires_decision_execution_adapter"


def test_do_not_repeat_for_blocks_l5_from_score_telemetry() -> None:
    text = do_not_repeat_for(
        {"decision_family": "abstain_capable_direction_agnostic_tradeability"},
        {"do_not_repeat_note": "do_not_treat_as_candidate"},
    )

    assert "do_not_treat_as_candidate" in text
    assert "do_not_open_L5" in text


def test_claim_boundary_and_parser_defaults_are_lowered() -> None:
    args = parse_args([])

    assert args.write_control_records is False
    assert "no_candidate" in CLAIM_BOUNDARY
    assert source_clue_value(["a", "b"]) == "a;b"
