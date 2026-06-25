from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from spacesonar.control_plane.agent_metrics import (
    AGENT_EVENTS_PATH,
    AGENT_HISTORY_DIR,
    AGENT_METRICS_PATH,
    AGENT_WINDOWS_PATH,
    begin_agent_work,
    close_agent_observation_window,
    open_agent_observation_window,
    project_agent_events,
    project_agent_operating_metrics,
    validate_agent_window_close_ready,
    write_agent_operating_events,
    write_agent_operating_metrics,
)


FAMILIES = [
    "workspace_state_sync",
    "policy_skill_governance",
    "code_refactor",
    "artifact_lineage",
    "publish_handoff",
]


def _seed_repo(repo_root: Path) -> None:
    registry = repo_root / "docs" / "agent_control" / "work_family_registry.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        yaml.safe_dump({"version": "test", "work_families": {family: {} for family in FAMILIES}}, sort_keys=False),
        encoding="utf-8",
    )
    slo = repo_root / "docs" / "policies" / "codex_operating_slo.yaml"
    slo.parent.mkdir(parents=True)
    slo.write_text(
        yaml.safe_dump(
            {
                "version": "codex_operating_slo_v1",
                "gates": {
                    "routine_solo_or_single_agent_share_min": 0.80,
                    "duplicate_agent_advice_ratio_max": 0.20,
                    "agent_observation_coverage_ratio_min": 0.80,
                    "agent_observed_work_item_count_min": 5,
                    "agent_observed_distinct_work_family_count_min": 4,
                    "agent_observation_window_closed_required": True,
                    "agent_receipt_validation_failure_count_max": 0,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    history = repo_root / AGENT_HISTORY_DIR
    history.mkdir(parents=True)
    events_snapshot = history / "control_plane_corrective_v3_events.yaml"
    metrics_snapshot = history / "control_plane_corrective_v3_metrics.yaml"
    events_snapshot.write_text("historical events\n", encoding="utf-8")
    metrics_snapshot.write_text("historical metrics\n", encoding="utf-8")
    windows = {
        "version": "agent_observation_windows_v1",
        "active_window_id": None,
        "windows": {
            "control_plane_corrective_v3_historical": {
                "status": "closed",
                "role": "historical_preserved",
                "start_utc": "2026-06-22T23:53:38Z",
                "end_utc": "2026-06-25T04:13:30Z",
                "event_snapshot_path": events_snapshot.relative_to(repo_root).as_posix(),
                "metric_snapshot_path": metrics_snapshot.relative_to(repo_root).as_posix(),
                "event_snapshot_sha256": __import__("hashlib").sha256(events_snapshot.read_bytes()).hexdigest(),
                "metric_snapshot_sha256": __import__("hashlib").sha256(metrics_snapshot.read_bytes()).hexdigest(),
                "observed_work_item_count": 1,
                "work_item_count": 8,
                "observation_coverage_ratio": 0.125,
                "claim_effect": "historical_telemetry_preserved_not_reclassified_as_contemporaneous",
            }
        },
    }
    (repo_root / AGENT_WINDOWS_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo_root / AGENT_WINDOWS_PATH).write_text(yaml.safe_dump(windows, sort_keys=False), encoding="utf-8")
    events = repo_root / AGENT_EVENTS_PATH
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(yaml.safe_dump({"version": "agent_operating_events_v2", "work_item_events": [], "consult_events": []}), encoding="utf-8")


def _evidence(repo_root: Path, work_item_id: str) -> str:
    path = repo_root / "lab" / "operating_proofs" / "post_wp08_operating_proof_v1" / work_item_id / "command_results.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"work_item_id": work_item_id, "status": "passed"}, sort_keys=False), encoding="utf-8")
    return path.relative_to(repo_root).as_posix()


def _open(repo_root: Path) -> None:
    open_agent_observation_window(
        repo_root,
        window_id="post_wp08_operating_proof_v1",
        minimum_observed_work_items=5,
        minimum_distinct_work_families=4,
        command_argv=("test", "window", "open"),
    )


def _begin_finalize(repo_root: Path, idx: int, *, family: str, result_status: str = "passed") -> None:
    work_item_id = f"work_agentproof_{idx}_v1"
    begin_agent_work(
        repo_root,
        window_id="post_wp08_operating_proof_v1",
        work_item_id=work_item_id,
        primary_family=family,
        agent_mode="solo",
        claim_boundary="test_boundary_no_runtime_authority",
        command_argv=("test", "begin"),
    )
    from spacesonar.control_plane.agent_metrics import finalize_agent_work

    finalize_agent_work(
        repo_root,
        work_item_id=work_item_id,
        result_status=result_status,
        evidence_refs=[_evidence(repo_root, work_item_id)],
        command_argv=("test", "finalize"),
    )


def test_historical_one_of_eight_metrics_remain_immutable_after_projection_changes(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _open(tmp_path)
    for idx, family in enumerate(FAMILIES, start=1):
        _begin_finalize(tmp_path, idx, family=family)
    close_agent_observation_window(tmp_path, window_id="post_wp08_operating_proof_v1", command_argv=("test", "close"))
    write_agent_operating_events(tmp_path)
    write_agent_operating_metrics(tmp_path)

    metrics = yaml.safe_load((tmp_path / AGENT_METRICS_PATH).read_text(encoding="utf-8"))
    historical = metrics["historical_windows"][0]
    assert historical["work_item_count"] == 8
    assert historical["observed_work_item_count"] == 1
    assert historical["observation_coverage_ratio"] == 0.125


def test_open_window_returns_insufficient_evidence(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _open(tmp_path)
    events = project_agent_events(tmp_path)
    (tmp_path / AGENT_EVENTS_PATH).write_text(yaml.safe_dump(events, sort_keys=False), encoding="utf-8")
    metrics = project_agent_operating_metrics(tmp_path)
    (tmp_path / AGENT_METRICS_PATH).write_text(yaml.safe_dump(metrics, sort_keys=False), encoding="utf-8")

    result = evaluate_agent_value(tmp_path)

    assert result["status"] == "insufficient_evidence"
    assert any(item["id"] == "agent_observation_window_not_closed" for item in result["findings"])


def test_one_item_window_cannot_pass_minimum_sample_gate(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _open(tmp_path)
    _begin_finalize(tmp_path, 1, family=FAMILIES[0])

    with pytest.raises(RuntimeError):
        close_agent_observation_window(tmp_path, window_id="post_wp08_operating_proof_v1", command_argv=("test", "close"))


def test_fewer_than_four_work_families_cannot_close(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _open(tmp_path)
    for idx in range(1, 6):
        _begin_finalize(tmp_path, idx, family=FAMILIES[0])

    with pytest.raises(RuntimeError):
        close_agent_observation_window(tmp_path, window_id="post_wp08_operating_proof_v1", command_argv=("test", "close"))


def test_failed_drill_blocks_window_close(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _open(tmp_path)
    for idx, family in enumerate(FAMILIES, start=1):
        _begin_finalize(tmp_path, idx, family=family, result_status="failed" if idx == 3 else "passed")

    with pytest.raises(RuntimeError):
        close_agent_observation_window(tmp_path, window_id="post_wp08_operating_proof_v1", command_argv=("test", "close"))


def test_five_valid_work_items_produce_five_of_five_coverage(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _open(tmp_path)
    for idx, family in enumerate(FAMILIES, start=1):
        _begin_finalize(tmp_path, idx, family=family)
    close_agent_observation_window(tmp_path, window_id="post_wp08_operating_proof_v1", command_argv=("test", "close"))
    write_agent_operating_events(tmp_path)
    write_agent_operating_metrics(tmp_path)

    metrics = yaml.safe_load((tmp_path / AGENT_METRICS_PATH).read_text(encoding="utf-8"))["agent_operating_metrics"]

    assert validate_agent_window_close_ready(tmp_path, "post_wp08_operating_proof_v1") == []
    assert metrics["observation_window_id"] == "post_wp08_operating_proof_v1"
    assert metrics["observation_window_status"] == "closed"
    assert metrics["work_item_count"] == 5
    assert metrics["observed_work_item_count"] == 5
    assert metrics["observed_distinct_work_family_count"] == 5
    assert metrics["observation_coverage_ratio"] == 1.0
    assert metrics["routine_solo_or_single_agent_share"] == 1.0
    assert metrics["receipt_validation_failure_count"] == 0
    assert evaluate_agent_value(tmp_path)["status"] == "passed"
