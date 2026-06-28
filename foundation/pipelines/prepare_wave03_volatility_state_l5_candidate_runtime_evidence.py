from __future__ import annotations

import argparse
import copy
import csv
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

import foundation.pipelines.decide_wave03_volatility_state_l5_routing as routing_writer
import foundation.pipelines.repair_wave03_volatility_state_l4_portable_runtime as portable_repair
import foundation.pipelines.run_wave0_l4_mt5_attempts as l4_base
from foundation.mt5.tester_report_kpi import parse_tester_report_kpis
from foundation.pipelines.run_mt5_fixed_fixture_probe import (
    DEFAULT_TERMINAL,
    portable_terminal_root_preflight,
    redact_path,
)
from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, sha256_file
from spacesonar.control_plane.writer_contract import (
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = routing_writer.GOAL_ID
WAVE_ID = routing_writer.WAVE_ID
CAMPAIGN_ID = routing_writer.CAMPAIGN_ID
IDEA_ID = routing_writer.IDEA_ID
HYPOTHESIS_ID = routing_writer.HYPOTHESIS_ID
SURFACE_ID = routing_writer.SURFACE_ID
SWEEP_ID = routing_writer.SWEEP_ID

PARENT_WORK_ITEM_ID = routing_writer.WORK_ITEM_ID
WORK_ITEM_ID = "work_wave03_volatility_state_l5_candidate_runtime_evidence_preparation_v0"
NEXT_WORK_ITEM_ID = "work_wave03_volatility_state_l5_candidate_boundary_decision_v0"
FINAL_GUARD_WORK_ITEM_ID = "work_wave03_volatility_state_l5_final_claim_guard_v0"

OUTPUT_DIR = routing_writer.OUTPUT_DIR
ROUTING_SUMMARY = routing_writer.ROUTING_SUMMARY
ROUTING_INDEX = routing_writer.ROUTING_INDEX
EVIDENCE_SUMMARY = OUTPUT_DIR / "l5_runtime_evidence_summary.yaml"
EVIDENCE_INDEX = OUTPUT_DIR / "l5_runtime_evidence_index.csv"
EVIDENCE_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave03_volatility_state_l5_candidate_runtime_evidence_preparation_v0_closeout.yaml"
)
NEXT_WORK_ITEM = routing_writer.NEXT_WORK_ITEM
RESUME_CURSOR = routing_writer.RESUME_CURSOR
GOAL_MANIFEST = routing_writer.GOAL_MANIFEST
WORKSPACE_STATE = routing_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = routing_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = routing_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = routing_writer.GOAL_REGISTRY
CAMPAIGN_REGISTRY = routing_writer.CAMPAIGN_REGISTRY
CANDIDATE_REGISTRY = routing_writer.CANDIDATE_REGISTRY

PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "l5_candidate_runtime_evidence_writer_smoke",
    "tester_report_kpi_parse_for_l5_decision_execution_attempts",
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
BROAD_VALIDATION_ESCALATION_REASON = "none_l5_candidate_runtime_evidence_writer_scope_only_no_protected_claim"
FORBIDDEN_CLAIMS = routing_writer.FORBIDDEN_CLAIMS

CLAIM_BOUNDARY = (
    "wave03_l5_candidate_runtime_evidence_observed_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
INCOMPLETE_CLAIM_BOUNDARY = (
    "wave03_l5_candidate_runtime_evidence_incomplete_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_l5_candidate_boundary_decision_pending_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
FINAL_GUARD_CLAIM_BOUNDARY = (
    "wave03_l5_final_claim_guard_pending_no_selected_baseline_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)

STATUS = "wave03_l5_candidate_runtime_evidence_observed_boundary_decision_pending"
INCOMPLETE_STATUS = "wave03_l5_candidate_runtime_evidence_incomplete_repair_pending"
FINAL_GUARD_STATUS = "wave03_l5_operational_review_reference_observed_final_claim_guard_pending"
NEXT_ACTION = (
    "decide Wave03 L5 candidate boundary from candidate-specific decision-execution runtime evidence; "
    "do not claim runtime authority, economics pass, live readiness, or Goal Achieve"
)
FINAL_GUARD_NEXT_ACTION = (
    "run final claim guard and prepare an operational-review evidence packet only if the L5 metrics remain "
    "consistent with the declared reference; no runtime authority, economics pass, live readiness, or Goal Achieve yet"
)
REPAIR_NEXT_ACTION = (
    "repair or rerun the candidate-specific L5 decision-execution runtime probe before any L5 candidate or "
    "operational-review claim"
)

COMMON_L5_ROOT = "SpaceSonar\\wave03_volatility_state_l5_decision_execution"
DEFAULT_HOLD_BARS = 72
DEFAULT_MAGIC_BASE = 503000
DEFAULT_DEVIATION_POINTS = 20


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
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


def write_plain_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, dump_yaml(payload))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def rel(path: Path) -> str:
    full = path if path.is_absolute() else REPO_ROOT / path
    return full.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else REPO_ROOT / path
    return {
        "path": rel(full),
        "sha256": sha256_file(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def git_state() -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def contract_fields(
    *,
    primary_family: str = PRIMARY_FAMILY,
    primary_skill: str = PRIMARY_SKILL,
    progress_effect: str,
    next_action: str,
    experiment_effect: str,
    claim_boundary: str,
    source_paths: list[str],
    outputs: list[str],
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": primary_family,
        "primary_skill": primary_skill,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": progress_effect,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": experiment_effect,
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
            "failures": [],
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": list(blockers or ["none"]),
        "next_action_or_reopen_condition": next_action,
    }


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def metric_value(parsed: dict[str, Any], metric_id: str) -> float | None:
    metric = (parsed.get("metrics") or {}).get(metric_id) or {}
    return safe_float(metric.get("metric_value"))


def date_days(from_date: str, to_date: str) -> int:
    try:
        start = datetime.strptime(from_date, "%Y.%m.%d")
        end = datetime.strptime(to_date, "%Y.%m.%d")
    except ValueError:
        return 0
    return max(1, (end - start).days + 1)


def candidate_summary_path(candidate_id: str) -> Path:
    return Path("lab") / "candidates" / candidate_id / "candidate_summary.yaml"


def candidate_evidence_path(candidate_id: str) -> Path:
    return Path("lab") / "candidates" / candidate_id / "l5_runtime_evidence_summary.yaml"


def opened_candidate_ids() -> list[str]:
    summary = read_yaml(REPO_ROOT / ROUTING_SUMMARY)
    return [str(item) for item in summary.get("opened_candidate_ids") or []]


def l5_attempt_id(cell_id: str, period_role: str) -> str:
    cell_number = cell_id.replace("wave03_vst_cell_", "")
    return f"attempt_wave03_vst_cell_{cell_number}_l5_{period_role}_decision_execution_v0"


def period_plan_from_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = candidate.get("source_evidence") or {}
    plans: list[dict[str, Any]] = []
    for period_role, key in [
        ("validation", "validation_attempt_id"),
        ("research_oos", "research_oos_attempt_id"),
    ]:
        source_probe_id = str(evidence.get(key) or "")
        if not source_probe_id:
            continue
        probe_root = REPO_ROOT / "runtime" / "mt5_attempts" / source_probe_id
        probe_manifest_path = probe_root / "portable_repair_attempt_manifest.yaml"
        probe_manifest = read_yaml(probe_manifest_path) if path_exists(probe_manifest_path) else {}
        source_attempt_id = str(probe_manifest.get("source_attempt_id") or source_probe_id)
        source_manifest_path = REPO_ROOT / "runtime" / "mt5_attempts" / source_attempt_id / "attempt_manifest.yaml"
        source_manifest = read_yaml(source_manifest_path) if path_exists(source_manifest_path) else {}
        period_identity = source_manifest.get("period_identity") or probe_manifest.get("period_identity") or {}
        attempt_id = l5_attempt_id(str(candidate["source_cell_id"]), period_role)
        plans.append(
            {
                "candidate_id": candidate["candidate_id"],
                "cell_id": candidate["source_cell_id"],
                "period_role": period_role,
                "attempt_id": attempt_id,
                "source_probe_attempt_id": source_probe_id,
                "source_attempt_id": source_attempt_id,
                "source_probe_manifest_path": probe_manifest_path,
                "source_attempt_manifest_path": source_manifest_path,
                "source_config_path": probe_root / "tester_config.ini",
                "source_manifest": source_manifest,
                "source_probe_manifest": probe_manifest,
                "run_id": candidate["run_id"],
                "bundle_id": candidate["bundle_id"],
                "from_date": str(period_identity.get("from_date") or ""),
                "to_date": str(period_identity.get("to_date") or ""),
                "period_profile_id": str(period_identity.get("period_profile_id") or "period_profile_split_set_v0"),
                "runtime_period_set_id": str(period_identity.get("runtime_period_set_id") or "split_base_anchor_v0_research_l4"),
            }
        )
    return plans


def prepare_l5_tester_config(
    *,
    source_config: Path,
    target_config: Path,
    attempt_id: str,
    hold_bars: int,
    magic_number: int,
    deviation_points: int,
) -> dict[str, Any]:
    target_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_config, target_config)
    with open(filesystem_path(target_config), "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    telemetry_common = f"{COMMON_L5_ROOT}\\{attempt_id}\\score_telemetry.csv"
    diagnostic_common = f"{COMMON_L5_ROOT}\\{attempt_id}\\score_diagnostics.csv"
    report_value = f"reports\\spacesonar\\{attempt_id}\\tester_report"
    text = l4_base.upsert_ini_line(text, "ReplaceReport", "1", after_key="Leverage")
    text = l4_base.upsert_ini_line(text, "Report", report_value, after_key="ReplaceReport")
    text = l4_base.upsert_ini_line(text, "ShutdownTerminal", "1", after_key="Report")
    text = l4_base.upsert_ini_line(text, "InpOutputPath", telemetry_common, after_key="InpFeatureColumnsPath")
    text = l4_base.upsert_ini_line(text, "InpDiagnosticPath", diagnostic_common, after_key="InpOutputPath")
    text = l4_base.upsert_ini_line(text, "InpExecuteTrades", "true", after_key="InpFixedLot")
    text = l4_base.upsert_ini_line(text, "InpHoldBars", str(hold_bars), after_key="InpExecuteTrades")
    text = l4_base.upsert_ini_line(text, "InpMagicNumber", str(magic_number), after_key="InpHoldBars")
    text = l4_base.upsert_ini_line(text, "InpDeviationPoints", str(deviation_points), after_key="InpMagicNumber")
    with open(filesystem_path(target_config), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    telemetry_path = l4_base.common_relative_to_path(telemetry_common)
    diagnostic_path = l4_base.common_relative_to_path(diagnostic_common)
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "tester_config": target_config,
        "report_value": report_value,
        "telemetry_common_relative": telemetry_common,
        "diagnostic_common_relative": diagnostic_common,
        "trade_inputs": {
            "InpExecuteTrades": True,
            "InpHoldBars": hold_bars,
            "InpMagicNumber": magic_number,
            "InpDeviationPoints": deviation_points,
            "InpFixedLot": "source_config_or_EA_default",
        },
        "config_artifact": artifact_ref(target_config),
    }


def build_initial_attempt_manifest(
    *,
    candidate: dict[str, Any],
    plan: dict[str, Any],
    config_summary: dict[str, Any],
    common_inputs: dict[str, Any],
    portable_root: Path,
    root_preflight: dict[str, Any],
    copy_result: dict[str, Any],
    created_at_utc: str,
) -> dict[str, Any]:
    source_manifest = copy.deepcopy(plan.get("source_manifest") or {})
    source_probe_manifest = copy.deepcopy(plan.get("source_probe_manifest") or {})
    attempt_id = plan["attempt_id"]
    attempt_manifest_path = Path("runtime") / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    runtime_contract = copy.deepcopy(
        source_manifest.get("runtime_surface_contract")
        or source_probe_manifest.get("runtime_surface_contract")
        or {}
    )
    runtime_contract.update(
        {
            "runtime_surface_kind": "decision_execution",
            "decision_output": "score_threshold_trade_execution_enabled",
            "trade_execution_adapter": "SpaceSonar_ONNX_L4_ScoreProbe_InpExecuteTrades_true",
            "score_probe_telemetry_still_written": True,
            "completion_surface_scope": "full_period_deterministic",
            "locked_final_oos_b_used": False,
        }
    )
    period_identity = copy.deepcopy(source_manifest.get("period_identity") or source_probe_manifest.get("period_identity") or {})
    execution_identity = copy.deepcopy(
        source_manifest.get("execution_identity")
        or source_probe_manifest.get("execution_identity")
        or {}
    )
    if not execution_identity:
        execution_identity = {"execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0"}
    tester_identity = copy.deepcopy(source_manifest.get("tester_identity") or {})
    telemetry_common = config_summary["telemetry_common_relative"]
    manifest = {
        "version": "wave03_l5_candidate_runtime_attempt_manifest_v1",
        "attempt_id": attempt_id,
        "source_attempt_id": plan["source_probe_attempt_id"],
        "l4_source_attempt_id": plan["source_attempt_id"],
        "candidate_id": candidate["candidate_id"],
        "run_id": plan["run_id"],
        "bundle_id": plan["bundle_id"],
        "cell_id": plan["cell_id"],
        "period_role": plan["period_role"],
        "active_goal_id": GOAL_ID,
        "work_item_id": WORK_ITEM_ID,
        "campaign_id": CAMPAIGN_ID,
        "created_at_utc": created_at_utc,
        "status": "l5_decision_execution_attempt_prepared",
        "tester_config": config_summary["config_artifact"],
        "period_identity": period_identity,
        "execution_identity": execution_identity,
        "tester_identity": tester_identity,
        "runtime_surface_contract": runtime_contract,
        "decision_execution_adapter": {
            "status": "materialized_in_local_ea_binary",
            "ea_source": artifact_ref(REPO_ROOT / l4_base.EA_SOURCE),
            "ea_binary": artifact_ref(REPO_ROOT / l4_base.EA_BINARY, availability="local_binary_hash_recorded_ignored_by_git")
            if path_exists(REPO_ROOT / l4_base.EA_BINARY)
            else {"path": l4_base.EA_BINARY.as_posix(), "availability": "missing_binary_compile_required"},
            "trade_inputs": config_summary["trade_inputs"],
            "claim_boundary": "adapter_materialized_for_l5_probe_only_no_runtime_authority",
        },
        "portable_runtime_preflight": {
            "portable_root_redacted": redact_path(str(portable_root)),
            "portable_root_copy": copy_result,
            "root_preflight": root_preflight,
            "common_file_inputs": common_inputs,
            "claim_boundary": "portable_preflight_only_no_runtime_authority",
        },
        "artifact_identity": {
            "tester_config": config_summary["config_artifact"],
            "telemetry": {
                "common_relative_path": telemetry_common,
                "redacted_absolute_path": "${MT5_COMMONDATA}\\Files\\" + telemetry_common,
                "durable_identity": "common_relative_path_plus_l5_attempt_id",
                "path_boundary": "redacted_local_context_only",
            },
        },
        "missing_evidence": ["l5_decision_execution_strategy_tester_not_yet_run"],
        "next_action": "launch no-fallback portable MT5 Strategy Tester for this L5 decision-execution attempt",
    }
    manifest.update(
        contract_fields(
            progress_effect="wave03_l5_decision_execution_attempt_manifest_prepared",
            next_action=manifest["next_action"],
            experiment_effect="candidate_specific_l5_decision_execution_attempt_prepared_without_protected_claim",
            claim_boundary=INCOMPLETE_CLAIM_BOUNDARY,
            source_paths=[
                candidate_summary_path(candidate["candidate_id"]).as_posix(),
                rel(plan["source_probe_manifest_path"]),
                rel(plan["source_attempt_manifest_path"]),
            ],
            outputs=[attempt_manifest_path.as_posix()],
            blockers=["l5_decision_execution_strategy_tester_pending"],
        )
    )
    return manifest


def prep_row(plan: dict[str, Any]) -> dict[str, str]:
    attempt_id = plan["attempt_id"]
    return {
        "attempt_id": attempt_id,
        "run_id": plan["run_id"],
        "bundle_id": plan["bundle_id"],
        "cell_id": plan["cell_id"],
        "period_role": plan["period_role"],
        "from_date": plan.get("from_date", ""),
        "to_date": plan.get("to_date", ""),
        "period_profile_id": plan.get("period_profile_id", "period_profile_split_set_v0"),
        "runtime_period_set_id": plan.get("runtime_period_set_id", "split_base_anchor_v0_research_l4"),
        "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
        "completion_surface_scope": "full_period_deterministic",
        "attempt_manifest_path": (Path("runtime") / "mt5_attempts" / attempt_id / "attempt_manifest.yaml").as_posix(),
        "tester_config_path": (Path("runtime") / "mt5_attempts" / attempt_id / "tester_config.ini").as_posix(),
    }


def tester_report_path(attempt_id: str) -> Path:
    return REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "reports" / "tester_report.htm"


def parse_attempt_report(attempt_id: str, *, write_summary: bool) -> dict[str, Any]:
    report = tester_report_path(attempt_id)
    parsed = parse_tester_report_kpis(report)
    parsed["source_report_path"] = rel(report) if path_exists(report) else report.as_posix()
    if write_summary:
        summary_path = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "tester_report_kpi_summary.yaml"
        write_plain_yaml(summary_path, parsed)
    return parsed


def period_judgment(parsed: dict[str, Any], row: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    reasons: list[str] = []
    total_net_profit = metric_value(parsed, "mt5.tester_report.total_net_profit")
    profit_factor = metric_value(parsed, "mt5.tester_report.profit_factor")
    dd_pct = metric_value(parsed, "mt5.tester_report.balance_drawdown_maximal_pct")
    total_trades = safe_int(metric_value(parsed, "mt5.tester_report.total_trades"))
    days = date_days(str(row.get("from_date") or ""), str(row.get("to_date") or ""))
    trades_per_day = (total_trades / days) if days else None
    critical_missing = [
        metric_id
        for metric_id in [
            "mt5.tester_report.total_net_profit",
            "mt5.tester_report.profit_factor",
            "mt5.tester_report.total_trades",
            "mt5.tester_report.balance_drawdown_maximal_pct",
        ]
        if metric_id in (parsed.get("missing_metrics") or [])
    ]
    if parsed.get("parse_status") != "parsed":
        reasons.append("tester_report_kpi_parse_failed")
    if critical_missing:
        reasons.append("critical_tester_report_metrics_missing")
    if total_trades <= 0:
        reasons.append("zero_or_missing_total_trades")
    if total_net_profit is None or total_net_profit <= 0:
        reasons.append("non_positive_total_net_profit")
    if profit_factor is None or profit_factor < 1.0:
        reasons.append("profit_factor_below_1")
    if dd_pct is None or dd_pct > 10.0:
        reasons.append("drawdown_above_10pct_reference")
    reference_flags = {
        "profit_factor_between_1_5_and_3_0": profit_factor is not None and 1.5 <= profit_factor <= 3.0,
        "trades_per_day_at_least_5": trades_per_day is not None and trades_per_day >= 5.0,
        "drawdown_at_or_below_10pct": dd_pct is not None and dd_pct <= 10.0,
        "positive_net_profit": total_net_profit is not None and total_net_profit > 0,
    }
    if reasons:
        return "negative_l5_runtime_evidence", reasons, {
            "days": days,
            "trades_per_day": trades_per_day,
            "operational_review_reference_flags": reference_flags,
            "operational_review_reference_observed": False,
        }
    return "positive_l5_runtime_observation_not_economics_pass", ["stronger_claim_requires_final_claim_guard"], {
        "days": days,
        "trades_per_day": trades_per_day,
        "operational_review_reference_flags": reference_flags,
        "operational_review_reference_observed": all(reference_flags.values()),
    }


def build_period_row(candidate: dict[str, Any], row: dict[str, Any], *, write_parse_summaries: bool) -> dict[str, Any]:
    attempt_id = str(row["attempt_id"])
    parsed = parse_attempt_report(attempt_id, write_summary=write_parse_summaries)
    judgment, reasons, reference = period_judgment(parsed, row)
    terminal_summary_path = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "terminal_run_summary.yaml"
    manifest_path = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    manifest = read_yaml(manifest_path) if path_exists(manifest_path) else {}
    execution_state = manifest.get("execution_state") or {}
    return {
        "candidate_id": candidate["candidate_id"],
        "run_id": candidate["run_id"],
        "bundle_id": candidate["bundle_id"],
        "cell_id": candidate["source_cell_id"],
        "period_role": row["period_role"],
        "attempt_id": attempt_id,
        "from_date": row.get("from_date", ""),
        "to_date": row.get("to_date", ""),
        "terminal_mode": execution_state.get("terminal_mode", row.get("terminal_mode", "")),
        "runtime_probe_complete": bool(execution_state.get("runtime_probe_complete")),
        "telemetry_observed": bool(execution_state.get("telemetry_rows_observed")),
        "tester_report_observed": bool(execution_state.get("tester_report_observed")),
        "tester_report_completed": bool(execution_state.get("tester_report_completed")),
        "report_parse_status": parsed.get("parse_status", ""),
        "missing_metric_count": len(parsed.get("missing_metrics") or []),
        "total_net_profit": metric_value(parsed, "mt5.tester_report.total_net_profit"),
        "gross_profit": metric_value(parsed, "mt5.tester_report.gross_profit"),
        "gross_loss": metric_value(parsed, "mt5.tester_report.gross_loss"),
        "profit_factor": metric_value(parsed, "mt5.tester_report.profit_factor"),
        "total_trades": safe_int(metric_value(parsed, "mt5.tester_report.total_trades")),
        "trades_per_day": reference["trades_per_day"],
        "balance_drawdown_maximal_pct": metric_value(parsed, "mt5.tester_report.balance_drawdown_maximal_pct"),
        "equity_drawdown_maximal_pct": metric_value(parsed, "mt5.tester_report.equity_drawdown_maximal_pct"),
        "period_judgment": judgment,
        "judgment_reasons": "|".join(reasons),
        "operational_review_reference_observed": reference["operational_review_reference_observed"],
        "operational_review_reference_flags": reference["operational_review_reference_flags"],
        "tester_report_kpi_summary_path": (
            Path("runtime") / "mt5_attempts" / attempt_id / "tester_report_kpi_summary.yaml"
        ).as_posix(),
        "terminal_run_summary_path": rel(terminal_summary_path) if path_exists(terminal_summary_path) else "",
        "tester_report_path": rel(tester_report_path(attempt_id)) if path_exists(tester_report_path(attempt_id)) else "",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def finalize_attempt_manifest(candidate: dict[str, Any], evidence_row: dict[str, Any]) -> None:
    attempt_id = evidence_row["attempt_id"]
    manifest_path = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    manifest = read_yaml(manifest_path)
    result = evidence_row["period_judgment"]
    missing: list[str] = []
    if not evidence_row["telemetry_observed"]:
        missing.append("l5_score_telemetry_rows_missing")
    if not evidence_row["tester_report_observed"]:
        missing.append("l5_tester_report_missing")
    if not evidence_row["tester_report_completed"]:
        missing.append("l5_tester_report_not_completed")
    if evidence_row["report_parse_status"] != "parsed":
        missing.append("l5_tester_report_kpi_parse_failed")
    if result == "negative_l5_runtime_evidence":
        missing.append("positive_candidate_specific_l5_evidence_not_observed")
    next_action = NEXT_ACTION if not missing else REPAIR_NEXT_ACTION
    claim_boundary = CLAIM_BOUNDARY if not missing else INCOMPLETE_CLAIM_BOUNDARY
    manifest.update(
        {
            "version": "wave03_l5_candidate_runtime_attempt_manifest_v1",
            "candidate_id": candidate["candidate_id"],
            "work_item_id": WORK_ITEM_ID,
            "status": result,
            "l5_runtime_evidence_row": evidence_row,
            "claim_boundary": claim_boundary,
            "missing_evidence": missing or ["none"],
            "next_action": next_action,
        }
    )
    runtime_contract = manifest.setdefault("runtime_surface_contract", {})
    runtime_contract.update(
        {
            "runtime_surface_kind": "decision_execution",
            "decision_output": "score_threshold_trade_execution_enabled",
            "trade_execution_adapter": "SpaceSonar_ONNX_L4_ScoreProbe_InpExecuteTrades_true",
            "score_probe_telemetry_still_written": True,
            "locked_final_oos_b_used": False,
        }
    )
    manifest.update(
        contract_fields(
            progress_effect="wave03_l5_decision_execution_attempt_evidence_recorded",
            next_action=next_action,
            experiment_effect="candidate_specific_l5_runtime_evidence_recorded_without_protected_claim",
            claim_boundary=claim_boundary,
            source_paths=[
                candidate_summary_path(candidate["candidate_id"]).as_posix(),
                rel(manifest_path),
                evidence_row["tester_report_kpi_summary_path"],
            ],
            outputs=[rel(manifest_path)],
            blockers=missing or ["none"],
        )
    )
    write_yaml(Path(rel(manifest_path)), manifest)


def candidate_result(rows: list[dict[str, Any]]) -> tuple[str, list[str], bool]:
    if not rows or len(rows) < 2:
        return "incomplete_l5_runtime_evidence_repair_pending", ["both_validation_and_research_oos_required"], False
    incomplete = [
        row
        for row in rows
        if not row["telemetry_observed"] or not row["tester_report_observed"] or row["report_parse_status"] != "parsed"
    ]
    if incomplete:
        return "incomplete_l5_runtime_evidence_repair_pending", ["candidate_period_runtime_or_kpi_evidence_incomplete"], False
    negative_reasons: list[str] = []
    for row in rows:
        if row["period_judgment"] == "negative_l5_runtime_evidence":
            negative_reasons.extend(str(row["judgment_reasons"]).split("|"))
    if negative_reasons:
        return "negative_l5_runtime_evidence_no_l5_candidate", sorted({reason for reason in negative_reasons if reason}), False
    operational_reference = all(bool(row.get("operational_review_reference_observed")) for row in rows)
    if operational_reference:
        return "operational_review_reference_observed_final_claim_guard_pending", ["final_claim_guard_required"], True
    return "positive_l5_runtime_observation_not_economics_pass", ["north_star_reference_not_fully_met_or_final_claim_guard_required"], False


def evidence_index_fieldnames() -> list[str]:
    return [
        "candidate_id",
        "run_id",
        "bundle_id",
        "cell_id",
        "period_role",
        "attempt_id",
        "from_date",
        "to_date",
        "terminal_mode",
        "runtime_probe_complete",
        "telemetry_observed",
        "tester_report_observed",
        "tester_report_completed",
        "report_parse_status",
        "missing_metric_count",
        "total_net_profit",
        "gross_profit",
        "gross_loss",
        "profit_factor",
        "total_trades",
        "trades_per_day",
        "balance_drawdown_maximal_pct",
        "equity_drawdown_maximal_pct",
        "period_judgment",
        "judgment_reasons",
        "operational_review_reference_observed",
        "tester_report_kpi_summary_path",
        "terminal_run_summary_path",
        "tester_report_path",
        "claim_boundary",
    ]


def build_candidate_evidence_summary(
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
    ended_at_utc: str,
    command_argv: list[str],
) -> dict[str, Any]:
    result, reasons, operational_reference = candidate_result(rows)
    claim_boundary = CLAIM_BOUNDARY if not result.startswith("incomplete") else INCOMPLETE_CLAIM_BOUNDARY
    missing = ["locked_final_oos_b_not_used", "final_claim_guard_not_run"]
    if result.startswith("negative"):
        missing.append("positive_candidate_specific_l5_runtime_evidence_not_observed")
    if result.startswith("incomplete"):
        missing.append("complete_candidate_specific_l5_runtime_evidence_not_observed")
    payload = {
        "version": "candidate_l5_runtime_evidence_summary_v1",
        "candidate_id": candidate["candidate_id"],
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "created_at_utc": ended_at_utc,
        "status": result,
        "period_rows": rows,
        "result_judgment": "runtime_probe" if not result.startswith("negative") else "negative",
        "operational_review_reference_observed": operational_reference,
        "l5_candidate": False,
        "economics_pass": False,
        "runtime_authority": False,
        "selected_baseline": False,
        "live_readiness": False,
        "goal_achieve": False,
        "judgment_reasons": reasons,
        "missing_evidence": missing,
        "source_evidence": {
            "candidate_summary": candidate_summary_path(candidate["candidate_id"]).as_posix(),
            "routing_summary": ROUTING_SUMMARY.as_posix(),
            "routing_index": ROUTING_INDEX.as_posix(),
            "campaign_l5_runtime_evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "campaign_l5_runtime_evidence_index": EVIDENCE_INDEX.as_posix(),
        },
        "provenance": {
            "source_inputs": [
                candidate_summary_path(candidate["candidate_id"]).as_posix(),
                ROUTING_SUMMARY.as_posix(),
                ROUTING_INDEX.as_posix(),
                *[row["terminal_run_summary_path"] for row in rows if row.get("terminal_run_summary_path")],
                *[row["tester_report_kpi_summary_path"] for row in rows],
            ],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [candidate_evidence_path(candidate["candidate_id"]).as_posix()],
            "source_of_truth_paths": [candidate_evidence_path(candidate["candidate_id"]).as_posix()],
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "candidate_l5_runtime_evidence_written_from_candidate_manifest_and_decision_execution_strategy_tester_attempts",
            "claim_boundary": claim_boundary,
        },
        "next_action": FINAL_GUARD_NEXT_ACTION if operational_reference else NEXT_ACTION,
        "forbidden_claims_respected": True,
    }
    payload.update(
        contract_fields(
            progress_effect="wave03_l5_candidate_runtime_evidence_recorded",
            next_action=payload["next_action"],
            experiment_effect="candidate_specific_l5_runtime_evidence_recorded_without_protected_claim",
            claim_boundary=claim_boundary,
            source_paths=[
                candidate_summary_path(candidate["candidate_id"]).as_posix(),
                EVIDENCE_INDEX.as_posix(),
            ],
            outputs=[candidate_evidence_path(candidate["candidate_id"]).as_posix()],
            blockers=["final_claim_guard_not_run"] if not result.startswith("incomplete") else ["l5_runtime_evidence_incomplete"],
        )
    )
    return payload


def build_summary(
    *,
    candidates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    by_candidate: dict[str, list[dict[str, Any]]],
    started_at_utc: str,
    command_argv: list[str],
    copy_result: dict[str, Any],
    root_preflight: dict[str, Any],
    skip_terminal_probe: bool,
) -> dict[str, Any]:
    ended_at = utc_now()
    candidate_results = {
        candidate["candidate_id"]: candidate_result(by_candidate.get(candidate["candidate_id"], []))[0]
        for candidate in candidates
    }
    operational_reference_ids = [
        candidate_id
        for candidate_id, candidate_rows in by_candidate.items()
        if candidate_result(candidate_rows)[2]
    ]
    incomplete_ids = [candidate_id for candidate_id, result in candidate_results.items() if result.startswith("incomplete")]
    negative_ids = [candidate_id for candidate_id, result in candidate_results.items() if result.startswith("negative")]
    period_counts = Counter(str(row["period_judgment"]) for row in rows)
    candidate_counts = Counter(candidate_results.values())
    if incomplete_ids:
        status = INCOMPLETE_STATUS
        claim_boundary = INCOMPLETE_CLAIM_BOUNDARY
        next_action = REPAIR_NEXT_ACTION
        next_work_id = WORK_ITEM_ID
        unresolved = ["wave03_candidate_specific_l5_decision_execution_runtime_evidence_incomplete"]
    elif operational_reference_ids:
        status = FINAL_GUARD_STATUS
        claim_boundary = FINAL_GUARD_CLAIM_BOUNDARY
        next_action = FINAL_GUARD_NEXT_ACTION
        next_work_id = FINAL_GUARD_WORK_ITEM_ID
        unresolved = ["wave03_l5_final_claim_guard_pending"]
    else:
        status = STATUS
        claim_boundary = CLAIM_BOUNDARY
        next_action = NEXT_ACTION
        next_work_id = NEXT_WORK_ITEM_ID
        unresolved = ["wave03_l5_candidate_boundary_decision_pending"]
    summary = {
        "version": "wave03_l5_candidate_runtime_evidence_summary_v1",
        "summary_id": "wave03_l5_candidate_runtime_evidence_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": next_work_id,
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
            "artifact_id": "artifact_wave03_l5_candidate_runtime_evidence_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at,
        "status": status,
        "claim_boundary": claim_boundary,
        "support_skills": [
            "spacesonar-runtime-evidence",
            "spacesonar-evidence-provenance",
            "spacesonar-performance-attribution",
            "spacesonar-claim-discipline",
        ],
        "counts": {
            "candidate_count": len(candidates),
            "candidate_runtime_evidence_count": len(by_candidate),
            "l5_candidate_count": 0,
            "period_evidence_row_count": len(rows),
            "runtime_probe_complete_period_count": sum(bool(row.get("runtime_probe_complete")) for row in rows),
            "telemetry_observed_period_count": sum(bool(row.get("telemetry_observed")) for row in rows),
            "tester_report_completed_period_count": sum(bool(row.get("tester_report_completed")) for row in rows),
            "negative_candidate_count": len(negative_ids),
            "incomplete_candidate_count": len(incomplete_ids),
            "operational_review_reference_observed_count": len(operational_reference_ids),
            "period_judgment_counts": dict(sorted(period_counts.items())),
            "candidate_result_counts": dict(sorted(candidate_counts.items())),
        },
        "candidate_results": candidate_results,
        "negative_candidate_ids": negative_ids,
        "incomplete_candidate_ids": incomplete_ids,
        "operational_review_reference_observed_ids": operational_reference_ids,
        "l5_candidate_ids": [],
        "period_rows": rows,
        "runtime_probe_environment": {
            "portable_root_copy": copy_result,
            "portable_root_preflight": root_preflight,
            "terminal_mode": "portable_required_no_main_mode_fallback",
            "skip_terminal_probe": skip_terminal_probe,
            "claim_boundary": "runtime_environment_observation_only_no_runtime_authority",
        },
        "judgment": {
            "judgment_label": status,
            "candidate_count": len(candidates),
            "l5_candidate_count": 0,
            "economics_metrics_observed": bool(rows),
            "operational_review_reference_observed": bool(operational_reference_ids),
            "economics_pass": False,
            "runtime_authority": False,
            "selected_baseline": False,
            "live_readiness": False,
            "goal_achieve": False,
            "claim_boundary": claim_boundary,
            "missing_evidence": [
                "final_claim_guard_not_run",
                "locked_final_oos_b_not_used",
                "operational_validation_not_started",
                "no_selected_baseline_or_runtime_authority_from_l5_runtime_evidence",
            ],
            "next_action": next_action,
        },
        "provenance": {
            "source_inputs": [
                ROUTING_SUMMARY.as_posix(),
                ROUTING_INDEX.as_posix(),
                CANDIDATE_REGISTRY.as_posix(),
                "foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5",
                "foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5",
            ],
            "producer": " ".join(command_argv),
            "consumer": next_work_id,
            "artifact_paths": [
                EVIDENCE_SUMMARY.as_posix(),
                EVIDENCE_INDEX.as_posix(),
                EVIDENCE_CLOSEOUT.as_posix(),
                *[candidate_evidence_path(candidate["candidate_id"]).as_posix() for candidate in candidates],
            ],
            "source_of_truth_paths": [
                EVIDENCE_SUMMARY.as_posix(),
                EVIDENCE_INDEX.as_posix(),
                EVIDENCE_CLOSEOUT.as_posix(),
            ],
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [ARTIFACT_REGISTRY.as_posix(), CANDIDATE_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "candidate_l5_runtime_evidence_written_from_opened_candidate_manifest_and_no_fallback_portable_mt5_attempts",
            "claim_boundary": claim_boundary,
        },
        "artifact_outputs": {
            "evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "evidence_index": EVIDENCE_INDEX.as_posix(),
            "evidence_closeout": EVIDENCE_CLOSEOUT.as_posix(),
            "candidate_evidence_summaries": [
                candidate_evidence_path(candidate["candidate_id"]).as_posix() for candidate in candidates
            ],
        },
        "prevention_memory": [
            "Candidate-specific L5 tester report metrics do not create runtime authority or economics pass by themselves.",
            "L5 candidate count remains zero until a final claim guard explicitly accepts the candidate boundary.",
            "Locked final OOS remains excluded by default.",
        ],
        "unresolved_blockers": unresolved,
        "reopen_conditions": [
            "rerun L5 runtime evidence if candidate manifest, EA adapter, tester report parser, or L4 source attempt ids change",
            "repair or rerun L5 attempts when either validation or research_oos runtime/report evidence is incomplete",
            "do not claim runtime authority, economics pass, live readiness, or Goal Achieve without final claim guard evidence",
        ],
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    summary.update(
        contract_fields(
            progress_effect="wave03_l5_candidate_runtime_evidence_recorded",
            next_action=next_action,
            experiment_effect="candidate_specific_l5_decision_execution_runtime_evidence_recorded_without_protected_claim",
            claim_boundary=claim_boundary,
            source_paths=[ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), CANDIDATE_REGISTRY.as_posix()],
            outputs=[EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), EVIDENCE_CLOSEOUT.as_posix()],
            blockers=unresolved,
        )
    )
    return summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": summary["next_work_item_id"],
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "support_skills": summary["support_skills"],
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [
            EVIDENCE_SUMMARY.as_posix(),
            EVIDENCE_INDEX.as_posix(),
            *summary["artifact_outputs"]["candidate_evidence_summaries"],
        ],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "forbidden_claims": summary["forbidden_claims"],
        "required_gate_coverage": {
            "passed": [
                "opened_candidate_manifest_present",
                "decision_execution_adapter_materialized",
                "portable_no_fallback_attempt_manifest_written",
                "tester_report_kpi_parse_attempted",
                "final_claim_guard_deferred",
                "writer_scope_self_check",
            ],
            "missing": summary["judgment"]["missing_evidence"],
            "not_applicable": [
                "selected_baseline",
                "runtime_authority",
                "economics_pass",
                "goal_achieve",
                "live_readiness",
            ],
        },
    }
    payload.update(
        contract_fields(
            progress_effect="wave03_l5_candidate_runtime_evidence_closeout_recorded",
            next_action=summary["judgment"]["next_action"],
            experiment_effect="l5_candidate_runtime_evidence_work_closed_to_next_executable_boundary_without_protected_claim",
            claim_boundary=summary["claim_boundary"],
            source_paths=[EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix()],
            outputs=[EVIDENCE_CLOSEOUT.as_posix()],
            blockers=summary["unresolved_blockers"],
        )
    )
    return payload


def next_work_record(summary: dict[str, Any]) -> dict[str, Any]:
    next_work_id = summary["next_work_item_id"]
    if next_work_id == FINAL_GUARD_WORK_ITEM_ID:
        claim_boundary = FINAL_GUARD_CLAIM_BOUNDARY
    elif next_work_id == WORK_ITEM_ID:
        claim_boundary = INCOMPLETE_CLAIM_BOUNDARY
    else:
        claim_boundary = NEXT_CLAIM_BOUNDARY
    next_action = summary["judgment"]["next_action"]
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": next_work_id,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "candidate_evaluation" if next_work_id != WORK_ITEM_ID else PRIMARY_FAMILY,
        "primary_skill": "spacesonar-result-judgment" if next_work_id != WORK_ITEM_ID else PRIMARY_SKILL,
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-performance-attribution", "spacesonar-claim-discipline"],
        "verification_profile": "wave03_l5_candidate_boundary_decision",
        "targets": [
            EVIDENCE_SUMMARY.as_posix(),
            EVIDENCE_INDEX.as_posix(),
            *summary["artifact_outputs"]["candidate_evidence_summaries"],
        ],
        "acceptance_criteria": [
            "use candidate-specific L5 decision-execution evidence only",
            "do not turn L5 tester report metrics into runtime authority or economics pass without final claim guard",
            "keep locked final OOS excluded unless an explicit unlock contract exists",
        ],
        "status": summary["status"],
        "claim_boundary": claim_boundary,
        "current_truth": {
            "l5_runtime_evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "l5_runtime_evidence_index": EVIDENCE_INDEX.as_posix(),
            "candidate_results": summary["candidate_results"],
            "l5_candidate_count": 0,
            "operational_review_reference_observed_ids": summary["operational_review_reference_observed_ids"],
        },
        "outputs": ["lab/candidates/<candidate_id>/candidate_summary.yaml"],
        "operational_validation_required": False,
        "next_action": next_action,
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "unresolved_blockers_or_none": list(summary["unresolved_blockers"]),
        "reopen_conditions": list(summary["reopen_conditions"]),
    }
    payload.update(
        contract_fields(
            primary_family=payload["primary_family"],
            primary_skill=payload["primary_skill"],
            progress_effect="wave03_l5_candidate_runtime_evidence_routed_to_next_boundary",
            next_action=next_action,
            experiment_effect="l5_runtime_evidence_boundary_decision_pending_without_protected_claim",
            claim_boundary=claim_boundary,
            source_paths=[EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[NEXT_WORK_ITEM.as_posix()],
            blockers=summary["unresolved_blockers"],
        )
    )
    return payload


def update_candidate_summary(candidate: dict[str, Any], candidate_rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    candidate_id = candidate["candidate_id"]
    result, reasons, operational_reference = candidate_result(candidate_rows)
    claim_boundary = CLAIM_BOUNDARY if not result.startswith("incomplete") else INCOMPLETE_CLAIM_BOUNDARY
    candidate["status"] = result
    candidate["claim_boundary"] = claim_boundary
    scope = candidate.setdefault("candidate_scope", {})
    scope.update(
        {
            "meaning": "candidate-specific L5 runtime evidence target with decision-execution observation",
            "selected_baseline": False,
            "runtime_authority": False,
            "economics_pass": False,
            "l5_candidate": False,
            "live_readiness": False,
            "goal_achieve": False,
        }
    )
    candidate["l5_runtime_evidence_summary"] = candidate_evidence_path(candidate_id).as_posix()
    candidate["runtime_evidence_result"] = {
        "result_judgment": "runtime_probe" if not result.startswith("negative") else "negative",
        "candidate_result": result,
        "operational_review_reference_observed": operational_reference,
        "l5_candidate": False,
        "economics_pass": False,
        "runtime_authority": False,
        "selected_baseline": False,
        "live_readiness": False,
        "goal_achieve": False,
        "judgment_reasons": reasons,
        "period_rows": candidate_rows,
    }
    candidate["missing_evidence"] = summary["judgment"]["missing_evidence"]
    candidate["next_action"] = summary["judgment"]["next_action"]
    candidate.update(
        contract_fields(
            progress_effect="wave03_l5_candidate_summary_runtime_evidence_updated",
            next_action=summary["judgment"]["next_action"],
            experiment_effect="candidate_summary_reflects_l5_runtime_evidence_without_protected_claim",
            claim_boundary=claim_boundary,
            source_paths=[
                candidate_summary_path(candidate_id).as_posix(),
                candidate_evidence_path(candidate_id).as_posix(),
                EVIDENCE_SUMMARY.as_posix(),
                EVIDENCE_INDEX.as_posix(),
            ],
            outputs=[candidate_summary_path(candidate_id).as_posix()],
            blockers=summary["unresolved_blockers"],
        )
    )
    write_yaml(candidate_summary_path(candidate_id), candidate)


def upsert_candidate_registry(summary: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    if not path_exists(REPO_ROOT / CANDIDATE_REGISTRY):
        return
    rows = read_csv_rows(REPO_ROOT / CANDIDATE_REGISTRY)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    by_id = {row.get("candidate_id"): row for row in rows if row.get("candidate_id")}
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        row = by_id.get(candidate_id, {key: "" for key in fieldnames})
        row.update(
            {
                "candidate_id": candidate_id,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "run_id": candidate.get("run_id", ""),
                "bundle_id": candidate.get("bundle_id", ""),
                "surface_id": SURFACE_ID,
                "status": candidate.get("status", ""),
                "summary_path": candidate_summary_path(candidate_id).as_posix(),
                "claim_boundary": candidate.get("claim_boundary", ""),
                "evidence_path": candidate_evidence_path(candidate_id).as_posix(),
                "missing_evidence": ";".join(summary["judgment"]["missing_evidence"]),
                "risk_notes": "l5_decision_execution_evidence_only_no_runtime_authority_no_economics_pass",
                "next_action": summary["judgment"]["next_action"],
            }
        )
        by_id[candidate_id] = row
    write_csv(CANDIDATE_REGISTRY, list(by_id.values()), fieldnames)


def upsert_artifact_registry(summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    if not path_exists(REPO_ROOT / ARTIFACT_REGISTRY):
        return
    registry_rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    if not registry_rows:
        return
    fieldnames = list(registry_rows[0].keys())
    by_id = {row.get("artifact_id"): row for row in registry_rows if row.get("artifact_id")}
    producer = (summary.get("provenance") or {}).get("producer", "")
    regen = producer

    def put(row: dict[str, Any]) -> None:
        payload = {key: "" for key in fieldnames}
        payload.update(row)
        by_id[str(payload["artifact_id"])] = payload

    for path, artifact_type, artifact_id in [
        (EVIDENCE_SUMMARY, "l5_runtime_evidence_summary", "artifact_wave03_l5_runtime_evidence_summary_v0"),
        (EVIDENCE_INDEX, "l5_runtime_evidence_index", "artifact_wave03_l5_runtime_evidence_index_v0"),
        (EVIDENCE_CLOSEOUT, "work_closeout", "artifact_wave03_l5_runtime_evidence_closeout_v0"),
    ]:
        full = REPO_ROOT / path
        if path_exists(full):
            put(
                {
                    "artifact_id": artifact_id,
                    "run_id": "",
                    "bundle_id": "",
                    "attempt_id": "",
                    "artifact_type": artifact_type,
                    "path_or_uri": path.as_posix(),
                    "sha256": sha256_file(full),
                    "size_bytes": full.stat().st_size,
                    "availability": "present_hash_recorded",
                    "producer_command": producer,
                    "regeneration_command": regen,
                    "source_of_truth": path.as_posix(),
                    "consumer": summary["next_work_item_id"],
                    "claim_boundary": summary["claim_boundary"],
                    "notes": "Wave03 L5 candidate runtime evidence control artifact",
                }
            )
    for row in rows:
        attempt_id = row["attempt_id"]
        for suffix, artifact_type, source in [
            ("attempt_manifest.yaml", "l5_attempt_manifest", "attempt_manifest.yaml"),
            ("tester_report_kpi_summary.yaml", "tester_report_kpi_summary", "tester_report_kpi_summary.yaml"),
            ("terminal_run_summary.yaml", "terminal_run_summary", "terminal_run_summary.yaml"),
        ]:
            rel_path = Path("runtime") / "mt5_attempts" / attempt_id / suffix
            full = REPO_ROOT / rel_path
            if not path_exists(full):
                continue
            put(
                {
                    "artifact_id": f"artifact_{attempt_id}_{artifact_type}_v0",
                    "run_id": row.get("run_id", ""),
                    "bundle_id": row.get("bundle_id", ""),
                    "attempt_id": attempt_id,
                    "artifact_type": artifact_type,
                    "path_or_uri": rel_path.as_posix(),
                    "sha256": sha256_file(full),
                    "size_bytes": full.stat().st_size,
                    "availability": "present_hash_recorded",
                    "producer_command": producer,
                    "regeneration_command": regen,
                    "source_of_truth": (Path("runtime") / "mt5_attempts" / attempt_id / source).as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row.get("claim_boundary", summary["claim_boundary"]),
                    "notes": "Wave03 L5 candidate runtime evidence attempt artifact",
                }
            )
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def next_claim_boundary_for_summary(summary: dict[str, Any]) -> str:
    next_work_id = summary["next_work_item_id"]
    if next_work_id == FINAL_GUARD_WORK_ITEM_ID:
        return FINAL_GUARD_CLAIM_BOUNDARY
    if next_work_id == WORK_ITEM_ID:
        return INCOMPLETE_CLAIM_BOUNDARY
    return NEXT_CLAIM_BOUNDARY


def update_goal_campaign_registries(summary: dict[str, Any]) -> None:
    next_claim_boundary = next_claim_boundary_for_summary(summary)
    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                if "status" in row:
                    row["status"] = summary["status"]
                if "active_phase" in row:
                    row["active_phase"] = summary["status"]
                if "next_work_item" in row:
                    row["next_work_item"] = summary["next_work_item_id"]
                if "claim_boundary" in row:
                    row["claim_boundary"] = next_claim_boundary
                if "notes" in row:
                    row["notes"] = "Wave03 L5 candidate runtime evidence observed; protected claims remain forbidden."
        if rows:
            write_csv(GOAL_REGISTRY, rows, list(rows[0].keys()))
    if path_exists(REPO_ROOT / CAMPAIGN_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / CAMPAIGN_REGISTRY)
        for row in rows:
            if row.get("campaign_id") == CAMPAIGN_ID:
                if "status" in row:
                    row["status"] = summary["status"]
                if "next_work_item" in row:
                    row["next_work_item"] = summary["next_work_item_id"]
                if "claim_boundary" in row:
                    row["claim_boundary"] = next_claim_boundary
                if "evidence_path" in row:
                    row["evidence_path"] = EVIDENCE_SUMMARY.as_posix()
                if "notes" in row:
                    row["notes"] = "Wave03 L5 decision-execution runtime evidence observed; no runtime authority or economics pass."
        if rows:
            write_csv(CAMPAIGN_REGISTRY, rows, list(rows[0].keys()))


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_record(summary)
    write_yaml(NEXT_WORK_ITEM, next_work)
    next_claim_boundary = next_work["claim_boundary"]
    next_action = summary["judgment"]["next_action"]
    common_contract = contract_fields(
        primary_family=next_work["primary_family"],
        primary_skill=next_work["primary_skill"],
        progress_effect="wave03_l5_candidate_runtime_evidence_routed_to_next_boundary",
        next_action=next_action,
        experiment_effect="l5_runtime_evidence_boundary_decision_pending_without_protected_claim",
        claim_boundary=next_claim_boundary,
        source_paths=[EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), NEXT_WORK_ITEM.as_posix()],
        outputs=[NEXT_WORK_ITEM.as_posix()],
        blockers=summary["unresolved_blockers"],
    )

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "cursor_state": summary["status"],
            "active_phase": summary["status"],
            "active_goal_id": GOAL_ID,
            "active_work_item_id": summary["next_work_item_id"],
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": next_claim_boundary,
            "next_action": next_action,
            "unresolved_blockers": list(summary["unresolved_blockers"]),
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
                "evidence_paths": [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": summary["next_work_item_id"], "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.setdefault("current_truth_sources", [])
    for source in [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), EVIDENCE_CLOSEOUT.as_posix()]:
        if source not in resume["current_truth_sources"]:
            resume["current_truth_sources"].append(source)
    resume.update({**common_contract, "writer_owned_outputs": [RESUME_CURSOR.as_posix()]})
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": summary["status"],
            "active_phase": summary["status"],
            "claim_boundary": next_claim_boundary,
            "active_ids": resume["active_ids"],
            "next_work_item": {
                "work_item_id": summary["next_work_item_id"],
                "path": NEXT_WORK_ITEM.as_posix(),
                "summary": next_action,
            },
        }
    )
    l5 = goal.setdefault("wave03_volatility_state_l5_candidate_runtime_evidence", {})
    l5.update(
        {
            "status": summary["status"],
            "claim_boundary": summary["claim_boundary"],
            "l5_runtime_evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "l5_runtime_evidence_index": EVIDENCE_INDEX.as_posix(),
            "candidate_results": summary["candidate_results"],
            "l5_candidate_count": 0,
            "operational_review_reference_observed_ids": summary["operational_review_reference_observed_ids"],
            "next_work_item": summary["next_work_item_id"],
        }
    )
    goal.update({**common_contract, "writer_owned_outputs": [GOAL_MANIFEST.as_posix()]})
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": summary["status"],
            "claim_boundary": next_claim_boundary,
            "candidate_count": summary["counts"]["candidate_count"],
            "l5_candidate_count": 0,
            "next_action": next_action,
            "missing_evidence": summary["judgment"]["missing_evidence"],
            "unresolved_blockers": list(summary["unresolved_blockers"]),
            "reopen_conditions": list(summary["reopen_conditions"]),
        }
    )
    l4 = campaign.setdefault("l4_follow_through", {})
    l4.update(
        {
            "l5_runtime_evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "l5_runtime_evidence_index": EVIDENCE_INDEX.as_posix(),
            "l5_runtime_evidence_status": summary["status"],
            "l5_runtime_evidence_counts": summary["counts"],
            "l5_candidate_count": 0,
        }
    )
    evidence_paths = campaign.setdefault("evidence_paths", [])
    for source in [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix()]:
        if source not in evidence_paths:
            evidence_paths.append(source)
    campaign.update({**common_contract, "writer_owned_outputs": [CAMPAIGN_MANIFEST.as_posix()]})
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": summary["ended_at_utc"],
            "active_goal": {"goal_id": GOAL_ID, "status": summary["status"], "manifest": GOAL_MANIFEST.as_posix()},
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": summary["status"],
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": None,
            },
            "active_work_item": {"work_item_id": summary["next_work_item_id"], "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": next_claim_boundary,
            "next_action": next_action,
            "unresolved_blockers": list(summary["unresolved_blockers"]),
            "active_record_authority": dict(routing_writer.pair_writer.ACTIVE_RECORD_AUTHORITY),
            "status": summary["status"],
            "primary_family": next_work["primary_family"],
            "primary_skill": next_work["primary_skill"],
            "next_executable_action": next_action,
            "operational_validation_required": False,
        }
    )
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = summary["counts"]["candidate_count"]
    counts["l5_candidate_count"] = 0
    counts["wave03_l5_candidate_runtime_evidence"] = summary["counts"]
    workspace.update({**common_contract, "writer_owned_outputs": [WORKSPACE_STATE.as_posix()]})
    write_yaml(WORKSPACE_STATE, workspace)

    update_goal_campaign_registries(summary)


def smoke_outputs(summary: dict[str, Any], candidates: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for path in [EVIDENCE_SUMMARY, EVIDENCE_INDEX, EVIDENCE_CLOSEOUT, NEXT_WORK_ITEM, WORKSPACE_STATE, GOAL_MANIFEST, CAMPAIGN_MANIFEST]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing source-of-truth path: {path.as_posix()}")
    loaded_summary = read_yaml(REPO_ROOT / EVIDENCE_SUMMARY) if path_exists(REPO_ROOT / EVIDENCE_SUMMARY) else {}
    if loaded_summary.get("claim_boundary") != summary["claim_boundary"]:
        errors.append("evidence summary claim_boundary mismatch")
    if (loaded_summary.get("counts") or {}).get("l5_candidate_count") != 0:
        errors.append("l5_candidate_count must remain zero before final claim guard")
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        path = candidate_summary_path(candidate_id)
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing candidate summary: {path.as_posix()}")
            continue
        current = read_yaml(REPO_ROOT / path)
        if (current.get("candidate_scope") or {}).get("l5_candidate") is not False:
            errors.append(f"{candidate_id}: l5_candidate scope must be false before final claim guard")
        evidence_path = candidate_evidence_path(candidate_id)
        if not path_exists(REPO_ROOT / evidence_path):
            errors.append(f"missing candidate evidence summary: {evidence_path.as_posix()}")
    skip_terminal_probe = bool((summary.get("runtime_probe_environment") or {}).get("skip_terminal_probe"))
    required_suffixes = ["attempt_manifest.yaml", "tester_config.ini", "tester_report_kpi_summary.yaml"]
    if not skip_terminal_probe:
        required_suffixes.append("terminal_run_summary.yaml")
    for row in rows:
        attempt_id = row["attempt_id"]
        for suffix in required_suffixes:
            path = Path("runtime") / "mt5_attempts" / attempt_id / suffix
            if not path_exists(REPO_ROOT / path):
                errors.append(f"{attempt_id}: missing {suffix}")
    next_work = read_yaml(REPO_ROOT / NEXT_WORK_ITEM) if path_exists(REPO_ROOT / NEXT_WORK_ITEM) else {}
    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE) if path_exists(REPO_ROOT / WORKSPACE_STATE) else {}
    if next_work.get("work_item_id") != summary["next_work_item_id"]:
        errors.append("next_work_item id mismatch")
    if workspace.get("current_claim_boundary") != next_work.get("claim_boundary"):
        errors.append("workspace claim boundary does not match next work")
    if workspace.get("operational_validation_required") is not False:
        errors.append("workspace operational_validation_required must be false")
    return errors


def execute_plans(
    *,
    candidates: list[dict[str, Any]],
    portable_root: Path,
    terminal_timeout_seconds: int,
    refresh_portable_root: bool,
    skip_terminal_probe: bool,
    reuse_existing_terminal_probe: bool,
    hold_bars: int,
    magic_base: int,
    deviation_points: int,
    started_at_utc: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, Any]]:
    copy_result = portable_repair.run_robocopy(DEFAULT_TERMINAL.parent, portable_root, refresh=refresh_portable_root)
    root_preflight = portable_terminal_root_preflight(portable_root / "terminal64.exe")
    rows: list[dict[str, Any]] = []
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        plans = period_plan_from_candidate(candidate)
        for offset, plan in enumerate(plans):
            attempt_id = plan["attempt_id"]
            attempt_root = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id
            attempt_root.mkdir(parents=True, exist_ok=True)
            magic_number = magic_base + safe_int(str(plan["cell_id"]).rsplit("_", 1)[-1]) * 10 + offset
            config_summary = prepare_l5_tester_config(
                source_config=plan["source_config_path"],
                target_config=attempt_root / "tester_config.ini",
                attempt_id=attempt_id,
                hold_bars=hold_bars,
                magic_number=magic_number,
                deviation_points=deviation_points,
            )
            common_inputs = portable_repair.ensure_common_file_inputs(
                plan["source_manifest"],
                config_summary["tester_config"],
            )
            row = prep_row(plan)
            existing_row = (
                l4_base.execution_row_from_manifest(REPO_ROOT, row)
                if reuse_existing_terminal_probe and path_exists(attempt_root / "attempt_manifest.yaml")
                else None
            )
            manifest = build_initial_attempt_manifest(
                candidate=candidate,
                plan=plan,
                config_summary=config_summary,
                common_inputs=common_inputs,
                portable_root=portable_root,
                root_preflight=root_preflight,
                copy_result=copy_result,
                created_at_utc=started_at_utc,
            )
            if existing_row:
                row.update(existing_row)
            else:
                write_yaml(Path("runtime") / "mt5_attempts" / attempt_id / "attempt_manifest.yaml", manifest)
                if not skip_terminal_probe and root_preflight.get("status") == "passed":
                    row.update(
                        l4_base.run_one_attempt(
                            repo_root=REPO_ROOT,
                            row=row,
                            terminal=portable_root / "terminal64.exe",
                            timeout_seconds=terminal_timeout_seconds,
                            terminate_existing=False,
                            allow_main_mode_fallback=False,
                            started_at_utc=started_at_utc,
                        )
                    )
            evidence_row = build_period_row(candidate, row, write_parse_summaries=True)
            finalize_attempt_manifest(candidate, evidence_row)
            rows.append(evidence_row)
            by_candidate.setdefault(candidate["candidate_id"], []).append(evidence_row)
    return rows, by_candidate, copy_result, root_preflight


def write_outputs(
    *,
    summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    by_candidate: dict[str, list[dict[str, Any]]],
    command_argv: list[str],
) -> None:
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        candidate_rows = by_candidate.get(candidate_id, [])
        write_yaml(
            candidate_evidence_path(candidate_id),
            build_candidate_evidence_summary(candidate, candidate_rows, summary["ended_at_utc"], command_argv),
        )
        update_candidate_summary(candidate, candidate_rows, summary)
    write_csv(EVIDENCE_INDEX, rows, evidence_index_fieldnames())
    write_yaml(EVIDENCE_SUMMARY, summary)
    write_yaml(EVIDENCE_CLOSEOUT, build_closeout(summary))
    upsert_candidate_registry(summary, candidates)
    upsert_artifact_registry(summary, rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and execute Wave03 L5 candidate-specific decision-execution runtime evidence."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--portable-root", default=str(portable_repair.default_portable_root()))
    parser.add_argument("--terminal-timeout-seconds", type=int, default=900)
    parser.add_argument("--refresh-portable-root", action="store_true")
    parser.add_argument("--skip-terminal-probe", action="store_true")
    parser.add_argument("--reuse-existing-terminal-probe", action="store_true")
    parser.add_argument("--hold-bars", type=int, default=DEFAULT_HOLD_BARS)
    parser.add_argument("--magic-base", type=int, default=DEFAULT_MAGIC_BASE)
    parser.add_argument("--deviation-points", type=int, default=DEFAULT_DEVIATION_POINTS)
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global REPO_ROOT
    args = parse_args(argv)
    REPO_ROOT = Path(args.repo_root).resolve()
    routing_writer.REPO_ROOT = REPO_ROOT
    routing_writer.pair_writer.REPO_ROOT = REPO_ROOT
    portable_repair.REPO_ROOT = REPO_ROOT
    l4_base.REPO_ROOT = REPO_ROOT
    started = utc_now()
    command_argv = [Path(sys.executable).name, *sys.argv] if argv is None else ["python", __file__, *argv]
    candidate_ids = opened_candidate_ids()
    candidates = [read_yaml(REPO_ROOT / candidate_summary_path(candidate_id)) for candidate_id in candidate_ids]
    candidates = [candidate for candidate in candidates if candidate.get("candidate_id")]
    if not candidates:
        raise RuntimeError("no opened Wave03 L5 candidate manifests found")
    rows, by_candidate, copy_result, root_preflight = execute_plans(
        candidates=candidates,
        portable_root=Path(args.portable_root).resolve(),
        terminal_timeout_seconds=args.terminal_timeout_seconds,
        refresh_portable_root=bool(args.refresh_portable_root),
        skip_terminal_probe=bool(args.skip_terminal_probe or args.smoke_only),
        reuse_existing_terminal_probe=bool(args.reuse_existing_terminal_probe),
        hold_bars=args.hold_bars,
        magic_base=args.magic_base,
        deviation_points=args.deviation_points,
        started_at_utc=started,
    )
    summary = build_summary(
        candidates=candidates,
        rows=rows,
        by_candidate=by_candidate,
        started_at_utc=started,
        command_argv=command_argv,
        copy_result=copy_result,
        root_preflight=root_preflight,
        skip_terminal_probe=bool(args.skip_terminal_probe or args.smoke_only),
    )
    write_outputs(summary=summary, candidates=candidates, rows=rows, by_candidate=by_candidate, command_argv=command_argv)
    if args.write_control_records:
        update_control_records(summary)
    errors = smoke_outputs(summary, candidates, rows)
    if errors:
        print({"status": "wave03_l5_candidate_runtime_evidence_writer_smoke_failed", "errors": errors})
        return 1
    print(
        "wave03 l5 candidate runtime evidence writer-smoke passed: "
        f"candidates={summary['counts']['candidate_count']} rows={len(rows)} "
        f"l5_candidate_count=0 status={summary['status']} claim_boundary={summary['claim_boundary']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
