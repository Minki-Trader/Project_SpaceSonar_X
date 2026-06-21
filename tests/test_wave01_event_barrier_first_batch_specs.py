from __future__ import annotations

import csv
from pathlib import Path

import yaml

from foundation.pipelines.materialize_wave01_event_barrier_first_batch_specs import (
    CLAIM_BOUNDARY,
    first_batch_rows,
    validate_rows,
)
from foundation.pipelines.run_wave01_event_barrier_proxy_batch import CLAIM_BOUNDARY as EXECUTED_CLAIM_BOUNDARY


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_wave01_first_batch_design_rows_are_broad_and_l4_bound() -> None:
    rows = first_batch_rows()
    validate_rows(rows)

    assert len({row["label_surface"] for row in rows}) >= 10
    assert len({row["feature_family"] for row in rows}) >= 3
    assert len({row["model_family"] for row in rows}) >= 3
    assert len({row["decision_family"] for row in rows}) >= 10
    assert all(row["runtime_level_required"] == "L4_split_runtime_probe" for row in rows)
    assert all(row["feature_count_policy"] == "variable_declared_per_run_no_fixed_count" for row in rows)
    assert not any(row["locked_final_oos_b_used"] for row in rows)
    assert {row["auxiliary_symbols"] for row in rows} == {"none"}


def test_wave01_materialized_first_batch_manifest_matches_policy() -> None:
    manifest = read_yaml(CAMPAIGN / "first_batch_run_specs_manifest.yaml")

    assert manifest["status"] in {
        "first_batch_specs_materialized_not_executed",
        "executed_proxy_observation_l4_required",
    }
    assert manifest["claim_boundary"] in {CLAIM_BOUNDARY, EXECUTED_CLAIM_BOUNDARY}
    assert manifest["spec_count"] == 12
    assert manifest["coverage_summary"]["multi_axis_discovery"] is True
    assert manifest["coverage_summary"]["feature_only_or_label_only_or_model_only"] is False
    assert manifest["coverage_summary"]["valid_proxy_model_bearing_specs_require_L4"] is True
    assert manifest["coverage_summary"]["locked_final_oos_b_used"] is False
    assert manifest["runtime_learning_probe_decision"]["target_level"] == "L4_split_runtime_probe"
    assert manifest["runtime_learning_probe_decision"]["required_period_roles"] == ["validation", "research_oos"]
    assert "runtime_authority" in manifest["forbidden_claims"]
    assert any("MT5_L4" in item for item in manifest["missing_evidence"])


def test_wave01_run_specs_index_and_refs_keep_specs_and_link_runs_after_execution() -> None:
    index_rows = read_csv(CAMPAIGN / "run_specs_index.csv")
    ref_rows = read_csv(CAMPAIGN / "sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv")

    assert len(index_rows) == 12
    assert len(ref_rows) == 12
    assert all(row["status"] == "planned_not_executed" for row in index_rows)
    assert all(row["claim_boundary"] == CLAIM_BOUNDARY for row in index_rows)
    assert "run_spec_path" in ref_rows[0]
    if "run_manifest_path" in ref_rows[0]:
        assert all(row["run_manifest_path"].startswith("lab/runs/") for row in ref_rows)
        assert all(row["claim_boundary"] == EXECUTED_CLAIM_BOUNDARY for row in ref_rows)
        assert all(row["next_action"] == "work_wave01_event_barrier_l4_materialization_preflight_v0" for row in ref_rows)
    else:
        assert all(row["result_judgment"] == "not_evaluated" for row in ref_rows)


def test_wave01_each_run_spec_preserves_blank_slate_and_parity_contract() -> None:
    spec_paths = sorted((CAMPAIGN / "run_specs").glob("wave01_eb_cell_*.yaml"))
    assert len(spec_paths) == 12

    for path in spec_paths:
        spec = read_yaml(path)
        assert spec["status"] == "planned_not_executed"
        assert spec["claim_boundary"] == CLAIM_BOUNDARY
        assert spec["data_contract"]["locked_final_oos_b_used"] is False
        assert spec["data_contract"]["auxiliary_symbols"] == "none"
        assert spec["feature_contract"]["feature_count_policy"] == "variable_declared_per_run_no_fixed_count"
        assert "fixed_feature_count" in spec["feature_contract"]["forbidden_defaults"]
        assert spec["runtime_learning_probe_decision"]["target_level"] == "L4_split_runtime_probe"
        assert spec["runtime_learning_probe_decision"]["proxy_only_closeout_allowed"] is False
        assert spec["proxy_runtime_parity"]["minimum_reconciliation_attempt"]["required"] is True
        assert "price_distance_conversion" in spec["proxy_runtime_parity"]["unit_semantics"]
        assert spec["result_judgment"] == "not_evaluated"
