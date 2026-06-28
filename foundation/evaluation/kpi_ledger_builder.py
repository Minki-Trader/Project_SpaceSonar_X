from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.kpi_record_model import (  # noqa: E402
    DEFAULT_CLAIM_BOUNDARY,
    FORBIDDEN_CLAIMS,
    KPI_SEGMENT_CLAIM_POLICY,
    KPI_LEDGER_CONTRACT_VERSION,
    KPI_LEDGER_MANIFEST_VERSION,
    KPI_RECORD_FIELDNAMES,
    KPI_RECORD_SCHEMA_VERSION,
    KPI_SUMMARY_VERSION,
    OPTIONAL_KPI_SEGMENT_AXES,
    REQUIRED_KPI_SEGMENT_AXES,
)
from foundation.mt5.tester_report_kpi import TESTER_REPORT_METRICS, parse_tester_report_kpis  # noqa: E402
from foundation.mt5.trade_shape_reconstruction import (  # noqa: E402
    DEFAULT_RAW_BARS,
    reconstruct_attempt,
)


TRADING_RUNTIME_SURFACE_KINDS = {"decision_execution", "decision_replay"}
NON_TRADING_RUNTIME_SURFACE_KINDS = {"score_probe"}


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def artifact_ref(path: Path, repo_root: Path) -> dict[str, Any]:
    full = path if path.is_absolute() else repo_root / path
    return {
        "path": repo_rel(full, repo_root),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": "present_hash_recorded",
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=KPI_RECORD_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in KPI_RECORD_FIELDNAMES})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_existing_csv(path: Path) -> list[dict[str, str]]:
    return read_csv(path) if path.exists() else []


def upsert_records(existing: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in existing:
        record_id = str(row.get("record_id", ""))
        if not record_id:
            continue
        if record_id not in by_id:
            order.append(record_id)
        by_id[record_id] = dict(row)
    for row in new_rows:
        record_id = str(row.get("record_id", ""))
        if not record_id:
            raise RuntimeError("KPI record missing record_id")
        if record_id not in by_id:
            order.append(record_id)
        by_id[record_id] = dict(row)
    return [by_id[record_id] for record_id in order]


def campaign_identity(repo_root: Path, campaign_id: str) -> dict[str, Any]:
    manifest = load_yaml(repo_root / "lab" / "campaigns" / campaign_id / "campaign_manifest.yaml")
    design = manifest.get("experiment_design") or {}
    synthesis = manifest.get("bounded_synthesis") or {}
    is_synthesis = manifest.get("campaign_type") == "bounded_synthesis" or synthesis.get("enabled") is True
    return {
        "goal_id": manifest.get("active_goal_id", ""),
        "wave_id": (manifest.get("wave_ids") or [""])[0],
        "campaign_id": campaign_id,
        "campaign_type": manifest.get("campaign_type", ""),
        "stage_kind": "special_mixing" if is_synthesis else "campaign",
        "synthesis_stage_id": (synthesis.get("synthesis_stage_id") or campaign_id) if is_synthesis else "",
        "surface_id": design.get("surface_id", ""),
        "sweep_id": design.get("sweep_id", ""),
    }


def base_record(identity: dict[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    return {
        "schema_version": KPI_RECORD_SCHEMA_VERSION,
        "stage_kind": identity.get("stage_kind", "campaign"),
        "goal_id": identity.get("goal_id", ""),
        "wave_id": identity.get("wave_id", ""),
        "campaign_id": identity.get("campaign_id", ""),
        "synthesis_stage_id": identity.get("synthesis_stage_id", ""),
        "surface_id": identity.get("surface_id", ""),
        "sweep_id": identity.get("sweep_id", ""),
        "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
        "created_at_utc": created_at_utc,
    }


def build_proxy_record(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    run_id: str,
    l4_pair_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    metrics_path = repo_root / "lab" / "runs" / run_id / "metrics.json"
    metrics = load_json(metrics_path)
    validation_metrics = metrics.get("model_metrics", {}).get("validation", {})
    metric_specs = [
        ("roc_auc", "proxy.validation.roc_auc", "ratio"),
        ("spearman_corr", "proxy.validation.spearman_corr", "ratio"),
        ("pearson_corr", "proxy.validation.pearson_corr", "ratio"),
        ("rmse", "proxy.validation.rmse", "target_units"),
        ("mae", "proxy.validation.mae", "target_units"),
    ]
    metric_key = ""
    metric_id = ""
    unit = ""
    value = None
    for candidate_key, candidate_metric_id, candidate_unit in metric_specs:
        candidate_value = validation_metrics.get(candidate_key)
        if candidate_value is not None:
            metric_key = candidate_key
            metric_id = candidate_metric_id
            unit = candidate_unit
            value = candidate_value
            break
    if value is None:
        supported = ", ".join(key for key, _, _ in metric_specs)
        raise RuntimeError(
            f"{repo_rel(metrics_path, repo_root)} missing supported model_metrics.validation KPI: {supported}"
        )
    row = base_record(identity, created_at_utc=created_at_utc)
    row.update(
        {
            "record_id": f"proxy_{run_id}_{metric_record_suffix(metric_id)}_v1",
            "record_family": "proxy_experiment",
            "run_id": run_id,
            "l4_pair_id": l4_pair_id,
            "bundle_id": "",
            "attempt_id": "",
            "period_role": "validation",
            "proxy_record_id": "",
            "mt5_record_id": "",
            "metric_id": metric_id,
            "metric_namespace": "proxy",
            "metric_value": f"{float(value):.12g}",
            "value_type": "float",
            "unit": unit,
            "value_status": "observed",
            "n_a_reason": "",
            "authority": "proxy_metrics_json",
            "authority_path": repo_rel(metrics_path, repo_root),
            "authority_sha256": sha256(metrics_path),
            "source_artifact_refs_json": json.dumps([artifact_ref(metrics_path, repo_root)], sort_keys=True),
            "parser_diagnostic": f"proxy_metrics_json_key:model_metrics.validation.{metric_key}",
            "claim_effect": "proxy_observation_only_no_runtime_authority_no_economics_pass",
        }
    )
    return row


def metric_record_suffix(metric_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", metric_id).strip("_")


def nested_get(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def attempt_runtime_surface_kind(manifest: dict[str, Any], attempt_root: Path) -> str:
    contract = manifest.get("runtime_surface_contract") or {}
    surface_kind = str(contract.get("runtime_surface_kind") or "").strip()
    if surface_kind:
        return surface_kind
    if (attempt_root / "execution_telemetry_summary.yaml").exists():
        return "decision_replay"
    if (manifest.get("execution_identity") or {}).get("non_trading_probe") is True:
        return "score_probe"
    if (attempt_root / "score_telemetry_summary.yaml").exists():
        return "score_probe"
    return "unknown"


def build_mt5_runtime_surface_record(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    attempt_id: str,
    l4_pair_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = attempt_root / "attempt_manifest.yaml"
    manifest = load_yaml(manifest_path)
    surface_kind = attempt_runtime_surface_kind(manifest, attempt_root)
    row = base_record(identity, created_at_utc=created_at_utc)
    row.update(
        {
            "record_id": f"mt5_{attempt_id}_runtime_surface_kind_v1",
            "record_family": "mt5_runtime",
            "run_id": manifest.get("run_id", ""),
            "l4_pair_id": l4_pair_id,
            "bundle_id": manifest.get("bundle_id", ""),
            "attempt_id": attempt_id,
            "period_role": manifest.get("period_identity", {}).get("period_role", ""),
            "proxy_record_id": "",
            "mt5_record_id": "",
            "metric_id": "mt5.runtime.surface_kind",
            "metric_namespace": "mt5_runtime",
            "metric_value": surface_kind,
            "value_type": "string",
            "unit": "class",
            "value_status": "observed",
            "n_a_reason": "",
            "authority": "mt5_attempt_manifest",
            "authority_path": repo_rel(manifest_path, repo_root),
            "authority_sha256": sha256(manifest_path),
            "source_artifact_refs_json": json.dumps([artifact_ref(manifest_path, repo_root)], sort_keys=True),
            "parser_diagnostic": "attempt_manifest_runtime_surface_contract.runtime_surface_kind",
            "claim_effect": "mt5_runtime_surface_classification_only_no_runtime_authority_no_economics_pass",
        }
    )
    return row


EXECUTION_TELEMETRY_METRICS: tuple[dict[str, Any], ...] = (
    {"metric_id": "mt5.execution.row_count", "keys": ("stats", "row_count"), "value_type": "int", "unit": "rows"},
    {
        "metric_id": "mt5.execution.open_action_count",
        "keys": ("stats", "trade_action_counts", "open_action_count"),
        "value_type": "int",
        "unit": "actions",
    },
    {
        "metric_id": "mt5.execution.close_action_count",
        "keys": ("stats", "trade_action_counts", "close_action_count"),
        "value_type": "int",
        "unit": "actions",
    },
    {
        "metric_id": "mt5.execution.open_failed_count",
        "keys": ("stats", "trade_action_counts", "open_failed_count"),
        "value_type": "int",
        "unit": "actions",
    },
    {
        "metric_id": "mt5.execution.long_signal_count",
        "keys": ("stats", "execution_signal_counts", "long"),
        "value_type": "int",
        "unit": "signals",
    },
    {
        "metric_id": "mt5.execution.short_signal_count",
        "keys": ("stats", "execution_signal_counts", "short"),
        "value_type": "int",
        "unit": "signals",
    },
    {
        "metric_id": "mt5.execution.flat_signal_count",
        "keys": ("stats", "execution_signal_counts", "flat"),
        "value_type": "int",
        "unit": "signals",
    },
    {
        "metric_id": "mt5.execution.no_trade_flat_count",
        "keys": ("stats", "trade_action_counts", "no_trade_flat_count"),
        "value_type": "int",
        "unit": "actions",
    },
    {
        "metric_id": "mt5.execution.hold_same_direction_count",
        "keys": ("stats", "trade_action_counts", "hold_same_direction_count"),
        "value_type": "int",
        "unit": "actions",
    },
    {
        "metric_id": "mt5.execution.skip_spread_count",
        "keys": ("stats", "trade_action_counts", "skip_spread_count"),
        "value_type": "int",
        "unit": "actions",
    },
)


def build_mt5_execution_telemetry_records(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    attempt_id: str,
    l4_pair_id: str,
    created_at_utc: str,
) -> list[dict[str, Any]]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = attempt_root / "attempt_manifest.yaml"
    summary_path = attempt_root / "execution_telemetry_summary.yaml"
    manifest = load_yaml(manifest_path)
    base_payload = {
        "record_family": "mt5_runtime",
        "run_id": manifest.get("run_id", ""),
        "l4_pair_id": l4_pair_id,
        "bundle_id": manifest.get("bundle_id", ""),
        "attempt_id": attempt_id,
        "period_role": manifest.get("period_identity", {}).get("period_role", ""),
        "proxy_record_id": "",
        "mt5_record_id": "",
        "metric_namespace": "mt5_runtime",
        "claim_effect": "mt5_decision_execution_observation_only_no_runtime_authority_no_economics_pass",
    }
    if not summary_path.exists():
        return [
            mt5_execution_absence_record(
                repo_root,
                identity,
                manifest_path=manifest_path,
                metric=metric,
                base_payload=base_payload,
                created_at_utc=created_at_utc,
                value_status="missing_source",
                diagnostic=(
                    "execution_telemetry_summary_missing;"
                    "repair_required=inspect decision replay terminal output and execution telemetry materialization;"
                    "fallback_required=derive counts from repo telemetry CSV or rerun decision replay parser before accepted n/a"
                ),
            )
            for metric in EXECUTION_TELEMETRY_METRICS
        ]

    summary = load_yaml(summary_path)
    source_refs = [artifact_ref(manifest_path, repo_root), artifact_ref(summary_path, repo_root)]
    rows: list[dict[str, Any]] = []
    for metric in EXECUTION_TELEMETRY_METRICS:
        value = nested_get(summary, metric["keys"])
        if value is None:
            rows.append(
                mt5_execution_absence_record(
                    repo_root,
                    identity,
                    manifest_path=manifest_path,
                    metric=metric,
                    base_payload=base_payload,
                    created_at_utc=created_at_utc,
                    value_status="parser_failed",
                    authority_path=summary_path,
                    authority="mt5_execution_telemetry_summary",
                    source_refs=source_refs,
                    diagnostic=(
                        f"execution_telemetry_summary_key_missing:{'.'.join(metric['keys'])};"
                        "repair_required=inspect execution telemetry summary schema and parser compatibility;"
                        "fallback_required=derive count from execution_telemetry.csv before accepted n/a"
                    ),
                )
            )
            continue
        row = base_record(identity, created_at_utc=created_at_utc)
        row.update(
            {
                **base_payload,
                "record_id": f"mt5_{attempt_id}_{metric_record_suffix(metric['metric_id'])}_v1",
                "metric_id": metric["metric_id"],
                "metric_value": str(int(value)),
                "value_type": metric["value_type"],
                "unit": metric["unit"],
                "value_status": "observed",
                "n_a_reason": "",
                "authority": "mt5_execution_telemetry_summary",
                "authority_path": repo_rel(summary_path, repo_root),
                "authority_sha256": sha256(summary_path),
                "source_artifact_refs_json": json.dumps(source_refs, sort_keys=True),
                "parser_diagnostic": f"execution_telemetry_summary_key:{'.'.join(metric['keys'])}",
            }
        )
        rows.append(row)
    return rows


def mt5_execution_absence_record(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    manifest_path: Path,
    metric: dict[str, Any],
    base_payload: dict[str, Any],
    created_at_utc: str,
    value_status: str,
    diagnostic: str,
    authority: str = "absence_recorded_by_attempt_manifest",
    authority_path: Path | None = None,
    source_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    authority_path = authority_path or manifest_path
    refs = source_refs or [artifact_ref(manifest_path, repo_root)]
    row = base_record(identity, created_at_utc=created_at_utc)
    row.update(
        {
            **base_payload,
            "record_id": f"mt5_{base_payload['attempt_id']}_{metric_record_suffix(metric['metric_id'])}_v1",
            "metric_id": metric["metric_id"],
            "metric_value": "",
            "value_type": metric["value_type"],
            "unit": metric["unit"],
            "value_status": value_status,
            "n_a_reason": "runtime_probe_incomplete",
            "authority": authority,
            "authority_path": repo_rel(authority_path, repo_root),
            "authority_sha256": sha256(authority_path),
            "source_artifact_refs_json": json.dumps(refs, sort_keys=True),
            "parser_diagnostic": diagnostic,
        }
    )
    return row


def tester_report_path_from_receipt(repo_root: Path, receipt: dict[str, Any], manifest: dict[str, Any]) -> Path | None:
    for value in [
        receipt.get("source_report_path"),
        (manifest.get("tester_report") or {}).get("path") if isinstance(manifest.get("tester_report"), dict) else None,
    ]:
        if not value:
            continue
        path = Path(str(value))
        return path if path.is_absolute() else repo_root / path
    for item in (manifest.get("artifact_identity") or {}).get("tester_reports") or []:
        if isinstance(item, dict) and item.get("path"):
            path = Path(str(item["path"]))
            return path if path.is_absolute() else repo_root / path
    return None


def build_mt5_tester_report_records(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    attempt_id: str,
    l4_pair_id: str,
    created_at_utc: str,
) -> list[dict[str, Any]]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = attempt_root / "attempt_manifest.yaml"
    receipt_path = attempt_root / "tester_report_receipt.yaml"
    manifest = load_yaml(manifest_path)
    receipt = load_yaml(receipt_path) if receipt_path.exists() else {}
    report_path = tester_report_path_from_receipt(repo_root, receipt, manifest)
    run_id = str(receipt.get("run_id") or manifest.get("run_id", ""))
    bundle_id = str(receipt.get("bundle_id") or manifest.get("bundle_id", ""))
    period_role = str(manifest.get("period_identity", {}).get("period_role", ""))
    base_payload = {
        "record_family": "mt5_runtime",
        "run_id": run_id,
        "l4_pair_id": l4_pair_id,
        "bundle_id": bundle_id,
        "attempt_id": attempt_id,
        "period_role": period_role,
        "proxy_record_id": "",
        "mt5_record_id": "",
        "metric_namespace": "mt5_tester_report",
        "claim_effect": "mt5_tester_report_observation_only_no_runtime_authority_no_economics_pass",
    }
    if not receipt_path.exists():
        return [
            mt5_tester_report_absence_record(
                repo_root,
                identity,
                manifest_path=manifest_path,
                metric=metric,
                base_payload=base_payload,
                created_at_utc=created_at_utc,
                value_status="missing_source",
                n_a_reason="tester_report_receipt_missing",
                authority="absence_recorded_by_attempt_manifest",
                authority_path=manifest_path,
                diagnostic=(
                    "tester_report_receipt_missing;"
                    "repair_required=run or repair MT5 report receipt materialization;"
                    "fallback_required=locate attempt-specific tester_report.htm and rebuild receipt before accepted n/a"
                ),
            )
            for metric in TESTER_REPORT_METRICS
        ]
    source_refs = [artifact_ref(receipt_path, repo_root)]
    if report_path and report_path.exists():
        source_refs.append(artifact_ref(report_path, repo_root))
    if not receipt.get("tester_report_completed"):
        return [
            mt5_tester_report_absence_record(
                repo_root,
                identity,
                manifest_path=manifest_path,
                metric=metric,
                base_payload=base_payload,
                created_at_utc=created_at_utc,
                value_status="source_incomplete",
                n_a_reason="tester_report_not_completed",
                authority="mt5_tester_report_receipt",
                authority_path=receipt_path,
                source_refs=source_refs,
                diagnostic=(
                    "tester_report_receipt_not_completed;"
                    "repair_required=inspect receipt missing_requirements and MT5 report freshness/identity;"
                    "fallback_required=rebuild receipt from attempt-specific report or rerun MT5 before accepted n/a"
                ),
            )
            for metric in TESTER_REPORT_METRICS
        ]
    if not report_path or not report_path.exists():
        return [
            mt5_tester_report_absence_record(
                repo_root,
                identity,
                manifest_path=manifest_path,
                metric=metric,
                base_payload=base_payload,
                created_at_utc=created_at_utc,
                value_status="missing_source",
                n_a_reason="tester_report_missing",
                authority="mt5_tester_report_receipt",
                authority_path=receipt_path,
                source_refs=source_refs,
                diagnostic=(
                    "tester_report_path_missing_after_completed_receipt;"
                    "repair_required=inspect receipt source_report_path and archived report path;"
                    "fallback_required=restore attempt-specific tester_report.htm or rerun MT5 report export before accepted n/a"
                ),
            )
            for metric in TESTER_REPORT_METRICS
        ]
    parsed = parse_tester_report_kpis(report_path)
    parsed["source_report_path"] = repo_rel(report_path, repo_root)
    parse_summary_path = attempt_root / "tester_report_kpi_summary.yaml"
    write_yaml(parse_summary_path, parsed)
    source_refs.append(artifact_ref(parse_summary_path, repo_root))
    rows: list[dict[str, Any]] = []
    parsed_metrics = parsed.get("metrics") or {}
    for metric in TESTER_REPORT_METRICS:
        parsed_metric = parsed_metrics.get(metric.metric_id)
        if not parsed_metric:
            rows.append(
                mt5_tester_report_absence_record(
                    repo_root,
                    identity,
                    manifest_path=manifest_path,
                    metric=metric,
                    base_payload=base_payload,
                    created_at_utc=created_at_utc,
                    value_status="parser_failed",
                    n_a_reason="metric_not_present_in_report",
                    authority="mt5_tester_report_receipt",
                    authority_path=receipt_path,
                    source_refs=source_refs,
                    diagnostic=(
                        f"tester_report_metric_missing:{metric.metric_id};"
                        "repair_required=inspect report labels/localization and update parser aliases;"
                        "fallback_required=export alternate tester report format or confirm metric absent before accepted n/a"
                    ),
                )
            )
            continue
        row = base_record(identity, created_at_utc=created_at_utc)
        row.update(
            {
                **base_payload,
                "record_id": f"mt5_{attempt_id}_{metric_record_suffix(metric.metric_id)}_v1",
                "metric_id": metric.metric_id,
                "metric_value": str(parsed_metric["metric_value"]),
                "value_type": metric.value_type,
                "unit": metric.unit,
                "value_status": "observed",
                "n_a_reason": "",
                "authority": "mt5_tester_report_receipt",
                "authority_path": repo_rel(receipt_path, repo_root),
                "authority_sha256": sha256(receipt_path),
                "source_artifact_refs_json": json.dumps(source_refs, sort_keys=True),
                "parser_diagnostic": (
                    f"tester_report_kpi_parser_v1:matched_label={parsed_metric.get('matched_label')}:"
                    f"raw_value={parsed_metric.get('raw_value')}"
                ),
            }
        )
        rows.append(row)
    return rows


def mt5_tester_report_absence_record(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    manifest_path: Path,
    metric: Any,
    base_payload: dict[str, Any],
    created_at_utc: str,
    value_status: str,
    n_a_reason: str,
    authority: str,
    authority_path: Path,
    diagnostic: str,
    source_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    refs = source_refs or [artifact_ref(manifest_path, repo_root)]
    row = base_record(identity, created_at_utc=created_at_utc)
    row.update(
        {
            **base_payload,
            "record_id": f"mt5_{base_payload['attempt_id']}_{metric_record_suffix(metric.metric_id)}_v1",
            "metric_id": metric.metric_id,
            "metric_value": "",
            "value_type": metric.value_type,
            "unit": metric.unit,
            "value_status": value_status,
            "n_a_reason": n_a_reason,
            "authority": authority,
            "authority_path": repo_rel(authority_path, repo_root),
            "authority_sha256": sha256(authority_path),
            "source_artifact_refs_json": json.dumps(refs, sort_keys=True),
            "parser_diagnostic": diagnostic,
        }
    )
    return row


def trade_shape_source_refs(
    repo_root: Path,
    *,
    manifest_path: Path,
    summary_path: Path,
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    refs = [artifact_ref(manifest_path, repo_root), artifact_ref(summary_path, repo_root)]
    source_artifacts = summary.get("source_artifacts") or {}
    for item in source_artifacts.values():
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = repo_root / str(item["path"])
        if path.exists():
            ref = artifact_ref(path, repo_root)
            if ref["path"] not in {existing["path"] for existing in refs}:
                refs.append(ref)
    return refs


def trade_shape_metric_rows(summary: dict[str, Any]) -> list[tuple[str, Any, str, str]]:
    rows: list[tuple[str, Any, str, str]] = []
    overall = summary.get("overall") or {}
    overall_specs = [
        ("closed_trade_count", overall.get("trade_count"), "int", "trades"),
        ("gross_points_sum", overall.get("gross_points_sum"), "float", "points"),
        ("gross_points_avg", overall.get("gross_points_avg"), "float", "points"),
        ("win_rate", overall.get("win_rate"), "float", "ratio"),
        ("avg_mfe_points", overall.get("avg_mfe_points"), "float", "points"),
        ("avg_mae_points", overall.get("avg_mae_points"), "float", "points"),
        ("avg_hold_bars", overall.get("avg_hold_bars"), "float", "bars"),
        ("avg_exit_efficiency", overall.get("avg_exit_efficiency"), "float", "ratio"),
    ]
    rows.extend((f"mt5.trade_shape.{name}", value, value_type, unit) for name, value, value_type, unit in overall_specs)

    for direction, payload in sorted((summary.get("by_direction") or {}).items()):
        if not isinstance(payload, dict):
            continue
        for name, value, value_type, unit in [
            ("trade_count", payload.get("trade_count"), "int", "trades"),
            ("gross_points_sum", payload.get("gross_points_sum"), "float", "points"),
            ("avg_mfe_points", payload.get("avg_mfe_points"), "float", "points"),
            ("avg_mae_points", payload.get("avg_mae_points"), "float", "points"),
            ("win_rate", payload.get("win_rate"), "float", "ratio"),
        ]:
            rows.append((f"mt5.trade_shape.direction.{direction}.{name}", value, value_type, unit))

    for bucket, payload in sorted((summary.get("by_trade_shape_bucket") or {}).items()):
        if not isinstance(payload, dict):
            continue
        safe_bucket = metric_record_suffix(str(bucket))
        for name, value, value_type, unit in [
            ("trade_count", payload.get("trade_count"), "int", "trades"),
            ("gross_points_sum", payload.get("gross_points_sum"), "float", "points"),
            ("avg_mfe_points", payload.get("avg_mfe_points"), "float", "points"),
            ("avg_mae_points", payload.get("avg_mae_points"), "float", "points"),
            ("win_rate", payload.get("win_rate"), "float", "ratio"),
        ]:
            rows.append((f"mt5.trade_shape.bucket.{safe_bucket}.{name}", value, value_type, unit))
    return rows


def build_mt5_trade_shape_records(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    attempt_id: str,
    l4_pair_id: str,
    created_at_utc: str,
) -> list[dict[str, Any]]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = attempt_root / "attempt_manifest.yaml"
    summary_path = attempt_root / "trade_shape_summary.yaml"
    telemetry_path = attempt_root / "telemetry" / "execution_telemetry.csv"
    raw_bars_path = repo_root / DEFAULT_RAW_BARS
    manifest = load_yaml(manifest_path)
    base_payload = {
        "record_family": "mt5_runtime",
        "run_id": manifest.get("run_id", ""),
        "l4_pair_id": l4_pair_id,
        "bundle_id": manifest.get("bundle_id", ""),
        "attempt_id": attempt_id,
        "period_role": manifest.get("period_identity", {}).get("period_role", ""),
        "proxy_record_id": "",
        "mt5_record_id": "",
        "metric_namespace": "mt5_trade_shape",
        "claim_effect": "mt5_trade_shape_observation_only_no_runtime_authority_no_economics_pass",
    }
    if not summary_path.exists() and telemetry_path.exists() and raw_bars_path.exists():
        reconstruct_attempt(
            repo_root=repo_root,
            attempt_id=attempt_id,
            raw_bars_path=raw_bars_path,
            write=True,
        )
    if not summary_path.exists():
        return [
            mt5_tester_report_absence_record(
                repo_root,
                identity,
                manifest_path=manifest_path,
                metric=type(
                    "Metric",
                    (),
                    {
                        "metric_id": "mt5.trade_shape.closed_trade_count",
                        "value_type": "int",
                        "unit": "trades",
                    },
                )(),
                base_payload=base_payload,
                created_at_utc=created_at_utc,
                value_status="missing_source",
                n_a_reason="trade_shape_telemetry_not_instrumented",
                authority="absence_recorded_by_attempt_manifest",
                authority_path=manifest_path,
                diagnostic=(
                    "trade_shape_summary_missing;"
                    "repair_required=reconstruct from execution_telemetry.csv plus retained OHLC or rerun EA with trade-shape telemetry;"
                    "fallback_required=prove telemetry/raw bars unavailable before accepting n/a"
                ),
            )
        ]

    summary = load_yaml(summary_path)
    source_refs = trade_shape_source_refs(
        repo_root,
        manifest_path=manifest_path,
        summary_path=summary_path,
        summary=summary,
    )
    rows: list[dict[str, Any]] = []
    for metric_id, value, value_type, unit in trade_shape_metric_rows(summary):
        if value is None:
            continue
        row = base_record(identity, created_at_utc=created_at_utc)
        row.update(
            {
                **base_payload,
                "record_id": f"mt5_{attempt_id}_{metric_record_suffix(metric_id)}_v1",
                "metric_id": metric_id,
                "metric_value": str(value),
                "value_type": value_type,
                "unit": unit,
                "value_status": "observed",
                "n_a_reason": "",
                "authority": "mt5_trade_shape_summary",
                "authority_path": repo_rel(summary_path, repo_root),
                "authority_sha256": sha256(summary_path),
                "source_artifact_refs_json": json.dumps(source_refs, sort_keys=True),
                "parser_diagnostic": f"trade_shape_reconstruction_summary_key:{metric_id}",
            }
        )
        rows.append(row)
    return rows


def build_mt5_runtime_records(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    attempt_id: str,
    l4_pair_id: str,
    created_at_utc: str,
) -> list[dict[str, Any]]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest = load_yaml(attempt_root / "attempt_manifest.yaml")
    surface_kind = attempt_runtime_surface_kind(manifest, attempt_root)
    if surface_kind in NON_TRADING_RUNTIME_SURFACE_KINDS:
        return []
    if surface_kind not in TRADING_RUNTIME_SURFACE_KINDS:
        raise RuntimeError(
            f"{attempt_id} has runtime_surface_kind={surface_kind!r}; "
            "campaign KPI ledger only accepts explicit trading runtime execution surfaces"
        )
    rows = [
        build_mt5_runtime_surface_record(
            repo_root,
            identity,
            attempt_id=attempt_id,
            l4_pair_id=l4_pair_id,
            created_at_utc=created_at_utc,
        )
    ]
    rows.extend(
        build_mt5_execution_telemetry_records(
            repo_root,
            identity,
            attempt_id=attempt_id,
            l4_pair_id=l4_pair_id,
            created_at_utc=created_at_utc,
        )
    )
    rows.extend(
        build_mt5_tester_report_records(
            repo_root,
            identity,
            attempt_id=attempt_id,
            l4_pair_id=l4_pair_id,
            created_at_utc=created_at_utc,
        )
    )
    rows.extend(
        build_mt5_trade_shape_records(
            repo_root,
            identity,
            attempt_id=attempt_id,
            l4_pair_id=l4_pair_id,
            created_at_utc=created_at_utc,
        )
    )
    return rows


def count_distinct(rows: list[dict[str, Any]], field: str) -> int:
    return len({str(row.get(field, "")) for row in rows if row.get(field, "")})


def count_by_field(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(field, "")) for row in rows if row.get(field, "")).items()))


def parse_mt5_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def server_hour_session_bucket(timestamp: datetime) -> str:
    hour = timestamp.hour
    if 0 <= hour < 7:
        return "server_hour_00_06"
    if 7 <= hour < 13:
        return "server_hour_07_12"
    if 13 <= hour < 21:
        return "server_hour_13_20"
    return "server_hour_21_23"


def score_threshold_bucket(score: float, low: float | None, high: float | None) -> str:
    if low is not None and score <= low:
        return "score_le_low_short_band"
    if high is not None and score >= high:
        return "score_ge_high_long_band"
    if low is not None or high is not None:
        return "score_between_thresholds_flat_band"
    if score < 0.33:
        return "score_low_tercile"
    if score > 0.67:
        return "score_high_tercile"
    return "score_mid_tercile"


def safe_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def telemetry_segment_counts_for_attempt(repo_root: Path, attempt_id: str) -> dict[str, Any]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    telemetry_path = attempt_root / "telemetry" / "execution_telemetry.csv"
    if not telemetry_path.exists():
        return {"available": False, "attempt_id": attempt_id}
    manifest = load_yaml(attempt_root / "attempt_manifest.yaml")
    contract = manifest.get("runtime_surface_contract") or {}
    low = safe_float(contract.get("score_low_threshold"))
    high = safe_float(contract.get("score_high_threshold"))
    time_counts: Counter[str] = Counter()
    session_counts: Counter[str] = Counter()
    score_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    rows_observed = 0
    with telemetry_path.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows_observed += 1
            timestamp = parse_mt5_datetime(str(row.get("bar_close_time") or ""))
            if timestamp is not None:
                time_counts[timestamp.strftime("%Y-%m")] += 1
                session_counts[server_hour_session_bucket(timestamp)] += 1
            score = safe_float(row.get("score"))
            if score is not None:
                score_counts[score_threshold_bucket(score, low, high)] += 1
            if row.get("execution_signal"):
                direction_counts[str(row["execution_signal"])] += 1
            if row.get("action"):
                action_counts[str(row["action"])] += 1
    return {
        "available": True,
        "attempt_id": attempt_id,
        "path": repo_rel(telemetry_path, repo_root),
        "sha256": sha256(telemetry_path),
        "size_bytes": telemetry_path.stat().st_size,
        "rows_observed": rows_observed,
        "time_window_counts": dict(sorted(time_counts.items())),
        "session_counts": dict(sorted(session_counts.items())),
        "score_or_threshold_bucket_counts": dict(sorted(score_counts.items())),
        "direction_counts": dict(sorted(direction_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "score_bucket_policy": "attempt_thresholds_when_available_else_fixed_terciles",
        "session_bucket_policy": "mt5_server_hour_quadrants_not_exchange_session_claim",
    }


def build_raw_telemetry_segment_materialization(repo_root: Path, mt5_rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_ids = sorted({str(row.get("attempt_id") or "") for row in mt5_rows if row.get("attempt_id")})
    by_attempt = [
        telemetry_segment_counts_for_attempt(repo_root, attempt_id)
        for attempt_id in attempt_ids
    ]
    available = [item for item in by_attempt if item.get("available")]
    aggregate: dict[str, Counter[str]] = {
        "time_window_counts": Counter(),
        "session_counts": Counter(),
        "score_or_threshold_bucket_counts": Counter(),
        "direction_counts": Counter(),
        "action_counts": Counter(),
    }
    for item in available:
        for key, counter in aggregate.items():
            counter.update(item.get(key) or {})
    return {
        "attempt_count": len(attempt_ids),
        "raw_telemetry_available_attempt_count": len(available),
        "raw_telemetry_missing_attempt_ids": [
            str(item.get("attempt_id")) for item in by_attempt if not item.get("available")
        ],
        "attempt_sources": [
            {
                "attempt_id": item["attempt_id"],
                "path": item["path"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "rows_observed": item["rows_observed"],
            }
            for item in available
        ],
        **{key: dict(sorted(counter.items())) for key, counter in aggregate.items()},
        "session_bucket_policy": "mt5_server_hour_quadrants_not_exchange_session_claim",
        "score_bucket_policy": "attempt_thresholds_when_available_else_fixed_terciles",
        "claim_boundary": "segment_materialization_counts_only_no_runtime_authority_no_economics_pass",
    }


def sample_ids(rows: list[dict[str, Any]], *, limit: int = 40) -> list[str]:
    return [str(row["record_id"]) for row in rows if row.get("record_id")][:limit]


def surface_kind_by_attempt(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(row.get("attempt_id", "")): str(row.get("metric_value", ""))
        for row in rows
        if row.get("metric_id") == "mt5.runtime.surface_kind" and row.get("attempt_id")
    }


def trade_execution_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surface_by_attempt = surface_kind_by_attempt(rows)
    return [
        row
        for row in rows
        if surface_by_attempt.get(str(row.get("attempt_id", "")), "unknown") in TRADING_RUNTIME_SURFACE_KINDS
    ]


def is_allowed_mt5_kpi_row(repo_root: Path, row: dict[str, Any]) -> bool:
    metric_id = str(row.get("metric_id", ""))
    if metric_id.startswith("mt5.score."):
        return False
    if str(row.get("metric_value", "")) == "score_probe" and metric_id == "mt5.runtime.surface_kind":
        return False
    attempt_id = str(row.get("attempt_id", ""))
    if not attempt_id:
        return True
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = attempt_root / "attempt_manifest.yaml"
    if not manifest_path.exists():
        return True
    surface_kind = attempt_runtime_surface_kind(load_yaml(manifest_path), attempt_root)
    return surface_kind not in NON_TRADING_RUNTIME_SURFACE_KINDS


def sum_observed_metric(rows: list[dict[str, Any]], metric_id: str) -> int:
    total = 0
    for row in rows:
        if row.get("metric_id") != metric_id or row.get("value_status") != "observed":
            continue
        try:
            total += int(float(str(row.get("metric_value", "0"))))
        except ValueError:
            continue
    return total


SEGMENT_CLAIM_EFFECT = "segment_breakdown_learning_only_no_selection_or_pass_claim"


def segment_metric_basis(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row.get("metric_id") or "") for row in rows if row.get("metric_id")})


def segment_status(
    *,
    observed: bool,
    not_collected_reason: str = "",
    next_materialization_step: str = "",
) -> dict[str, Any]:
    if observed:
        return {
            "status": "observed",
            "analysis_status": "materialized",
            "claim_effect": SEGMENT_CLAIM_EFFECT,
        }
    return {
        "status": "not_collected",
        "analysis_status": "not_materialized",
        "missing_reason": not_collected_reason,
        "next_materialization_step": next_materialization_step,
        "claim_effect": "segment_missing_lowers_attribution_confidence_no_selection_or_pass_claim",
    }


def observed_metric_value(rows: list[dict[str, Any]], metric_id: str) -> str:
    for row in rows:
        if row.get("metric_id") == metric_id and row.get("value_status") == "observed":
            return str(row.get("metric_value", ""))
    return ""


def trade_shape_direction_breakdown(mt5_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for direction in ["long", "short"]:
        payload = {
            "trade_count": observed_metric_value(mt5_rows, f"mt5.trade_shape.direction.{direction}.trade_count"),
            "gross_points_sum": observed_metric_value(mt5_rows, f"mt5.trade_shape.direction.{direction}.gross_points_sum"),
            "avg_mfe_points": observed_metric_value(mt5_rows, f"mt5.trade_shape.direction.{direction}.avg_mfe_points"),
            "avg_mae_points": observed_metric_value(mt5_rows, f"mt5.trade_shape.direction.{direction}.avg_mae_points"),
            "win_rate": observed_metric_value(mt5_rows, f"mt5.trade_shape.direction.{direction}.win_rate"),
        }
        if any(value != "" for value in payload.values()):
            result[direction] = payload
    return result


def trade_shape_bucket_breakdown(mt5_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    prefix = "mt5.trade_shape.bucket."
    suffixes = {
        ".trade_count": "trade_count",
        ".gross_points_sum": "gross_points_sum",
        ".avg_mfe_points": "avg_mfe_points",
        ".avg_mae_points": "avg_mae_points",
        ".win_rate": "win_rate",
    }
    buckets: dict[str, dict[str, str]] = {}
    for row in mt5_rows:
        metric_id = str(row.get("metric_id") or "")
        if row.get("value_status") != "observed" or not metric_id.startswith(prefix):
            continue
        rest = metric_id[len(prefix) :]
        for suffix, key in suffixes.items():
            if rest.endswith(suffix):
                bucket = rest[: -len(suffix)]
                buckets.setdefault(bucket, {})[key] = str(row.get("metric_value", ""))
                break
    return dict(sorted(buckets.items()))


def build_segment_breakdowns(
    *,
    raw_segments: dict[str, Any],
    proxy_rows: list[dict[str, Any]],
    mt5_rows: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
    surface_counts: dict[str, int],
) -> dict[str, dict[str, Any]]:
    all_rows = [*proxy_rows, *mt5_rows, *comparison_rows]
    period_counts = count_by_field(all_rows, "period_role")
    rows_by_period = {
        period_role: [row for row in all_rows if str(row.get("period_role") or "") == period_role]
        for period_role in period_counts
    }
    direction_counts = {
        "long": sum_observed_metric(mt5_rows, "mt5.execution.long_signal_count"),
        "short": sum_observed_metric(mt5_rows, "mt5.execution.short_signal_count"),
        "flat": sum_observed_metric(mt5_rows, "mt5.execution.flat_signal_count"),
    }
    direction_observed = any(direction_counts.values())
    direction_trade_shape = trade_shape_direction_breakdown(mt5_rows)
    direction_pnl_observed = any(
        payload.get("gross_points_sum") != ""
        for payload in direction_trade_shape.values()
    )
    trade_shape_count = sum(
        1
        for row in mt5_rows
        if str(row.get("metric_namespace", "")) in {"mt5_tester_report", "mt5_trade_shape"}
    )
    bucket_breakdown = trade_shape_bucket_breakdown(mt5_rows)
    execution_rows = [
        row
        for row in mt5_rows
        if str(row.get("metric_id") or "").startswith("mt5.execution.")
    ]
    trade_shape_rows = [
        row
        for row in mt5_rows
        if str(row.get("metric_namespace", "")) in {"mt5_tester_report", "mt5_trade_shape"}
    ]
    surface_rows = [
        row
        for row in mt5_rows
        if str(row.get("metric_id") or "") == "mt5.runtime.surface_kind"
    ]
    time_window_counts = raw_segments.get("time_window_counts") or {}
    session_counts = raw_segments.get("session_counts") or {}
    score_bucket_counts = raw_segments.get("score_or_threshold_bucket_counts") or {}
    raw_available = int(raw_segments.get("raw_telemetry_available_attempt_count") or 0)
    return {
        "overall": {
            "status": "observed",
            "analysis_status": "materialized",
            "record_count": len(all_rows),
            "proxy_record_count": len(proxy_rows),
            "mt5_runtime_record_count": len(mt5_rows),
            "comparison_record_count": len(comparison_rows),
            "metric_basis": segment_metric_basis(all_rows),
            "claim_effect": SEGMENT_CLAIM_EFFECT,
        },
        "period_role": {
            **segment_status(
                observed=bool(period_counts),
                not_collected_reason="period_role_missing_from_kpi_records",
                next_materialization_step="write period_role on every KPI record before campaign closeout",
            ),
            "counts": period_counts,
            "metric_basis_by_period_role": {
                period_role: segment_metric_basis(rows)
                for period_role, rows in rows_by_period.items()
            },
        },
        "time_window": {
            **(
                {
                    "status": "observed",
                    "analysis_status": "materialized",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if time_window_counts
                else segment_status(
                    observed=False,
                    not_collected_reason="time_window_bucket_not_materialized_in_kpi_records_yet",
                    next_materialization_step=(
                        "project attempt period identity and telemetry timestamps into stable time_window buckets"
                    ),
                )
            ),
            "counts": time_window_counts,
            "raw_telemetry_available_attempt_count": raw_available,
            "expected_sources": ["period_profile", "attempt_period_identity", "runtime_telemetry_time_bucket"],
        },
        "session": {
            **(
                {
                    "status": "observed",
                    "analysis_status": "materialized",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if session_counts
                else segment_status(
                    observed=False,
                    not_collected_reason="session_bucket_not_materialized_in_kpi_records_yet",
                    next_materialization_step="map US100 bar close timestamps to declared session buckets",
                )
            ),
            "counts": session_counts,
            "session_bucket_policy": raw_segments.get("session_bucket_policy", ""),
            "expected_sources": ["MT5 server bar close time"],
        },
        "direction": {
            **(
                {
                    "status": "observed",
                    "analysis_status": "materialized",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if direction_pnl_observed
                else {
                    "status": "partial",
                    "analysis_status": "partial_materialized",
                    "missing_reason": "direction_signal_counts_observed_without_full_direction_pnl_breakdown",
                    "next_materialization_step": "materialize mt5.trade_shape.direction.* PnL/MFE/MAE records before closeout",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if direction_observed
                else segment_status(
                    observed=False,
                    not_collected_reason="direction_signal_counts_not_available",
                    next_materialization_step="emit long/short/flat signal counts in execution telemetry summary",
                )
            ),
            "signal_counts": direction_counts,
            "trade_shape_pnl_by_direction": direction_trade_shape,
            "metric_basis": segment_metric_basis(execution_rows),
        },
        "score_or_threshold_bucket": {
            **(
                {
                    "status": "observed",
                    "analysis_status": "materialized",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if score_bucket_counts
                else segment_status(
                    observed=False,
                    not_collected_reason="score_threshold_bucket_not_materialized_in_kpi_records_yet",
                    next_materialization_step="write score band or threshold bucket per decision replay attempt",
                )
            ),
            "counts": score_bucket_counts,
            "score_bucket_policy": raw_segments.get("score_bucket_policy", ""),
            "expected_sources": ["score telemetry", "threshold policy", "decision band"],
        },
        "trade_shape_bucket": {
            **(
                {
                    "status": "observed",
                    "analysis_status": "materialized",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if bucket_breakdown
                else {
                    "status": "partial",
                    "analysis_status": "partial_materialized",
                    "missing_reason": "trade_shape_metrics_observed_without_full_bucketed_trade_shape_breakdown",
                    "next_materialization_step": "materialize mt5.trade_shape.bucket.* count/PnL/MFE/MAE records before closeout",
                    "claim_effect": SEGMENT_CLAIM_EFFECT,
                }
                if trade_shape_count > 0
                else segment_status(
                    observed=False,
                    not_collected_reason="trade_shape_kpi_not_materialized",
                    next_materialization_step="parse tester report and trade-shape summary before closeout interpretation",
                )
            ),
            "record_count": trade_shape_count,
            "bucket_breakdown": bucket_breakdown,
            "metric_basis": segment_metric_basis(trade_shape_rows),
        },
        "runtime_surface": {
            **segment_status(
                observed=bool(surface_counts),
                not_collected_reason="runtime_surface_kind_missing",
                next_materialization_step="record runtime_surface_contract.runtime_surface_kind for every MT5 attempt",
            ),
            "counts": surface_counts,
            "metric_basis": segment_metric_basis(surface_rows),
        },
    }


def build_segment_coverage(segment_breakdowns: dict[str, dict[str, Any]]) -> dict[str, Any]:
    covered = sorted(axis for axis in REQUIRED_KPI_SEGMENT_AXES if axis in segment_breakdowns)
    missing = sorted(set(REQUIRED_KPI_SEGMENT_AXES) - set(covered))
    materialized = sorted(
        axis
        for axis in covered
        if segment_breakdowns.get(axis, {}).get("analysis_status") == "materialized"
    )
    partial = sorted(
        axis
        for axis in covered
        if segment_breakdowns.get(axis, {}).get("analysis_status") == "partial_materialized"
    )
    not_collected = sorted(
        axis
        for axis in covered
        if segment_breakdowns.get(axis, {}).get("status") in {"not_collected", "missing_source"}
    )
    return {
        "required_axes": REQUIRED_KPI_SEGMENT_AXES,
        "optional_axes": OPTIONAL_KPI_SEGMENT_AXES,
        "covered_axes": covered,
        "missing_axes": missing,
        "materialized_axes": materialized,
        "partial_materialized_axes": partial,
        "not_collected_axes": not_collected,
        "pending_materialization_axes": not_collected,
        "claim_policy": KPI_SEGMENT_CLAIM_POLICY,
    }


def row_metric_float(rows: list[dict[str, Any]], metric_id: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        if row.get("metric_id") != metric_id or row.get("value_status") != "observed":
            continue
        value = safe_float(row.get("metric_value"))
        if value is not None:
            values.append(value)
    return values


def classify_proxy_mt5_gap(proxy_auc: float | None, total_trades: int, profit_factors: list[float]) -> str:
    if total_trades <= 0:
        return "proxy_observed_mt5_no_closed_trades"
    if not profit_factors:
        return "proxy_observed_mt5_trades_pf_unavailable"
    min_pf = min(profit_factors)
    max_pf = max(profit_factors)
    if max_pf < 1.0:
        return "proxy_observed_mt5_trades_pf_below_1"
    if min_pf <= 1.0 <= max_pf:
        return "proxy_observed_mt5_trades_pf_mixed_around_1"
    if proxy_auc is not None and proxy_auc < 0.55 and min_pf > 1.0:
        return "weak_proxy_but_mt5_pf_above_1"
    return "proxy_observed_mt5_trades_pf_above_1"


def comparison_source_refs(repo_root: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for row in rows:
        path_value = str(row.get("authority_path") or "")
        if not path_value:
            continue
        path = repo_root / path_value
        if path.exists():
            refs[path_value] = artifact_ref(path, repo_root)
    return [refs[key] for key in sorted(refs)]


def build_comparison_record(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    run_id: str,
    l4_pair_id: str,
    proxy_row: dict[str, Any],
    mt5_rows_for_pair: list[dict[str, Any]],
    metric_id: str,
    metric_value: str,
    value_type: str,
    unit: str,
    created_at_utc: str,
) -> dict[str, Any]:
    campaign_manifest_path = repo_root / "lab" / "campaigns" / identity["campaign_id"] / "campaign_manifest.yaml"
    first_mt5 = mt5_rows_for_pair[0]
    row = base_record(identity, created_at_utc=created_at_utc)
    row.update(
        {
            "record_id": f"comparison_{run_id}_{metric_record_suffix(metric_id)}_v1",
            "record_family": "proxy_mt5_comparison",
            "run_id": run_id,
            "l4_pair_id": l4_pair_id,
            "bundle_id": first_mt5.get("bundle_id", ""),
            "attempt_id": first_mt5.get("attempt_id", ""),
            "period_role": "validation_research_oos_pair",
            "proxy_record_id": proxy_row.get("record_id", ""),
            "mt5_record_id": first_mt5.get("record_id", ""),
            "metric_id": metric_id,
            "metric_namespace": "comparison",
            "metric_value": metric_value,
            "value_type": value_type,
            "unit": unit,
            "value_status": "observed",
            "n_a_reason": "",
            "authority": "campaign_kpi_projection",
            "authority_path": repo_rel(campaign_manifest_path, repo_root),
            "authority_sha256": sha256(campaign_manifest_path),
            "source_artifact_refs_json": json.dumps(
                comparison_source_refs(repo_root, [proxy_row, *mt5_rows_for_pair]),
                sort_keys=True,
            ),
            "parser_diagnostic": "comparison_projection_from_proxy_and_mt5_kpi_records",
            "claim_effect": "proxy_mt5_comparison_observation_only_no_runtime_authority_no_economics_pass",
        }
    )
    return row


def build_proxy_mt5_comparison_records(
    repo_root: Path,
    identity: dict[str, Any],
    *,
    proxy_rows: list[dict[str, Any]],
    mt5_rows: list[dict[str, Any]],
    created_at_utc: str,
) -> list[dict[str, Any]]:
    proxy_by_run = {str(row.get("run_id")): row for row in proxy_rows if row.get("run_id")}
    mt5_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in mt5_rows:
        run_id = str(row.get("run_id") or "")
        l4_pair_id = str(row.get("l4_pair_id") or "")
        if run_id and l4_pair_id:
            mt5_by_pair.setdefault((run_id, l4_pair_id), []).append(row)

    comparison_rows: list[dict[str, Any]] = []
    for (run_id, l4_pair_id), rows_for_pair in sorted(mt5_by_pair.items()):
        proxy_row = proxy_by_run.get(run_id)
        if not proxy_row:
            continue
        proxy_auc = safe_float(proxy_row.get("metric_value"))
        total_trades = int(sum(row_metric_float(rows_for_pair, "mt5.tester_report.total_trades")))
        profit_factors = row_metric_float(rows_for_pair, "mt5.tester_report.profit_factor")
        open_actions = int(sum(row_metric_float(rows_for_pair, "mt5.execution.open_action_count")))
        gap_class = classify_proxy_mt5_gap(proxy_auc, total_trades, profit_factors)
        specs = [
            (
                "comparison.proxy_mt5.gap_class",
                gap_class,
                "string",
                "class",
            ),
            (
                "comparison.proxy_mt5.total_trades_sum",
                str(total_trades),
                "int",
                "trades",
            ),
            (
                "comparison.proxy_mt5.open_action_count_sum",
                str(open_actions),
                "int",
                "actions",
            ),
        ]
        if profit_factors:
            specs.append(
                (
                    "comparison.proxy_mt5.profit_factor_min",
                    f"{min(profit_factors):.12g}",
                    "float",
                    "ratio",
                )
            )
            specs.append(
                (
                    "comparison.proxy_mt5.profit_factor_max",
                    f"{max(profit_factors):.12g}",
                    "float",
                    "ratio",
                )
            )
        for metric_id, metric_value, value_type, unit in specs:
            comparison_rows.append(
                build_comparison_record(
                    repo_root,
                    identity,
                    run_id=run_id,
                    l4_pair_id=l4_pair_id,
                    proxy_row=proxy_row,
                    mt5_rows_for_pair=rows_for_pair,
                    metric_id=metric_id,
                    metric_value=metric_value,
                    value_type=value_type,
                    unit=unit,
                    created_at_utc=created_at_utc,
                )
            )
    return comparison_rows


def build_summary(
    *,
    repo_root: Path,
    identity: dict[str, Any],
    proxy_rows: list[dict[str, Any]],
    mt5_rows: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
    created_at_utc: str,
) -> dict[str, Any]:
    all_rows = [*proxy_rows, *mt5_rows, *comparison_rows]
    surface_by_attempt = surface_kind_by_attempt(mt5_rows)
    surface_counts = dict(sorted(Counter(surface_by_attempt.values()).items()))
    default_mt5_rows = trade_execution_rows(mt5_rows)
    raw_segments = build_raw_telemetry_segment_materialization(repo_root, mt5_rows)
    segment_breakdowns = build_segment_breakdowns(
        raw_segments=raw_segments,
        proxy_rows=proxy_rows,
        mt5_rows=mt5_rows,
        comparison_rows=comparison_rows,
        surface_counts=surface_counts,
    )
    segment_coverage = build_segment_coverage(segment_breakdowns)
    return {
        "version": KPI_SUMMARY_VERSION,
        "campaign_id": identity["campaign_id"],
        "wave_id": identity.get("wave_id", ""),
        "stage_kind": identity.get("stage_kind", "campaign"),
        "synthesis_stage_id": identity.get("synthesis_stage_id", ""),
        "created_at_utc": created_at_utc,
        "record_counts": {
            "proxy_kpi_records": len(proxy_rows),
            "mt5_runtime_kpi_records": len(mt5_rows),
            "proxy_mt5_comparison_records": len(comparison_rows),
        },
        "proxy_run_count": count_distinct(proxy_rows, "run_id"),
        "mt5_attempt_count": count_distinct(mt5_rows, "attempt_id"),
        "mt5_surface_kind_counts": surface_counts,
        "trade_execution_attempt_count": len(
            {attempt_id for attempt_id, surface_kind in surface_by_attempt.items() if surface_kind in TRADING_RUNTIME_SURFACE_KINDS}
        ),
        "comparison_pair_count": count_distinct(comparison_rows, "l4_pair_id"),
        "sample_record_ids": {
            "proxy": sample_ids(proxy_rows),
            "mt5_runtime_trade_execution": sample_ids(default_mt5_rows),
            "proxy_mt5_comparison": sample_ids(comparison_rows),
        },
        "authority_counts": dict(sorted(Counter(row.get("authority", "") for row in all_rows).items())),
        "missing_value_reason_counts": dict(sorted(Counter(row.get("n_a_reason", "") for row in all_rows if row.get("n_a_reason")).items())),
        "segment_materialization_sources": raw_segments,
        "segment_coverage": segment_coverage,
        "segment_breakdowns": segment_breakdowns,
        "kpi_policy": {
            "fixed_schema": True,
            "mt5_missing_is_repair_trigger_before_na": True,
            "proxy_only_runs_excluded_from_comparison_ledger": True,
            "non_trading_score_probe_excluded_from_kpi_ledger": True,
            "score_probe_retained_only_in_runtime_evidence_not_kpi": True,
            "overall_and_segment_breakdowns_required": True,
            "fake_segment_placeholder_forbidden": True,
            "observed_segment_requires_metric_or_count_basis": True,
            "missing_segment_requires_next_materialization_step": True,
            "required_segment_axes": REQUIRED_KPI_SEGMENT_AXES,
            "optional_segment_axes": OPTIONAL_KPI_SEGMENT_AXES,
            "segment_claim_policy": KPI_SEGMENT_CLAIM_POLICY,
        },
        "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def build_manifest(
    repo_root: Path,
    *,
    identity: dict[str, Any],
    output_dir: Path,
    proxy_rows: list[dict[str, Any]],
    mt5_rows: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
    summary_path: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    record_paths = {
        "proxy_kpi_records": output_dir / "proxy_kpi_records.csv",
        "mt5_runtime_kpi_records": output_dir / "mt5_runtime_kpi_records.csv",
        "proxy_mt5_comparison_records": output_dir / "proxy_mt5_comparison_records.csv",
    }
    return {
        "version": KPI_LEDGER_MANIFEST_VERSION,
        "ledger_id": f"kpi_ledger_{identity['campaign_id']}_v0",
        "ledger_scope": "campaign",
        "schema_ref": {
            "path": "docs/contracts/kpi_ledger_contract.yaml",
            "version": KPI_LEDGER_CONTRACT_VERSION,
        },
        "scope_identity": {
            "active_goal_id": identity.get("goal_id", ""),
            "wave_id": identity.get("wave_id", ""),
            "campaign_id": identity["campaign_id"],
            "stage_kind": identity.get("stage_kind", "campaign"),
            "synthesis_stage_id": identity.get("synthesis_stage_id", ""),
        },
        "source_artifacts": {
            "proxy_authorities": sorted({row["authority_path"] for row in proxy_rows}),
            "mt5_authorities": sorted({row["authority_path"] for row in mt5_rows}),
        },
        "record_files": {
            name: {
                "path": repo_rel(path, repo_root),
                "sha256": sha256(path),
                "row_count": len(rows),
            }
            for name, path, rows in [
                ("proxy_kpi_records", record_paths["proxy_kpi_records"], proxy_rows),
                ("mt5_runtime_kpi_records", record_paths["mt5_runtime_kpi_records"], mt5_rows),
                ("proxy_mt5_comparison_records", record_paths["proxy_mt5_comparison_records"], comparison_rows),
            ]
        },
        "summary": {
            "path": repo_rel(summary_path, repo_root),
            "sha256": sha256(summary_path),
            "proxy_run_count": count_distinct(proxy_rows, "run_id"),
            "mt5_attempt_count": count_distinct(mt5_rows, "attempt_id"),
            "trade_execution_attempt_count": count_distinct(mt5_rows, "attempt_id"),
            "comparison_pair_count": count_distinct(comparison_rows, "l4_pair_id"),
            "proxy_only_excluded_from_comparison_count": 0,
            "segment_breakdown_required": True,
            "required_segment_axes": REQUIRED_KPI_SEGMENT_AXES,
            "segment_materialization": {
                "materialized_axes": (summary.get("segment_coverage") or {}).get("materialized_axes", []),
                "partial_materialized_axes": (summary.get("segment_coverage") or {}).get(
                    "partial_materialized_axes",
                    [],
                ),
                "pending_materialization_axes": (summary.get("segment_coverage") or {}).get(
                    "pending_materialization_axes",
                    [],
                ),
            },
        },
        "kpi_policy": {
            "fixed_schema": True,
            "mt5_missing_is_repair_trigger_before_na": True,
            "proxy_only_runs_excluded_from_comparison_ledger": True,
            "non_trading_score_probe_excluded_from_kpi_ledger": True,
            "score_probe_retained_only_in_runtime_evidence_not_kpi": True,
            "overall_and_segment_breakdowns_required": True,
            "fake_segment_placeholder_forbidden": True,
            "observed_segment_requires_metric_or_count_basis": True,
            "missing_segment_requires_next_materialization_step": True,
            "required_segment_axes": REQUIRED_KPI_SEGMENT_AXES,
            "optional_segment_axes": OPTIONAL_KPI_SEGMENT_AXES,
            "segment_claim_policy": KPI_SEGMENT_CLAIM_POLICY,
        },
        "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def build_campaign_kpi_ledger(
    repo_root: Path,
    *,
    campaign_id: str,
    run_id: str,
    attempt_id: str,
    l4_pair_id: str,
    write: bool,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created_at = created_at_utc or utc_now()
    identity = campaign_identity(repo_root, campaign_id)
    proxy_rows = [build_proxy_record(repo_root, identity, run_id=run_id, l4_pair_id=l4_pair_id, created_at_utc=created_at)]
    mt5_rows = build_mt5_runtime_records(
        repo_root,
        identity,
        attempt_id=attempt_id,
        l4_pair_id=l4_pair_id,
        created_at_utc=created_at,
    )
    return write_campaign_kpi_files(
        repo_root,
        campaign_id=campaign_id,
        proxy_rows=proxy_rows,
        mt5_rows=mt5_rows,
        comparison_rows=[],
        write=write,
        created_at_utc=created_at,
        include_existing=write,
    )


def write_campaign_kpi_files(
    repo_root: Path,
    *,
    campaign_id: str,
    proxy_rows: list[dict[str, Any]] | None = None,
    mt5_rows: list[dict[str, Any]] | None = None,
    comparison_rows: list[dict[str, Any]] | None = None,
    write: bool,
    created_at_utc: str | None = None,
    include_existing: bool = True,
) -> dict[str, Any]:
    created_at = created_at_utc or utc_now()
    identity = campaign_identity(repo_root, campaign_id)
    output_dir = repo_root / "lab" / "campaigns" / campaign_id / "kpi"
    proxy_path = output_dir / "proxy_kpi_records.csv"
    mt5_path = output_dir / "mt5_runtime_kpi_records.csv"
    comparison_path = output_dir / "proxy_mt5_comparison_records.csv"
    existing_proxy = read_existing_csv(proxy_path) if include_existing else []
    existing_mt5 = read_existing_csv(mt5_path) if include_existing else []
    existing_mt5 = [row for row in existing_mt5 if is_allowed_mt5_kpi_row(repo_root, row)]
    existing_comparison = read_existing_csv(comparison_path) if include_existing else []
    proxy_all = upsert_records(existing_proxy, proxy_rows or [])
    mt5_all = upsert_records(existing_mt5, mt5_rows or [])
    comparison_all = upsert_records(existing_comparison, comparison_rows or [])
    summary = build_summary(
        repo_root=repo_root,
        identity=identity,
        proxy_rows=proxy_all,
        mt5_rows=mt5_all,
        comparison_rows=comparison_all,
        created_at_utc=created_at,
    )

    if write:
        write_csv(proxy_path, proxy_all)
        write_csv(mt5_path, mt5_all)
        write_csv(comparison_path, comparison_all)
        summary_path = output_dir / "kpi_summary.yaml"
        write_yaml(summary_path, summary)
        manifest = build_manifest(
            repo_root,
            identity=identity,
            output_dir=output_dir,
            proxy_rows=proxy_all,
            mt5_rows=mt5_all,
            comparison_rows=comparison_all,
            summary_path=summary_path,
            summary=summary,
        )
        write_yaml(output_dir / "kpi_ledger_manifest.yaml", manifest)
        summary["manifest_path"] = repo_rel(output_dir / "kpi_ledger_manifest.yaml", repo_root)
    return summary


def upsert_proxy_kpi_for_run(
    repo_root: Path,
    *,
    campaign_id: str,
    run_id: str,
    l4_pair_id: str,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created_at = created_at_utc or utc_now()
    identity = campaign_identity(repo_root, campaign_id)
    row = build_proxy_record(repo_root, identity, run_id=run_id, l4_pair_id=l4_pair_id, created_at_utc=created_at)
    return write_campaign_kpi_files(
        repo_root,
        campaign_id=campaign_id,
        proxy_rows=[row],
        write=True,
        created_at_utc=created_at,
    )


def upsert_mt5_kpi_for_attempt(
    repo_root: Path,
    *,
    campaign_id: str,
    attempt_id: str,
    l4_pair_id: str,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created_at = created_at_utc or utc_now()
    identity = campaign_identity(repo_root, campaign_id)
    rows = build_mt5_runtime_records(
        repo_root,
        identity,
        attempt_id=attempt_id,
        l4_pair_id=l4_pair_id,
        created_at_utc=created_at,
    )
    return write_campaign_kpi_files(
        repo_root,
        campaign_id=campaign_id,
        mt5_rows=rows,
        write=True,
        created_at_utc=created_at,
    )


def derive_l4_pair_id(value: str) -> str:
    patterns = [
        r"(wave\d+_[a-z]+_cell_\d+)",
        r"(wave\d+_cell_\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return value


def campaign_run_registry_rows(repo_root: Path, campaign_id: str) -> list[dict[str, str]]:
    registry_path = repo_root / "docs" / "registers" / "run_registry.csv"
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    if not registry_path.exists():
        registry_rows: list[dict[str, str]] = []
    else:
        registry_rows = [
            row
            for row in read_csv(registry_path)
            if row.get("campaign_id") == campaign_id
        ]
    for row in registry_rows:
        run_id = str(row.get("run_id") or "")
        if run_id and run_id not in seen:
            rows.append(row)
            seen.add(run_id)

    proxy_summary_path = repo_root / "lab" / "campaigns" / campaign_id / "proxy_execution_summary.yaml"
    if proxy_summary_path.exists():
        summary = load_yaml(proxy_summary_path)
        for item in summary.get("result_rows") or []:
            run_id = str(item.get("run_id") or "")
            if run_id and run_id not in seen:
                rows.append({"run_id": run_id, "campaign_id": campaign_id})
                seen.add(run_id)
    return rows


def campaign_attempt_manifests(repo_root: Path, campaign_id: str, run_ids: set[str]) -> list[Path]:
    paths: list[Path] = []
    for manifest_path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
        manifest = load_yaml(manifest_path)
        if manifest.get("campaign_id") == campaign_id or manifest.get("run_id") in run_ids:
            paths.append(manifest_path)
    return paths


def build_campaign_kpi_ledger_from_existing_evidence(
    repo_root: Path,
    *,
    campaign_id: str,
    write: bool,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created_at = created_at_utc or utc_now()
    identity = campaign_identity(repo_root, campaign_id)
    run_rows = campaign_run_registry_rows(repo_root, campaign_id)
    proxy_rows: list[dict[str, Any]] = []
    for run_row in run_rows:
        run_id = str(run_row.get("run_id") or "")
        if not run_id:
            continue
        proxy_rows.append(
            build_proxy_record(
                repo_root,
                identity,
                run_id=run_id,
                l4_pair_id=derive_l4_pair_id(run_id),
                created_at_utc=created_at,
            )
        )

    run_ids = {str(row.get("run_id") or "") for row in run_rows if row.get("run_id")}
    mt5_rows: list[dict[str, Any]] = []
    for manifest_path in campaign_attempt_manifests(repo_root, campaign_id, run_ids):
        manifest = load_yaml(manifest_path)
        attempt_id = str(manifest.get("attempt_id") or manifest_path.parent.name)
        l4_pair_id = str(manifest.get("cell_id") or derive_l4_pair_id(str(manifest.get("run_id") or attempt_id)))
        mt5_rows.extend(
            build_mt5_runtime_records(
                repo_root,
                identity,
                attempt_id=attempt_id,
                l4_pair_id=l4_pair_id,
                created_at_utc=created_at,
            )
        )

    comparison_rows = build_proxy_mt5_comparison_records(
        repo_root,
        identity,
        proxy_rows=proxy_rows,
        mt5_rows=mt5_rows,
        created_at_utc=created_at,
    )
    return write_campaign_kpi_files(
        repo_root,
        campaign_id=campaign_id,
        proxy_rows=proxy_rows,
        mt5_rows=mt5_rows,
        comparison_rows=comparison_rows,
        write=write,
        created_at_utc=created_at,
        include_existing=False,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a campaign-local KPI ledger from proxy and MT5 evidence.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--l4-pair-id")
    parser.add_argument("--all-existing-evidence", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.all_existing_evidence:
        summary = build_campaign_kpi_ledger_from_existing_evidence(
            repo_root,
            campaign_id=args.campaign_id,
            write=args.write,
        )
    else:
        missing = [
            name
            for name in ["run_id", "attempt_id", "l4_pair_id"]
            if not getattr(args, name)
        ]
        if missing:
            raise SystemExit(f"--all-existing-evidence or {', '.join('--' + item.replace('_', '-') for item in missing)} required")
        summary = build_campaign_kpi_ledger(
            repo_root,
            campaign_id=args.campaign_id,
            run_id=args.run_id,
            attempt_id=args.attempt_id,
            l4_pair_id=args.l4_pair_id,
            write=args.write,
        )
    print(yaml.safe_dump(summary, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
