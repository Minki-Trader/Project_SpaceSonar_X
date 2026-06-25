from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from spacesonar.control_plane.agent_metrics import (
    AGENT_METRICS_PATH,
    agent_operating_metrics_diff,
    project_agent_operating_metrics,
    write_agent_operating_events,
    write_agent_operating_metrics,
)


def _copy_registry(repo_root: Path, source_root: Path) -> None:
    target = repo_root / "docs" / "agent_control"
    target.mkdir(parents=True)
    shutil.copyfile(
        source_root / "docs" / "agent_control" / "codex_task_force_registry.yaml",
        target / "codex_task_force_registry.yaml",
    )


def _write_progress(repo_root: Path, *, consult_created_at: str = "2026-06-24T00:30:00Z") -> None:
    path = repo_root / "docs" / "migrations" / "control_plane_corrective_v3_progress.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": "corrective_workflow_progress_v1",
                "initialized_at_utc": "2026-06-24T00:00:00Z",
                "completed_at_utc": "2026-06-24T01:00:00Z",
                "work_units": {
                    "WP00": {
                        "agent_execution": {
                            "mode": "solo",
                            "evidence_class": "contemporaneous_work_receipt",
                            "consult_ids": [],
                            "source_refs": [],
                            "started_at_utc": "2026-06-24T00:05:00Z",
                            "ended_at_utc": "2026-06-24T00:10:00Z",
                        }
                    },
                    "WP01": {
                        "agent_execution": {
                            "mode": "micro_specialist",
                            "evidence_class": "contemporaneous_work_receipt",
                            "consult_ids": [],
                            "source_refs": [],
                            "started_at_utc": "2026-06-24T00:10:00Z",
                            "ended_at_utc": "2026-06-24T00:20:00Z",
                        }
                    },
                    "WP02": {
                        "agent_execution": {
                            "mode": "micro_adversarial",
                            "evidence_class": "contemporaneous_work_receipt",
                            "consult_ids": ["consult_test_v2"],
                            "source_refs": [],
                            "started_at_utc": "2026-06-24T00:20:00Z",
                            "ended_at_utc": "2026-06-24T00:40:00Z",
                        }
                    },
                },
                "test_consult_created_at": consult_created_at,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_receipt(repo_root: Path, *, created_at_utc: str = "2026-06-24T00:30:00Z") -> None:
    path = repo_root / "lab" / "goals" / "goal_test" / "task_force_consultation_test_v2.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": "agent_consult_receipt_v2",
                "consult_id": "consult_test_v2",
                "created_at_utc": created_at_utc,
                "profile": "micro_adversarial",
                "question_digest": "sha256:test",
                "selected_agent_ids": ["agent_01_system_governor", "agent_02_platform_routing_architect"],
                "role_modes": {
                    "agent_01_system_governor": "design",
                    "agent_02_platform_routing_architect": "preflight",
                },
                "source_refs": ["AGENTS.md"],
                "opinions": [
                    {"opinion_id": "opinion_a", "classification": "accepted", "summary": "same", "evidence_refs": ["AGENTS.md"]},
                    {"opinion_id": "opinion_b", "classification": "rewritten", "summary": "same", "evidence_refs": ["AGENTS.md"]},
                    {"opinion_id": "opinion_c", "classification": "rejected", "summary": "unique", "evidence_refs": []},
                    {"opinion_id": "opinion_d", "classification": "accepted", "summary": "other", "evidence_refs": ["AGENTS.md"]},
                ],
                "owner_decision": "accepted after local verification",
                "verification_refs": ["AGENTS.md"],
                "claim_effect": "advisory_only_no_reviewed_pass",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_agent_ratios_are_reproducible_from_progress_and_consult_items(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_progress(tmp_path)
    _write_receipt(tmp_path)
    write_agent_operating_events(tmp_path)

    projected = project_agent_operating_metrics(tmp_path)
    metrics = projected["agent_operating_metrics"]

    assert metrics["work_item_count"] == 3
    assert metrics["observed_work_item_count"] == 3
    assert metrics["solo_work_item_count"] == 1
    assert metrics["consult_count"] == 1
    assert metrics["two_agent_consult_count"] == 1
    assert metrics["total_advice_items"] == 4
    assert metrics["duplicate_advice_items"] == 1
    assert metrics["accepted_after_verification_count"] == 2
    assert metrics["solo_work_share"] == 0.333333
    assert metrics["observation_coverage_ratio"] == 1.0
    assert metrics["two_agent_consult_share"] == 1.0
    assert metrics["routine_solo_or_single_agent_share"] == 0.666667
    assert metrics["duplicate_advice_ratio"] == 0.25


def test_out_of_boundary_consultation_is_excluded(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_progress(tmp_path)
    _write_receipt(tmp_path, created_at_utc="2026-06-23T23:59:59Z")
    write_agent_operating_events(tmp_path)

    metrics = project_agent_operating_metrics(tmp_path)["agent_operating_metrics"]

    assert metrics["work_item_count"] == 3
    assert metrics["consult_count"] == 0
    assert metrics["total_advice_items"] == 0


def test_manually_edited_agent_metric_fails_projection_check(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _copy_registry(tmp_path, source_root)
    _write_progress(tmp_path)
    _write_receipt(tmp_path)
    write_agent_operating_events(tmp_path)
    write_agent_operating_metrics(tmp_path)

    metrics_path = tmp_path / AGENT_METRICS_PATH
    data = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))
    data["agent_operating_metrics"]["consult_count"] = 99
    metrics_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    assert agent_operating_metrics_diff(tmp_path) == [
        "docs/workspace/agent_operating_metrics.yaml: generated projection drift"
    ]
