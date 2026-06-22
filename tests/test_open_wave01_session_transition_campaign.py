from __future__ import annotations

from pathlib import Path

import yaml

from foundation.pipelines import open_wave01_session_transition_regime_campaign as opener
from foundation.pipelines import materialize_wave01_session_transition_first_batch_specs as materializer


ROOT = Path(__file__).resolve().parents[1]
PROXY_CLAIM_BOUNDARY = "wave01_session_transition_proxy_batch_l4_required_no_candidate_no_baseline_no_runtime_authority"
PROXY_STATUS = "executed_proxy_observation_l4_required"
CLOSED_CLAIM_BOUNDARY = (
    "wave01_session_transition_campaign_closed_preserved_clues_no_candidate_no_l5_"
    "no_runtime_authority_no_economics_pass"
)
CLOSED_STATUS = "wave01_session_transition_closed_preserved_clues_no_candidate"


def load_yaml(rel_path: Path) -> dict:
    return yaml.safe_load((ROOT / rel_path).read_text(encoding="utf-8-sig"))


def test_session_transition_campaign_is_multi_axis_not_repair() -> None:
    campaign = load_yaml(opener.NEW_CAMPAIGN_PATH)

    assert campaign["campaign_id"] == opener.NEW_CAMPAIGN_ID
    assert campaign["campaign_type"] == "standard_experiment"
    assert campaign["bounded_synthesis"]["enabled"] is False
    assert campaign["claim_boundary"] in {
        opener.CLAIM_BOUNDARY,
        materializer.CLAIM_BOUNDARY,
        PROXY_CLAIM_BOUNDARY,
        CLOSED_CLAIM_BOUNDARY,
    }
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

    boundary = campaign["prior_material_boundary"]
    assert boundary["uses_prior_material_as"] == "prevention_boundary_only"
    assert "do_not_relabel_score_band_side_replay_as_new_candidate" in boundary["forbidden_carryover"]
    assert "do_not_turn_event_barrier_repair_into_session_transition_hypothesis" in boundary["forbidden_carryover"]


def test_session_transition_feature_recipe_keeps_feature_count_variable() -> None:
    feature_recipe = load_yaml(opener.RECIPE_PATHS[opener.FEATURE_RECIPE_ID])

    assert feature_recipe["feature_count_policy"] == "variable_declared_per_run_no_fixed_count"
    assert "fixed_feature_count" in feature_recipe["forbidden_defaults"]
    assert "inherited_feature_list" in feature_recipe["forbidden_defaults"]
    assert feature_recipe["claim_boundary"] == "recipe_skeleton_only_no_candidate_no_runtime_authority"


def test_session_transition_sweep_starts_empty_with_l4_follow_through() -> None:
    sweep = load_yaml(opener.NEW_SWEEP_PATH)
    run_refs = (ROOT / opener.NEW_RUN_REFS_PATH).read_text(encoding="utf-8-sig").splitlines()

    assert sweep["status"] in {"planned_not_executed", materializer.STATUS, PROXY_STATUS, CLOSED_STATUS}
    assert sweep["runtime_learning_probe_decision"]["decision"] == "L4_required_for_each_valid_proxy_model_bearing_run"
    assert run_refs[0].split(",")[:4] == ["run_id", "campaign_id", "surface_id", "sweep_id"]
    if sweep["status"] == "planned_not_executed":
        assert len(run_refs) == 1
    elif sweep["status"] == materializer.STATUS:
        assert len(run_refs) == 11
        assert "run_spec_id" in run_refs[0]
        assert "not_evaluated" in "\n".join(run_refs)
    else:
        assert len(run_refs) == 11
        assert "run_spec_id" in run_refs[0]
        assert any(status in "\n".join(run_refs) for status in [PROXY_STATUS, CLOSED_STATUS])
