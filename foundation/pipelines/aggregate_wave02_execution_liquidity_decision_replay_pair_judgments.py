from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.run_wave02_execution_liquidity_l4_decision_replay_attempts as runtime_writer


base = runtime_writer.base

GOAL_ID = runtime_writer.GOAL_ID
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
CAMPAIGN_ID = runtime_writer.CAMPAIGN_ID
IDEA_ID = "idea_us100_wave02_execution_liquidity_surface_v0"
HYPOTHESIS_ID = "hyp_us100_wave02_execution_liquidity_runtime_alignment_v0"
SURFACE_ID = "surface_us100_wave02_execution_liquidity_v0"
SWEEP_ID = runtime_writer.SWEEP_ID

PARENT_WORK_ITEM_ID = runtime_writer.SUBWORK_ID
WORK_ITEM_ID = "work_wave02_execution_liquidity_decision_replay_judgment_v0"
NEXT_WORK_ITEM_ID = "work_wave02_execution_liquidity_decision_replay_l5_routing_decision_v0"

OUTPUT_DIR = runtime_writer.OUTPUT_DIR
RUNTIME_SUMMARY = runtime_writer.RUNTIME_SUMMARY
RUNTIME_INDEX = runtime_writer.RUNTIME_INDEX
SOURCE_PAIR_INDEX = Path(
    "lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/"
    "l4_follow_through/l4_pair_judgment_index.csv"
)
PAIR_SUMMARY = OUTPUT_DIR / "pair_judgment_summary.yaml"
PAIR_INDEX = OUTPUT_DIR / "pair_judgment_index.csv"
PAIR_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_execution_liquidity_decision_replay_judgment_v0_closeout.yaml"
)
NEXT_WORK_ITEM = runtime_writer.NEXT_WORK_ITEM
RESUME_CURSOR = runtime_writer.RESUME_CURSOR
GOAL_MANIFEST = runtime_writer.GOAL_MANIFEST
WORKSPACE_STATE = runtime_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = runtime_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = runtime_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = runtime_writer.GOAL_REGISTRY

CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_pair_judgment_only_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_l5_routing_decision_pending_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_execution_liquidity_decision_replay_pair_judgment_completed_l5_routing_decision_pending"
NEXT_ACTION = (
    "decide whether Wave02 execution/liquidity decision replay evidence justifies candidate-specific L5 routing; "
    "do not claim candidate, economics pass, runtime authority, live readiness, or Goal Achieve"
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
WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v2"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "pair_writer_smoke",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
    "targeted_artifact_hash_check",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_optional_yaml(path: Path) -> dict[str, Any]:
    full = REPO_ROOT / path
    return base.load_yaml(full) if full.exists() else {}


def read_optional_csv(path: Path) -> list[dict[str, str]]:
    full = REPO_ROOT / path
    return base.read_csv_rows(full) if full.exists() else []


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


def safe_int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def ratio(numerator: int, denominator: int) -> float | str:
    return "" if denominator <= 0 else numerator / denominator


def abs_delta(left: float | None, right: float | None) -> float | str:
    return "" if left is None or right is None else abs(right - left)


def source_pairs_by_cell() -> dict[str, dict[str, str]]:
    return {row["cell_id"]: row for row in read_optional_csv(SOURCE_PAIR_INDEX) if row.get("cell_id")}


def telemetry_stats(row: dict[str, str]) -> dict[str, Any]:
    path_value = row.get("execution_telemetry_summary_path")
    if not path_value:
        return {}
    summary = read_optional_yaml(Path(path_value))
    stats = summary.get("stats")
    return stats if isinstance(stats, dict) else {}


def action_counts(stats: dict[str, Any]) -> dict[str, int]:
    counts = stats.get("action_counts") or {}
    return {str(key): safe_int(value) for key, value in counts.items()} if isinstance(counts, dict) else {}


def source_decision_counts(stats: dict[str, Any]) -> dict[str, int]:
    counts = stats.get("source_decision_counts") or {}
    return {str(key): safe_int(value) for key, value in counts.items()} if isinstance(counts, dict) else {}


def runtime_pair_status(
    *,
    both_complete: bool,
    nonempty_pair: bool,
    validation_open: int,
    research_open: int,
    open_failed_total: int,
    max_open_failed_rate: float | None,
) -> tuple[str, str]:
    if not both_complete or not nonempty_pair:
        return "no_l5_runtime_incomplete", "repair incomplete decision replay runtime pair before any L5 routing review"
    if validation_open <= 0 or research_open <= 0:
        return "no_l5_no_decision_actions", "record decision replay observation and rotate unless a new action surface is opened"
    if max_open_failed_rate is not None and max_open_failed_rate >= 0.05:
        return (
            "l5_routing_review_requires_execution_repair_no_candidate_claim",
            "review decision replay only after resolving high open_failed asymmetry; no candidate claim",
        )
    if open_failed_total > 0:
        return (
            "l5_routing_review_required_with_open_failed_note_no_candidate_claim",
            "review bounded L5 routing with open_failed caveat; no candidate claim",
        )
    return (
        "l5_routing_review_required_no_candidate_claim",
        "review bounded L5 routing from paired decision replay action telemetry; no candidate claim",
    )


def aggregate_pairs(started_at_utc: str, command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runtime_rows = base.read_csv_rows(REPO_ROOT / RUNTIME_INDEX)
    rows_by_cell: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        rows_by_cell[row["cell_id"]].append(row)

    source_pairs = source_pairs_by_cell()
    pair_rows: list[dict[str, Any]] = []
    for cell_id in sorted(rows_by_cell):
        by_period = {row["period_role"]: row for row in rows_by_cell[cell_id]}
        validation = by_period.get("validation", {})
        research = by_period.get("research_oos", {})
        anchor = validation or research
        validation_stats = telemetry_stats(validation) if validation else {}
        research_stats = telemetry_stats(research) if research else {}
        validation_actions = action_counts(validation_stats)
        research_actions = action_counts(research_stats)
        validation_source = source_decision_counts(validation_stats)
        research_source = source_decision_counts(research_stats)

        validation_rows = safe_int(validation.get("execution_row_count") or validation_stats.get("row_count"))
        research_rows = safe_int(research.get("execution_row_count") or research_stats.get("row_count"))
        validation_open = safe_int(validation.get("open_action_count"))
        research_open = safe_int(research.get("open_action_count"))
        validation_close = safe_int(validation.get("close_action_count"))
        research_close = safe_int(research.get("close_action_count"))
        validation_failed = safe_int(validation.get("open_failed_count"))
        research_failed = safe_int(research.get("open_failed_count"))
        validation_open_rate = ratio(validation_open, validation_rows)
        research_open_rate = ratio(research_open, research_rows)
        validation_failed_rate = ratio(validation_failed, validation_rows)
        research_failed_rate = ratio(research_failed, research_rows)
        failed_rate_values = [
            value for value in [safe_float(validation_failed_rate), safe_float(research_failed_rate)] if value is not None
        ]
        both_complete = boolish(validation.get("runtime_probe_complete")) and boolish(research.get("runtime_probe_complete"))
        nonempty_pair = validation_rows > 0 and research_rows > 0
        tester_reports_observed = boolish(validation.get("tester_report_observed")) and boolish(
            research.get("tester_report_observed")
        )
        l5_status, next_action = runtime_pair_status(
            both_complete=both_complete,
            nonempty_pair=nonempty_pair,
            validation_open=validation_open,
            research_open=research_open,
            open_failed_total=validation_failed + research_failed,
            max_open_failed_rate=max(failed_rate_values) if failed_rate_values else None,
        )
        source_pair = source_pairs.get(cell_id, {})
        result_judgment = "runtime_probe" if both_complete and nonempty_pair and tester_reports_observed else "inconclusive"
        pair_rows.append(
            {
                "cell_id": cell_id,
                "run_id": anchor.get("run_id", ""),
                "bundle_id": anchor.get("bundle_id", ""),
                "direction_policy": anchor.get("direction_policy", ""),
                "validation_attempt_id": validation.get("attempt_id", ""),
                "research_oos_attempt_id": research.get("attempt_id", ""),
                "validation_execution_observed": str(boolish(validation.get("execution_telemetry_observed"))).lower(),
                "research_oos_execution_observed": str(boolish(research.get("execution_telemetry_observed"))).lower(),
                "both_period_roles_observed": str(
                    boolish(validation.get("execution_telemetry_observed"))
                    and boolish(research.get("execution_telemetry_observed"))
                ).lower(),
                "nonempty_execution_pair": str(nonempty_pair).lower(),
                "tester_report_pair_observed": str(tester_reports_observed).lower(),
                "runtime_probe_pair_complete": str(both_complete).lower(),
                "validation_row_count": validation_rows,
                "research_oos_row_count": research_rows,
                "validation_open_action_count": validation_open,
                "research_oos_open_action_count": research_open,
                "validation_close_action_count": validation_close,
                "research_oos_close_action_count": research_close,
                "validation_open_failed_count": validation_failed,
                "research_oos_open_failed_count": research_failed,
                "validation_open_rate": validation_open_rate,
                "research_oos_open_rate": research_open_rate,
                "abs_open_rate_delta": abs_delta(safe_float(validation_open_rate), safe_float(research_open_rate)),
                "validation_open_failed_rate": validation_failed_rate,
                "research_oos_open_failed_rate": research_failed_rate,
                "max_open_failed_rate": max(failed_rate_values) if failed_rate_values else "",
                "validation_source_tradeable_count": validation_source.get("tradeable", 0),
                "research_oos_source_tradeable_count": research_source.get("tradeable", 0),
                "validation_action_counts": json.dumps(validation_actions, sort_keys=True),
                "research_oos_action_counts": json.dumps(research_actions, sort_keys=True),
                "source_proxy_judgment": source_pair.get("proxy_judgment", ""),
                "source_l4_score_l5_status": source_pair.get("l5_routing_status", ""),
                "source_l4_score_comparison_class": source_pair.get("comparison_class", ""),
                "decision_replay_comparison_class": (
                    "decision_replay_actions_observed_with_high_open_failed"
                    if l5_status == "l5_routing_review_requires_execution_repair_no_candidate_claim"
                    else "decision_replay_actions_observed"
                    if validation_open > 0 and research_open > 0
                    else "decision_replay_no_actions_or_incomplete"
                ),
                "result_judgment": result_judgment,
                "l5_routing_status": l5_status,
                "candidate_count": 0,
                "l5_candidate_count": 0,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": next_action,
            }
        )

    runtime_summary = read_optional_yaml(RUNTIME_SUMMARY)
    runtime_counts = runtime_summary.get("counts") or {}
    ended_at_utc = utc_now()
    status_counts = Counter(row["l5_routing_status"] for row in pair_rows)
    comparison_counts = Counter(row["decision_replay_comparison_class"] for row in pair_rows)
    result_counts = Counter(row["result_judgment"] for row in pair_rows)
    source_proxy_counts = Counter(row["source_proxy_judgment"] for row in pair_rows)
    pair_complete_count = sum(row["runtime_probe_pair_complete"] == "true" for row in pair_rows)
    action_pair_count = sum(
        safe_int(row["validation_open_action_count"]) > 0 and safe_int(row["research_oos_open_action_count"]) > 0
        for row in pair_rows
    )
    repair_first_count = sum(
        row["l5_routing_status"] == "l5_routing_review_requires_execution_repair_no_candidate_claim"
        for row in pair_rows
    )
    routing_review_count = sum(str(row["l5_routing_status"]).startswith("l5_routing_review") for row in pair_rows)
    all_pairs_complete = bool(pair_rows) and pair_complete_count == len(pair_rows)
    missing_evidence = [
        "candidate_specific_L5_manifest_not_opened",
        "economics_metrics_not_parsed_or_claimable",
        "row_level_proxy_vs_decision_replay_alignment_not_performed",
    ]
    if repair_first_count:
        missing_evidence.append("high_open_failed_pair_requires_execution_repair_before_candidate_specific_L5")
    if not all_pairs_complete:
        missing_evidence.insert(0, "remaining_or_incomplete_decision_replay_pairs")

    summary = {
        "version": "wave02_execution_liquidity_decision_replay_pair_judgment_summary_v1",
        "summary_id": "wave02_execution_liquidity_decision_replay_pair_judgment_summary_v0",
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
            "artifact_id": "artifact_wave02_execution_liquidity_decision_replay_pair_judgment_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS if all_pairs_complete else "wave02_execution_liquidity_decision_replay_pair_judgment_partial_progress",
        "claim_boundary": CLAIM_BOUNDARY,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": "none_pair_judgment_progress_no_protected_claim",
        "counts": {
            "cell_pair_count": len(pair_rows),
            "runtime_probe_pair_complete_count": pair_complete_count,
            "both_period_roles_observed_count": sum(row["both_period_roles_observed"] == "true" for row in pair_rows),
            "nonempty_execution_pair_count": sum(row["nonempty_execution_pair"] == "true" for row in pair_rows),
            "tester_report_pair_observed_count": sum(row["tester_report_pair_observed"] == "true" for row in pair_rows),
            "decision_action_pair_count": action_pair_count,
            "l5_routing_review_required_count": routing_review_count,
            "l5_routing_review_repair_first_count": repair_first_count,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "source_proxy_judgment_counts": dict(sorted(source_proxy_counts.items())),
            "result_judgment_counts": dict(sorted(result_counts.items())),
            "l5_status_counts": dict(sorted(status_counts.items())),
            "decision_replay_comparison_class_counts": dict(sorted(comparison_counts.items())),
            "runtime_execution_counts": runtime_counts,
        },
        "judgment": {
            "result_subject": "Wave02 execution/liquidity decision replay validation/research_oos action telemetry pair aggregation",
            "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
            "metric_identity": "paired MT5 decision replay action telemetry and Strategy Tester report presence",
            "comparison_baseline": "source Wave02 ELQ L4 score pair judgment plus paired decision replay action observation",
            "tested_factor": "sparse momentum_ret_1 direction policy replayed from Wave02 execution/liquidity score telemetry",
            "kpi_interpretation": "runtime action observation only; no trading economics, no profit factor, no drawdown, no live or production meaning",
            "directional_effect_hypothesis": (
                "decision replay produced paired action telemetry for preserved clue cells, "
                "but candidate-specific L5 work remains unopened"
            ),
            "attribution_confidence": "moderate_runtime_observation_only",
            "judgment_label": "runtime_probe" if all_pairs_complete else "inconclusive",
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": missing_evidence,
            "next_action": NEXT_ACTION if all_pairs_complete else "repair incomplete decision replay period pairs before L5 routing decision",
        },
        "runtime_contract_effect": {
            "decision_replay_runtime_observed": "observed_for_all_pairs" if all_pairs_complete else "partial",
            "standard_l4_completion": "completed_for_all_pairs_no_runtime_authority" if all_pairs_complete else "partial",
            "l5_continuation": "routing_decision_pending_no_candidate_claim",
            "locked_final_oos_b": "not_used",
            "runtime_authority": False,
            "economics_pass": False,
            "candidate": False,
            "goal_achieve": False,
        },
        "source_of_truth_paths": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), SOURCE_PAIR_INDEX.as_posix()],
        "writer_owned_outputs": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()],
        "provenance": {
            "source_inputs": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), SOURCE_PAIR_INDEX.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()],
            "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()],
            "environment_summary": {
                "python_executable": base.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(REPO_ROOT),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [ARTIFACT_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "pair_summary_index_and_closeout_written_from_runtime_execution_index_and_attempt_telemetry_summaries",
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
            "Decision replay pair judgment is an observation gate, not candidate selection.",
            "Action telemetry and tester reports cannot create economics pass, runtime authority, live readiness, or Goal Achieve.",
            "Writer-scope smoke is the default operating proof; broad pytest/full-regression is boundary or explicit-request only.",
        ],
        "unresolved_blockers": ["Wave02_execution_liquidity_decision_replay_L5_routing_decision_pending"],
        "reopen_conditions": [
            "rerun pair aggregation if a decision replay runtime attempt manifest, telemetry summary, or tester report receipt changes",
            "open L5 only with candidate-specific manifest and bounded evidence plan",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    return summary, pair_rows


def pair_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "direction_policy",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "validation_execution_observed",
        "research_oos_execution_observed",
        "both_period_roles_observed",
        "nonempty_execution_pair",
        "tester_report_pair_observed",
        "runtime_probe_pair_complete",
        "validation_row_count",
        "research_oos_row_count",
        "validation_open_action_count",
        "research_oos_open_action_count",
        "validation_close_action_count",
        "research_oos_close_action_count",
        "validation_open_failed_count",
        "research_oos_open_failed_count",
        "validation_open_rate",
        "research_oos_open_rate",
        "abs_open_rate_delta",
        "validation_open_failed_rate",
        "research_oos_open_failed_rate",
        "max_open_failed_rate",
        "validation_source_tradeable_count",
        "research_oos_source_tradeable_count",
        "validation_action_counts",
        "research_oos_action_counts",
        "source_proxy_judgment",
        "source_l4_score_l5_status",
        "source_l4_score_comparison_class",
        "decision_replay_comparison_class",
        "result_judgment",
        "l5_routing_status",
        "candidate_count",
        "l5_candidate_count",
        "claim_boundary",
        "next_action",
    ]


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "source_of_truth_paths": summary["source_of_truth_paths"],
        "writer_owned_outputs": summary["writer_owned_outputs"],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": summary["broad_validation_escalation_reason"],
        "writer_scope_self_check": summary.get("writer_scope_self_check"),
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
        "required_gate_coverage": {
            "passed": [
                "decision_replay_runtime_pair_index",
                "artifact_hash_registry_update",
                "final_claim_guard",
                "writer_scope_self_check",
            ],
            "missing": summary["judgment"]["missing_evidence"],
            "not_applicable": [
                "runtime_authority",
                "economics_pass",
                "selected_baseline",
                "goal_achieve",
                "live_readiness",
            ],
        },
    }


def upsert_artifact_registry(summary: dict[str, Any]) -> None:
    registry_path = REPO_ROOT / ARTIFACT_REGISTRY
    rows = base.read_csv_rows(registry_path) if registry_path.exists() else []
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
            "sha256": base.sha256(full),
            "size_bytes": str(full.stat().st_size),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": PAIR_SUMMARY.as_posix(),
            "consumer": NEXT_WORK_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "notes": notes,
        }

    put(
        "artifact_wave02_execution_liquidity_decision_replay_pair_judgment_summary_v0",
        "decision_replay_pair_judgment_summary",
        PAIR_SUMMARY,
        "Wave02 ELQ decision replay validation/research_oos pair judgment summary",
    )
    put(
        "artifact_wave02_execution_liquidity_decision_replay_pair_judgment_index_v0",
        "decision_replay_pair_judgment_index",
        PAIR_INDEX,
        "Wave02 ELQ decision replay pair-level action telemetry judgment index",
    )
    put(
        "artifact_wave02_execution_liquidity_decision_replay_pair_judgment_closeout_v0",
        "work_closeout",
        PAIR_CLOSEOUT,
        "Wave02 ELQ decision replay pair judgment closeout",
    )
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def next_work_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
        "verification_profile": "writer_scope_l5_routing_decision",
        "targets": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "acceptance_criteria": [
            "decide whether to open candidate-specific L5 work from decision replay pair evidence",
            "record candidate_count and l5_candidate_count explicitly before any candidate manifest exists",
            "do not claim selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
        "status": "wave02_execution_liquidity_decision_replay_l5_routing_decision_pending",
        "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()],
        "writer_owned_outputs": [
            "l5 routing decision summary/index/closeout or no-candidate closeout records",
        ],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": "none_pair_judgment_progress_no_protected_claim",
        "writer_scope_self_check": summary.get("writer_scope_self_check"),
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "current_truth": {
            "decision_replay_pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "decision_replay_pair_judgment_index": PAIR_INDEX.as_posix(),
            "decision_replay_pair_judgment_status": summary["status"],
            "decision_replay_pair_judgment_counts": summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "unresolved_blockers": ["Wave02_execution_liquidity_decision_replay_L5_routing_decision_pending"],
        "unresolved_blockers_or_none": ["Wave02_execution_liquidity_decision_replay_L5_routing_decision_pending"],
        "next_action_or_reopen_condition": NEXT_ACTION,
        "reopen_conditions": ["open L5 only with candidate-specific manifest and bounded evidence plan"],
        "missing_material_if_relevant": [
            "candidate_specific_L5_manifest_not_opened",
            "economics_metrics_not_parsed_or_claimable",
        ],
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 ELQ decision replay L5 routing decision pending; no candidate claim.",
    }


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_payload(summary)
    base.write_yaml(REPO_ROOT / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = next_work["status"]
    resume["active_phase"] = next_work["status"]
    resume["active_work_item_id"] = next_work["work_item_id"]
    resume["claim_boundary"] = next_work["claim_boundary"]
    resume["next_action"] = next_work["next_action"]
    resume["unresolved_blockers"] = list(next_work["unresolved_blockers"])
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
    resume["next_work_item"] = {"work_item_id": next_work["work_item_id"], "path": NEXT_WORK_ITEM.as_posix()}
    base.write_yaml(REPO_ROOT / RESUME_CURSOR, resume)

    goal = base.load_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = next_work["status"]
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": next_work["work_item_id"],
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 ELQ decision replay L5 routing decision pending; no candidate claim.",
    }
    wave02 = goal.setdefault("wave02_execution_liquidity_campaign", {})
    wave02["decision_replay_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    wave02["decision_replay_pair_judgment_status"] = summary["status"]
    wave02["decision_replay_pair_judgment_counts"] = summary["counts"]
    wave02["candidate_count"] = 0
    wave02["l5_candidate_count"] = 0
    wave02["next_work_item"] = next_work["work_item_id"]
    base.write_yaml(REPO_ROOT / GOAL_MANIFEST, goal)

    campaign = base.load_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = summary["ended_at_utc"]
    campaign["status"] = next_work["status"]
    campaign["claim_boundary"] = next_work["claim_boundary"]
    campaign["candidate_count"] = 0
    campaign["l5_candidate_count"] = 0
    campaign["next_action"] = next_work["next_action"]
    replay = campaign.setdefault("l4_follow_through", {}).setdefault("decision_replay", {})
    replay["pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    replay["pair_judgment_index"] = PAIR_INDEX.as_posix()
    replay["pair_judgment_status"] = summary["status"]
    replay["pair_judgment_counts"] = summary["counts"]
    campaign.setdefault("runtime_follow_through", {})["decision_replay_pair_judgment"] = {
        "summary": PAIR_SUMMARY.as_posix(),
        "index": PAIR_INDEX.as_posix(),
        "status": summary["status"],
        "counts": summary["counts"],
        "claim_boundary": summary["claim_boundary"],
    }
    base.write_yaml(REPO_ROOT / CAMPAIGN_MANIFEST, campaign)

    workspace = base.load_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace.setdefault("active_campaign", {})["status"] = next_work["status"]
    workspace["active_work_item"] = {"work_item_id": next_work["work_item_id"], "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = next_work["claim_boundary"]
    workspace["next_action"] = next_work["next_action"]
    workspace["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave02_execution_liquidity_decision_replay_pair_judgment"] = summary["counts"]
    elq = workspace.setdefault("wave02_execution_liquidity_l4_materialization", {})
    elq["status"] = next_work["status"]
    elq["claim_boundary"] = next_work["claim_boundary"]
    elq["decision_replay_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    elq["decision_replay_pair_judgment_index"] = PAIR_INDEX.as_posix()
    elq["decision_replay_pair_judgment_status"] = summary["status"]
    elq["decision_replay_pair_judgment_counts"] = summary["counts"]
    elq["candidate_count"] = 0
    elq["l5_candidate_count"] = 0
    base.write_yaml(REPO_ROOT / WORKSPACE_STATE, workspace)

    if (REPO_ROOT / GOAL_REGISTRY).exists():
        goal_rows = base.read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = next_work["status"]
                row["next_work_item"] = next_work["work_item_id"]
                row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
        if goal_rows:
            base.write_csv(REPO_ROOT / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def write_records(summary: dict[str, Any], rows: list[dict[str, Any]], *, write_control_records: bool) -> None:
    base.write_yaml(REPO_ROOT / PAIR_SUMMARY, summary)
    base.write_csv(REPO_ROOT / PAIR_INDEX, rows, pair_index_fieldnames())
    base.write_yaml(REPO_ROOT / PAIR_CLOSEOUT, build_closeout(summary))
    upsert_artifact_registry(summary)
    if write_control_records:
        update_control_records(summary)


def writer_scope_self_check(summary: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [PAIR_SUMMARY, PAIR_INDEX, PAIR_CLOSEOUT]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    if (REPO_ROOT / PAIR_INDEX).exists():
        rows = base.read_csv_rows(REPO_ROOT / PAIR_INDEX)
        if len(rows) != summary["counts"]["cell_pair_count"]:
            failures.append("pair_index_row_count_mismatch")
    if summary["counts"].get("candidate_count") or summary["counts"].get("l5_candidate_count"):
        failures.append("candidate_count_present_before_candidate_manifest")
    registry_rows = base.read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    by_id = {row.get("artifact_id"): row for row in registry_rows}
    for artifact_id, path in [
        ("artifact_wave02_execution_liquidity_decision_replay_pair_judgment_summary_v0", PAIR_SUMMARY),
        ("artifact_wave02_execution_liquidity_decision_replay_pair_judgment_index_v0", PAIR_INDEX),
        ("artifact_wave02_execution_liquidity_decision_replay_pair_judgment_closeout_v0", PAIR_CLOSEOUT),
    ]:
        row = by_id.get(artifact_id)
        if not row:
            failures.append(f"missing_registry:{artifact_id}")
            continue
        if row.get("sha256") != base.sha256(REPO_ROOT / path):
            failures.append(f"registry_hash_mismatch:{artifact_id}")
    return {
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "claim_boundary": CLAIM_BOUNDARY,
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "next_action_or_reopen_condition": NEXT_ACTION,
    }


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/aggregate_wave02_execution_liquidity_decision_replay_pair_judgments.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave02 ELQ decision replay runtime pair judgments.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    runtime_writer.configure_base()
    args = parse_args(argv)
    started_at = utc_now()
    command_argv = build_command_argv(args)
    summary, pair_rows = aggregate_pairs(started_at, command_argv)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "cell_pair_count": len(pair_rows),
                    "counts": summary["counts"],
                    "claim_boundary": summary["claim_boundary"],
                },
                indent=2,
            )
        )
        return 0
    write_records(summary, pair_rows, write_control_records=args.write_control_records)
    self_check = writer_scope_self_check(summary)
    summary["writer_scope_self_check"] = self_check
    base.write_yaml(REPO_ROOT / PAIR_SUMMARY, summary)
    base.write_yaml(REPO_ROOT / PAIR_CLOSEOUT, build_closeout(summary))
    upsert_artifact_registry(summary)
    if args.write_control_records:
        update_control_records(summary)
    self_check = writer_scope_self_check(summary)
    if self_check["status"] != "passed":
        print(
            json.dumps(
                {
                    "status": "writer_scope_self_check_failed",
                    "self_check": self_check,
                    "summary": PAIR_SUMMARY.as_posix(),
                    "claim_boundary": summary["claim_boundary"],
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": PAIR_SUMMARY.as_posix(),
                "pair_index": PAIR_INDEX.as_posix(),
                "counts": summary["counts"],
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
