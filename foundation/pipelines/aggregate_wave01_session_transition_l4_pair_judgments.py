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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_session_transition_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_session_transition_l4_pair_judgment_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through")
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
PAIR_SUMMARY = OUTPUT_DIR / "l4_pair_judgment_summary.yaml"
PAIR_INDEX = OUTPUT_DIR / "l4_pair_judgment_index.csv"
PAIR_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave01_session_transition_l4_pair_judgment_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
RUN_REFS = OUTPUT_DIR.parent / "sweeps" / SWEEP_ID / "run_refs.csv"
CLAIM_BOUNDARY = "wave01_session_transition_l4_pair_score_observation_judgment_only_no_runtime_authority_no_economics_pass_no_candidate"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return redact_path(str(path))


def artifact_ref(path: Path, repo_root: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else repo_root / path
    return {
        "path": rel(full, repo_root),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


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


def first_scalar(mapping: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def run_refs_by_id(repo_root: Path) -> dict[str, dict[str, str]]:
    refs_path = repo_root / RUN_REFS
    if not refs_path.exists():
        return {}
    return {row["run_id"]: row for row in read_csv_rows(refs_path)}


def proxy_report_for_run(repo_root: Path, run_ref: dict[str, str]) -> dict[str, Any]:
    if not run_ref:
        return {}
    evidence_path = run_ref.get("evidence_path")
    if evidence_path and (repo_root / evidence_path).exists():
        return load_json(repo_root / evidence_path)
    manifest_path = repo_root / run_ref.get("run_manifest_path", "") if run_ref.get("run_manifest_path") else None
    if not manifest_path:
        return {}
    candidate = manifest_path.parent / "reports" / "proxy_session_transition_report.json"
    return load_json(candidate) if candidate.exists() else {}


def bundle_for_row(repo_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    path = repo_root / "runtime" / "packages" / row["bundle_id"] / "experiment_bundle.json"
    return load_json(path) if path.exists() else {}


def score_summary_for_row(repo_root: Path, row: dict[str, str]) -> dict[str, Any]:
    path = repo_root / row["score_telemetry_summary_path"]
    return load_yaml(path) if path.exists() else {}


def runtime_progress_contract(repo_root: Path, pair_rows: list[dict[str, Any]]) -> dict[str, Any]:
    runtime_summary_path = repo_root / RUNTIME_SUMMARY
    runtime_summary = load_yaml(runtime_summary_path) if runtime_summary_path.exists() else {}
    counts = runtime_summary.get("counts", {}) if isinstance(runtime_summary, dict) else {}
    required_roles = first_scalar(runtime_summary, "runtime_contract_binding", "required_period_roles", default=[])
    role_count = len(required_roles) if isinstance(required_roles, list) and required_roles else 2
    prepared_attempt_count = int(counts.get("prepared_attempt_count") or len(pair_rows) * role_count)
    expected_pair_count = int(prepared_attempt_count / role_count) if role_count else len(pair_rows)
    nonempty_pair_count = sum(row["nonempty_telemetry_pair"] == "true" for row in pair_rows)
    remaining_pair_count = max(0, expected_pair_count - nonempty_pair_count)
    runtime_status = str(runtime_summary.get("status") or "")
    complete = remaining_pair_count == 0 and runtime_status != "partial_l4_terminal_execution_started"
    return {
        "runtime_execution_summary": RUNTIME_SUMMARY.as_posix() if runtime_summary_path.exists() else "",
        "runtime_execution_status": runtime_status,
        "prepared_attempt_count": prepared_attempt_count,
        "expected_cell_pair_count": expected_pair_count,
        "nonempty_pair_count": nonempty_pair_count,
        "remaining_cell_pair_count": remaining_pair_count,
        "all_prepared_pairs_observed": complete,
    }


def classify_proxy_runtime(proxy_judgment: str, both_observed: bool, nonempty_pair: bool) -> str:
    if not both_observed:
        return "proxy_observed_runtime_score_missing_or_partial"
    if not nonempty_pair:
        return "proxy_observed_runtime_score_empty"
    if proxy_judgment == "preserved_clue":
        return "proxy_preserved_clue_runtime_score_observed"
    if proxy_judgment == "inconclusive":
        return "proxy_inconclusive_runtime_score_observed"
    if proxy_judgment == "negative":
        return "proxy_negative_runtime_score_observed"
    if proxy_judgment == "positive":
        return "proxy_positive_runtime_score_observed_without_trading_report"
    return "proxy_unclassified_runtime_score_observed"


def proxy_metric(proxy: dict[str, Any]) -> tuple[str, Any]:
    validation = proxy.get("validation_metrics", {})
    for key in ["roc_auc", "spearman_corr", "balanced_accuracy", "average_precision"]:
        if key in validation:
            return key, validation[key]
    return "", ""


def l5_routing_decision(
    *,
    both_observed: bool,
    nonempty_pair: bool,
    tester_reports_observed: bool,
    proxy_judgment: str,
    decision_unknown: bool,
) -> tuple[str, str]:
    if not both_observed or not nonempty_pair:
        return (
            "no_l5_runtime_score_missing_or_empty",
            "repair_or_rerun_missing_or_empty_L4_score_telemetry_before_any_L5_routing",
        )
    if not tester_reports_observed:
        if proxy_judgment == "preserved_clue":
            return (
                "no_l5_yet_preserved_clue_requires_decision_execution_adapter",
                "prepare a bounded Wave01 decision/trading execution adapter for preserved clues before any L5 candidate claim",
            )
        return (
            "no_l5_score_probe_only",
            "record L4 score observation and rotate unless a new decision-execution surface is opened",
        )
    if decision_unknown:
        return (
            "no_l5_decision_mapping_unknown",
            "repair decision mapping before candidate-specific L5 evidence",
        )
    if proxy_judgment == "preserved_clue":
        return (
            "l5_candidate_review_required_not_auto_promoted",
            "open candidate-specific L5 manifest only after decision/economics surface is declared",
        )
    return ("no_l5_not_promising_enough", "record L4 runtime observation and rotate")


def aggregate_pairs(repo_root: Path, *, started_at_utc: str, command_argv: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runtime_rows = read_csv_rows(repo_root / RUNTIME_INDEX)
    rows_by_cell: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in runtime_rows:
        rows_by_cell[row["cell_id"]].append(row)

    refs = run_refs_by_id(repo_root)
    pair_rows: list[dict[str, Any]] = []
    for cell_id in sorted(rows_by_cell):
        period_rows = {row["period_role"]: row for row in rows_by_cell[cell_id]}
        validation = period_rows.get("validation", {})
        research = period_rows.get("research_oos", {})
        anchor = validation or research
        run_id = anchor.get("run_id", "")
        bundle_id = anchor.get("bundle_id", "")
        proxy = proxy_report_for_run(repo_root, refs.get(run_id, {}))
        bundle = bundle_for_row(repo_root, anchor) if anchor else {}
        validation_summary = score_summary_for_row(repo_root, validation) if validation else {}
        research_summary = score_summary_for_row(repo_root, research) if research else {}
        validation_stats = validation_summary.get("stats", {})
        research_stats = research_summary.get("stats", {})
        decision_surface = bundle.get("decision_surface", {})
        axis_values = proxy.get("axis_values", {})
        proxy_judgment = str(proxy.get("validation_judgment") or proxy.get("result_judgment") or refs.get(run_id, {}).get("result_judgment") or "")
        decision_family = str(decision_surface.get("decision_family") or axis_values.get("decision_family") or "")
        both_observed = boolish(validation.get("telemetry_observed")) and boolish(research.get("telemetry_observed"))
        validation_rows = int(first_scalar(validation_stats, "row_count", default=0) or 0)
        research_rows = int(first_scalar(research_stats, "row_count", default=0) or 0)
        nonempty_pair = validation_rows > 0 and research_rows > 0
        tester_reports_observed = boolish(validation.get("tester_report_observed")) and boolish(research.get("tester_report_observed"))
        validation_decisions = validation_stats.get("decision_counts", {})
        research_decisions = research_stats.get("decision_counts", {})
        decision_unknown = set(validation_decisions) == {"unknown"} and set(research_decisions) == {"unknown"}
        comparison_class = classify_proxy_runtime(proxy_judgment, both_observed, nonempty_pair)
        l5_status, next_action = l5_routing_decision(
            both_observed=both_observed,
            nonempty_pair=nonempty_pair,
            tester_reports_observed=tester_reports_observed,
            proxy_judgment=proxy_judgment,
            decision_unknown=decision_unknown,
        )
        metric_key, metric_value = proxy_metric(proxy)
        pair_rows.append(
            {
                "cell_id": cell_id,
                "run_id": run_id,
                "bundle_id": bundle_id,
                "validation_attempt_id": validation.get("attempt_id", ""),
                "research_oos_attempt_id": research.get("attempt_id", ""),
                "validation_telemetry_observed": str(boolish(validation.get("telemetry_observed"))).lower(),
                "research_oos_telemetry_observed": str(boolish(research.get("telemetry_observed"))).lower(),
                "both_period_roles_observed": str(both_observed).lower(),
                "nonempty_telemetry_pair": str(nonempty_pair).lower(),
                "validation_row_count": validation_rows,
                "research_oos_row_count": research_rows,
                "validation_score_mean": first_scalar(validation_stats, "score_stats", "mean", default=""),
                "research_oos_score_mean": first_scalar(research_stats, "score_stats", "mean", default=""),
                "validation_score_min": first_scalar(validation_stats, "score_stats", "min", default=""),
                "validation_score_max": first_scalar(validation_stats, "score_stats", "max", default=""),
                "research_oos_score_min": first_scalar(research_stats, "score_stats", "min", default=""),
                "research_oos_score_max": first_scalar(research_stats, "score_stats", "max", default=""),
                "validation_decision_counts": json.dumps(validation_decisions, sort_keys=True),
                "research_oos_decision_counts": json.dumps(research_decisions, sort_keys=True),
                "decision_family": decision_family,
                "decision_mapping_status": "unknown_in_score_probe" if decision_unknown else "mapped_or_observed",
                "proxy_judgment": proxy_judgment,
                "proxy_validation_metric_key": metric_key,
                "proxy_validation_metric": metric_value,
                "comparison_class": comparison_class,
                "standard_l4_completion": "incomplete_tester_report_missing" if not tester_reports_observed else "completed_with_report_observed",
                "result_judgment": "runtime_probe" if both_observed and nonempty_pair else "inconclusive",
                "l5_routing_status": l5_status,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": next_action,
            }
        )

    ended_at = utc_now()
    status_counts = Counter(row["l5_routing_status"] for row in pair_rows)
    comparison_counts = Counter(row["comparison_class"] for row in pair_rows)
    proxy_counts = Counter(row["proxy_judgment"] for row in pair_rows)
    progress = runtime_progress_contract(repo_root, pair_rows)
    missing_evidence = [
        "tester_reports_missing_for_all_pairs",
        "decision_execution_adapter_not_yet_applied_to_preserved_clues",
        "row_level_proxy_vs_MT5_score_alignment_not_performed",
        "economics_metrics_not_available_from_non_trading_score_probe",
    ]
    if not progress["all_prepared_pairs_observed"]:
        missing_evidence.insert(0, "remaining_prepared_L4_attempt_pairs")
    is_complete_pair_judgment = bool(progress["all_prepared_pairs_observed"])
    status = (
        "wave01_session_transition_l4_pair_judgment_completed_no_l5_candidates"
        if is_complete_pair_judgment
        else "wave01_session_transition_l4_pair_judgment_partial_progress"
    )
    next_action = (
        "prepare bounded Wave01 decision/trading execution adapter for preserved clues before any L5 candidate claim"
        if is_complete_pair_judgment
        else "continue running remaining prepared Wave01 L4 Strategy Tester attempts before final pair judgment"
    )
    summary = {
        "version": "wave01_session_transition_l4_pair_judgment_summary_v1",
        "summary_id": "wave01_session_transition_l4_pair_judgment_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at,
        "status": status,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": {
            "cell_pair_count": len(pair_rows),
            "expected_cell_pair_count": progress["expected_cell_pair_count"],
            "remaining_cell_pair_count": progress["remaining_cell_pair_count"],
            "both_period_roles_observed_count": sum(row["both_period_roles_observed"] == "true" for row in pair_rows),
            "nonempty_telemetry_pair_count": sum(row["nonempty_telemetry_pair"] == "true" for row in pair_rows),
            "tester_report_pair_observed_count": sum(row["standard_l4_completion"] == "completed_with_report_observed" for row in pair_rows),
            "standard_l4_incomplete_count": sum(row["standard_l4_completion"] != "completed_with_report_observed" for row in pair_rows),
            "decision_unknown_pair_count": sum(row["decision_mapping_status"] == "unknown_in_score_probe" for row in pair_rows),
            "proxy_judgment_counts": dict(sorted(proxy_counts.items())),
            "l5_status_counts": dict(sorted(status_counts.items())),
            "comparison_class_counts": dict(sorted(comparison_counts.items())),
        },
        "runtime_progress_contract": progress,
        "judgment": {
            "result_subject": "Wave01 session-transition first-batch L4 score telemetry pair aggregation",
            "judgment_label": "runtime_probe" if is_complete_pair_judgment else "runtime_probe_progress",
            "metric_identity": "paired validation/research_oos MT5 score telemetry summaries; no trading report/economics metric",
            "comparison_baseline": "source proxy validation judgment plus MT5 score-observation presence",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": missing_evidence,
            "next_action": next_action,
        },
        "runtime_contract_effect": {
            "l4_score_observation": "observed_nonempty_for_all_pairs" if is_complete_pair_judgment else "observed_nonempty_for_indexed_pairs_only",
            "standard_l4_completion": "not_claimed_tester_reports_missing",
            "l5_continuation": "not_opened_until_decision_execution_adapter_observed" if is_complete_pair_judgment else "not_opened_partial_l4_batch",
            "locked_final_oos_b": "not_used",
        },
        "prevention_memory": [
            "empty score telemetry must not count as completed L4 telemetry",
            "Wave01 EA adapter must include every declared feature column before L4 rerun",
            "score telemetry observation is useful runtime evidence but is not Strategy Tester economics evidence",
            "unknown score-probe decision mapping keeps preserved clues below L5 candidate status",
        ],
        "artifact_outputs": {
            "pair_summary": PAIR_SUMMARY.as_posix(),
            "pair_index": PAIR_INDEX.as_posix(),
            "runtime_execution_index": RUNTIME_INDEX.as_posix(),
        },
        "environment": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **git_state(repo_root),
            "started_at_utc": started_at_utc,
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
    return summary, pair_rows


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
        "validation_row_count",
        "research_oos_row_count",
        "validation_score_mean",
        "research_oos_score_mean",
        "validation_score_min",
        "validation_score_max",
        "research_oos_score_min",
        "research_oos_score_max",
        "validation_decision_counts",
        "research_oos_decision_counts",
        "decision_family",
        "decision_mapping_status",
        "proxy_judgment",
        "proxy_validation_metric_key",
        "proxy_validation_metric",
        "comparison_class",
        "standard_l4_completion",
        "result_judgment",
        "l5_routing_status",
        "claim_boundary",
        "next_action",
    ]


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


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
        path_value = row.get("path_or_uri")
        full = repo_root / path_value if path_value else None
        if full and full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        (
            "artifact_wave01_session_transition_l4_pair_judgment_summary_v0",
            "l4_pair_judgment_summary",
            PAIR_SUMMARY,
            "source-of-truth summary for Wave01 paired L4 score-observation judgment",
        ),
        (
            "artifact_wave01_session_transition_l4_pair_judgment_index_v0",
            "l4_pair_judgment_index",
            PAIR_INDEX,
            "compact index of Wave01 paired validation/research_oos L4 judgments",
        ),
        (
            "artifact_wave01_session_transition_l4_pair_judgment_closeout_v0",
            "work_closeout",
            PAIR_CLOSEOUT,
            "closeout for Wave01 L4 pair judgment subwork",
        ),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": PAIR_SUMMARY.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    state = git_state(repo_root)
    output_hashes = [
        artifact_ref(repo_root / PAIR_SUMMARY, repo_root),
        artifact_ref(repo_root / PAIR_INDEX, repo_root),
        artifact_ref(repo_root / PAIR_CLOSEOUT, repo_root),
    ]
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["wave01_session_transition_l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    current_truth["wave01_session_transition_l4_pair_judgment_status"] = summary["status"]
    current_truth["wave01_session_transition_l4_pair_judgment_counts"] = summary["counts"]
    is_complete_pair_judgment = bool(summary["runtime_progress_contract"]["all_prepared_pairs_observed"])
    next_work["status"] = (
        "wave01_session_transition_l4_pair_judgment_completed_decision_adapter_required"
        if is_complete_pair_judgment
        else "l4_strategy_tester_execution_in_progress"
    )
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
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
        "input_hashes": [artifact_ref(repo_root / RUNTIME_INDEX, repo_root)],
        "output_hashes": output_hashes,
        "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_runtime_authority",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix(), PAIR_CLOSEOUT.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [PAIR_SUMMARY.as_posix(), PAIR_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    phase = (
        "wave01_session_transition_l4_pair_judgment_completed_decision_adapter_required"
        if is_complete_pair_judgment
        else "wave01_session_transition_l4_terminal_execution_in_progress"
    )
    goal["active_phase"] = phase
    session_transition = goal.setdefault("session_transition_campaign", {})
    session_transition["l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    session_transition["l4_pair_judgment_status"] = summary["status"]
    session_transition["l4_pair_judgment_counts"] = summary["counts"]
    session_transition["next_work_item"] = WORK_ITEM_ID
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = phase
    claims["wave0_third_campaign_L4_status"] = (
        "L4_pair_judgment_completed_decision_adapter_required"
        if is_complete_pair_judgment
        else "L4_terminal_execution_in_progress"
    )
    claims["wave0_third_campaign_l4_pair_judgment_summary"] = PAIR_SUMMARY.as_posix()
    claims["wave0_third_campaign_l4_pair_judgment_status"] = summary["status"]
    claims["wave0_third_campaign_l4_pair_judgment_counts"] = summary["counts"]
    claims["wave0_third_campaign_next_work_item"] = WORK_ITEM_ID
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = phase
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave01_session_transition_l4_pair_judgment_not_goal_achieve"
        if goal_rows:
            write_csv(repo_root / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Wave01 session-transition L4 validation/research_oos pair judgments.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/aggregate_wave01_session_transition_l4_pair_judgments.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    summary, rows = aggregate_pairs(repo_root, started_at_utc=started_at, command_argv=command_argv)
    write_yaml(repo_root / PAIR_SUMMARY, summary)
    write_csv(repo_root / PAIR_INDEX, rows, pair_index_fieldnames())
    write_yaml(repo_root / PAIR_CLOSEOUT, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary)
    if args.write_control_records:
        update_control_records(repo_root, summary)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": PAIR_SUMMARY.as_posix(),
                "pair_count": len(rows),
                "nonempty_telemetry_pair_count": summary["counts"]["nonempty_telemetry_pair_count"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

