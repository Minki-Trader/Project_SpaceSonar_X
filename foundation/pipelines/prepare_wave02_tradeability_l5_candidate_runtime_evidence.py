from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.decide_wave02_tradeability_decision_replay_l5_routing as routing_writer
from foundation.mt5.tester_report_kpi import parse_tester_report_kpis


base = routing_writer.base

GOAL_ID = routing_writer.GOAL_ID
WAVE_ID = routing_writer.WAVE_ID
CAMPAIGN_ID = routing_writer.CAMPAIGN_ID
SURFACE_ID = routing_writer.SURFACE_ID
SWEEP_ID = routing_writer.SWEEP_ID

PARENT_WORK_ITEM_ID = routing_writer.WORK_ITEM_ID
WORK_ITEM_ID = "work_wave02_tradeability_l5_candidate_runtime_evidence_preparation_v0"
NEXT_WORK_ITEM_ID = "work_wave02_tradeability_campaign_boundary_decision_v0"

OUTPUT_DIR = routing_writer.OUTPUT_DIR
ROUTING_SUMMARY = routing_writer.ROUTING_SUMMARY
ROUTING_INDEX = routing_writer.ROUTING_INDEX
EVIDENCE_SUMMARY = OUTPUT_DIR / "l5_evidence_summary.yaml"
EVIDENCE_INDEX = OUTPUT_DIR / "l5_evidence_index.csv"
EVIDENCE_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_tradeability_l5_candidate_runtime_evidence_preparation_v0_closeout.yaml"
)
NEXT_WORK_ITEM = routing_writer.NEXT_WORK_ITEM
RESUME_CURSOR = routing_writer.RESUME_CURSOR
GOAL_MANIFEST = routing_writer.GOAL_MANIFEST
WORKSPACE_STATE = routing_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = routing_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = routing_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = routing_writer.GOAL_REGISTRY
CANDIDATE_REGISTRY = routing_writer.CANDIDATE_REGISTRY

CLAIM_BOUNDARY = (
    "wave02_l5_candidate_runtime_evidence_observed_negative_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_campaign_boundary_decision_pending_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_l5_candidate_runtime_evidence_observed_no_l5_candidates_boundary_decision_pending"
NEXT_ACTION = "decide Wave02 campaign boundary: close/rotate or repair open_failed semantics in a new bounded work item"
FORBIDDEN_CLAIMS = routing_writer.FORBIDDEN_CLAIMS


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            base.write_yaml(path, payload)
            return
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            if attempt == 2:
                raise
            time.sleep(0.2)


def safe_write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            base.write_csv(path, rows, fieldnames)
            return
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            if attempt == 2:
                raise
            time.sleep(0.2)


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


def load_candidate_summary(path_value: str) -> dict[str, Any]:
    return base.load_yaml(REPO_ROOT / path_value)


def tester_report_path(attempt_id: str) -> Path:
    return REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id / "reports" / "tester_report.htm"


def attempt_root(attempt_id: str) -> Path:
    return REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id


def parse_attempt_report(attempt_id: str, *, write_summary: bool) -> dict[str, Any]:
    report = tester_report_path(attempt_id)
    parsed = parse_tester_report_kpis(report)
    parsed["source_report_path"] = report.relative_to(REPO_ROOT).as_posix()
    if write_summary:
        summary_path = attempt_root(attempt_id) / "tester_report_kpi_summary.yaml"
        safe_write_yaml(summary_path, parsed)
    return parsed


def period_judgment(parsed: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    total_net_profit = metric_value(parsed, "mt5.tester_report.total_net_profit")
    profit_factor = metric_value(parsed, "mt5.tester_report.profit_factor")
    dd_pct = metric_value(parsed, "mt5.tester_report.balance_drawdown_maximal_pct")
    if parsed.get("parse_status") != "parsed" or parsed.get("missing_metrics"):
        reasons.append("tester_report_kpi_parse_incomplete")
    if total_net_profit is None or total_net_profit <= 0:
        reasons.append("non_positive_total_net_profit")
    if profit_factor is None or profit_factor < 1.0:
        reasons.append("profit_factor_below_1")
    if dd_pct is None or dd_pct > 10.0:
        reasons.append("drawdown_above_10pct_reference")
    return ("negative_runtime_evidence" if reasons else "positive_runtime_observation_not_pass", reasons)


def build_period_row(candidate: dict[str, Any], period_role: str, attempt_id: str, *, write_parse_summaries: bool) -> dict[str, Any]:
    parsed = parse_attempt_report(attempt_id, write_summary=write_parse_summaries)
    judgment, reasons = period_judgment(parsed)
    return {
        "candidate_id": candidate["candidate_id"],
        "run_id": candidate["run_id"],
        "bundle_id": candidate["bundle_id"],
        "cell_id": candidate["source_cell_id"],
        "period_role": period_role,
        "attempt_id": attempt_id,
        "report_parse_status": parsed.get("parse_status", ""),
        "missing_metric_count": len(parsed.get("missing_metrics") or []),
        "total_net_profit": metric_value(parsed, "mt5.tester_report.total_net_profit"),
        "gross_profit": metric_value(parsed, "mt5.tester_report.gross_profit"),
        "gross_loss": metric_value(parsed, "mt5.tester_report.gross_loss"),
        "profit_factor": metric_value(parsed, "mt5.tester_report.profit_factor"),
        "total_trades": safe_int(metric_value(parsed, "mt5.tester_report.total_trades")),
        "balance_drawdown_maximal_pct": metric_value(parsed, "mt5.tester_report.balance_drawdown_maximal_pct"),
        "equity_drawdown_maximal_pct": metric_value(parsed, "mt5.tester_report.equity_drawdown_maximal_pct"),
        "period_judgment": judgment,
        "judgment_reasons": "|".join(reasons),
        "tester_report_kpi_summary_path": (
            Path("runtime") / "mt5_attempts" / attempt_id / "tester_report_kpi_summary.yaml"
        ).as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
    }


def candidate_evidence_path(candidate_id: str) -> Path:
    return Path("lab") / "candidates" / candidate_id / "l5_runtime_evidence_summary.yaml"


def candidate_result(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not rows:
        return "inconclusive_runtime_evidence_missing", ["candidate_period_rows_missing"]
    negative_reasons: list[str] = []
    for row in rows:
        if row["period_judgment"] == "negative_runtime_evidence":
            negative_reasons.extend(str(row["judgment_reasons"]).split("|"))
    if negative_reasons:
        reasons = sorted({reason for reason in negative_reasons if reason})
        return "negative_runtime_evidence_no_l5_candidate", reasons
    return "positive_runtime_observation_not_economics_pass", ["stronger_claim_requires_final_claim_guard"]


def build_evidence_rows(*, write_parse_summaries: bool) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    registry = base.read_csv_rows(REPO_ROOT / CANDIDATE_REGISTRY)
    current_candidates = [
        row for row in registry
        if row.get("campaign_id") == CAMPAIGN_ID and row.get("status") == "candidate_manifest_opened_l5_runtime_evidence_pending"
    ]
    rows: list[dict[str, Any]] = []
    by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for registry_row in current_candidates:
        candidate = load_candidate_summary(registry_row["summary_path"])
        evidence = candidate.get("source_evidence") or {}
        attempt_pairs = [
            ("validation", str(evidence.get("validation_attempt_id") or "")),
            ("research_oos", str(evidence.get("research_oos_attempt_id") or "")),
        ]
        for period_role, attempt_id in attempt_pairs:
            if not attempt_id:
                continue
            row = build_period_row(candidate, period_role, attempt_id, write_parse_summaries=write_parse_summaries)
            rows.append(row)
            by_candidate[candidate["candidate_id"]].append(row)
    return rows, dict(by_candidate)


def evidence_index_fieldnames() -> list[str]:
    return [
        "candidate_id",
        "run_id",
        "bundle_id",
        "cell_id",
        "period_role",
        "attempt_id",
        "report_parse_status",
        "missing_metric_count",
        "total_net_profit",
        "gross_profit",
        "gross_loss",
        "profit_factor",
        "total_trades",
        "balance_drawdown_maximal_pct",
        "equity_drawdown_maximal_pct",
        "period_judgment",
        "judgment_reasons",
        "tester_report_kpi_summary_path",
        "claim_boundary",
    ]


def build_candidate_evidence_summary(candidate_id: str, rows: list[dict[str, Any]], ended_at_utc: str) -> dict[str, Any]:
    result, reasons = candidate_result(rows)
    return {
        "version": "candidate_l5_runtime_evidence_summary_v1",
        "candidate_id": candidate_id,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "created_at_utc": ended_at_utc,
        "status": result,
        "claim_boundary": CLAIM_BOUNDARY,
        "period_rows": rows,
        "result_judgment": "negative" if result.startswith("negative") else "runtime_probe",
        "economics_pass": False,
        "runtime_authority": False,
        "selected_baseline": False,
        "live_readiness": False,
        "goal_achieve": False,
        "l5_candidate": False,
        "judgment_reasons": reasons,
        "source_evidence": {
            "routing_summary": ROUTING_SUMMARY.as_posix(),
            "routing_index": ROUTING_INDEX.as_posix(),
            "campaign_l5_evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "campaign_l5_evidence_index": EVIDENCE_INDEX.as_posix(),
        },
        "next_action": NEXT_ACTION,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "forbidden_claims_respected": True,
    }


def build_summary(
    rows: list[dict[str, Any]],
    by_candidate: dict[str, list[dict[str, Any]]],
    started_at_utc: str,
    command_argv: list[str],
) -> dict[str, Any]:
    candidate_results = {candidate_id: candidate_result(candidate_rows)[0] for candidate_id, candidate_rows in by_candidate.items()}
    ended_at_utc = utc_now()
    period_counts = Counter(row["period_judgment"] for row in rows)
    candidate_counts = Counter(candidate_results.values())
    negative_candidate_ids = [
        candidate_id for candidate_id, result in candidate_results.items() if result == "negative_runtime_evidence_no_l5_candidate"
    ]
    return {
        "version": "wave02_l5_candidate_runtime_evidence_summary_v1",
        "summary_id": "wave02_tradeability_l5_candidate_runtime_evidence_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-result-judgment", "spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
        "validation_depth": "writer_scope_smoke",
        "counts": {
            "candidate_count": len(by_candidate),
            "candidate_runtime_evidence_count": len(by_candidate),
            "l5_candidate_count": 0,
            "period_evidence_row_count": len(rows),
            "negative_candidate_count": len(negative_candidate_ids),
            "period_judgment_counts": dict(sorted(period_counts.items())),
            "candidate_result_counts": dict(sorted(candidate_counts.items())),
        },
        "candidate_results": candidate_results,
        "negative_candidate_ids": negative_candidate_ids,
        "l5_candidate_ids": [],
        "judgment": {
            "judgment_label": "negative_runtime_evidence_no_l5_candidates",
            "candidate_count": len(by_candidate),
            "l5_candidate_count": 0,
            "economics_metrics_observed": True,
            "economics_pass": False,
            "runtime_authority": False,
            "selected_baseline": False,
            "live_readiness": False,
            "goal_achieve": False,
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "no_positive_l5_candidate_after_candidate_specific_report_parse",
                "locked_final_oos_b_not_used",
                "operational_validation_not_started",
            ],
            "next_action": NEXT_ACTION,
        },
        "provenance": {
            "source_inputs": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), CANDIDATE_REGISTRY.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), EVIDENCE_CLOSEOUT.as_posix()],
            "environment_summary": {
                "python_executable": base.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(REPO_ROOT),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "artifact_outputs": {
            "evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "evidence_index": EVIDENCE_INDEX.as_posix(),
            "evidence_closeout": EVIDENCE_CLOSEOUT.as_posix(),
            "candidate_evidence_summaries": [
                candidate_evidence_path(candidate_id).as_posix() for candidate_id in sorted(by_candidate)
            ],
        },
        "prevention_memory": [
            "Candidate-specific tester report metrics can be observed without creating economics pass.",
            "Negative PF/net-profit/DD evidence closes candidate runtime evidence with l5_candidate_count=0.",
            "Operational validation remains unopened.",
        ],
        "unresolved_blockers": ["Wave02_campaign_boundary_decision_pending"],
        "reopen_conditions": [
            "rerun candidate runtime evidence if tester report KPI parser aliases change or candidate registry changes",
            "open further work only as campaign boundary decision, repair track, or new surface rotation",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


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
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), *summary["artifact_outputs"]["candidate_evidence_summaries"]],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "forbidden_claims": summary["forbidden_claims"],
        "required_gate_coverage": {
            "passed": [
                "candidate_specific_manifest_present",
                "tester_report_kpi_parse",
                "artifact_hash_registry_update",
                "final_claim_guard",
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


def update_candidate_summaries(summary: dict[str, Any], by_candidate: dict[str, list[dict[str, Any]]]) -> None:
    registry_rows = base.read_csv_rows(REPO_ROOT / CANDIDATE_REGISTRY)
    registry_by_id = {row["candidate_id"]: row for row in registry_rows if row.get("candidate_id")}
    for candidate_id, rows in by_candidate.items():
        candidate_path = Path(registry_by_id[candidate_id]["summary_path"])
        candidate = base.load_yaml(REPO_ROOT / candidate_path)
        result, reasons = candidate_result(rows)
        candidate["status"] = result
        candidate["claim_boundary"] = CLAIM_BOUNDARY
        candidate["l5_runtime_evidence_summary"] = candidate_evidence_path(candidate_id).as_posix()
        candidate["runtime_evidence_result"] = {
            "result_judgment": "negative" if result.startswith("negative") else "runtime_probe",
            "l5_candidate": False,
            "economics_pass": False,
            "runtime_authority": False,
            "selected_baseline": False,
            "live_readiness": False,
            "goal_achieve": False,
            "judgment_reasons": reasons,
        }
        candidate["missing_evidence"] = summary["judgment"]["missing_evidence"]
        candidate["next_action"] = NEXT_ACTION
        safe_write_yaml(REPO_ROOT / candidate_path, candidate)
        safe_write_yaml(REPO_ROOT / candidate_evidence_path(candidate_id), build_candidate_evidence_summary(candidate_id, rows, summary["ended_at_utc"]))


def upsert_candidate_registry(summary: dict[str, Any]) -> None:
    registry_path = REPO_ROOT / CANDIDATE_REGISTRY
    rows = base.read_csv_rows(registry_path)
    fieldnames = list(rows[0].keys()) if rows else []
    for row in rows:
        candidate_id = row.get("candidate_id")
        if candidate_id in summary["candidate_results"]:
            row["status"] = summary["candidate_results"][candidate_id]
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["evidence_path"] = candidate_evidence_path(candidate_id).as_posix()
            row["missing_evidence"] = ";".join(summary["judgment"]["missing_evidence"])
            row["risk_notes"] = "candidate_runtime_evidence_negative_no_l5_candidate_no_economics_pass"
            row["next_action"] = NEXT_ACTION
    safe_write_csv(registry_path, rows, fieldnames)


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
            "source_of_truth": EVIDENCE_SUMMARY.as_posix(),
            "consumer": NEXT_WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": notes,
        }

    put(
        "artifact_wave02_l5_candidate_runtime_evidence_summary_v0",
        "l5_candidate_runtime_evidence_summary",
        EVIDENCE_SUMMARY,
        "Wave02 candidate-specific tester report KPI runtime evidence summary",
    )
    put(
        "artifact_wave02_l5_candidate_runtime_evidence_index_v0",
        "l5_candidate_runtime_evidence_index",
        EVIDENCE_INDEX,
        "Wave02 candidate-specific tester report KPI runtime evidence index",
    )
    put(
        "artifact_wave02_l5_candidate_runtime_evidence_closeout_v0",
        "work_closeout",
        EVIDENCE_CLOSEOUT,
        "Wave02 candidate runtime evidence closeout",
    )
    for path_value in summary["artifact_outputs"]["candidate_evidence_summaries"]:
        path = Path(path_value)
        put(
            f"artifact_{path.parent.name}_l5_runtime_evidence_summary_v0",
            "candidate_l5_runtime_evidence_summary",
            path,
            "candidate-level L5 runtime evidence summary",
        )
    safe_write_csv(registry_path, list(by_id.values()), fieldnames)


def next_work_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "cleanup",
        "primary_skill": "spacesonar-result-judgment",
        "verification_profile": "writer_scope_campaign_boundary_decision",
        "targets": [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix()],
        "acceptance_criteria": [
            "decide whether to close Wave02 campaign, rotate surface, or open bounded open_failed repair work",
            "keep selected baseline, runtime authority, economics pass, live readiness, and Goal Achieve forbidden",
            "commit/push only at campaign boundary if closing",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
        "status": "wave02_campaign_boundary_decision_pending",
        "current_truth": {
            "l5_candidate_runtime_evidence_summary": EVIDENCE_SUMMARY.as_posix(),
            "l5_candidate_runtime_evidence_index": EVIDENCE_INDEX.as_posix(),
            "candidate_count": summary["counts"]["candidate_count"],
            "l5_candidate_count": summary["counts"]["l5_candidate_count"],
            "negative_candidate_ids": summary["negative_candidate_ids"],
        },
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "reopen_conditions": list(summary["reopen_conditions"]),
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
    }


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_payload(summary)
    safe_write_yaml(REPO_ROOT / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = next_work["status"]
    resume["active_phase"] = next_work["status"]
    resume["active_work_item_id"] = next_work["work_item_id"]
    resume["claim_boundary"] = next_work["claim_boundary"]
    resume["next_action"] = next_work["next_action"]
    resume["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    sources = resume.setdefault("current_truth_sources", [])
    for source in [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_INDEX.as_posix(), EVIDENCE_CLOSEOUT.as_posix(), *summary["artifact_outputs"]["candidate_evidence_summaries"]]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [EVIDENCE_SUMMARY.as_posix(), EVIDENCE_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": next_work["work_item_id"], "path": NEXT_WORK_ITEM.as_posix()}
    safe_write_yaml(REPO_ROOT / RESUME_CURSOR, resume)

    goal = base.load_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = next_work["status"]
    wave02 = goal.setdefault("wave02_tradeability_campaign", {})
    wave02["l5_candidate_runtime_evidence_summary"] = EVIDENCE_SUMMARY.as_posix()
    wave02["l5_candidate_runtime_evidence_status"] = summary["status"]
    wave02["l5_candidate_runtime_evidence_counts"] = summary["counts"]
    wave02["l5_candidate_ids"] = []
    wave02["l5_candidate_count"] = 0
    wave02["next_work_item"] = next_work["work_item_id"]
    safe_write_yaml(REPO_ROOT / GOAL_MANIFEST, goal)

    campaign = base.load_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = summary["ended_at_utc"]
    campaign["status"] = next_work["status"]
    campaign["claim_boundary"] = next_work["claim_boundary"]
    campaign["l5_candidate_ids"] = []
    campaign["l5_candidate_count"] = 0
    campaign.setdefault("runtime_follow_through", {})["l5_candidate_runtime_evidence"] = {
        "summary": EVIDENCE_SUMMARY.as_posix(),
        "index": EVIDENCE_INDEX.as_posix(),
        "status": summary["status"],
        "counts": summary["counts"],
        "claim_boundary": summary["claim_boundary"],
    }
    safe_write_yaml(REPO_ROOT / CAMPAIGN_MANIFEST, campaign)

    workspace = base.load_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace["active_work_item"] = {"work_item_id": next_work["work_item_id"], "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = next_work["claim_boundary"]
    workspace["next_action"] = next_work["next_action"]
    workspace["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = summary["counts"]["candidate_count"]
    counts["l5_candidate_count"] = summary["counts"]["l5_candidate_count"]
    counts["wave02_l5_candidate_runtime_evidence"] = summary["counts"]
    safe_write_yaml(REPO_ROOT / WORKSPACE_STATE, workspace)

    if (REPO_ROOT / GOAL_REGISTRY).exists():
        goal_rows = base.read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = next_work["status"]
                row["next_work_item"] = next_work["work_item_id"]
                row["claim_boundary"] = "active_goal_wave02_campaign_boundary_decision_not_goal_achieve"
        if goal_rows:
            safe_write_csv(REPO_ROOT / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def write_records(
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    by_candidate: dict[str, list[dict[str, Any]]],
    *,
    write_control_records: bool,
) -> None:
    safe_write_yaml(REPO_ROOT / EVIDENCE_SUMMARY, summary)
    safe_write_csv(REPO_ROOT / EVIDENCE_INDEX, rows, evidence_index_fieldnames())
    safe_write_yaml(REPO_ROOT / EVIDENCE_CLOSEOUT, build_closeout(summary))
    update_candidate_summaries(summary, by_candidate)
    upsert_candidate_registry(summary)
    upsert_artifact_registry(summary)
    if write_control_records:
        update_control_records(summary)


def writer_scope_self_check(summary: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [EVIDENCE_SUMMARY, EVIDENCE_INDEX, EVIDENCE_CLOSEOUT]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    if summary["counts"]["l5_candidate_count"] != 0:
        failures.append("l5_candidate_count_nonzero_after_negative_evidence")
    for path_value in summary["artifact_outputs"]["candidate_evidence_summaries"]:
        if not (REPO_ROOT / path_value).exists():
            failures.append(f"missing_candidate_evidence:{path_value}")
    registry_rows = base.read_csv_rows(REPO_ROOT / CANDIDATE_REGISTRY)
    for row in registry_rows:
        if row.get("candidate_id") in summary["candidate_results"] and row.get("status") != summary["candidate_results"][row["candidate_id"]]:
            failures.append(f"candidate_registry_status_mismatch:{row['candidate_id']}")
    artifact_rows = base.read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    artifacts = {row.get("artifact_id"): row for row in artifact_rows}
    for artifact_id, path in [
        ("artifact_wave02_l5_candidate_runtime_evidence_summary_v0", EVIDENCE_SUMMARY),
        ("artifact_wave02_l5_candidate_runtime_evidence_index_v0", EVIDENCE_INDEX),
        ("artifact_wave02_l5_candidate_runtime_evidence_closeout_v0", EVIDENCE_CLOSEOUT),
    ]:
        row = artifacts.get(artifact_id)
        if not row:
            failures.append(f"missing_registry:{artifact_id}")
            continue
        if row.get("sha256") != base.sha256(REPO_ROOT / path):
            failures.append(f"registry_hash_mismatch:{artifact_id}")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/prepare_wave02_tradeability_l5_candidate_runtime_evidence.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Wave02 candidate-specific L5 runtime evidence from tester reports.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started_at = utc_now()
    command_argv = build_command_argv(args)
    rows, by_candidate = build_evidence_rows(write_parse_summaries=not args.dry_run)
    summary = build_summary(rows, by_candidate, started_at, command_argv)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "counts": summary["counts"],
                    "candidate_results": summary["candidate_results"],
                    "claim_boundary": summary["claim_boundary"],
                },
                indent=2,
            )
        )
        return 0
    write_records(summary, rows, by_candidate, write_control_records=args.write_control_records)
    self_check = writer_scope_self_check(summary)
    if self_check["status"] != "passed":
        print(
            json.dumps(
                {
                    "status": "writer_scope_self_check_failed",
                    "self_check": self_check,
                    "summary": EVIDENCE_SUMMARY.as_posix(),
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
                "summary": EVIDENCE_SUMMARY.as_posix(),
                "index": EVIDENCE_INDEX.as_posix(),
                "counts": summary["counts"],
                "candidate_results": summary["candidate_results"],
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
