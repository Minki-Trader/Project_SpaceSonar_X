from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from foundation.validation.active_record_validator import FIXTURE_GATE, validate


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_evidence_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name in ["docs", "lab", "runtime"]:
        shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(
        ROOT / "foundation" / "mt5",
        repo / "foundation" / "mt5",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return repo


def active_ids(repo: Path) -> tuple[str, str, str]:
    state = load_yaml(repo / "docs" / "workspace" / "workspace_state.yaml")
    claims = state["current_claims"]
    return (
        claims["first_vertical_slice_run_id"],
        claims["first_vertical_slice_bundle_id"],
        claims["first_vertical_slice_attempt_id"],
    )


def test_active_validator_rejects_stale_receipt_after_mt5_closeout(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    run_id, _bundle_id, _attempt_id = active_ids(repo)
    receipt_path = repo / "lab" / "runs" / run_id / "experiment_receipt.yaml"
    receipt = load_yaml(receipt_path)
    coverage = receipt["required_gate_coverage"]
    coverage["passed"] = [item for item in coverage["passed"] if item != FIXTURE_GATE]
    coverage["missing"] = [*coverage.get("missing", []), FIXTURE_GATE]
    receipt["missing_evidence"] = ["MT5 native ONNX fixed-fixture output not observed yet"]
    receipt["claim_boundary"] = "bundle_preflight"
    receipt["result_judgment"] = "inconclusive"
    write_yaml(receipt_path, receipt)

    errors = validate(repo)

    assert any("receipt" in error and FIXTURE_GATE in error for error in errors)


def test_active_validator_rejects_registry_path_missing_from_lineage(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    run_id, _bundle_id, _attempt_id = active_ids(repo)
    lineage_path = repo / "lab" / "runs" / run_id / "artifact_lineage.json"
    lineage = load_json(lineage_path)
    lineage["artifact_paths"] = [
        item
        for item in lineage["artifact_paths"]
        if not (isinstance(item, dict) and item.get("path", "").endswith("mt5_probe_summary.yaml"))
    ]
    write_json(lineage_path, lineage)

    errors = validate(repo)

    assert any("registry path missing from lineage" in error and "mt5_probe_summary.yaml" in error for error in errors)


def test_active_validator_rejects_completed_campaign_with_planning_status(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    campaign_path = repo / "lab" / "campaigns" / "campaign_minimal_onnx_mt5_vertical_slice_v0" / "campaign_manifest.yaml"
    campaign = load_yaml(campaign_path)
    campaign["vertical_slice_entry_contract"]["dataset"]["status"] = "to_materialize_in_target_branch"
    write_yaml(campaign_path, campaign)

    errors = validate(repo)

    assert any("completed campaign retains planning status" in error for error in errors)


def test_active_validator_rejects_missing_ea_entrypoint_hash(tmp_path: Path) -> None:
    repo = copy_evidence_repo(tmp_path)
    _run_id, _bundle_id, attempt_id = active_ids(repo)
    attempt_path = repo / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    attempt = load_yaml(attempt_path)
    attempt["artifact_identity"]["ea_entrypoint"]["sha256"] = None
    write_yaml(attempt_path, attempt)

    errors = validate(repo)

    assert any("ea_entrypoint sha256 is missing" in error for error in errors)
