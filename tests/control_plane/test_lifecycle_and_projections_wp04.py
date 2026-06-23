from __future__ import annotations

import csv
import hashlib
import inspect
from pathlib import Path

import pytest
import yaml

from foundation.pipelines import control_plane_legacy_wrappers
from spacesonar import cli
from spacesonar.control_plane.lifecycle import close_campaign, open_campaign
from spacesonar.control_plane.models import ExecutionContext
from spacesonar.control_plane.registry_projection import PROJECTIONS, projection_diffs, write_registry_projections
from spacesonar.control_plane.state_projection import workspace_projection_text
from spacesonar.control_plane.transaction import ControlPlaneTransaction


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spec_payload() -> dict:
    return {
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
        "claim_boundary": "campaign_open_only_no_runtime_authority_no_economics_pass",
        "routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
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


def test_campaign_open_preserves_non_target_fields_and_updates_graph_neighbors(tmp_path: Path) -> None:
    campaign = tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml"
    write_yaml(campaign, {"campaign_id": "campaign_wave02_surface_probe_v0", "custom_non_target": "keep_me"})

    result = open_campaign(write_spec(tmp_path), context(tmp_path))

    assert result.status == "committed"
    assert load_yaml(campaign)["custom_non_target"] == "keep_me"
    assert (tmp_path / "lab/surfaces/surface_wave02_fixture_v0/surface_manifest.yaml").exists()
    assert (tmp_path / "lab/hypotheses/hyp_wave02_fixture_v0.yaml").exists()
    assert (tmp_path / "lab/hypotheses/idea_wave02_fixture_v0.yaml").exists()
    assert (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/sweeps/sweep_wave02_fixture_v0/sweep_manifest.yaml").exists()
    assert "campaign_wave02_surface_probe_v0" in (tmp_path / "lab/waves/wave_wave02_fixture_v0/campaign_refs.csv").read_text(encoding="utf-8")
    assert load_yaml(tmp_path / "lab/goals/goal_wave02_fixture_v0/goal_manifest.yaml")["active_ids"]["campaign_id"] == "campaign_wave02_surface_probe_v0"
    assert projection_diffs(tmp_path) == []
    assert "surface_wave02_fixture_v0" in (tmp_path / "docs/registers/experiment_surface_registry.csv").read_text(encoding="utf-8")
    assert "goal_wave02_fixture_v0" in (tmp_path / "docs/workspace/workspace_state.yaml").read_text(encoding="utf-8")


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


def test_closeout_requires_evidence_inputs_and_commits_zero_closeout(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "lab/campaigns/campaign_no_evidence_v0/campaign_manifest.yaml",
        {"campaign_id": "campaign_no_evidence_v0", "status": "judged"},
    )

    result = close_campaign("campaign_no_evidence_v0", context(tmp_path))

    assert result.status == "aborted_validation_failed"
    assert not (tmp_path / "lab/campaigns/campaign_no_evidence_v0/campaign_closeout.yaml").exists()


def test_all_nine_registry_projection_checks_detect_drift(tmp_path: Path) -> None:
    result = open_campaign(write_spec(tmp_path), context(tmp_path))
    assert result.status == "committed"
    write_registry_projections(tmp_path)

    for rel_path in sorted(PROJECTIONS, key=lambda item: item.as_posix()):
        write_registry_projections(tmp_path)
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
    spec = write_spec(tmp_path)
    write_progress(tmp_path, wp04_status="in_progress")

    blocked = cli.main(["--repo-root", str(tmp_path), "--work-item-id", "work_wp04_test", "campaign", "open", "--spec", str(spec)])

    assert blocked == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert not (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml").exists()

    write_progress(tmp_path, wp04_status="completed")
    activated = cli.main(["--repo-root", str(tmp_path), "--work-item-id", "work_wp04_test", "campaign", "open", "--spec", str(spec)])

    assert activated == 0
    assert (tmp_path / "lab/campaigns/campaign_wave02_surface_probe_v0/campaign_manifest.yaml").exists()
