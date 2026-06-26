from __future__ import annotations

from pathlib import Path

import yaml

from foundation.validation.control_plane_validator import validate_agent_consult_receipts


def _write_receipt(repo_root: Path, path: Path) -> Path:
    path.parent.mkdir(parents=True)
    data = {
        "version": "agent_consult_receipt_v2",
        "consult_id": "consult_test_v2",
        "profile": "micro_specialist",
        "question_digest": "sha256:test",
        "selected_agent_ids": ["agent_01_system_governor"],
        "source_refs": ["AGENTS.md"],
        "opinions": [
            {
                "opinion_id": "opinion_test",
                "classification": "accepted",
                "evidence_refs": ["AGENTS.md"],
            }
        ],
        "owner_decision": "historical record only",
        "verification_refs": ["AGENTS.md"],
        "claim_effect": "historical_advisory_only_no_reviewed_pass",
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_historical_initial_task_force_receipt_is_tolerated_as_archive_only(tmp_path: Path) -> None:
    _write_receipt(
        tmp_path,
        tmp_path / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "task_force_consultation_initial_v2.yaml",
    )

    assert validate_agent_consult_receipts(tmp_path) == []


def test_new_agent_consult_receipt_is_rejected(tmp_path: Path) -> None:
    _write_receipt(tmp_path, tmp_path / "lab" / "goals" / "goal_test" / "agent_consult.yaml")

    errors = validate_agent_consult_receipts(tmp_path)

    assert any("active agent consult receipts are disabled" in error for error in errors)
