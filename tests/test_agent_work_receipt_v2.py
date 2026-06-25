from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from foundation.validation.execution_provenance_validator import validate_agent_work_receipt
from spacesonar.control_plane.agent_metrics import (
    AGENT_WINDOWS_PATH,
    FINAL_RECEIPT_VERSION,
    START_RECEIPT_VERSION,
    begin_agent_work,
    finalize_agent_work,
    open_agent_observation_window,
    validate_agent_observation_windows,
    v2_finalization_receipt_path,
    v2_start_receipt_path,
    with_receipt_self_hash,
)


def _write_registry(repo_root: Path) -> None:
    path = repo_root / "docs" / "agent_control" / "work_family_registry.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": "test",
                "work_families": {
                    "workspace_state_sync": {},
                    "policy_skill_governance": {},
                    "code_refactor": {},
                    "artifact_lineage": {},
                    "publish_handoff": {},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _open_window(repo_root: Path) -> None:
    _write_registry(repo_root)
    open_agent_observation_window(
        repo_root,
        window_id="post_wp08_operating_proof_v1",
        minimum_observed_work_items=5,
        minimum_distinct_work_families=4,
        command_argv=("test", "window", "open"),
    )


def _write_evidence(repo_root: Path, work_item_id: str, text: str = "ok\n") -> Path:
    path = repo_root / "lab" / "operating_proofs" / "post_wp08_operating_proof_v1" / work_item_id / "command_results.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_new_receipts_do_not_require_wp06_specific_refs(tmp_path: Path) -> None:
    _open_window(tmp_path)
    begin_agent_work(
        tmp_path,
        window_id="post_wp08_operating_proof_v1",
        work_item_id="work_agentproof_cold_reentry_v1",
        primary_family="workspace_state_sync",
        agent_mode="solo",
        claim_boundary="test_boundary",
        command_argv=("test", "begin"),
    )
    evidence = _write_evidence(tmp_path, "work_agentproof_cold_reentry_v1")
    finalize_agent_work(
        tmp_path,
        work_item_id="work_agentproof_cold_reentry_v1",
        result_status="passed",
        evidence_refs=[evidence.relative_to(tmp_path).as_posix()],
        command_argv=("test", "finalize"),
    )

    assert validate_agent_work_receipt(tmp_path, v2_start_receipt_path("work_agentproof_cold_reentry_v1")) == []
    assert validate_agent_work_receipt(tmp_path, v2_finalization_receipt_path("work_agentproof_cold_reentry_v1")) == []


def test_finalization_without_start_receipt_fails(tmp_path: Path) -> None:
    _open_window(tmp_path)
    final_path = tmp_path / v2_finalization_receipt_path("work_missing_start")
    final_path.parent.mkdir(parents=True)
    final_path.write_text(
        yaml.safe_dump(
            with_receipt_self_hash(
                {
                    "version": FINAL_RECEIPT_VERSION,
                    "receipt_status": "finalized",
                    "work_item_id": "work_missing_start",
                    "observation_window_id": "post_wp08_operating_proof_v1",
                    "primary_family": "workspace_state_sync",
                    "agent_mode": "solo",
                    "consult_ids": [],
                    "evidence_class": "contemporaneous_work_receipt",
                    "start_receipt_ref": {"path": v2_start_receipt_path("work_missing_start").as_posix(), "sha256": "missing", "size_bytes": 0},
                    "ended_at_utc": "2026-06-25T00:00:01Z",
                    "end_commit_sha": "abc",
                    "result_status": "passed",
                    "command_results": [],
                    "evidence_refs": [],
                    "validation_results": [],
                    "claim_boundary": "test_boundary",
                    "receipt_sha256": {"algorithm": "sha256", "value": ""},
                }
            ),
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_agent_work_receipt(tmp_path, v2_finalization_receipt_path("work_missing_start"))
    assert any("start receipt missing" in error or "start_receipt_ref" in error for error in errors)


def test_start_final_receipt_id_mismatch_fails(tmp_path: Path) -> None:
    _open_window(tmp_path)
    begin_agent_work(
        tmp_path,
        window_id="post_wp08_operating_proof_v1",
        work_item_id="work_agentproof_cold_reentry_v1",
        primary_family="workspace_state_sync",
        agent_mode="solo",
        claim_boundary="test_boundary",
        command_argv=("test", "begin"),
    )
    evidence = _write_evidence(tmp_path, "work_agentproof_cold_reentry_v1")
    finalize_agent_work(
        tmp_path,
        work_item_id="work_agentproof_cold_reentry_v1",
        result_status="passed",
        evidence_refs=[evidence.relative_to(tmp_path).as_posix()],
        command_argv=("test", "finalize"),
    )
    final_path = tmp_path / v2_finalization_receipt_path("work_agentproof_cold_reentry_v1")
    payload = yaml.safe_load(final_path.read_text(encoding="utf-8"))
    payload["work_item_id"] = "other_work"
    final_path.write_text(yaml.safe_dump(with_receipt_self_hash(payload), sort_keys=False), encoding="utf-8")

    errors = validate_agent_work_receipt(tmp_path, v2_finalization_receipt_path("work_agentproof_cold_reentry_v1"))
    assert any("start/final work_item_id mismatch" in error for error in errors)


def test_receipt_self_hash_tampering_fails(tmp_path: Path) -> None:
    _open_window(tmp_path)
    begin_agent_work(
        tmp_path,
        window_id="post_wp08_operating_proof_v1",
        work_item_id="work_agentproof_cold_reentry_v1",
        primary_family="workspace_state_sync",
        agent_mode="solo",
        claim_boundary="test_boundary",
        command_argv=("test", "begin"),
    )
    path = tmp_path / v2_start_receipt_path("work_agentproof_cold_reentry_v1")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["claim_boundary"] = "tampered"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert any("self-hash mismatch" in error for error in validate_agent_work_receipt(tmp_path, v2_start_receipt_path("work_agentproof_cold_reentry_v1")))


def test_evidence_hash_tampering_fails(tmp_path: Path) -> None:
    _open_window(tmp_path)
    begin_agent_work(
        tmp_path,
        window_id="post_wp08_operating_proof_v1",
        work_item_id="work_agentproof_cold_reentry_v1",
        primary_family="workspace_state_sync",
        agent_mode="solo",
        claim_boundary="test_boundary",
        command_argv=("test", "begin"),
    )
    evidence = _write_evidence(tmp_path, "work_agentproof_cold_reentry_v1")
    finalize_agent_work(
        tmp_path,
        work_item_id="work_agentproof_cold_reentry_v1",
        result_status="passed",
        evidence_refs=[evidence.relative_to(tmp_path).as_posix()],
        command_argv=("test", "finalize"),
    )
    evidence.write_text("changed\n", encoding="utf-8")

    errors = validate_agent_work_receipt(tmp_path, v2_finalization_receipt_path("work_agentproof_cold_reentry_v1"))
    assert any("evidence_refs: ref hash mismatch" in error for error in errors)


def test_receipt_begin_time_cannot_predate_window(tmp_path: Path) -> None:
    _open_window(tmp_path)
    begin_agent_work(
        tmp_path,
        window_id="post_wp08_operating_proof_v1",
        work_item_id="work_agentproof_cold_reentry_v1",
        primary_family="workspace_state_sync",
        agent_mode="solo",
        claim_boundary="test_boundary",
        command_argv=("test", "begin"),
    )
    window_payload = yaml.safe_load((tmp_path / AGENT_WINDOWS_PATH).read_text(encoding="utf-8"))
    window_payload["windows"]["post_wp08_operating_proof_v1"]["start_utc"] = "2999-01-01T00:00:00Z"
    (tmp_path / AGENT_WINDOWS_PATH).write_text(yaml.safe_dump(window_payload, sort_keys=False), encoding="utf-8")

    errors = validate_agent_observation_windows(tmp_path)
    assert any("started_at_utc outside observation window" in error for error in errors)


def test_one_receipt_cannot_belong_to_two_windows(tmp_path: Path) -> None:
    _open_window(tmp_path)
    begin_agent_work(
        tmp_path,
        window_id="post_wp08_operating_proof_v1",
        work_item_id="work_agentproof_cold_reentry_v1",
        primary_family="workspace_state_sync",
        agent_mode="solo",
        claim_boundary="test_boundary",
        command_argv=("test", "begin"),
    )
    payload = yaml.safe_load((tmp_path / AGENT_WINDOWS_PATH).read_text(encoding="utf-8"))
    copied = copy.deepcopy(payload["windows"]["post_wp08_operating_proof_v1"])
    copied["status"] = "closed"
    copied["end_utc"] = "2999-01-02T00:00:00Z"
    payload["windows"]["second_window"] = copied
    (tmp_path / AGENT_WINDOWS_PATH).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    errors = validate_agent_observation_windows(tmp_path)
    assert any("receipt belongs to multiple windows" in error or "duplicate receipt path" in error for error in errors)
