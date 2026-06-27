from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.kpi_record_model import (  # noqa: E402
    ALLOWED_AUTHORITIES,
    ALLOWED_METRIC_NAMESPACES,
    ALLOWED_NA_REASONS,
    ALLOWED_RECORD_FAMILIES,
    ALLOWED_STAGE_KINDS,
    ALLOWED_VALUE_STATUSES,
    AUTHORITIES_BY_NAMESPACE,
    DEFAULT_CLAIM_BOUNDARY,
    FORBIDDEN_CLAIMS,
    KPI_SEGMENT_CLAIM_POLICY,
    KPI_LEDGER_CONTRACT_VERSION,
    KPI_LEDGER_MANIFEST_VERSION,
    KPI_RECORD_FIELDNAMES,
    KPI_RECORD_SCHEMA_VERSION,
    NAMESPACE_BY_FAMILY,
    OBSERVED,
    REQUIRED_KPI_SEGMENT_AXES,
    RECORD_FILES,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def is_repo_relative(value: str) -> bool:
    if not value:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return False
    candidate = Path(value)
    return not candidate.is_absolute() and ".." not in candidate.parts


def validate_contract(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "contracts" / "kpi_ledger_contract.yaml"
    if not path.exists():
        return ["docs/contracts/kpi_ledger_contract.yaml: missing"]
    data = load_yaml(path)
    errors: list[str] = []
    if data.get("version") != KPI_LEDGER_CONTRACT_VERSION:
        errors.append("docs/contracts/kpi_ledger_contract.yaml: version must be kpi_ledger_contract_v1")
    allowed = data.get("allowed") or {}
    for key, expected in {
        "record_family": ALLOWED_RECORD_FAMILIES,
        "stage_kind": ALLOWED_STAGE_KINDS,
        "metric_namespace": ALLOWED_METRIC_NAMESPACES,
        "value_status": ALLOWED_VALUE_STATUSES,
        "authority": ALLOWED_AUTHORITIES,
    }.items():
        observed = set(allowed.get(key) or [])
        missing = sorted(expected - observed)
        if missing:
            errors.append(f"docs/contracts/kpi_ledger_contract.yaml: allowed.{key} missing {missing}")
    segment_policy = data.get("segment_breakdown_policy") or {}
    required_axes = set(segment_policy.get("required_axes") or [])
    missing_axes = sorted(set(REQUIRED_KPI_SEGMENT_AXES) - required_axes)
    if missing_axes:
        errors.append(f"docs/contracts/kpi_ledger_contract.yaml: segment_breakdown_policy.required_axes missing {missing_axes}")
    if segment_policy.get("segment_claim_policy") != KPI_SEGMENT_CLAIM_POLICY:
        errors.append("docs/contracts/kpi_ledger_contract.yaml: segment_breakdown_policy.segment_claim_policy mismatch")
    for key in [
        "fake_segment_placeholder_forbidden",
        "observed_segment_requires_metric_or_count_basis",
        "missing_segment_requires_next_materialization_step",
    ]:
        if segment_policy.get(key) is not True:
            errors.append(f"docs/contracts/kpi_ledger_contract.yaml: segment_breakdown_policy.{key} must be true")
    return errors


def validate_manifest_shape(manifest_path: Path, manifest: dict[str, Any], repo_root: Path) -> list[str]:
    label = rel(manifest_path, repo_root)
    errors: list[str] = []
    if manifest.get("version") != KPI_LEDGER_MANIFEST_VERSION:
        errors.append(f"{label}: version must be {KPI_LEDGER_MANIFEST_VERSION}")
    schema_ref = manifest.get("schema_ref") or {}
    if schema_ref.get("version") != KPI_LEDGER_CONTRACT_VERSION:
        errors.append(f"{label}: schema_ref.version must be {KPI_LEDGER_CONTRACT_VERSION}")
    if schema_ref.get("path") != "docs/contracts/kpi_ledger_contract.yaml":
        errors.append(f"{label}: schema_ref.path must be docs/contracts/kpi_ledger_contract.yaml")
    if manifest.get("claim_boundary") != DEFAULT_CLAIM_BOUNDARY:
        errors.append(f"{label}: claim_boundary must be {DEFAULT_CLAIM_BOUNDARY}")
    policy = manifest.get("kpi_policy") or {}
    if policy.get("fixed_schema") is not True:
        errors.append(f"{label}: kpi_policy.fixed_schema must be true")
    if policy.get("mt5_missing_is_repair_trigger_before_na") is not True:
        errors.append(f"{label}: kpi_policy.mt5_missing_is_repair_trigger_before_na must be true")
    if policy.get("non_trading_score_probe_excluded_from_kpi_ledger") is not True:
        errors.append(f"{label}: kpi_policy.non_trading_score_probe_excluded_from_kpi_ledger must be true")
    if policy.get("score_probe_retained_only_in_runtime_evidence_not_kpi") is not True:
        errors.append(f"{label}: kpi_policy.score_probe_retained_only_in_runtime_evidence_not_kpi must be true")
    if policy.get("overall_and_segment_breakdowns_required") is not True:
        errors.append(f"{label}: kpi_policy.overall_and_segment_breakdowns_required must be true")
    for key in [
        "fake_segment_placeholder_forbidden",
        "observed_segment_requires_metric_or_count_basis",
        "missing_segment_requires_next_materialization_step",
    ]:
        if policy.get(key) is not True:
            errors.append(f"{label}: kpi_policy.{key} must be true")
    policy_axes = set(policy.get("required_segment_axes") or [])
    missing_policy_axes = sorted(set(REQUIRED_KPI_SEGMENT_AXES) - policy_axes)
    if missing_policy_axes:
        errors.append(f"{label}: kpi_policy.required_segment_axes missing {missing_policy_axes}")
    if policy.get("segment_claim_policy") != KPI_SEGMENT_CLAIM_POLICY:
        errors.append(f"{label}: kpi_policy.segment_claim_policy must be {KPI_SEGMENT_CLAIM_POLICY}")
    forbidden = set(manifest.get("forbidden_claims") or [])
    missing_forbidden = sorted(set(FORBIDDEN_CLAIMS) - forbidden)
    if missing_forbidden:
        errors.append(f"{label}: forbidden_claims missing {missing_forbidden}")
    return errors


def validate_summary_shape(summary_path: Path, summary: dict[str, Any], repo_root: Path) -> list[str]:
    label = rel(summary_path, repo_root)
    errors: list[str] = []
    policy = summary.get("kpi_policy") or {}
    if policy.get("overall_and_segment_breakdowns_required") is not True:
        errors.append(f"{label}: kpi_policy.overall_and_segment_breakdowns_required must be true")
    for key in [
        "fake_segment_placeholder_forbidden",
        "observed_segment_requires_metric_or_count_basis",
        "missing_segment_requires_next_materialization_step",
    ]:
        if policy.get(key) is not True:
            errors.append(f"{label}: kpi_policy.{key} must be true")
    policy_axes = set(policy.get("required_segment_axes") or [])
    missing_policy_axes = sorted(set(REQUIRED_KPI_SEGMENT_AXES) - policy_axes)
    if missing_policy_axes:
        errors.append(f"{label}: kpi_policy.required_segment_axes missing {missing_policy_axes}")
    if policy.get("segment_claim_policy") != KPI_SEGMENT_CLAIM_POLICY:
        errors.append(f"{label}: kpi_policy.segment_claim_policy must be {KPI_SEGMENT_CLAIM_POLICY}")

    coverage = summary.get("segment_coverage") or {}
    breakdowns = summary.get("segment_breakdowns") or {}
    coverage_axes = set(coverage.get("required_axes") or [])
    missing_coverage_axes = sorted(set(REQUIRED_KPI_SEGMENT_AXES) - coverage_axes)
    if missing_coverage_axes:
        errors.append(f"{label}: segment_coverage.required_axes missing {missing_coverage_axes}")
    if coverage.get("missing_axes"):
        errors.append(f"{label}: segment_coverage.missing_axes must be empty")
    if coverage.get("claim_policy") != KPI_SEGMENT_CLAIM_POLICY:
        errors.append(f"{label}: segment_coverage.claim_policy must be {KPI_SEGMENT_CLAIM_POLICY}")
    coverage_pending = set(coverage.get("pending_materialization_axes") or [])
    for axis in REQUIRED_KPI_SEGMENT_AXES:
        segment = breakdowns.get(axis)
        if not isinstance(segment, dict):
            errors.append(f"{label}: segment_breakdowns missing required axis {axis}")
            continue
        status = segment.get("status")
        analysis_status = segment.get("analysis_status")
        if status not in {"observed", "not_collected", "missing_source", "partial"}:
            errors.append(f"{label}: segment_breakdowns.{axis}.status is invalid")
        if status == "observed":
            if analysis_status != "materialized":
                errors.append(f"{label}: segment_breakdowns.{axis}.analysis_status must be materialized")
            has_count_basis = "record_count" in segment or "counts" in segment
            has_metric_basis = bool(segment.get("metric_basis") or segment.get("metric_basis_by_period_role"))
            if not (has_count_basis or has_metric_basis):
                errors.append(f"{label}: segment_breakdowns.{axis} observed segment lacks metric/count basis")
        if status == "partial":
            if analysis_status != "partial_materialized":
                errors.append(f"{label}: segment_breakdowns.{axis}.analysis_status must be partial_materialized")
            if not segment.get("missing_reason"):
                errors.append(f"{label}: segment_breakdowns.{axis} partial segment requires missing_reason")
            if not segment.get("next_materialization_step"):
                errors.append(f"{label}: segment_breakdowns.{axis} partial segment requires next_materialization_step")
        if axis != "overall" and status in {"not_collected", "missing_source"}:
            if analysis_status not in {"not_materialized", "missing_source"}:
                errors.append(f"{label}: segment_breakdowns.{axis}.analysis_status must show not materialized")
            if not segment.get("missing_reason"):
                errors.append(f"{label}: segment_breakdowns.{axis} requires missing_reason when not collected")
            if not segment.get("next_materialization_step"):
                errors.append(f"{label}: segment_breakdowns.{axis} requires next_materialization_step when not collected")
            if axis not in coverage_pending:
                errors.append(f"{label}: segment_coverage.pending_materialization_axes missing {axis}")
        claim_effect = str(segment.get("claim_effect") or "")
        if status in {"observed", "partial", "not_collected", "missing_source"} and "no_selection_or_pass" not in claim_effect:
            errors.append(f"{label}: segment_breakdowns.{axis}.claim_effect must keep no_selection_or_pass boundary")
    return errors


def validate_record_file_hashes(
    manifest_path: Path,
    manifest: dict[str, Any],
    repo_root: Path,
) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    label = rel(manifest_path, repo_root)
    errors: list[str] = []
    rows_by_file: dict[str, list[dict[str, str]]] = {}
    for file_key, expected_family in RECORD_FILES.items():
        spec = (manifest.get("record_files") or {}).get(file_key) or {}
        path_value = spec.get("path", "")
        if not is_repo_relative(path_value):
            errors.append(f"{label}: record_files.{file_key}.path must be repo-relative")
            continue
        path = repo_root / path_value
        if not path.exists():
            errors.append(f"{label}: record file missing {path_value}")
            continue
        header, rows = read_csv(path)
        rows_by_file[file_key] = rows
        if header != KPI_RECORD_FIELDNAMES:
            errors.append(f"{path_value}: header must match fixed KPI_RECORD_FIELDNAMES")
        if spec.get("sha256") != sha256(path):
            errors.append(f"{label}: record_files.{file_key}.sha256 mismatch")
        if int(spec.get("row_count", -1)) != len(rows):
            errors.append(f"{label}: record_files.{file_key}.row_count mismatch")
        for index, row in enumerate(rows, start=2):
            if row.get("record_family") != expected_family:
                errors.append(f"{path_value}:{index}: record_family must be {expected_family}")
    return errors, rows_by_file


def validate_source_refs(row: dict[str, str], *, row_label: str) -> list[str]:
    errors: list[str] = []
    value = row.get("source_artifact_refs_json", "")
    if not value:
        return [f"{row_label}: source_artifact_refs_json missing"]
    try:
        refs = json.loads(value)
    except json.JSONDecodeError as exc:
        return [f"{row_label}: source_artifact_refs_json invalid JSON: {exc}"]
    if not isinstance(refs, list):
        return [f"{row_label}: source_artifact_refs_json must be a list"]
    for ref in refs:
        if not isinstance(ref, dict):
            errors.append(f"{row_label}: source artifact ref must be object")
            continue
        path_value = str(ref.get("path", ""))
        if not is_repo_relative(path_value):
            errors.append(f"{row_label}: source artifact path must be repo-relative")
        if not ref.get("sha256"):
            errors.append(f"{row_label}: source artifact ref missing sha256")
    return errors


def attempt_surface_kind(repo_root: Path, attempt_id: str) -> str:
    if not attempt_id:
        return ""
    manifest_path = repo_root / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    if not manifest_path.exists():
        return ""
    manifest = load_yaml(manifest_path)
    contract = manifest.get("runtime_surface_contract") or {}
    surface_kind = str(contract.get("runtime_surface_kind") or "").strip()
    if surface_kind:
        return surface_kind
    if (manifest.get("execution_identity") or {}).get("non_trading_probe") is True:
        return "score_probe"
    if (manifest_path.parent / "score_telemetry_summary.yaml").exists():
        return "score_probe"
    return ""


def validate_row(row: dict[str, str], *, row_label: str, repo_root: Path) -> list[str]:
    errors: list[str] = []
    family = row.get("record_family", "")
    namespace = row.get("metric_namespace", "")
    authority = row.get("authority", "")
    status = row.get("value_status", "")
    metric_id = row.get("metric_id", "")
    if row.get("schema_version") != KPI_RECORD_SCHEMA_VERSION:
        errors.append(f"{row_label}: schema_version must be {KPI_RECORD_SCHEMA_VERSION}")
    if family not in ALLOWED_RECORD_FAMILIES:
        errors.append(f"{row_label}: unknown record_family {family}")
    if row.get("stage_kind") not in ALLOWED_STAGE_KINDS:
        errors.append(f"{row_label}: unknown stage_kind {row.get('stage_kind')}")
    if namespace not in ALLOWED_METRIC_NAMESPACES:
        errors.append(f"{row_label}: unknown metric_namespace {namespace}")
    if namespace not in NAMESPACE_BY_FAMILY.get(family, set()):
        errors.append(f"{row_label}: metric_namespace {namespace} not allowed for record_family {family}")
    if status not in ALLOWED_VALUE_STATUSES:
        errors.append(f"{row_label}: unknown value_status {status}")
    if authority not in ALLOWED_AUTHORITIES:
        errors.append(f"{row_label}: unknown authority {authority}")
    if authority not in AUTHORITIES_BY_NAMESPACE.get(namespace, set()):
        errors.append(f"{row_label}: authority {authority} not allowed for metric_namespace {namespace}")
    if row.get("n_a_reason", "") not in ALLOWED_NA_REASONS:
        errors.append(f"{row_label}: unknown n_a_reason {row.get('n_a_reason')}")
    if row.get("claim_boundary") != DEFAULT_CLAIM_BOUNDARY:
        errors.append(f"{row_label}: claim_boundary must be {DEFAULT_CLAIM_BOUNDARY}")
    if family == "mt5_runtime":
        surface_kind = attempt_surface_kind(repo_root, row.get("attempt_id", ""))
        if metric_id.startswith("mt5.score."):
            errors.append(f"{row_label}: mt5.score.* metrics are non-trading score-probe telemetry and forbidden in KPI ledger")
        if surface_kind == "score_probe":
            errors.append(f"{row_label}: non-trading score_probe attempts are excluded from KPI ledger")

    metric_value = row.get("metric_value", "")
    n_a_reason = row.get("n_a_reason", "")
    if status == OBSERVED:
        if metric_value == "":
            errors.append(f"{row_label}: observed row requires metric_value")
        if n_a_reason:
            errors.append(f"{row_label}: observed row must not set n_a_reason")
    else:
        if metric_value != "":
            errors.append(f"{row_label}: non-observed row must leave metric_value empty")
        if not n_a_reason:
            errors.append(f"{row_label}: non-observed row requires n_a_reason")
        if family == "mt5_runtime":
            diagnostic = row.get("parser_diagnostic", "")
            if not diagnostic:
                errors.append(f"{row_label}: MT5 non-observed KPI requires parser_diagnostic before accepting n/a")
            else:
                lowered = diagnostic.lower()
                if "repair" not in lowered:
                    errors.append(f"{row_label}: MT5 non-observed KPI diagnostic must name repair_required before accepting n/a")
                if "fallback" not in lowered and "workaround" not in lowered:
                    errors.append(f"{row_label}: MT5 non-observed KPI diagnostic must name fallback/workaround before accepting n/a")

    authority_path = row.get("authority_path", "")
    if not is_repo_relative(authority_path):
        errors.append(f"{row_label}: authority_path must be repo-relative")
    else:
        full = repo_root / authority_path
        if not full.exists():
            errors.append(f"{row_label}: authority_path missing {authority_path}")
        elif row.get("authority_sha256") != sha256(full):
            errors.append(f"{row_label}: authority_sha256 mismatch")
    if metric_id.startswith("mt5.tester_report.") and status == OBSERVED and authority != "mt5_tester_report_receipt":
        errors.append(f"{row_label}: observed tester report economics KPI requires mt5_tester_report_receipt authority")
    if metric_id.startswith("mt5.trade_shape.") and status == OBSERVED and authority != "mt5_trade_shape_summary":
        errors.append(f"{row_label}: observed trade-shape KPI requires mt5_trade_shape_summary authority")
    if family == "proxy_mt5_comparison":
        if not row.get("attempt_id") and not row.get("mt5_record_id"):
            errors.append(f"{row_label}: comparison row requires attempt_id or mt5_record_id")
    for claim in FORBIDDEN_CLAIMS:
        if re.search(rf"(?<!no_)(?<!not_){re.escape(claim)}\s*[:=]\s*(true|pass|ready|granted)", row.get("claim_effect", ""), re.I):
            errors.append(f"{row_label}: forbidden positive claim in claim_effect: {claim}")
    errors.extend(validate_source_refs(row, row_label=row_label))
    return errors


def validate_manifest(manifest_path: Path, repo_root: Path) -> list[str]:
    manifest = load_yaml(manifest_path)
    errors = validate_manifest_shape(manifest_path, manifest, repo_root)
    hash_errors, rows_by_file = validate_record_file_hashes(manifest_path, manifest, repo_root)
    errors.extend(hash_errors)
    record_ids: set[str] = set()
    mt5_record_ids: set[str] = set()
    proxy_record_ids: set[str] = set()
    for file_key, rows in rows_by_file.items():
        path_value = (manifest.get("record_files") or {}).get(file_key, {}).get("path", file_key)
        for index, row in enumerate(rows, start=2):
            row_label = f"{path_value}:{index}"
            errors.extend(validate_row(row, row_label=row_label, repo_root=repo_root))
            record_id = row.get("record_id", "")
            if not record_id:
                errors.append(f"{row_label}: record_id missing")
                continue
            if record_id in record_ids:
                errors.append(f"{row_label}: duplicate record_id {record_id}")
            record_ids.add(record_id)
            if row.get("record_family") == "proxy_experiment":
                proxy_record_ids.add(record_id)
            if row.get("record_family") == "mt5_runtime":
                mt5_record_ids.add(record_id)
    for file_key, rows in rows_by_file.items():
        if file_key != "proxy_mt5_comparison_records":
            continue
        path_value = (manifest.get("record_files") or {}).get(file_key, {}).get("path", file_key)
        for index, row in enumerate(rows, start=2):
            if row.get("proxy_record_id") and row["proxy_record_id"] not in proxy_record_ids:
                errors.append(f"{path_value}:{index}: proxy_record_id does not resolve")
            if row.get("mt5_record_id") and row["mt5_record_id"] not in mt5_record_ids:
                errors.append(f"{path_value}:{index}: mt5_record_id does not resolve")

    summary = manifest.get("summary") or {}
    summary_path_value = summary.get("path", "")
    if not is_repo_relative(summary_path_value):
        errors.append(f"{rel(manifest_path, repo_root)}: summary.path must be repo-relative")
    else:
        summary_path = repo_root / summary_path_value
        if not summary_path.exists():
            errors.append(f"{rel(manifest_path, repo_root)}: summary.path missing {summary_path_value}")
        elif summary.get("sha256") != sha256(summary_path):
            errors.append(f"{rel(manifest_path, repo_root)}: summary.sha256 mismatch")
        else:
            errors.extend(validate_summary_shape(summary_path, load_yaml(summary_path), repo_root))
    return errors


def validate(repo_root: Path) -> list[str]:
    errors = validate_contract(repo_root)
    manifest_paths = sorted((repo_root / "lab" / "campaigns").glob("**/kpi/kpi_ledger_manifest.yaml"))
    for manifest_path in manifest_paths:
        errors.extend(validate_manifest(manifest_path, repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("kpi ledger validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
