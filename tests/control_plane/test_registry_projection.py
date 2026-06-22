from __future__ import annotations

from pathlib import Path

import yaml

from spacesonar.control_plane.registry_projection import projection_diffs, write_registry_projections


def seed_repo(root: Path) -> None:
    goal = root / "lab/goals/goal_a/goal_manifest.yaml"
    goal.parent.mkdir(parents=True)
    goal.write_text(
        yaml.safe_dump(
            {
                "active_goal_id": "goal_a",
                "status": "open",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "active_phase": "phase_a",
                "claim_boundary": "no_runtime_authority",
                "storage_contract": {"terminal_eligibility_contract": "lab/goals/goal_a/terminal.yaml"},
                "next_work_item": {"work_item_id": "work_next", "summary": "next"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    wave = root / "lab/waves/wave_a/wave_allocation.yaml"
    wave.parent.mkdir(parents=True)
    wave.write_text(
        yaml.safe_dump(
            {
                "wave_id": "wave_a",
                "status": "open",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "allocation_goal": "map surfaces",
                "claim_boundary": "no_runtime_authority",
                "budget": {"max_runs": 1},
                "storage_contract": {"wave_closeout": "lab/waves/wave_a/wave_closeout.yaml"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (root / "lab/waves/wave_a/wave_closeout.yaml").write_text("next_action: work_next\n", encoding="utf-8")
    campaign = root / "lab/campaigns/campaign_a/campaign_manifest.yaml"
    campaign.parent.mkdir(parents=True)
    campaign.write_text(
        yaml.safe_dump(
            {
                "campaign_id": "campaign_a",
                "status": "open",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "objective": "test",
                "axis_tags": ["a", "b"],
                "routing": {"primary_family": "experiment_design", "primary_skill": "spacesonar-experiment-design"},
                "claim_boundary": "no_runtime_authority",
                "next_action": "work_next",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_registry_projection_detects_manual_drift(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    write_registry_projections(tmp_path)

    assert projection_diffs(tmp_path) == []

    goal_registry = tmp_path / "docs/registers/goal_registry.csv"
    goal_registry.write_text(goal_registry.read_text(encoding="utf-8").replace("work_next", "manual_edit", 1), encoding="utf-8")

    assert "docs/registers/goal_registry.csv" in projection_diffs(tmp_path)
