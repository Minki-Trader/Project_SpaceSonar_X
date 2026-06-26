from __future__ import annotations

import argparse
import csv
import hashlib
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.mt5.tester_report_kpi import parse_tester_report_kpis  # noqa: E402


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
PARENT_WORK_ITEM_ID = "work_wave01_event_barrier_l4_materialization_preflight_v0"
WORK_ITEM_ID = "work_wave01_event_barrier_l4_decision_replay_judgment_v0"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
SURFACE_ID = "surface_us100_event_barrier_decision_surface_v0"
HYPOTHESIS_ID = "hyp_us100_event_barrier_decision_surface_v0"
INITIAL_DEPOSIT = 500.0

CAMPAIGN_ROOT = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0")
L4_DIR = CAMPAIGN_ROOT / "l4_follow_through"
DECISION_REPLAY_DIR = L4_DIR / "decision_replay"
EXECUTION_INDEX = DECISION_REPLAY_DIR / "runtime_execution_index.csv"
EXECUTION_SUMMARY = DECISION_REPLAY_DIR / "runtime_execution_summary.yaml"
SOURCE_PAIR_INDEX = L4_DIR / "l4_pair_judgment_index.csv"
JUDGMENT_SUMMARY = DECISION_REPLAY_DIR / "judgment_summary.yaml"
JUDGMENT_INDEX = DECISION_REPLAY_DIR / "judgment_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_event_barrier_l4_decision_replay_judgment_v0_closeout.yaml"
)
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative/neg_wave01_event_barrier_score_band_decision_replay_loss_v0.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
NEGATIVE_MEMORY_REGISTRY = Path("docs/registers/negative_memory_registry.csv")

CLAIM_BOUNDARY = (
    "wave01_event_barrier_decision_replay_judgment_log_balance_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)
NEGATIVE_MEMORY_ID = "neg_wave01_event_barrier_score_band_decision_replay_loss_v0"


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


def rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def artifact_ref(path: Path, repo_root: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else repo_root / path
    return {
        "path": rel(full, repo_root),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle)
    return loaded or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def redact_path(value: str) -> str:
    redacted = value
    for env_name, token in {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


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


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_float(value: Any) -> float | None:
    try:
        if value in {"", None}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int:
    try:
        if value in {"", None}:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def balance_delta(final_balance: float | None, *, initial_deposit: float = INITIAL_DEPOSIT) -> float | None:
    if final_balance is None:
        return None
    return round(final_balance - initial_deposit, 2)


def tester_report_metrics(repo_root: Path, row: dict[str, str]) -> dict[str, str]:
    report_value = row.get("tester_report_path")
    if not report_value:
        return {}
    report_path = repo_root / report_value
    if not report_path.exists():
        return {}
    parsed = parse_tester_report_kpis(report_path)
    metrics = parsed.get("metrics") or {}

    def value(metric_id: str) -> str:
        metric = metrics.get(metric_id) or {}
        return str(metric.get("metric_value", ""))

    return {
        "total_trades": value("mt5.tester_report.total_trades"),
        "profit_factor": value("mt5.tester_report.profit_factor"),
        "total_net_profit": value("mt5.tester_report.total_net_profit"),
        "equity_drawdown_maximal_pct": value("mt5.tester_report.equity_drawdown_maximal_pct"),
    }


def classify_decision_pair(
    validation_final_balance: float | None,
    research_oos_final_balance: float | None,
    *,
    tester_report_pair_observed: bool,
    open_failed_count: int,
) -> dict[str, str]:
    if validation_final_balance is None or research_oos_final_balance is None:
        return {
            "final_balance_pair_class": "final_balance_missing",
            "result_judgment": "inconclusive",
            "l5_routing_status": "no_l5_missing_tester_log_balance",
            "comparison_class": "runtime_decision_balance_missing",
            "divergence_judgment": "inconclusive_missing_balance_evidence",
            "next_action": "repair tester log/report parsing before any L5 decision",
        }
    if validation_final_balance < INITIAL_DEPOSIT and research_oos_final_balance < INITIAL_DEPOSIT:
        return {
            "final_balance_pair_class": "loss_in_validation_and_research_oos",
            "result_judgment": "negative",
            "l5_routing_status": "no_l5_decision_replay_loss_observed",
            "comparison_class": "proxy_preserved_clue_runtime_decision_loss_observed",
            "divergence_judgment": "mt5_decision_replay_negative_under_score_band_side",
            "next_action": "record negative memory and rotate to a new surface or genuinely new decision policy; do not continue this recipe to L5",
        }
    if validation_final_balance >= INITIAL_DEPOSIT and research_oos_final_balance >= INITIAL_DEPOSIT:
        l5_status = (
            "l5_review_required_report_equity_or_open_failed_audit"
            if (not tester_report_pair_observed or open_failed_count > 0)
            else "l5_candidate_review_required_not_auto_candidate"
        )
        return {
            "final_balance_pair_class": "non_loss_in_validation_and_research_oos",
            "result_judgment": "preserved_clue",
            "l5_routing_status": l5_status,
            "comparison_class": "proxy_preserved_clue_runtime_decision_non_loss_observed",
            "divergence_judgment": "mt5_decision_replay_requires_report_equity_confirmation",
            "next_action": "open L5 review only after tester report/equity evidence and open-failed audit are present",
        }
    return {
        "final_balance_pair_class": "mixed_validation_research_oos_balance",
        "result_judgment": "inconclusive",
        "l5_routing_status": "no_l5_mixed_period_balance",
        "comparison_class": "proxy_preserved_clue_runtime_decision_mixed_observed",
        "divergence_judgment": "period_instability_observed",
        "next_action": "record instability and redesign decision policy before L5",
    }


def source_pair_by_cell(repo_root: Path) -> dict[str, dict[str, str]]:
    if not (repo_root / SOURCE_PAIR_INDEX).exists():
        return {}
    return {row["cell_id"]: row for row in read_csv_rows(repo_root / SOURCE_PAIR_INDEX)}


def group_execution_rows(repo_root: Path) -> dict[str, dict[str, dict[str, str]]]:
    rows = read_csv_rows(repo_root / EXECUTION_INDEX)
    grouped: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        grouped[row["cell_id"]][row["period_role"]] = row
    return grouped


def evidence_paths_for(validation: dict[str, str], research: dict[str, str]) -> list[str]:
    paths = [
        EXECUTION_SUMMARY.as_posix(),
        EXECUTION_INDEX.as_posix(),
        SOURCE_PAIR_INDEX.as_posix(),
    ]
    for row in [validation, research]:
        for key in ["terminal_run_summary_path", "execution_telemetry_summary_path", "tester_log_summary_path"]:
            value = row.get(key)
            if value:
                paths.append(value)
        report_value = row.get("tester_report_path")
        if report_value:
            paths.append(report_value)
    return paths


def build_judgment_rows(repo_root: Path) -> list[dict[str, Any]]:
    source_pairs = source_pair_by_cell(repo_root)
    grouped = group_execution_rows(repo_root)
    rows: list[dict[str, Any]] = []
    for cell_id in sorted(grouped):
        validation = grouped[cell_id].get("validation", {})
        research = grouped[cell_id].get("research_oos", {})
        anchor = validation or research
        source = source_pairs.get(cell_id, {})
        validation_balance = as_float(validation.get("tester_final_balance"))
        research_balance = as_float(research.get("tester_final_balance"))
        validation_open_failed = as_int(validation.get("open_failed_count"))
        research_open_failed = as_int(research.get("open_failed_count"))
        total_open_failed = validation_open_failed + research_open_failed
        tester_report_pair_observed = boolish(validation.get("tester_report_observed")) and boolish(
            research.get("tester_report_observed")
        )
        validation_report = tester_report_metrics(repo_root, validation)
        research_report = tester_report_metrics(repo_root, research)
        tester_report_kpi_pair_observed = bool(
            validation_report.get("total_trades") and research_report.get("total_trades")
        )
        classification = classify_decision_pair(
            validation_balance,
            research_balance,
            tester_report_pair_observed=tester_report_pair_observed,
            open_failed_count=total_open_failed,
        )
        missing = ["locked_final_oos_b_not_used"]
        if not tester_report_pair_observed:
            missing.append("tester_report_missing")
        if tester_report_pair_observed and not tester_report_kpi_pair_observed:
            missing.append("tester_report_kpi_parse_missing")
        if not tester_report_pair_observed or not tester_report_kpi_pair_observed:
            missing.append("pf_dd_trade_list_metrics_missing")
        if total_open_failed:
            missing.append("open_failed_actions_observed_requires_execution_audit_before_L5")
        prevention = [
            "preserved score-band clue does not imply tradeability under direct score-band replay",
            "score_band_side decision mapping produced validation/research_oos loss for this Wave01 direct-trade subset",
            "tester report PF/DD/trade metrics can support observation but cannot create economics pass without a separate review boundary",
            "open_failed actions are runtime friction evidence and must be audited before any future L5 review",
        ]
        rows.append(
            {
                "cell_id": cell_id,
                "run_id": anchor.get("run_id", ""),
                "bundle_id": anchor.get("bundle_id", ""),
                "validation_attempt_id": validation.get("attempt_id", ""),
                "research_oos_attempt_id": research.get("attempt_id", ""),
                "direction_policy": anchor.get("direction_policy", ""),
                "decision_family": source.get("decision_family", ""),
                "source_proxy_judgment": source.get("proxy_judgment", ""),
                "validation_final_balance": validation_balance if validation_balance is not None else "",
                "research_oos_final_balance": research_balance if research_balance is not None else "",
                "validation_balance_delta": balance_delta(validation_balance) if validation_balance is not None else "",
                "research_oos_balance_delta": balance_delta(research_balance) if research_balance is not None else "",
                "validation_open_action_count": validation.get("open_action_count", ""),
                "research_oos_open_action_count": research.get("open_action_count", ""),
                "validation_close_action_count": validation.get("close_action_count", ""),
                "research_oos_close_action_count": research.get("close_action_count", ""),
                "validation_open_failed_count": validation_open_failed,
                "research_oos_open_failed_count": research_open_failed,
                "total_open_failed_count": total_open_failed,
                "validation_execution_telemetry_observed": str(boolish(validation.get("execution_telemetry_observed"))).lower(),
                "research_oos_execution_telemetry_observed": str(boolish(research.get("execution_telemetry_observed"))).lower(),
                "validation_tester_log_observed": str(boolish(validation.get("tester_log_observed"))).lower(),
                "research_oos_tester_log_observed": str(boolish(research.get("tester_log_observed"))).lower(),
                "validation_tester_report_observed": str(boolish(validation.get("tester_report_observed"))).lower(),
                "research_oos_tester_report_observed": str(boolish(research.get("tester_report_observed"))).lower(),
                "validation_report_total_trades": validation_report.get("total_trades", ""),
                "research_oos_report_total_trades": research_report.get("total_trades", ""),
                "validation_report_profit_factor": validation_report.get("profit_factor", ""),
                "research_oos_report_profit_factor": research_report.get("profit_factor", ""),
                "validation_report_total_net_profit": validation_report.get("total_net_profit", ""),
                "research_oos_report_total_net_profit": research_report.get("total_net_profit", ""),
                "validation_report_equity_dd_max_pct": validation_report.get("equity_drawdown_maximal_pct", ""),
                "research_oos_report_equity_dd_max_pct": research_report.get("equity_drawdown_maximal_pct", ""),
                "validation_terminal_timed_out": str(boolish(validation.get("terminal_timed_out"))).lower(),
                "research_oos_terminal_timed_out": str(boolish(research.get("terminal_timed_out"))).lower(),
                "both_period_roles_observed": str(bool(validation and research)).lower(),
                "both_tester_logs_observed": str(
                    boolish(validation.get("tester_log_observed")) and boolish(research.get("tester_log_observed"))
                ).lower(),
                "tester_report_pair_observed": str(tester_report_pair_observed).lower(),
                "final_balance_pair_class": classification["final_balance_pair_class"],
                "comparison_class": classification["comparison_class"],
                "divergence_judgment": classification["divergence_judgment"],
                "result_judgment": classification["result_judgment"],
                "l5_routing_status": classification["l5_routing_status"],
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": ";".join(evidence_paths_for(validation, research)),
                "missing_evidence": ";".join(missing),
                "prevention_memory": ";".join(prevention),
                "next_action": classification["next_action"],
            }
        )
    return rows


def judgment_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "direction_policy",
        "decision_family",
        "source_proxy_judgment",
        "validation_final_balance",
        "research_oos_final_balance",
        "validation_balance_delta",
        "research_oos_balance_delta",
        "validation_open_action_count",
        "research_oos_open_action_count",
        "validation_close_action_count",
        "research_oos_close_action_count",
        "validation_open_failed_count",
        "research_oos_open_failed_count",
        "total_open_failed_count",
        "validation_execution_telemetry_observed",
        "research_oos_execution_telemetry_observed",
        "validation_tester_log_observed",
        "research_oos_tester_log_observed",
        "validation_tester_report_observed",
        "research_oos_tester_report_observed",
        "validation_report_total_trades",
        "research_oos_report_total_trades",
        "validation_report_profit_factor",
        "research_oos_report_profit_factor",
        "validation_report_total_net_profit",
        "research_oos_report_total_net_profit",
        "validation_report_equity_dd_max_pct",
        "research_oos_report_equity_dd_max_pct",
        "validation_terminal_timed_out",
        "research_oos_terminal_timed_out",
        "both_period_roles_observed",
        "both_tester_logs_observed",
        "tester_report_pair_observed",
        "final_balance_pair_class",
        "comparison_class",
        "divergence_judgment",
        "result_judgment",
        "l5_routing_status",
        "claim_boundary",
        "evidence_paths",
        "missing_evidence",
        "prevention_memory",
        "next_action",
    ]


def build_negative_memory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    run_ids = sorted({str(row["run_id"]) for row in rows if row.get("run_id")})
    families = sorted({str(row["decision_family"]) for row in rows if row.get("decision_family")})
    return {
        "version": "negative_memory_v1",
        "memory_id": NEGATIVE_MEMORY_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "run_id": ";".join(run_ids),
        "failed_boundary": "wave01_score_band_side_decision_replay_validation_and_research_oos",
        "decision_families": families,
        "why_failed": (
            "All five direct-trade eligible Wave01 preserved-clue score-band decision replay pairs ended below "
            "the 500 USD tester deposit in both validation and research_oos tester-log final balances."
        ),
        "salvage_value": (
            "Confirms the MT5 score-band decision replay path can run and records that direct score-band replay "
            "is not automatically tradeable even when the proxy score observation was preserved as a clue."
        ),
        "reopen_condition": (
            "Reopen only with a genuinely new decision/risk/holding policy, report/equity parser evidence, "
            "or a new surface question; do not relabel the same score_band_side replay as a new candidate."
        ),
        "do_not_repeat_note": (
            "Do not promote Wave01 score_band_side decision replay to L5/candidate/economics without new "
            "decision-policy evidence, tester report/equity metrics, and open-failed execution audit."
        ),
        "evidence_path": JUDGMENT_SUMMARY.as_posix(),
        "storage_contract": {
            "source_of_truth": NEGATIVE_MEMORY_PATH.as_posix(),
            "registry_rows": [NEGATIVE_MEMORY_REGISTRY.as_posix()],
        },
        "claim_boundary": "negative_memory_no_candidate_no_economics_pass_no_runtime_authority",
    }


def build_summary(repo_root: Path, rows: list[dict[str, Any]], *, started_at: str, command_argv: list[str]) -> dict[str, Any]:
    ended_at = utc_now()
    judgment_counts = Counter(str(row["result_judgment"]) for row in rows)
    l5_counts = Counter(str(row["l5_routing_status"]) for row in rows)
    balance_counts = Counter(str(row["final_balance_pair_class"]) for row in rows)
    family_counts = Counter(str(row["decision_family"]) for row in rows)
    missing_counts = Counter(
        item
        for row in rows
        for item in str(row.get("missing_evidence", "")).split(";")
        if item
    )
    tester_report_kpi_pair_observed_count = sum(
        bool(row.get("validation_report_total_trades")) and bool(row.get("research_oos_report_total_trades"))
        for row in rows
    )
    total_open = sum(int(row["validation_open_action_count"] or 0) + int(row["research_oos_open_action_count"] or 0) for row in rows)
    total_close = sum(int(row["validation_close_action_count"] or 0) + int(row["research_oos_close_action_count"] or 0) for row in rows)
    total_open_failed = sum(int(row["total_open_failed_count"] or 0) for row in rows)
    all_report_kpis_observed = bool(rows) and tester_report_kpi_pair_observed_count == len(rows)
    return {
        "version": "wave01_event_barrier_decision_replay_judgment_summary_v1",
        "summary_id": "wave01_event_barrier_l4_decision_replay_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at,
        "ended_at_utc": ended_at,
        "status": "wave01_decision_replay_judgment_completed_no_l5_candidates",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "cell_pair_count": len(rows),
            "negative_count": judgment_counts.get("negative", 0),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "tester_log_pair_observed_count": sum(row["both_tester_logs_observed"] == "true" for row in rows),
            "tester_report_pair_observed_count": sum(row["tester_report_pair_observed"] == "true" for row in rows),
            "tester_report_kpi_pair_observed_count": tester_report_kpi_pair_observed_count,
            "loss_in_both_periods_count": balance_counts.get("loss_in_validation_and_research_oos", 0),
            "open_action_count": total_open,
            "close_action_count": total_close,
            "open_failed_count": total_open_failed,
            "terminal_timeout_pair_count": sum(
                row["validation_terminal_timed_out"] == "true" or row["research_oos_terminal_timed_out"] == "true"
                for row in rows
            ),
            "decision_family_counts": dict(sorted(family_counts.items())),
            "result_judgment_counts": dict(sorted(judgment_counts.items())),
            "l5_routing_status_counts": dict(sorted(l5_counts.items())),
            "final_balance_pair_class_counts": dict(sorted(balance_counts.items())),
        },
        "judgment": {
            "result_subject": "Wave01 preserved-clue score-band decision replay over validation and research_oos",
            "judgment_label": "negative",
            "metric_identity": (
                "MT5 tester-log final_balance plus parsed Strategy Tester report trades/PF/net/DD; "
                "observation only, no economics pass"
                if all_report_kpis_observed
                else "MT5 tester-log final_balance from score-band decision replay probes; tester report KPI parse incomplete"
            ),
            "comparison_baseline": "500 USD initial deposit under us100_m5_fpmarkets_tester_execution_v0",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": sorted(missing_counts),
            "next_action": (
                "Record negative memory, keep candidate count at zero, and rotate to a new multi-axis surface or "
                "a genuinely new decision-policy question. Do not continue score_band_side replay to L5."
            ),
        },
        "runtime_contract_effect": {
            "runtime_level": "L4_split_runtime_probe_decision_replay_follow_through",
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "required_period_roles": ["validation", "research_oos"],
            "standard_l4_completion": (
                "runtime_probe_completed_with_tester_report_kpis_no_runtime_authority"
                if all_report_kpis_observed
                else "runtime_probe_observed_tester_report_kpis_incomplete_no_runtime_authority"
            ),
            "l5_continuation": "not_opened_loss_observed_and_no_candidate_evidence",
            "locked_final_oos_b": "not_used",
        },
        "prevention_memory": [
            "Preserved score-band proxy clues did not become tradeable under direct score_band_side replay.",
            "All direct-trade eligible Wave01 decision replay pairs lost in both validation and research_oos tester-log final balances.",
            "Parsed tester report PF/DD/trade metrics are observation evidence only and do not create economics pass.",
            "Open-failed actions are runtime friction evidence and must be audited before any future L5 review.",
            "Do not carry this losing decision replay forward as a new campaign without a genuinely new decision/risk/holding surface.",
        ],
        "negative_memory": {
            "memory_id": NEGATIVE_MEMORY_ID,
            "path": NEGATIVE_MEMORY_PATH.as_posix(),
        },
        "artifact_outputs": {
            "judgment_summary": JUDGMENT_SUMMARY.as_posix(),
            "judgment_index": JUDGMENT_INDEX.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "closeout": CLOSEOUT_PATH.as_posix(),
        },
        "environment": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **git_state(repo_root),
            "started_at_utc": started_at,
            "ended_at_utc": ended_at,
        },
        "forbidden_claims": [
            "selected_baseline",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "negative",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [
            JUDGMENT_SUMMARY.as_posix(),
            JUDGMENT_INDEX.as_posix(),
            NEGATIVE_MEMORY_PATH.as_posix(),
            EXECUTION_SUMMARY.as_posix(),
            EXECUTION_INDEX.as_posix(),
        ],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
        "forbidden_claims_respected": True,
    }


def upsert_negative_memory_registry(repo_root: Path, negative_memory: dict[str, Any]) -> None:
    registry_path = repo_root / NEGATIVE_MEMORY_REGISTRY
    rows = read_csv_rows(registry_path) if registry_path.exists() else []
    fieldnames = list(rows[0].keys()) if rows else [
        "memory_id",
        "hypothesis_id",
        "surface_id",
        "sweep_id",
        "run_id",
        "status",
        "evidence_path",
        "failed_boundary",
        "why_failed",
        "salvage_value",
        "reopen_condition",
        "do_not_repeat_note",
        "next_action",
    ]
    by_id = {row["memory_id"]: row for row in rows}
    by_id[negative_memory["memory_id"]] = {
        "memory_id": negative_memory["memory_id"],
        "hypothesis_id": negative_memory["hypothesis_id"],
        "surface_id": negative_memory["surface_id"],
        "sweep_id": negative_memory["sweep_id"],
        "run_id": negative_memory["run_id"],
        "status": "active_negative_memory",
        "evidence_path": negative_memory["evidence_path"],
        "failed_boundary": negative_memory["failed_boundary"],
        "why_failed": negative_memory["why_failed"],
        "salvage_value": negative_memory["salvage_value"],
        "reopen_condition": negative_memory["reopen_condition"],
        "do_not_repeat_note": negative_memory["do_not_repeat_note"],
        "next_action": "rotate_or_open_new_decision_policy_surface_not_same_candidate_repair",
    }
    write_csv(registry_path, list(by_id.values()), fieldnames)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path)
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
    producer = " ".join(summary["environment"]["command_argv"])

    def put(row: dict[str, Any]) -> None:
        full = repo_root / row["path_or_uri"]
        if full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        ("artifact_wave01_decision_replay_judgment_summary_v0", "decision_replay_judgment_summary", JUDGMENT_SUMMARY, "source-of-truth summary for Wave01 decision replay judgment"),
        ("artifact_wave01_decision_replay_judgment_index_v0", "decision_replay_judgment_index", JUDGMENT_INDEX, "cell-level validation/research_oos Wave01 decision replay judgment index"),
        ("artifact_wave01_decision_replay_judgment_closeout_v0", "work_closeout", CLOSEOUT_PATH, "closeout for Wave01 decision replay judgment subwork"),
        ("artifact_neg_wave01_event_barrier_score_band_decision_replay_loss_v0", "negative_memory", NEGATIVE_MEMORY_PATH, "negative memory for Wave01 score-band decision replay losses"),
        ("artifact_negative_memory_registry_v0", "negative_memory_registry", NEGATIVE_MEMORY_REGISTRY, "index of negative memory records"),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": JUDGMENT_SUMMARY.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def sync_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    state = git_state(repo_root)
    input_hashes = [
        artifact_ref(repo_root / EXECUTION_INDEX, repo_root),
        artifact_ref(repo_root / EXECUTION_SUMMARY, repo_root),
        artifact_ref(repo_root / SOURCE_PAIR_INDEX, repo_root),
    ]
    output_hashes = [
        artifact_ref(repo_root / JUDGMENT_SUMMARY, repo_root),
        artifact_ref(repo_root / JUDGMENT_INDEX, repo_root),
        artifact_ref(repo_root / NEGATIVE_MEMORY_PATH, repo_root),
        artifact_ref(repo_root / CLOSEOUT_PATH, repo_root),
    ]

    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["wave01_event_barrier_l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    current_truth["wave01_event_barrier_l4_decision_replay_judgment_status"] = summary["status"]
    current_truth["wave01_event_barrier_l4_decision_replay_judgment_counts"] = summary["counts"]
    current_truth["wave01_event_barrier_l4_decision_replay_negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
    current_truth["candidate_count"] = 0
    next_work["status"] = "wave01_decision_replay_judgment_completed_no_l5_candidates"
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work["branch_worktree"] = {
        "current_branch": state["branch"],
        "requested_branch": state["branch"],
        "branch_worktree_fit": "fit" if str(state["branch"]).startswith("codex/") else "unchecked_lowered_claim",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
    }
    next_work["execution_provenance"] = {
        "git_sha": state["git_sha"],
        "branch": state["branch"],
        "dirty_flag": state["dirty_flag"],
        "changed_files": state["changed_files"],
        "command_argv": summary["environment"]["command_argv"],
        "python_executable": summary["environment"]["python_executable"],
        "python_version": summary["environment"]["python_version"],
        "key_package_versions": summary["environment"]["dependency_summary"],
        "started_at_utc": summary["created_at_utc"],
        "ended_at_utc": summary["ended_at_utc"],
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_runtime_authority",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["active_phase"] = "wave01_event_barrier_decision_replay_judgment_completed"
    sources = resume.setdefault("current_truth_sources", [])
    for source in [
        JUDGMENT_SUMMARY.as_posix(),
        JUDGMENT_INDEX.as_posix(),
        NEGATIVE_MEMORY_PATH.as_posix(),
        CLOSEOUT_PATH.as_posix(),
        NEGATIVE_MEMORY_REGISTRY.as_posix(),
    ]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "negative",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [JUDGMENT_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
    }
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = "wave01_event_barrier_decision_replay_judgment_completed"
    event_barrier = goal.setdefault("event_barrier_campaign", {})
    event_barrier["l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    event_barrier["l4_decision_replay_judgment_status"] = summary["status"]
    event_barrier["l4_decision_replay_judgment_counts"] = summary["counts"]
    event_barrier["negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
    event_barrier["next_work_item"] = PARENT_WORK_ITEM_ID
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = "wave01_event_barrier_decision_replay_judgment_completed"
    claims["wave01_event_barrier_l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    claims["wave01_event_barrier_l4_decision_replay_judgment_status"] = summary["status"]
    claims["wave01_event_barrier_l4_decision_replay_judgment_counts"] = summary["counts"]
    claims["wave01_event_barrier_negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
    claims["wave01_event_barrier_candidate_count"] = 0
    claims["wave01_event_barrier_next_work_item"] = PARENT_WORK_ITEM_ID
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        rows = read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = "wave01_event_barrier_decision_replay_judgment_completed"
                row["next_work_item"] = PARENT_WORK_ITEM_ID
        if rows:
            write_csv(repo_root / GOAL_REGISTRY, rows, list(rows[0].keys()))


def judge(repo_root: Path, *, started_at: str, command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = build_judgment_rows(repo_root)
    summary = build_summary(repo_root, rows, started_at=started_at, command_argv=command_argv)
    negative_memory = build_negative_memory(rows)
    write_csv(repo_root / JUDGMENT_INDEX, rows, judgment_index_fieldnames())
    write_yaml(repo_root / JUDGMENT_SUMMARY, summary)
    write_yaml(repo_root / NEGATIVE_MEMORY_PATH, negative_memory)
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_negative_memory_registry(repo_root, negative_memory)
    upsert_artifact_registry(repo_root, summary)
    return summary, rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge Wave01 score-band decision replay results.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main())
