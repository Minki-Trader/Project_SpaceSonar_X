from __future__ import annotations

from pathlib import Path

import yaml

from spacesonar.control_plane.state_projection import workspace_projection_text, write_workspace_projection


def test_workspace_projection_excludes_historical_payloads(tmp_path: Path) -> None:
    goal = tmp_path / "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml"
    goal.parent.mkdir(parents=True)
    goal.write_text(
        yaml.safe_dump(
            {
                    "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
                    "workspace_active": True,
                    "status": "closed",
                "updated_at_utc": "2026-06-22T00:00:00Z",
                "claim_boundary": "no_runtime_authority",
                "active_ids": {"campaign_id": "campaign_a"},
                "next_work_item": {"work_item_id": "work_next", "path": "next.yaml", "summary": "next"},
                "historical_campaign_details": ["do not copy me"] * 50,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    wave = tmp_path / "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml"
    wave.parent.mkdir(parents=True)
    wave.write_text("wave_id: wave_us100_closedbar_surface_cartography_v0\nstatus: closed\n", encoding="utf-8")
    (wave.parent / "wave_closeout.yaml").write_text("candidate_count: 0\nl5_candidate_count: 0\n", encoding="utf-8")

    text = workspace_projection_text(tmp_path)
    write_workspace_projection(tmp_path)

    assert "historical_campaign_details" not in text
    assert len(text.splitlines()) < 100
    assert (tmp_path / "docs/workspace/workspace_state.yaml").exists()
