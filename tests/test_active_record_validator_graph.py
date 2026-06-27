from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from spacesonar.control_plane.store import filesystem_path
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
    for name in ["docs", "lab"]:
        shutil.copytree(
            filesystem_path(ROOT / name),
            filesystem_path(repo / name),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    shutil.copytree(
        filesystem_path(ROOT / "runtime"),
        filesystem_path(repo / "runtime"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "telemetry", "reports"),
    )
    shutil.copytree(
        filesystem_path(ROOT / "foundation" / "mt5"),
        filesystem_path(repo / "foundation" / "mt5"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return repo


def active_ids(repo: Path) -> tuple[str, str, str]:
    state = load_yaml(repo / "docs" / "workspace" / "workspace_state.yaml")
    claims = state.get("current_claims")
    if claims:
        return (
            claims["first_vertical_slice_run_id"],
            claims["first_vertical_slice_bundle_id"],
            claims["first_vertical_slice_attempt_id"],
        )
    return (
        "onnxlab_20260621T131542Z_minimal_onnx_mt5_plumbing",
        "bundle_20260621T131542Z_fixture_plumbing_v0",
        "attempt_20260621T131542Z_mt5_onnx_fixture_v0",
    )


def bounded_synthesis_campaign(campaign_id: str, **synthesis_overrides: Any) -> dict[str, Any]:
    source_campaign_ids = [f"campaign_source_{index:02d}_v0" for index in range(1, 6)]
    synthesis = {
        "enabled": True,
        "source_scope": "previous_material_only",
        "cadence": {
            "trigger": "after_5_standard_campaign_closeouts",
            "standard_campaign_closeout_count_required": 5,
            "counting_scope": "since_last_bounded_synthesis_campaign",
            "counted_standard_campaign_ids": source_campaign_ids,
            "early_open_exception_reason": "",
        },
        "source_campaign_ids": source_campaign_ids,
        "mix_queue_path": f"lab/campaigns/{campaign_id}/synthesis/mix_queue.yaml",
        "mix_depth_policy": {
            "default_sequence": ["mix-2", "mix-3"],
            "mix4_policy": "exception_only_with_recorded_reason",
            "mix5_plus_policy": "forbidden",
        },
        "ingredient_lifecycle_policy": {
            "raw_reuse_default": "forbidden_after_consumed_by_completed_synthesis",
            "allowed_reuse_statuses": ["carry_forward_ingredient", "reopened_ingredient_exception"],
            "carry_forward_requires_source_synthesis": True,
            "reopened_exception_requires_reason": True,
        },
        "kpi_policy": {
            "ledger_required": True,
            "stage_kind": "special_mixing",
            "same_fixed_schema_as_campaign_wave": True,
            "overall_and_segment_breakdowns_required": True,
        },
        "next_wave_influence": "forbidden_reference_only",
        "runtime_follow_through": {
            "valid_proxy_model_bearing_mix_requires_l4": True,
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "claim_boundary": (
            "synthesis_learning_only_no_next_wave_direction_"
            "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness"
        ),
    }
    synthesis.update(synthesis_overrides)
    return {
        "campaign_id": campaign_id,
        "campaign_type": "bounded_synthesis",
        "bounded_synthesis": synthesis,
    }


def seed_standard_campaign_closeouts(repo: Path, campaign_ids: list[str]) -> None:
    for index, campaign_id in enumerate(campaign_ids, start=1):
        campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
        closeout_path = repo / "lab" / "campaigns" / campaign_id / "campaign_closeout.yaml"
        campaign_path.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(
            campaign_path,
            {
                "campaign_id": campaign_id,
                "campaign_type": "standard",
                "status": "closed_for_synthesis_source",
                "created_at_utc": f"2026-06-2{index}T00:00:00Z",
                "claim_boundary": "standard_campaign_closed_no_selected_baseline_no_runtime_authority",
                "campaign_closeout": f"lab/campaigns/{campaign_id}/campaign_closeout.yaml",
            },
        )
        write_yaml(
            closeout_path,
            {
                "campaign_id": campaign_id,
                "status": "closed",
                "claim_boundary": "closeout_evidence_only_no_selected_baseline_no_runtime_authority",
            },
        )


def write_bounded_ingredient(
    repo: Path,
    campaign_id: str,
    ingredient_id: str,
    *,
    source_campaign_id: str,
    source_run_id: str = "run_source_fixture_v0",
    evidence_path: str = "docs/workspace/workspace_state.yaml",
    status: str = "available_for_first_synthesis",
    consumed_by: str = "",
    carry_from: str = "",
    reopen_reason: str = "",
) -> Path:
    ingredient_path = repo / "lab" / "campaigns" / campaign_id / "synthesis" / "ingredients" / f"{ingredient_id}.yaml"
    ingredient_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(
        ingredient_path,
        {
            "version": "ingredient_card_v1",
            "ingredient_card_id": ingredient_id,
            "source_campaign_ids": [source_campaign_id],
            "source_run_ids": [source_run_id],
            "source_clue_ids": [],
            "source_negative_memory_ids": [],
            "source_divergence_ids": [],
            "material_type": "preserved_clue",
            "salvage_value": "usable synthesis fixture material with bounded claim",
            "evidence_paths": [evidence_path],
            "selection_eligibility": "eligible_for_mix",
            "ingredient_lifecycle": {
                "synthesis_use_status": status,
                "consumed_by_synthesis_campaign_id": consumed_by,
                "consumed_by_mix_item_id": "mix_item_fixture_v0" if consumed_by else "",
                "carry_forward_from_synthesis_campaign_id": carry_from,
                "reopened_ingredient_exception_reason": reopen_reason,
            },
            "forbidden_uses": [
                "selected_baseline",
                "next_wave_direction",
                "repair_relabeling",
            ],
            "claim_boundary": "ingredient_reference_only_no_candidate_no_selected_baseline_no_runtime_authority",
        },
    )
    return ingredient_path


def write_valid_bounded_synthesis(repo: Path, campaign_id: str) -> dict[str, Any]:
    manifest = bounded_synthesis_campaign(campaign_id)
    source_campaign_ids = manifest["bounded_synthesis"]["source_campaign_ids"]
    seed_standard_campaign_closeouts(repo, source_campaign_ids)
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(campaign_path, manifest)
    write_bounded_ingredient(
        repo,
        campaign_id,
        "ingredient_valid_fixture_v0",
        source_campaign_id=source_campaign_ids[0],
    )
    return manifest


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


def test_active_validator_rejects_runtime_complete_without_report(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    attempt_path = repo / "runtime" / "mt5_attempts" / "attempt_wave01_eb_cell_001_l4_validation_v0" / "attempt_manifest.yaml"
    attempt = load_yaml(attempt_path)
    attempt["status"] = "runtime_probe_completed"
    attempt["execution_state"] = {
        "terminal_launched": True,
        "telemetry_file_observed": True,
        "telemetry_rows_observed": True,
        "tester_report_observed": False,
        "tester_report_completed": False,
        "terminal_mode": "portable_contract_attempt",
        "runtime_probe_complete": True,
    }
    write_yaml(attempt_path, attempt)

    errors = validate(repo)

    assert any("runtime_probe_complete true without tester_report_observed" in error for error in errors)


def test_active_validator_rejects_legacy_completed_runtime_status(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    attempt_path = repo / "runtime" / "mt5_attempts" / "attempt_wave01_eb_cell_001_l4_validation_v0" / "attempt_manifest.yaml"
    attempt = load_yaml(attempt_path)
    attempt["status"] = "completed_l4_score_telemetry_observed"
    attempt["execution_state"] = {
        "terminal_launched": True,
        "telemetry_file_observed": True,
        "telemetry_rows_observed": True,
        "tester_report_observed": False,
        "tester_report_completed": False,
        "terminal_mode": "main_mode_config_fallback",
        "runtime_probe_complete": False,
    }
    write_yaml(attempt_path, attempt)

    errors = validate(repo)

    assert any("completed_* status without runtime_probe_complete" in error for error in errors)


def test_active_validator_accepts_bounded_synthesis_with_real_sources_and_ingredient(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_valid_fixture_v0"
    write_valid_bounded_synthesis(repo, campaign_id)

    errors = validate(repo)

    assert not any("bounded synthesis" in error and campaign_id in error for error in errors)
    assert not any("ingredient_valid_fixture_v0" in error for error in errors)


def test_active_validator_rejects_counted_campaign_without_closeout_evidence(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_missing_closeout_v0"
    manifest = write_valid_bounded_synthesis(repo, campaign_id)
    source_campaign_id = manifest["bounded_synthesis"]["source_campaign_ids"][0]
    closeout_path = repo / "lab" / "campaigns" / source_campaign_id / "campaign_closeout.yaml"
    closeout_path.unlink()

    errors = validate(repo)

    assert any("counted standard campaign missing closeout evidence" in error for error in errors)


def test_active_validator_rejects_consumed_raw_ingredient_reused_as_fresh_material(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    first_campaign_id = "campaign_synthesis_consumed_fixture_v0"
    second_campaign_id = "campaign_synthesis_reuse_fixture_v0"
    first_manifest = write_valid_bounded_synthesis(repo, first_campaign_id)
    source_campaign_id = first_manifest["bounded_synthesis"]["source_campaign_ids"][0]
    write_bounded_ingredient(
        repo,
        first_campaign_id,
        "ingredient_consumed_fixture_v0",
        source_campaign_id=source_campaign_id,
        status="consumed_by_completed_synthesis",
        consumed_by=first_campaign_id,
    )
    second_manifest = bounded_synthesis_campaign(second_campaign_id)
    second_manifest["bounded_synthesis"]["source_campaign_ids"] = first_manifest["bounded_synthesis"]["source_campaign_ids"]
    second_manifest["bounded_synthesis"]["cadence"]["counted_standard_campaign_ids"] = first_manifest["bounded_synthesis"][
        "source_campaign_ids"
    ]
    second_path = repo / "lab" / "campaigns" / second_campaign_id / "campaign_manifest.yaml"
    second_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(second_path, second_manifest)
    write_bounded_ingredient(
        repo,
        second_campaign_id,
        "ingredient_reused_fresh_fixture_v0",
        source_campaign_id=source_campaign_id,
        status="available_for_first_synthesis",
    )

    errors = validate(repo)

    assert any("raw ingredient identity was already consumed" in error for error in errors)


def test_active_validator_rejects_bad_bounded_synthesis_mix_depth(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_mix_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    write_yaml(
        campaign_path,
        bounded_synthesis_campaign(
            campaign_id,
            mix_depth_policy={
                "default_sequence": ["mix-3"],
                "mix4_policy": "exception_only_with_recorded_reason",
                "mix5_plus_policy": "forbidden",
            },
        ),
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
        bounded_synthesis_campaign(campaign_id, next_wave_influence="allowed_to_direct_next_wave"),
    )

    errors = validate(repo)

    assert any("next_wave_influence must be forbidden" in error for error in errors)


def test_active_validator_rejects_bounded_synthesis_without_five_campaign_cadence(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_cadence_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    manifest = bounded_synthesis_campaign(campaign_id)
    manifest["bounded_synthesis"]["cadence"]["counted_standard_campaign_ids"] = ["campaign_one_v0"]
    write_yaml(campaign_path, manifest)

    errors = validate(repo)

    assert any("requires 5 counted standard campaigns" in error for error in errors)


def test_active_validator_rejects_bounded_synthesis_kpi_stage_kind_drift(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_kpi_stage_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    manifest = bounded_synthesis_campaign(campaign_id)
    manifest["bounded_synthesis"]["kpi_policy"]["stage_kind"] = "campaign"
    write_yaml(campaign_path, manifest)

    errors = validate(repo)

    assert any("KPI stage_kind must be special_mixing" in error for error in errors)


def test_active_validator_rejects_mix4_without_exception_reason(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_mix4_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    write_yaml(campaign_path, bounded_synthesis_campaign(campaign_id))
    queue_path = repo / "lab" / "campaigns" / campaign_id / "synthesis" / "mix_queue.yaml"
    queue_path.parent.mkdir(parents=True)
    write_yaml(
        queue_path,
        {
            "version": "synthesis_mix_queue_v1",
            "campaign_id": campaign_id,
            "queue_id": "queue_bad_mix4_v0",
            "source_scope": "previous_material_only",
            "ingredient_lifecycle_policy": {
                "raw_reuse_default": "forbidden_after_consumed_by_completed_synthesis",
            },
            "kpi_policy": {"stage_kind": "special_mixing"},
            "mix_items": [{"mix_item_id": "mix_item_bad_v0", "mix_depth": "mix-4"}],
        },
    )

    errors = validate(repo)

    assert any("mix-4 requires exception_reason" in error for error in errors)


def test_active_validator_rejects_carry_forward_ingredient_without_source(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_id = "campaign_synthesis_bad_carry_forward_v0"
    campaign_path = repo / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml"
    campaign_path.parent.mkdir(parents=True)
    write_yaml(campaign_path, bounded_synthesis_campaign(campaign_id))
    ingredient_path = (
        repo
        / "lab"
        / "campaigns"
        / campaign_id
        / "synthesis"
        / "ingredients"
        / "ingredient_bad_carry_forward_v0.yaml"
    )
    ingredient_path.parent.mkdir(parents=True)
    write_yaml(
        ingredient_path,
        {
            "version": "ingredient_card_v1",
            "ingredient_card_id": "ingredient_bad_carry_forward_v0",
            "ingredient_lifecycle": {
                "synthesis_use_status": "carry_forward_ingredient",
                "carry_forward_from_synthesis_campaign_id": "",
            },
        },
    )

    errors = validate(repo)

    assert any("carry_forward_ingredient requires source synthesis campaign" in error for error in errors)


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


def test_active_validator_rejects_active_wave_run_missing_goal_id(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    run_id = "onnxlab_wave0_cell_001_surface_scout_v0"
    run_dir = repo / "lab" / "runs" / run_id

    manifest = load_json(run_dir / "run_manifest.json")
    manifest["id_chain"].pop("goal_id", None)
    write_json(run_dir / "run_manifest.json", manifest)

    receipt = load_yaml(run_dir / "experiment_receipt.yaml")
    receipt["id_chain"].pop("goal_id", None)
    write_yaml(run_dir / "experiment_receipt.yaml", receipt)

    errors = validate(repo)

    assert any(f"run_registry.csv {run_id}: manifest id_chain.goal_id" in error for error in errors)
    assert any(f"run_registry.csv {run_id}: receipt id_chain.goal_id" in error for error in errors)


def test_active_validator_rejects_surface_registry_status_drift(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    registry_path = repo / "docs" / "registers" / "experiment_surface_registry.csv"
    rows = registry_path.read_text(encoding="utf-8").splitlines()
    rows = [
        line.replace("wave01_session_transition_closed_preserved_clues_no_candidate", "stale_status", 1)
        if line.startswith("surface_us100_session_transition_regime_surface_v0,")
        else line
        for line in rows
    ]
    registry_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    errors = validate(repo)

    assert any(
        "experiment_surface_registry.csv surface_us100_session_transition_regime_surface_v0: status mismatch"
        in error
        for error in errors
    )


def test_active_validator_rejects_sweep_registry_status_drift(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    registry_path = repo / "docs" / "registers" / "sweep_registry.csv"
    rows = registry_path.read_text(encoding="utf-8").splitlines()
    rows = [
        line.replace("wave01_session_transition_closed_preserved_clues_no_candidate", "stale_status", 1)
        if line.startswith("sweep_us100_session_transition_broad_v0,")
        else line
        for line in rows
    ]
    registry_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    errors = validate(repo)

    assert any("sweep_registry.csv sweep_us100_session_transition_broad_v0: status mismatch" in error for error in errors)


def test_active_validator_rejects_wave_referenced_memory_missing_from_registries(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    clue_registry = repo / "docs" / "registers" / "clue_registry.csv"
    negative_registry = repo / "docs" / "registers" / "negative_memory_registry.csv"
    clue_registry.write_text(
        "\n".join(
            line
            for line in clue_registry.read_text(encoding="utf-8").splitlines()
            if not line.startswith("clue_wave01_session_transition_remaining_decision_surface_needed_v0,")
        )
        + "\n",
        encoding="utf-8",
    )
    negative_registry.write_text(
        "\n".join(
            line
            for line in negative_registry.read_text(encoding="utf-8").splitlines()
            if not line.startswith("neg_wave01_session_transition_inverse_score_band_decision_replay_loss_v0,")
        )
        + "\n",
        encoding="utf-8",
    )

    errors = validate(repo)

    assert any("negative_memory_id missing registry row" in error for error in errors)
    assert any("preserved_clue_id missing registry row" in error for error in errors)


def test_active_validator_rejects_missing_goal_objective_revision(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    goal_path = repo / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "goal_manifest.yaml"
    goal = load_yaml(goal_path)
    goal["objective_identity"]["source_path"] = (
        "lab/goals/goal_us100_onnx_forward_boundary_v0/missing_goal_revision.yaml"
    )
    write_yaml(goal_path, goal)

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
