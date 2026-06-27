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


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave02_cost_risk_holding_surface_v0"
IDEA_ID = "idea_us100_wave02_cost_risk_holding_surface_v0"
HYPOTHESIS_ID = "hyp_us100_wave02_cost_risk_holding_runtime_alignment_v0"
SURFACE_ID = "surface_us100_wave02_cost_risk_holding_v0"
SWEEP_ID = "sweep_us100_wave02_cost_risk_holding_broad_v0"

PARENT_WORK_ITEM_ID = "work_wave02_cost_risk_holding_l4_runtime_execution_v0"
WORK_ITEM_ID = "work_wave02_cost_risk_holding_l4_pair_judgment_v0"
NEXT_WORK_ITEM_ID = "work_wave02_cost_risk_holding_l5_routing_decision_v0"

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/l4_follow_through")
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
PAIR_SUMMARY = OUTPUT_DIR / "l4_pair_judgment_summary.yaml"
PAIR_INDEX = OUTPUT_DIR / "l4_pair_judgment_index.csv"
PAIR_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_cost_risk_holding_l4_pair_judgment_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/campaign_manifest.yaml")
RUN_REFS = (
    Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0")
    / "sweeps"
    / SWEEP_ID
    / "run_refs.csv"
)

CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_l4_pair_judgment_only_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_l5_routing_decision_pending_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_cost_risk_holding_l4_pair_judgment_completed_l5_routing_decision_pending"
NEXT_ACTION = (
    "decide whether Wave02 cost/risk/holding pairs justify a bounded decision-execution adapter "
    "before any L5 candidate manifest"
)
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
        return int(value)
    except (TypeError, ValueError):
        return 0


def first_scalar(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def ratio_delta(left: float | None, right: float | None) -> float | str:
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


def classify_pair(
    *,
    proxy_judgment: str,
    both_observed: bool,
    nonempty_pair: bool,
    tester_reports_observed: bool,
    decision_execution_ready: bool,
) -> str:
    if not both_observed:
        return "proxy_preserved_runtime_score_missing_or_partial"
    if not nonempty_pair:
        return "proxy_preserved_runtime_score_empty"
    if not tester_reports_observed:
        return "runtime_score_observed_report_missing"
    if not decision_execution_ready and proxy_judgment == "preserved_clue":
        return "proxy_preserved_clue_runtime_score_observed_decision_execution_pending"
    if proxy_judgment == "preserved_clue":
        return "proxy_preserved_clue_runtime_score_observed"
    if proxy_judgment == "negative":
        return "proxy_negative_runtime_score_observed"
    return "proxy_unclassified_runtime_score_observed"


def l5_routing_status(
    *,
    proxy_judgment: str,
    both_observed: bool,
    nonempty_pair: bool,
    tester_reports_observed: bool,
    decision_execution_ready: bool,
) -> tuple[str, str]:
    if not both_observed or not nonempty_pair:
        return (
            "no_l5_runtime_score_missing_or_empty",
            "repair_or_rerun_missing_or_empty_L4_score_telemetry_before_any_L5_routing",
        )
    if not tester_reports_observed:
        return (
            "no_l5_score_probe_report_incomplete",
            "repair missing Strategy Tester reports before any L5 routing decision",
        )
    if proxy_judgment == "preserved_clue" and not decision_execution_ready:
        return (
            "l5_routing_review_requires_decision_execution_adapter_no_candidate_claim",
            "build or choose a bounded decision-execution adapter before any candidate-specific L5 manifest",
        )
    if proxy_judgment == "preserved_clue":
        return (
            "l5_routing_review_required_no_candidate_claim",
            "decide L5 routing with candidate-specific manifest before any candidate claim",
        )
    return ("no_l5_not_promising_enough", "record L4 runtime observation and rotate")


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
        "runtime_probe_pair_complete",
        "validation_row_count",
        "research_oos_row_count",
        "validation_score_mean",
        "research_oos_score_mean",
        "score_mean_delta_research_minus_validation",
        "validation_score_min",
        "validation_score_max",
        "research_oos_score_min",
        "research_oos_score_max",
        "validation_spread_points_mean",
        "research_oos_spread_points_mean",
        "validation_proxy_trade_count",
        "research_oos_proxy_trade_count",
        "validation_proxy_trade_density",
        "research_oos_proxy_trade_density",
        "validation_proxy_profit_factor",
        "research_oos_proxy_profit_factor",
        "proxy_profit_factor_delta_research_minus_validation",
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


def aggregate_pairs(started_at_utc: str, command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runtime_rows = read_csv_rows(REPO_ROOT / RUNTIME_INDEX)
    rows_by_cell: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
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
        validation_stats = validation_summary.get("stats") or {}
        research_stats = research_summary.get("stats") or {}
        validation_rows = safe_int(validation_stats.get("row_count"))
        research_rows = safe_int(research_stats.get("row_count"))
        validation_mean = safe_float(first_scalar(validation_stats, "score_stats", "mean", default=None))
        research_mean = safe_float(first_scalar(research_stats, "score_stats", "mean", default=None))
        validation_pf = safe_float(first_scalar(metrics, "trading_proxy_metrics", "validation", "gross_proxy_profit_factor", default=None))
        research_pf = safe_float(first_scalar(metrics, "trading_proxy_metrics", "research_oos_a", "gross_proxy_profit_factor", default=None))
        validation_trade_density = safe_float(first_scalar(metrics, "trading_proxy_metrics", "validation", "trade_density", default=None))
        research_trade_density = safe_float(first_scalar(metrics, "trading_proxy_metrics", "research_oos_a", "trade_density", default=None))
        decision_surface = bundle.get("decision_surface") or {}
        proxy_judgment = str(metrics.get("judgment_label") or manifest.get("result_judgment") or "")
        holding_policy = str(decision_surface.get("holding_policy") or "")
        decision_execution_ready = holding_policy.strip() not in {"", "not_executed_score_telemetry_only"}
        both_observed = boolish(validation.get("telemetry_observed")) and boolish(research.get("telemetry_observed"))
        nonempty_pair = validation_rows > 0 and research_rows > 0
        tester_reports_observed = boolish(validation.get("tester_report_observed")) and boolish(
            research.get("tester_report_observed")
        )
        runtime_pair_complete = boolish(validation.get("runtime_probe_complete")) and boolish(
            research.get("runtime_probe_complete")
        )
        comparison_class = classify_pair(
            proxy_judgment=proxy_judgment,
            both_observed=both_observed,
            nonempty_pair=nonempty_pair,
            tester_reports_observed=tester_reports_observed,
            decision_execution_ready=decision_execution_ready,
        )
        l5_status, next_action = l5_routing_status(
            proxy_judgment=proxy_judgment,
            both_observed=both_observed,
            nonempty_pair=nonempty_pair,
            tester_reports_observed=tester_reports_observed,
            decision_execution_ready=decision_execution_ready,
        )
        result_judgment = "runtime_probe" if runtime_pair_complete and nonempty_pair else "inconclusive"
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
                "tester_report_pair_observed": str(tester_reports_observed).lower(),
                "runtime_probe_pair_complete": str(runtime_pair_complete).lower(),
                "validation_row_count": validation_rows,
                "research_oos_row_count": research_rows,
                "validation_score_mean": "" if validation_mean is None else validation_mean,
                "research_oos_score_mean": "" if research_mean is None else research_mean,
                "score_mean_delta_research_minus_validation": ratio_delta(validation_mean, research_mean),
                "validation_score_min": first_scalar(validation_stats, "score_stats", "min", default=""),
                "validation_score_max": first_scalar(validation_stats, "score_stats", "max", default=""),
                "research_oos_score_min": first_scalar(research_stats, "score_stats", "min", default=""),
                "research_oos_score_max": first_scalar(research_stats, "score_stats", "max", default=""),
                "validation_spread_points_mean": first_scalar(validation_stats, "spread_points_stats", "mean", default=""),
                "research_oos_spread_points_mean": first_scalar(research_stats, "spread_points_stats", "mean", default=""),
                "validation_proxy_trade_count": first_scalar(metrics, "trading_proxy_metrics", "validation", "trade_count", default=""),
                "research_oos_proxy_trade_count": first_scalar(metrics, "trading_proxy_metrics", "research_oos_a", "trade_count", default=""),
                "validation_proxy_trade_density": "" if validation_trade_density is None else validation_trade_density,
                "research_oos_proxy_trade_density": "" if research_trade_density is None else research_trade_density,
                "validation_proxy_profit_factor": "" if validation_pf is None else validation_pf,
                "research_oos_proxy_profit_factor": "" if research_pf is None else research_pf,
                "proxy_profit_factor_delta_research_minus_validation": ratio_delta(validation_pf, research_pf),
                "decision_family": str(decision_surface.get("decision_family") or ""),
                "holding_policy": holding_policy,
                "runtime_translation_status": str(decision_surface.get("runtime_translation_status") or ""),
                "proxy_judgment": proxy_judgment,
                "comparison_class": comparison_class,
                "standard_l4_completion": "completed_score_probe_with_report_observed"
                if tester_reports_observed
                else "incomplete_tester_report_missing",
                "result_judgment": result_judgment,
                "l5_routing_status": l5_status,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": next_action,
            }
        )

    runtime_summary = read_yaml(REPO_ROOT / RUNTIME_SUMMARY)
    runtime_counts = runtime_summary.get("counts") or {}
    ended_at_utc = utc_now()
    status_counts = Counter(row["l5_routing_status"] for row in pair_rows)
    comparison_counts = Counter(row["comparison_class"] for row in pair_rows)
    proxy_counts = Counter(row["proxy_judgment"] for row in pair_rows)
    result_counts = Counter(row["result_judgment"] for row in pair_rows)
    pair_complete_count = sum(row["runtime_probe_pair_complete"] == "true" for row in pair_rows)
    nonempty_pair_count = sum(row["nonempty_telemetry_pair"] == "true" for row in pair_rows)
    tester_report_pair_count = sum(row["tester_report_pair_observed"] == "true" for row in pair_rows)
    l5_review_count = sum(
        row["l5_routing_status"] == "l5_routing_review_requires_decision_execution_adapter_no_candidate_claim"
        for row in pair_rows
    )
    missing_evidence = [
        "decision_execution_adapter_not_yet_applied",
        "candidate_specific_L5_manifest_not_opened",
        "economics_metrics_not_available_from_non_trading_score_probe",
        "row_level_proxy_vs_MT5_score_alignment_not_performed",
    ]
    if pair_complete_count != len(pair_rows):
        missing_evidence.insert(0, "remaining_or_incomplete_L4_period_pairs")

    summary = {
        "version": "wave02_cost_risk_holding_l4_pair_judgment_summary_v1",
        "summary_id": "wave02_cost_risk_holding_l4_pair_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-result-judgment", "spacesonar-evidence-provenance"],
        "validation_depth": "writer_scope_smoke",
        "runtime_contract_binding": runtime_summary.get("runtime_contract_binding", {}),
        "counts": {
            "cell_pair_count": len(pair_rows),
            "runtime_probe_pair_complete_count": pair_complete_count,
            "both_period_roles_observed_count": sum(row["both_period_roles_observed"] == "true" for row in pair_rows),
            "nonempty_telemetry_pair_count": nonempty_pair_count,
            "tester_report_pair_observed_count": tester_report_pair_count,
            "decision_execution_pending_pair_count": l5_review_count,
            "l5_routing_review_required_count": l5_review_count,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "proxy_judgment_counts": dict(sorted(proxy_counts.items())),
            "result_judgment_counts": dict(sorted(result_counts.items())),
            "l5_status_counts": dict(sorted(status_counts.items())),
            "comparison_class_counts": dict(sorted(comparison_counts.items())),
            "runtime_execution_counts": runtime_counts,
        },
        "judgment": {
            "result_subject": "Wave02 cost/risk/holding paired validation/research_oos L4 score runtime observations",
            "judgment_label": "runtime_probe",
            "metric_identity": (
                "paired MT5 score telemetry summaries and completed tester-report receipts; "
                "proxy PF/trade-density values are proxy context only"
            ),
            "comparison_baseline": "source proxy preserved_clue judgment plus paired MT5 score-observation presence",
            "tested_factor": "cost/risk/holding score-probe runtime follow-through for six preserved proxy clues",
            "kpi_interpretation": (
                "score-probe confirms ONNX/EA/MT5 observation coverage, but the EA did not execute trades; "
                "therefore economics, PF pass, drawdown pass, and runtime authority remain unclaimed"
            ),
            "directional_effect_hypothesis": (
                "cost/risk/holding semantics remain runtime-testable enough to justify a decision-execution adapter review, "
                "not a candidate claim"
            ),
            "attribution_confidence": "low_to_medium_observation_only_non_trading_runtime_surface",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": missing_evidence,
            "next_action": NEXT_ACTION,
        },
        "runtime_contract_effect": {
            "l4_score_runtime_observation": "completed_for_all_pairs" if pair_complete_count == len(pair_rows) else "partial",
            "standard_l4_score_probe_completion": "completed_with_telemetry_and_report_receipts",
            "decision_execution": "pending_adapter_or_routing_decision",
            "l5_continuation": "routing_decision_pending_no_candidate_claim",
            "locked_final_oos_b": "not_used",
            "runtime_authority": False,
            "economics_pass": False,
            "candidate": False,
            "goal_achieve": False,
        },
        "provenance": {
            "source_inputs": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), RUN_REFS.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()],
            "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()],
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
            "lineage_judgment": "pair_summary_index_and_closeout_written_from_runtime_execution_summary_and_score_telemetry_summaries",
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
            "Wave02 cost/risk/holding score-probe pair judgment must precede any L5 routing decision.",
            "Non-trading score probes can preserve a runtime-testable clue but cannot create economics pass, runtime authority, selected baseline, live readiness, or Goal Achieve.",
            "A preserved CRH score clue needs decision-execution adapter evidence before any candidate-specific L5 manifest.",
        ],
        "unresolved_blockers": ["Wave02_cost_risk_holding_L5_routing_decision_pending"],
        "reopen_conditions": [
            "rerun pair aggregation if a Wave02 CRH L4 runtime attempt manifest, score telemetry summary, or tester report receipt changes",
            "open L5 only with candidate-specific manifest and decision-execution adapter evidence plan",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    return summary, pair_rows


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-result-judgment", "spacesonar-evidence-provenance"],
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def upsert_artifact_registry(summary: dict[str, Any]) -> None:
    registry_path = REPO_ROOT / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path) if path_exists(registry_path) else []
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
    by_id = {row["artifact_id"]: row for row in rows}
    producer = summary["provenance"]["producer"]

    def put(artifact_id: str, artifact_type: str, path: Path, notes: str) -> None:
        full = REPO_ROOT / path
        by_id[artifact_id] = {
            **{key: "" for key in fieldnames},
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
            "claim_boundary": summary["claim_boundary"],
            "notes": notes,
        }

    put(
        "artifact_wave02_cost_risk_holding_l4_pair_judgment_summary_v0",
        "l4_pair_judgment_summary",
        PAIR_SUMMARY,
        "source-of-truth summary for Wave02 CRH paired L4 runtime score judgment",
    )
    put(
        "artifact_wave02_cost_risk_holding_l4_pair_judgment_index_v0",
        "l4_pair_judgment_index",
        PAIR_INDEX,
        "compact index of Wave02 CRH paired validation/research_oos L4 judgments",
    )
    put(
        "artifact_wave02_cost_risk_holding_l4_pair_judgment_closeout_v0",
        "work_closeout",
        PAIR_CLOSEOUT,
        "closeout for Wave02 CRH L4 pair judgment work",
    )
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def update_control_records(summary: dict[str, Any]) -> None:
    state = git_state(REPO_ROOT)
    output_hashes = [artifact_ref(PAIR_SUMMARY), artifact_ref(PAIR_INDEX), artifact_ref(PAIR_CLOSEOUT)]
    input_hashes = [artifact_ref(RUNTIME_SUMMARY), artifact_ref(RUNTIME_INDEX)]
    if path_exists(REPO_ROOT / RUN_REFS):
        input_hashes.append(artifact_ref(RUN_REFS))

    next_work = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-result-judgment", "spacesonar-evidence-provenance"],
        "verification_profile": "writer_scope_smoke",
        "targets": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "acceptance_criteria": [
            "decide whether Wave02 cost/risk/holding score-observation pairs justify bounded decision-execution adapter work",
            "keep candidate_count and l5_candidate_count at zero until candidate-specific L5 manifest exists",
            "keep runtime_authority, economics_pass, selected_baseline, live_readiness, and goal_achieve forbidden",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "policy_binding": {
            "revision": "policy_contract_v2",
            "guards": [
                "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
                "GUARD_002_RUNTIME_COMPLETION_TRUTH",
                "GUARD_003_CLAIM_BOUNDARY",
                "GUARD_004_ARTIFACT_IDENTITY",
                "GUARD_007_OPERATIONAL_STABILITY",
            ],
        },
        "outputs": [
            "decision-execution adapter work item or candidate summary only if L5 is explicitly opened later",
            "runtime/packages/<bundle_id>/experiment_bundle.json only if candidate-specific L5 materialization is opened later",
        ],
        "next_action": NEXT_ACTION,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Route Wave02 CRH pair judgment outcomes without promoting score probes to candidates.",
        "provenance": {
            "source": WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "source_of_truth": PAIR_SUMMARY.as_posix(),
        },
        "current_truth": {
            "l4_runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "l4_pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "l4_pair_judgment_index": PAIR_INDEX.as_posix(),
            "l4_pair_judgment_status": summary["status"],
            "l4_pair_judgment_counts": summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "status": "wave02_cost_risk_holding_l5_routing_decision_pending",
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "execution_provenance": {
            "git_sha": state["git_sha"],
            "branch": state["branch"],
            "dirty_flag": state["dirty_flag"],
            "changed_files": state["changed_files"],
            "command_argv": summary["provenance"]["regeneration_commands"],
            "python_executable": summary["provenance"]["environment_summary"]["python_executable"],
            "python_version": summary["provenance"]["environment_summary"]["python_version"],
            "key_package_versions": {"python": platform.python_version(), "yaml": yaml.__version__},
            "started_at_utc": summary["created_at_utc"],
            "ended_at_utc": summary["ended_at_utc"],
            "input_hashes": input_hashes,
            "output_hashes": output_hashes,
            "unknown_git_claim_effect": "dirty_worktree_recorded_claim_lowered_no_candidate_runtime_authority_or_economics_pass",
        },
    }
    write_yaml(NEXT_WORK_ITEM, next_work)

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = STATUS
    resume["active_phase"] = STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_ACTION
    resume["unresolved_blockers"] = summary["unresolved_blockers"]
    resume["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    sources = resume.setdefault("current_truth_sources", [])
    for source in [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["active_ids"] = resume["active_ids"]
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 CRH L5 routing decision pending; no candidate claim.",
    }
    wave02 = goal.setdefault("wave02_cost_risk_holding_campaign", {})
    wave02["status"] = STATUS
    wave02["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave02["next_work_item"] = NEXT_WORK_ITEM_ID
    wave02["candidate_count"] = 0
    wave02["l5_candidate_count"] = 0
    wave02["l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    wave02["l4_pair_judgment_index"] = PAIR_INDEX.as_posix()
    wave02["l4_pair_judgment_status"] = summary["status"]
    wave02["l4_pair_judgment_counts"] = summary["counts"]
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = summary["ended_at_utc"]
    campaign["status"] = STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["candidate_count"] = 0
    campaign["l5_candidate_count"] = 0
    campaign["next_action"] = NEXT_ACTION
    l4 = campaign.setdefault("l4_follow_through", {})
    l4["pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    l4["pair_judgment_index"] = PAIR_INDEX.as_posix()
    l4["pair_judgment_status"] = summary["status"]
    l4["pair_judgment_counts"] = summary["counts"]
    evidence = campaign.setdefault("evidence_paths", [])
    for source in [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()]:
        if source not in evidence:
            evidence.append(source)
    campaign["missing_evidence"] = summary["judgment"]["missing_evidence"]
    campaign["unresolved_blockers"] = summary["unresolved_blockers"]
    campaign["reopen_conditions"] = summary["reopen_conditions"]
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace.setdefault("active_campaign", {})["status"] = STATUS
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = NEXT_ACTION
    workspace["unresolved_blockers"] = summary["unresolved_blockers"]
    workspace["active_record_authority"] = dict(ACTIVE_RECORD_AUTHORITY)
    counts = workspace.setdefault("summary_counts", {})
    counts["wave02_cost_risk_holding_l4_pair_judgment"] = summary["counts"]
    crh = workspace.setdefault("wave02_cost_risk_holding_l4_materialization", {})
    crh["status"] = STATUS
    crh["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    crh["l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    crh["l4_pair_judgment_index"] = PAIR_INDEX.as_posix()
    crh["l4_pair_judgment_status"] = summary["status"]
    crh["l4_pair_judgment_counts"] = summary["counts"]
    crh["candidate_count"] = 0
    crh["l5_candidate_count"] = 0
    write_yaml(WORKSPACE_STATE, workspace)

    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        goal_rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                if "active_phase" in row:
                    row["active_phase"] = STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
        if goal_rows:
            write_csv(GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def smoke_pair_outputs(summary: dict[str, Any], pair_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for path in [PAIR_SUMMARY, PAIR_INDEX, PAIR_CLOSEOUT, RUNTIME_SUMMARY, RUNTIME_INDEX]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing source-of-truth path: {path.as_posix()}")
    loaded_summary = read_yaml(REPO_ROOT / PAIR_SUMMARY) if path_exists(REPO_ROOT / PAIR_SUMMARY) else {}
    loaded_closeout = read_yaml(REPO_ROOT / PAIR_CLOSEOUT) if path_exists(REPO_ROOT / PAIR_CLOSEOUT) else {}
    loaded_rows = read_csv_rows(REPO_ROOT / PAIR_INDEX) if path_exists(REPO_ROOT / PAIR_INDEX) else []
    if loaded_summary.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("pair summary claim_boundary mismatch")
    if loaded_closeout.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("pair closeout claim_boundary mismatch")
    if len(loaded_rows) != len(pair_rows):
        errors.append("pair index row count mismatch")
    counts = loaded_summary.get("counts") or {}
    if counts.get("cell_pair_count") != len(pair_rows):
        errors.append("pair summary cell_pair_count mismatch")
    if counts.get("runtime_probe_pair_complete_count") != len(pair_rows):
        errors.append("pair summary runtime_probe_pair_complete_count mismatch")
    if counts.get("candidate_count") != 0 or counts.get("l5_candidate_count") != 0:
        errors.append("candidate counts must stay zero")
    if loaded_summary.get("validation_depth") != "writer_scope_smoke":
        errors.append("pair summary validation_depth must be writer_scope_smoke")

    registry_rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    by_id = {row.get("artifact_id"): row for row in registry_rows}
    for artifact_id, path in [
        ("artifact_wave02_cost_risk_holding_l4_pair_judgment_summary_v0", PAIR_SUMMARY),
        ("artifact_wave02_cost_risk_holding_l4_pair_judgment_index_v0", PAIR_INDEX),
        ("artifact_wave02_cost_risk_holding_l4_pair_judgment_closeout_v0", PAIR_CLOSEOUT),
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
    active_work_item = workspace.get("active_work_item") or {}
    active_campaign = workspace.get("active_campaign") or {}
    current_truth = next_work.get("current_truth") or {}
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("workspace claim boundary mismatch")
    if workspace.get("next_action") != NEXT_ACTION:
        errors.append("workspace next_action mismatch")
    if workspace.get("unresolved_blockers") != ["Wave02_cost_risk_holding_L5_routing_decision_pending"]:
        errors.append("workspace unresolved_blockers mismatch")
    if workspace.get("active_record_authority", {}).get("summary_counts_role") != "cumulative_reference_not_active_pointer":
        errors.append("workspace active_record_authority missing summary_counts role")
    if active_campaign.get("status") != STATUS:
        errors.append("workspace active_campaign status mismatch")
    if active_work_item.get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("workspace active_work_item id mismatch")
    if active_work_item.get("path") != NEXT_WORK_ITEM.as_posix():
        errors.append("workspace active_work_item path mismatch")
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("next_work_item id mismatch")
    if next_work.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("next_work_item claim_boundary mismatch")
    if next_work.get("status") != "wave02_cost_risk_holding_l5_routing_decision_pending":
        errors.append("next_work_item status mismatch")
    if current_truth.get("l4_pair_judgment_summary") != PAIR_SUMMARY.as_posix():
        errors.append("next_work_item missing pair summary current truth")
    if current_truth.get("candidate_count") != 0 or current_truth.get("l5_candidate_count") != 0:
        errors.append("next_work_item candidate counts must stay zero")
    if goal.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("goal manifest claim_boundary mismatch")
    if (goal.get("next_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("goal manifest next_work_item mismatch")
    if campaign.get("status") != STATUS:
        errors.append("campaign manifest status mismatch")
    if campaign.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("campaign manifest claim_boundary mismatch")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave02 cost/risk/holding L4 validation/research_oos pair judgments.")
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
        "foundation/pipelines/aggregate_wave02_cost_risk_holding_l4_pair_judgments.py",
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
        "wave02 CRH l4 pair judgment writer-smoke passed: "
        f"pairs={len(pair_rows)} status={summary.get('status')} claim_boundary={summary.get('claim_boundary')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
