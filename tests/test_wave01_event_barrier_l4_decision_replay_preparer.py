from __future__ import annotations

from foundation.pipelines.prepare_wave01_event_barrier_l4_decision_replay_attempts import (
    CLAIM_BOUNDARY,
    DIRECTION_POLICY,
    REPO_ROOT,
    build_records,
)


def test_wave01_decision_replay_preparer_routes_preserved_clues_by_decision_surface() -> None:
    summary, rows, eligibility, manifests, configs = build_records(
        REPO_ROOT,
        created_at_utc="2026-06-22T00:00:00Z",
    )

    assert summary["counts"]["preserved_clue_count"] == 8
    assert summary["counts"]["direct_trade_adapter_eligible_cell_count"] == 5
    assert summary["counts"]["not_direct_trade_adapter_eligible_cell_count"] == 3
    assert summary["counts"]["prepared_attempt_count"] == 10
    assert summary["counts"]["period_role_counts"] == {"research_oos": 5, "validation": 5}
    assert set(row["cell_id"] for row in rows) == {
        "wave01_eb_cell_002",
        "wave01_eb_cell_006",
        "wave01_eb_cell_007",
        "wave01_eb_cell_008",
        "wave01_eb_cell_011",
    }
    assert all(row["direction_policy"] == DIRECTION_POLICY for row in rows)
    assert all(row["claim_boundary"] == CLAIM_BOUNDARY for row in rows)
    assert all(manifest["adapter_id"] for manifest in manifests.values())
    assert all("InpScoreLow=" in text for text in configs.values())
    assert all("InpDirectionPolicy=score_band_side" in text for text in configs.values())

    by_cell = {row["cell_id"]: row for row in eligibility}
    assert by_cell["wave01_eb_cell_002"]["direct_trade_adapter_eligible"] == "true"
    assert by_cell["wave01_eb_cell_004"]["eligibility_reason"] == (
        "requires_new_decision_surface_not_direct_trade_adapter"
    )
    assert by_cell["wave01_eb_cell_012"]["direct_trade_adapter_eligible"] == "false"
