from __future__ import annotations

from pathlib import Path

import yaml

from foundation.pipelines import materialize_wave01_event_barrier_first_batch_specs as materializer
from foundation.pipelines import open_wave01_event_barrier_decision_campaign as opener
from foundation.pipelines import run_wave01_event_barrier_proxy_batch as proxy_runner


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(rel_path: Path) -> dict:
    return yaml.safe_load((ROOT / rel_path).read_text(encoding="utf-8-sig"))


def test_event_barrier_campaign_is_multi_axis_and_not_synthesis() -> None:
    campaign = load_yaml(opener.NEW_CAMPAIGN_PATH)

    assert campaign["campaign_id"] == opener.NEW_CAMPAIGN_ID
    assert campaign["campaign_type"] == "standard_experiment"
    assert campaign["bounded_synthesis"]["enabled"] is False
    assert campaign["claim_boundary"] in {opener.CLAIM_BOUNDARY, materializer.CLAIM_BOUNDARY, proxy_runner.CLAIM_BOUNDARY}
    assert "runtime_authority" in campaign["forbidden_claims"]

    coverage = campaign["exploration_coverage"]
    assert coverage["mode"] == "unexplored_surface_discovery_not_single_axis_progression"
    assert {
        "target_or_label_surface",
        "feature_or_input_surface",
        "model_or_training_surface",
    }.issubset(set(coverage["required_research_axes"]))
    assert {
        "decision_surface",
        "horizon_or_holding_policy",
        "evaluation_or_runtime_surface",
    }.issubset(set(coverage["companion_axes"]))
    assert "repair_only_wave_or_campaign" in coverage["forbidden_research_shapes"]


def test_event_barrier_campaign_does_not_relabel_prior_repair() -> None:
    campaign = load_yaml(opener.NEW_CAMPAIGN_PATH)
    boundary = campaign["prior_material_boundary"]

    assert boundary["uses_prior_material_as"] == "prevention_boundary_only"
    assert boundary["source_negative_memory_ids"] == [
        "neg_wave0_decision_replay_momentum_ret_1_loss_v0"
    ]
    assert "do_not_relabel_momentum_ret_1_score_replay_as_new_candidate" in boundary["forbidden_carryover"]
    assert campaign["next_action"] in {opener.NEXT_WORK_ID, materializer.NEXT_WORK_ITEM_ID, proxy_runner.NEXT_WORK_ITEM_ID}


def test_feature_recipe_keeps_feature_count_variable() -> None:
    feature_recipe = load_yaml(opener.RECIPE_PATHS[opener.FEATURE_RECIPE_ID])

    assert feature_recipe["feature_count_policy"] == "variable_declared_per_run_no_fixed_count"
    assert "fixed_feature_count" in feature_recipe["forbidden_defaults"]
    assert "inherited_feature_list" in feature_recipe["forbidden_defaults"]
    assert feature_recipe["claim_boundary"] == "recipe_skeleton_only_not_feature_set_not_candidate"


def test_new_sweep_has_planned_run_refs_after_specs_materialize() -> None:
    run_refs = (ROOT / opener.NEW_RUN_REFS_PATH).read_text(encoding="utf-8-sig").splitlines()
    sweep = load_yaml(opener.NEW_SWEEP_PATH)

    assert sweep["status"] in {
        "planned_not_executed",
        "first_batch_specs_materialized_not_executed",
        "executed_proxy_observation_l4_required",
    }
    assert sweep["runtime_learning_probe_decision"]["decision"] == "L4_required_for_each_valid_proxy_model_bearing_run"
    assert len(run_refs) in {1, 13}
    assert run_refs[0].startswith(
        (
            "run_id,campaign_id,surface_id,sweep_id,status",
            "run_spec_id,planned_run_id,status",
            "run_spec_id,planned_run_id,run_id,status",
        )
    )
    if len(run_refs) == 13:
        assert all(("planned_not_executed" in row) or ("executed_proxy_observation_l4_required" in row) for row in run_refs[1:])
