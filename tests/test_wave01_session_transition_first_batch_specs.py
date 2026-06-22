from __future__ import annotations

import csv
from pathlib import Path

import yaml

from foundation.pipelines.materialize_wave01_session_transition_first_batch_specs import (
    CLAIM_BOUNDARY,
    first_batch_rows,
    validate_rows,
)


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "lab/campaigns/campaign_us100_session_transition_regime_surface_v0"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_session_transition_first_batch_rows_are_broad_and_l4_bound() -> None:
    rows = first_batch_rows()
    validate_rows(rows)

    assert len(rows) == 10
    assert len({row["label_surface"] for row in rows}) == 10
    assert len({row["feature_family"] for row in rows}) >= 6
    assert len({row["model_family"] for row in rows}) >= 3
    assert len({row["decision_family"] for row in rows}) >= 9
    assert len({row["session_anchor"] for row in rows}) >= 8
    assert all(row["runtime_level_required"] == "L4_split_runtime_probe" for row in rows)
    assert all(row["feature_count_policy"] == "variable_declared_per_run_no_fixed_count" for row in rows)
    assert not any(row["locked_final_oos_b_used"] for row in rows)
    assert {row["auxiliary_symbols"] for row in rows} == {"none"}


def test_session_transition_materialized_manifest_matches_policy() -> None:
    manifest = read_yaml(CAMPAIGN / "first_batch_run_specs_manifest.yaml")

    assert manifest["status"] == "first_batch_specs_materialized_not_executed"
    assert manifest["claim_boundary"] == CLAIM_BOUNDARY
    assert manifest["spec_count"] == 10
    assert manifest["coverage_summary"]["multi_axis_discovery"] is True
    assert manifest["coverage_summary"]["feature_only_or_label_only_or_model_only"] is False
    assert manifest["coverage_summary"]["valid_proxy_model_bearing_specs_require_L4"] is True
    assert manifest["coverage_summary"]["locked_final_oos_b_used"] is False
    assert manifest["coverage_summary"]["fixed_feature_count_used"] is False
    assert manifest["runtime_learning_probe_decision"]["target_level"] == "L4_split_runtime_probe"
    assert manifest["runtime_learning_probe_decision"]["required_period_roles"] == ["validation", "research_oos"]
    assert manifest["runtime_learning_probe_decision"]["proxy_only_closeout_allowed"] is False
    assert manifest["spec_source_policy"]["source_of_truth"] == "first_batch_matrix_row"
    assert manifest["spec_source_policy"]["per_run_manifest_creation"] == "defer_until_proxy_execution"
    assert "runtime_authority" in manifest["forbidden_claims"]
    assert "MT5_L4_not_run" in manifest["missing_evidence"]


def test_session_transition_run_specs_index_and_refs_are_matrix_backed_planned_only() -> None:
    index_rows = read_csv(CAMPAIGN / "run_specs_index.csv")
    ref_rows = read_csv(CAMPAIGN / "sweeps/sweep_us100_session_transition_broad_v0/run_refs.csv")

    assert len(index_rows) == 10
    assert len(ref_rows) == 10
    assert all(row["status"] == "planned_not_executed" for row in index_rows)
    assert all(row["claim_boundary"] == CLAIM_BOUNDARY for row in index_rows)
    assert all(row["runtime_level_required"] == "L4_split_runtime_probe" for row in index_rows)
    assert all(row["spec_source"] == "first_batch_matrix_row" for row in index_rows)
    assert all(row["matrix_path"].endswith("first_batch_matrix.csv") for row in index_rows)
    assert all(row["result_judgment"] == "not_evaluated" for row in ref_rows)
    assert all(row["spec_source"] == "first_batch_matrix_row" for row in ref_rows)
    assert all(row["matrix_path"].endswith("first_batch_matrix.csv") for row in ref_rows)
    assert all(row["next_action"] == "work_wave01_session_transition_execute_first_batch_proxy_v0" for row in ref_rows)


def test_session_transition_first_batch_does_not_precreate_run_local_specs() -> None:
    assert not list((CAMPAIGN / "run_specs").glob("wave01_st_cell_*.yaml"))
