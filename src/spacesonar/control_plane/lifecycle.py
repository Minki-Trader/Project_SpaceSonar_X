from __future__ import annotations

from pathlib import Path

from .models import ExecutionContext, RunResult, TransactionResult
from .store import read_yaml
from .transaction import ControlPlaneTransaction


def _commit_single_manifest(context: ExecutionContext, rel_path: Path, payload: dict) -> TransactionResult:
    tx = ControlPlaneTransaction(context)
    tx.stage_yaml(rel_path, payload)
    return tx.commit()


def open_campaign(spec_path: Path, context: ExecutionContext) -> TransactionResult:
    spec = read_yaml(spec_path)
    campaign_id = spec["campaign_id"]
    payload = {
        "version": "campaign_manifest_v2",
        "campaign_id": campaign_id,
        "status": spec.get("status", "campaign_opened"),
        "created_at_utc": spec.get("created_at_utc"),
        "claim_boundary": context.claim_boundary,
        "source_spec": spec_path.as_posix(),
        "objective": spec.get("objective", ""),
        "policy_binding": spec.get("policy_binding", {}),
    }
    return _commit_single_manifest(context, Path("lab/campaigns") / campaign_id / "campaign_manifest.yaml", payload)


def materialize_run_specs(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "run_specs_manifest_v2",
        "campaign_id": campaign_id,
        "status": "materialized",
        "claim_boundary": context.claim_boundary,
    }
    return _commit_single_manifest(context, Path("lab/campaigns") / campaign_id / "run_specs_manifest.yaml", payload)


def record_run_result(run_id: str, result: RunResult, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "run_result_record_v1",
        "run_id": run_id,
        "status": result.status,
        "result_judgment": result.result_judgment,
        "claim_boundary": result.claim_boundary,
        **result.payload,
    }
    return _commit_single_manifest(context, Path("lab/runs") / run_id / "result.yaml", payload)


def judge_campaign(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "campaign_judgment_v1",
        "campaign_id": campaign_id,
        "status": "judged",
        "claim_boundary": context.claim_boundary,
    }
    return _commit_single_manifest(context, Path("lab/campaigns") / campaign_id / "campaign_judgment.yaml", payload)


def close_campaign(campaign_id: str, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "campaign_closeout_v2",
        "campaign_id": campaign_id,
        "status": "closed",
        "claim_boundary": context.claim_boundary,
    }
    return _commit_single_manifest(context, Path("lab/campaigns") / campaign_id / "campaign_closeout.yaml", payload)


def close_wave(wave_id: str, context: ExecutionContext) -> TransactionResult:
    payload = {
        "version": "wave_closeout_v2",
        "wave_id": wave_id,
        "status": "closed",
        "claim_boundary": context.claim_boundary,
    }
    return _commit_single_manifest(context, Path("lab/waves") / wave_id / "wave_closeout.yaml", payload)
