from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from foundation.validation.control_plane_validator import validate_agent_consult_receipts


def _copy_registry(repo_root: Path, source_root: Path) -> None:
    target = repo_root / "docs" / "agent_control"
    target.mkdir(parents=True)
    shutil.copyfile(
        source_root / "docs" / "agent_control" / "codex_task_force_registry.yaml",
        target / "codex_task_force_registry.yaml",
    )


def _write_receipt(repo_root: Path, **updates: object) -> Path:
    path = repo_root / "lab" / "goals" / "goal_test" / "agent_consult.yaml"
    path.parent.mkdir(parents=True)
    data = {
        "version": "agent_consult_receipt_v2",
        "consult_id": "consult_test_v2",
        "profile": "micro_specialist",
        "question_digest": "sha256:test",
        "selected_agent_ids": ["agent_01_system_governor"],
        "role_modes": {"agent_01_system_governor": "design"},
        "source_refs": ["AGENTS.md"],
        "opinions": [
            {
                "opinion_id": "opinion_test",
                "classification": "accepted",
                "evidence_refs": ["AGENTS.md"],
            }
        ],
        "owner_decision": "accepted after local verification",
        "verification_refs": ["AGENTS.md"],
        "claim_effect": "advisory_only_no_reviewed_pass",
        "metrics": {
            "total_advice_items": 1,
            "duplicate_advice_items": 0,
            "unsupported_assertions": 0,
            "accepted_after_verification": 1,
            "rejected_after_verification": 0,
            "rewritten_after_verification": 0,
        },
    }
    data.update(updates)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_agent_consult_receipt_v2_validates(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(tmp_path)

    assert validate_agent_consult_receipts(tmp_path) == []


def test_agent_consult_receipt_rejects_unknown_agent(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(tmp_path, selected_agent_ids=["missing_agent"])

    errors = validate_agent_consult_receipts(tmp_path)
    assert any("unknown registry agent ids" in error for error in errors)


def test_agent_consult_receipt_requires_escalation_for_three_agents(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(
        tmp_path,
        profile="formal_protected_review",
        selected_agent_ids=[
            "agent_01_system_governor",
            "agent_02_platform_routing_architect",
            "agent_03_philosophy_policy_skill_governance",
        ],
        role_modes={
            "agent_01_system_governor": "design",
            "agent_02_platform_routing_architect": "preflight",
            "agent_03_philosophy_policy_skill_governance": "evidence_check",
        },
    )

    errors = validate_agent_consult_receipts(tmp_path)
    assert any("3 or more agents require escalation_reason" in error for error in errors)


def test_agent_consult_receipt_rejects_unknown_role_mode(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(tmp_path, role_modes={"agent_01_system_governor": "rubber_stamp"})

    errors = validate_agent_consult_receipts(tmp_path)
    assert any("unknown role modes" in error for error in errors)


def test_agent_consult_receipt_requires_verification_refs_for_accepted_advice(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(
        tmp_path,
        opinions=[
            {
                "opinion_id": "opinion_test",
                "classification": "accepted",
                "evidence_refs": [],
            }
        ],
    )

    errors = validate_agent_consult_receipts(tmp_path)
    assert any("accepted/rewritten advice requires evidence_refs" in error for error in errors)
