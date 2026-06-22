from __future__ import annotations

from foundation.pipelines.prepare_wave01_session_transition_l4_decision_replay_attempts import (
    CLAIM_BOUNDARY,
    INVERSE_SCORE_BAND_POLICY,
    REPO_ROOT,
    build_records,
)


def test_session_transition_decision_replay_preparer_uses_thin_directional_path() -> None:
    summary, rows, eligibility, manifests, configs = build_records(
        REPO_ROOT,
        created_at_utc="2026-06-22T00:00:00Z",
        cell_id_filter="wave01_st_cell_003",
    )

    assert summary["execution_weight"] == "thin_first_pass"
    assert summary["counts"]["preserved_clue_count"] == 5
    assert summary["counts"]["direct_trade_adapter_eligible_cell_count"] == 1
    assert summary["counts"]["not_direct_trade_adapter_eligible_cell_count"] == 4
    assert summary["counts"]["prepared_attempt_count"] == 2
    assert summary["counts"]["period_role_counts"] == {"research_oos": 1, "validation": 1}
    assert set(row["cell_id"] for row in rows) == {"wave01_st_cell_003"}
    assert all(row["direction_policy"] == INVERSE_SCORE_BAND_POLICY for row in rows)
    assert all(row["decision_output"] == "score_ge_high_short_score_le_low_long_otherwise_flat" for row in rows)
    assert all(row["claim_boundary"] == CLAIM_BOUNDARY for row in rows)
    assert all("locked_final" not in row["period_role"] for row in rows)
    assert all(manifest["adapter_id"] for manifest in manifests.values())
    assert all("InpScoreLow=" in text for text in configs.values())
    assert all("InpDirectionPolicy=score_band_inverse_side" in text for text in configs.values())

    by_cell = {row["cell_id"]: row for row in eligibility}
    assert by_cell["wave01_st_cell_003"]["direct_trade_adapter_eligible"] == "true"
    assert by_cell["wave01_st_cell_003"]["prepared_attempt_count"] == 2
    assert by_cell["wave01_st_cell_002"]["eligibility_reason"] == "non_directional_event_score_requires_declared_side_surface"
    assert by_cell["wave01_st_cell_006"]["eligibility_reason"] == "diagnostic_or_no_trade_requires_new_decision_surface"
    assert by_cell["wave01_st_cell_009"]["eligibility_reason"] == "non_directional_event_score_requires_declared_side_surface"
    assert by_cell["wave01_st_cell_010"]["eligibility_reason"] == "diagnostic_or_no_trade_requires_new_decision_surface"

