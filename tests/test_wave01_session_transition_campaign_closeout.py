from __future__ import annotations

from pathlib import Path

from foundation.pipelines.close_wave01_session_transition_campaign import (
    CLAIM_BOUNDARY,
    build_closeout,
    build_remaining_preserved_clue_review,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_remaining_preserved_clue_review_keeps_non_directional_clues_out_of_l5() -> None:
    summary, rows, clue_memory = build_remaining_preserved_clue_review(
        REPO_ROOT,
        created_at_utc="2026-06-22T00:00:00Z",
    )

    assert summary["status"] == "remaining_preserved_clues_reviewed_requires_new_decision_surface"
    assert summary["claim_boundary"] == CLAIM_BOUNDARY
    assert summary["counts"]["source_preserved_clue_count"] == 5
    assert summary["counts"]["negative_memory_recorded_count"] == 1
    assert summary["counts"]["remaining_preserved_clue_count"] == 4
    assert summary["counts"]["remaining_non_directional_event_count"] == 2
    assert summary["counts"]["remaining_diagnostic_or_no_trade_count"] == 2
    assert summary["counts"]["candidate_count"] == 0
    assert summary["counts"]["l5_candidate_count"] == 0
    assert clue_memory["observed_cells"] == [
        "wave01_st_cell_002",
        "wave01_st_cell_006",
        "wave01_st_cell_009",
        "wave01_st_cell_010",
    ]

    row_by_cell = {row["cell_id"]: row for row in rows}
    assert row_by_cell["wave01_st_cell_003"]["closeout_judgment"] == "negative_memory_recorded"
    assert row_by_cell["wave01_st_cell_002"]["l5_routing_status"] == "no_l5_preserved_clue_requires_declared_side_surface"
    assert row_by_cell["wave01_st_cell_006"]["l5_routing_status"] == "no_l5_preserved_clue_requires_trade_surface"


def test_session_transition_campaign_closeout_has_no_candidate_claim() -> None:
    closeout = build_closeout(REPO_ROOT, "2026-06-22T00:00:00Z")

    assert closeout["status"] == "wave01_session_transition_closed_preserved_clues_no_candidate"
    assert closeout["result_judgment"] == "preserved_clue"
    assert closeout["claim_boundary"] == CLAIM_BOUNDARY
    assert closeout["counts"]["valid_proxy_model_bearing_run_count"] == 10
    assert closeout["counts"]["decision_replay_negative_count"] == 1
    assert closeout["counts"]["remaining_preserved_clue_count"] == 4
    assert closeout["counts"]["candidate_count"] == 0
    assert closeout["counts"]["l5_candidate_count"] == 0
    assert "runtime_authority" in closeout["forbidden_claims"]
    assert "goal_achieve" in closeout["forbidden_claims"]
