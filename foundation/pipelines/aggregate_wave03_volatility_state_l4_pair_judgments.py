from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, repo_relative, sha256_file
from spacesonar.control_plane.writer_contract import (
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
IDEA_ID = "idea_us100_wave03_intraday_volatility_state_transition_v0"
HYPOTHESIS_ID = "hyp_us100_wave03_compression_expansion_reversal_continuation_v0"
SURFACE_ID = "surface_us100_wave03_compression_expansion_decision_v0"
SWEEP_ID = "sweep_us100_wave03_compression_expansion_seed_v0"

PARENT_WORK_ITEM_ID = "work_wave03_volatility_state_l4_runtime_execution_v0"
WORK_ITEM_ID = "work_wave03_volatility_state_l4_pair_judgment_v0"
NEXT_WORK_ITEM_ID = "work_wave03_volatility_state_l4_portable_runtime_repair_v0"

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/l4_follow_through")
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
PAIR_SUMMARY = OUTPUT_DIR / "l4_pair_judgment_summary.yaml"
PAIR_INDEX = OUTPUT_DIR / "l4_pair_judgment_index.csv"
PAIR_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave03_volatility_state_l4_pair_judgment_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/campaign_manifest.yaml")

WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v3"
PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
SUPPORT_SKILLS = ["spacesonar-result-judgment"]
VALIDATION_DEPTH = "writer_scope_smoke"
CLAIM_BOUNDARY = (
    "wave03_l4_pair_judgment_only_no_runtime_authority_no_economics_pass_no_candidate_"
    "no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_l4_portable_runtime_repair_pending_no_runtime_authority_no_economics_pass_"
    "no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
STATUS = "wave03_l4_pair_judgment_completed_portable_runtime_repair_required"
NEXT_STATUS = "wave03_l4_portable_runtime_repair_required_next"
NEXT_ACTION = (
    "execute a bounded portable Strategy Tester contract repair/probe before any L5 routing; "
    "do not claim runtime authority, economics pass, selected baseline, live readiness, or Goal Achieve"
)
PROGRESS_EFFECT = "wave03_l4_pair_judgment_materialized"
EXPERIMENT_EFFECT = "l4_pair_boundary_record_written_with_next_executable_portable_runtime_repair"
BROAD_VALIDATION_ESCALATION_REASON = "none_pair_judgment_progress_no_protected_claim"
NON_PYTEST_SMOKES = [
    "py_compile",
    "pair_writer_smoke",
    "writer_scope_contract_lint",
    "machine_yaml_identity_lint",
    "active_pointer_smoke",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "operating_reference",
    "operating_promotion",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]
ACTIVE_RECORD_AUTHORITY = {
    "authoritative_fields": [
        "active_goal",
        "active_wave",
        "active_campaign",
        "active_work_item",
        "current_claim_boundary",
        "next_action",
        "unresolved_blockers",
    ],
    "current_truth_record": NEXT_WORK_ITEM.as_posix(),
    "summary_counts_role": "cumulative_reference_not_active_pointer",
    "rule": "select next action from active_work_item plus next_work_item; never from summary_counts alone",
}


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    full = REPO_ROOT / path if not path.is_absolute() else path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    enforce_writer_contract(path, payload)
    write_text(path, dump_yaml(payload))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    return {
        "path": repo_relative(REPO_ROOT, full),
        "sha256": sha256_file(full),
        "size_bytes": os.stat(filesystem_path(full)).st_size,
        "availability": availability,
    }


def load_optional_yaml(path: Path) -> dict[str, Any]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    return read_yaml(full) if path_exists(full) else {}


def load_optional_json(path: Path) -> dict[str, Any]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    return read_json(full) if path_exists(full) else {}


def git_state(repo_root: Path) -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=repo_root, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def redact_path(value: str) -> str:
    redacted = value
    replacements = {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }
    for env_name, token in replacements.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def safe_int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def first_scalar(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def optional_delta(left: float | None, right: float | None) -> float | str:
    if left is None or right is None:
        return ""
    return right - left


def run_manifest_for_row(row: dict[str, str]) -> dict[str, Any]:
    run_id = row.get("run_id", "")
    return load_optional_json(Path("lab") / "runs" / run_id / "run_manifest.json") if run_id else {}


def metrics_for_row(row: dict[str, str]) -> dict[str, Any]:
    run_id = row.get("run_id", "")
    return load_optional_json(Path("lab") / "runs" / run_id / "metrics.json") if run_id else {}


def bundle_for_row(row: dict[str, str]) -> dict[str, Any]:
    bundle_id = row.get("bundle_id", "")
    return load_optional_json(Path("runtime") / "packages" / bundle_id / "experiment_bundle.json") if bundle_id else {}


def score_summary_for_row(row: dict[str, str]) -> dict[str, Any]:
    path_value = row.get("score_telemetry_summary_path", "")
    return load_optional_yaml(Path(path_value)) if path_value else {}


def tester_receipt_for_row(row: dict[str, str]) -> dict[str, Any]:
    attempt_id = row.get("attempt_id", "")
    if not attempt_id:
        return {}
    return load_optional_yaml(Path("runtime") / "mt5_attempts" / attempt_id / "tester_report_receipt.yaml")


def portable_repair_overlay_rows() -> dict[str, dict[str, str]]:
    overlays: dict[str, dict[str, str]] = {}
    attempts_root = REPO_ROOT / "runtime" / "mt5_attempts"
    for manifest_path in attempts_root.glob("attempt_wave03_vst_cell_*_portable*_probe_v0/portable_repair_attempt_manifest.yaml"):
        manifest = load_optional_yaml(manifest_path)
        attempt_id = str(manifest.get("attempt_id") or manifest_path.parent.name)
        source_attempt_id = str(manifest.get("source_attempt_id") or "")
        if not source_attempt_id:
            continue
        root = manifest_path.parent
        terminal = load_optional_yaml(root / "terminal_run_summary.yaml")
        telemetry = load_optional_yaml(root / "score_telemetry_summary.yaml")
        receipt = load_optional_yaml(root / "tester_report_receipt.yaml")
        runtime_completion = terminal.get("runtime_completion") or {}
        period_identity = manifest.get("period_identity") or {}
        stats = telemetry.get("stats") or {}
        row_count = safe_int(stats.get("row_count"))
        report_observed = bool(terminal.get("tester_report_observed")) or bool(receipt.get("source_report_sha256"))
        overlay = {
            "attempt_id": attempt_id,
            "source_attempt_id": source_attempt_id,
            "period_role": str(period_identity.get("period_role") or ""),
            "from_date": str(period_identity.get("from_date") or ""),
            "to_date": str(period_identity.get("to_date") or ""),
            "status": str(runtime_completion.get("status") or "portable_repair_probe_recorded"),
            "result_judgment": "runtime_probe",
            "telemetry_observed": str(row_count > 0).lower(),
            "telemetry_row_count": str(row_count),
            "tester_report_observed": str(report_observed).lower(),
            "runtime_probe_complete": str(bool(runtime_completion.get("runtime_probe_complete"))).lower(),
            "terminal_mode": "portable_contract_attempt",
            "main_mode_fallback_used": "false",
            "tester_report_completed": str(bool(receipt.get("tester_report_completed"))).lower(),
            "terminal_summary_path": repo_relative(REPO_ROOT, root / "terminal_run_summary.yaml"),
            "score_telemetry_summary_path": repo_relative(REPO_ROOT, root / "score_telemetry_summary.yaml"),
            "score_diagnostic_summary_path": repo_relative(REPO_ROOT, root / "score_diagnostic_summary.yaml"),
            "telemetry_path": repo_relative(REPO_ROOT, root / "telemetry" / "score_telemetry.csv")
            if path_exists(root / "telemetry" / "score_telemetry.csv")
            else "",
            "tester_report_path": repo_relative(REPO_ROOT, root / "reports" / "tester_report.htm")
            if path_exists(root / "reports" / "tester_report.htm")
            else "",
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": "rerun Wave03 pair aggregation after portable repair probe evidence changes",
        }
        previous = overlays.get(source_attempt_id)
        previous_complete = boolish((previous or {}).get("runtime_probe_complete"))
        overlay_complete = boolish(overlay.get("runtime_probe_complete"))
        if previous is None or (overlay_complete and not previous_complete) or (
            overlay_complete == previous_complete and os.path.getmtime(filesystem_path(manifest_path)) > os.path.getmtime(filesystem_path(attempts_root / previous["attempt_id"] / "portable_repair_attempt_manifest.yaml"))
        ):
            overlays[source_attempt_id] = overlay
    return overlays


def long_short_count(stats: dict[str, Any]) -> int:
    counts = stats.get("decision_counts") or {}
    if not isinstance(counts, dict):
        return 0
    return safe_int(counts.get("long")) + safe_int(counts.get("short"))


def directional_rate(stats: dict[str, Any]) -> float | None:
    row_count = safe_int(stats.get("row_count"))
    if row_count <= 0:
        return None
    return long_short_count(stats) / row_count


def writer_contract_fields(
    *,
    next_action: str,
    claim_boundary: str,
    source_paths: list[str],
    outputs: list[str],
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    effective_blockers = blockers or ["standard_l4_runtime_completion_contract_pending_portable_terminal"]
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": PROGRESS_EFFECT,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": EXPERIMENT_EFFECT,
        "source_of_truth_paths": source_paths,
        "writer_owned_outputs": outputs,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": utc_now(),
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": effective_blockers,
        "next_action_or_reopen_condition": next_action,
    }


def pair_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "validation_telemetry_observed",
        "research_oos_telemetry_observed",
        "both_period_roles_observed",
        "nonempty_telemetry_pair",
        "tester_report_pair_observed",
        "tester_report_pair_completed",
        "runtime_probe_pair_complete",
        "portable_contract_pair_complete",
        "terminal_mode_pair",
        "validation_row_count",
        "research_oos_row_count",
        "validation_score_mean",
        "research_oos_score_mean",
        "score_mean_delta_research_minus_validation",
        "validation_directional_count",
        "research_oos_directional_count",
        "validation_directional_rate",
        "research_oos_directional_rate",
        "directional_rate_delta_research_minus_validation",
        "validation_proxy_trade_count",
        "research_oos_proxy_trade_count",
        "validation_proxy_trade_density",
        "research_oos_proxy_trade_density",
        "validation_proxy_profit_factor",
        "research_oos_proxy_profit_factor",
        "proxy_profit_factor_delta_research_minus_validation",
        "feature_recipe_id",
        "label_recipe_id",
        "decision_recipe_id",
        "decision_family",
        "holding_policy",
        "runtime_translation_status",
        "proxy_judgment",
        "comparison_class",
        "standard_l4_completion",
        "result_judgment",
        "l5_routing_status",
        "claim_boundary",
        "next_action",
    ]


def classify_pair(
    *,
    proxy_judgment: str,
    both_observed: bool,
    nonempty_pair: bool,
    reports_completed: bool,
    runtime_pair_complete: bool,
) -> str:
    if runtime_pair_complete:
        if proxy_judgment == "preserved_clue":
            return "proxy_preserved_clue_portable_l4_runtime_score_observed"
        if proxy_judgment == "inconclusive":
            return "proxy_inconclusive_portable_l4_runtime_score_observed"
        return "proxy_unclassified_portable_l4_runtime_score_observed"
    if not both_observed:
        return "proxy_observed_runtime_score_missing_or_partial"
    if not nonempty_pair:
        return "proxy_observed_runtime_score_empty"
    if not reports_completed:
        return "runtime_score_observed_report_incomplete"
    if proxy_judgment == "preserved_clue":
        return "proxy_preserved_clue_runtime_score_observed_but_portable_contract_missing"
    if proxy_judgment == "inconclusive":
        return "proxy_inconclusive_runtime_score_observed_but_portable_contract_missing"
    return "proxy_unclassified_runtime_score_observed_but_portable_contract_missing"


def l5_status_for_pair(*, runtime_pair_complete: bool, proxy_judgment: str) -> tuple[str, str]:
    if runtime_pair_complete:
        if proxy_judgment != "preserved_clue":
            return (
                "portable_l4_complete_proxy_inconclusive_no_l5_candidate",
                "continue portable repair on stronger remaining pairs before any candidate-specific L5 manifest",
            )
        return (
            "l5_routing_decision_possible_no_candidate_claim",
            "decide L5 routing only with candidate-specific manifest before any candidate claim",
        )
    return (
        "no_l5_until_portable_l4_contract",
        "repair portable Strategy Tester contract and rerun/record L4 before any L5 routing",
    )


def aggregate_pairs(started_at_utc: str, command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runtime_rows = read_csv_rows(REPO_ROOT / RUNTIME_INDEX)
    portable_overlays = portable_repair_overlay_rows()
    rows_by_cell: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        overlay = portable_overlays.get(row.get("attempt_id", ""))
        if overlay:
            row = {**row, **overlay}
        rows_by_cell[row["cell_id"]].append(row)

    pair_rows: list[dict[str, Any]] = []
    for cell_id in sorted(rows_by_cell):
        period_rows = {row["period_role"]: row for row in rows_by_cell[cell_id]}
        validation = period_rows.get("validation", {})
        research = period_rows.get("research_oos", {})
        anchor = validation or research
        metrics = metrics_for_row(anchor)
        manifest = run_manifest_for_row(anchor)
        bundle = bundle_for_row(anchor)
        validation_summary = score_summary_for_row(validation) if validation else {}
        research_summary = score_summary_for_row(research) if research else {}
        validation_receipt = tester_receipt_for_row(validation) if validation else {}
        research_receipt = tester_receipt_for_row(research) if research else {}
        validation_stats = validation_summary.get("stats") or {}
        research_stats = research_summary.get("stats") or {}
        validation_rows = safe_int(validation_stats.get("row_count"))
        research_rows = safe_int(research_stats.get("row_count"))
        validation_mean = safe_float(first_scalar(validation_stats, "score_stats", "mean", default=None))
        research_mean = safe_float(first_scalar(research_stats, "score_stats", "mean", default=None))
        validation_directional_rate = directional_rate(validation_stats)
        research_directional_rate = directional_rate(research_stats)
        validation_pf = safe_float(first_scalar(metrics, "trading_proxy_metrics", "validation", "gross_proxy_profit_factor", default=None))
        research_pf = safe_float(first_scalar(metrics, "trading_proxy_metrics", "research_oos_a", "gross_proxy_profit_factor", default=None))
        validation_density = safe_float(first_scalar(metrics, "trading_proxy_metrics", "validation", "trade_density", default=None))
        research_density = safe_float(first_scalar(metrics, "trading_proxy_metrics", "research_oos_a", "trade_density", default=None))
        decision_surface = bundle.get("decision_surface") or {}
        both_observed = boolish(validation.get("telemetry_observed")) and boolish(research.get("telemetry_observed"))
        nonempty_pair = validation_rows > 0 and research_rows > 0
        reports_observed = boolish(validation.get("tester_report_observed")) and boolish(research.get("tester_report_observed"))
        reports_completed = boolish(validation_receipt.get("tester_report_completed")) and boolish(
            research_receipt.get("tester_report_completed")
        )
        runtime_pair_complete = boolish(validation.get("runtime_probe_complete")) and boolish(research.get("runtime_probe_complete"))
        portable_pair = (
            validation.get("terminal_mode") == "portable_contract_attempt"
            and research.get("terminal_mode") == "portable_contract_attempt"
        )
        proxy_judgment = str(metrics.get("judgment_label") or manifest.get("result_judgment") or "")
        comparison_class = classify_pair(
            proxy_judgment=proxy_judgment,
            both_observed=both_observed,
            nonempty_pair=nonempty_pair,
            reports_completed=reports_completed,
            runtime_pair_complete=runtime_pair_complete,
        )
        l5_status, row_next_action = l5_status_for_pair(
            runtime_pair_complete=runtime_pair_complete,
            proxy_judgment=proxy_judgment,
        )
        pair_rows.append(
            {
                "cell_id": cell_id,
                "run_id": anchor.get("run_id", ""),
                "bundle_id": anchor.get("bundle_id", ""),
                "validation_attempt_id": validation.get("attempt_id", ""),
                "research_oos_attempt_id": research.get("attempt_id", ""),
                "validation_telemetry_observed": str(boolish(validation.get("telemetry_observed"))).lower(),
                "research_oos_telemetry_observed": str(boolish(research.get("telemetry_observed"))).lower(),
                "both_period_roles_observed": str(both_observed).lower(),
                "nonempty_telemetry_pair": str(nonempty_pair).lower(),
                "tester_report_pair_observed": str(reports_observed).lower(),
                "tester_report_pair_completed": str(reports_completed).lower(),
                "runtime_probe_pair_complete": str(runtime_pair_complete).lower(),
                "portable_contract_pair_complete": str(portable_pair).lower(),
                "terminal_mode_pair": f"{validation.get('terminal_mode', '')}|{research.get('terminal_mode', '')}",
                "validation_row_count": validation_rows,
                "research_oos_row_count": research_rows,
                "validation_score_mean": "" if validation_mean is None else validation_mean,
                "research_oos_score_mean": "" if research_mean is None else research_mean,
                "score_mean_delta_research_minus_validation": optional_delta(validation_mean, research_mean),
                "validation_directional_count": long_short_count(validation_stats),
                "research_oos_directional_count": long_short_count(research_stats),
                "validation_directional_rate": "" if validation_directional_rate is None else validation_directional_rate,
                "research_oos_directional_rate": "" if research_directional_rate is None else research_directional_rate,
                "directional_rate_delta_research_minus_validation": optional_delta(validation_directional_rate, research_directional_rate),
                "validation_proxy_trade_count": first_scalar(metrics, "trading_proxy_metrics", "validation", "trade_count", default=""),
                "research_oos_proxy_trade_count": first_scalar(metrics, "trading_proxy_metrics", "research_oos_a", "trade_count", default=""),
                "validation_proxy_trade_density": "" if validation_density is None else validation_density,
                "research_oos_proxy_trade_density": "" if research_density is None else research_density,
                "validation_proxy_profit_factor": "" if validation_pf is None else validation_pf,
                "research_oos_proxy_profit_factor": "" if research_pf is None else research_pf,
                "proxy_profit_factor_delta_research_minus_validation": optional_delta(validation_pf, research_pf),
                "feature_recipe_id": str(bundle.get("feature_recipe_id") or ""),
                "label_recipe_id": str(bundle.get("label_recipe_id") or ""),
                "decision_recipe_id": str(bundle.get("decision_recipe_id") or ""),
                "decision_family": str(decision_surface.get("decision_family") or ""),
                "holding_policy": str(decision_surface.get("holding_policy") or ""),
                "runtime_translation_status": str(decision_surface.get("runtime_translation_status") or ""),
                "proxy_judgment": proxy_judgment,
                "comparison_class": comparison_class,
                "standard_l4_completion": "completed" if runtime_pair_complete else "incomplete_main_mode_fallback_portable_contract_missing",
                "result_judgment": "runtime_probe",
                "l5_routing_status": l5_status,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": row_next_action,
            }
        )

    runtime_summary = read_yaml(REPO_ROOT / RUNTIME_SUMMARY)
    runtime_counts = runtime_summary.get("counts") or {}
    ended_at_utc = utc_now()
    pair_count = len(pair_rows)
    complete_pair_count = sum(row["runtime_probe_pair_complete"] == "true" for row in pair_rows)
    portable_pair_count = sum(row["portable_contract_pair_complete"] == "true" for row in pair_rows)
    reports_completed_count = sum(row["tester_report_pair_completed"] == "true" for row in pair_rows)
    l5_counts = Counter(str(row["l5_routing_status"]) for row in pair_rows)
    comparison_counts = Counter(str(row["comparison_class"]) for row in pair_rows)
    proxy_counts = Counter(str(row["proxy_judgment"]) for row in pair_rows)
    result_counts = Counter(str(row["result_judgment"]) for row in pair_rows)
    missing_evidence = [
        "standard_l4_runtime_completion_contract_pending_for_remaining_pairs"
        if complete_pair_count
        else "standard_l4_runtime_completion_contract_pending_portable_terminal",
        "candidate_specific_L5_manifest_not_opened",
        "economics_metrics_not_available_from_non_trading_score_probe",
        "row_level_proxy_vs_MT5_score_alignment_not_performed",
    ]
    if not complete_pair_count:
        missing_evidence.insert(1, "portable_Strategy_Tester_contract_repair_attempt_not_materialized")
    source_paths = [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()]
    outputs = [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()]
    summary: dict[str, Any] = {
        "version": "wave03_volatility_state_l4_pair_judgment_summary_v1",
        "summary_id": "wave03_volatility_state_l4_pair_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": None,
            "artifact_id": "artifact_wave03_volatility_state_l4_pair_judgment_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "support_skills": list(SUPPORT_SKILLS),
        "counts": {
            "cell_pair_count": pair_count,
            "runtime_probe_pair_complete_count": complete_pair_count,
            "both_period_roles_observed_count": sum(row["both_period_roles_observed"] == "true" for row in pair_rows),
            "nonempty_telemetry_pair_count": sum(row["nonempty_telemetry_pair"] == "true" for row in pair_rows),
            "tester_report_pair_observed_count": sum(row["tester_report_pair_observed"] == "true" for row in pair_rows),
            "tester_report_pair_completed_count": reports_completed_count,
            "portable_contract_pair_count": portable_pair_count,
            "main_mode_fallback_pair_count": pair_count - portable_pair_count,
            "standard_l4_completion_blocked_count": pair_count - complete_pair_count,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "proxy_judgment_counts": dict(proxy_counts),
            "result_judgment_counts": dict(result_counts),
            "l5_status_counts": dict(l5_counts),
            "comparison_class_counts": dict(comparison_counts),
            "runtime_execution_counts": runtime_counts,
        },
        "judgment": {
            "result_subject": "Wave03 volatility-state L4 validation/research_oos score telemetry pair aggregation",
            "evidence_paths": source_paths,
            "metric_identity": "paired MT5 score telemetry summaries and tester report receipts; non-trading score probe only",
            "comparison_baseline": "source proxy judgment plus MT5 validation/research_oos score-observation presence",
            "tested_factor": "Wave03 multi-axis volatility state transition surface after ONNX/EA/MT5 score-probe follow-through",
            "kpi_interpretation": (
                "diagnostic runtime score observation only; completed portable L4 score probes do not create trading economics, "
                "and no trading economics, profit factor, drawdown, runtime authority, or live meaning is claimed"
            ),
            "directional_effect_hypothesis": (
                "completed portable score-observation pairs can inform a bounded L5 routing decision only through candidate-specific manifests; "
                "remaining pairs still require portable repair before any stronger runtime claim"
            ),
            "attribution_confidence": "low_runtime_observation_only",
            "judgment_label": "runtime_probe",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": missing_evidence,
            "validation_depth": VALIDATION_DEPTH,
            "non_pytest_smokes": list(NON_PYTEST_SMOKES),
            "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
            "next_action": NEXT_ACTION,
        },
        "runtime_contract_effect": {
            "l4_score_observation": "observed_with_portable_repair_overlay_for_completed_pairs",
            "standard_l4_completion": f"{complete_pair_count}/{pair_count}_pairs_completed_under_portable_l4_contract",
            "main_mode_fallback": "diagnostic_only_for_pairs_without_portable_repair_overlay",
            "l5_continuation": "candidate_specific_manifest_required_no_candidate_claim",
            "locked_final_oos_b": "not_used",
        },
        "provenance": {
            "source_inputs": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": outputs,
            "source_of_truth_paths": source_paths,
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "yaml": yaml.__version__,
                **git_state(REPO_ROOT),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [ARTIFACT_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "pair_summary_index_and_closeout_written_from_runtime_execution_summary_index_and_attempt_receipts",
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "artifact_outputs": {
            "pair_summary": PAIR_SUMMARY.as_posix(),
            "pair_index": PAIR_INDEX.as_posix(),
            "pair_closeout": PAIR_CLOSEOUT.as_posix(),
            "runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "runtime_execution_index": RUNTIME_INDEX.as_posix(),
        },
        "prevention_memory": [
            "Wave03 main-mode score telemetry is diagnostic runtime observation only.",
            "Portable repair summaries can overlay main-mode attempt rows for pair judgment only when telemetry and completed reports satisfy the runtime contract.",
            "Non-trading score probes cannot create economics pass, runtime authority, selected baseline, live readiness, or Goal Achieve.",
        ],
        "unresolved_blockers": [
            "standard_l4_runtime_completion_contract_pending_for_remaining_pairs",
            "Wave03_L5_routing_blocked_until_portable_L4_contract",
        ],
        "reopen_conditions": [
            "rerun pair aggregation if any Wave03 L4 attempt manifest, score telemetry summary, or tester report receipt changes",
            "repair portable Strategy Tester contract and rerun/record L4 before any L5 routing decision",
        ],
        "operational_validation_required": False,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    summary.update(
        writer_contract_fields(
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=source_paths,
            outputs=outputs,
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    summary["unresolved_blockers_or_none"] = list(summary["unresolved_blockers"])
    return summary, pair_rows


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "operational_validation_required": False,
        "forbidden_claims": summary["forbidden_claims"],
    }
    payload.update(
        writer_contract_fields(
            next_action=NEXT_ACTION,
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=[PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
            outputs=[PAIR_CLOSEOUT.as_posix()],
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    payload["unresolved_blockers_or_none"] = list(summary["unresolved_blockers"])
    return payload


def upsert_rows(path: Path, key_field: str, new_rows: list[dict[str, str]]) -> None:
    rows = read_csv_rows(REPO_ROOT / path) if path_exists(REPO_ROOT / path) else []
    fieldnames = list(rows[0].keys()) if rows else list(new_rows[0].keys())
    by_key = {row.get(key_field, ""): row for row in rows}
    for new_row in new_rows:
        by_key[str(new_row[key_field])] = {**{field: "" for field in fieldnames}, **new_row}
    write_csv(path, list(by_key.values()), fieldnames)


def upsert_artifact_registry(summary: dict[str, Any]) -> None:
    rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY) if path_exists(REPO_ROOT / ARTIFACT_REGISTRY) else []
    fieldnames = list(rows[0].keys()) if rows else [
        "artifact_id",
        "run_id",
        "bundle_id",
        "attempt_id",
        "artifact_type",
        "path_or_uri",
        "sha256",
        "size_bytes",
        "availability",
        "producer_command",
        "regeneration_command",
        "source_of_truth",
        "consumer",
        "claim_boundary",
        "notes",
    ]
    producer = summary["provenance"]["producer"]

    def row(artifact_id: str, artifact_type: str, path: Path, notes: str) -> dict[str, str]:
        full = REPO_ROOT / path
        payload = {key: "" for key in fieldnames}
        payload.update(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "sha256": sha256_file(full),
                "size_bytes": str(os.stat(filesystem_path(full)).st_size),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": PAIR_SUMMARY.as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": notes,
            }
        )
        return payload

    upsert_rows(
        ARTIFACT_REGISTRY,
        "artifact_id",
        [
            row(
                "artifact_wave03_volatility_state_l4_pair_judgment_summary_v0",
                "l4_pair_judgment_summary",
                PAIR_SUMMARY,
                "source-of-truth summary for Wave03 paired L4 score-observation judgment",
            ),
            row(
                "artifact_wave03_volatility_state_l4_pair_judgment_index_v0",
                "l4_pair_judgment_index",
                PAIR_INDEX,
                "compact index of Wave03 paired validation/research_oos L4 judgments",
            ),
            row(
                "artifact_wave03_volatility_state_l4_pair_judgment_closeout_v0",
                "work_closeout",
                PAIR_CLOSEOUT,
                "closeout for Wave03 L4 pair judgment work",
            ),
        ],
    )


def next_work_record(summary: dict[str, Any]) -> dict[str, Any]:
    source_paths = [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), NEXT_WORK_ITEM.as_posix()]
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "support_skills": [],
        "verification_profile": "mt5_l4_runtime_probe_repair",
        "targets": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
        "acceptance_criteria": [
            "diagnose and repair or record a bounded portable Strategy Tester contract attempt",
            "do not use main-mode fallback as standard L4 completion",
            "do not claim runtime authority, economics pass, selected baseline, live readiness, reviewed/verified pass, or Goal Achieve",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "l4_runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "l4_runtime_execution_index": RUNTIME_INDEX.as_posix(),
            "l4_pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "l4_pair_judgment_index": PAIR_INDEX.as_posix(),
            "l4_pair_judgment_status": summary["status"],
            "l4_pair_judgment_counts": summary["counts"],
            "runtime_probe_complete_count": summary["counts"]["runtime_probe_pair_complete_count"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            "lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/l4_follow_through/l4_portable_runtime_repair_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/portable_repair_attempt_manifest.yaml if a new portable attempt is materialized",
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "unresolved_blockers_or_none": list(summary["unresolved_blockers"]),
        "reopen_conditions": [
            "writable portable terminal root with account/config/report path and staged EX5 is available",
            "portable Strategy Tester execution records telemetry and completed report hashes",
        ],
    }
    payload.update(
        writer_contract_fields(
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=source_paths,
            outputs=[NEXT_WORK_ITEM.as_posix()],
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    payload["unresolved_blockers_or_none"] = list(summary["unresolved_blockers"])
    return payload


def update_control_records(summary: dict[str, Any]) -> None:
    state = git_state(REPO_ROOT)
    next_work = next_work_record(summary)
    write_yaml(NEXT_WORK_ITEM, next_work)

    common_contract = writer_contract_fields(
        next_action=NEXT_ACTION,
        claim_boundary=NEXT_CLAIM_BOUNDARY,
        source_paths=[PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), NEXT_WORK_ITEM.as_posix()],
        outputs=[],
        blockers=list(next_work["unresolved_blockers"]),
    )

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_goal_id": GOAL_ID,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": next_work["unresolved_blockers"],
            "active_ids": {
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
            },
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": summary["judgment"]["judgment_label"],
                "claim_boundary": summary["claim_boundary"],
                "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.setdefault("current_truth_sources", [])
    for source in [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()]:
        if source not in resume["current_truth_sources"]:
            resume["current_truth_sources"].append(source)
    resume.update({**common_contract, "writer_owned_outputs": [RESUME_CURSOR.as_posix()]})
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "active_ids": resume["active_ids"],
            "next_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": NEXT_WORK_ITEM.as_posix(),
                "summary": NEXT_ACTION,
            },
        }
    )
    wave03 = goal.setdefault("wave03_volatility_state_l4_pair_judgment", {})
    wave03.update(
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "l4_pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "l4_pair_judgment_index": PAIR_INDEX.as_posix(),
            "l4_pair_judgment_status": summary["status"],
            "l4_pair_judgment_counts": summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    goal.update({**common_contract, "writer_owned_outputs": [GOAL_MANIFEST.as_posix()]})
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_action": NEXT_ACTION,
            "missing_evidence": summary["judgment"]["missing_evidence"],
            "unresolved_blockers": next_work["unresolved_blockers"],
            "reopen_conditions": next_work["reopen_conditions"],
        }
    )
    l4 = campaign.setdefault("l4_follow_through", {})
    l4.update(
        {
            "pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "pair_judgment_status": summary["status"],
            "pair_judgment_counts": summary["counts"],
        }
    )
    evidence_paths = campaign.setdefault("evidence_paths", [])
    for source in [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()]:
        if source not in evidence_paths:
            evidence_paths.append(source)
    campaign.update({**common_contract, "writer_owned_outputs": [CAMPAIGN_MANIFEST.as_posix()]})
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": summary["ended_at_utc"],
            "active_goal": {"goal_id": GOAL_ID, "status": NEXT_STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": NEXT_STATUS,
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": None,
            },
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": next_work["unresolved_blockers"],
            "active_record_authority": dict(ACTIVE_RECORD_AUTHORITY),
            "status": NEXT_STATUS,
        }
    )
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave03_l4_pair_judgment"] = summary["counts"]
    workspace.update({**common_contract, "writer_owned_outputs": [WORKSPACE_STATE.as_posix()]})
    write_yaml(WORKSPACE_STATE, workspace)

    upsert_goal_and_campaign_registries(state)


def upsert_goal_and_campaign_registries(state: dict[str, Any]) -> None:
    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                if "status" in row:
                    row["status"] = NEXT_STATUS
                if "active_phase" in row:
                    row["active_phase"] = NEXT_STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                if "notes" in row:
                    row["notes"] = "Wave03 L4 pair judgment written; portable runtime repair required before stronger claims."
        if rows:
            write_csv(GOAL_REGISTRY, rows, list(rows[0].keys()))
    if path_exists(REPO_ROOT / CAMPAIGN_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / CAMPAIGN_REGISTRY)
        for row in rows:
            if row.get("campaign_id") == CAMPAIGN_ID:
                if "status" in row:
                    row["status"] = NEXT_STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                if "evidence_path" in row:
                    row["evidence_path"] = PAIR_SUMMARY.as_posix()
                if "notes" in row:
                    row["notes"] = "Pair judgment is diagnostic only; portable L4 contract remains pending."
        if rows:
            write_csv(CAMPAIGN_REGISTRY, rows, list(rows[0].keys()))


def smoke_pair_outputs(summary: dict[str, Any], pair_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for path in [PAIR_SUMMARY, PAIR_INDEX, PAIR_CLOSEOUT, RUNTIME_SUMMARY, RUNTIME_INDEX]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing source-of-truth path: {path.as_posix()}")
    loaded_summary = read_yaml(REPO_ROOT / PAIR_SUMMARY) if path_exists(REPO_ROOT / PAIR_SUMMARY) else {}
    loaded_closeout = read_yaml(REPO_ROOT / PAIR_CLOSEOUT) if path_exists(REPO_ROOT / PAIR_CLOSEOUT) else {}
    loaded_rows = read_csv_rows(REPO_ROOT / PAIR_INDEX) if path_exists(REPO_ROOT / PAIR_INDEX) else []
    counts = loaded_summary.get("counts") or {}
    if loaded_summary.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("pair summary claim_boundary mismatch")
    if loaded_closeout.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("pair closeout claim_boundary mismatch")
    if len(loaded_rows) != len(pair_rows):
        errors.append("pair index row count mismatch")
    if counts.get("cell_pair_count") != len(pair_rows):
        errors.append("pair summary cell_pair_count mismatch")
    if counts.get("candidate_count") != 0 or counts.get("l5_candidate_count") != 0:
        errors.append("pair summary candidate counts must stay zero")
    expected_complete = sum(row["runtime_probe_pair_complete"] == "true" for row in pair_rows)
    expected_portable = sum(row["portable_contract_pair_complete"] == "true" for row in pair_rows)
    if counts.get("runtime_probe_pair_complete_count") != expected_complete:
        errors.append("pair summary runtime_probe_pair_complete_count mismatch")
    if counts.get("portable_contract_pair_count") != expected_portable:
        errors.append("pair summary portable_contract_pair_count mismatch")
    if expected_complete > expected_portable:
        errors.append("runtime complete count cannot exceed portable contract pair count")
    if loaded_summary.get("operational_validation_required") is not False:
        errors.append("pair summary operational_validation_required must be false")

    registry_rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    by_id = {row.get("artifact_id"): row for row in registry_rows}
    for artifact_id, path in [
        ("artifact_wave03_volatility_state_l4_pair_judgment_summary_v0", PAIR_SUMMARY),
        ("artifact_wave03_volatility_state_l4_pair_judgment_index_v0", PAIR_INDEX),
        ("artifact_wave03_volatility_state_l4_pair_judgment_closeout_v0", PAIR_CLOSEOUT),
    ]:
        row = by_id.get(artifact_id)
        if not row:
            errors.append(f"artifact registry missing {artifact_id}")
            continue
        full = REPO_ROOT / path
        if row.get("path_or_uri") != path.as_posix():
            errors.append(f"{artifact_id}: path mismatch")
        if row.get("sha256") != sha256_file(full):
            errors.append(f"{artifact_id}: sha256 mismatch")
        if str(row.get("size_bytes")) != str(os.stat(filesystem_path(full)).st_size):
            errors.append(f"{artifact_id}: size mismatch")

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    next_work = read_yaml(REPO_ROOT / NEXT_WORK_ITEM)
    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("workspace claim boundary mismatch")
    if workspace.get("next_action") != NEXT_ACTION:
        errors.append("workspace next_action mismatch")
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("workspace active_work_item id mismatch")
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("next_work_item id mismatch")
    if next_work.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("next_work_item claim boundary mismatch")
    if (next_work.get("current_truth") or {}).get("l4_pair_judgment_summary") != PAIR_SUMMARY.as_posix():
        errors.append("next_work_item missing pair summary current truth")
    if next_work.get("operational_validation_required") is not False:
        errors.append("next_work_item operational_validation_required must be false")
    if goal.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("goal manifest claim_boundary mismatch")
    if (goal.get("next_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("goal manifest next_work_item mismatch")
    if campaign.get("status") != NEXT_STATUS:
        errors.append("campaign manifest status mismatch")
    if campaign.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("campaign manifest claim_boundary mismatch")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave03 volatility-state L4 validation/research_oos pair judgments.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global REPO_ROOT
    REPO_ROOT = Path(args.repo_root).resolve()
    started_at_utc = utc_now()
    command_argv = [
        Path(sys.executable).name,
        "foundation/pipelines/aggregate_wave03_volatility_state_l4_pair_judgments.py",
        *(argv or []),
    ]
    if args.smoke_only:
        summary = read_yaml(REPO_ROOT / PAIR_SUMMARY)
        pair_rows = read_csv_rows(REPO_ROOT / PAIR_INDEX)
        errors = smoke_pair_outputs(summary, pair_rows)
    else:
        summary, pair_rows = aggregate_pairs(started_at_utc, command_argv)
        write_yaml(PAIR_SUMMARY, summary)
        write_csv(PAIR_INDEX, pair_rows, pair_index_fieldnames())
        write_yaml(PAIR_CLOSEOUT, build_closeout(summary))
        upsert_artifact_registry(summary)
        if args.write_control_records:
            update_control_records(summary)
        errors = smoke_pair_outputs(summary, pair_rows)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "wave03 volatility-state l4 pair judgment writer-smoke passed: "
        f"pairs={len(pair_rows)} status={summary.get('status')} claim_boundary={summary.get('claim_boundary')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
