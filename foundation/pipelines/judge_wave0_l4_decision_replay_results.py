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


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
PARENT_WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
WORK_ITEM_ID = "work_wave0_l4_decision_replay_judgment_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
SURFACE_ID = "surface_us100_task_input_decision_rotation_v0"
HYPOTHESIS_ID = "hyp_surface_diversity_before_model_search_v0"
INITIAL_DEPOSIT = 500.0

CAMPAIGN_ROOT = Path("lab/campaigns/campaign_us100_task_surface_scout_v0")
SYNTHESIS_DIR = CAMPAIGN_ROOT / "synthesis"
L4_DIR = CAMPAIGN_ROOT / "l4_follow_through"
EXECUTION_INDEX = SYNTHESIS_DIR / "decision_replay_runtime_execution_index.csv"
EXECUTION_SUMMARY = SYNTHESIS_DIR / "decision_replay_runtime_execution_summary.yaml"
SOURCE_PAIR_INDEX = L4_DIR / "l4_pair_judgment_index.csv"
JUDGMENT_SUMMARY = SYNTHESIS_DIR / "decision_replay_judgment_summary.yaml"
JUDGMENT_INDEX = SYNTHESIS_DIR / "decision_replay_judgment_index.csv"
CLOSEOUT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_decision_replay_judgment_v0_closeout.yaml")
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative/neg_wave0_decision_replay_momentum_ret_1_loss_v0.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
NEGATIVE_MEMORY_REGISTRY = Path("docs/registers/negative_memory_registry.csv")

CLAIM_BOUNDARY = "decision_replay_judgment_log_balance_only_no_runtime_authority_no_economics_pass_no_candidate"
NEGATIVE_MEMORY_ID = "neg_wave0_decision_replay_momentum_ret_1_loss_v0"


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


def balance_delta(final_balance: float | None, *, initial_deposit: float = INITIAL_DEPOSIT) -> float | None:
    if final_balance is None:
        return None
    return round(final_balance - initial_deposit, 2)


def classify_decision_pair(validation_final_balance: float | None, research_oos_final_balance: float | None) -> dict[str, str]:
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
            "divergence_judgment": "mt5_decision_replay_negative_under_naive_momentum_direction",
            "next_action": "record negative memory and rotate to a new surface or new decision policy; do not continue this recipe to L5",
        }
    if validation_final_balance >= INITIAL_DEPOSIT and research_oos_final_balance >= INITIAL_DEPOSIT:
        return {
            "final_balance_pair_class": "non_loss_in_validation_and_research_oos",
            "result_judgment": "preserved_clue",
            "l5_routing_status": "l5_review_required_not_auto_candidate",
            "comparison_class": "proxy_preserved_clue_runtime_decision_non_loss_observed",
            "divergence_judgment": "mt5_decision_replay_requires_report_equity_confirmation",
            "next_action": "open candidate-specific review only after tester report/equity evidence is present",
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
        classification = classify_decision_pair(validation_balance, research_balance)
        missing = [
            "tester_report_missing",
            "equity_curve_missing",
            "pf_dd_metrics_missing",
            "locked_final_oos_b_not_used",
        ]
        prevention = [
            "preserved score clue does not imply tradeability under a naive score-replay decision adapter",
            "momentum_ret_1 direction proxy should not be reused as an L5 gate without new decision-policy evidence",
            "tester log final balance can support negative memory but cannot create economics pass without report/equity metrics",
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
                "validation_open_failed_count": validation.get("open_failed_count", ""),
                "research_oos_open_failed_count": research.get("open_failed_count", ""),
                "validation_execution_telemetry_observed": str(boolish(validation.get("execution_telemetry_observed"))).lower(),
                "research_oos_execution_telemetry_observed": str(boolish(research.get("execution_telemetry_observed"))).lower(),
                "validation_tester_log_observed": str(boolish(validation.get("tester_log_observed"))).lower(),
                "research_oos_tester_log_observed": str(boolish(research.get("tester_log_observed"))).lower(),
                "validation_tester_report_observed": str(boolish(validation.get("tester_report_observed"))).lower(),
                "research_oos_tester_report_observed": str(boolish(research.get("tester_report_observed"))).lower(),
                "both_period_roles_observed": str(bool(validation and research)).lower(),
                "both_tester_logs_observed": str(
                    boolish(validation.get("tester_log_observed")) and boolish(research.get("tester_log_observed"))
                ).lower(),
                "tester_report_pair_observed": str(
                    boolish(validation.get("tester_report_observed")) and boolish(research.get("tester_report_observed"))
                ).lower(),
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
        "validation_execution_telemetry_observed",
        "research_oos_execution_telemetry_observed",
        "validation_tester_log_observed",
        "research_oos_tester_log_observed",
        "validation_tester_report_observed",
        "research_oos_tester_report_observed",
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
    return {
        "version": "negative_memory_v1",
        "memory_id": NEGATIVE_MEMORY_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "run_id": ";".join(run_ids),
        "failed_boundary": "score_replay_sparse_decision_momentum_ret_1_validation_and_research_oos",
        "why_failed": (
            "All tested preserved-clue tradeability cells using the naive momentum_ret_1 score replay decision adapter "
            "ended below the 500 USD tester deposit in both validation and research_oos tester-log final balances."
        ),
        "salvage_value": (
            "Confirms the MT5 sparse decision execution path can run and records that score-observed preserved clues "
            "do not automatically become tradeable when replayed with a naive momentum direction policy."
        ),
        "reopen_condition": (
            "Reopen only with a genuinely new decision/risk/holding policy, report/equity parser evidence, "
            "or a new surface question; do not relabel the same momentum_ret_1 replay as a new candidate."
        ),
        "do_not_repeat_note": (
            "Do not promote momentum_ret_1 score replay of preserved score clues to L5/candidate/economics "
            "without new decision-policy evidence and tester report/equity metrics."
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
    total_open = sum(int(row["validation_open_action_count"] or 0) + int(row["research_oos_open_action_count"] or 0) for row in rows)
    total_close = sum(int(row["validation_close_action_count"] or 0) + int(row["research_oos_close_action_count"] or 0) for row in rows)
    return {
        "version": "decision_replay_judgment_summary_v1",
        "summary_id": "wave0_l4_decision_replay_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at,
        "ended_at_utc": ended_at,
        "status": "decision_replay_judgment_completed_no_l5_candidates",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "cell_pair_count": len(rows),
            "negative_count": judgment_counts.get("negative", 0),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "tester_log_pair_observed_count": sum(row["both_tester_logs_observed"] == "true" for row in rows),
            "tester_report_pair_observed_count": sum(row["tester_report_pair_observed"] == "true" for row in rows),
            "loss_in_both_periods_count": balance_counts.get("loss_in_validation_and_research_oos", 0),
            "open_action_count": total_open,
            "close_action_count": total_close,
            "result_judgment_counts": dict(sorted(judgment_counts.items())),
            "l5_routing_status_counts": dict(sorted(l5_counts.items())),
            "final_balance_pair_class_counts": dict(sorted(balance_counts.items())),
        },
        "judgment": {
            "result_subject": "Wave01 preserved-clue sparse decision replay over validation and research_oos",
            "judgment_label": "negative",
            "metric_identity": "MT5 tester-log final_balance from score replay decision probes; no tester report/equity/PF/DD claim",
            "comparison_baseline": "500 USD initial deposit under us100_m5_fpmarkets_tester_execution_v0",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "tester_reports_missing_for_all_decision_replay_pairs",
                "equity_curve_missing",
                "pf_dd_trade_list_metrics_missing",
                "locked_final_oos_b_not_used",
            ],
            "next_action": (
                "Record negative memory, keep candidate count at zero, and rotate to a new multi-axis surface or "
                "a genuinely new decision-policy question. Do not continue momentum_ret_1 score replay to L5."
            ),
        },
        "runtime_contract_effect": {
            "runtime_level": "score_replay_decision_probe_not_standard_l4_completion",
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "required_period_roles": ["validation", "research_oos"],
            "standard_l4_completion": "not_claimed_tester_reports_missing",
            "l5_continuation": "not_opened_loss_observed_and_no_candidate_evidence",
            "locked_final_oos_b": "not_used",
        },
        "prevention_memory": [
            "A preserved score telemetry clue does not imply a tradeable sparse decision policy.",
            "Naive momentum_ret_1 direction mapping produced losses across all tested preserved tradeability cells.",
            "Tester log final_balance may support negative memory, but report/equity evidence is required before PF/DD/economics claims.",
            "Do not carry a losing decision replay forward as a new campaign without a genuinely new decision/risk/holding surface.",
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
        ("artifact_wave0_l4_decision_replay_judgment_summary_v0", "decision_replay_judgment_summary", JUDGMENT_SUMMARY, "source-of-truth summary for decision replay judgment"),
        ("artifact_wave0_l4_decision_replay_judgment_index_v0", "decision_replay_judgment_index", JUDGMENT_INDEX, "cell-level validation/research_oos decision replay judgment index"),
        ("artifact_wave0_l4_decision_replay_judgment_closeout_v0", "work_closeout", CLOSEOUT_PATH, "closeout for decision replay judgment subwork"),
        ("artifact_neg_wave0_decision_replay_momentum_ret_1_loss_v0", "negative_memory", NEGATIVE_MEMORY_PATH, "negative memory for naive momentum_ret_1 score replay decision loss"),
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
    current_truth["l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    current_truth["l4_decision_replay_judgment_status"] = summary["status"]
    current_truth["l4_decision_replay_judgment_counts"] = summary["counts"]
    current_truth["l4_decision_replay_negative_memory"] = NEGATIVE_MEMORY_PATH.as_posix()
    current_truth["candidate_count"] = 0
    next_work["status"] = "decision_replay_judgment_completed_no_l5_candidates"
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work["branch_worktree"] = {
        "current_branch": state["branch"],
        "requested_branch": state["branch"],
        "branch_worktree_fit": "fit" if str(state["branch"]).startswith("codex/") else "unchecked_lowered_claim",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "no_branch_mismatch_detected_for_decision_replay_judgment"
        if str(state["branch"]).startswith("codex/")
        else "main_branch_used_lowers_boundary_until_boundary_commit",
    }
    next_work["agent_allocation"] = {
        "phase": "wave0_l4_decision_replay_judgment",
        "selected_agents": [],
        "role_modes": [],
        "selection_reason": "Deterministic evidence judgment over executed MT5 decision replay attempts; no protected promotion or policy change required.",
        "why_not_smaller": "Codex alone is the smallest allocation for evidence aggregation and registry sync.",
        "why_not_larger": "No runtime authority, economics pass, reviewed/pass, promotion, or cross-system handoff claim is being made.",
        "max_threads_is_capacity_only": True,
        "claim_effect": "no_new_advisory_claim",
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
    resume["active_phase"] = "wave01_operating_proof_window_decision_replay_judgment_completed"
    sources = resume.setdefault("current_truth_sources", [])
    for source in [JUDGMENT_SUMMARY.as_posix(), JUDGMENT_INDEX.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), CLOSEOUT_PATH.as_posix(), NEGATIVE_MEMORY_REGISTRY.as_posix()]:
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
    goal["active_phase"] = "wave01_operating_proof_window_decision_replay_judgment_completed"
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    wave_spec["l4_decision_replay_judgment_status"] = summary["status"]
    wave_spec["l4_decision_replay_judgment_counts"] = summary["counts"]
    wave_spec["negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = "wave01_operating_proof_window_decision_replay_judgment_completed"
    claims["wave0_l4_decision_replay_judgment_summary"] = JUDGMENT_SUMMARY.as_posix()
    claims["wave0_l4_decision_replay_judgment_status"] = summary["status"]
    claims["wave0_l4_decision_replay_judgment_counts"] = summary["counts"]
    claims["wave0_negative_memory_ids"] = [NEGATIVE_MEMORY_ID]
    claims["wave0_candidate_count"] = 0
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        rows = read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = "wave01_operating_proof_window_decision_replay_judgment_completed"
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
    parser = argparse.ArgumentParser(description="Judge Wave01 L4 decision replay results and record negative memory.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/judge_wave0_l4_decision_replay_results.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    summary, rows = judge(repo_root, started_at=started_at, command_argv=command_argv)
    if args.write_control_records:
        sync_control_records(repo_root, summary)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": JUDGMENT_SUMMARY.as_posix(),
                "cell_pair_count": len(rows),
                "negative_count": summary["counts"]["negative_count"],
                "candidate_count": summary["counts"]["candidate_count"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
