from __future__ import annotations

from pathlib import Path
import hashlib

import yaml

from spacesonar.control_plane.lifecycle import open_campaign
from spacesonar.control_plane.models import ExecutionContext


def test_second_identical_command_writes_byte_identical_manifest(tmp_path: Path) -> None:
    objective_path = tmp_path / "lab/goals/goal_test_v0/objective.yaml"
    objective_path.parent.mkdir(parents=True, exist_ok=True)
    objective_path.write_text("objective: idempotency fixture\n", encoding="utf-8")
    objective_hash = hashlib.sha256(objective_path.read_bytes()).hexdigest()
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "version": "campaign_lifecycle_spec_v1",
                "campaign_id": "campaign_test_v0",
                "goal_id": "goal_test_v0",
                "wave_id": "wave_test_v0",
                "idea_id": "idea_test_v0",
                "hypothesis_id": "hyp_test_v0",
                "surface_id": "surface_test_v0",
                "sweep_id": "sweep_test_v0",
                "status": "campaign_opened",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "objective": "test objective",
                "claim_boundary": "claim_boundary",
                "routing": {
                    "primary_family": "experiment_design",
                    "primary_skill": "spacesonar-experiment-design",
                },
                "exploration_coverage": {
                    "mode": "fixture",
                    "primary_unknown_axis": "decision_surface",
                    "required_research_axes": ["target_or_label_surface"],
                    "companion_axes": ["evaluation_or_runtime_surface"],
                },
                "policy_binding": {"revision": "policy_contract_v2", "guards": ["GUARD_003_CLAIM_BOUNDARY"]},
                "storage_contract": {"durable_identity_policy": "repo_relative_paths_only"},
                "objective_identity": {
                    "source_type": "test_fixture",
                    "content_hash_sha256": objective_hash,
                    "source_path": "lab/goals/goal_test_v0/objective.yaml",
                    "summary": "idempotency fixture",
                },
                "objective_revision": {
                    "revision_id": "objective_test_v0",
                    "source_of_truth": "lab/goals/goal_test_v0/objective.yaml",
                    "primary_objective": "idempotency",
                    "proof_window": "unit_test",
                },
                "next_work_item": {
                    "version": "work_item_lite_v1",
                    "work_item_id": "work_test_next_v0",
                    "request_digest": "fixture",
                    "primary_family": "experiment_design",
                    "primary_skill": "spacesonar-experiment-design",
                    "verification_profile": "governance",
                    "targets": ["lab/campaigns/campaign_test_v0/campaign_manifest.yaml"],
                    "acceptance_criteria": ["open fixture campaign"],
                    "claim_boundary": "claim_boundary",
                    "policy_binding": {"revision": "policy_contract_v2", "guards": ["GUARD_003_CLAIM_BOUNDARY"]},
                    "outputs": [],
                    "next_action": "materialize fixture",
                    "summary": "materialize fixture",
                    "path": "lab/goals/goal_test_v0/next_work_item.yaml",
                    "provenance": {"source": "test"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    context = ExecutionContext(tmp_path, "work_test", "claim_boundary", ("open",))

    first = open_campaign(spec, context)
    manifest_path = tmp_path / "lab/campaigns/campaign_test_v0/campaign_manifest.yaml"
    first_bytes = manifest_path.read_bytes()
    second = open_campaign(spec, context)

    assert first.status == "committed"
    assert second.status == "noop_already_applied"
    assert second.committed_paths == ()
    assert manifest_path.read_bytes() == first_bytes
