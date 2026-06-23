from __future__ import annotations

from pathlib import Path

import yaml

from spacesonar.control_plane.lifecycle import open_campaign
from spacesonar.control_plane.models import ExecutionContext


def test_second_identical_command_writes_byte_identical_manifest(tmp_path: Path) -> None:
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "campaign_id": "campaign_test_v0",
                "status": "campaign_opened",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "objective": "test objective",
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
