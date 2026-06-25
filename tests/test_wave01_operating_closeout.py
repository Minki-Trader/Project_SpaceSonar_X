from __future__ import annotations

import csv
import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

import foundation.evaluation.build_operating_closeout as closeout_builder
import foundation.evaluation.operating_slo_evaluator as slo_evaluator
from foundation.evaluation.build_operating_closeout import (
    CloseoutEvaluation,
    evaluate_operating_closeout,
    load_committed_closeout,
    validate_committed_closeout,
)
from foundation.evaluation.common import finalize_result, stable_sha256, write_yaml
from foundation.evaluation.fresh_evaluator_validator import compare_committed_evaluator_file
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.migrations.runtime_graph_target_inventory import INVENTORY_REL_PATH
from spacesonar.control_plane.state_projection import workspace_projection_diff
from tests.test_runtime_graph_revalidation import materialize_committed_repo, receipt_path


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT_PATH = (
    ROOT
    / "lab"
    / "waves"
    / "wave_us100_closedbar_surface_cartography_v0"
    / "wave_closeout.yaml"
)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_wave01_closeout_matches_recomputed_evaluator_digest() -> None:
    recomputed = evaluate_operating_closeout(ROOT)
    committed = load_committed_closeout(ROOT)

    assert committed["evaluation_digest"] == recomputed.digest
    assert committed["requirement_audit"] == recomputed.requirement_audit


def test_wave01_closeout_requirements_are_evaluator_backed() -> None:
    committed = load_committed_closeout(ROOT)

    assert committed["version"] == "wave_closeout_v2"
    for item in committed["requirement_audit"]:
        assert item["evaluator_id"]
        assert item["evaluator_result_path"]
        assert item["evaluator_result_sha256"]
    assert validate_committed_closeout(ROOT) == []


def test_wave01_closeout_result_separates_operating_proof_from_runtime_contract() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    result = closeout["result"]
    summary = closeout["wave_summary"]

    assert result["control_plane_operating_proof"] == "passed"
    assert result["research_cycle_closeout"] == "passed"
    assert result["runtime_contract_integrity"] == "passed"
    assert result["agent_value_metrics"] == "passed"
    assert result["runtime_authority"] == "not_claimed"
    assert result["economics_pass"] == "not_claimed"
    assert result["candidate_count"] == 0
    assert result["l5_candidate_count"] == 0
    assert summary["candidate_count"] == 0
    assert summary["l5_candidate_count"] == 0
    assert summary["runtime_authority"] is False
    assert summary["economics_pass"] is False
    assert summary["locked_final_oos_used"] is False
    assert summary["runtime_contract_integrity"] == "passed"
    assert summary["agent_value_status"] == "passed"


def test_current_workspace_projection_is_not_stale() -> None:
    assert workspace_projection_diff(ROOT) is False


def test_goal_next_work_cursor_workspace_wave_registry_and_closeout_agree() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    goal = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "goal_manifest.yaml")
    next_work = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "next_work_item.yaml")
    cursor = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "resume_cursor.yaml")
    workspace = load_yaml(ROOT / "docs" / "workspace" / "workspace_state.yaml")
    wave_rows = read_csv(ROOT / "docs" / "registers" / "wave_registry.csv")
    work_item_id = "work_post_wave01_user_directed_wave02_or_review_v0"

    assert goal["status"] == "complete_wave01_operating_proof_window"
    assert goal["active_phase"] == "wave01_operating_closeout_complete"
    assert goal["active_ids"]["campaign_id"] is None
    assert goal["next_work_item"]["work_item_id"] == work_item_id
    assert next_work["work_item_id"] == work_item_id
    assert cursor["cursor_state"] == "complete_wave01_operating_proof_window"
    assert cursor["active_phase"] == "wave01_operating_closeout_complete"
    assert workspace["active_wave"]["status"] == closeout["status"]
    assert workspace["active_work_item"]["work_item_id"] == work_item_id
    assert workspace["unresolved_blockers"] == []
    assert wave_rows[0]["status"] == closeout["status"]
    assert wave_rows[0]["next_action"] == closeout["next_action"]


def test_agent_observation_proof_releases_repair_work_item_everywhere() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    goal = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "goal_manifest.yaml")
    workspace = load_yaml(ROOT / "docs" / "workspace" / "workspace_state.yaml")

    assert closeout["result"]["agent_value_metrics"] == "passed"
    assert closeout["next_action"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert goal["next_work_item"]["work_item_id"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert workspace["active_work_item"]["work_item_id"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert closeout["handoff"]["blocking_requirements"] == []
    assert closeout["handoff"]["blocking_findings"] == []


def test_handoff_advertises_only_user_directed_wave02_or_review_after_required_evaluators_pass() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)

    assert closeout["status"] == "wave01_control_plane_proof_closed_runtime_contract_complete"
    assert closeout["handoff"]["next_action"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert closeout["handoff"]["blocking_requirements"] == []


def test_successful_proof_restores_user_directed_next_allowed_shapes() -> None:
    next_work = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "next_work_item.yaml")

    assert "user_directed_wave02_open" in next_work["next_allowed_shapes"]
    assert "post_closeout_review" in next_work["next_allowed_shapes"]
    assert "closeout_evidence_repair" not in next_work["next_allowed_shapes"]
    assert next_work["missing_material_if_relevant"] == []


def test_successful_proof_updates_wave_allocation_status_next_action_and_git_integration() -> None:
    wave = load_yaml(ROOT / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0" / "wave_allocation.yaml")

    assert wave["status"] == "wave01_operating_proof_window_closed"
    assert wave["next_action"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert wave["claim_boundary"] == "active_goal_complete_wave01_operating_proof_only_no_candidate_no_runtime_authority_no_economics_pass_no_live_readiness"
    assert wave["git_integration"]["status"] == "wave_closeout_ready_for_boundary_commit_and_main_integration"


def test_wave_registry_records_boundary_closeout_ready_after_proof() -> None:
    wave_rows = read_csv(ROOT / "docs" / "registers" / "wave_registry.csv")

    assert wave_rows[0]["notes"] == "wave_closeout_ready_for_boundary_commit_and_main_integration"
    assert wave_rows[0]["next_action"] == "work_post_wave01_user_directed_wave02_or_review_v0"


def test_wave02_is_not_created_automatically_after_proof() -> None:
    wave_paths = [path.as_posix().lower() for path in (ROOT / "lab" / "waves").rglob("*")]
    campaign_paths = [path.as_posix().lower() for path in (ROOT / "lab" / "campaigns").rglob("*")]

    assert not any("wave02" in path or "wave_02" in path for path in wave_paths + campaign_paths)


def test_updated_timestamps_change_with_state_transition() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    goal = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "goal_manifest.yaml")
    next_work = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "next_work_item.yaml")
    cursor = load_yaml(ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "resume_cursor.yaml")
    wave = load_yaml(ROOT / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0" / "wave_allocation.yaml")

    assert goal["updated_at_utc"] == closeout["generated_at_utc"]
    assert next_work["updated_at_utc"] == closeout["generated_at_utc"]
    assert cursor["updated_at_utc"] == closeout["generated_at_utc"]
    assert wave["updated_at_utc"] == closeout["generated_at_utc"]


def test_wave01_closeout_handoff_ids_are_registered() -> None:
    closeout = load_yaml(CLOSEOUT_PATH)
    clue_rows = read_csv(ROOT / "docs" / "registers" / "clue_registry.csv")
    negative_rows = read_csv(ROOT / "docs" / "registers" / "negative_memory_registry.csv")
    clue_ids = {row["clue_id"] for row in clue_rows}
    negative_ids = {row["memory_id"] for row in negative_rows}

    assert set(closeout["handoff"]["preserved_clue_ids"]) <= clue_ids
    assert set(closeout["handoff"]["negative_memory_ids"]) <= negative_ids


@pytest.mark.parametrize("field", ["active_goal_id", "wave_id"])
def test_closeout_identity_tampering_with_recomputed_digest_fails(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    original = load_committed_closeout(ROOT)
    mutated = copy.deepcopy(original)
    mutated[field] = f"tampered_{field}"
    mutated["evaluation_digest"] = closeout_builder._closeout_digest(mutated)
    monkeypatch.setattr(closeout_builder, "load_committed_closeout", lambda repo_root: mutated)
    monkeypatch.setattr(
        closeout_builder,
        "evaluate_operating_closeout",
        lambda repo_root, write=False: CloseoutEvaluation(closeout=original, digest=original["evaluation_digest"], requirement_audit=original["requirement_audit"], staged_texts={}),
    )

    errors = validate_committed_closeout(ROOT)

    assert any("semantic payload" in error for error in errors)


def test_self_attested_pass_would_change_closeout_digest() -> None:
    committed = load_committed_closeout(ROOT)
    mutated = copy.deepcopy(committed)
    mutated["requirement_audit"][0].pop("evaluator_id", None)

    payload = {
        "result": mutated["result"],
        "wave_summary": mutated["wave_summary"],
        "requirement_audit": mutated["requirement_audit"],
        "claim_boundary": mutated["claim_boundary"],
        "not_claimed": mutated["not_claimed"],
    }
    assert stable_sha256(payload) != committed["evaluation_digest"]


def test_self_authored_pass_is_rejected_even_before_digest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    closeout_dir = tmp_path / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0"
    closeout_dir.mkdir(parents=True)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_stabilization_v2" / "fixture.yaml"
    evaluator = finalize_result(
        {
            "version": "evaluator_result_v1",
            "evaluator_id": "fixture_evaluator_v1",
            "executed_at_utc": "2026-06-24T00:00:00Z",
            "input_hashes": [],
            "status": "failed",
            "metrics": {},
            "findings": [],
        }
    )
    write_yaml(evaluator_path, evaluator)
    closeout = {
        "result": {},
        "wave_summary": {},
        "requirement_audit": [
            {
                "requirement": "manual_requirement",
                "evaluator_result_path": "lab/evaluations/control_plane_stabilization_v2/fixture.yaml",
                "evaluator_result_sha256": evaluator["output_sha256"],
                "status": "passed",
            }
        ],
        "claim_boundary": "test_only",
        "not_claimed": [],
        "evaluation_digest": "manual",
    }
    write_yaml(closeout_dir / "wave_closeout.yaml", closeout)
    monkeypatch.setattr(
        closeout_builder,
        "evaluate_operating_closeout",
        lambda repo_root, write=False: CloseoutEvaluation(closeout=closeout, digest="manual", requirement_audit=closeout["requirement_audit"], staged_texts={}),
    )
    monkeypatch.setattr(closeout_builder, "compare_committed_evaluator_file", lambda repo_root, path: [])
    monkeypatch.setattr(closeout_builder, "_required_evaluator_entries", lambda repo_root: [])

    errors = validate_committed_closeout(tmp_path)

    assert any("self-attested passed status" in error for error in errors)
    assert any("missing evaluator fields" in error for error in errors)


def test_operating_requirement_status_comes_from_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    failed_operating = _evaluator_result("operating_slo_evaluator_v1", "failed")
    _patch_closeout_evaluators(
        monkeypatch,
        operating=failed_operating,
        research=_evaluator_result("research_cycle_closeout_evaluator_v1", "passed"),
        runtime=_evaluator_result("runtime_contract_evaluator_v2", "passed"),
        routing=_evaluator_result("routing_quality_evaluator_v1", "passed"),
        agent=_evaluator_result("agent_value_evaluator_v1", "passed"),
    )

    evaluation = evaluate_operating_closeout(ROOT)
    audit = {item["requirement"]: item for item in evaluation.requirement_audit}

    assert audit["control_plane_operating_proof"]["status"] == "failed"
    assert evaluation.closeout["result"]["control_plane_operating_proof"] == "failed"
    assert evaluation.closeout["status"] == "wave01_evaluator_backed_closeout_requires_evidence_repair"
    assert "control_plane_operating_proof" in evaluation.closeout["result_judgment"]["failed_or_insufficient_requirements"]


def test_research_requirement_status_comes_from_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_closeout_evaluators(
        monkeypatch,
        operating=_evaluator_result("operating_slo_evaluator_v1", "passed"),
        research=_evaluator_result("research_cycle_closeout_evaluator_v1", "failed"),
        runtime=_evaluator_result("runtime_contract_evaluator_v2", "passed"),
        routing=_evaluator_result("routing_quality_evaluator_v1", "passed"),
        agent=_evaluator_result("agent_value_evaluator_v1", "passed"),
    )

    evaluation = evaluate_operating_closeout(ROOT)
    audit = {item["requirement"]: item for item in evaluation.requirement_audit}

    assert audit["research_cycle_closeout"]["status"] == "failed"
    assert evaluation.closeout["result"]["research_cycle_closeout"] == "failed"
    assert evaluation.closeout["status"] == "wave01_evaluator_backed_closeout_requires_evidence_repair"
    assert "research_cycle_closeout" in evaluation.closeout["result_judgment"]["failed_or_insufficient_requirements"]


def test_actual_nonzero_candidate_count_appears_in_closeout(monkeypatch: pytest.MonkeyPatch) -> None:
    research = _evaluator_result("research_cycle_closeout_evaluator_v1", "failed")
    research["metrics"] = {"candidate_count": 2, "l5_candidate_count": 1, "campaign_count": 1, "locked_final_oos_used": False}
    research["campaign_results"] = [
        {
            "campaign_id": "campaign_fixture",
            "status": "closed",
            "evidence_path": "lab/campaigns/campaign_fixture/campaign_closeout.yaml",
            "evidence_class": "campaign_closeout",
            "candidate_count": 2,
            "l5_candidate_count": 1,
            "forbidden_claims_respected": True,
        }
    ]
    research = finalize_result(research)
    _patch_closeout_evaluators(
        monkeypatch,
        operating=_evaluator_result("operating_slo_evaluator_v1", "passed"),
        research=research,
        runtime=_evaluator_result("runtime_contract_evaluator_v2", "passed"),
        routing=_evaluator_result("routing_quality_evaluator_v1", "passed"),
        agent=_evaluator_result("agent_value_evaluator_v1", "passed"),
    )

    evaluation = evaluate_operating_closeout(ROOT)

    assert evaluation.closeout["result"]["candidate_count"] == 2
    assert evaluation.closeout["result"]["l5_candidate_count"] == 1
    assert evaluation.closeout["wave_summary"]["candidate_count"] == 2
    assert evaluation.closeout["campaign_summaries"][0]["candidate_count"] == 2


def test_all_evaluators_passed_transitions_state_out_of_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    research = _evaluator_result("research_cycle_closeout_evaluator_v1", "passed")
    research["metrics"] = {"candidate_count": 0, "l5_candidate_count": 0, "campaign_count": 3, "locked_final_oos_used": False}
    research["campaign_results"] = []
    research = finalize_result(research)
    _patch_closeout_evaluators(
        monkeypatch,
        operating=_evaluator_result("operating_slo_evaluator_v1", "passed"),
        research=research,
        runtime=_evaluator_result("runtime_contract_evaluator_v2", "passed"),
        routing=_evaluator_result("routing_quality_evaluator_v1", "passed"),
        agent=_evaluator_result("agent_value_evaluator_v1", "passed"),
    )

    evaluation = evaluate_operating_closeout(ROOT)
    staged = {
        path.as_posix(): yaml.safe_load(text)
        for path, text in evaluation.staged_texts.items()
        if path.suffix == ".yaml"
    }
    goal = staged["lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml"]
    next_work = staged["lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml"]
    cursor = staged["lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml"]
    wave = staged["lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml"]
    workspace = staged["docs/workspace/workspace_state.yaml"]

    assert goal["status"] == "complete_wave01_operating_proof_window"
    assert goal["active_phase"] == "wave01_operating_closeout_complete"
    assert next_work["work_item_id"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert cursor["cursor_state"] == "complete_wave01_operating_proof_window"
    assert cursor["active_phase"] == "wave01_operating_closeout_complete"
    assert wave["status"] == "wave01_operating_proof_window_closed"
    assert wave["git_integration"]["status"] == "wave_closeout_ready_for_boundary_commit_and_main_integration"
    assert workspace["active_work_item"]["work_item_id"] == "work_post_wave01_user_directed_wave02_or_review_v0"
    assert workspace["unresolved_blockers"] == []


def test_no_repair_work_item_id_remains_after_all_pass_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    research = _evaluator_result("research_cycle_closeout_evaluator_v1", "passed")
    research["metrics"] = {"candidate_count": 0, "l5_candidate_count": 0, "campaign_count": 3, "locked_final_oos_used": False}
    research = finalize_result(research)
    _patch_closeout_evaluators(
        monkeypatch,
        operating=_evaluator_result("operating_slo_evaluator_v1", "passed"),
        research=research,
        runtime=_evaluator_result("runtime_contract_evaluator_v2", "passed"),
        routing=_evaluator_result("routing_quality_evaluator_v1", "passed"),
        agent=_evaluator_result("agent_value_evaluator_v1", "passed"),
    )

    evaluation = evaluate_operating_closeout(ROOT)
    combined = yaml.safe_dump(evaluation.closeout, sort_keys=False) + "\n".join(evaluation.staged_texts.values())

    assert "work_wp07_closeout_evidence_repair_v0" not in combined
    assert "wp07_closeout_evidence_repair" not in combined


def test_research_evaluator_failure_appears_in_workspace_blocker_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    research = _evaluator_result("research_cycle_closeout_evaluator_v1", "failed")
    research["findings"] = [{"id": "locked_final_oos_used"}]
    research = finalize_result(research)
    _patch_closeout_evaluators(
        monkeypatch,
        operating=_evaluator_result("operating_slo_evaluator_v1", "passed"),
        research=research,
        runtime=_evaluator_result("runtime_contract_evaluator_v2", "passed"),
        routing=_evaluator_result("routing_quality_evaluator_v1", "passed"),
        agent=_evaluator_result("agent_value_evaluator_v1", "passed"),
    )

    evaluation = evaluate_operating_closeout(ROOT)
    workspace = yaml.safe_load(evaluation.staged_texts[closeout_builder.WORKSPACE_STATE_PATH])
    next_work = yaml.safe_load(evaluation.staged_texts[closeout_builder.NEXT_WORK_ITEM_PATH])

    assert "locked_final_oos_used" in workspace["unresolved_blockers"]
    assert "locked_final_oos_used" in next_work["blocking_findings"]


def test_new_required_evaluator_cannot_be_omitted_from_closeout(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = closeout_builder.load_evaluator_registry(ROOT)
    entries.append(
        {
            "evaluator_id": "unsupported_required_evaluator_v1",
            "canonical_result_path": "lab/evaluations/control_plane_stabilization_v2/unsupported_required_evaluator_v1.yaml",
            "implementation_paths": ["foundation/evaluation/unsupported.py"],
            "required_for_operating_closeout": True,
            "closeout_requirement": "unsupported_requirement",
            "role": "active",
            "allowed_alias_paths": [],
        }
    )
    monkeypatch.setattr(closeout_builder, "load_evaluator_registry", lambda repo_root: entries)

    with pytest.raises(ValueError, match="unsupported_required_evaluator_v1"):
        evaluate_operating_closeout(ROOT)


@pytest.mark.parametrize(
    ("field", "mutator"),
    [
        ("status", lambda payload: payload.update({"status": "tampered_pass"})),
        ("next_action", lambda payload: payload.update({"next_action": "tampered_action"})),
        ("campaign_summaries", lambda payload: payload["campaign_summaries"].append({"campaign_id": "tampered"})),
        ("handoff", lambda payload: payload["handoff"].update({"next_action": "tampered"})),
    ],
)
def test_closeout_full_semantic_tampering_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    mutator: Any,
) -> None:
    closeout = _minimal_closeout_payload()
    closeout["evaluation_digest"] = closeout_builder._closeout_digest(closeout)
    mutated = copy.deepcopy(closeout)
    mutator(mutated)
    write_yaml(tmp_path / closeout_builder.WAVE_CLOSEOUT_PATH, mutated)
    monkeypatch.setattr(
        closeout_builder,
        "evaluate_operating_closeout",
        lambda repo_root, write=False: CloseoutEvaluation(closeout=closeout, digest=closeout["evaluation_digest"], requirement_audit=[], staged_texts={}),
    )
    monkeypatch.setattr(closeout_builder, "_required_evaluator_entries", lambda repo_root: [])

    errors = validate_committed_closeout(tmp_path)

    assert errors, field
    assert any("semantic payload" in error or "evaluation_digest" in error for error in errors)


def test_operating_closeout_write_failure_rolls_back_evaluators_closeout_and_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator_path = Path("lab/evaluations/control_plane_stabilization_v2/runtime_contract_evaluator_v2.yaml")
    closeout_path = closeout_builder.WAVE_CLOSEOUT_PATH
    registry_path = closeout_builder.ARTIFACT_REGISTRY_PATH
    goal_path = closeout_builder.GOAL_MANIFEST_PATH
    next_work_path = closeout_builder.NEXT_WORK_ITEM_PATH
    cursor_path = closeout_builder.RESUME_CURSOR_PATH
    workspace_path = closeout_builder.WORKSPACE_STATE_PATH
    wave_path = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml")
    originals = {
        evaluator_path: "old evaluator\n",
        closeout_path: "old closeout\n",
        registry_path: "artifact_id,path_or_uri,sha256,size_bytes\n",
        goal_path: "old goal\n",
        next_work_path: "old next work\n",
        cursor_path: "old cursor\n",
        workspace_path: "old workspace\n",
        wave_path: "old wave allocation\n",
    }
    for rel_path, text in originals.items():
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    closeout = _minimal_closeout_payload()
    monkeypatch.setattr(
        closeout_builder,
        "evaluate_operating_closeout",
        lambda repo_root, write=False: CloseoutEvaluation(
            closeout=closeout,
            digest="rollback_test",
            requirement_audit=[],
            staged_texts={
                evaluator_path: "new evaluator\n",
                closeout_path: "new closeout\n",
                goal_path: "new goal\n",
                next_work_path: "new next work\n",
                cursor_path: "new cursor\n",
                workspace_path: "new workspace\n",
                wave_path: "new wave allocation\n",
                registry_path: "artifact_id,path_or_uri,sha256,size_bytes\nnew,path,sha,1\n",
            },
        ),
    )
    monkeypatch.setattr(closeout_builder, "_transaction_validation", lambda future_root: [])

    result = closeout_builder.write_operating_closeout_transaction(tmp_path, fail_after_replace_count=1)

    assert result.status == "rolled_back_commit_failure"
    for rel_path, text in originals.items():
        assert (tmp_path / rel_path).read_text(encoding="utf-8") == text


def test_control_plane_validator_invokes_closeout_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import foundation.validation.control_plane_validator as control_plane_validator

    monkeypatch.setattr(control_plane_validator, "ensure_paths", lambda repo_root, rel_paths: [])
    for name in [
        "validate_yaml_json_csv_parse",
        "validate_work_item_schema",
        "validate_policy_contract_and_context_slo",
        "validate_skill_receipt_schema",
        "validate_templates",
        "validate_task_force_registry",
        "validate_agent_consult_receipts",
        "validate_agent_operating_metrics_projection",
        "validate_execution_provenance",
        "validate_fresh_evaluators",
        "validate_routing_smoke_prompts",
        "validate_import_smoke",
    ]:
        monkeypatch.setattr(control_plane_validator, name, lambda repo_root: [])
    monkeypatch.setattr(control_plane_validator, "validate_operating_closeout", lambda repo_root: ["closeout sentinel"])

    errors = control_plane_validator.validate(tmp_path)

    assert "closeout sentinel" in errors


def test_runtime_evidence_mutation_changes_evaluator_digest(tmp_path: Path) -> None:
    inventory = _runtime_inventory_fixture()
    inventory_path = tmp_path / INVENTORY_REL_PATH
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
    first_entry = inventory["attempts"][0]
    attempt_dir = tmp_path / Path(first_entry["manifest_path"]).parent
    attempt_dir.mkdir(parents=True)
    manifest = {
        "attempt_id": first_entry["attempt_id"],
        "status": "telemetry_adapter_observed_runtime_contract_incomplete",
        "execution_state": {
            "terminal_launched": True,
            "telemetry_file_observed": True,
            "telemetry_rows_observed": True,
            "tester_report_observed": False,
            "tester_report_completed": False,
            "terminal_mode": "main_mode_config_fallback",
            "runtime_probe_complete": False,
            "missing_requirements": ["tester_report_observed", "portable_terminal_contract"],
        },
    }
    path = tmp_path / first_entry["manifest_path"]
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    before = evaluate_runtime_contract(tmp_path)

    manifest["execution_state"]["tester_report_observed"] = True
    manifest["execution_state"]["tester_report_completed"] = True
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    after = evaluate_runtime_contract(tmp_path)

    assert before["output_sha256"] != after["output_sha256"]


@pytest.mark.parametrize("mutation", ["attempt", "terminal_summary", "tester_report_receipt"])
def test_stale_runtime_evaluator_detects_runtime_input_mutation(tmp_path: Path, mutation: str) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    _write_runtime_evaluator_registry(tmp_path)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_corrective_v3" / "runtime_contract_evaluator_v2.yaml"
    write_yaml(evaluator_path, evaluate_runtime_contract(tmp_path))
    target = entries[0]
    attempt_dir = tmp_path / Path(target["manifest_path"]).parent

    if mutation == "attempt":
        manifest_path = tmp_path / target["manifest_path"]
        manifest = load_yaml(manifest_path)
        manifest["execution_state"]["runtime_probe_complete"] = False
        write_yaml(manifest_path, manifest)
    elif mutation == "terminal_summary":
        terminal_path = attempt_dir / "terminal_run_summary.yaml"
        terminal = load_yaml(terminal_path)
        terminal["mode"] = ""
        write_yaml(terminal_path, terminal)
    else:
        receipt = load_yaml(receipt_path(tmp_path, target))
        receipt["source_report_sha256"] = "0" * 64
        write_yaml(receipt_path(tmp_path, target), receipt)

    errors = compare_committed_evaluator_file(tmp_path, evaluator_path)

    assert any("does not match fresh recomputation" in error for error in errors)


def test_evaluator_input_hash_corruption_is_detected(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)
    _write_runtime_evaluator_registry(tmp_path)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_corrective_v3" / "runtime_contract_evaluator_v2.yaml"
    result = evaluate_runtime_contract(tmp_path)
    result["input_hashes"][0]["sha256"] = "bad"
    write_yaml(evaluator_path, result)

    errors = compare_committed_evaluator_file(tmp_path, evaluator_path)

    assert any("semantic payload" in error or "output_sha256" in error for error in errors)


def test_evaluator_output_hash_corruption_is_detected(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)
    _write_runtime_evaluator_registry(tmp_path)
    evaluator_path = tmp_path / "lab" / "evaluations" / "control_plane_corrective_v3" / "runtime_contract_evaluator_v2.yaml"
    result = evaluate_runtime_contract(tmp_path)
    result["output_sha256"] = "bad"
    write_yaml(evaluator_path, result)

    errors = compare_committed_evaluator_file(tmp_path, evaluator_path)

    assert any("output_sha256" in error for error in errors)


def test_missing_slo_metric_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_minimal_slo_repo(tmp_path)
    monkeypatch.setattr(slo_evaluator, "evaluate_routing_quality", lambda repo_root: {"metrics": {"accuracy": 1.0, "protected_claim_guard_recall": 1.0}, "status": "passed"})
    monkeypatch.setattr(slo_evaluator, "evaluate_runtime_contract", lambda repo_root: {"metrics": {}, "status": "passed"})
    monkeypatch.setattr(slo_evaluator, "evaluate_agent_value", lambda repo_root: {"metrics": {"duplicate_advice_ratio": 0.0}, "status": "passed", "findings": []})
    monkeypatch.setattr(slo_evaluator, "validate_repository_hygiene", lambda repo_root: [])
    monkeypatch.setattr(
        slo_evaluator,
        "_transaction_metrics",
        lambda repo_root: {
            "durable_transaction_receipt_count": 1,
            "transaction_idempotency_probe_count": 1,
            "transaction_idempotency_pass_count": 1,
            "transaction_idempotency_score": 1.0,
            "partial_unclassified_transactions": 0,
        },
    )
    monkeypatch.setattr(slo_evaluator, "_batch_receipt_metrics", lambda repo_root: {"durable_runs_with_unbounded_dirty_source": 0})
    monkeypatch.setattr(slo_evaluator, "_closeout_metrics", lambda repo_root: {"self_attested_closeout_requirements": 0})
    monkeypatch.setattr(slo_evaluator.subprocess, "run", lambda *args, **kwargs: _Completed(returncode=0, stdout="", stderr=""))

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert result["status"] == "failed"
    assert {"id": "required_slo_metric_unavailable", "metric": "routine_solo_or_single_agent_share"} in result["findings"]


def test_zero_transaction_count_cannot_satisfy_idempotency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed_minimal_slo_repo(tmp_path)
    monkeypatch.setattr(slo_evaluator, "evaluate_routing_quality", lambda repo_root: {"metrics": {"accuracy": 1.0, "protected_claim_guard_recall": 1.0}, "status": "passed"})
    monkeypatch.setattr(slo_evaluator, "evaluate_runtime_contract", lambda repo_root: {"metrics": {}, "status": "passed"})
    monkeypatch.setattr(
        slo_evaluator,
        "evaluate_agent_value",
        lambda repo_root: {"metrics": {"routine_solo_or_single_agent_share": 1.0, "duplicate_advice_ratio": 0.0}, "status": "passed", "findings": []},
    )
    monkeypatch.setattr(slo_evaluator, "validate_repository_hygiene", lambda repo_root: [])
    monkeypatch.setattr(
        slo_evaluator,
        "_transaction_metrics",
        lambda repo_root: {
            "durable_transaction_receipt_count": 0,
            "transaction_idempotency_probe_count": 0,
            "transaction_idempotency_pass_count": 0,
            "transaction_idempotency_score": None,
            "partial_unclassified_transactions": 0,
        },
    )
    monkeypatch.setattr(slo_evaluator, "_batch_receipt_metrics", lambda repo_root: {"durable_runs_with_unbounded_dirty_source": 0})
    monkeypatch.setattr(slo_evaluator, "_closeout_metrics", lambda repo_root: {"self_attested_closeout_requirements": 0})
    monkeypatch.setattr(slo_evaluator.subprocess, "run", lambda *args, **kwargs: _Completed(returncode=0, stdout="", stderr=""))

    result = slo_evaluator.evaluate_operating_slo(tmp_path)

    assert result["status"] == "failed"
    assert {"id": "required_slo_metric_unavailable", "metric": "transaction_idempotency_score"} in result["findings"]


def test_research_cycle_evaluator_fails_when_candidate_count_is_nonzero(tmp_path: Path) -> None:
    wave_dir = tmp_path / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0"
    campaign_dir = tmp_path / "lab" / "campaigns" / "campaign_fixture"
    _seed_research_registries(tmp_path)
    write_yaml(
        wave_dir / "wave_allocation.yaml",
        {
            "wave_id": "wave_us100_closedbar_surface_cartography_v0",
            "fixed_controls": {"locked_final_oos": "do_not_use"},
            "campaign_allocations": [
                {
                    "campaign_id": "campaign_fixture",
                    "status": "decision_replay_judgment_closed_no_candidate",
                    "campaign_manifest": "lab/campaigns/campaign_fixture/campaign_manifest.yaml",
                    "campaign_closeout": "lab/campaigns/campaign_fixture/campaign_closeout.yaml",
                }
            ],
        },
    )
    (wave_dir / "campaign_refs.csv").write_text(
        "wave_id,campaign_id,campaign_path,status\n"
        "wave_us100_closedbar_surface_cartography_v0,campaign_fixture,lab/campaigns/campaign_fixture/campaign_manifest.yaml,decision_replay_judgment_closed_no_candidate\n",
        encoding="utf-8",
    )
    write_yaml(
        campaign_dir / "campaign_manifest.yaml",
        {
            "version": "campaign_manifest_v1",
            "campaign_id": "campaign_fixture",
            "wave_ids": ["wave_us100_closedbar_surface_cartography_v0"],
            "status": "decision_replay_judgment_closed_no_candidate",
        },
    )
    write_yaml(
        campaign_dir / "campaign_closeout.yaml",
        {
            "version": "campaign_closeout_v1",
            "campaign_id": "campaign_fixture",
            "status": "decision_replay_judgment_closed_no_candidate",
            "counts": {"candidate_count": 1, "l5_candidate_count": 0},
            "forbidden_claims_respected": True,
        },
    )

    result = evaluate_research_cycle_closeout(tmp_path)

    assert result["status"] == "failed"
    assert any(item["id"] == "candidate_count_nonzero" for item in result["findings"])


def _minimal_closeout_payload() -> dict[str, Any]:
    return {
        "version": "wave_closeout_v2",
        "status": "wave01_evaluator_backed_closeout_requires_evidence_repair",
        "result": {"control_plane_operating_proof": "failed"},
        "result_judgment": {"failed_or_insufficient_requirements": ["control_plane_operating_proof"]},
        "claim_boundary": "test_claim_boundary",
        "active_goal_id": "goal_fixture",
        "wave_id": "wave_us100_closedbar_surface_cartography_v0",
        "source_inputs": [],
        "wave_summary": {"candidate_count": 0, "l5_candidate_count": 0},
        "campaign_summaries": [],
        "requirement_audit": [],
        "evaluation_results": [],
        "handoff": {"next_action": "repair"},
        "runtime_contract_integrity": {"status": "passed"},
        "not_claimed": ["runtime_authority", "economics_pass"],
        "next_action": "repair",
    }


def _evaluator_result(evaluator_id: str, status: str) -> dict[str, Any]:
    return finalize_result(
        {
            "version": "evaluator_result_v1",
            "evaluator_id": evaluator_id,
            "executed_at_utc": "2026-06-24T00:00:00Z",
            "input_hashes": [],
            "status": status,
            "metrics": {},
            "findings": [] if status == "passed" else [{"id": "forced_failure"}],
            "claim_effect": "test_only",
        }
    )


def _patch_closeout_evaluators(
    monkeypatch: pytest.MonkeyPatch,
    *,
    operating: dict[str, Any],
    research: dict[str, Any],
    runtime: dict[str, Any],
    routing: dict[str, Any],
    agent: dict[str, Any],
) -> None:
    patched = dict(closeout_builder.EVALUATOR_FUNCTIONS)
    patched.update(
        {
            "operating_slo_evaluator_v1": lambda repo_root: operating,
            "research_cycle_closeout_evaluator_v1": lambda repo_root: research,
            "runtime_contract_evaluator_v2": lambda repo_root: runtime,
            "routing_quality_evaluator_v1": lambda repo_root: routing,
            "agent_value_evaluator_v1": lambda repo_root: agent,
        }
    )
    monkeypatch.setattr(closeout_builder, "EVALUATOR_FUNCTIONS", patched)


class _Completed:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _seed_minimal_slo_repo(repo: Path) -> None:
    for rel_path, text in {
        "docs/policies/codex_operating_slo.yaml": yaml.safe_dump(
            {
                "version": "codex_operating_slo_v1",
                "gates": {
                    "cold_reentry_truth_files_max": 4,
                    "cold_reentry_context_bytes_max": 50000,
                    "routing_golden_accuracy_min": 0.95,
                    "protected_claim_guard_recall_min": 1.0,
                    "transaction_idempotency_required": 1.0,
                    "partial_unclassified_transactions_max": 0,
                    "durable_runs_with_unbounded_dirty_source_max": 0,
                    "agent_observation_coverage_ratio_min": 0.80,
                    "runtime_completion_contract_violations_max": 0,
                    "self_attested_closeout_requirements_max": 0,
                    "routine_solo_or_single_agent_share_min": 0.80,
                    "duplicate_agent_advice_ratio_max": 0.20,
                },
            },
            sort_keys=False,
        ),
        "AGENTS.md": "boot\n",
        "docs/workspace/workspace_state.yaml": "version: test\n",
        "docs/agent_control/policy_contract.yaml": "version: test\n",
        "docs/agent_control/work_family_registry.yaml": "version: test\n",
    }.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _write_runtime_evaluator_registry(repo: Path) -> None:
    write_yaml(
        repo / "docs" / "agent_control" / "evaluator_registry.yaml",
        {
            "version": "evaluator_registry_v1",
            "evaluators": [
                {
                    "evaluator_id": "runtime_contract_evaluator_v2",
                    "canonical_result_path": "lab/evaluations/control_plane_corrective_v3/runtime_contract_evaluator_v2.yaml",
                    "implementation_paths": [
                        "foundation/evaluation/runtime_contract_evaluator.py",
                    ],
                    "required_for_operating_closeout": True,
                    "role": "active",
                    "allowed_alias_paths": [],
                }
            ],
        },
    )


def _seed_research_registries(repo: Path) -> None:
    registers = repo / "docs" / "registers"
    registers.mkdir(parents=True, exist_ok=True)
    (registers / "candidate_registry.csv").write_text(
        "candidate_id,wave_id,campaign_id,run_id,bundle_id,surface_id,status,allocation_reason,summary_path,claim_boundary,evidence_path,missing_evidence,risk_notes,next_action\n",
        encoding="utf-8",
    )
    (registers / "clue_registry.csv").write_text(
        "clue_id,status,created_at_utc,clue_path,surface_id,sweep_id,run_ids,observed_cells,salvage_value,reopen_condition,claim_boundary,evidence_path,evidence_paths,next_action,notes\n",
        encoding="utf-8",
    )
    (registers / "negative_memory_registry.csv").write_text(
        "memory_id,hypothesis_id,surface_id,sweep_id,run_id,observed_cells,status,evidence_path,evidence_paths,failed_boundary,why_failed,salvage_value,reopen_condition,do_not_repeat_note,do_not_repeat_entries,next_action\n",
        encoding="utf-8",
    )


def _runtime_inventory_fixture() -> dict[str, Any]:
    attempts: list[dict[str, str]] = []
    for index in range(1, 35):
        for role in ("validation", "research_oos"):
            attempt_id = f"attempt_wave01_fixture_score_cell_{index:03d}_l4_{role}_v0"
            attempts.append(_inventory_entry(attempt_id, f"score_cell_{index:03d}", role, "score_probe"))
    for index in range(1, 10):
        for role in ("validation", "research_oos"):
            attempt_id = f"attempt_wave01_fixture_decision_cell_{index:03d}_l4_decision_replay_{role}_v0"
            attempts.append(_inventory_entry(attempt_id, f"decision_cell_{index:03d}", role, "decision_replay"))
    return {
        "version": "runtime_graph_target_inventory_v1",
        "expected_attempt_count": 86,
        "expected_pair_group_count": 43,
        "expected_surface_kind_counts": {"score_probe": 68, "decision_replay": 18},
        "attempts": attempts,
    }


def _inventory_entry(attempt_id: str, cell_id: str, role: str, kind: str) -> dict[str, str]:
    manifest_path = f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml"
    root = Path(manifest_path).parent
    telemetry = "execution_telemetry_summary.yaml" if kind == "decision_replay" else "score_telemetry_summary.yaml"
    return {
        "attempt_id": attempt_id,
        "manifest_path": manifest_path,
        "campaign_id": "campaign_wave01_digest_fixture_v0",
        "cell_id": cell_id,
        "period_role": role,
        "runtime_surface_kind": kind,
        "expected_terminal_summary_path": (root / "terminal_run_summary.yaml").as_posix(),
        "expected_telemetry_summary_path": (root / telemetry).as_posix(),
        "expected_tester_report_receipt_path": (root / "tester_report_receipt.yaml").as_posix(),
    }
