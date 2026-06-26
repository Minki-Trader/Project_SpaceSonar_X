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
    KPI_LEDGER_CONTRACT_VERSION,
    KPI_LEDGER_MANIFEST_VERSION,
    KPI_RECORD_FIELDNAMES,
    KPI_RECORD_SCHEMA_VERSION,
    KPI_SUMMARY_VERSION,
)
from foundation.mt5.tester_report_kpi import TESTER_REPORT_METRICS, parse_tester_report_kpis  # noqa: E402


TRADING_RUNTIME_SURFACE_KINDS = {"decision_replay"}
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
    return {
        "goal_id": manifest.get("active_goal_id", ""),
        "wave_id": (manifest.get("wave_ids") or [""])[0],
        "campaign_id": campaign_id,
        "surface_id": design.get("surface_id", ""),
        "sweep_id": design.get("sweep_id", ""),
    }


def base_record(identity: dict[str, Any], *, created_at_utc: str) -> dict[str, Any]:
    return {
        "schema_version": KPI_RECORD_SCHEMA_VERSION,
        "stage_kind": "campaign",
        "goal_id": identity.get("goal_id", ""),
        "wave_id": identity.get("wave_id", ""),
        "campaign_id": identity.get("campaign_id", ""),
        "synthesis_stage_id": "",
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
    value = metrics.get("model_metrics", {}).get("validation", {}).get("roc_auc")
    if value is None:
        raise RuntimeError(f"{repo_rel(metrics_path, repo_root)} missing model_metrics.validation.roc_auc")
    row = base_record(identity, created_at_utc=created_at_utc)
    row.update(
        {
            "record_id": f"proxy_{run_id}_validation_roc_auc_v1",
            "record_family": "proxy_experiment",
            "run_id": run_id,
            "l4_pair_id": l4_pair_id,
            "bundle_id": "",
            "attempt_id": "",
            "period_role": "validation",
            "proxy_record_id": "",
            "mt5_record_id": "",
            "metric_id": "proxy.validation.roc_auc",
            "metric_namespace": "proxy",
            "metric_value": f"{float(value):.12g}",
            "value_type": "float",
            "unit": "ratio",
            "value_status": "observed",
            "n_a_reason": "",
            "authority": "proxy_metrics_json",
            "authority_path": repo_rel(metrics_path, repo_root),
            "authority_sha256": sha256(metrics_path),
            "source_artifact_refs_json": json.dumps([artifact_ref(metrics_path, repo_root)], sort_keys=True),
            "parser_diagnostic": "proxy_metrics_json_key:model_metrics.validation.roc_auc",
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
    return rows


def count_distinct(rows: list[dict[str, Any]], field: str) -> int:
    return len({str(row.get(field, "")) for row in rows if row.get(field, "")})


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


def build_summary(
    *,
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
    return {
        "version": KPI_SUMMARY_VERSION,
        "campaign_id": identity["campaign_id"],
        "wave_id": identity.get("wave_id", ""),
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
        "kpi_policy": {
            "fixed_schema": True,
            "mt5_missing_is_repair_trigger_before_na": True,
            "proxy_only_runs_excluded_from_comparison_ledger": True,
            "non_trading_score_probe_excluded_from_kpi_ledger": True,
            "score_probe_retained_only_in_runtime_evidence_not_kpi": True,
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
            "stage_kind": "campaign",
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
        },
        "kpi_policy": {
            "fixed_schema": True,
            "mt5_missing_is_repair_trigger_before_na": True,
            "proxy_only_runs_excluded_from_comparison_ledger": True,
            "non_trading_score_probe_excluded_from_kpi_ledger": True,
            "score_probe_retained_only_in_runtime_evidence_not_kpi": True,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a campaign-local KPI ledger from proxy and MT5 evidence.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--l4-pair-id", required=True)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = build_campaign_kpi_ledger(
        Path(args.repo_root).resolve(),
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
