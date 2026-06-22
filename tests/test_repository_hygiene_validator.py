from __future__ import annotations

from pathlib import Path

import yaml

from foundation.validation.repository_hygiene_validator import validate


def _write_policy_files(repo_root: Path) -> None:
    policy_dir = repo_root / "docs" / "policies"
    policy_dir.mkdir(parents=True)
    (policy_dir / "branch_policy.md").write_text(
        """
```yaml
main_integration_policy:
  allowed_boundary_events:
    - control_plane_stabilization
  merge_mode: squash_only
  direct_push: forbidden
```
""",
        encoding="utf-8",
    )
    (policy_dir / "github_branch_protection_required.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "github_branch_protection_required_v1",
                "required_settings": {
                    "pull_request_required": True,
                    "squash_merge_only": True,
                    "force_push": "disabled",
                    "direct_push": "forbidden",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_repository_hygiene_accepts_clean_tracked_ignored_list(tmp_path: Path) -> None:
    _write_policy_files(tmp_path)

    assert validate(tmp_path, tracked_ignored=[]) == []


def test_repository_hygiene_rejects_tracked_ignored_artifact(tmp_path: Path) -> None:
    _write_policy_files(tmp_path)

    errors = validate(tmp_path, tracked_ignored=["lab/runs/example/artifacts/model.onnx"])
    assert any("tracked ignored artifact outside allowlist" in error for error in errors)
