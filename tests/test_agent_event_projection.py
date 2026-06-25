from __future__ import annotations

from pathlib import Path

import yaml

from spacesonar.control_plane.agent_metrics import (
    AGENT_EVENTS_PATH,
    agent_operating_events_diff,
    project_agent_events,
    validate_agent_events_projection,
    write_agent_operating_events,
)


def _write_progress(repo_root: Path) -> None:
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
                            "consult_ids": ["consult_test_v2"],
                            "source_refs": [],
                            "started_at_utc": "2026-06-24T00:05:00Z",
                            "ended_at_utc": "2026-06-24T00:10:00Z",
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_receipt(repo_root: Path, *, created_at_utc: str = "2026-06-24T00:06:00Z") -> None:
    path = repo_root / "lab" / "goals" / "goal_test" / "task_force_consultation_test_v2.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": "agent_consult_receipt_v2",
                "consult_id": "consult_test_v2",
                "created_at_utc": created_at_utc,
                "profile": "micro_specialist",
                "question_digest": "sha256:test",
                "selected_agent_ids": ["agent_01_system_governor"],
                "opinions": [
                    {"opinion_id": "opinion_a", "classification": "accepted", "evidence_refs": ["AGENTS.md"]},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_agent_events_are_derived_from_progress_ledger(tmp_path: Path) -> None:
    _write_progress(tmp_path)
    _write_receipt(tmp_path)

    events = project_agent_events(tmp_path)

    assert events["version"] == "agent_operating_events_v2"
    assert events["work_item_events"][0]["work_item_id"] == "WP00"
    assert events["consult_events"][0]["consult_id"] == "consult_test_v2"
    assert events["consult_events"][0]["in_boundary"] is True


def test_agent_events_use_work_receipt_when_present(tmp_path: Path) -> None:
    _write_progress(tmp_path)
    receipt_path = tmp_path / "docs" / "workspace" / "agent_work_receipts" / "WP00.yaml"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        yaml.safe_dump(
            {
                "version": "agent_work_receipt_v1",
                "work_item_id": "WP00",
                "agent_mode": "solo",
                "evidence_class": "contemporaneous_work_receipt",
                "consult_ids": [],
                "started_at_utc": "2026-06-24T00:05:00Z",
                "ended_at_utc": "2026-06-24T00:10:00Z",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    event = project_agent_events(tmp_path)["work_item_events"][0]

    assert event["source_refs"][0]["path"] == "docs/workspace/agent_work_receipts/WP00.yaml"
    assert event["work_receipt_ref"]["sha256"]


def test_out_of_boundary_consult_is_classified_not_silently_counted(tmp_path: Path) -> None:
    _write_progress(tmp_path)
    _write_receipt(tmp_path, created_at_utc="2026-06-23T23:59:59Z")

    consult = project_agent_events(tmp_path)["consult_events"][0]

    assert consult["in_boundary"] is False
    assert consult["boundary_class"] == "historical_out_of_boundary"


def test_duplicate_work_item_and_consult_ids_fail_validation() -> None:
    events = {
        "version": "agent_operating_events_v2",
        "work_item_events": [
            {"work_item_id": "WP00", "agent_mode": "solo", "evidence_class": "contemporaneous_work_receipt"},
            {"work_item_id": "WP00", "agent_mode": "solo", "evidence_class": "contemporaneous_work_receipt"},
        ],
        "consult_events": [
            {"consult_id": "consult_a", "work_item_id": "WP00"},
            {"consult_id": "consult_a", "work_item_id": "WP00"},
        ],
    }

    errors = validate_agent_events_projection(Path("."), events)

    assert any("duplicate work_item_id WP00" in error for error in errors)
    assert any("duplicate consult_id consult_a" in error for error in errors)


def test_hand_edited_agent_event_source_hash_fails(tmp_path: Path) -> None:
    _write_progress(tmp_path)
    _write_receipt(tmp_path)
    events = project_agent_events(tmp_path)
    events["work_item_events"][0]["source_refs"][0]["sha256"] = "bad"

    errors = validate_agent_events_projection(tmp_path, events)

    assert any("source hash mismatch" in error for error in errors)


def test_manual_agent_mode_change_fails_projection_check(tmp_path: Path) -> None:
    _write_progress(tmp_path)
    _write_receipt(tmp_path)
    write_agent_operating_events(tmp_path)
    path = tmp_path / AGENT_EVENTS_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["work_item_events"][0]["agent_mode"] = "micro_specialist"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    assert agent_operating_events_diff(tmp_path) == [
        "docs/workspace/agent_operating_events.yaml: generated projection drift"
    ]
