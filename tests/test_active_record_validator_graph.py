from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from foundation.validation.active_record_validator import FIXTURE_GATE, validate


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_evidence_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name in ["docs", "lab", "runtime"]:
        shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(
        ROOT / "foundation" / "mt5",
        repo / "foundation" / "mt5",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return repo


def active_ids(repo: Path) -> tuple[str, str, str]:
    state = load_yaml(repo / "docs" / "workspace" / "workspace_state.yaml")
    claims = state["current_claims"]
    return (
        claims["first_vertical_slice_run_id"],
        claims["first_vertical_slice_bundle_id"],
        claims["first_vertical_slice_attempt_id"],
    )


def test_active_validator_rejects_stale_receipt_after_mt5_closeout(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    run_id, _bundle_id, _attempt_id = active_ids(repo)
    receipt_path = repo / "lab" / "runs" / run_id / "experiment_receipt.yaml"
    receipt = load_yaml(receipt_path)
    coverage = receipt["required_gate_coverage"]
    coverage["passed"] = [item for item in coverage["passed"] if item != FIXTURE_GATE]
    coverage["missing"] = [*coverage.get("missing", []), FIXTURE_GATE]
    receipt["missing_evidence"] = ["MT5 native ONNX fixed-fixture output not observed yet"]
    receipt["claim_boundary"] = "bundle_preflight"
    receipt["result_judgment"] = "inconclusive"
    write_yaml(receipt_path, receipt)

    errors = validate(repo)

    assert any("receipt" in error and FIXTURE_GATE in error for error in errors)


def test_active_validator_rejects_registry_path_missing_from_lineage(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    run_id, _bundle_id, _attempt_id = active_ids(repo)
    lineage_path = repo / "lab" / "runs" / run_id / "artifact_lineage.json"
    lineage = load_json(lineage_path)
    lineage["artifact_paths"] = [
        item
        for item in lineage["artifact_paths"]
        if not (isinstance(item, dict) and item.get("path", "").endswith("mt5_probe_summary.yaml"))
    ]
    write_json(lineage_path, lineage)

    errors = validate(repo)

    assert any("registry path missing from lineage" in error and "mt5_probe_summary.yaml" in error for error in errors)


def test_active_validator_rejects_completed_campaign_with_planning_status(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_path = repo / "lab" / "campaigns" / "campaign_minimal_onnx_mt5_vertical_slice_v0" / "campaign_manifest.yaml"
    campaign = load_yaml(campaign_path)
    campaign["vertical_slice_entry_contract"]["dataset"]["status"] = "to_materialize_in_target_branch"
    write_yaml(campaign_path, campaign)

    errors = validate(repo)

    assert any("completed campaign retains planning status" in error for error in errors)


def test_active_validator_rejects_missing_ea_entrypoint_hash(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    _run_id, _bundle_id, attempt_id = active_ids(repo)
    attempt_path = repo / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    attempt = load_yaml(attempt_path)
    attempt["artifact_identity"]["ea_entrypoint"]["sha256"] = None
    write_yaml(attempt_path, attempt)

    errors = validate(repo)

    assert any("ea_entrypoint sha256 is missing" in error for error in errors)


def test_active_validator_rejects_bad_bounded_synthesis_mix_depth(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_mix_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    write_yaml(
        campaign_path,
        {
            "campaign_id": campaign_id,
            "campaign_type": "bounded_synthesis",
            "bounded_synthesis": {
                "enabled": True,
                "source_scope": "previous_material_only",
                "source_campaign_ids": ["campaign_minimal_onnx_mt5_vertical_slice_v0"],
                "mix_depth_policy": {
                    "default_sequence": ["mix-3"],
                    "mix4_policy": "exception_only_with_recorded_reason",
                    "mix5_plus_policy": "forbidden",
                },
                "next_wave_influence": "forbidden_reference_only",
                "runtime_follow_through": {
                    "valid_proxy_model_bearing_mix_requires_l4": True,
                    "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
                },
                "claim_boundary": (
                    "synthesis_learning_only_no_next_wave_direction_"
                    "no_selected_baseline_no_runtime_authority"
                ),
            },
        },
    )

    errors = validate(repo)

    assert any("bounded synthesis mix depth" in error for error in errors)


def test_active_validator_rejects_synthesis_next_wave_influence(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_influence_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    write_yaml(
        campaign_path,
        {
            "campaign_id": campaign_id,
            "campaign_type": "bounded_synthesis",
            "bounded_synthesis": {
                "enabled": True,
                "source_scope": "previous_material_only",
                "source_campaign_ids": ["campaign_minimal_onnx_mt5_vertical_slice_v0"],
                "mix_depth_policy": {
                    "default_sequence": ["mix-2", "mix-3"],
                    "mix4_policy": "exception_only_with_recorded_reason",
                    "mix5_plus_policy": "forbidden",
                },
                "next_wave_influence": "allowed_to_direct_next_wave",
                "runtime_follow_through": {
                    "valid_proxy_model_bearing_mix_requires_l4": True,
                    "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
                },
                "claim_boundary": (
                    "synthesis_learning_only_no_next_wave_direction_"
                    "no_selected_baseline_no_runtime_authority"
                ),
            },
        },
    )

    errors = validate(repo)

    assert any("next_wave_influence must be forbidden" in error for error in errors)


def test_active_validator_rejects_research_campaign_missing_exploration_coverage(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_path = repo / "lab" / "campaigns" / "campaign_us100_task_surface_scout_v0" / "campaign_manifest.yaml"
    campaign = load_yaml(campaign_path)
    campaign.pop("exploration_coverage", None)
    write_yaml(campaign_path, campaign)

    errors = validate(repo)

    assert any("research campaign missing exploration_coverage" in error for error in errors)


def test_active_validator_rejects_research_campaign_missing_model_axis(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_path = repo / "lab" / "campaigns" / "campaign_us100_task_surface_scout_v0" / "campaign_manifest.yaml"
    campaign = load_yaml(campaign_path)
    campaign["exploration_coverage"]["required_research_axes"] = [
        "target_or_label_surface",
        "feature_or_input_surface",
    ]
    write_yaml(campaign_path, campaign)

    errors = validate(repo)

    assert any("exploration_coverage missing research axes" in error and "model_or_training_surface" in error for error in errors)


def test_active_validator_rejects_campaign_registry_status_drift(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    registry_path = repo / "docs" / "registers" / "campaign_registry.csv"
    rows = registry_path.read_text(encoding="utf-8").splitlines()
    rows = [
        line.replace("decision_replay_judgment_closed_no_candidate", "stale_status", 1)
        if line.startswith("campaign_us100_task_surface_scout_v0,")
        else line
        for line in rows
    ]
    registry_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    errors = validate(repo)

    assert any("campaign_registry.csv campaign_us100_task_surface_scout_v0: status mismatch" in error for error in errors)


def test_active_validator_rejects_wave_campaign_ref_status_drift(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    refs_path = repo / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0" / "campaign_refs.csv"
    rows = refs_path.read_text(encoding="utf-8").splitlines()
    rows = [
        line.replace("decision_replay_judgment_closed_no_candidate", "stale_status", 1)
        if line.startswith("wave_us100_closedbar_surface_cartography_v0,campaign_us100_task_surface_scout_v0,")
        else line
        for line in rows
    ]
    refs_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    errors = validate(repo)

    assert any("campaign_refs.csv campaign_us100_task_surface_scout_v0: status mismatch" in error for error in errors)


def test_active_validator_rejects_missing_goal_objective_revision(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    state_path = repo / "docs" / "workspace" / "workspace_state.yaml"
    state = load_yaml(state_path)
    state["current_claims"]["active_goal_objective_revision"] = (
        "lab/goals/goal_us100_onnx_forward_boundary_v0/missing_goal_revision.yaml"
    )
    write_yaml(state_path, state)

    errors = validate(repo)

    assert any("missing objective revision" in error for error in errors)


def test_active_validator_rejects_goal_objective_hash_mismatch(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    goal_path = repo / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "goal_manifest.yaml"
    goal = load_yaml(goal_path)
    goal["objective_identity"]["content_hash_sha256"] = "0" * 64
    write_yaml(goal_path, goal)

    errors = validate(repo)

    assert any("objective revision sha256 mismatch" in error for error in errors)


def test_active_validator_rejects_try_first_dispositions_without_try_first_record(tmp_path: Path) -> None:
    for judgment in ["blocked", "deferred", "invalid", "discarded", "blocked_retry"]:
        repo = copy_evidence_repo(tmp_path / judgment)
        run_id, _bundle_id, _attempt_id = active_ids(repo)
        receipt_path = repo / "lab" / "runs" / run_id / "experiment_receipt.yaml"
        receipt = load_yaml(receipt_path)
        receipt["result_judgment"] = judgment
        receipt["failure_disposition"] = {
            "status": "missing_adapter",
            "failure_reproduction": None,
            "exact_failing_layer": None,
            "repair_or_fallback_attempts": [],
            "attempt_blocker_if_no_repair": None,
            "evidence_paths": [],
            "remaining_blocker": None,
            "reopen_condition": None,
        }
        write_yaml(receipt_path, receipt)

        errors = validate(repo)

        assert any(f"{judgment} requires failure reproduction" in error for error in errors)
        assert any(f"{judgment} requires bounded repair/fallback attempt" in error for error in errors)


def test_active_validator_rejects_try_first_status_prefix_without_record(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    run_id, _bundle_id, _attempt_id = active_ids(repo)
    manifest_path = repo / "lab" / "runs" / run_id / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest["status"] = "deferred_missing_conversion_adapter"
    manifest["failure_disposition"] = {
        "status": "missing_conversion_adapter",
        "failure_reproduction": None,
        "exact_failing_layer": None,
        "repair_or_fallback_attempts": [],
        "attempt_blocker_if_no_repair": None,
        "evidence_paths": [],
        "remaining_blocker": None,
        "reopen_condition": None,
    }
    write_json(manifest_path, manifest)

    errors = validate(repo)

    assert any("deferred_missing_conversion_adapter requires failure reproduction" in error for error in errors)
    assert any("deferred_missing_conversion_adapter requires bounded repair/fallback attempt" in error for error in errors)
