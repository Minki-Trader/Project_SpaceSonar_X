from __future__ import annotations

from pathlib import Path

import yaml

from foundation.pipelines import open_wave01_event_barrier_decision_campaign as opener


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(rel_path: Path) -> dict:
    return yaml.safe_load((ROOT / rel_path).read_text(encoding="utf-8-sig"))


def test_event_barrier_campaign_is_multi_axis_and_not_synthesis() -> None:
    campaign = load_yaml(opener.NEW_CAMPAIGN_PATH)

    assert campaign["campaign_id"] == opener.NEW_CAMPAIGN_ID
    assert campaign["campaign_type"] == "standard_experiment"
    assert campaign["bounded_synthesis"]["enabled"] is False
    assert campaign["claim_boundary"] == opener.CLAIM_BOUNDARY

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
    assert campaign["next_action"] == opener.NEXT_WORK_ID


def test_feature_recipe_keeps_feature_count_variable() -> None:
    feature_recipe = load_yaml(opener.RECIPE_PATHS[opener.FEATURE_RECIPE_ID])

    assert feature_recipe["feature_count_policy"] == "variable_declared_per_run_no_fixed_count"
    assert "fixed_feature_count" in feature_recipe["forbidden_defaults"]
    assert "inherited_feature_list" in feature_recipe["forbidden_defaults"]
    assert feature_recipe["claim_boundary"] == "recipe_skeleton_only_not_feature_set_not_candidate"


def test_new_sweep_has_empty_run_refs_until_specs_materialize() -> None:
    run_refs = (ROOT / opener.NEW_RUN_REFS_PATH).read_text(encoding="utf-8-sig").splitlines()
    sweep = load_yaml(opener.NEW_SWEEP_PATH)

    assert sweep["status"] == "planned_not_executed"
    assert sweep["runtime_learning_probe_decision"]["decision"] == "L4_required_for_each_valid_proxy_model_bearing_run"
    assert len(run_refs) == 1
    assert run_refs[0].startswith("run_id,campaign_id,surface_id,sweep_id,status")
