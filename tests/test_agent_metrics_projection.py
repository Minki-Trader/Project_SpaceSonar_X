from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from spacesonar.control_plane.agent_metrics import (
    AGENT_METRICS_PATH,
    agent_operating_metrics_diff,
    project_agent_operating_metrics,
    write_agent_operating_metrics,
)


def _copy_registry(repo_root: Path, source_root: Path) -> None:
    target = repo_root / "docs" / "agent_control"
    target.mkdir(parents=True)
    shutil.copyfile(
        source_root / "docs" / "agent_control" / "codex_task_force_registry.yaml",
        target / "codex_task_force_registry.yaml",
    )


def _write_receipt(repo_root: Path) -> None:
    path = repo_root / "lab" / "goals" / "goal_test" / "agent_consult.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": "agent_consult_receipt_v2",
                "consult_id": "consult_test_v2",
                "profile": "micro_adversarial",
                "question_digest": "sha256:test",
                "selected_agent_ids": ["agent_01_system_governor", "agent_02_platform_routing_architect"],
                "role_modes": {
                    "agent_01_system_governor": "design",
                    "agent_02_platform_routing_architect": "preflight",
                },
                "source_refs": ["AGENTS.md"],
                "opinions": [
                    {"opinion_id": "opinion_a", "classification": "accepted", "evidence_refs": ["AGENTS.md"]},
                    {"opinion_id": "opinion_b", "classification": "rewritten", "evidence_refs": ["AGENTS.md"]},
                ],
                "owner_decision": "accepted after local verification",
                "verification_refs": ["AGENTS.md"],
                "claim_effect": "advisory_only_no_reviewed_pass",
                "metrics": {
                    "total_advice_items": 4,
                    "duplicate_advice_items": 1,
                    "unsupported_assertions": 0,
                    "accepted_after_verification": 1,
                    "rejected_after_verification": 0,
                    "rewritten_after_verification": 1,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_events(repo_root: Path) -> None:
    path = repo_root / "docs" / "workspace" / "agent_operating_events.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": "agent_operating_events_v1",
                "updated_utc": "2026-06-24T00:00:00Z",
                "measurement_boundary": "test_projection_only",
                "work_item_events": [
                    {"work_item_id": "WP00", "agent_mode": "solo"},
                    {"work_item_id": "WP01", "agent_mode": "solo"},
                    {"work_item_id": "WP02", "agent_mode": "solo"},
                ],
                "consult_receipts": [
                    {"path": "lab/goals/goal_test/agent_consult.yaml"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_agent_ratios_are_reproducible_from_event_counts(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(tmp_path)
    _write_events(tmp_path)

    projected = project_agent_operating_metrics(tmp_path)
    metrics = projected["agent_operating_metrics"]

    assert metrics["work_item_count"] == 3
    assert metrics["solo_work_item_count"] == 3
    assert metrics["consult_count"] == 1
    assert metrics["two_agent_consult_count"] == 1
    assert metrics["total_advice_items"] == 4
    assert metrics["duplicate_advice_items"] == 1
    assert metrics["accepted_after_verification_count"] == 1
    assert metrics["solo_work_share"] == 0.75
    assert metrics["two_agent_share"] == 0.25
    assert metrics["duplicate_advice_ratio"] == 0.25


def test_manually_edited_agent_metric_fails_projection_check(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_receipt(tmp_path)
    _write_events(tmp_path)
    write_agent_operating_metrics(tmp_path)

    metrics_path = tmp_path / AGENT_METRICS_PATH
    data = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    data["agent_operating_metrics"]["consult_count"] = 99
    metrics_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    assert agent_operating_metrics_diff(tmp_path) == [
        "docs/workspace/agent_operating_metrics.yaml: generated projection drift"
    ]
