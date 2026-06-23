from __future__ import annotations

import csv
import hashlib
import inspect
import os
import socket
from pathlib import Path

import pytest
import yaml

from foundation.pipelines import control_plane_legacy_wrappers
from spacesonar import cli
from spacesonar.control_plane.lifecycle import close_campaign, close_wave, judge_campaign, materialize_run_specs, open_campaign
from spacesonar.control_plane.lock import LOCK_REL_PATH, ControlPlaneLockError, control_plane_lock
from spacesonar.control_plane.models import ExecutionContext, TransactionResult
from spacesonar.control_plane.registry_projection import (
    PROJECTIONS,
    clue_registry_projection,
    negative_memory_registry_projection,
    project_registries,
    projection_diffs,
    write_registry_projections,
)
from spacesonar.control_plane.state_projection import workspace_projection_text
from spacesonar.control_plane.transaction import ControlPlaneTransaction


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spec_payload() -> dict:
    claim_boundary = "campaign_open_only_no_runtime_authority_no_economics_pass"
    return {
        "version": "campaign_lifecycle_spec_v1",
        "campaign_id": "campaign_wave02_surface_probe_v0",
        "goal_id": "goal_wave02_fixture_v0",
        "wave_id": "wave_wave02_fixture_v0",
        "idea_id": "idea_wave02_fixture_v0",
        "hypothesis_id": "hyp_wave02_fixture_v0",
        "surface_id": "surface_wave02_fixture_v0",
        "sweep_id": "sweep_wave02_fixture_v0",
        "status": "campaign_opened",
        "created_at_utc": "2026-06-23T00:00:00Z",
        "objective": "Open a synthetic Wave02 multi-axis surface.",
        "axis_tags": ["target_or_label_surface", "feature_or_input_surface", "decision_surface"],
        "claim_boundary": claim_boundary,
        "routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
        },
        "exploration_coverage": {
            "mode": "unexplored_surface_discovery_not_single_axis_progression",
            "primary_unknown_axis": "decision_surface",
            "required_research_axes": ["target_or_label_surface", "feature_or_input_surface"],
            "companion_axes": ["model_or_training_surface", "evaluation_or_runtime_surface"],
        },
        "policy_binding": {"revision": "policy_contract_v2", "guards": ["GUARD_003_CLAIM_BOUNDARY"]},
        "storage_contract": {"durable_identity_policy": "repo_relative_paths_only"},
        "next_work_item": {
            "version": "work_item_lite_v1",
            "work_item_id": "work_wave02_materialize_fixture_v0",
            "request_digest": "fixture_digest",
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "verification_profile": "governance",
            "targets": ["lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml"],
            "acceptance_criteria": ["materialize declared run specs"],
            "claim_boundary": claim_boundary,
            "policy_binding": {"revision": "policy_contract_v2", "guards": ["GUARD_003_CLAIM_BOUNDARY"]},
            "outputs": ["lab/campaigns/campaign_wave02_surface_probe_v0/run_specs/"],
            "next_action": "materialize synthetic specs",
            "summary": "materialize synthetic specs",
            "path": "lab/goals/goal_wave02_fixture_v0/next_work_item.yaml",
            "provenance": {"source": "test_fixture"},
        },
        "recipe_refs": {
            "label_recipe_id": "label_fixture_v0",
            "feature_recipe_id": "feature_fixture_v0",
            "model_recipe_id": "model_fixture_v0",
            "decision_recipe_id": "decision_fixture_v0",
            "split_recipe_id": "split_fixture_v0",
            "eval_recipe_id": "eval_fixture_v0",
        },
        "materialization": {
            "run_specs": [
                {
                    "run_id": "run_wave02_fixture_001",
                    "recipe_refs": {
                        "label_recipe_id": "label_fixture_v0",
                        "feature_recipe_id": "feature_fixture_v0",
                        "model_recipe_id": "model_fixture_v0",
                        "decision_recipe_id": "decision_fixture_v0",
                    },
                    "split_profile": "split_fixture_v0",
                    "evaluation_profile": "eval_fixture_v0",
                    "verification_profile": "runtime",
                    "acceptance_criteria": ["record proxy observation"],
                }
            ]
        },
        "judgment_contract": {
            "evidence_inputs": ["lab/campaigns/campaign_wave02_surface_probe_v0/evidence/judgment.yaml"],
            "result_judgment": "inconclusive",
            "evaluator_refs": ["fixture_evaluator_v0"],
            "candidate_effect": "no_candidate_claimed",
            "clue_effect": "no_new_clue_claimed",
            "negative_memory_effect": "no_new_negative_memory_claimed",
            "missing_evidence": ["runtime_authority_not_claimed"],
            "reopen_conditions": ["new evidence"],
        },
        "next_action": "materialize synthetic specs",
    }


def write_spec(tmp_path: Path, payload: dict | None = None) -> Path:
    spec = tmp_path / "spec.yaml"
    spec.write_text(yaml.safe_dump(payload or spec_payload(), sort_keys=False), encoding="utf-8")
    return spec


def context(tmp_path: Path) -> ExecutionContext:
    return ExecutionContext(
        repo_root=tmp_path,
        work_item_id="work_wp04_test",
        claim_boundary="control_plane_operation_only_no_runtime_authority_no_economics_pass",
        command_argv=("campaign", "open"),
        validation_commands=("registry_projection_check", "workspace_projection_check"),
    )


def artifact_paths(root: Path) -> set[str]:
    rows = list(csv.DictReader((root / "docs/registers/artifact_registry.csv").read_text(encoding="utf-8").splitlines()))
    return {row["path_or_uri"] for row in rows}


def write_judgment_evidence(root: Path) -> None:
    write_yaml(
        root / "lab/campaigns/campaign_wave02_surface_probe_v0/evidence/judgment.yaml",
        {"status": "evidence_present", "claim_boundary": "fixture_only"},
    )


def test_campaign_open_preserves_non_target_fields_and_updates_graph_neighbors(tmp_path: Path) -> None:
    campaign = tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml"
    write_yaml(
        campaign,
        {
            "campaign_id": "campaign_wave02_surface_probe_v0",
            "custom_non_target": "keep_me",
            "wave_ids": ["wave_existing_v0"],
            "idea_ids": ["idea_existing_v0"],
            "hypothesis_ids": ["hyp_existing_v0"],
        },
    )

    result = open_campaign(write_spec(tmp_path), context(tmp_path))

    assert result.status == "committed", result.errors
    campaign_payload = load_yaml(campaign)
    assert campaign_payload["custom_non_target"] == "keep_me"
    assert campaign_payload["wave_ids"] == ["wave_existing_v0", "wave_wave02_fixture_v0"]
    assert campaign_payload["idea_ids"] == ["idea_existing_v0", "idea_wave02_fixture_v0"]
    assert campaign_payload["hypothesis_ids"] == ["hyp_existing_v0", "hyp_wave02_fixture_v0"]
    assert (tmp_path / "lab/surfaces/surface_wave02_fixture_v0/surface_manifest.yaml").exists()
    assert (tmp_path / "lab/hypotheses/hyp_wave02_fixture_v0.yaml").exists()
    assert (tmp_path / "lab/hypotheses/idea_wave02_fixture_v0.yaml").exists()
    assert (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/sweeps/sweep_wave02_fixture_v0/sweep_manifest.yaml").exists()
    assert (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/sweeps/sweep_wave02_fixture_v0/run_refs.csv").exists()
    assert "campaign_wave02_surface_probe_v0" in (tmp_path / "lab/waves/wave_wave02_fixture_v0/campaign_refs.csv").read_text(encoding="utf-8")
    assert load_yaml(tmp_path / "lab/goals/goal_wave02_fixture_v0/goal_manifest.yaml")["active_ids"]["campaign_id"] == "campaign_wave02_surface_probe_v0"
    assert "acceptance_criteria" in load_yaml(tmp_path / "lab/goals/goal_wave02_fixture_v0/next_work_item.yaml")
    assert projection_diffs(tmp_path) == []
    assert "surface_wave02_fixture_v0" in (tmp_path / "docs/registers/experiment_surface_registry.csv").read_text(encoding="utf-8")
    assert "idea_wave02_fixture_v0" in (tmp_path / "docs/registers/idea_registry.csv").read_text(encoding="utf-8")
    assert "hyp_wave02_fixture_v0" in (tmp_path / "docs/registers/hypothesis_registry.csv").read_text(encoding="utf-8")
    assert "goal_wave02_fixture_v0" in (tmp_path / "docs/workspace/workspace_state.yaml").read_text(encoding="utf-8")
    registry_rows = list(csv.DictReader((tmp_path / "docs/registers/campaign_registry.csv").read_text(encoding="utf-8").splitlines()))
    assert all((tmp_path / row["evidence_path"]).exists() for row in registry_rows)
    expected_artifacts = {
        "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml",
        "lab/hypotheses/idea_wave02_fixture_v0.yaml",
        "lab/hypotheses/hyp_wave02_fixture_v0.yaml",
        "lab/surfaces/surface_wave02_fixture_v0/surface_manifest.yaml",
        "lab/campaigns/campaign_wave02_surface_probe_v0/sweeps/sweep_wave02_fixture_v0/sweep_manifest.yaml",
        "lab/campaigns/campaign_wave02_surface_probe_v0/sweeps/sweep_wave02_fixture_v0/run_refs.csv",
        "lab/goals/goal_wave02_fixture_v0/goal_manifest.yaml",
        "lab/goals/goal_wave02_fixture_v0/next_work_item.yaml",
        "lab/waves/wave_wave02_fixture_v0/wave_allocation.yaml",
        "lab/waves/wave_wave02_fixture_v0/campaign_refs.csv",
        "docs/registers/idea_registry.csv",
        "docs/registers/hypothesis_registry.csv",
    }
    assert expected_artifacts <= artifact_paths(tmp_path)


def test_incomplete_open_spec_is_rejected_with_zero_mutation(tmp_path: Path) -> None:
    spec = write_spec(tmp_path, {"version": "campaign_lifecycle_spec_v1", "campaign_id": "campaign_incomplete_v0"})

    result = open_campaign(spec, context(tmp_path))

    assert result.status == "aborted_validation_failed"
    assert not (tmp_path / "lab").exists()
    assert not (tmp_path / ".spacesonar/transactions").exists()


def test_mid_lifecycle_fault_rolls_back_all_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_commit = ControlPlaneTransaction.commit

    def failing_commit(self: ControlPlaneTransaction, *args, **kwargs):
        kwargs["fail_after_replace_count"] = 1
        return original_commit(self, *args, **kwargs)

    monkeypatch.setattr(ControlPlaneTransaction, "commit", failing_commit)

    result = open_campaign(write_spec(tmp_path), context(tmp_path))

    assert result.status == "rolled_back_commit_failure"
    assert not (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml").exists()
    assert not (tmp_path / "docs/registers/campaign_registry.csv").exists()
    assert not (tmp_path / "docs/workspace/workspace_state.yaml").exists()
    assert not (tmp_path / LOCK_REL_PATH).exists()


def test_closeout_requires_evidence_inputs_and_commits_zero_closeout(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "lab/campaigns/campaign_no_evidence_v0/campaign_manifest.yaml",
        {"campaign_id": "campaign_no_evidence_v0", "status": "judged"},
    )

    result = close_campaign("campaign_no_evidence_v0", context(tmp_path))

    assert result.status == "aborted_validation_failed"
    assert not (tmp_path / "lab/campaigns/campaign_no_evidence_v0/campaign_closeout.yaml").exists()


def test_nonexistent_campaign_materialize_and_judge_are_rejected(tmp_path: Path) -> None:
    materialized = materialize_run_specs("campaign_missing_v0", context(tmp_path))
    judged = judge_campaign("campaign_missing_v0", context(tmp_path))

    assert materialized.status == "aborted_validation_failed"
    assert judged.status == "aborted_validation_failed"
    assert not (tmp_path / "lab").exists()


def test_materialize_judge_campaign_close_and_wave_close_state_machine(tmp_path: Path) -> None:
    assert open_campaign(write_spec(tmp_path), context(tmp_path)).status == "committed"
    assert close_wave("wave_wave02_fixture_v0", context(tmp_path)).status == "aborted_validation_failed"
    assert materialize_run_specs("campaign_wave02_surface_probe_v0", context(tmp_path)).status == "committed"
    run_spec = load_yaml(tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/run_specs/run_wave02_fixture_001.yaml")
    assert run_spec["recipe_refs"]["model_recipe_id"] == "model_fixture_v0"
    assert run_spec["split_profile"] == "split_fixture_v0"
    assert run_spec["evaluation_profile"] == "eval_fixture_v0"
    assert run_spec["verification_profile"] == "runtime"
    refs = (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/sweeps/sweep_wave02_fixture_v0/run_refs.csv").read_text(encoding="utf-8")
    assert "run_wave02_fixture_001" in refs
    assert load_yaml(tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml")["status"] == "run_specs_materialized"
    assert any(path.endswith("run_wave02_fixture_001.yaml") for path in artifact_paths(tmp_path))
    no_evidence = judge_campaign("campaign_wave02_surface_probe_v0", context(tmp_path))
    assert no_evidence.status == "aborted_validation_failed"
    write_judgment_evidence(tmp_path)

    judged = judge_campaign("campaign_wave02_surface_probe_v0", context(tmp_path))
    closed = close_campaign("campaign_wave02_surface_probe_v0", context(tmp_path))
    wave_closed = close_wave("wave_wave02_fixture_v0", context(tmp_path))

    assert judged.status == "committed"
    assert closed.status == "committed"
    assert wave_closed.status == "committed"
    assert load_yaml(tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml")["status"] == "closed"
    assert load_yaml(tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_closeout.yaml")["candidate_effect"] == "no_candidate_claimed"
    refs = (tmp_path / "lab/waves/wave_wave02_fixture_v0/campaign_refs.csv").read_text(encoding="utf-8")
    assert "closed" in refs
    assert "close_campaign" not in (tmp_path / "docs/workspace/workspace_state.yaml").read_text(encoding="utf-8")
    assert load_yaml(tmp_path / "lab/waves/wave_wave02_fixture_v0/wave_allocation.yaml")["status"] == "closed"
    assert load_yaml(tmp_path / "lab/goals/goal_wave02_fixture_v0/goal_manifest.yaml")["status"] == "wave_closed"
    assert load_yaml(tmp_path / "lab/waves/wave_wave02_fixture_v0/wave_closeout.yaml")["evaluator_backed"] is True


def test_all_nine_registry_projection_checks_detect_drift(tmp_path: Path) -> None:
    result = open_campaign(write_spec(tmp_path), context(tmp_path))
    assert result.status == "committed"
    write_registry_projections(tmp_path)

    for rel_path in sorted(PROJECTIONS, key=lambda item: item.as_posix()):
        for projected_path, text in project_registries(tmp_path).items():
            (tmp_path / projected_path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / projected_path).write_text(text, encoding="utf-8")
        path = tmp_path / rel_path
        path.write_text(path.read_text(encoding="utf-8") + "manual_drift\n", encoding="utf-8")
        assert rel_path.as_posix() in projection_diffs(tmp_path)


def test_registry_projection_updates_registry_artifact_hashes(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "lab/memory/clues/clue_fixture_v0.yaml",
        {
            "clue_id": "clue_fixture_v0",
            "status": "preserved",
            "created_at_utc": "2026-06-23T00:00:00Z",
            "evidence_path": "lab/memory/clues/clue_fixture_v0.yaml",
        },
    )
    artifact_registry = tmp_path / "docs/registers/artifact_registry.csv"
    artifact_registry.parent.mkdir(parents=True, exist_ok=True)
    artifact_registry.write_text(
        "artifact_id,run_id,bundle_id,attempt_id,artifact_type,path_or_uri,sha256,size_bytes,availability,producer_command,regeneration_command,source_of_truth,consumer,claim_boundary,notes\n"
        "artifact_clue_registry_v0,,,,registry,docs/registers/clue_registry.csv,bad,1,present_hash_recorded,,,,,,\n",
        encoding="utf-8",
    )

    write_registry_projections(tmp_path)

    clue_text = (tmp_path / "docs/registers/clue_registry.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(artifact_registry.read_text(encoding="utf-8").splitlines()))
    assert rows[0]["sha256"] == sha256_text(clue_text)
    assert rows[0]["size_bytes"] == str(len(clue_text.encode("utf-8")))


def test_memory_projection_preserves_current_semantic_values() -> None:
    clue_rows = list(csv.DictReader(clue_registry_projection(REPO_ROOT).splitlines()))
    clue_by_id = {row["clue_id"]: row for row in clue_rows}
    clue_source = load_yaml(REPO_ROOT / "lab/memory/clues/clue_wave01_session_transition_remaining_decision_surface_needed_v0.yaml")
    clue = clue_by_id[clue_source["clue_id"]]
    assert clue["status"] == clue_source["clue_type"]
    assert clue["observed_cells"] == ";".join(clue_source["observed_cells"])
    assert clue["evidence_paths"] == ";".join(clue_source["evidence_paths"])
    assert clue["reopen_condition"]

    negative_rows = list(csv.DictReader(negative_memory_registry_projection(REPO_ROOT).splitlines()))
    negative_by_id = {row["memory_id"]: row for row in negative_rows}
    negative_source = load_yaml(REPO_ROOT / "lab/memory/negative/neg_wave01_session_transition_inverse_score_band_decision_replay_loss_v0.yaml")
    negative = negative_by_id[negative_source["negative_memory_id"]]
    assert negative["status"] == negative_source["failed_boundary"]
    assert negative["observed_cells"] == ";".join(negative_source["observed_cells"])
    assert negative["evidence_paths"] == ";".join(negative_source["evidence_paths"])
    assert negative["reopen_condition"]


def test_workspace_projection_selects_synthetic_active_goal_and_wave(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "lab/goals/goal_a/goal_manifest.yaml",
        {
            "active_goal_id": "goal_a",
            "status": "older",
            "created_at_utc": "2026-01-01T00:00:00Z",
            "updated_at_utc": "2026-01-01T00:00:00Z",
            "active_ids": {"wave_id": "wave_a"},
        },
    )
    write_yaml(tmp_path / "lab/waves/wave_a/wave_allocation.yaml", {"wave_id": "wave_a", "status": "older"})
    write_yaml(
        tmp_path / "lab/goals/goal_b/goal_manifest.yaml",
        {
            "active_goal_id": "goal_b",
            "status": "active",
            "workspace_active": True,
            "updated_at_utc": "2026-06-23T00:00:00Z",
            "active_ids": {"wave_id": "wave_b", "campaign_id": "campaign_b"},
            "next_work_item": {"work_item_id": "work_b", "summary": "next b"},
            "claim_boundary": "goal_b_boundary",
        },
    )
    write_yaml(
        tmp_path / "lab/waves/wave_b/wave_allocation.yaml",
        {
            "wave_id": "wave_b",
            "active_goal_id": "goal_b",
            "status": "active_wave",
            "storage_contract": {"wave_closeout": "lab/waves/wave_b/wave_closeout.yaml"},
        },
    )
    write_yaml(
        tmp_path / "lab/waves/wave_b/wave_closeout.yaml",
        {"status": "wave_b_closed", "result": {"candidate_count": 0, "l5_candidate_count": 0}},
    )

    text = workspace_projection_text(tmp_path)

    assert "goal_b" in text
    assert "wave_b" in text
    assert "goal_a" not in text


def test_workspace_projection_rejects_two_active_goals_and_missing_requested_wave(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "lab/goals/goal_a/goal_manifest.yaml",
        {"active_goal_id": "goal_a", "workspace_active": True, "active_ids": {"wave_id": "wave_a"}},
    )
    write_yaml(
        tmp_path / "lab/goals/goal_b/goal_manifest.yaml",
        {"active_goal_id": "goal_b", "workspace_active": True, "active_ids": {"wave_id": "wave_b"}},
    )
    write_yaml(tmp_path / "lab/waves/wave_a/wave_allocation.yaml", {"wave_id": "wave_a"})
    write_yaml(tmp_path / "lab/waves/wave_b/wave_allocation.yaml", {"wave_id": "wave_b"})
    with pytest.raises(ValueError, match="multiple workspace-active goals"):
        workspace_projection_text(tmp_path)

    (tmp_path / "lab/goals/goal_b/goal_manifest.yaml").unlink()
    (tmp_path / "lab/waves/wave_a/wave_allocation.yaml").unlink()
    with pytest.raises(ValueError, match="missing wave_id"):
        workspace_projection_text(tmp_path)


def test_legacy_wrapper_contains_no_direct_mutation_logic() -> None:
    source = inspect.getsource(control_plane_legacy_wrappers)

    forbidden = [
        "csv.DictWriter",
        "yaml.safe_dump",
        "write_text(",
        "registry",
        "workspace",
        "sha256",
    ]
    for token in forbidden:
        assert token not in source


def test_every_declared_legacy_lifecycle_script_is_thin() -> None:
    manifest = load_yaml(REPO_ROOT / "docs/agent_control/legacy_lifecycle_entrypoints.yaml")
    forbidden = [
        "csv.DictWriter",
        "yaml.safe_dump",
        ".write_text(",
        "registry",
        "workspace",
        "sha256",
        "git rev-parse",
    ]
    for entry in manifest["entrypoints"]:
        source = (REPO_ROOT / entry["path"]).read_text(encoding="utf-8-sig")
        for token in forbidden:
            assert token not in source, entry["path"]


def test_concurrent_lifecycle_command_is_rejected_by_lock(tmp_path: Path) -> None:
    lock = tmp_path / LOCK_REL_PATH
    write_yaml(
        lock,
        {
            "version": "control_plane_lock_v1",
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "command": "other",
            "work_item_id": "work_other",
            "started_at_utc": "2026-06-23T00:00:00Z",
        },
    )

    result = open_campaign(write_spec(tmp_path), context(tmp_path))

    assert result.status == "aborted_validation_failed"
    assert "lock held by live owner" in result.errors[0]
    assert not (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0").exists()


def test_stale_lock_recovery_is_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock = tmp_path / LOCK_REL_PATH
    write_yaml(
        lock,
        {
            "version": "control_plane_lock_v1",
            "pid": 999999,
            "hostname": socket.gethostname(),
            "command": "old",
            "work_item_id": "work_old",
            "started_at_utc": "2026-06-23T00:00:00Z",
        },
    )
    monkeypatch.setattr("spacesonar.control_plane.lock.owner_is_live", lambda _owner: False)

    with pytest.raises(ControlPlaneLockError, match="requires --recover-stale-lock"):
        with control_plane_lock(context(tmp_path)):
            pass
    recovered_context = ExecutionContext(
        repo_root=tmp_path,
        work_item_id="work_wp04_test",
        claim_boundary="control_plane_operation_only_no_runtime_authority_no_economics_pass",
        command_argv=("campaign", "open"),
        validation_commands=("registry_projection_check", "workspace_projection_check"),
        recover_stale_lock=True,
    )
    with control_plane_lock(recovered_context):
        assert lock.exists()
    assert not lock.exists()


def write_progress(tmp_path: Path, *, wp04_status: str) -> None:
    write_yaml(
        tmp_path / cli.CORRECTIVE_PROGRESS_PATH,
        {
            "version": cli.CORRECTIVE_LEDGER_VERSION,
            "work_item_id": cli.CORRECTIVE_WORK_ITEM_ID,
            "branch": cli.CORRECTIVE_BRANCH,
            "work_units": {
                "WP02": {"status": "completed"},
                "WP04": {"status": wp04_status},
            },
        },
    )


def test_cli_blocks_until_wp04_completed_then_activates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "current_git_branch", lambda _repo_root: cli.CORRECTIVE_BRANCH)
    called = {"open": False}

    def fake_open_campaign(_spec_path: Path, context: ExecutionContext) -> TransactionResult:
        called["open"] = True
        return TransactionResult("tx_fake", "noop_already_applied", context.repo_root / "receipt.yaml")

    monkeypatch.setattr(cli, "open_campaign", fake_open_campaign)
    spec = write_spec(tmp_path)
    write_progress(tmp_path, wp04_status="in_progress")

    blocked = cli.main(["--repo-root", str(tmp_path), "--work-item-id", "work_wp04_test", "campaign", "open", "--spec", str(spec)])

    assert blocked == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert not (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml").exists()

    write_progress(tmp_path, wp04_status="completed")
    activated = cli.main(["--repo-root", str(tmp_path), "--work-item-id", "work_wp04_test", "campaign", "open", "--spec", str(spec)])

    assert activated == 0
    assert called["open"] is True
